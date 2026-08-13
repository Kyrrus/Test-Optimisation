from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdRule:
    metric: str
    low: float
    medium: float
    high: float


THRESHOLD_RULES = [
    ThresholdRule("cpu_usage", 70, 80, 90),
    ThresholdRule("memory_usage", 75, 80, 90),
    ThresholdRule("latency_ms", 180, 250, 300),
    ThresholdRule("disk_usage", 80, 85, 95),
    ThresholdRule("io_wait", 8, 10, 20),
    ThresholdRule("error_rate", 0.03, 0.05, 0.10),
    ThresholdRule("temperature_celsius", 70, 75, 85),
]


SERVICES = ("database", "api_gateway", "cache")

# Modèle local utilisé par défaut pour le nœud de recommandations.
DEFAULT_OLLAMA_MODEL = "llama3.1:8b-instruct-q8_0"
