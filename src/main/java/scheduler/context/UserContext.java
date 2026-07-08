package scheduler.context;

import scheduler.model.Caregiver;
import scheduler.model.Patient;

public class UserContext {
    private static final ThreadLocal<Caregiver> currentCaregiver = new ThreadLocal<>();
    private static final ThreadLocal<Patient> currentPatient = new ThreadLocal<>();

    public static void setCaregiver(Caregiver caregiver) {
        currentCaregiver.set(caregiver);
    }

    public static Caregiver getCaregiver() {
        return currentCaregiver.get();
    }

    public static void setPatient(Patient patient) {
        currentPatient.set(patient);
    }

    public static Patient getPatient() {
        return currentPatient.get();
    }

    public static void clear() {
        currentCaregiver.remove();
        currentPatient.remove();
    }
}
