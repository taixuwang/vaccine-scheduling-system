FROM maven:3.8.4-openjdk-11-slim AS build
WORKDIR /app
COPY pom.xml .
COPY settings.xml .
# Download dependencies first to cache them if pom.xml doesn't change
RUN mvn -s settings.xml dependency:go-offline

COPY src ./src
RUN mvn -s settings.xml clean package -DskipTests

FROM eclipse-temurin:11-jre-focal
WORKDIR /app
COPY --from=build /app/target/vaccine-scheduler-1.0-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java","-jar","app.jar"]
