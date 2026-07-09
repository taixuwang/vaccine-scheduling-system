# Vaccine Scheduling System

A RESTful backend application built with Java and Spring Boot for managing vaccine scheduling. The application provides endpoints for user management (patients and caregivers), vaccine inventory, and appointment bookings.

## Architecture

The system is designed for high availability and scalability:
- **Application Server**: Spring Boot 2.7
- **Database**: PostgreSQL (or SQLite for local development)
- **Caching & Session Management**: Redis
- **Load Balancing**: Nginx

## Prerequisites

- Java 11 or higher
- Maven
- Docker and Docker Compose (for distributed deployment)

## Running the Application

### 1. Multi-Node Deployment (Recommended)

The easiest way to run the application in a production-like environment is using Docker Compose. This sets up an Nginx load balancer, three application instances, and a Redis server.

```bash
# Build the application
mvn clean package

# Start the cluster
docker-compose up --build
```
The API will be available at `http://localhost`.

Note: You may need to provide your PostgreSQL credentials in the `docker-compose.yml` or via environment variables before running Docker Compose.

### 2. Local Development (Standalone)

To run a single instance locally using Maven:

1. Ensure you have a Redis server running locally or accessible.
2. Initialize the SQLite database (if not using PostgreSQL):
   - Run the application once to generate `reservation.db`.
   - Execute `src/main/resources/sqlite/create.sql` against it.
3. Set the required environment variables (e.g., in your IDE):
   - `DBPath=reservation.db` (for SQLite)
   - `RedisEndpoint=localhost`
4. Run the application:

```bash
mvn spring-boot:run
```

The application's main entry point is `scheduler.VaccineApplication`.
