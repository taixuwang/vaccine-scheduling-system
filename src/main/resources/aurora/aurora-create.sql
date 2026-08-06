DROP TABLE IF EXISTS Reservations CASCADE;
DROP TABLE IF EXISTS VaccineDoses CASCADE;
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
    PRIMARY KEY (Name)
);

CREATE TABLE VaccineDoses (
    Dose_id SERIAL PRIMARY KEY,
    Vaccine_name varchar(255) NOT NULL,
    Status varchar(20) DEFAULT 'available',
    FOREIGN KEY (Vaccine_name) REFERENCES Vaccines(Name)
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
    Dose_id int NOT NULL,
    Time date NOT NULL,
    FOREIGN KEY (Patient_name) REFERENCES Patients(Username),
    FOREIGN KEY (Caregiver_name) REFERENCES Caregivers(Username),
    FOREIGN KEY (Vaccine_name) REFERENCES Vaccines(Name),
    FOREIGN KEY (Dose_id) REFERENCES VaccineDoses(Dose_id),
    UNIQUE (Caregiver_name, Time)
);
