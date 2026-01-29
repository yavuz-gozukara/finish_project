# Quick Reference Guide

## Commands Cheat Sheet

### Starting the Platform

```bash
cd /workspaces/finish_project
docker-compose up -d
```

### Checking Service Health

```bash
# All services
docker-compose ps

# Specific service logs
docker-compose logs -f log-producer
docker-compose logs -f log-processor

# Health endpoint
curl http://localhost:8080/api/v1/logs/health
```

### Publishing Logs

```bash
# Single log
curl -X POST http://localhost:8080/api/v1/logs/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "my-service",
    "level": "ERROR",
    "message": "Something went wrong",
    "duration_ms": 1000,
    "status_code": 500
  }'

# Batch test (50 logs)
for i in {1..50}; do
  curl -X POST http://localhost:8080/api/v1/logs/ingest \
    -H "Content-Type: application/json" \
    -d '{"service_name":"test","level":"INFO","message":"Log '$i'"}' &
done
```

### Querying Data

```bash
# View Elasticsearch logs
curl http://localhost:9200/logs-*/_search | jq .

# Count logs
curl http://localhost:9200/logs-*/_count | jq .count

# Check incidents
docker-compose exec postgres psql -U graduation -d incident_db \
  -c "SELECT * FROM incidents ORDER BY created_at DESC LIMIT 5;"

# Count incidents
docker-compose exec postgres psql -U graduation -d incident_db \
  -c "SELECT COUNT(*) FROM incidents;"
```

### Monitoring Metrics

```bash
# All metrics
curl http://localhost:8080/api/v1/actuator/metrics | jq .

# Specific metric
curl http://localhost:8080/api/v1/actuator/metrics/logs.published.total | jq .value

# Prometheus format
curl http://localhost:8080/api/v1/actuator/prometheus
```

### Stopping Services

```bash
# Stop all services (keep data)
docker-compose stop

# Stop and remove all services
docker-compose down

# Stop and remove all data
docker-compose down -v
```

## API Reference

### POST /api/v1/logs/ingest

**Request:**
```json
{
  "service_name": "string (required)",
  "level": "ERROR|WARN|INFO|DEBUG|CRITICAL",
  "message": "string",
  "trace_id": "string",
  "user_id": "string",
  "duration_ms": "number",
  "status_code": "number",
  "exception": "string",
  "context": {
    "key": "value"
  }
}
```

**Response (200 Accepted):**
```json
{
  "log_id": "uuid",
  "published": true
}
```

**Error Response (400):**
```json
{
  "error": "service_name is required"
}
```

### GET /api/v1/logs/health

**Response:**
```json
{
  "status": "UP",
  "service": "log-producer"
}
```

### GET /api/v1/actuator/metrics

**Response:**
```json
{
  "names": [
    "logs.published.total",
    "logs.publish.failed.total",
    "logs.publish.duration",
    ...
  ]
}
```

## Database Queries

### PostgreSQL

```sql
-- View incidents
SELECT incident_id, service_name, anomaly_score, severity, created_at 
FROM incidents 
ORDER BY created_at DESC;

-- Count by severity
SELECT severity, COUNT(*) 
FROM incidents 
GROUP BY severity;

-- High-scoring anomalies
SELECT incident_id, service_name, anomaly_score 
FROM incidents 
WHERE anomaly_score > 0.8 
ORDER BY anomaly_score DESC;

-- Incidents from last hour
SELECT * FROM incidents 
WHERE created_at > NOW() - INTERVAL '1 hour' 
ORDER BY created_at DESC;
```

### Elasticsearch

```bash
# All logs from service-X
curl 'http://localhost:9200/logs-*/_search' \
  -d '{"query": {"match": {"service_name": "service-X"}}}'

# ERROR level logs only
curl 'http://localhost:9200/logs-*/_search' \
  -d '{"query": {"match": {"level": "ERROR"}}}'

# Slow requests (>1000ms)
curl 'http://localhost:9200/logs-*/_search' \
  -d '{"query": {"range": {"duration_ms": {"gte": 1000}}}}'

# Logs with exceptions
curl 'http://localhost:9200/logs-*/_search' \
  -d '{"query": {"exists": {"field": "exception"}}}'

# Time-based search (last 1 hour)
curl 'http://localhost:9200/logs-*/_search' \
  -d '{
    "query": {
      "range": {
        "timestamp": {
          "gte": "now-1h"
        }
      }
    }
  }'
```

## Configuration

### Log Producer (application.yml)

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      retries: 3
      compression-type: snappy

server:
  port: 8080
```

### Log Processor (environment variables)

```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
ELASTICSEARCH_HOST=localhost
ELASTICSEARCH_PORT=9200
POSTGRES_HOST=localhost
POSTGRES_USER=graduation
POSTGRES_PASSWORD=graduation-pass-2026
POSTGRES_DB=incident_db
```

## Key Metrics Explained

| Metric | Unit | Meaning |
|--------|------|---------|
| `logs.published.total` | count | Total logs sent to Kafka |
| `logs.publish.failed.total` | count | Failed publishes (errors) |
| `logs.publish.duration` | ms | Time to publish (p50, p95, p99) |
| `anomalies.detected.total` | count | Anomalies found by processor |
| `processor.lag` | offset | Kafka consumer lag (lower is better) |

## Typical Thresholds

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Anomaly Score Threshold | 0.7 | 70% isolation = anomaly (adjustable) |
| Isolation Forest Contamination | 0.05 | Assume 5% of logs are anomalies |
| Kafka Batching Linger | 100ms | Wait up to 100ms for batch |
| Kafka Batch Size | 32KB | Batch up to 32KB of logs |
| Producer Acks | all | Wait for all replicas (safe) |

## Architecture at a Glance

```
Client
  ↓ (REST)
Log Producer (port 8080)
  ↓ (Kafka)
Message Broker (port 9092)
  ↓ (Kafka Consumer)
Log Processor (Python)
  ├→ Elasticsearch (port 9200) - logs search
  └→ PostgreSQL (port 5432) - incidents
```

## File Locations

```
/workspaces/finish_project/
├── log-producer/
│   ├── src/main/java/com/graduation/logproducer/
│   │   ├── model/StructuredLog.java
│   │   ├── service/KafkaLogPublisher.java
│   │   ├── controller/LogController.java
│   │   └── config/KafkaConfig.java
│   ├── src/main/resources/application.yml
│   ├── pom.xml
│   └── Dockerfile
├── log-processor/
│   ├── processor.py
│   ├── requirements.txt
│   └── Dockerfile
├── infrastructure/
│   └── init.sql
├── docker-compose.yml
├── README.md
├── ARCHITECTURE.md
├── IMPLEMENTATION_GUIDE.md
└── QUICK_REFERENCE.md (this file)
```

## Troubleshooting Quick Fixes

| Issue | Solution |
|-------|----------|
| Port already in use | `lsof -i :8080` and `kill -9 <PID>` |
| Elasticsearch disk full | `docker-compose exec elasticsearch curl -X DELETE "localhost:9200/logs-*"` |
| No anomalies detected | Publish 50+ normal logs first for model training |
| Processor lag increasing | Check Elasticsearch write latency or increase processor instances |
| Logs not in Elasticsearch | Check processor logs: `docker-compose logs log-processor` |
| Database connection error | Verify PostgreSQL is healthy: `docker-compose exec postgres pg_isready` |

## Performance Optimization

### Increase Throughput

```yaml
# log-producer/pom.xml (modify build config)
spring.kafka.producer.batch.size: 65536  # Increase from 32KB
spring.kafka.producer.linger.ms: 200      # Increase from 100ms
```

### Improve Anomaly Detection

```python
# log-processor/processor.py
model = IsolationForest(
    contamination=0.02,      # Lower = more sensitive
    n_estimators=150,        # More trees = better accuracy
    random_state=42
)
```

### Scale Processor

```bash
# Run multiple instances
docker-compose up -d --scale log-processor=3
```

## Learning Resources

- **Kafka Concepts**: Partitions, Consumer Groups, Offsets
- **Isolation Forest**: Unsupervised anomaly detection, tree ensembles
- **Elasticsearch**: Inverted indexes, sharding, mapping
- **Spring Boot**: Actuator metrics, Kafka integration
- **Docker Compose**: Multi-container orchestration, networking

## Next Steps

1. **Local Testing**: Follow [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)
2. **Architecture Deep Dive**: Read [ARCHITECTURE.md](ARCHITECTURE.md)
3. **Extend Functionality**: Add alerting, dashboards, or more ML algorithms
4. **Production Deployment**: Use Kubernetes for scaling
5. **Performance Tuning**: Monitor metrics and adjust parameters

## Support Resources

- Kafka Docs: https://kafka.apache.org/documentation/
- Elasticsearch Docs: https://www.elastic.co/guide/en/elasticsearch/reference/
- Spring Boot Docs: https://spring.io/projects/spring-boot
- Scikit-learn Docs: https://scikit-learn.org/
- Docker Docs: https://docs.docker.com/
