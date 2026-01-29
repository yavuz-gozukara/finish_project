"""
Persistence layer for logs and incidents.

Handles writing to Elasticsearch (logs) and PostgreSQL (incidents).
Designed for reliable, idempotent writes with error recovery.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ElasticsearchException
import psycopg2
from psycopg2.extras import execute_values
from psycopg2.errors import UniqueViolation

from config import ElasticsearchConfig, PostgresConfig
from domain import LogEntry, IncidentRecord

logger = logging.getLogger(__name__)


class LogStorage:
    """
    Elasticsearch integration for log storage and full-text search.
    
    Uses daily indexes (logs-YYYY.MM.DD) for lifecycle management
    and efficient time-range queries.
    """
    
    def __init__(self, config: ElasticsearchConfig):
        """
        Initialize Elasticsearch client.
        
        Args:
            config: ElasticsearchConfig with host/port/auth
        """
        self.config = config
        
        # Build connection URL
        scheme = "https" if config.password else "http"
        hosts = [f"{config.host}:{config.port}"]
        
        auth = None
        if config.username and config.password:
            auth = (config.username, config.password)
        
        self.client = Elasticsearch(
            hosts=hosts,
            basic_auth=auth,
            request_timeout=10
        )
        
        self._create_index_template()
    
    def _create_index_template(self) -> None:
        """
        Create index template for dynamic index creation.
        
        Ensures consistent mappings across daily indexes.
        """
        template_name = f"{self.config.index_prefix}-template"
        template_body = {
            "index_patterns": [f"{self.config.index_prefix}-*"],
            "template": {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0
                },
                "mappings": {
                    "properties": {
                        "log_id": {"type": "keyword"},
                        "timestamp": {"type": "date"},
                        "service_name": {"type": "keyword"},
                        "level": {"type": "keyword"},
                        "message": {"type": "text"},
                        "duration_ms": {"type": "integer"},
                        "status_code": {"type": "keyword"},
                        "trace_id": {"type": "keyword"},
                        "user_id": {"type": "keyword"},
                        "is_anomaly": {"type": "boolean"},
                        "anomaly_score": {"type": "float"}
                    }
                }
            }
        }
        
        try:
            self.client.indices.put_index_template(
                name=template_name,
                body=template_body
            )
            logger.debug(f"Created/updated index template: {template_name}")
        except ElasticsearchException as e:
            logger.warning(f"Failed to create index template: {e}")
    
    def index_log(self, log: LogEntry, is_anomaly: bool, 
                  anomaly_score: float = 0.0) -> bool:
        """
        Index a log entry in Elasticsearch.
        
        Args:
            log: LogEntry to index
            is_anomaly: Whether log was flagged as anomalous
            anomaly_score: Anomaly score [0, 1]
            
        Returns:
            True if successful, False otherwise
        """
        index_name = self._get_index_name(log.timestamp)
        
        doc = {
            "log_id": log.log_id,
            "timestamp": log.timestamp.isoformat(),
            "service_name": log.service_name,
            "level": log.level.name,
            "message": log.message,
            "duration_ms": log.duration_ms,
            "status_code": log.status_code,
            "trace_id": log.trace_id,
            "user_id": log.user_id,
            "is_anomaly": is_anomaly,
            "anomaly_score": anomaly_score
        }
        
        try:
            self.client.index(
                index=index_name,
                id=log.log_id,
                body=doc
            )
            return True
        except ElasticsearchException as e:
            logger.error(f"Failed to index log {log.log_id}: {e}")
            return False
    
    def _get_index_name(self, timestamp: datetime) -> str:
        """Generate daily index name: logs-YYYY.MM.DD"""
        return f"{self.config.index_prefix}-{timestamp.strftime('%Y.%m.%d')}"
    
    def health(self) -> Dict[str, Any]:
        """Check Elasticsearch cluster health."""
        try:
            return self.client.cluster.health()
        except ElasticsearchException as e:
            logger.error(f"Failed to get ES health: {e}")
            return {"status": "red"}


class IncidentStorage:
    """
    PostgreSQL integration for incident tracking.
    
    Stores anomaly incidents with metadata for alerting and
    post-incident analysis.
    """
    
    def __init__(self, config: PostgresConfig):
        """
        Initialize PostgreSQL connection.
        
        Args:
            config: PostgresConfig with connection details
        """
        self.config = config
        self.conn = None
        self._connect()
    
    def _connect(self) -> bool:
        """Establish connection to PostgreSQL."""
        try:
            self.conn = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password
            )
            logger.info(f"Connected to PostgreSQL: {self.config.host}:"
                       f"{self.config.port}/{self.config.database}")
            return True
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            return False
    
    def write_incident(self, incident: IncidentRecord) -> bool:
        """
        Write incident record to database.
        
        Args:
            incident: IncidentRecord to write
            
        Returns:
            True if successful, False otherwise
        """
        if not self.conn:
            logger.error("Not connected to PostgreSQL")
            return False
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO incidents 
                (incident_id, service_name, anomaly_score, 
                 severity, summary, affected_log_count, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                incident.incident_id,
                incident.service_name,
                incident.anomaly_score,
                incident.severity,
                incident.summary,
                len(incident.log_ids),
                incident.created_at
            ))
            self.conn.commit()
            cursor.close()
            
            logger.info(f"Wrote incident {incident.incident_id} "
                       f"for {incident.service_name}")
            return True
        except UniqueViolation:
            self.conn.rollback()
            logger.debug(f"Incident {incident.incident_id} already exists")
            return True  # Idempotent
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to write incident: {e}")
            return False
    
    def record_anomaly_metric(self, service_name: str, 
                             metric_date: datetime,
                             anomaly_count: int,
                             total_logs: int) -> bool:
        """
        Record daily anomaly statistics for observability.
        
        Args:
            service_name: Service name
            metric_date: Date for metric
            anomaly_count: Number of anomalies detected
            total_logs: Total logs processed
            
        Returns:
            True if successful
        """
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            # Upsert (update if exists, insert if not)
            cursor.execute("""
                INSERT INTO anomaly_metrics 
                (service_name, metric_date, anomaly_count, total_logs)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (service_name, metric_date)
                DO UPDATE SET 
                  anomaly_count = EXCLUDED.anomaly_count,
                  total_logs = EXCLUDED.total_logs
            """, (service_name, metric_date.date(), anomaly_count, total_logs))
            
            self.conn.commit()
            cursor.close()
            return True
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to record anomaly metric: {e}")
            return False
    
    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("PostgreSQL connection closed")
