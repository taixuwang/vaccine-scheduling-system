package scheduler.service;

import org.springframework.stereotype.Service;
import scheduler.context.UserContext;
import java.util.ArrayList;
import java.util.List;
import scheduler.model.*;
import scheduler.db.*;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Date;
import scheduler.model.Vaccine.VaccineGetter;

@Service
public class ReservationService {

    public List<String> searchCaregiverSchedule(String date) {
        if (UserContext.getPatient() == null && UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login first");
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        List<String> res = new ArrayList<>();
        try {
            Date d = Date.valueOf(date);
            String getSchedule = "SELECT A.Username FROM Availabilities as A WHERE Time = ? ORDER BY A.Username";
            try (PreparedStatement sheduleStatement = con.prepareStatement(getSchedule)) {
                sheduleStatement.setDate(1, d);
                try (ResultSet scheduleResult = sheduleStatement.executeQuery()) {
                    res.add("Caregivers:");
                    boolean hasCaregivers = false;
                    while (scheduleResult.next()) {
                        hasCaregivers = true;
                        res.add(scheduleResult.getString("Username"));
                    }
                    if (!hasCaregivers) {
                        res.add("No caregivers available");
                    }
                }
            }
            String getVaccine = "SELECT V.Name, COUNT(D.Dose_id) as Doses FROM Vaccines as V JOIN VaccineDoses as D ON V.Name = D.Vaccine_name WHERE D.Status = 'available' GROUP BY V.Name";
            try (PreparedStatement vaccineStatement = con.prepareStatement(getVaccine)) {
                try (ResultSet vaccineResult = vaccineStatement.executeQuery()) {
                    res.add("Vaccines:");
                    boolean hasVaccines = false;
                    while (vaccineResult.next()) {
                        hasVaccines = true;
                        res.add(vaccineResult.getString("Name") + " " + vaccineResult.getInt("Doses"));
                    }
                    if (!hasVaccines) {
                        res.add("No vaccines available");
                    }
                }
            }
        } catch (IllegalArgumentException e) {
            throw new RuntimeException("Invalid date format");
        } catch (SQLException e) {
            throw new RuntimeException("Operation failed, please try again");
        } finally {
            cm.closeConnection();
        }
        
        return res;
    }

    public String reserve(String date, String vaccineName) {
        if (UserContext.getPatient() == null) {
            throw new RuntimeException("Please login first");
        }
        if (UserContext.getCaregiver() != null) {
            throw new RuntimeException("Please login as a patient");
        }

        // 1. Redis Cache Interception (atomic claim when Redis is up)
        String redisKey = "vaccine:" + vaccineName + ":doses";
        long currentStock = -1;
        boolean redisDown = false;
        try (redis.clients.jedis.Jedis jedis = scheduler.db.RedisManager.getJedis()) {
            currentStock = jedis.decr(redisKey);
        } catch (Exception e) {
            redisDown = true;
        }

        if (redisDown) {
            // Redis is down: skip the check, the SKIP LOCKED claim later in the transaction is
            // the real guard against oversell.
            currentStock = 1; // pass the guard below; the real claim happens via SKIP LOCKED
        } else if (currentStock < 0) {
            try (redis.clients.jedis.Jedis jedis = scheduler.db.RedisManager.getJedis()) {
                jedis.incr(redisKey); // Revert the negative count
            } catch (Exception e) {}
            throw new RuntimeException("Not enough available doses");
        }

        boolean reserveSuccess = false;
        try {
            ConnectionManager cm = new ConnectionManager();
            Connection con = cm.createConnection();

            try {
                con.setAutoCommit(false);
                Date d = Date.valueOf(date);

                // 1. Claim a vaccine dose and mark it reserved in one statement
                String getDose = "WITH dose AS (SELECT Dose_id FROM VaccineDoses WHERE Vaccine_name = ? AND Status = 'available' LIMIT 1 FOR UPDATE SKIP LOCKED) UPDATE VaccineDoses d SET Status = 'reserved' FROM dose WHERE d.Dose_id = dose.Dose_id RETURNING d.Dose_id";
                int doseId;
                try (PreparedStatement doseStatement = con.prepareStatement(getDose)) {
                    doseStatement.setString(1, vaccineName);
                    try (ResultSet doseResult = doseStatement.executeQuery()) {
                        if (!doseResult.next()) {
                            con.rollback();
                            throw new RuntimeException("Not enough available doses");
                        }
                        doseId = doseResult.getInt("Dose_id");
                    }
                }

                // 2. Select caregiver and remove availability in one statement
                String getCaregiver = "WITH avail AS (SELECT Time, Username FROM Availabilities WHERE Time = ? ORDER BY Username LIMIT 1 FOR UPDATE SKIP LOCKED) DELETE FROM Availabilities a USING avail WHERE a.Time = avail.Time AND a.Username = avail.Username RETURNING a.Username";
                String assignedCaregiver;
                try (PreparedStatement caregiverStatement = con.prepareStatement(getCaregiver)) {
                    caregiverStatement.setDate(1, d);
                    try (ResultSet caregiverResult = caregiverStatement.executeQuery()) {
                        if (!caregiverResult.next()) {
                            con.rollback();
                            throw new RuntimeException("No caregiver available");
                        }
                        assignedCaregiver = caregiverResult.getString("Username");
                    }
                }

                try {
                    String addReservations = "INSERT INTO Reservations (Patient_name, Caregiver_name, Vaccine_name, Dose_id, Time) VALUES (?, ?, ?, ?, ?)";
                    try (PreparedStatement addStatement = con.prepareStatement(addReservations, java.sql.Statement.RETURN_GENERATED_KEYS)) {
                        addStatement.setString(1, UserContext.getPatient().getUsername());
                        addStatement.setString(2, assignedCaregiver);
                        addStatement.setString(3, vaccineName);
                        addStatement.setInt(4, doseId);
                        addStatement.setDate(5, d);
                        addStatement.executeUpdate();

                        try (ResultSet generatedKeys = addStatement.getGeneratedKeys()) {
                            int currentId = 0;
                            if (generatedKeys.next()) {
                                currentId = generatedKeys.getInt(1);
                            }
                            String resMsg = "Appointment ID "+ currentId + ", Caregiver username " + assignedCaregiver;

                            con.commit();
                            reserveSuccess = true; // Mark as success!
                            return resMsg;
                        }
                    }
                } catch (SQLException e) {
                    con.rollback();
                    throw e;
                }
            } catch (IllegalArgumentException e) {
                throw new RuntimeException("Invalid date format");
            } catch (SQLException e) {
                try { con.rollback(); } catch (SQLException ex) {}
                throw new RuntimeException("Operation failed, please try again");
            } finally {
                try { con.setAutoCommit(true); } catch (SQLException ex) {}
                cm.closeConnection();
            }
        } finally {
            if (!reserveSuccess && !redisDown) {
                // If anything failed, return the dose to Redis (only if we actually claimed one)
                try (redis.clients.jedis.Jedis jedis = scheduler.db.RedisManager.getJedis()) {
                    jedis.incr(redisKey);
                } catch (Exception e) {}
            }
        }
    }

    public String cancel(String appointmentId) {
        if (UserContext.getPatient() == null && UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login first");
        }

        int appId;
        try {
            appId = Integer.parseInt(appointmentId);
        } catch (NumberFormatException e) {
            throw new RuntimeException("Appointment ID " + appointmentId + " does not exist");
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        try {
            con.setAutoCommit(false);
            String getAppointment = "SELECT R.Appointment_id, R.Patient_name, R.Caregiver_name, R.Vaccine_name, R.Dose_id, R.Time FROM Reservations as R WHERE R.Appointment_id = ? FOR UPDATE";
            String patientName, caregiverName, vaccineName;
            int doseId;
            Date time;
            try (PreparedStatement statement = con.prepareStatement(getAppointment)) {
                statement.setInt(1, appId);
                try (ResultSet result = statement.executeQuery()) {
                    if (!result.next()) {
                        throw new RuntimeException("Appointment ID " + appointmentId + " does not exist");
                    }
                    patientName = result.getString("Patient_name");
                    caregiverName = result.getString("Caregiver_name");
                    vaccineName = result.getString("Vaccine_name");
                    doseId = result.getInt("Dose_id");
                    time = result.getDate("Time");
                }
            }

            if (UserContext.getPatient() != null && !UserContext.getPatient().getUsername().equals(patientName)) {
                throw new RuntimeException("Access denied");
            }
            if (UserContext.getCaregiver() != null && !UserContext.getCaregiver().getUsername().equals(caregiverName)) {
                throw new RuntimeException("Access denied");
            }

            try {
                String deleteReservation = "DELETE FROM Reservations as R WHERE R.Appointment_id = ?";
                try (PreparedStatement deleteStatement = con.prepareStatement(deleteReservation)) {
                    deleteStatement.setInt(1, appId);
                    deleteStatement.executeUpdate();
                }
                
                // Restore the specific dose to available (replaces UPDATE vaccines SET Doses = Doses + 1)
                String restoreDose = "UPDATE VaccineDoses SET Status = 'available' WHERE Dose_id = ?";
                try (PreparedStatement restoreStmt = con.prepareStatement(restoreDose)) {
                    restoreStmt.setInt(1, doseId);
                    restoreStmt.executeUpdate();
                }
                
                String addAvailability = "INSERT INTO Availabilities VALUES (?, ?)";
                try (PreparedStatement addStatement = con.prepareStatement(addAvailability)) {
                    addStatement.setDate(1, time);
                    addStatement.setString(2, caregiverName);
                    addStatement.executeUpdate();
                }

                con.commit();

                // Sync Redis cache with restored dose
                try (redis.clients.jedis.Jedis jedis = scheduler.db.RedisManager.getJedis()) {
                    String redisKey = "vaccine:" + vaccineName + ":doses";
                    jedis.incr(redisKey);
                } catch (Exception redisEx) {
                    // Redis update is best-effort; DB is the source of truth
                }

                return "Appointment ID " + appointmentId + " has been successfully canceled";
            } catch (SQLException e) {
                con.rollback();
                throw e;
            }
        } catch (SQLException e) {
            throw new RuntimeException("Operation failed, please try again");
        } finally {
            try { con.setAutoCommit(true); } catch (SQLException ex) {}
            cm.closeConnection();
        }
    }

    public List<String> showAppointments() {
        if (UserContext.getPatient() == null && UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login first");
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        List<String> res = new ArrayList<>();
        try {
            String query;
            String username;
            if (UserContext.getPatient() != null) {
                query = "SELECT R.Appointment_id, R.Vaccine_name, R.Time, R.Caregiver_name as Name FROM Reservations as R WHERE R.Patient_name = ? ORDER BY R.Appointment_id";
                username = UserContext.getPatient().getUsername();
            } else {
                query = "SELECT R.Appointment_id, R.Vaccine_name, R.Time, R.Patient_name as Name FROM Reservations as R WHERE R.Caregiver_name = ? ORDER BY R.Appointment_id";
                username = UserContext.getCaregiver().getUsername();
            }
            try (PreparedStatement statement = con.prepareStatement(query)) {
                statement.setString(1, username);
                try (ResultSet result = statement.executeQuery()) {
                    boolean hasAppointments = false;
                    while (result.next()) {
                        hasAppointments = true;
                        res.add(result.getInt("Appointment_id") + " " + result.getString("Vaccine_name") + " " + result.getDate("Time") + " " + result.getString("Name"));
                    }
                    if (!hasAppointments) {
                        res.add("No appointments scheduled");
                    }
                }
            }
        } catch (SQLException e) {
            throw new RuntimeException("Operation failed, please try again");
        } finally {
            cm.closeConnection();
        }
        return res;
    }
}
