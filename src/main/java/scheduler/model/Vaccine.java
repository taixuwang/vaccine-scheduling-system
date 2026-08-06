package scheduler.model;

import scheduler.db.ConnectionManager;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class Vaccine {
    private final String vaccineName;
    private int availableDoses;

    private Vaccine(VaccineBuilder builder) {
        this.vaccineName = builder.vaccineName;
        this.availableDoses = builder.availableDoses;
    }

    private Vaccine(VaccineGetter getter) {
        this.vaccineName = getter.vaccineName;
        this.availableDoses = getter.availableDoses;
    }

    // Getters
    public String getVaccineName() {
        return vaccineName;
    }

    public int getAvailableDoses() {
        return availableDoses;
    }

    public void saveToDB() throws SQLException {
        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        try {
            // Insert vaccine name (if not exists)
            String addVaccine = "INSERT INTO Vaccines (Name) VALUES (?) ON CONFLICT DO NOTHING";
            PreparedStatement vaccineStmt = con.prepareStatement(addVaccine);
            vaccineStmt.setString(1, this.vaccineName);
            vaccineStmt.executeUpdate();
            vaccineStmt.close();

            // Insert individual dose rows
            String addDose = "INSERT INTO VaccineDoses (Vaccine_name, Status) VALUES (?, 'available')";
            PreparedStatement doseStmt = con.prepareStatement(addDose);
            for (int i = 0; i < this.availableDoses; i++) {
                doseStmt.setString(1, this.vaccineName);
                doseStmt.addBatch();
            }
            doseStmt.executeBatch();
            doseStmt.close();
        } catch (SQLException e) {
            throw new SQLException();
        } finally {
            cm.closeConnection();
        }
    }

    // Increment the available doses by inserting new dose rows
    public void increaseAvailableDoses(int num) throws SQLException {
        if (num <= 0) {
            throw new IllegalArgumentException("Argument cannot be negative!");
        }
        this.availableDoses += num;

        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        String addDoses = "INSERT INTO VaccineDoses (Vaccine_name, Status) VALUES (?, 'available')";
        try {
            PreparedStatement statement = con.prepareStatement(addDoses);
            for (int i = 0; i < num; i++) {
                statement.setString(1, this.vaccineName);
                statement.addBatch();
            }
            statement.executeBatch();
        } catch (SQLException e) {
            throw new SQLException();
        } finally {
            cm.closeConnection();
        }
    }

    // Decrement the available doses by marking dose rows as reserved
    public void decreaseAvailableDoses(int num) throws SQLException {
        if (this.availableDoses - num < 0) {
            throw new IllegalArgumentException("Not enough available doses!");
        }
        this.availableDoses -= num;
        ConnectionManager cm = new ConnectionManager();
        Connection con = cm.createConnection();

        String reserveDoses = "UPDATE VaccineDoses SET Status = 'reserved' "
                + "WHERE Dose_id IN (SELECT Dose_id FROM VaccineDoses "
                + "WHERE Vaccine_name = ? AND Status = 'available' LIMIT ?)";
        try {
            PreparedStatement statement = con.prepareStatement(reserveDoses);
            statement.setString(1, this.vaccineName);
            statement.setInt(2, num);
            statement.executeUpdate();
        } catch (SQLException e) {
            throw new SQLException();
        } finally {
            cm.closeConnection();
        }
    }

    @Override
    public String toString() {
        return "Vaccine{" +
                "vaccineName='" + vaccineName + '\'' +
                ", availableDoses=" + availableDoses +
                '}';
    }

    public static class VaccineBuilder {
        private final String vaccineName;
        private int availableDoses;

        public VaccineBuilder(String vaccineName, int availableDoses) {
            this.vaccineName = vaccineName;
            this.availableDoses = availableDoses;
        }

        public Vaccine build() throws SQLException {
            return new Vaccine(this);
        }
    }

    public static class VaccineGetter {
        private final String vaccineName;
        private int availableDoses;

        public VaccineGetter(String vaccineName) {
            this.vaccineName = vaccineName;
        }

        public Vaccine get() throws SQLException {
            ConnectionManager cm = new ConnectionManager();
            Connection con = cm.createConnection();

            String getVaccine = "SELECT V.Name, COUNT(D.Dose_id) as Doses "
                    + "FROM Vaccines as V "
                    + "JOIN VaccineDoses as D ON V.Name = D.Vaccine_name "
                    + "WHERE V.Name = ? AND D.Status = 'available' "
                    + "GROUP BY V.Name";
            try {
                PreparedStatement statement = con.prepareStatement(getVaccine);
                statement.setString(1, this.vaccineName);
                ResultSet resultSet = statement.executeQuery();
                while (resultSet.next()) {
                    this.availableDoses = resultSet.getInt("Doses");
                    cm.closeConnection();
                    return new Vaccine(this);
                }
                return null;
            } catch (SQLException e) {
                throw new SQLException();
            } finally {
                cm.closeConnection();
            }
        }
    }
}
