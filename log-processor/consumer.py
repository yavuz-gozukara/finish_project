"""
Kafka consumer integration.

Handles connection to Kafka, consuming logs from the 'logs.raw' topic,
and providing an iterator interface for the processing pipeline.
"""

import json
import logging
from typing import Iterator, Optional

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from config import KafkaConfig

logger = logging.getLogger(__name__)


class LogConsumer:
    """
    Kafka consumer for structured logs.
    
    Consumes from a configured topic and yields raw JSON messages
    for processing. Handles connection errors and offset management.
    """
    
    def __init__(self, config: KafkaConfig):
        """
        Initialize Kafka consumer.
        
        Args:
            config: KafkaConfig with bootstrap servers and topic info
        """
        self.config = config
        self.consumer: Optional[KafkaConsumer] = None
        self._connected = False
    
    def connect(self) -> bool:
        """
        Establish connection to Kafka cluster.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.consumer = KafkaConsumer(
                self.config.topic,
                bootstrap_servers=self.config.bootstrap_servers.split(","),
                group_id=self.config.group_id,
                auto_offset_reset=self.config.auto_offset_reset,
                enable_auto_commit=self.config.enable_auto_commit,
                value_deserializer=lambda m: m.decode("utf-8") if m else None,
                session_timeout_ms=10000,
                heartbeat_interval_ms=3000
            )
            self._connected = True
            logger.info(f"Connected to Kafka: {self.config.bootstrap_servers}, "
                       f"topic: {self.config.topic}, group: {self.config.group_id}")
            return True
        except KafkaError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            self._connected = False
            return False
    
    def consume(self) -> Iterator[str]:
        """
        Consume messages from Kafka topic indefinitely.
        
        Yields raw JSON strings from the 'logs.raw' topic.
        
        Note:
            This is a blocking generator. Call in a dedicated thread
            or use async/await if needed.
        """
        if not self._connected:
            if not self.connect():
                logger.error("Cannot consume: not connected to Kafka")
                return
        
        try:
            for message in self.consumer:
                if message.value is None:
                    continue
                yield message.value
        except KafkaError as e:
            logger.error(f"Kafka consumer error: {e}")
            self._connected = False
    
    def close(self) -> None:
        """Close connection to Kafka."""
        if self.consumer:
            self.consumer.close()
            self._connected = False
            logger.info("Kafka consumer closed")
    
    def is_connected(self) -> bool:
        """Check if consumer is currently connected."""
        return self._connected
