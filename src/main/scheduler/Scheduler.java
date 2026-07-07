package scheduler;

import scheduler.db.ConnectionManager;
import scheduler.model.Caregiver;
import scheduler.model.Patient;
import scheduler.model.Vaccine;
import scheduler.model.Vaccine.VaccineGetter;
import scheduler.util.Util;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Date;

public class Scheduler {

    // objects to keep track of the currently logged-in user
    // Note: it is always true that at most one of currentCaregiver and currentPatient is not null
    //       since only one user can be logged-in at a time
    private static final ThreadLocal<Caregiver> currentCaregiver = new ThreadLocal<>();
    private static final ThreadLocal<Patient> currentPatient = new ThreadLocal<>();

    public static void main(String[] args) {
        // printing greetings text
        System.out.println();
        System.out.println("Welcome to the COVID-19 Vaccine Reservation Scheduling Application!");
        System.out.println("*** Please enter one of the following commands ***");
        System.out.println("> create_patient <username> <password>");  //TODO: implement create_patient (Part 1)
        System.out.println("> create_caregiver <username> <password>");
        System.out.println("> login_patient <username> <password>");  // TODO: implement login_patient (Part 1)
        System.out.println("> login_caregiver <username> <password>");
        System.out.println("> search_caregiver_schedule <date>");  // TODO: implement search_caregiver_schedule (Part 2)
        System.out.println("> reserve <date> <vaccine>");  // TODO: implement reserve (Part 2)
        System.out.println("> upload_availability <date>");
        System.out.println("> cancel <appointment_id>");  // TODO: implement cancel (extra credit)
        System.out.println("> add_doses <vaccine> <number>");
        System.out.println("> show_appointments");  // TODO: implement show_appointments (Part 2)
        System.out.println("> logout");  // TODO: implement logout (Part 2)
        System.out.println("> quit");
        System.out.println();

        // read input from user
        BufferedReader r = new BufferedReader(new InputStreamReader(System.in));
        while (true) {
            System.out.print("> ");
            String response = "";
            try {
                response = r.readLine();
            } catch (IOException e) {
                System.out.println("Please try again!");
            }
            // split the user input by spaces
            String[] tokens = response.split(" ");
            // check if input exists
            if (tokens.length == 0) {
                System.out.println("Please try again!");
                continue;
            }
            // determine which operation to perform
            String operation = tokens[0];
            if (operation.equals("create_patient")) {
                createPatient(tokens);
            } else if (operation.equals("create_caregiver")) {
                createCaregiver(tokens);
            } else if (operation.equals("login_patient")) {
                loginPatient(tokens);
            } else if (operation.equals("login_caregiver")) {
                loginCaregiver(tokens);
            } else if (operation.equals("search_caregiver_schedule")) {
                searchCaregiverSchedule(tokens);
            } else if (operation.equals("reserve")) {
                reserve(tokens);
            } else if (operation.equals("upload_availability")) {
                uploadAvailability(tokens);
            } else if (operation.equals("cancel")) {
                cancel(tokens);
            } else if (operation.equals("add_doses")) {
                addDoses(tokens);
            } else if (operation.equals("show_appointments")) {
                showAppointments(tokens);
            } else if (operation.equals("logout")) {
                logout(tokens);
            } else if (operation.equals("quit")) {
                System.out.println("Bye!");
                return;
            } else {
                System.out.println("Invalid operation name!");
            }
        }
    }

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
        if (!hasUpper || !hasLower || !hasNumber || !hasSpecial) {
            return false;
        }
        return true;
    }

    private static void createPatient(String[] tokens) {
        if (tokens.length != 3) {
            System.out.println("Create patient failed");
            return;
        }
        
        String username = tokens[1];
        String password = tokens[2];

        if (!checkPassword(password)) {
            System.out.println("Create patient failed, please use a strong password " +
            "(8+ char, at least one upper and one lower, at least one letter and one number, " +
            "and at least one special character, from \"!\", \"@\", \"#\", \"?\")");
            return;
        }

        try {
            if (usernameExistsPatient(username)) {
                System.out.println("Username taken, try again");
                return;
            }
        } catch (SQLException e) {
            System.out.println("Create patient failed");
            return;
        }

        byte[] salt = Util.generateSalt();
        byte[] hash = Util.generateHash(password, salt);

        try {
            Patient patient = new Patient.PatientBuilder(username, salt, hash).build();
            patient.saveToDB();
            System.out.println("Created user " + username);
        } catch (SQLException e) {
            System.out.println("Create patient failed");
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
            // returns false if the cursor is not before the first record or if there are no rows in the ResultSet.
            return resultSet.isBeforeFirst();
        } catch (SQLException e) {
            throw new SQLException();
        } finally {
            cm.closeConnection();
        }
    }

    private static void createCaregiver(String[] tokens) {
        // create_caregiver <username> <password>
        // check 1: the length for tokens need to be exactly 3 to include all information (with the operation name)
        if (tokens.length != 3) {
            System.out.println("Failed to create user.");
            return;
        }
        String username = tokens[1];
        String password = tokens[2];
        if (!checkPassword(password)) {
            System.out.println("Create caregiver failed, please use a strong password " +
            "(8+ char, at least one upper and one lower, at least one letter and one number, " +
            "and at least one special character, from \"!\", \"@\", \"#\", \"?\")");
            return;
        }
        // check 2: check if the username has been taken already
        if (usernameExistsCaregiver(username)) {
            System.out.println("Username taken, try again!");
            return;
        }
        byte[] salt = Util.generateSalt();
        byte[] hash = Util.generateHash(password, salt);
        // create the caregiver
        try {
            Caregiver caregiver = new Caregiver.CaregiverBuilder(username, salt, hash).build(); 
            // save to caregiver information to our database
            caregiver.saveToDB();
            System.out.println("Created user " + username);
        } catch (SQLException e) {
            System.out.println("Failed to create user.");
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
            // returns false if the cursor is not before the first record or if there are no rows in the ResultSet.
            return resultSet.isBeforeFirst();
        } catch (SQLException e) {
            System.out.println("Error occurred when checking username");
        } finally {
            cm.closeConnection();
        }
        return true;
    }

    private static void loginPatient(String[] tokens) {
        if (currentPatient.get() != null || currentCaregiver.get() != null) {
            System.out.println("User already logged in, try again");
            return;
        }
        
        if (tokens.length != 3) {
            System.out.println("Login patient failed");
            return;
        }
        
        String username = tokens[1];
        String password = tokens[2];

        try {
            if (!usernameExistsPatient(username)) {
                System.out.println("Login patient failed");
                return;
            }
        } catch (SQLException e) {
            System.out.println("Login patient failed");
            return;
        }

        Patient patient = null;
        try {
            patient = new Patient.PatientGetter(username, password).get();
        } catch (SQLException e) {
            System.out.println("Login patient failed");
            return;
        }

        if (patient == null) {
            System.out.println("Login patient failed");
        } else {
            System.out.println("Logged in as " + username);
            currentPatient.set(patient);
        }
    }

    private static void loginCaregiver(String[] tokens) {
        // login_caregiver <username> <password>
        // check 1: if someone's already logged-in, they need to log out first
        if (currentCaregiver.get() != null || currentPatient.get() != null) {
            System.out.println("User already logged in.");
            return;
        }
        // check 2: the length for tokens need to be exactly 3 to include all information (with the operation name)
        if (tokens.length != 3) {
            System.out.println("Login failed.");
            return;
        }
        String username = tokens[1];
        String password = tokens[2];

        Caregiver caregiver = null;
        try {
            caregiver = new Caregiver.CaregiverGetter(username, password).get();
        } catch (SQLException e) {
            System.out.println("Login failed.");
        }
        // check if the login was successful
        if (caregiver == null) {
            System.out.println("Login failed.");
        } else {
            System.out.println("Logged in as: " + username);
            currentCaregiver.set(caregiver);
        }
    }

    private static void searchCaregiverSchedule(String[] tokens) {
        if (currentPatient.get() == null && currentCaregiver.get() == null) {
            System.out.println("Please login first");
            return;
        }
        
        if (tokens.length != 2) {
            System.out.println("Please try again");
            return;
        }
        
        String date = tokens[1];

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        try{
            String getSchedule = "SELECT A.Username FROM Availabilities as A WHERE Time = ? ORDER BY A.Username";
            PreparedStatement sheduleStatement = con.prepareStatement(getSchedule);
            Date d = Date.valueOf(date);
            sheduleStatement.setDate(1, d);
            ResultSet scheduleResult = sheduleStatement.executeQuery();
            System.out.println("Caregivers:");
            boolean hasCaregivers = false;
            while (scheduleResult.next()) {
                hasCaregivers = true;
                System.out.println(scheduleResult.getString("Username"));
            }
            if (!hasCaregivers) {
                System.out.println("No caregivers available");
            }
            String getVaccine = "SELECT V.Name, V.Doses FROM Vaccines as V WHERE V.Doses > 0";
            PreparedStatement vaccineStatement = con.prepareStatement(getVaccine);
            ResultSet vaccineResult = vaccineStatement.executeQuery();
            System.out.println("Vaccines:");
            boolean hasVaccines = false;
            while (vaccineResult.next()) {
                hasVaccines = true;
                System.out.println(vaccineResult.getString("Name") + " " + vaccineResult.getInt("Doses"));
            }
            if (!hasVaccines) {
                System.out.println("No vaccines available");
            }
        } catch (IllegalArgumentException e) {
            System.out.println("Please try again");
        } catch (SQLException e) {
            System.out.println("Please try again");
        } finally {
            cm.closeConnection();
        }
    }

    private static void reserve(String[] tokens) {
        if (currentCaregiver.get() != null) {
            System.out.println("Please login as a patient");
            return;
        }
        if (currentPatient.get() == null) {
            System.out.println("Please login first");
            return;
        }
        
        if (tokens.length != 3) {
            System.out.println("Please try again");
            return;
        }

        String date = tokens[1];
        String vaccineName = tokens[2];

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        try {
            String getCaregiver = "SELECT A.Username FROM Availabilities as A WHERE Time = ? ORDER BY A.Username";
            PreparedStatement caregiverStatement = con.prepareStatement(getCaregiver);
            Date d = Date.valueOf(date);
            caregiverStatement.setDate(1, d);
            ResultSet caregiverResult = caregiverStatement.executeQuery();
            if (caregiverResult.next()) {
                VaccineGetter getVaccine = new VaccineGetter(vaccineName);
                Vaccine currentVaccine = getVaccine.get();
                if (currentVaccine == null || currentVaccine.getAvailableDoses() == 0) {
                    System.out.println("Not enough available doses");
                    return;
                }
                String assignedCaregiver = caregiverResult.getString("Username");
                caregiverResult.close();
                caregiverStatement.close();

                con.setAutoCommit(false);
                try {
                    String addReservations = "INSERT INTO Reservations (Patient_name, Caregiver_name, Vaccine_name, Time) VALUES (?, ?, ?, ?)";
                    PreparedStatement addStatement = con.prepareStatement(addReservations, java.sql.Statement.RETURN_GENERATED_KEYS);
                    addStatement.setString(1, currentPatient.get().getUsername());
                    addStatement.setString(2, assignedCaregiver);
                    addStatement.setString(3, vaccineName);
                    addStatement.setDate(4, d);
                    addStatement.executeUpdate();

                    ResultSet generatedKeys = addStatement.getGeneratedKeys();
                    int currentId = 0;
                    if (generatedKeys.next()) {
                        currentId = generatedKeys.getInt(1);
                    }
                    System.out.println("Appointment ID "+ currentId + ", Caregiver username " + assignedCaregiver);

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
                } catch (SQLException e) {
                    con.rollback();
                    throw e;
                } finally {
                    con.setAutoCommit(true);
                }
            } else {
                System.out.println("No caregiver is available");
            }
        } catch (IllegalArgumentException e) {
            System.out.println("Please try again");
        } catch (SQLException e) {
            System.out.println("Please try again");
        } finally {
            cm.closeConnection();
        }
    }

    private static void uploadAvailability(String[] tokens) {
        // upload_availability <date>
        // check 1: check if the current logged-in user is a caregiver
        if (currentCaregiver.get() == null) {
            System.out.println("Please login as a caregiver first!");
            return;
        }
        // check 2: the length for tokens need to be exactly 2 to include all information (with the operation name)
        if (tokens.length != 2) {
            System.out.println("Please try again!");
            return;
        }
        String date = tokens[1];
        try {
            Date d = Date.valueOf(date);
            currentCaregiver.get().uploadAvailability(d);
            System.out.println("Availability uploaded!");
        } catch (IllegalArgumentException e) {
            System.out.println("Please enter a valid date!");
        } catch (SQLException e) {
            System.out.println("Error occurred when uploading availability");
        }
    }

    private static void cancel(String[] tokens) {
        if (currentPatient.get() == null && currentCaregiver.get() == null) {
            System.out.println("Please login first");
            return;
        }
        
        if (tokens.length != 2) {
            System.out.println("Please try again");
            return;
        }

        String appointmentId = tokens[1];

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
                
                if (currentPatient.get() != null && !currentPatient.get().getUsername().equals(patientName)) {
                    System.out.println("Please try again");
                    return;
                }
                if (currentCaregiver.get() != null && !currentCaregiver.get().getUsername().equals(caregiverName)) {
                    System.out.println("Please try again");
                    return;
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
                    System.out.println("Appointment ID " + appointmentId + " has been successfully canceled");
                } catch (SQLException e) {
                    con.rollback();
                    throw e;
                } finally {
                    con.setAutoCommit(true);
                }
            } else {
                System.out.println("Appointment ID " + appointmentId + " does not exist");
            }
        } catch (SQLException e) {
            System.out.println("Please try again");
        }
    }

    private static void addDoses(String[] tokens) {
        // add_doses <vaccine> <number>
        // check 1: check if the current logged-in user is a caregiver
        if (currentCaregiver.get() == null) {
            System.out.println("Please login as a caregiver first!");
            return;
        }
        // check 2: the length for tokens need to be exactly 3 to include all information (with the operation name)
        if (tokens.length != 3) {
            System.out.println("Please try again!");
            return;
        }
        String vaccineName = tokens[1];
        int doses = Integer.parseInt(tokens[2]);
        Vaccine vaccine = null;
        try {
            vaccine = new Vaccine.VaccineGetter(vaccineName).get();
        } catch (SQLException e) {
            System.out.println("Error occurred when adding doses");
        }
        // check 3: if getter returns null, it means that we need to create the vaccine and insert it into the Vaccines
        //          table
        if (vaccine == null) {
            try {
                vaccine = new Vaccine.VaccineBuilder(vaccineName, doses).build();
                vaccine.saveToDB();
            } catch (SQLException e) {
                System.out.println("Error occurred when adding doses");
                return;
            }
        } else {
            // if the vaccine is not null, meaning that the vaccine already exists in our table
            try {
                vaccine.increaseAvailableDoses(doses);
            } catch (SQLException e) {
                System.out.println("Error occurred when adding doses");
                return;
            }
        }

        // Sync to Redis Cache
        try (var jedis = scheduler.db.RedisManager.getJedis()) {
            String redisKey = "vaccine:" + vaccineName + ":doses";
            jedis.incrBy(redisKey, doses);
        } catch (Exception e) {
            System.out.println("Warning: Failed to sync doses to Redis cache.");
        }

        System.out.println("Doses updated!");
    }

    private static void showAppointments(String[] tokens) {
        if (currentPatient.get() == null && currentCaregiver.get() == null) {
            System.out.println("Please login first");
            return;
        }
        
        if (tokens.length != 1) {
            System.out.println("Please try again");
            return;
        }

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        try {
            PreparedStatement statement;
            if (currentPatient.get() != null) {
                String getAppointments = "SELECT R.Appointment_id, R.Vaccine_name, R.Time, R.Caregiver_name as Name FROM Reservations as R WHERE R.Patient_name = ? ORDER BY R.Appointment_id";
                statement = con.prepareStatement(getAppointments);
                statement.setString(1, currentPatient.get().getUsername());
            } else {
                String getAppointments = "SELECT R.Appointment_id, R.Vaccine_name, R.Time, R.Patient_name as Name FROM Reservations as R WHERE R.Caregiver_name = ? ORDER BY R.Appointment_id";
                statement = con.prepareStatement(getAppointments);
                statement.setString(1, currentCaregiver.get().getUsername());    
            }
            ResultSet result = statement.executeQuery();
            boolean hasAppointments = false;
            while (result.next()) {
                hasAppointments = true;
                System.out.println(result.getInt("Appointment_id") + " " + result.getString("Vaccine_name") + " " + result.getDate("Time") + " " + result.getString("Name"));
            }
            if (!hasAppointments) {
                System.out.println("No appointments scheduled");
            }
        } catch (SQLException e) {
            System.out.println("Please try again");
        } finally {
            cm.closeConnection();
        }
    }

    private static void logout(String[] tokens) {
        if (currentPatient.get() == null && currentCaregiver.get() == null) {
            System.out.println("Please login first");
            return;
        }
        
        if (tokens.length != 1) {
            System.out.println("Please try again");
            return;
        }

        currentPatient.remove();
        currentCaregiver.remove();
        System.out.println("Successfully logged out");
    }
}