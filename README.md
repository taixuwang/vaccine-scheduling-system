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
- Python 3.9+ with the dependencies in `requirements.txt` (for the test suite)

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

### Running Tests

The tests create accounts, availability, and vaccine inventory. Run integration
and load tests only against a disposable instance: the application has no API
for deleting these fixtures. The test scripts do not truncate the database or
flush Redis.

```bash
# Install the test dependencies
python3 -m pip install -r requirements.txt

# Run offline checks (integration tests are skipped unless explicitly configured)
python3 -m unittest discover -s src/test -v

# Run integration tests against a running, disposable cluster
python3 src/test/run_all.py --target http://localhost
```

The suite includes regression tests for known backend defects, so it may report
failures until those defects are fixed. See [the test guide](src/test/README.md)
for configuration, individual suites, and fixture details.

### Running Load Tests

A throughput and latency load test script is available to benchmark the performance of the system under sustained load. This test measures the requests per second (req/s), latency distributions, and error rates across critical endpoints.

```bash
# Run the load test against a disposable cluster (20 threads, 10 seconds per workload)
python3 src/test/test_throughput.py

# Run with custom parameters and target
python3 src/test/test_throughput.py --target http://localhost --threads 50 --duration 15
```

### Stopping the Cluster

```bash
# Stop and remove containers and networks
docker-compose down
```

## System Highlights

- **Stateless Authentication**: Removed local in-memory session management in favor of JWT tokens, enabling seamless request routing across multiple nodes.
- **Concurrency Control**: Implemented robust concurrency handling using a combination of Redis atomic decrements (fast path) and PostgreSQL `FOR UPDATE SKIP LOCKED` (source of truth) to prevent overselling of vaccine doses under heavy load.
- **Resource Management**: Extensively refactored database interactions to use `try-with-resources`, ensuring no connection or statement leaks occur during high traffic or error conditions.
