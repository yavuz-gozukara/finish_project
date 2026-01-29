"""
Configuration management for the log processor.

Loads settings from environment variables with sensible defaults.
Suitable for containerized deployment.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class KafkaConfig:
    """Apache Kafka connection settings."""
    bootstrap_servers: str
    topic: str
    group_id: str
    auto_offset_reset: str
    enable_auto_commit: bool
    
    @classmethod
    def from_env(cls) -> "KafkaConfig":
        return cls(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            topic=os.getenv("KAFKA_TOPIC", "logs.raw"),
            group_id=os.getenv("KAFKA_GROUP_ID", "log-processor-prod"),
            auto_offset_reset=os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest"),
            enable_auto_commit=os.getenv("KAFKA_AUTO_COMMIT", "true").lower() == "true"
        )


@dataclass
class ElasticsearchConfig:
    """Elasticsearch connection settings."""
    host: str
    port: int
    index_prefix: str
    username: Optional[str]
    password: Optional[str]
    
    @classmethod
    def from_env(cls) -> "ElasticsearchConfig":
        return cls(
            host=os.getenv("ELASTICSEARCH_HOST", "localhost"),
            port=int(os.getenv("ELASTICSEARCH_PORT", "9200")),
            index_prefix=os.getenv("ELASTICSEARCH_INDEX_PREFIX", "logs"),
            username=os.getenv("ELASTICSEARCH_USER"),
            password=os.getenv("ELASTICSEARCH_PASSWORD")
        )


@dataclass
class PostgresConfig:
    """PostgreSQL connection settings."""
    host: str
    port: int
    database: str
    user: str
    password: str
    
    @classmethod
    def from_env(cls) -> "PostgresConfig":
        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "logs_db"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres")
        )


@dataclass
class AnomalyDetectionConfig:
    """Anomaly detection model hyperparameters."""
    contamination: float  # Expected proportion of anomalies
    n_estimators: int    # Number of isolation trees
    min_training_samples: int  # Minimum samples before inference
    retraining_interval_seconds: int  # How often to retrain
    anomaly_score_threshold: float  # Score threshold for alerting
    
    @classmethod
    def from_env(cls) -> "AnomalyDetectionConfig":
        return cls(
            contamination=float(os.getenv("ANOMALY_CONTAMINATION", "0.05")),
            n_estimators=int(os.getenv("ANOMALY_N_ESTIMATORS", "100")),
            min_training_samples=int(os.getenv("ANOMALY_MIN_SAMPLES", "50")),
            retraining_interval_seconds=int(os.getenv("ANOMALY_RETRAIN_INTERVAL", "3600")),
            anomaly_score_threshold=float(os.getenv("ANOMALY_THRESHOLD", "0.7"))
        )


@dataclass
class AlertingConfig:
    """Alerting mechanism configuration."""
    webhook_url: Optional[str]
    console_enabled: bool
    severity_threshold: str  # MIN severity level to alert on
    
    @classmethod
    def from_env(cls) -> "AlertingConfig":
        return cls(
            webhook_url=os.getenv("ALERT_WEBHOOK_URL"),
            console_enabled=os.getenv("ALERT_CONSOLE_ENABLED", "true").lower() == "true",
            severity_threshold=os.getenv("ALERT_MIN_SEVERITY", "HIGH")
        )


@dataclass
class ProcessorConfig:
    """Complete processor configuration."""
    kafka: KafkaConfig
    elasticsearch: ElasticsearchConfig
    postgres: PostgresConfig
    anomaly_detection: AnomalyDetectionConfig
    alerting: AlertingConfig
    batch_size: int  # How many logs to process before committing
    log_level: str  # DEBUG, INFO, WARNING, ERROR
    
    @classmethod
    def from_env(cls) -> "ProcessorConfig":
        """Load all configuration from environment variables."""
        return cls(
            kafka=KafkaConfig.from_env(),
            elasticsearch=ElasticsearchConfig.from_env(),
            postgres=PostgresConfig.from_env(),
            anomaly_detection=AnomalyDetectionConfig.from_env(),
            alerting=AlertingConfig.from_env(),
            batch_size=int(os.getenv("BATCH_SIZE", "100")),
            log_level=os.getenv("LOG_LEVEL", "INFO")
        )
