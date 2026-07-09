package scheduler.service;

import org.springframework.stereotype.Service;
import scheduler.context.UserContext;
import java.util.ArrayList;
import java.util.List;
import scheduler.model.*;
import scheduler.db.*;
import scheduler.util.*;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Date;
import scheduler.model.Vaccine.VaccineGetter;

@Service
public class SchedulerService {

    private static boolean checkPassword(String password) {
        if (password.length() < 8) {
            return false;
        }
        boolean hasUpper = false;
        boolean hasLower = false;
        boolean hasNumber = false;
        String special = "!@#?";
        boolean hasSpecial = false;
        for (char c : password.toCharArray()) {
            if (Character.isUpperCase(c)) {
                hasUpper = true;
            }
            if (Character.isLowerCase(c)) {
                hasLower = true;
            }
            if (Character.isDigit(c)) {
                hasNumber = true;
            }
            if (special.indexOf(c) != -1) {
                hasSpecial = true;
            } 
        }
        return hasUpper && hasLower && hasNumber && hasSpecial;
    }

    public String createPatient(String username, String password) {
        if (!checkPassword(password)) {
            throw new RuntimeException("Create patient failed, please use a strong password");
        }

        try {
            if (usernameExistsPatient(username)) {
                throw new RuntimeException("Username taken, try again");
            }
        } catch (SQLException e) {
            throw new RuntimeException("Create patient failed");
        }

        byte[] salt = Util.generateSalt();
        byte[] hash = Util.generateHash(password, salt);

        try {
            Patient patient = new Patient.PatientBuilder(username, salt, hash).build();
            patient.saveToDB();
            return "Created user " + username;
        } catch (SQLException e) {
            throw new RuntimeException("Create patient failed");
        }
    }

    private static boolean usernameExistsPatient(String username) throws SQLException {
        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        String selectUsername = "SELECT * FROM Patients WHERE Username = ?";
        try {
            PreparedStatement statement = con.prepareStatement(selectUsername);
            statement.setString(1, username);
            ResultSet resultSet = statement.executeQuery();
            return resultSet.isBeforeFirst();
        } catch (SQLException e) {
            throw new SQLException();
        } finally {
            cm.closeConnection();
        }
    }

    public String createCaregiver(String username, String password) {
        if (!checkPassword(password)) {
            throw new RuntimeException("Create caregiver failed, please use a strong password");
        }
        if (usernameExistsCaregiver(username)) {
            throw new RuntimeException("Username taken, try again!");
        }
        
        byte[] salt = Util.generateSalt();
        byte[] hash = Util.generateHash(password, salt);
        
        try {
            Caregiver caregiver = new Caregiver.CaregiverBuilder(username, salt, hash).build(); 
            caregiver.saveToDB();
            return "Created user " + username;
        } catch (SQLException e) {
            throw new RuntimeException("Failed to create user.");
        }
    }

    private static boolean usernameExistsCaregiver(String username) {
        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        String selectUsername = "SELECT * FROM Caregivers WHERE Username = ?";
        try {
            PreparedStatement statement = con.prepareStatement(selectUsername);
            statement.setString(1, username);
            ResultSet resultSet = statement.executeQuery();
            return resultSet.isBeforeFirst();
        } catch (SQLException e) {
            throw new RuntimeException("Error occurred when checking username");
        } finally {
            cm.closeConnection();
        }
    }

    public String loginPatient(String username, String password) {
        if (UserContext.getPatient() != null || UserContext.getCaregiver() != null) {
            throw new RuntimeException("User already logged in, try again");
        }

        try {
            if (!usernameExistsPatient(username)) {
                throw new RuntimeException("Login patient failed");
            }
        } catch (SQLException e) {
            throw new RuntimeException("Login patient failed");
        }

        Patient patient = null;
        try {
            patient = new Patient.PatientGetter(username, password).get();
        } catch (SQLException e) {
            throw new RuntimeException("Login patient failed");
        }

        if (patient == null) {
            throw new RuntimeException("Login patient failed");
        } else {
            UserContext.setPatient(patient);
            return JwtUtil.generateToken(username, "Patient");
        }
    }

    public String loginCaregiver(String username, String password) {
        if (UserContext.getCaregiver() != null || UserContext.getPatient() != null) {
            throw new RuntimeException("User already logged in.");
        }

        Caregiver caregiver = null;
        try {
            caregiver = new Caregiver.CaregiverGetter(username, password).get();
        } catch (SQLException e) {
            throw new RuntimeException("Login failed.");
        }
        
        if (caregiver == null) {
            throw new RuntimeException("Login failed.");
        } else {
            UserContext.setCaregiver(caregiver);
            return JwtUtil.generateToken(username, "Caregiver");
        }
    }

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
            String getVaccine = "SELECT V.Name, V.Doses FROM Vaccines as V WHERE V.Doses > 0";
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

        // 1. Redis Cache Interception
        String redisKey = "vaccine:" + vaccineName + ":doses";
        long currentStock = -1;
        try (redis.clients.jedis.Jedis jedis = scheduler.db.RedisManager.getJedis()) {
            currentStock = jedis.decr(redisKey);
        } catch (Exception e) {
            currentStock = 1; // Fallback to DB if Redis is down
        }

        if (currentStock < 0) {
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
                String getCaregiver = "SELECT A.Username FROM Availabilities as A WHERE Time = ? ORDER BY A.Username FOR UPDATE";
                PreparedStatement caregiverStatement = con.prepareStatement(getCaregiver);
                Date d = Date.valueOf(date);
                caregiverStatement.setDate(1, d);
                ResultSet caregiverResult = caregiverStatement.executeQuery();
                if (caregiverResult.next()) {
                    VaccineGetter getVaccine = new VaccineGetter(vaccineName);
                    Vaccine currentVaccine = getVaccine.get();
                    if (currentVaccine == null || currentVaccine.getAvailableDoses() == 0) {
                        con.rollback();
                        throw new RuntimeException("Not enough available doses"); // Revert will happen in finally
                    }
                    String assignedCaregiver = caregiverResult.getString("Username");
                    caregiverResult.close();
                    caregiverStatement.close();

                    try {
                        String addReservations = "INSERT INTO Reservations (Patient_name, Caregiver_name, Vaccine_name, Time) VALUES (?, ?, ?, ?)";
                        PreparedStatement addStatement = con.prepareStatement(addReservations, java.sql.Statement.RETURN_GENERATED_KEYS);
                        addStatement.setString(1, UserContext.getPatient().getUsername());
                        addStatement.setString(2, assignedCaregiver);
                        addStatement.setString(3, vaccineName);
                        addStatement.setDate(4, d);
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

                        String updateVaccine = "UPDATE vaccines SET Doses = Doses - 1 WHERE name = ?";
                        PreparedStatement updateVaccineStatement = con.prepareStatement(updateVaccine);
                        updateVaccineStatement.setString(1, vaccineName);
                        updateVaccineStatement.executeUpdate();

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
            if (!reserveSuccess) {
                // If anything failed, return the dose to Redis
                try (redis.clients.jedis.Jedis jedis = scheduler.db.RedisManager.getJedis()) {
                    jedis.incr(redisKey);
                } catch (Exception e) {}
            }
        }
    }

    public String uploadAvailability(String date) {
        if (UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login as a caregiver first!");
        }

        try {
            Date d = Date.valueOf(date);
            UserContext.getCaregiver().uploadAvailability(d);
            return "Availability uploaded!";
        } catch (IllegalArgumentException e) {
            throw new RuntimeException("Please enter a valid date!");
        } catch (SQLException e) {
            throw new RuntimeException("Error occurred when uploading availability");
        }
    }

    public String cancel(String appointmentId) {
        if (UserContext.getPatient() == null && UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login first");
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        try {
            String getAppointment = "SELECT R.Appointment_id, R.Patient_name, R.Caregiver_name, R.Vaccine_name, R.Time FROM Reservations as R WHERE R.Appointment_id = ?";
            PreparedStatement statement = con.prepareStatement(getAppointment);
            statement.setString(1, appointmentId);
            ResultSet result = statement.executeQuery();
            if (result.next()) {
                String patientName = result.getString("Patient_name");
                String caregiverName = result.getString("Caregiver_name");
                String vaccineName = result.getString("Vaccine_name");
                Date time = result.getDate("Time");
                
                result.close();
                statement.close();
                
                if (UserContext.getPatient() != null && !UserContext.getPatient().getUsername().equals(patientName)) {
                    throw new RuntimeException("Please try again");
                }
                if (UserContext.getCaregiver() != null && !UserContext.getCaregiver().getUsername().equals(caregiverName)) {
                    throw new RuntimeException("Please try again");
                }

                VaccineGetter getVaccine = new VaccineGetter(vaccineName);
                Vaccine vaccine = getVaccine.get();

                con.setAutoCommit(false);
                try {
                    String deleteReservation = "DELETE FROM Reservations as R WHERE R.Appointment_id = ?";
                    PreparedStatement deleteStatement = con.prepareStatement(deleteReservation);
                    deleteStatement.setString(1, appointmentId);
                    deleteStatement.executeUpdate();
                    
                    String updateVaccine = "UPDATE vaccines SET Doses = ? WHERE name = ?";
                    PreparedStatement updateVaccineStatement = con.prepareStatement(updateVaccine);
                    updateVaccineStatement.setInt(1, vaccine.getAvailableDoses() + 1);
                    updateVaccineStatement.setString(2, vaccineName);
                    updateVaccineStatement.executeUpdate();
                    
                    String addAvailability = "INSERT INTO Availabilities VALUES (?, ?)";
                    PreparedStatement addStatement = con.prepareStatement(addAvailability);
                    addStatement.setDate(1, time);
                    addStatement.setString(2, caregiverName);
                    addStatement.executeUpdate();

                    con.commit();
                    return "Appointment ID " + appointmentId + " has been successfully canceled";
                } catch (SQLException e) {
                    con.rollback();
                    throw e;
                } finally {
                    con.setAutoCommit(true);
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

    public String addDoses(String vaccineName, int doses) {
        if (UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login as a caregiver first!");
        }

        Vaccine vaccine = null;
        try {
            vaccine = new Vaccine.VaccineGetter(vaccineName).get();
        } catch (SQLException e) {
            throw new RuntimeException("Error occurred when adding doses");
        }
        
        if (vaccine == null) {
            try {
                vaccine = new Vaccine.VaccineBuilder(vaccineName, doses).build();
                vaccine.saveToDB();
            } catch (SQLException e) {
                throw new RuntimeException("Error occurred when adding doses");
            }
        } else {
            try {
                vaccine.increaseAvailableDoses(doses);
            } catch (SQLException e) {
                throw new RuntimeException("Error occurred when adding doses");
            }
        }

        try (redis.clients.jedis.Jedis jedis = scheduler.db.RedisManager.getJedis()) {
            String redisKey = "vaccine:" + vaccineName + ":doses";
            jedis.incrBy(redisKey, doses);
        } catch (Exception e) {}

        return "Doses updated!";
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

    public String logout() {
        if (UserContext.getPatient() == null && UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login first");
        }

        UserContext.clear();
        return "Successfully logged out";
    }
}