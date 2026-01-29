package com.graduation.logproducer.model;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.io.Serializable;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.UUID;

/**
 * Represents a structured log entry in JSON format.
 * 
 * This is the canonical format for all logs produced by services.
 * Fields are designed to support both operational logging and incident detection.
 */
public class StructuredLog implements Serializable {
    private static final long serialVersionUID = 1L;

    @JsonProperty("log_id")
    private String logId;

    @JsonProperty("timestamp")
    @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ss.SSS")
    private LocalDateTime timestamp;

    @JsonProperty("service_name")
    private String serviceName;

    @JsonProperty("level")
    private LogLevel level;

    @JsonProperty("message")
    private String message;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("user_id")
    private String userId;

    @JsonProperty("duration_ms")
    private Long durationMs;

    @JsonProperty("status_code")
    private Integer statusCode;

    @JsonProperty("exception")
    private String exception;

    @JsonProperty("context")
    private Map<String, Object> context;

    // Constructors
    public StructuredLog() {
        this.logId = UUID.randomUUID().toString();
        this.timestamp = LocalDateTime.now();
    }

    public StructuredLog(String serviceName, LogLevel level, String message) {
        this();
        this.serviceName = serviceName;
        this.level = level;
        this.message = message;
    }

    // Getters and Setters
    public String getLogId() { return logId; }
    public void setLogId(String logId) { this.logId = logId; }

    public LocalDateTime getTimestamp() { return timestamp; }
    public void setTimestamp(LocalDateTime timestamp) { this.timestamp = timestamp; }

    public String getServiceName() { return serviceName; }
    public void setServiceName(String serviceName) { this.serviceName = serviceName; }

    public LogLevel getLevel() { return level; }
    public void setLevel(LogLevel level) { this.level = level; }

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }

    public String getTraceId() { return traceId; }
    public void setTraceId(String traceId) { this.traceId = traceId; }

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }

    public Long getDurationMs() { return durationMs; }
    public void setDurationMs(Long durationMs) { this.durationMs = durationMs; }

    public Integer getStatusCode() { return statusCode; }
    public void setStatusCode(Integer statusCode) { this.statusCode = statusCode; }

    public String getException() { return exception; }
    public void setException(String exception) { this.exception = exception; }

    public Map<String, Object> getContext() { return context; }
    public void setContext(Map<String, Object> context) { this.context = context; }

    /**
     * Log levels following standard severity classification
     */
    public enum LogLevel {
        DEBUG,
        INFO,
        WARN,
        ERROR,
        CRITICAL
    }
}
