-- Initialize incident database schema
-- This script runs once when PostgreSQL container starts

CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    incident_id UUID UNIQUE NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    anomaly_score FLOAT NOT NULL,
    anomaly_type VARCHAR(100) NOT NULL,
    description TEXT,
    affected_logs JSONB,
    severity VARCHAR(50) DEFAULT 'MEDIUM',
    status VARCHAR(50) DEFAULT 'OPEN',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    INDEX idx_incident_id (incident_id),
    INDEX idx_service_name (service_name),
    INDEX idx_created_at (created_at)
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    incident_id UUID NOT NULL,
    alert_type VARCHAR(100) NOT NULL,
    channel VARCHAR(100) NOT NULL,
    recipient VARCHAR(255),
    status VARCHAR(50) DEFAULT 'PENDING',
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
);

CREATE TABLE IF NOT EXISTS processor_state (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_incident_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incident_service ON incidents(service_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_incident ON alerts(incident_id);
