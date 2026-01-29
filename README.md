# AI-Assisted Real-Time Log Analysis and Incident Detection Platform

A production-grade microservices platform for streaming structured logs, real-time anomaly detection, and incident alerting. Built as a graduation project demonstrating distributed systems, logging infrastructure, and observability patterns.

## System Architecture

```
Log Producer (Spring Boot) 
    → Kafka (Message Broker) 
    → Log Processor (Python)
    ├→ Elasticsearch (Log Storage)
    └→ PostgreSQL (Incident Metadata)
```

### Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Log Producer** | Java Spring Boot | Generates structured JSON logs via REST API |
| **Message Broker** | Apache Kafka | Reliable log streaming with ordering guarantees |
| **Log Processor** | Python + Isolation Forest | Real-time anomaly detection and incident creation |
| **Search Index** | Elasticsearch | Full-text log indexing and time-series queries |
| **Persistence** | PostgreSQL | Incident metadata, alerts, processor state |

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Java 17+ (for local development)
- Python 3.11+ (for local development)
- Maven 3.9+ (for local Spring Boot builds)

### Quick Start

```bash
# Start all services
docker-compose up -d

# Wait for services to initialize (30-60 seconds)
# Check logs: docker-compose logs -f

# Verify health
curl http://localhost:8080/api/v1/logs/health
```

### Publish Sample Log

```bash
curl -X POST http://localhost:8080/api/v1/logs/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "payment-service",
    "level": "ERROR",
    "message": "Connection timeout to database",
    "trace_id": "abc123",
    "user_id": "user-456",
    "duration_ms": 5000,
    "status_code": 500,
    "exception": "java.io.IOException"
  }'
```

### View Logs in Elasticsearch

```bash
curl http://localhost:9200/logs-*/_search?size=10 | jq .
```

### Check Incidents in PostgreSQL

```bash
psql -h localhost -U graduation -d incident_db \
  -c "SELECT * FROM incidents ORDER BY created_at DESC LIMIT 5;"
```

## Project Structure

```
.
├── log-producer/              # Java Spring Boot service
│   ├── src/main/java/
│   │   └── com/graduation/logproducer/
│   │       ├── model/         # Data models (StructuredLog)
│   │       ├── service/       # Business logic (KafkaLogPublisher)
│   │       ├── controller/    # REST endpoints
│   │       └── config/        # Kafka configuration
│   ├── pom.xml               # Maven dependencies
│   └── Dockerfile
│
├── log-processor/             # Python processor service
│   ├── processor.py          # Main processing pipeline
│   ├── requirements.txt       # Python dependencies
│   └── Dockerfile
│
├── infrastructure/            # Infrastructure configs
│   └── init.sql              # PostgreSQL schema initialization
│
└── docker-compose.yml        # Multi-container orchestration
```

## Architecture Decisions

### 1. Kafka for Log Streaming
- **Why**: Guarantees log ordering per service (partition key = service name)
- **Why**: Decouples producer from processor; producer never blocks on processing
- **Why**: Enables multiple consumers for different analysis pipelines

### 2. Isolation Forest for Anomaly Detection
- **Why**: Unsupervised learning (no labeled training data required)
- **Why**: Linear time complexity with tree ensemble approach
- **Why**: Effective for detecting statistical outliers in operational logs
- **Contamination**: Set to 5% (adjust based on observed anomaly rate)

### 3. Elasticsearch + PostgreSQL Dual Storage
- **Elasticsearch**: Fast full-text search, time-series queries, dashboard integration
- **PostgreSQL**: Transactional incident records, alert state, audit trail
- **Trade-off**: Slight duplication for operational efficiency

### 4. Spring Boot for Log Producer
- **Why**: Built-in Kafka support, excellent production tooling
- **Why**: Structured logging with Micrometer metrics
- **Why**: REST API for log ingestion from any client

## Configuration

### Environment Variables

**Log Producer** (`log-producer/src/main/resources/application.yml`)
```yaml
spring.kafka.bootstrap-servers: kafka:9092
server.port: 8080
```

**Log Processor** (Docker Compose)
```bash
KAFKA_BOOTSTRAP_SERVERS: kafka:9092
ELASTICSEARCH_HOST: elasticsearch
ELASTICSEARCH_PORT: 9200
POSTGRES_HOST: postgres
POSTGRES_USER: graduation
POSTGRES_PASSWORD: graduation-pass-2026
POSTGRES_DB: incident_db
```

### Tuning Parameters

Log Producer:
- `spring.kafka.producer.acks`: Reliability setting (default: all)
- `spring.kafka.producer.compression-type`: snappy (reduces bandwidth)

Log Processor:
- `isolation_forest_contamination`: Expected anomaly rate (default: 0.05)
- `anomaly_score_threshold`: Alert threshold (default: 0.7)

## Monitoring & Observability

### Spring Boot Actuator Endpoints

```bash
# Health check
curl http://localhost:8080/api/v1/actuator/health

# Prometheus metrics
curl http://localhost:8080/api/v1/actuator/prometheus
```

### Key Metrics

- `logs.published.total`: Count of successfully published logs
- `logs.publish.failed.total`: Count of publishing failures
- `logs.publish.duration`: Publishing latency (p50, p95, p99)

### Viewing Metrics

```bash
curl http://localhost:8080/api/v1/actuator/metrics
curl http://localhost:8080/api/v1/actuator/metrics/logs.published.total
```

## Development

### Building Log Producer Locally

```bash
cd log-producer
mvn clean package
mvn spring-boot:run
```

### Running Log Processor Locally

```bash
cd log-processor
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python processor.py
```

### Testing the Complete Flow

```bash
# Terminal 1: View logs
docker-compose logs -f log-processor

# Terminal 2: Publish logs
for i in {1..50}; do
  curl -X POST http://localhost:8080/api/v1/logs/ingest \
    -H "Content-Type: application/json" \
    -d "{\"service_name\": \"test-service\", \"level\": \"INFO\", \"message\": \"Log \$i\"}"
done

# Terminal 3: Monitor incidents
watch 'psql -h localhost -U graduation -d incident_db -c "SELECT COUNT(*) FROM incidents;"'
```

## Production Considerations

### Scalability
1. **Kafka**: Increase partitions and add broker nodes
2. **Elasticsearch**: Add replica shards and enable tiering
3. **Log Processor**: Deploy multiple instances with same consumer group
4. **Spring Boot**: Add load balancer (Nginx, HAProxy)

### Reliability
1. Enable Kafka replication (currently 1, use 3 for production)
2. Configure Elasticsearch snapshots for backup
3. Set up PostgreSQL WAL archiving for disaster recovery
4. Implement circuit breakers in Log Processor

### Security
1. Enable Kafka SSL/TLS and SASL authentication
2. Restrict PostgreSQL access via network policies
3. Add authentication to Elasticsearch (X-Pack)
4. Implement API rate limiting on Log Producer

### Performance
1. Batch logs in processor (current: 100 per batch)
2. Tune Isolation Forest hyperparameters based on data
3. Implement log sampling for high-volume scenarios
4. Add caching layer for incident deduplication

## Academic Notes

This project demonstrates:
- **Distributed Systems**: Asynchronous message processing, eventual consistency
- **Logging Infrastructure**: Structured logs, centralized storage, searchability
- **Machine Learning Operations**: Model serving in production, feature engineering
- **Microservices Architecture**: Service boundaries, inter-service communication
- **Infrastructure as Code**: Docker, Docker Compose, health checks, resource limits

## License

Graduation Project - 2026
