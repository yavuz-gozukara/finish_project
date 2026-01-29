"""
Domain models representing structured logs and parsed events.

These dataclasses provide type safety and clear contracts
for data flowing through the processor pipeline.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class LogLevel(Enum):
    """Log severity levels."""
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3
    CRITICAL = 4


@dataclass
class LogEntry:
    """
    Parsed structured log entry.
    
    Represents a single log event with validated fields.
    This is the core domain object flowing through the pipeline.
    """
    log_id: str
    timestamp: datetime
    service_name: str
    level: LogLevel
    message: str
    trace_id: Optional[str] = None
    duration_ms: Optional[int] = None
    status_code: Optional[int] = None
    user_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "LogEntry":
        """
        Create LogEntry from raw JSON (from Kafka).
        
        Validates required fields and converts string values to enums.
        Raises ValueError if required fields are missing.
        """
        required = {"log_id", "timestamp", "service_name", "level", "message"}
        if not required.issubset(data.keys()):
            missing = required - set(data.keys())
            raise ValueError(f"Missing required fields: {missing}")
        
        try:
            level = LogLevel[data["level"].upper()]
        except KeyError:
            raise ValueError(f"Invalid log level: {data['level']}")
        
        # Parse timestamp (ISO format assumed)
        try:
            ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid timestamp: {data['timestamp']}") from e
        
        return cls(
            log_id=str(data["log_id"]),
            timestamp=ts,
            service_name=str(data["service_name"]),
            level=level,
            message=str(data["message"]),
            trace_id=data.get("trace_id"),
            duration_ms=data.get("duration_ms"),
            status_code=data.get("status_code"),
            user_id=data.get("user_id"),
            context=data.get("context")
        )


@dataclass
class AnomalyDetectionResult:
    """
    Result of anomaly detection inference on a single log.
    """
    log_id: str
    service_name: str
    is_anomaly: bool
    anomaly_score: float  # Range [0, 1], higher = more anomalous
    features: list  # The numeric features that were used
    
    def severity(self) -> str:
        """Classify severity based on anomaly score."""
        if self.anomaly_score > 0.85:
            return "CRITICAL"
        elif self.anomaly_score > 0.75:
            return "HIGH"
        elif self.anomaly_score > 0.65:
            return "MEDIUM"
        else:
            return "LOW"


@dataclass
class IncidentRecord:
    """
    Incident created when an anomaly is detected.
    
    Stored in PostgreSQL for operational tracking and alerting.
    """
    incident_id: str
    service_name: str
    anomaly_score: float
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    summary: str
    log_ids: list  # Related log IDs
    created_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for database insertion."""
        return {
            "incident_id": self.incident_id,
            "service_name": self.service_name,
            "anomaly_score": self.anomaly_score,
            "severity": self.severity,
            "summary": self.summary,
            "affected_log_count": len(self.log_ids),
            "created_at": self.created_at
        }
