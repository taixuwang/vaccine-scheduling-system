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
            String getSchedule = "SELECT A.Username FROM Availabilities as A WHERE Time = ? ORDER BY A.Username";
            PreparedStatement sheduleStatement = con.prepareStatement(getSchedule);
            Date d = Date.valueOf(date);
            sheduleStatement.setDate(1, d);
            ResultSet scheduleResult = sheduleStatement.executeQuery();
            res.add("Caregivers:");
            boolean hasCaregivers = false;
            while (scheduleResult.next()) {
                hasCaregivers = true;
                res.add(scheduleResult.getString("Username"));
            }
            if (!hasCaregivers) {
                res.add("No caregivers available");
            }
            String getVaccine = "SELECT V.Name, COUNT(D.Dose_id) as Doses FROM Vaccines as V JOIN VaccineDoses as D ON V.Name = D.Vaccine_name WHERE D.Status = 'available' GROUP BY V.Name";
            PreparedStatement vaccineStatement = con.prepareStatement(getVaccine);
            ResultSet vaccineResult = vaccineStatement.executeQuery();
            res.add("Vaccines:");
            boolean hasVaccines = false;
            while (vaccineResult.next()) {
                hasVaccines = true;
                res.add(vaccineResult.getString("Name") + " " + vaccineResult.getInt("Doses"));
            }
            if (!hasVaccines) {
                res.add("No vaccines available");
            }
        } catch (IllegalArgumentException e) {
            throw new RuntimeException("Please try again");
        } catch (SQLException e) {
            throw new RuntimeException("Please try again");
        } finally {
            cm.closeConnection();
        }
        
        return res;
    }

    public String reserve(String date, String vaccineName) {
        if (UserContext.getCaregiver() != null) {
            throw new RuntimeException("Please login as a patient");
        }
        if (UserContext.getPatient() == null) {
            throw new RuntimeException("Please login first");
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
            // Redis is down: fall back to a DB stock check. This is only an early
            // bail-out; the SKIP LOCKED claim later in the transaction is
            // the real guard against oversell.
            ConnectionManager fallbackCm = new ConnectionManager();
            Connection fallbackCon = fallbackCm.createConnection();
            try {
                String checkDoses = "SELECT COUNT(*) as cnt FROM VaccineDoses WHERE Vaccine_name = ? AND Status = 'available'";
                PreparedStatement ps = fallbackCon.prepareStatement(checkDoses);
                ps.setString(1, vaccineName);
                ResultSet rs = ps.executeQuery();
                if (!rs.next() || rs.getInt("cnt") <= 0) {
                    rs.close();
                    ps.close();
                    throw new RuntimeException("Not enough available doses");
                }
                rs.close();
                ps.close();
                currentStock = 1; // pass the guard below; the real claim happens via SKIP LOCKED
            } catch (SQLException sqlEx) {
                throw new RuntimeException("Please try again");
            } finally {
                fallbackCm.closeConnection();
            }
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

                // 1. Claim a vaccine dose (SKIP LOCKED - no contention with other transactions)
                String getDose = "SELECT Dose_id FROM VaccineDoses WHERE Vaccine_name = ? AND Status = 'available' LIMIT 1 FOR UPDATE SKIP LOCKED";
                PreparedStatement doseStatement = con.prepareStatement(getDose);
                doseStatement.setString(1, vaccineName);
                ResultSet doseResult = doseStatement.executeQuery();
                if (!doseResult.next()) {
                    doseResult.close();
                    doseStatement.close();
                    con.rollback();
                    throw new RuntimeException("Not enough available doses");
                }
                int doseId = doseResult.getInt("Dose_id");
                doseResult.close();
                doseStatement.close();

                // 2. Select caregiver (SKIP LOCKED - same as before)
                String getCaregiver = "SELECT A.Username FROM Availabilities as A WHERE Time = ? ORDER BY A.Username LIMIT 1 FOR UPDATE SKIP LOCKED";
                PreparedStatement caregiverStatement = con.prepareStatement(getCaregiver);
                caregiverStatement.setDate(1, d);
                ResultSet caregiverResult = caregiverStatement.executeQuery();
                if (caregiverResult.next()) {
                    String assignedCaregiver = caregiverResult.getString("Username");
                    caregiverResult.close();
                    caregiverStatement.close();

                    try {
                        String addReservations = "INSERT INTO Reservations (Patient_name, Caregiver_name, Vaccine_name, Dose_id, Time) VALUES (?, ?, ?, ?, ?)";
                        PreparedStatement addStatement = con.prepareStatement(addReservations, java.sql.Statement.RETURN_GENERATED_KEYS);
                        addStatement.setString(1, UserContext.getPatient().getUsername());
                        addStatement.setString(2, assignedCaregiver);
                        addStatement.setString(3, vaccineName);
                        addStatement.setInt(4, doseId);
                        addStatement.setDate(5, d);
                        addStatement.executeUpdate();

                        ResultSet generatedKeys = addStatement.getGeneratedKeys();
                        int currentId = 0;
                        if (generatedKeys.next()) {
                            currentId = generatedKeys.getInt(1);
                        }
                        String resMsg = "Appointment ID "+ currentId + ", Caregiver username " + assignedCaregiver;

                        String removeAvailability = "DELETE FROM Availabilities as A WHERE A.Time = ? AND A.Username = ?";
                        PreparedStatement removeStatement = con.prepareStatement(removeAvailability);
                        removeStatement.setDate(1, d);
                        removeStatement.setString(2, assignedCaregiver);
                        removeStatement.executeUpdate();

                        // Mark dose as reserved (replaces UPDATE vaccines SET Doses = Doses - 1)
                        String claimDose = "UPDATE VaccineDoses SET Status = 'reserved' WHERE Dose_id = ?";
                        PreparedStatement claimStmt = con.prepareStatement(claimDose);
                        claimStmt.setInt(1, doseId);
                        claimStmt.executeUpdate();

                        con.commit();
                        reserveSuccess = true; // Mark as success!
                        return resMsg;
                    } catch (SQLException e) {
                        con.rollback();
                        throw e;
                    }
                } else {
                    con.rollback();
                    throw new RuntimeException("No caregiver is available");
                }
            } catch (IllegalArgumentException e) {
                throw new RuntimeException("Please try again");
            } catch (SQLException e) {
                try { con.rollback(); } catch (SQLException ex) {}
                throw new RuntimeException("Please try again");
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
            PreparedStatement statement = con.prepareStatement(getAppointment);
            statement.setInt(1, appId);
            ResultSet result = statement.executeQuery();
            if (result.next()) {
                String patientName = result.getString("Patient_name");
                String caregiverName = result.getString("Caregiver_name");
                String vaccineName = result.getString("Vaccine_name");
                int doseId = result.getInt("Dose_id");
                Date time = result.getDate("Time");
                
                result.close();
                statement.close();
                
                if (UserContext.getPatient() != null && !UserContext.getPatient().getUsername().equals(patientName)) {
                    throw new RuntimeException("Please try again");
                }
                if (UserContext.getCaregiver() != null && !UserContext.getCaregiver().getUsername().equals(caregiverName)) {
                    throw new RuntimeException("Please try again");
                }

                try {
                    String deleteReservation = "DELETE FROM Reservations as R WHERE R.Appointment_id = ?";
                    PreparedStatement deleteStatement = con.prepareStatement(deleteReservation);
                    deleteStatement.setInt(1, appId);
                    deleteStatement.executeUpdate();
                    
                    // Restore the specific dose to available (replaces UPDATE vaccines SET Doses = Doses + 1)
                    String restoreDose = "UPDATE VaccineDoses SET Status = 'available' WHERE Dose_id = ?";
                    PreparedStatement restoreStmt = con.prepareStatement(restoreDose);
                    restoreStmt.setInt(1, doseId);
                    restoreStmt.executeUpdate();
                    
                    String addAvailability = "INSERT INTO Availabilities VALUES (?, ?)";
                    PreparedStatement addStatement = con.prepareStatement(addAvailability);
                    addStatement.setDate(1, time);
                    addStatement.setString(2, caregiverName);
                    addStatement.executeUpdate();

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
            } else {
                throw new RuntimeException("Appointment ID " + appointmentId + " does not exist");
            }
        } catch (SQLException e) {
            throw new RuntimeException("Please try again");
        } finally {
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
            PreparedStatement statement;
            if (UserContext.getPatient() != null) {
                String getAppointments = "SELECT R.Appointment_id, R.Vaccine_name, R.Time, R.Caregiver_name as Name FROM Reservations as R WHERE R.Patient_name = ? ORDER BY R.Appointment_id";
                statement = con.prepareStatement(getAppointments);
                statement.setString(1, UserContext.getPatient().getUsername());
            } else {
                String getAppointments = "SELECT R.Appointment_id, R.Vaccine_name, R.Time, R.Patient_name as Name FROM Reservations as R WHERE R.Caregiver_name = ? ORDER BY R.Appointment_id";
                statement = con.prepareStatement(getAppointments);
                statement.setString(1, UserContext.getCaregiver().getUsername());    
            }
            ResultSet result = statement.executeQuery();
            boolean hasAppointments = false;
            while (result.next()) {
                hasAppointments = true;
                res.add(result.getInt("Appointment_id") + " " + result.getString("Vaccine_name") + " " + result.getDate("Time") + " " + result.getString("Name"));
            }
            if (!hasAppointments) {
                res.add("No appointments scheduled");
            }
        } catch (SQLException e) {
            throw new RuntimeException("Please try again");
        } finally {
            cm.closeConnection();
        }
        return res;
    }
}
