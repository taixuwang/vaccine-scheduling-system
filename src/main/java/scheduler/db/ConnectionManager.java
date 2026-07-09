package scheduler.db;

import java.sql.Connection;
import java.sql.SQLException;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public class ConnectionManager {

    // Single pool instance for the entire application
    private static HikariDataSource dataSource;

    static {
        String endpoint = System.getenv("Endpoint");
        String database = System.getenv("Database");
        String user = System.getenv("Username");
        String password = System.getenv("Password");

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:postgresql://" + endpoint + ":5432/" + database);
        config.setUsername(user);
        config.setPassword(password);

        // Connection pool optimization settings
        config.setMaximumPoolSize(10);          
        config.setMinimumIdle(2);               
        config.setIdleTimeout(30000);           
        config.setConnectionTimeout(30000);     
        config.setMaxLifetime(1800000);         

        dataSource = new HikariDataSource(config);
    }

    private Connection con = null;

    public ConnectionManager() {
        // Initialization handled by HikariCP
    }

    public Connection createConnection() {
        try {
            // Retrieve connection from the pool
            con = dataSource.getConnection();
        } catch (SQLException e) {
            e.printStackTrace();
        }
        return con;
    }

    public void closeConnection() {
        if (con != null) {
            try {
                // Returns the connection to the pool rather than closing it
                this.con.close();
            } catch (SQLException e) {
                e.printStackTrace();
            }
        }
    }
    
    // Optional: for graceful shutdown
    public static void closeDataSource() {
        if (dataSource != null && !dataSource.isClosed()) {
            dataSource.close();
        }
    }
}