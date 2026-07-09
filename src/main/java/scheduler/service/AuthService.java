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

    public String logout() {
        if (UserContext.getPatient() == null && UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login first");
        }

        UserContext.clear();
        return "Successfully logged out";
    }
}
