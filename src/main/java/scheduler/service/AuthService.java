package scheduler.service;

import org.springframework.stereotype.Service;
import scheduler.context.UserContext;
import scheduler.model.*;
import scheduler.db.*;
import scheduler.util.*;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;

@Service
public class AuthService {

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

        byte[] salt = Util.generateSalt();
        byte[] hash = Util.generateHash(password, salt);

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();
        try {
            String selectUsername = "SELECT Username FROM Patients WHERE Username = ?";
            PreparedStatement checkStmt = con.prepareStatement(selectUsername);
            checkStmt.setString(1, username);
            ResultSet rs = checkStmt.executeQuery();
            if (rs.next()) {
                throw new RuntimeException("Username taken, try again");
            }
            rs.close();
            checkStmt.close();

            String addPatient = "INSERT INTO Patients VALUES (?, ?, ?)";
            PreparedStatement insertStmt = con.prepareStatement(addPatient);
            insertStmt.setString(1, username);
            insertStmt.setBytes(2, salt);
            insertStmt.setBytes(3, hash);
            insertStmt.executeUpdate();
            insertStmt.close();
            
            return "Created user " + username;
        } catch (SQLException e) {
            throw new RuntimeException("Create patient failed");
        } finally {
            cm.closeConnection();
        }
    }

    public String createCaregiver(String username, String password) {
        if (!checkPassword(password)) {
            throw new RuntimeException("Create caregiver failed, please use a strong password");
        }
        
        byte[] salt = Util.generateSalt();
        byte[] hash = Util.generateHash(password, salt);
        
        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();
        try {
            String selectUsername = "SELECT Username FROM Caregivers WHERE Username = ?";
            PreparedStatement checkStmt = con.prepareStatement(selectUsername);
            checkStmt.setString(1, username);
            ResultSet rs = checkStmt.executeQuery();
            if (rs.next()) {
                throw new RuntimeException("Username taken, try again!");
            }
            rs.close();
            checkStmt.close();

            String addCaregiver = "INSERT INTO Caregivers VALUES (?, ?, ?)";
            PreparedStatement insertStmt = con.prepareStatement(addCaregiver);
            insertStmt.setString(1, username);
            insertStmt.setBytes(2, salt);
            insertStmt.setBytes(3, hash);
            insertStmt.executeUpdate();
            insertStmt.close();

            return "Created user " + username;
        } catch (SQLException e) {
            throw new RuntimeException("Failed to create user.");
        } finally {
            cm.closeConnection();
        }
    }

    public String loginPatient(String username, String password) {
        if (UserContext.getPatient() != null || UserContext.getCaregiver() != null) {
            throw new RuntimeException("User already logged in, try again");
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();
        try {
            String getPatient = "SELECT Salt, Hash FROM Patients WHERE Username = ?";
            PreparedStatement statement = con.prepareStatement(getPatient);
            statement.setString(1, username);
            ResultSet resultSet = statement.executeQuery();
            
            if (resultSet.next()) {
                byte[] salt = resultSet.getBytes("Salt");
                byte[] hash = Util.trim(resultSet.getBytes("Hash"));
                byte[] calculatedHash = Util.generateHash(password, salt);
                
                if (!Arrays.equals(hash, calculatedHash)) {
                    throw new RuntimeException("Login patient failed");
                } else {
                    Patient patient = new Patient.PatientBuilder(username, salt, hash).build();
                    UserContext.setPatient(patient);
                    return JwtUtil.generateToken(username, "Patient");
                }
            } else {
                throw new RuntimeException("Login patient failed");
            }
        } catch (SQLException e) {
            throw new RuntimeException("Login patient failed");
        } finally {
            cm.closeConnection();
        }
    }

    public String loginCaregiver(String username, String password) {
        if (UserContext.getCaregiver() != null || UserContext.getPatient() != null) {
            throw new RuntimeException("User already logged in.");
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();
        try {
            String getCaregiver = "SELECT Salt, Hash FROM Caregivers WHERE Username = ?";
            PreparedStatement statement = con.prepareStatement(getCaregiver);
            statement.setString(1, username);
            ResultSet resultSet = statement.executeQuery();
            
            if (resultSet.next()) {
                byte[] salt = resultSet.getBytes("Salt");
                byte[] hash = Util.trim(resultSet.getBytes("Hash"));
                byte[] calculatedHash = Util.generateHash(password, salt);
                
                if (!Arrays.equals(hash, calculatedHash)) {
                    throw new RuntimeException("Login failed.");
                } else {
                    Caregiver caregiver = new Caregiver.CaregiverBuilder(username, salt, hash).build();
                    UserContext.setCaregiver(caregiver);
                    return JwtUtil.generateToken(username, "Caregiver");
                }
            } else {
                throw new RuntimeException("Login failed.");
            }
        } catch (SQLException e) {
            throw new RuntimeException("Login failed.");
        } finally {
            cm.closeConnection();
        }
    }

    public String logout() {
        if (UserContext.getPatient() == null && UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login first");
        }

        UserContext.clear();
        return "Successfully logged out";
    }
}
