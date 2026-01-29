package com.graduation.logproducer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.kafka.annotation.EnableKafka;

/**
 * Log Producer Application Entry Point
 * 
 * Generates structured JSON logs and streams them to Apache Kafka
 * for consumption by the real-time log processor.
 * 
 * This service is designed for academic/production deployment
 * in a distributed logging infrastructure.
 */
@SpringBootApplication
@EnableKafka
public class LogProducerApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogProducerApplication.class, args);
    }
}
