package scheduler.service;

import org.springframework.stereotype.Service;
import scheduler.context.UserContext;
import scheduler.model.*;
import scheduler.db.*;

import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.ResultSet;

@Service
public class VaccineService {

    public String uploadAvailability(String date) {
        if (UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login as a caregiver");
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();
        try {
            Date d = Date.valueOf(date);
            con.setAutoCommit(false);
            String username = UserContext.getCaregiver().getUsername();
            // Serialize availability changes with reservation assignment for
            // this caregiver, including concurrent re-uploads during booking.
            try (PreparedStatement lock = con.prepareStatement(
                    "SELECT Username FROM Caregivers WHERE Username = ? FOR UPDATE")) {
                lock.setString(1, username);
                try (ResultSet ignored = lock.executeQuery()) {
                    if (!ignored.next()) {
                        throw new RuntimeException("Caregiver does not exist");
                    }
                }
            }
            try (PreparedStatement booked = con.prepareStatement(
                    "SELECT 1 FROM Reservations WHERE Caregiver_name = ? AND Time = ?")) {
                booked.setString(1, username);
                booked.setDate(2, d);
                try (ResultSet result = booked.executeQuery()) {
                    if (result.next()) {
                        throw new RuntimeException("Caregiver already has an appointment on this date");
                    }
                }
            }
            String addAvailability = "INSERT INTO Availabilities VALUES (?, ?) ON CONFLICT DO NOTHING";
            try (PreparedStatement statement = con.prepareStatement(addAvailability)) {
                statement.setDate(1, d);
                statement.setString(2, username);
                statement.executeUpdate();
            }
            con.commit();
            return "Availability uploaded!";
        } catch (IllegalArgumentException e) {
            try { con.rollback(); } catch (SQLException ignored) {}
            throw new RuntimeException("Invalid date format");
        } catch (SQLException e) {
            try { con.rollback(); } catch (SQLException ignored) {}
            throw new RuntimeException("Operation failed, please try again");
        } catch (RuntimeException e) {
            try { con.rollback(); } catch (SQLException ignored) {}
            throw e;
        } finally {
            try { con.setAutoCommit(true); } catch (SQLException ignored) {}
            cm.closeConnection();
        }
    }

    public String addDoses(String vaccineName, int doses) {
        if (UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login as a caregiver");
        }
        if (doses <= 0) {
            throw new IllegalArgumentException("Dose count must be positive");
        }
        if (vaccineName == null || vaccineName.trim().isEmpty()) {
            throw new IllegalArgumentException("Vaccine name is required");
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();
        try {
            con.setAutoCommit(false);

            // 1. Ensure vaccine exists (INSERT if not, do nothing if already exists)
            String upsertVaccine = "INSERT INTO Vaccines (Name) VALUES (?) ON CONFLICT DO NOTHING";
            try (PreparedStatement upsertStmt = con.prepareStatement(upsertVaccine)) {
                upsertStmt.setString(1, vaccineName);
                upsertStmt.executeUpdate();
            }

            // 2. Insert N individual dose rows (one row per dose, no counter)
            String insertDose = "INSERT INTO VaccineDoses (Vaccine_name, Status) VALUES (?, 'available')";
            try (PreparedStatement insertStmt = con.prepareStatement(insertDose)) {
                for (int i = 0; i < doses; i++) {
                    insertStmt.setString(1, vaccineName);
                    insertStmt.addBatch();
                }
                insertStmt.executeBatch();
            }

            con.commit();

            // 3. Update Redis cache (count of available doses)
            try (redis.clients.jedis.Jedis jedis = scheduler.db.RedisManager.getJedis()) {
                String redisKey = "vaccine:" + vaccineName + ":doses";
                jedis.incrBy(redisKey, doses);
            } catch (Exception e) {}

            return "Doses updated!";
        } catch (SQLException e) {
            try { con.rollback(); } catch (SQLException ex) {}
            throw new RuntimeException("Operation failed, please try again");
        } finally {
            try { con.setAutoCommit(true); } catch (SQLException ex) {}
            cm.closeConnection();
        }
    }
}
