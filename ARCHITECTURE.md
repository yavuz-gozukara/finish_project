# Architecture & Design Documentation

## System Design Overview

This document provides detailed architectural guidance for the AI-Assisted Real-Time Log Analysis Platform.

## 1. Data Flow

```
Request Flow:
┌─────────────────────────────────────────────────────────────────────┐
│ External Service                                                      │
│ POST /api/v1/logs/ingest                                             │
└────────────────┬────────────────────────────────────────────────────┘
                 │ StructuredLog JSON
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Log Producer Service (Spring Boot)                                   │
│ • Validate JSON schema                                               │
│ • Add timestamp & log_id                                             │
│ • Record metrics                                                     │
└────────────────┬────────────────────────────────────────────────────┘
                 │ Serialize to string, partition by service_name
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Apache Kafka Topic: raw-logs                                         │
│ • Partition 0: logs from service-A                                   │
│ • Partition 1: logs from service-B                                   │
│ • Partition N: logs from service-N                                   │
└────────────────┬────────────────────────────────────────────────────┘
                 │ Consumed by Log Processor Group
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Log Processor (Python)                                               │
│ • Parse JSON                                                         │
│ • Extract numerical features                                         │
│ • Score with Isolation Forest model                                  │
└────────┬──────────────────────────────────┬─────────────────────────┘
         │ Index document                   │ Detected anomaly?
         │ (with context metadata)          │
         ▼                                  ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│ Elasticsearch            │    │ PostgreSQL               │
│ Index: logs-YYYY.MM.DD   │    │ Table: incidents         │
│ • Full-text search       │    │ • Incident record        │
│ • Time-range queries     │    │ • Severity classification│
│ • Dashboard data         │    │ • Alert triggers         │
└──────────────────────────┘    └──────────────────────────┘
```

## 2. Service Responsibilities (Clean Architecture)

### Log Producer Service
**Domain**: Log Ingestion
- **Input**: HTTP POST with StructuredLog payload
- **Processing**: Validation, enrichment, serialization
- **Output**: Published to Kafka topic
- **Guarantees**: At-least-once delivery to Kafka

**Key Classes**:
- `StructuredLog`: Value object representing canonical log format
- `KafkaLogPublisher`: Service responsible for publishing
- `LogController`: REST API endpoint

**Design Pattern**: Dependency Injection for testability
```java
@Service
public class KafkaLogPublisher {
    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;
    // Injection allows mocking in tests
}
```

### Log Processor Service
**Domain**: Anomaly Detection & Incident Management
- **Input**: Kafka message stream (raw JSON logs)
- **Processing**: Parsing, feature extraction, model inference
- **Output**: Logs → Elasticsearch, Incidents → PostgreSQL
- **Guarantees**: Exactly-once semantics via Kafka commit offset

**Key Classes**:
- `LogParser`: Transforms raw JSON → structured format
- `AnomalyDetector`: Isolation Forest model wrapper
- `LogProcessor`: Orchestrator coordinating sub-components

**Design Pattern**: Strategy pattern for pluggable detection algorithms
```python
class AnomalyDetector:
    def predict_anomaly(self, log_data) -> (bool, float):
        # Swappable implementation (future: add more algorithms)
        pass
```

## 3. Data Models

### StructuredLog (Producer Output)
```json
{
  "log_id": "uuid",
  "timestamp": "2026-01-29T14:30:00.000",
  "service_name": "payment-service",
  "level": "ERROR|WARN|INFO|DEBUG|CRITICAL",
  "message": "Human-readable description",
  "trace_id": "distributed-trace-id",
  "user_id": "user-identifier",
  "duration_ms": 5000,
  "status_code": 500,
  "exception": "exception stacktrace (optional)",
  "context": {
    "database_pool": "exhausted",
    "retry_count": 3
  }
}
```

### Incident Record (PostgreSQL)
```sql
CREATE TABLE incidents (
  id SERIAL PRIMARY KEY,
  incident_id UUID UNIQUE NOT NULL,
  service_name VARCHAR(255),
  anomaly_score FLOAT,          -- Output from Isolation Forest
  anomaly_type VARCHAR(100),     -- Log level that triggered
  description TEXT,              -- Original log message
  affected_logs JSONB,          -- References to related logs
  severity VARCHAR(50),          -- AUTO | HIGH | MEDIUM | LOW
  status VARCHAR(50),            -- OPEN | ACKNOWLEDGED | RESOLVED
  created_at TIMESTAMP,
  resolved_at TIMESTAMP
);
```

### Elasticsearch Document (Log Storage)
```json
{
  "_index": "logs-2026.01.29",
  "_id": "log_id_value",
  "_source": {
    // All fields from StructuredLog
    // Plus computed fields for search optimization
    "message_length": 45,
    "has_exception": 1,
    "is_critical_keyword": 1
  }
}
```

## 4. Anomaly Detection Strategy

### Isolation Forest Algorithm Choice

**Why Isolation Forest?**
1. **Unsupervised**: No labeled training data required (common in ops scenarios)
2. **Efficient**: O(n*log n) complexity vs. distance-based algorithms O(n²)
3. **Effective**: Captures statistical outliers in multi-dimensional feature space
4. **Interpretable**: Can trace anomalous paths in isolation trees

### Feature Engineering

Extracted from each log:
1. **Message Length**: Unusual verbosity may indicate issues
2. **Exception Presence**: Binary indicator (0/1)
3. **Critical Keywords**: Count of {error, exception, failed, timeout, crash}
4. **Response Time**: Duration in milliseconds (normalized)
5. **Status Code**: HTTP status (normalized as code/100)

### Contamination Parameter

```python
model = IsolationForest(contamination=0.05)
# Assumes ~5% of logs are anomalies in steady state
# Adjust based on:
# - Observed anomaly rate in historical data
# - SLA requirements (lower contamination = higher sensitivity)
```

### Anomaly Score

```python
score = abs(model.score_samples(features)[0])  # Range: [0, 1]
is_anomaly = (prediction == -1) and (score > 0.7)

# Severity mapping:
if score > 0.85:
    severity = "CRITICAL"
elif score > 0.70:
    severity = "HIGH"
else:
    severity = "MEDIUM"
```

## 5. Kafka Partitioning Strategy

### Partition Key: Service Name

```
Topic: raw-logs
├── Partition 0 (service-A)  → logs ordered by timestamp
├── Partition 1 (service-B)  → logs ordered by timestamp
├── Partition 2 (service-C)  → logs ordered by timestamp
└── Partition N (service-N)  → logs ordered by timestamp
```

**Benefits**:
1. **Ordering Guarantee**: Logs from same service maintain chronological order
2. **Scalability**: Add services without rebalancing existing partitions
3. **Parallel Processing**: Different services processed independently

**Consumer Group Rebalancing**:
- Single processor instance: consumes all partitions
- Multiple instances: automatic rebalancing assigns partitions

## 6. Storage Strategy: Dual Write Pattern

### Why Elasticsearch + PostgreSQL?

| Requirement | Elasticsearch | PostgreSQL |
|---|---|---|
| Full-text search | ✅ | ❌ |
| Time-range queries | ✅ | ✅ |
| Structured incidents | ⚠️ | ✅ |
| ACID transactions | ❌ | ✅ |
| Index management | ✅ (auto-rollover) | Manual |
| Cost @ scale | Lower | Higher |

### Implementation Pattern

```python
# Dual writes from processor
def process_log(raw_log):
    parsed = parse(raw_log)
    
    # Write 1: Index in Elasticsearch (analytics)
    elasticsearch.index(index="logs-*", doc=parsed)
    
    # Write 2: Store incident in PostgreSQL (operational)
    if is_anomaly(parsed):
        postgres.insert("incidents", incident_record)
```

**Risk**: Inconsistency if one write fails. Mitigation:
- Implement retry logic with exponential backoff
- Monitor write latencies to detect degradation
- Use DLQ (Dead Letter Queue) for failed logs

## 7. Deployment Architecture

### Container Orchestration (Docker Compose)

```yaml
services:
  kafka:           # Message broker (single node for dev)
  zookeeper:       # Kafka coordination
  postgres:        # Incident storage
  elasticsearch:   # Log indexing
  log-producer:    # Spring Boot app (port 8080)
  log-processor:   # Python app (no external port)

networks:
  graduation-network:  # Internal DNS resolution

volumes:
  postgres-data:       # Persistent storage
  elasticsearch-data:  # Persistent storage
```

### Production Deployment (Not included, but guidance)

```
Kubernetes:
├── log-producer (Deployment, 3+ replicas)
├── log-processor (Deployment, 2+ replicas with auto-scaling)
├── kafka-cluster (StatefulSet, 3 brokers)
├── postgresql (StatefulSet with PVC for persistence)
└── elasticsearch (StatefulSet with data/master nodes)

Monitoring:
├── Prometheus (metrics scraping)
├── Grafana (dashboards)
└── ELK Stack (log aggregation)
```

## 8. Performance Considerations

### Throughput Optimization

**Log Producer**:
- Kafka producer batching: `linger.ms=100`, `batch.size=32KB`
- Compression: `snappy` (fast, good ratio)
- Acks: `all` (reliability over raw throughput)

**Processor**:
- Batch feature extraction: Process multiple logs before model prediction
- Isolation Forest settings: 100 trees (balance speed/accuracy)
- Elasticsearch bulk indexing: Buffer documents before flush

### Latency Targets

| Operation | Target | Actual (Dev) |
|---|---|---|
| Log ingest to Kafka | <10ms | ~5ms |
| Processor consumption | <100ms | ~50ms |
| Elasticsearch indexing | <50ms | ~30ms |
| Incident creation | <200ms | ~100ms |
| End-to-end (ingest→incident) | <500ms | ~300ms |

### Resource Constraints

```yaml
log-producer:
  memory: 512MB   # Java heap
  cpu: 500m       # 0.5 cores

log-processor:
  memory: 1GB     # Python + ML model
  cpu: 1000m      # 1 core

elasticsearch:
  memory: 2GB     # Index memory
  
postgres:
  memory: 512MB
```

## 9. Testing Strategy

### Unit Testing

**Log Producer**:
```java
@Test
void testLogValidation() {
    StructuredLog log = new StructuredLog("service", LogLevel.ERROR, "msg");
    assertTrue(logPublisher.publish(log));
}
```

**Log Processor**:
```python
def test_anomaly_detection():
    detector = AnomalyDetector()
    normal_log = {message_length: 50, ...}
    assert not detector.predict_anomaly(normal_log)[0]
```

### Integration Testing

```bash
# Docker Compose test environment
docker-compose -f docker-compose.test.yml up
# Publish test logs, verify Elasticsearch + PostgreSQL updates
```

## 10. Monitoring & Alerting

### Key Metrics

```
Application Metrics:
- logs.published.total (counter)
- logs.publish.duration (timer with percentiles)
- logs.publish.failed.total (counter)

Processor Metrics:
- anomalies.detected.total (counter)
- processor.lag (Kafka consumer group lag)

System Metrics:
- kafka.broker.bytes_in_rate
- elasticsearch.indexing.index_time_in_millis
- postgres.connections.active
```

### Alert Rules

```yaml
alerts:
  - name: HighPublishFailureRate
    condition: rate(logs.publish.failed.total[5m]) > 0.1
    severity: critical
    
  - name: ProcessorLagIncreasing
    condition: rate(processor.lag[5m]) > 100
    severity: warning
    
  - name: AnomalySpike
    condition: rate(anomalies.detected.total[5m]) > 10
    severity: info
```

## 11. Clean Architecture Principles Applied

1. **Dependency Inversion**: Services depend on abstractions (interfaces), not concrete implementations
2. **Separation of Concerns**: Parser, Detector, Processor are independent
3. **Configuration Over Hardcoding**: All settings via environment variables
4. **Single Responsibility**: Each class has one reason to change
5. **Testability**: Constructor injection enables mocking
6. **Documentation**: Comments explain the "why", not the "what"

## 12. Academic Learning Outcomes

This architecture demonstrates:

- **Distributed Systems**: Eventual consistency, at-least-once semantics
- **Microservices**: Independent deployment, technology diversity (Java + Python)
- **Event-Driven Architecture**: Kafka as the single source of truth
- **Machine Learning in Production**: Feature engineering, model serving
- **Observability**: Metrics, health checks, structured logging
- **Infrastructure as Code**: Configuration and resource management
