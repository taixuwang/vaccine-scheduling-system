# vaccine-scheduler-java

## Environment Setup
1. Clone the repository.
2. Ensure you have the PostgreSQL/SQLite JDBC driver in your IDE's classpath.
3. Set the environment variables in your IDE's Run Configuration:
   - For SQLite: `DBPath=reservation.db`

## Database Initialization
Since the `.db` file is ignored in version control, you need to initialize the tables on your first run:
1. Run the application once to automatically generate an empty `reservation.db` file.
2. Execute the SQL script located at `src/main/resources/sqlite/create.sql` against the generated `reservation.db` to construct the schemas.

## Run
Run `Scheduler.java` and follow the console prompts to interact with the system.
