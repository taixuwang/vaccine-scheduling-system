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

            // 1. Ensure vaccine exists (INSERT if not, do nothing if already exists)
            String upsertVaccine = "INSERT INTO Vaccines (Name) VALUES (?) ON CONFLICT DO NOTHING";
            PreparedStatement upsertStmt = con.prepareStatement(upsertVaccine);
            upsertStmt.setString(1, vaccineName);
            upsertStmt.executeUpdate();
            upsertStmt.close();

            // 2. Insert N individual dose rows (one row per dose, no counter)
            String insertDose = "INSERT INTO VaccineDoses (Vaccine_name, Status) VALUES (?, 'available')";
            PreparedStatement insertStmt = con.prepareStatement(insertDose);
            for (int i = 0; i < doses; i++) {
                insertStmt.setString(1, vaccineName);
                insertStmt.addBatch();
            }
            insertStmt.executeBatch();
            insertStmt.close();

            con.commit();

            // 3. Update Redis cache (count of available doses)
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
