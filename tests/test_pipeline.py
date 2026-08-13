import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from infrastructure_analyzer.models import (
    LogRecord,
    OutputReport,
    Recommendation,
    RecommendationResponse,
)
from infrastructure_analyzer.pipeline import (
    compute_insights,
    detect_anomalies,
    generate_recommendations,
    ingest_data,
    run_pipeline,
    summarize_services,
)


def make_record(**overrides: object) -> LogRecord:
    data = {
        "timestamp": "2023-10-01T12:00:00Z",
        "cpu_usage": 50,
        "memory_usage": 60,
        "latency_ms": 100,
        "disk_usage": 50,
        "network_in_kbps": 1000,
        "network_out_kbps": 900,
        "io_wait": 2,
        "thread_count": 100,
        "active_connections": 40,
        "error_rate": 0.01,
        "uptime_seconds": 1000,
        "temperature_celsius": 60,
        "power_consumption_watts": 200,
        "service_status": {
            "database": "online",
            "api_gateway": "online",
            "cache": "online",
        },
    }
    data.update(overrides)
    return LogRecord.model_validate(data)


@pytest.fixture
def mock_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remplace Ollama pendant les tests pour ne pas charger un vrai modèle."""

    llm_result = RecommendationResponse(
        recommendations=[
            Recommendation(
                id="REC-TEST",
                action="Mettre en place une réplication de la base de données",
                target="database",
                parameters={"type_incident": "offline", "occurrences": 1},
                benefit_estimate="Améliorer la disponibilité de la base de données.",
            )
        ]
    )

    def fake_chat(**_: object) -> SimpleNamespace:
        message = SimpleNamespace(content=llm_result.model_dump_json())
        return SimpleNamespace(message=message)

    monkeypatch.setattr("infrastructure_analyzer.pipeline.chat", fake_chat)


def test_no_anomaly_for_normal_metrics() -> None:
    assert detect_anomalies([make_record()]) == []


def test_high_cpu_is_detected() -> None:
    anomalies = detect_anomalies([make_record(cpu_usage=95)])
    cpu_anomaly = next(a for a in anomalies if a.metric == "cpu_usage")

    assert cpu_anomaly.value == 95
    assert cpu_anomaly.threshold == 90
    assert cpu_anomaly.severity == "high"


def test_service_incidents_are_counted() -> None:
    records = [
        make_record(
            service_status={
                "database": "offline",
                "api_gateway": "online",
                "cache": "degraded",
            }
        ),
        make_record(timestamp="2023-10-01T12:30:00Z"),
    ]

    analysis = summarize_services(records)

    assert analysis.incidents["database"]["offline"] == 1
    assert analysis.incidents["cache"]["degraded"] == 1
    assert analysis.current_status.online == [
        "database",
        "api_gateway",
        "cache",
    ]


def test_ollama_generates_a_structured_recommendation(mock_ollama: None) -> None:
    records = [make_record(cpu_usage=95, latency_ms=350)]
    anomalies = detect_anomalies(records)
    service_analysis = summarize_services(records)

    recommendations = generate_recommendations(
        insights=compute_insights(records),
        anomalies=anomalies,
        service_analysis=service_analysis,
    )

    assert len(recommendations) == 1
    assert recommendations[0].id == "REC-TEST"
    assert recommendations[0].target == "database"
    assert recommendations[0].parameters["occurrences"] == 1


def test_empty_input_is_rejected(tmp_path: Path) -> None:
    input_path = tmp_path / "empty.json"
    input_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="liste non vide"):
        ingest_data(input_path)


def test_pipeline_on_provided_report(mock_ollama: None) -> None:
    report = run_pipeline("rapport.json")

    assert report.timestamp == "2023-10-11T21:30:00Z"
    assert report.insights.average_latency_ms == 156.018
    assert report.insights.max_cpu_usage == 99
    assert report.insights.max_memory_usage == 92
    assert report.insights.error_rate == 0.032
    assert report.insights.uptime_seconds == 1_258_200
    assert len(report.anomalies) == 7
    assert len(report.recommendations) == 1


def test_output_can_be_serialized_to_json(mock_ollama: None) -> None:
    report = run_pipeline("rapport.json")
    parsed = json.loads(report.model_dump_json())

    assert parsed["insights"]["max_cpu_usage"] == 99
    assert parsed["recommendations"][0]["id"] == "REC-TEST"


def test_provided_output_matches_expected_schema() -> None:
    output = Path("output.json").read_text(encoding="utf-8")
    report = OutputReport.model_validate_json(output)

    assert report.timestamp == "2023-10-11T21:30:00Z"
    assert len(report.recommendations) == 5
