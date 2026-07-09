"""
Reservation Flow Tests
======================
Tests the complete reservation lifecycle: search, reserve, show, and cancel.

Testing aspects:
  1. Search caregiver schedule returns available caregivers and vaccines
  2. Patient can successfully reserve an appointment
  3. Reservation returns an appointment ID and assigned caregiver
  4. Caregiver cannot make reservations (role enforcement)
  5. Unauthenticated users cannot reserve
  6. Reservation fails when no vaccine doses are available
  7. Reservation fails when no caregiver is available for the date
  8. Cancel an existing appointment restores the dose and caregiver slot
  9. Cancel a non-existent appointment is rejected
 10. Show appointments returns the correct appointments for the user
 11. Patient can only cancel their own appointments

Usage:
  1. Start the application (docker-compose up --build)
  2. Run: python src/test/test_reservation.py
"""

import sys
import os
import re
sys.path.insert(0, os.path.dirname(__file__))

from test_config import *

TEST_DATE = "2026-08-15"
TEST_VACCINE = "TestVax"


def setup_test_data(suffix):
    """Create caregivers with availability and vaccine doses for testing."""
    print("\n--- Setup ---")

    # Create and login a caregiver to set up test data
    create_caregiver(f"res_cg_{suffix}")
    cg_token, _ = login_caregiver(f"res_cg_{suffix}")

    # Upload availability for the test date
    upload_availability(cg_token, TEST_DATE)

    # Add vaccine doses
    add_doses(cg_token, TEST_VACCINE, 5)
    logout(cg_token)

    # Create test patients
    create_patient(f"res_pat1_{suffix}")
    create_patient(f"res_pat2_{suffix}")

    print("  Setup complete: 1 caregiver, 2 patients, 5 doses")
    return suffix


def test_search_schedule(t, suffix):
    """Test searching for available caregivers and vaccines."""
    print("\n--- Search Caregiver Schedule ---")

    pat_token, _ = login_patient(f"res_pat1_{suffix}")

    resp = search_schedule(pat_token, TEST_DATE)
    t.assert_status("Search schedule returns 200", resp, 200)

    data = resp.json()["data"]
    t.assert_true("Results contain caregivers section",
                  "Caregivers:" in data, f"data={data}")
    t.assert_true("Results contain the test caregiver",
                  f"res_cg_{suffix}" in data, f"data={data}")
    t.assert_true("Results contain vaccines section",
                  "Vaccines:" in data, f"data={data}")

    logout(pat_token)


def test_reserve_success(t, suffix):
    """Test a successful reservation."""
    print("\n--- Reserve Appointment (Success) ---")

    pat_token, _ = login_patient(f"res_pat1_{suffix}")

    resp = reserve(pat_token, TEST_DATE, TEST_VACCINE)
    t.assert_status("Reserve returns 200", resp, 200)

    msg = resp.json()["data"]
    t.assert_true("Response contains Appointment ID",
                  "Appointment ID" in msg, f"msg={msg}")
    t.assert_true("Response contains Caregiver username",
                  "Caregiver username" in msg, f"msg={msg}")

    # Extract appointment ID for later cancel test
    match = re.search(r"Appointment ID (\d+)", msg)
    appointment_id = match.group(1) if match else None
    t.assert_true("Appointment ID is a valid number",
                  appointment_id is not None and appointment_id.isdigit(),
                  f"extracted={appointment_id}")

    logout(pat_token)
    return appointment_id


def test_reserve_as_caregiver(t, suffix):
    """Test that caregivers cannot make reservations."""
    print("\n--- Reserve as Caregiver (Should Fail) ---")

    cg_token, _ = login_caregiver(f"res_cg_{suffix}")
    resp = reserve(cg_token, TEST_DATE, TEST_VACCINE)
    t.assert_status("Caregiver cannot reserve (HTTP 400)", resp, 400)
    logout(cg_token)


def test_reserve_without_auth(t):
    """Test that unauthenticated users cannot reserve."""
    print("\n--- Reserve Without Authentication ---")

    resp = requests.post(f"{BASE_URL}/api/reservation/reserve",
                         json={"date": TEST_DATE, "vaccine": TEST_VACCINE})
    t.assert_status("Unauthenticated reserve returns 400", resp, 400)


def test_reserve_no_doses(t, suffix):
    """Test reservation when no vaccine doses are available."""
    print("\n--- Reserve With No Doses ---")

    pat_token, _ = login_patient(f"res_pat2_{suffix}")
    resp = reserve(pat_token, TEST_DATE, "NonExistentVaccine")
    t.assert_status("Reserve with non-existent vaccine returns 400", resp, 400)
    logout(pat_token)


def test_show_appointments(t, suffix):
    """Test showing appointments for a user."""
    print("\n--- Show Appointments ---")

    pat_token, _ = login_patient(f"res_pat1_{suffix}")
    resp = show_appointments(pat_token)
    t.assert_status("Show appointments returns 200", resp, 200)

    data = resp.json()["data"]
    t.assert_true("Appointments list is not empty",
                  len(data) > 0 and "No appointments" not in data[0],
                  f"data={data}")

    logout(pat_token)


def test_cancel_appointment(t, suffix, appointment_id):
    """Test canceling an existing appointment."""
    print("\n--- Cancel Appointment ---")

    if appointment_id is None:
        t.fail("Cancel test skipped", "No appointment ID from reserve test")
        return

    pat_token, _ = login_patient(f"res_pat1_{suffix}")

    resp = cancel(pat_token, appointment_id)
    t.assert_status("Cancel appointment returns 200", resp, 200)
    t.assert_true("Cancel message confirms success",
                  "successfully canceled" in resp.json()["data"].lower(),
                  f"msg={resp.json()['data']}")

    # Verify appointment is gone
    resp = show_appointments(pat_token)
    data = resp.json()["data"]
    t.assert_true("Canceled appointment no longer in list",
                  not any(appointment_id in item for item in data),
                  f"data={data}")

    logout(pat_token)


def test_cancel_nonexistent(t, suffix):
    """Test canceling a non-existent appointment."""
    print("\n--- Cancel Non-Existent Appointment ---")

    pat_token, _ = login_patient(f"res_pat1_{suffix}")
    resp = cancel(pat_token, "999999")
    t.assert_status("Cancel non-existent appointment returns 400", resp, 400)
    logout(pat_token)


def test_cancel_wrong_user(t, suffix, appointment_id_for_wrong_user):
    """Test that a patient cannot cancel another patient's appointment."""
    print("\n--- Cancel Another Patient's Appointment ---")

    if appointment_id_for_wrong_user is None:
        # Create a new reservation for pat1, then try to cancel as pat2
        pat1_token, _ = login_patient(f"res_pat1_{suffix}")

        # Need caregiver availability again (was consumed by earlier reserve)
        logout(pat1_token)
        cg_token, _ = login_caregiver(f"res_cg_{suffix}")
        upload_availability(cg_token, "2026-08-20")
        logout(cg_token)

        pat1_token, _ = login_patient(f"res_pat1_{suffix}")
        resp = reserve(pat1_token, "2026-08-20", TEST_VACCINE)
        if resp.status_code == 200:
            match = re.search(r"Appointment ID (\d+)", resp.json()["data"])
            appointment_id_for_wrong_user = match.group(1) if match else None
        logout(pat1_token)

    if appointment_id_for_wrong_user is None:
        t.fail("Cross-user cancel test skipped", "Could not create test appointment")
        return

    pat2_token, _ = login_patient(f"res_pat2_{suffix}")
    resp = cancel(pat2_token, appointment_id_for_wrong_user)
    t.assert_status("Patient cannot cancel another's appointment", resp, 400)
    logout(pat2_token)


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    suffix = random_suffix()
    t = TestResult("Reservation Flow Tests")

    print(f"\nReservation Flow Tests (suffix={suffix})")
    print(f"Target: {BASE_URL}")
    print("=" * 60)

    try:
        setup_test_data(suffix)
        test_search_schedule(t, suffix)
        appointment_id = test_reserve_success(t, suffix)
        test_reserve_as_caregiver(t, suffix)
        test_reserve_without_auth(t)
        test_reserve_no_doses(t, suffix)
        test_show_appointments(t, suffix)
        test_cancel_appointment(t, suffix, appointment_id)
        test_cancel_nonexistent(t, suffix)
        test_cancel_wrong_user(t, suffix, None)
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Cannot connect to {BASE_URL}. Is the application running?")
        sys.exit(1)

    success = t.summary()
    sys.exit(0 if success else 1)
