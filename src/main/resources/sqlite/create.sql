CREATE TABLE Caregivers (
    Username varchar(255),
    Salt BINARY(16),
    Hash BINARY(16),
    PRIMARY KEY (Username)
);

CREATE TABLE Availabilities (
    Time date,
    Username varchar(255) REFERENCES Caregivers,
    PRIMARY KEY (Time, Username)
);

CREATE TABLE Vaccines (
    Name varchar(255),
    PRIMARY KEY (Name)
);

CREATE TABLE VaccineDoses (
    Dose_id INTEGER PRIMARY KEY AUTOINCREMENT,
    Vaccine_name varchar(255) NOT NULL,
    Status varchar(20) DEFAULT 'available',
    FOREIGN KEY (Vaccine_name) REFERENCES Vaccines(Name)
);

CREATE INDEX idx_vaccine_doses_vaccine_status ON VaccineDoses(Vaccine_name, Status);

CREATE TABLE Patients (
    Username varchar(255),
    Salt BINARY(16),
    Hash BINARY(16),
    PRIMARY KEY (Username)
);

CREATE TABLE Reservations (
    Appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    Patient_name varchar(255) NOT NULL,
    Caregiver_name varchar(255) NOT NULL,
    Vaccine_name varchar(255) NOT NULL,
    Dose_id int NOT NULL,
    Time date NOT NULL,
    FOREIGN KEY (Patient_name) REFERENCES Patients(Username),
    FOREIGN KEY (Caregiver_name) REFERENCES Caregivers(Username),
    FOREIGN KEY (Vaccine_name) REFERENCES Vaccines(Name),
    FOREIGN KEY (Dose_id) REFERENCES VaccineDoses(Dose_id),
    UNIQUE (Caregiver_name, Time)
);
