# Implementation & Testing Guide

## Local Development Setup

This guide walks through setting up and testing the platform locally.

### Prerequisites

```bash
# Check installations
docker --version          # Docker 24+
docker-compose --version  # Docker Compose 2.0+
java -version            # Java 17+
python3 --version        # Python 3.11+
```

## Phase 1: Infrastructure Setup

### Step 1a: Start All Services

```bash
cd /workspaces/finish_project

# Build and start all services
docker-compose up -d

# Verify all services are running
docker-compose ps

# Expected output:
# NAME                COMMAND                  SERVICE            STATUS
# postgres            "docker-entrypoint.s…"   postgres           Up (healthy)
# elasticsearch       "/bin/tini -- /usr/l…"  elasticsearch      Up (healthy)
# kafka               "/etc/confluent/dock…"   kafka              Up (healthy)
# zookeeper           "/etc/confluent/dock…"   zookeeper          Up (healthy)
# log-producer        "java -jar app.jar"      log-producer       Up (healthy)
# log-processor       "python processor.py"    log-processor      Up (healthy)
```

### Step 1b: Verify Health Checks

```bash
# Log Producer health
curl http://localhost:8080/api/v1/logs/health
# Expected: {"status":"UP","service":"log-producer"}

# Elasticsearch health
curl http://localhost:9200/_cluster/health
# Expected: {"cluster_name":"elasticsearch","status":"green",...}

# PostgreSQL connection (inside container)
docker-compose exec postgres psql -U graduation -d incident_db -c "SELECT 1;"
# Expected: 1
```

### Step 1c: Monitor Logs

```bash
# Follow all logs
docker-compose logs -f

# Or specific service
docker-compose logs -f log-processor
docker-compose logs -f log-producer

# Exit with Ctrl+C
```

## Phase 2: Basic Functionality Test

### Step 2a: Publish Single Log

```bash
# Publish an INFO level log
curl -X POST http://localhost:8080/api/v1/logs/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "api-gateway",
    "level": "INFO",
    "message": "Request processed successfully",
    "trace_id": "trace-001",
    "user_id": "user-123",
    "duration_ms": 45,
    "status_code": 200
  }'

# Expected response:
# {
#   "log_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
#   "published": true
# }
```

### Step 2b: Verify Elasticsearch Storage

```bash
# Wait 2-3 seconds for indexing

# Search all logs
curl http://localhost:9200/logs-*/_search?pretty

# Should see the log indexed with metadata added:
# {
#   "_source": {
#     "log_id": "...",
#     "timestamp": "2026-01-29T...",
#     "message_length": 30,
#     "has_exception": 0,
#     "is_critical_keyword": 0
#   }
# }

# Count logs
curl http://localhost:9200/logs-*/_count
# {"count":1,"_shards":{"total":1,...}}
```

### Step 2c: Check PostgreSQL

```bash
# Connect to database
docker-compose exec postgres psql -U graduation -d incident_db

# Inside psql:
SELECT COUNT(*) FROM incidents;  -- Should be 0 (no anomalies yet)
SELECT COUNT(*) FROM incidents;
\q  # Exit

# Or single command:
docker-compose exec postgres psql -U graduation -d incident_db \
  -c "SELECT COUNT(*) as incident_count FROM incidents;"
```

## Phase 3: Anomaly Detection Test

### Step 3a: Publish Anomalous Logs

The Isolation Forest requires ~50 normal logs to train before detecting anomalies.

```bash
#!/bin/bash
# Publish 50 normal logs from different services
echo "Publishing 50 normal logs for model training..."
for i in {1..50}; do
  curl -X POST http://localhost:8080/api/v1/logs/ingest \
    -H "Content-Type: application/json" \
    -d "{
      \"service_name\": \"order-service\",
      \"level\": \"INFO\",
      \"message\": \"Order processed\",
      \"trace_id\": \"trace-normal-$i\",
      \"duration_ms\": $((50 + RANDOM % 50)),
      \"status_code\": 200
    }" 2>/dev/null
  
  # Small delay to avoid overwhelming
  sleep 0.1
done

echo "Normal logs published. Model training started..."
sleep 5

# Now publish anomalous logs (high latency, errors)
echo "Publishing anomalous logs..."
for i in {1..5}; do
  curl -X POST http://localhost:8080/api/v1/logs/ingest \
    -H "Content-Type: application/json" \
    -d "{
      \"service_name\": \"order-service\",
      \"level\": \"ERROR\",
      \"message\": \"Database connection timeout\",
      \"trace_id\": \"trace-anomaly-$i\",
      \"duration_ms\": 5000,
      \"status_code\": 500,
      \"exception\": \"java.sql.SQLTimeoutException: Connection timeout\"
    }" 2>/dev/null
  sleep 0.2
done

echo "Test logs published!"
```

Save as `publish_test_logs.sh`:
```bash
chmod +x publish_test_logs.sh
./publish_test_logs.sh
```

### Step 3b: Monitor Processor Output

```bash
# Watch processor logs in real-time
docker-compose logs -f log-processor

# Look for lines like:
# 2026-01-29 14:35:22 - __main__ - WARNING - Anomaly detected: ...
```

### Step 3c: Query Detected Incidents

```bash
# Check PostgreSQL for incidents
docker-compose exec postgres psql -U graduation -d incident_db \
  -c "SELECT incident_id, service_name, anomaly_score, severity, created_at 
       FROM incidents 
       ORDER BY created_at DESC 
       LIMIT 5;"

# Expected output:
#                 incident_id            | service_name | anomaly_score | severity | created_at
# xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx | order-service |      0.82     |  HIGH    | 2026-01-29 14:35:22
```

### Step 3d: Search Anomalous Logs in Elasticsearch

```bash
# Get all ERROR level logs
curl 'http://localhost:9200/logs-*/_search?pretty' \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "match": {
        "level": "ERROR"
      }
    },
    "size": 10
  }'

# Get logs with specific duration range (anomaly indicator)
curl 'http://localhost:9200/logs-*/_search?pretty' \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "range": {
        "duration_ms": {
          "gte": 4000
        }
      }
    }
  }'
```

## Phase 4: Producer Metrics & Monitoring

### Step 4a: Access Prometheus Metrics

```bash
# Raw metrics endpoint
curl http://localhost:8080/api/v1/actuator/prometheus

# Specific metric: logs published
curl http://localhost:8080/api/v1/actuator/metrics/logs.published.total

# Response format:
# {
#   "name": "logs.published.total",
#   "description": "Total number of logs published to Kafka",
#   "value": 55
# }
```

### Step 4b: Monitor Publishing Performance

```bash
# Observe publishing latency percentiles
curl http://localhost:8080/api/v1/actuator/metrics/logs.publish.duration

# Look for p50, p95, p99 values
```

## Phase 5: End-to-End Flow Verification

### Step 5a: Full Scenario Test

```bash
#!/bin/bash
# Complete test scenario

echo "=== Phase 1: Clear previous data ==="
docker-compose exec postgres psql -U graduation -d incident_db \
  -c "TRUNCATE incidents; TRUNCATE alerts;"
docker-compose exec elasticsearch curl -X DELETE "localhost:9200/logs-*"

sleep 2

echo "=== Phase 2: Publish normal baseline ==="
# 60 normal logs for better model training
for i in {1..60}; do
  curl -s -X POST http://localhost:8080/api/v1/logs/ingest \
    -H "Content-Type: application/json" \
    -d "{
      \"service_name\": \"auth-service\",
      \"level\": \"INFO\",
      \"message\": \"Authentication successful\",
      \"duration_ms\": $((30 + RANDOM % 40)),
      \"status_code\": 200
    }" > /dev/null
done

echo "Baseline published. Waiting for processing..."
sleep 10

echo "=== Phase 3: Publish anomalies ==="
# High latency events
for i in {1..3}; do
  curl -s -X POST http://localhost:8080/api/v1/logs/ingest \
    -H "Content-Type: application/json" \
    -d "{
      \"service_name\": \"auth-service\",
      \"level\": \"ERROR\",
      \"message\": \"LDAP server connection failed\",
      \"duration_ms\": 9000,
      \"status_code\": 503,
      \"exception\": \"TimeoutException\"
    }" > /dev/null
done

echo "Anomalies published. Waiting for detection..."
sleep 5

echo "=== Phase 4: Results ==="
echo "Incidents detected:"
docker-compose exec postgres psql -U graduation -d incident_db \
  -c "SELECT COUNT(*) as count FROM incidents;"

echo ""
echo "Incident details:"
docker-compose exec postgres psql -U graduation -d incident_db \
  -c "SELECT service_name, anomaly_score, severity FROM incidents LIMIT 3;"

echo ""
echo "Logs in Elasticsearch:"
docker-compose exec -e ELASTICSEARCH_HOST=elasticsearch elasticsearch \
  curl -s "http://localhost:9200/logs-*/_count" | jq '.count'

echo ""
echo "Producer metrics:"
curl -s http://localhost:8080/api/v1/actuator/metrics/logs.published.total | jq '.value'
```

## Phase 6: Troubleshooting

### Issue: Services not starting

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs log-producer
docker-compose logs log-processor

# Clean and restart
docker-compose down -v
docker-compose up -d

# Check port conflicts
lsof -i :8080  # Log Producer
lsof -i :9200  # Elasticsearch
lsof -i :5432  # PostgreSQL
```

### Issue: Logs not appearing in Elasticsearch

```bash
# Check Elasticsearch is accepting writes
curl -X POST http://localhost:9200/test/_doc -H 'Content-Type: application/json' \
  -d '{"test": "value"}'

# Check index exists
curl http://localhost:9200/_cat/indices

# Check Elasticsearch disk space
curl http://localhost:9200/_cluster/health?v
```

### Issue: PostgreSQL connection failures

```bash
# Test connection
docker-compose exec postgres psql -U graduation -d incident_db -c "SELECT 1;"

# Check logs
docker-compose logs postgres

# View active connections
docker-compose exec postgres psql -U graduation -d incident_db \
  -c "SELECT datname, usename, state FROM pg_stat_activity;"
```

### Issue: Processor not detecting anomalies

```bash
# Check Isolation Forest training
docker-compose logs log-processor | grep -i "train"

# Verify model parameters
# Look for: "Model trained on X samples"

# Check feature extraction
docker-compose logs log-processor | grep -i "feature"

# Verify anomaly threshold is not too high (default: 0.7)
# If no anomalies, try lowering threshold in processor.py
```

## Phase 7: Performance Baseline

### Measure Throughput

```bash
# Publish 100 logs rapidly and measure time
time for i in {1..100}; do
  curl -s -X POST http://localhost:8080/api/v1/logs/ingest \
    -H "Content-Type: application/json" \
    -d '{"service_name":"test","level":"INFO","message":"Log '$i'"}' > /dev/null
done

# Expected: ~2-5 seconds for 100 logs (20-50 logs/sec)
# This is acceptable for demonstration; production with batching: 1000+ logs/sec
```

### Check Processing Latency

```bash
# Timestamp a log publication
start=$(date +%s%N)
curl -X POST http://localhost:8080/api/v1/logs/ingest \
  -H "Content-Type: application/json" \
  -d '{"service_name":"latency-test","level":"INFO","message":"Test"}' 
end=$(date +%s%N)

# Calculate latency
echo "Producer latency: $((($end - $start) / 1000000)) ms"

# Check if incident appears in PostgreSQL (delay indicates processor latency)
```

## Cleanup & Reset

```bash
# Stop all services
docker-compose down

# Remove all data
docker-compose down -v

# Rebuild images (after code changes)
docker-compose build --no-cache

# Full reset
docker-compose down -v
docker system prune -f
docker-compose up -d --build
```

## Next Steps: Extending the Platform

### 1. Add Alert Integration
Modify `log-processor/processor.py` to send alerts:
```python
def _send_alert(self, incident_id, severity):
    # Email integration
    # Slack integration
    # PagerDuty integration
    pass
```

### 2. Add Log Sampling
For high-volume scenarios, add sampling in producer:
```python
if random.random() < sampling_rate:
    publish_log(log)
```

### 3. Add Dashboards
Use Kibana (Elasticsearch):
```bash
# Kibana UI at http://localhost:5601
# Create visualizations for:
# - Logs per service
# - Anomaly rate over time
# - Average latency trends
```

### 4. Scale Processor
Deploy multiple processor instances:
```yaml
log-processor:
  deploy:
    replicas: 3  # Docker Compose scaling
```

## Documentation References

- [README.md](README.md) - Project overview
- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed architecture decisions
- Producer Code: [log-producer/](log-producer/)
- Processor Code: [log-processor/](log-processor/)
