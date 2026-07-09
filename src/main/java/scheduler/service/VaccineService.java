package scheduler.service;

import org.springframework.stereotype.Service;
import scheduler.context.UserContext;
import scheduler.model.*;
import scheduler.db.*;

import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.SQLException;

@Service
public class VaccineService {

    public String uploadAvailability(String date) {
        if (UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login as a caregiver first!");
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();
        try {
            Date d = Date.valueOf(date);
            String addAvailability = "INSERT INTO Availabilities VALUES (?, ?)";
            PreparedStatement statement = con.prepareStatement(addAvailability);
            statement.setDate(1, d);
            statement.setString(2, UserContext.getCaregiver().getUsername());
            statement.executeUpdate();
            statement.close();
            return "Availability uploaded!";
        } catch (IllegalArgumentException e) {
            throw new RuntimeException("Please enter a valid date!");
        } catch (SQLException e) {
            throw new RuntimeException("Error occurred when uploading availability");
        } finally {
            cm.closeConnection();
        }
    }

    public String addDoses(String vaccineName, int doses) {
        if (UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login as a caregiver first!");
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();
        try {
            con.setAutoCommit(false);
            
            // Try to update first (Atomic increment)
            String updateVaccine = "UPDATE vaccines SET Doses = Doses + ? WHERE name = ?";
            PreparedStatement updateStmt = con.prepareStatement(updateVaccine);
            updateStmt.setInt(1, doses);
            updateStmt.setString(2, vaccineName);
            int rowsAffected = updateStmt.executeUpdate();
            updateStmt.close();
            
            if (rowsAffected == 0) {
                // Vaccine does not exist, insert it
                String insertVaccine = "INSERT INTO vaccines VALUES (?, ?)";
                PreparedStatement insertStmt = con.prepareStatement(insertVaccine);
                insertStmt.setString(1, vaccineName);
                insertStmt.setInt(2, doses);
                insertStmt.executeUpdate();
                insertStmt.close();
            }

            con.commit();
            
            // Also update Redis
            try (redis.clients.jedis.Jedis jedis = scheduler.db.RedisManager.getJedis()) {
                String redisKey = "vaccine:" + vaccineName + ":doses";
                jedis.incrBy(redisKey, doses);
            } catch (Exception e) {}
            
            return "Doses updated!";
        } catch (SQLException e) {
            try { con.rollback(); } catch (SQLException ex) {}
            throw new RuntimeException("Error occurred when adding doses");
        } finally {
            try { con.setAutoCommit(true); } catch (SQLException ex) {}
            cm.closeConnection();
        }
    }
}
