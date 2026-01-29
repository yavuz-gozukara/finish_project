"""
Log parsing and feature extraction.

Transforms raw JSON logs into typed domain objects and extracts
numerical features suitable for machine learning.
"""

import json
import logging
import numpy as np
from datetime import datetime
from typing import Dict, Any, Tuple

from domain import LogEntry, LogLevel

logger = logging.getLogger(__name__)


class LogParser:
    """
    Parses raw JSON logs from Kafka into structured LogEntry objects.
    
    Performs validation and enrichment while maintaining clarity
    and error handling.
    """
    
    def __init__(self):
        """Initialize parser with any state needed."""
        self.parse_errors = 0
        self.parse_success = 0
    
    def parse(self, raw_message: str) -> Tuple[LogEntry, bool]:
        """
        Parse raw JSON string into LogEntry.
        
        Args:
            raw_message: JSON string from Kafka
            
        Returns:
            Tuple of (LogEntry, success: bool)
            If parsing fails, returns (None, False) and logs error
        """
        try:
            data = json.loads(raw_message)
            log_entry = LogEntry.from_json(data)
            self.parse_success += 1
            return log_entry, True
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            self.parse_errors += 1
            logger.warning(f"Failed to parse log: {e}")
            return None, False
    
    def get_stats(self) -> Dict[str, int]:
        """Return parsing statistics for monitoring."""
        return {
            "parse_success": self.parse_success,
            "parse_errors": self.parse_errors
        }


class FeatureExtractor:
    """
    Extracts numerical features from structured logs for ML inference.
    
    Features are carefully chosen to capture:
    - Message complexity (length)
    - Severity (log level)
    - HTTP status (success vs error)
    - Performance (latency)
    - Error keywords (heuristic)
    
    Per-service statistics are maintained to detect anomalies
    relative to that service's baseline.
    """
    
    def __init__(self, window_size: int = 1000):
        """
        Initialize feature extractor.
        
        Args:
            window_size: Number of recent logs to maintain statistics
        """
        self.window_size = window_size
        # Per-service: {service_name: {'durations': [ms, ...], ...}}
        self.service_stats = {}
    
    def extract(self, log: LogEntry) -> np.ndarray:
        """
        Extract feature vector from a single log entry.
        
        Returns np.array of shape (1, 5) with features:
          [message_length, log_level_score, status_code_class, 
           duration_percentile, error_keyword_present]
        """
        features = [
            self._message_length_feature(log.message),
            self._log_level_feature(log.level),
            self._status_code_feature(log.status_code),
            self._duration_feature(log.service_name, log.duration_ms),
            self._error_keyword_feature(log.message)
        ]
        
        # Update service statistics for next inference
        self._update_service_stats(log)
        
        return np.array(features, dtype=float).reshape(1, -1)
    
    def _message_length_feature(self, message: str) -> float:
        """
        Message length (0-5000 chars).
        
        Rationale: Very long or unusual messages may indicate errors.
        Normalized to 0-100 scale.
        """
        length = len(message) if message else 0
        return min(length / 50.0, 100.0)
    
    def _log_level_feature(self, level: LogLevel) -> int:
        """
        Log level severity score.
        
        CRITICAL(4) > ERROR(3) > WARN(2) > INFO(1) > DEBUG(0)
        """
        return level.value
    
    def _status_code_feature(self, status_code: int) -> int:
        """
        HTTP status code class.
        
        Rationale: 5xx and 4xx errors are more anomalous than 2xx.
        Returns: 0=None, 1=1xx, 2=2xx, 3=3xx, 4=4xx, 5=5xx
        """
        if status_code is None:
            return 0
        code_class = status_code // 100
        return min(code_class, 5)
    
    def _duration_feature(self, service_name: str, duration_ms: int) -> float:
        """
        Duration as percentile within service baseline.
        
        Rationale: Latency anomalies are service-relative.
        Returns: 0-100 percentile (higher = slower than baseline)
        """
        if duration_ms is None:
            return 50.0  # Neutral if missing
        
        stats = self.service_stats.get(service_name, {})
        durations = stats.get("durations", [])
        
        if len(durations) < 10:
            # Not enough data, return normalized value
            return min(duration_ms / 5000.0, 100.0)
        
        # Calculate percentile within service baseline
        percentile = (sum(1 for d in durations if d < duration_ms) 
                      / len(durations) * 100)
        return percentile
    
    def _error_keyword_feature(self, message: str) -> int:
        """
        Binary indicator for error keywords.
        
        Rationale: Certain keywords strongly correlate with issues.
        """
        if not message:
            return 0
        
        keywords = ["error", "exception", "failed", "timeout", "crash", 
                    "failure", "fault", "critical"]
        message_lower = message.lower()
        
        return 1 if any(kw in message_lower for kw in keywords) else 0
    
    def _update_service_stats(self, log: LogEntry) -> None:
        """
        Maintain rolling statistics per service for baseline comparison.
        """
        service = log.service_name
        
        if service not in self.service_stats:
            self.service_stats[service] = {"durations": []}
        
        stats = self.service_stats[service]
        
        # Append duration if present
        if log.duration_ms is not None:
            stats["durations"].append(log.duration_ms)
            
            # Keep only recent window
            if len(stats["durations"]) > self.window_size:
                stats["durations"].pop(0)
    
    def get_service_baseline(self, service_name: str) -> Dict[str, float]:
        """
        Get baseline statistics for a service.
        Useful for observability and debugging.
        """
        stats = self.service_stats.get(service_name, {})
        durations = stats.get("durations", [])
        
        if not durations:
            return {"count": 0}
        
        durations_sorted = sorted(durations)
        return {
            "count": len(durations),
            "min_ms": min(durations),
            "max_ms": max(durations),
            "avg_ms": sum(durations) / len(durations),
            "p50_ms": durations_sorted[len(durations) // 2],
            "p95_ms": durations_sorted[int(len(durations) * 0.95)],
            "p99_ms": durations_sorted[int(len(durations) * 0.99)]
        }
