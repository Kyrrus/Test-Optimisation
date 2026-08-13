from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


Status = Literal["online", "degraded", "offline"]
ServiceName = Literal["database", "api_gateway", "cache"]
Severity = Literal["low", "medium", "high"]
RecommendationTarget = Literal[
    "database",
    "api_gateway",
    "cache",
    "infrastructure",
]


class StrictModel(BaseModel):
    """Modèle qui refuse les champs JSON inconnus."""

    model_config = ConfigDict(extra="forbid")


class ServiceStatus(StrictModel):
    database: Status
    api_gateway: Status
    cache: Status


class LogRecord(StrictModel):
    timestamp: AwareDatetime
    cpu_usage: float = Field(ge=0, le=100)
    memory_usage: float = Field(ge=0, le=100)
    latency_ms: float = Field(ge=0)
    disk_usage: float = Field(ge=0, le=100)
    network_in_kbps: float = Field(ge=0)
    network_out_kbps: float = Field(ge=0)
    io_wait: float = Field(ge=0)
    thread_count: int = Field(ge=0)
    active_connections: int = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    uptime_seconds: int = Field(ge=0)
    temperature_celsius: float = Field(ge=-20, le=150)
    power_consumption_watts: float = Field(ge=0)
    service_status: ServiceStatus


class Insights(StrictModel):
    average_latency_ms: float
    max_cpu_usage: float
    max_memory_usage: float
    error_rate: float
    uptime_seconds: int


class Anomaly(StrictModel):
    metric: str
    value: float
    threshold: float
    severity: Severity
    description: str


class Recommendation(StrictModel):
    id: str
    action: str
    target: RecommendationTarget
    parameters: dict[str, str | int | float | bool]
    benefit_estimate: str


class RecommendationResponse(StrictModel):
    recommendations: list[Recommendation] = Field(min_length=1, max_length=5)


class ServiceStatusSummary(StrictModel):
    online: list[ServiceName] = Field(default_factory=list)
    degraded: list[ServiceName] = Field(default_factory=list)
    offline: list[ServiceName] = Field(default_factory=list)


class OutputReport(StrictModel):
    timestamp: str
    insights: Insights
    anomalies: list[Anomaly]
    recommendations: list[Recommendation]
    service_status_summary: ServiceStatusSummary
