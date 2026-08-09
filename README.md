# Vaccine Scheduling System

A RESTful backend application built with Java and Spring Boot for managing vaccine scheduling. The application provides endpoints for user management (patients and caregivers), vaccine inventory, and appointment bookings.

## Architecture & Tech Stack

The system is designed for high availability, high concurrency, and scalability:
- **Application Framework**: Spring Boot 2.7
- **Database**: PostgreSQL (handling transactions and concurrency control via `FOR UPDATE SKIP LOCKED`)
- **Caching**: Redis (for rapid pre-flight checks and atomic dose counting)
- **Authentication**: Stateless JWT tokens (solving multi-node session issues)
- **Connection Pooling**: HikariCP
- **Load Balancing**: Nginx

## Prerequisites

- Java 11 or higher
- Maven
- Docker and Docker Compose (recommended for deployment)
- Python 3.x with `requests` and `aiohttp` (for running the integration test suite)

## Running the Application

### Multi-Node Deployment (Recommended)

The easiest way to run the application in a production-like distributed environment is using Docker Compose. This sets up an Nginx load balancer (port 80), three application instances, a PostgreSQL server, and a Redis server.

```bash
# Build the application using Maven
mvn clean package -DskipTests

# Start the cluster in detached mode
docker-compose up --build -d
```
The API will be available at `http://localhost`.

### Running Integration Tests

A comprehensive Python test suite is provided in the `src/test/` directory to verify authentication, business logic, and concurrency safety.

```bash
# Install required Python packages
pip3 install requests aiohttp

# Run the complete test suite against the running cluster
python3 src/test/run_all.py
```

### Stopping the Cluster

```bash
# Stop and remove containers, networks, and volumes
docker-compose down
```

## System Highlights

- **Stateless Authentication**: Removed local in-memory session management in favor of JWT tokens, enabling seamless request routing across multiple nodes.
- **Concurrency Control**: Implemented robust concurrency handling using a combination of Redis atomic decrements (fast path) and PostgreSQL `FOR UPDATE SKIP LOCKED` (source of truth) to prevent overselling of vaccine doses under heavy load.
- **Resource Management**: Extensively refactored database interactions to use `try-with-resources`, ensuring no connection or statement leaks occur during high traffic or error conditions.
