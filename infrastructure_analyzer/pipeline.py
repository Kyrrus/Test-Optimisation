"""Étapes du pipeline d'analyse de l'infrastructure."""

import json
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from statistics import fmean

from ollama import chat
from pydantic import ValidationError

from .config import DEFAULT_OLLAMA_MODEL, SERVICES, THRESHOLD_RULES, ThresholdRule
from .models import (
    Anomaly,
    Insights,
    LogRecord,
    OutputReport,
    Recommendation,
    RecommendationResponse,
    ServiceStatusSummary,
    Severity,
)


def ingest_data(input_path: str | Path) -> list[LogRecord]:
    """Lit, valide et trie chronologiquement les relevés JSON."""

    path = Path(input_path)

    try:
        raw_data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Fichier introuvable : {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Le fichier {path} ne contient pas un JSON valide.") from error

    if not isinstance(raw_data, list) or not raw_data:
        raise ValueError("Le fichier doit contenir une liste non vide de relevés.")

    try:
        records = [LogRecord.model_validate(item) for item in raw_data]
    except ValidationError as error:
        raise ValueError(f"Données d’entrée invalides :\n{error}") from error

    records.sort(key=lambda record: record.timestamp)

    timestamps = [record.timestamp for record in records]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("Le fichier contient au moins un timestamp dupliqué.")

    return records


def compute_insights(records: list[LogRecord]) -> Insights:
    """Calcule les indicateurs agrégés demandés dans le sujet."""

    latest_record = records[-1]

    return Insights(
        average_latency_ms=round(fmean(r.latency_ms for r in records), 3),
        max_cpu_usage=max(r.cpu_usage for r in records),
        max_memory_usage=max(r.memory_usage for r in records),
        error_rate=round(fmean(r.error_rate for r in records), 3),
        uptime_seconds=latest_record.uptime_seconds,
    )


def get_severity(value: float, rule: ThresholdRule) -> Severity | None:
    """Retourne la sévérité correspondant à une valeur et à ses seuils."""

    if value >= rule.high:
        return "high"
    if value >= rule.medium:
        return "medium"
    if value >= rule.low:
        return "low"
    return None


def detect_anomalies(records: list[LogRecord]) -> list[Anomaly]:
    """Produit au maximum une anomalie agrégée par métrique."""

    anomalies: list[Anomaly] = []

    for rule in THRESHOLD_RULES:
        values = [float(getattr(record, rule.metric)) for record in records]
        maximum = max(values)
        severity = get_severity(maximum, rule)

        if severity is None:
            continue

        active_threshold = float(getattr(rule, severity))
        occurrence_count = sum(value >= active_threshold for value in values)

        anomalies.append(
            Anomaly(
                metric=rule.metric,
                value=maximum,
                threshold=active_threshold,
                severity=severity,
                description=(
                    f"{rule.metric} : pic de {maximum:g}. "
                    f"{occurrence_count}/{len(records)} relevés atteignent ou "
                    f"dépassent le seuil {severity} de {active_threshold:g}."
                ),
            )
        )

    return anomalies


@dataclass(frozen=True)
class ServiceAnalysis:
    current_status: ServiceStatusSummary
    incidents: dict[str, dict[str, int]]


def summarize_services(records: list[LogRecord]) -> ServiceAnalysis:
    """Résume l’état actuel et compte les incidents historiques."""

    current_status: dict[str, list[str]] = {
        "online": [],
        "degraded": [],
        "offline": [],
    }
    incidents = {
        service: {"degraded": 0, "offline": 0}
        for service in SERVICES
    }

    latest_record = records[-1]
    for service in SERVICES:
        status = getattr(latest_record.service_status, service)
        current_status[status].append(service)

    for record in records:
        for service in SERVICES:
            status = getattr(record.service_status, service)
            if status in ("degraded", "offline"):
                incidents[service][status] += 1

    return ServiceAnalysis(
        current_status=ServiceStatusSummary.model_validate(current_status),
        incidents=incidents,
    )


def generate_recommendations(
    insights: Insights,
    anomalies: list[Anomaly],
    service_analysis: ServiceAnalysis,
    model: str = DEFAULT_OLLAMA_MODEL,
) -> list[Recommendation]:
    """Demande à Ollama de produire les recommandations structurées."""

    context = {
        "global_insights": insights.model_dump(mode="json"),
        "global_anomalies": [
            anomaly.model_dump(mode="json") for anomaly in anomalies
        ],
        "service_incidents": service_analysis.incidents,
    }

    response = chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es un ingénieur infrastructure. Produis en français de 3 à 5 "
                    "recommandations prioritaires, concrètes et applicables pour optimiser "
                    "l'infrastructure à partir du JSON. Tu peux proposer une solution "
                    "raisonnable même si la cause exacte n'est pas connue.\n\n"
                    "- Une recommandation liée à global_anomalies a target "
                    "'infrastructure'. Tu peux proposer répartition de charge, autoscaling, "
                    "ajustement de ressources, nettoyage du stockage, optimisation des "
                    "entrées/sorties ou refroidissement.\n"
                    "- Une recommandation liée à service_incidents a pour target le service "
                    "concerné. Tu peux proposer réplication, bascule automatique, health "
                    "checks ou répartition de charge. Ne relie pas une métrique globale à "
                    "un service particulier.\n"
                    "- N'invente aucun nombre. Réutilise seulement les valeurs du JSON. Le "
                    "bénéfice attendu reste qualitatif, sans pourcentage ni SLA inventé.\n"
                    "- Pour une anomalie, parameters indique la métrique, la valeur observée "
                    "et son seuil d'alerte. Pour un incident de service, parameters indique "
                    "le type d'incident et son nombre d'occurrences. Les clés sont courtes, "
                    "en snake_case, et les valeurs ne sont jamais vides.\n"
                    "- Chaque recommandation traite un problème distinct. Ne répète pas une "
                    "métrique. L'action doit correspondre à la métrique : le stockage aux "
                    "disques, les ressources mémoire à memory_usage et le refroidissement "
                    "à temperature_celsius.\n"
                    "- Si global_anomalies et service_incidents contiennent tous les deux "
                    "des problèmes, inclus au moins une recommandation pour une anomalie "
                    "globale et au moins une pour un service incidenté.\n"
                    "- Priorise les anomalies high et les incidents offline avant degraded. "
                    "Ne te limite pas au diagnostic ou à la surveillance. Chaque action doit "
                    "nommer précisément l'opération technique à réaliser, pas seulement "
                    "l'objectif à atteindre.\n"
                    "- Utilise des identifiants REC-001, REC-002, etc."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, indent=2),
            },
        ],
        format=RecommendationResponse.model_json_schema(),
        options={"temperature": 0},
    )

    parsed_response = RecommendationResponse.model_validate_json(
        response.message.content
    )
    return parsed_response.recommendations


def run_pipeline(
    input_path: str | Path,
    model: str = DEFAULT_OLLAMA_MODEL,
) -> OutputReport:
    """Exécute les nœuds dans l’ordre et retourne le rapport final."""

    records = ingest_data(input_path)
    insights = compute_insights(records)
    anomalies = detect_anomalies(records)
    service_analysis = summarize_services(records)
    recommendations = generate_recommendations(
        insights,
        anomalies,
        service_analysis,
        model,
    )

    latest_timestamp = records[-1].timestamp.astimezone(timezone.utc)

    return OutputReport(
        timestamp=latest_timestamp.isoformat().replace("+00:00", "Z"),
        insights=insights,
        anomalies=anomalies,
        recommendations=recommendations,
        service_status_summary=service_analysis.current_status,
    )
