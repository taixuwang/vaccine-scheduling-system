package scheduler.db;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;

public class CreateTables {
    public static void main(String[] args) {
        String endpoint = System.getenv("Endpoint");
        String database = System.getenv("Database");
        String user = System.getenv("Username");
        String password = System.getenv("Password");

        String url = "jdbc:postgresql://" + endpoint + ":5432/" + database;

        try (Connection conn = DriverManager.getConnection(url, user, password);
             Statement stmt = conn.createStatement()) {

            System.out.println("Connected to PostgreSQL successfully.");

            Path sqlPath = Path.of("src/main/resources/aurora/aurora-create.sql");
            String sql = Files.readString(sqlPath);
            stmt.execute(sql);
            System.out.println("Tables created successfully from aurora-create.sql.");
        } catch (SQLException e) {
            e.printStackTrace();
        } catch (IOException e) {
            System.out.println("Failed to read aurora-create.sql.");
            e.printStackTrace();
        }
    }
}