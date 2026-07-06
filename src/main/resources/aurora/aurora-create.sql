DROP TABLE IF EXISTS Reservations CASCADE;
DROP TABLE IF EXISTS Patients CASCADE;
DROP TABLE IF EXISTS Vaccines CASCADE;
DROP TABLE IF EXISTS Availabilities CASCADE;
DROP TABLE IF EXISTS Caregivers CASCADE;

CREATE TABLE Caregivers (
    Username varchar(255),
    Salt BYTEA,
    Hash BYTEA,
    PRIMARY KEY (Username)
);

CREATE TABLE Availabilities (
    Time date,
    Username varchar(255) REFERENCES Caregivers,
    PRIMARY KEY (Time, Username)
);

CREATE TABLE Vaccines (
    Name varchar(255),
    Doses int CHECK (Doses >= 0),
    PRIMARY KEY (Name)
);

CREATE TABLE Patients (
    Username varchar(255),
    Salt BYTEA,
    Hash BYTEA,
    PRIMARY KEY (Username)
);

CREATE TABLE Reservations (
    Appointment_id SERIAL PRIMARY KEY,
    Patient_name varchar(255) NOT NULL,
    Caregiver_name varchar(255) NOT NULL,
    Vaccine_name varchar(255) NOT NULL,
    Time date NOT NULL,
    FOREIGN KEY (Patient_name) REFERENCES Patients(Username),
    FOREIGN KEY (Caregiver_name) REFERENCES Caregivers(Username),
    FOREIGN KEY (Vaccine_name) REFERENCES Vaccines(Name),
    UNIQUE (Caregiver_name, Time)
);