"""
Alerting mechanism for incident notifications.

Sends notifications when anomalies are detected.
Supports webhooks for integration with external systems,
and console logging for development/debugging.
"""

import logging
import json
from datetime import datetime
from typing import Optional

import requests

from config import AlertingConfig
from domain import IncidentRecord

logger = logging.getLogger(__name__)


class Alerter:
    """
    Sends alerts when incidents are detected.
    
    Supports multiple notification channels:
    - Webhook (HTTP POST to external service)
    - Console logging (for dev/debugging)
    """
    
    SEVERITY_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    
    def __init__(self, config: AlertingConfig):
        """
        Initialize alerter with configuration.
        
        Args:
            config: AlertingConfig specifying channels and thresholds
        """
        self.config = config
        self.alerts_sent = 0
        self.alerts_failed = 0
    
    def alert(self, incident: IncidentRecord) -> bool:
        """
        Send alert for an incident if it meets severity threshold.
        
        Args:
            incident: IncidentRecord to alert on
            
        Returns:
            True if alert was sent (or suppressed by threshold)
        """
        # Check severity threshold
        if not self._should_alert(incident.severity):
            logger.debug(f"Alert suppressed: severity {incident.severity} "
                        f"below threshold {self.config.severity_threshold}")
            return True
        
        success = True
        
        # Console alert
        if self.config.console_enabled:
            success &= self._console_alert(incident)
        
        # Webhook alert
        if self.config.webhook_url:
            success &= self._webhook_alert(incident)
        
        if success:
            self.alerts_sent += 1
        else:
            self.alerts_failed += 1
        
        return success
    
    def _should_alert(self, incident_severity: str) -> bool:
        """Check if incident severity meets alert threshold."""
        threshold_idx = self.SEVERITY_LEVELS.index(
            self.config.severity_threshold
        )
        incident_idx = self.SEVERITY_LEVELS.index(incident_severity)
        return incident_idx >= threshold_idx
    
    def _console_alert(self, incident: IncidentRecord) -> bool:
        """Log alert to console/stdout."""
        message = (
            f"\n{'='*80}\n"
            f"🚨 INCIDENT DETECTED\n"
            f"{'='*80}\n"
            f"  Incident ID: {incident.incident_id}\n"
            f"  Service: {incident.service_name}\n"
            f"  Severity: {incident.severity}\n"
            f"  Anomaly Score: {incident.anomaly_score:.3f}\n"
            f"  Summary: {incident.summary}\n"
            f"  Affected Logs: {len(incident.log_ids)}\n"
            f"  Created: {incident.created_at.isoformat()}\n"
            f"{'='*80}\n"
        )
        logger.warning(message)
        return True
    
    def _webhook_alert(self, incident: IncidentRecord) -> bool:
        """Send alert via HTTP webhook."""
        payload = {
            "incident_id": incident.incident_id,
            "service_name": incident.service_name,
            "severity": incident.severity,
            "anomaly_score": incident.anomaly_score,
            "summary": incident.summary,
            "affected_log_count": len(incident.log_ids),
            "created_at": incident.created_at.isoformat(),
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            response = requests.post(
                self.config.webhook_url,
                json=payload,
                timeout=5
            )
            
            if response.status_code >= 400:
                logger.error(f"Webhook failed with status {response.status_code}")
                return False
            
            logger.debug(f"Webhook alert sent to {self.config.webhook_url}")
            return True
        except requests.RequestException as e:
            logger.error(f"Webhook request failed: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Get alerter statistics for monitoring."""
        return {
            "alerts_sent": self.alerts_sent,
            "alerts_failed": self.alerts_failed
        }
