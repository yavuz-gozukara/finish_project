"""
Anomaly detection using Isolation Forest.

Unsupervised learning approach suitable for detecting statistical
outliers in operational logs without labeled training data.

Theory:
  Isolation Forest isolates observations by randomly selecting features
  and split values. Anomalies are isolated with fewer splits (shorter
  path length) than normal points. This is efficient and effective for
  high-dimensional data.

References:
  Liu, F. T., Ting, K. M., & Zhou, Z. H. (2012).
  "Isolation-based anomaly detection" (IEEE TKDE)
"""

import logging
import numpy as np
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest

from config import AnomalyDetectionConfig

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """
    Isolation Forest-based anomaly detection with per-service models.
    
    Maintains separate models per service to account for different
    baseline behavior (e.g., payment-service may have different latency
    distribution than auth-service).
    """
    
    def __init__(self, config: AnomalyDetectionConfig):
        """
        Initialize detector with configuration.
        
        Args:
            config: AnomalyDetectionConfig with hyperparameters
        """
        self.config = config
        self.models: Dict[str, IsolationForest] = {}  # Per-service models
        self.training_data: Dict[str, list] = {}      # Accumulated features
        self.last_training_time: Dict[str, datetime] = {}
        self.model_ready: Dict[str, bool] = {}        # Training status
    
    def infer(self, service_name: str, features: np.ndarray) -> Tuple[bool, float]:
        """
        Perform anomaly detection inference on a single feature vector.
        
        Args:
            service_name: Service that generated the log
            features: np.array of shape (1, n_features)
            
        Returns:
            Tuple of (is_anomaly: bool, anomaly_score: float)
            
        Behavior:
          - If model not ready: accumulate training data, return (False, 0.0)
          - If model ready: score and compare against threshold
        """
        if not self.model_ready.get(service_name, False):
            # Still accumulating training data
            self._accumulate_training_data(service_name, features)
            
            # Check if we have enough to train
            if (len(self.training_data.get(service_name, [])) >= 
                self.config.min_training_samples):
                self._train_model(service_name)
                logger.info(f"Trained model for service: {service_name}")
            
            return False, 0.0
        
        # Model is ready, perform inference
        model = self.models[service_name]
        prediction = model.predict(features)[0]  # -1 or 1
        score = abs(model.score_samples(features)[0])  # Range ~[0, 1]
        
        is_anomaly = (prediction == -1 and 
                      score >= self.config.anomaly_score_threshold)
        
        # Check if retraining is due
        self._check_and_retrain(service_name, features)
        
        return is_anomaly, float(score)
    
    def _accumulate_training_data(self, service_name: str, 
                                   features: np.ndarray) -> None:
        """
        Accumulate feature vectors for training.
        
        During cold start, we collect samples before training.
        """
        if service_name not in self.training_data:
            self.training_data[service_name] = []
        
        self.training_data[service_name].append(features.flatten().tolist())
    
    def _train_model(self, service_name: str) -> None:
        """
        Train Isolation Forest model for a service.
        
        Uses accumulated training data and sets up the model
        for inference.
        """
        training_samples = np.array(self.training_data[service_name])
        
        logger.debug(f"Training IF model for {service_name} "
                    f"with {len(training_samples)} samples")
        
        model = IsolationForest(
            n_estimators=self.config.n_estimators,
            contamination=self.config.contamination,
            random_state=42,  # Reproducibility
            n_jobs=-1  # Use all cores
        )
        
        model.fit(training_samples)
        self.models[service_name] = model
        self.model_ready[service_name] = True
        self.last_training_time[service_name] = datetime.now()
        
        logger.info(f"Model ready for {service_name}: "
                   f"expects {self.config.contamination*100:.1f}% anomalies")
    
    def _check_and_retrain(self, service_name: str, 
                          features: np.ndarray) -> None:
        """
        Periodically retrain model to adapt to distribution changes.
        
        Retraining interval: AnomalyDetectionConfig.retraining_interval_seconds
        """
        last_train = self.last_training_time.get(service_name)
        if not last_train:
            return
        
        elapsed = (datetime.now() - last_train).total_seconds()
        if elapsed < self.config.retraining_interval_seconds:
            return
        
        # Time to retrain: add new sample and retrain
        if service_name not in self.training_data:
            self.training_data[service_name] = []
        
        self.training_data[service_name].append(features.flatten().tolist())
        
        # Keep recent window for retraining
        max_samples = 1000
        if len(self.training_data[service_name]) > max_samples:
            self.training_data[service_name] = \
                self.training_data[service_name][-max_samples:]
        
        # Retrain
        self._train_model(service_name)
        logger.info(f"Retraining model for {service_name} after "
                   f"{elapsed:.0f}s")
    
    def get_status(self) -> Dict:
        """
        Get detector status for monitoring/debugging.
        
        Returns information about which models are ready and
        their training state.
        """
        return {
            "models_ready": {
                service: ready 
                for service, ready in self.model_ready.items()
            },
            "training_data_counts": {
                service: len(data)
                for service, data in self.training_data.items()
            },
            "last_training_times": {
                service: time.isoformat()
                for service, time in self.last_training_time.items()
            }
        }
