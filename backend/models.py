"""Pydantic models for StorageWatch API."""

from pydantic import BaseModel


class Metrics(BaseModel):
    """Filesystem metrics from monitoring agent."""
    timestamp: str
    hostname: str
    filesystem: str
    filesystem_type: str

    total_bytes: int
    used_bytes: int
    free_bytes: int

    used_percent: float

    read_bytes_per_sec: int
    write_bytes_per_sec: int

    # Whether the menu bar app is on that Mac right now. The collector sends it
    # only when it changes — a collector starting up, or one that has just
    # applied the dashboard's setting — so a steady report carries nothing
    # extra and costs no extra write.
    menu_bar_installed: bool | None = None


class MetricsResponse(BaseModel):
    """Response from GET endpoints."""
    timestamp: str
    hostname: str
    filesystem: str
    filesystem_type: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    read_bytes_per_sec: int
    write_bytes_per_sec: int


class Alert(BaseModel):
    """Alert from anomaly detection."""
    id: int
    created_at: str
    hostname: str
    alert_type: str
    severity: str
    message: str
    metric_value: float
    resolved: bool
