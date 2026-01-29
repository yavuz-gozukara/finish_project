"""
Log Processor Application

This module implements the core log processing pipeline with anomaly detection
using Isolation Forest (unsupervised ML technique).

Architecture:
- Kafka Consumer: Pulls raw logs from 'raw-logs' topic
- Log Parser: Transforms JSON logs into feature vectors
- Anomaly Detection: Isolation Forest identifies statistical anomalies
- Storage: Persists logs to Elasticsearch, incidents to PostgreSQL
- Alerting: Triggers notifications on anomaly detection
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

# Third-party imports
from kafka import KafkaConsumer
from elasticsearch import Elasticsearch
import psycopg2
from psycopg2.extras import Json as PostgresJson
import numpy as np
from sklearn.ensemble import IsolationForest
from datetime import datetime
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class LogProcessorConfig:
    """Configuration for log processor service."""
    
    kafka_bootstrap_servers: str
    kafka_topic: str = 'raw-logs'
    kafka_group_id: str = 'log-processor-group'
    
    elasticsearch_host: str
    elasticsearch_port: int = 9200
    elasticsearch_index: str = 'logs'
    
    postgres_host: str
    postgres_user: str
    postgres_password: str
    postgres_db: str
    
    isolation_forest_contamination: float = 0.05
    anomaly_score_threshold: float = 0.7
    batch_size: int = 100
    
    @classmethod
    def from_environment(cls) -> 'LogProcessorConfig':
        """Load configuration from environment variables."""
        return cls(
            kafka_bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
            elasticsearch_host=os.getenv('ELASTICSEARCH_HOST', 'localhost'),
            elasticsearch_port=int(os.getenv('ELASTICSEARCH_PORT', 9200)),
            postgres_host=os.getenv('POSTGRES_HOST', 'localhost'),
            postgres_user=os.getenv('POSTGRES_USER', 'graduation'),
            postgres_password=os.getenv('POSTGRES_PASSWORD', 'graduation-pass-2026'),
            postgres_db=os.getenv('POSTGRES_DB', 'incident_db'),
        )


class LogParser:
    """Parses structured JSON logs into analyzable features."""
    
    def __init__(self):
        self.critical_keywords = ['error', 'exception', 'failed', 'timeout', 'crash']
    
    def parse(self, raw_log: str) -> Optional[Dict[str, Any]]:
        """
        Parse raw JSON log string into structured format.
        
        Args:
            raw_log: JSON string representation of log
            
        Returns:
            Parsed log dictionary or None if invalid
        """
        try:
            log_data = json.loads(raw_log)
            return self._validate_and_enrich(log_data)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse log: {e}")
            return None
    
    def _validate_and_enrich(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate required fields and add computed features."""
        required_fields = ['service_name', 'timestamp', 'level', 'message']
        
        if not all(field in log_data for field in required_fields):
            raise ValueError(f"Missing required fields. Got: {log_data.keys()}")
        
        # Add computed features for anomaly detection
        log_data['message_length'] = len(log_data.get('message', ''))
        log_data['has_exception'] = 1 if log_data.get('exception') else 0
        log_data['is_critical_keyword'] = 1 if any(
            keyword in log_data.get('message', '').lower() 
            for keyword in self.critical_keywords
        ) else 0
        
        return log_data


class AnomalyDetector:
    """
    Detects anomalies in log streams using Isolation Forest.
    
    Isolation Forest is chosen because:
    - Unsupervised learning (no labeled training data required)
    - Efficient for high-dimensional data
    - Good for detecting statistical outliers in operational metrics
    """
    
    def __init__(self, contamination: float = 0.05):
        """
        Initialize detector.
        
        Args:
            contamination: Expected proportion of anomalies in dataset (0-1)
        """
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        self.trained = False
        self.training_data: List[List[float]] = []
    
    def extract_features(self, log_data: Dict[str, Any]) -> List[float]:
        """
        Extract numerical features from log data.
        
        Features selected:
        - Message length (lexical complexity)
        - Exception presence (indicator of issues)
        - Critical keyword presence
        - Response time if available
        - Status code range
        """
        features = [
            log_data.get('message_length', 0),
            log_data.get('has_exception', 0),
            log_data.get('is_critical_keyword', 0),
            float(log_data.get('duration_ms', 0)),
            float(log_data.get('status_code', 200)) / 100.0,  # Normalize status code
        ]
        return features
    
    def train(self, logs: List[Dict[str, Any]]) -> None:
        """Train the model on historical logs."""
        if len(logs) < 50:
            logger.warning("Insufficient data for training. Need at least 50 samples.")
            return
        
        features = [self.extract_features(log) for log in logs]
        self.training_data = features
        self.model.fit(features)
        self.trained = True
        logger.info(f"Model trained on {len(logs)} samples")
    
    def predict_anomaly(self, log_data: Dict[str, Any]) -> tuple[bool, float]:
        """
        Predict if log represents an anomaly.
        
        Returns:
            Tuple of (is_anomaly, anomaly_score)
        """
        if not self.trained:
            logger.debug("Model not trained yet, skipping anomaly detection")
            return False, 0.0
        
        features = [self.extract_features(log_data)]
        prediction = self.model.predict(features)[0]
        score = abs(self.model.score_samples(features)[0])
        
        is_anomaly = prediction == -1
        return is_anomaly, float(score)


class LogProcessor:
    """Main orchestrator for log processing pipeline."""
    
    def __init__(self, config: LogProcessorConfig):
        self.config = config
        self.parser = LogParser()
        self.detector = AnomalyDetector(contamination=config.isolation_forest_contamination)
        
        # Initialize external connections
        self.kafka_consumer = self._init_kafka_consumer()
        self.elasticsearch = self._init_elasticsearch()
        self.postgres_conn = self._init_postgres()
        
        self.batch: List[Dict[str, Any]] = []
        self.anomalies_detected = 0
    
    def _init_kafka_consumer(self) -> KafkaConsumer:
        """Initialize Kafka consumer."""
        return KafkaConsumer(
            self.config.kafka_topic,
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            group_id=self.config.kafka_group_id,
            auto_offset_reset='earliest',
            value_deserializer=lambda m: m.decode('utf-8'),
            enable_auto_commit=True
        )
    
    def _init_elasticsearch(self) -> Elasticsearch:
        """Initialize Elasticsearch client."""
        es = Elasticsearch(
            [f'http://{self.config.elasticsearch_host}:{self.config.elasticsearch_port}']
        )
        return es
    
    def _init_postgres(self) -> psycopg2.connection:
        """Initialize PostgreSQL connection."""
        return psycopg2.connect(
            host=self.config.postgres_host,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
            database=self.config.postgres_db
        )
    
    def process_log(self, raw_log: str) -> None:
        """Process a single log entry."""
        parsed_log = self.parser.parse(raw_log)
        if not parsed_log:
            return
        
        # Store in Elasticsearch
        self._store_log_in_elasticsearch(parsed_log)
        
        # Detect anomalies
        is_anomaly, score = self.detector.predict_anomaly(parsed_log)
        if is_anomaly and score >= self.config.anomaly_score_threshold:
            self._handle_anomaly(parsed_log, score)
            self.anomalies_detected += 1
        
        self.batch.append(parsed_log)
    
    def _store_log_in_elasticsearch(self, log_data: Dict[str, Any]) -> None:
        """Index log document in Elasticsearch."""
        try:
            index_name = f"{self.config.elasticsearch_index}-{datetime.now().strftime('%Y.%m.%d')}"
            self.elasticsearch.index(
                index=index_name,
                id=log_data.get('log_id'),
                document=log_data
            )
        except Exception as e:
            logger.error(f"Failed to index log in Elasticsearch: {e}")
    
    def _handle_anomaly(self, log_data: Dict[str, Any], score: float) -> None:
        """Handle detected anomaly by creating incident record."""
        try:
            incident_id = str(uuid.uuid4())
            severity = 'CRITICAL' if score > 0.85 else 'HIGH'
            
            cursor = self.postgres_conn.cursor()
            cursor.execute("""
                INSERT INTO incidents 
                (incident_id, service_name, anomaly_score, anomaly_type, description, severity)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                incident_id,
                log_data.get('service_name'),
                float(score),
                log_data.get('level', 'UNKNOWN'),
                log_data.get('message'),
                severity
            ))
            self.postgres_conn.commit()
            cursor.close()
            
            logger.warning(f"Anomaly detected: {incident_id} - Score: {score:.2f}")
        except Exception as e:
            logger.error(f"Failed to record incident: {e}")
    
    def run(self) -> None:
        """Main processing loop."""
        logger.info("Log processor started. Waiting for logs...")
        try:
            for message in self.kafka_consumer:
                self.process_log(message.value)
        except KeyboardInterrupt:
            logger.info("Processor interrupted by user")
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Clean up resources."""
        self.kafka_consumer.close()
        self.postgres_conn.close()
        logger.info(f"Processor shutdown. Total anomalies detected: {self.anomalies_detected}")


if __name__ == '__main__':
    config = LogProcessorConfig.from_environment()
    processor = LogProcessor(config)
    processor.run()
