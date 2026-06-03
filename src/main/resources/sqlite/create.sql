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
    Doses int,
    PRIMARY KEY (Name)
);

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
    Time date NOT NULL,
    FOREIGN KEY (Patient_name) REFERENCES Patients(Username),
    FOREIGN KEY (Caregiver_name) REFERENCES Caregivers(Username),
    FOREIGN KEY (Vaccine_name) REFERENCES Vaccines(Name),
    UNIQUE (Caregiver_name, Time)
);