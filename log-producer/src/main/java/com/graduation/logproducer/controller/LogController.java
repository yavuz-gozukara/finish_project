package com.graduation.logproducer.controller;

import com.graduation.logproducer.model.StructuredLog;
import com.graduation.logproducer.service.KafkaLogPublisher;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashMap;
import java.util.Map;

/**
 * REST API for log ingestion.
 * 
 * Provides endpoints for external services to submit structured logs
 * for real-time analysis and incident detection.
 */
@RestController
@RequestMapping("/logs")
public class LogController {
    private static final Logger logger = LoggerFactory.getLogger(LogController.class);

    @Autowired
    private KafkaLogPublisher logPublisher;

    /**
     * Ingest a single structured log entry.
     * 
     * @param log the structured log to ingest
     * @return response indicating success or failure
     */
    @PostMapping("/ingest")
    public ResponseEntity<Map<String, Object>> ingestLog(@RequestBody StructuredLog log) {
        if (log.getServiceName() == null || log.getServiceName().isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "service_name is required"));
        }

        boolean published = logPublisher.publish(log);

        Map<String, Object> response = new HashMap<>();
        response.put("log_id", log.getLogId());
        response.put("published", published);

        return ResponseEntity.status(published ? HttpStatus.ACCEPTED : HttpStatus.INTERNAL_SERVER_ERROR)
                .body(response);
    }

    /**
     * Health check endpoint for orchestration systems.
     * 
     * @return status information
     */
    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "UP", "service", "log-producer"));
    }
}
