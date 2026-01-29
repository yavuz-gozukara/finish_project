# Multi-stage build for optimized production image

# Stage 1: Build
FROM maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /build
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src/ src/
RUN mvn clean package -DskipTests

# Stage 2: Runtime
FROM eclipse-temurin:17-jre-noble
WORKDIR /app
COPY --from=builder /build/target/log-producer-1.0.0.jar app.jar

# Create logs directory
RUN mkdir -p /app/logs

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/logs/health || exit 1

ENTRYPOINT ["java", "-jar", "app.jar"]
