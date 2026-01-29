package com.graduation.logproducer.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.graduation.logproducer.model.StructuredLog;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Service responsible for publishing structured logs to Kafka.
 * 
 * Uses Spring's KafkaTemplate for async publishing with metrics tracking.
 * Logs are partitioned by service name to maintain ordering guarantees.
 */
@Service
public class KafkaLogPublisher {
    private static final Logger logger = LoggerFactory.getLogger(KafkaLogPublisher.class);

    @Value("${kafka.topic.raw-logs:raw-logs}")
    private String topicName;

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private MeterRegistry meterRegistry;

    private final Counter publishedLogsCounter;
    private final Counter failedLogsCounter;
    private final Timer publishingTimer;

    public KafkaLogPublisher(MeterRegistry meterRegistry) {
        this.publishedLogsCounter = Counter.builder("logs.published.total")
                .description("Total number of logs published to Kafka")
                .register(meterRegistry);

        this.failedLogsCounter = Counter.builder("logs.publish.failed.total")
                .description("Total number of failed log publications")
                .register(meterRegistry);

        this.publishingTimer = Timer.builder("logs.publish.duration")
                .description("Duration of log publishing operation")
                .publishPercentiles(0.5, 0.95, 0.99)
                .register(meterRegistry);
    }

    /**
     * Publishes a structured log to Kafka.
     * 
     * @param log the structured log to publish
     * @return true if publishing was successful, false otherwise
     */
    public boolean publish(StructuredLog log) {
        return publishingTimer.recordCallable(() -> {
            try {
                String logJson = objectMapper.writeValueAsString(log);
                String partitionKey = log.getServiceName();

                // Use service name as partition key for ordering guarantees
                Message<String> message = MessageBuilder
                        .withPayload(logJson)
                        .setHeader(KafkaHeaders.TOPIC, topicName)
                        .setHeader(KafkaHeaders.MESSAGE_KEY, partitionKey)
                        .build();

                kafkaTemplate.send(message);
                publishedLogsCounter.increment();
                
                logger.debug("Published log: {} to topic: {}", log.getLogId(), topicName);
                return true;

            } catch (Exception e) {
                failedLogsCounter.increment();
                logger.error("Failed to publish log: {}", log.getLogId(), e);
                return false;
            }
        });
    }

    /**
     * Batch publishes multiple logs for efficiency.
     * 
     * @param logs list of structured logs
     * @return count of successfully published logs
     */
    public int publishBatch(java.util.List<StructuredLog> logs) {
        return logs.stream()
                .mapToInt(log -> publish(log) ? 1 : 0)
                .sum();
    }
}
