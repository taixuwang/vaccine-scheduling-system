"""
Authentication Tests
====================
Tests the auth lifecycle: registration, login, JWT issuance, and logout.

Testing aspects:
  1. Patient registration with valid credentials
  2. Caregiver registration with valid credentials
  3. Rejection of weak passwords (missing uppercase, special chars, etc.)
  4. Rejection of duplicate usernames
  5. Patient login returns a valid JWT token
  6. Caregiver login returns a valid JWT token
  7. Login with incorrect password is rejected
  8. Login with non-existent username is rejected
  9. Logout clears session and returns success
 10. Accessing protected endpoints without a token is rejected
 11. HTTP status codes: 200 for success, 400 for errors

Usage:
  1. Start the application (docker-compose up --build)
  2. Run: python src/test/test_auth.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from test_config import *


def test_patient_registration(t, suffix):
    """Test patient creation with valid and invalid inputs."""
    print("\n--- Patient Registration ---")

    # Valid registration
    resp = create_patient(f"testpat_{suffix}")
    t.assert_status("Create patient with valid credentials", resp, 200)

    # Weak password: too short
    resp = create_patient(f"testpat_short_{suffix}", "Ab1!")
    t.assert_status("Reject password < 8 characters", resp, 400)

    # Weak password: no uppercase
    resp = create_patient(f"testpat_noup_{suffix}", "abcdefg1!")
    t.assert_status("Reject password without uppercase", resp, 400)

    # Weak password: no special character
    resp = create_patient(f"testpat_nospec_{suffix}", "Abcdefg1")
    t.assert_status("Reject password without special character", resp, 400)

    # Weak password: no digit
    resp = create_patient(f"testpat_nodig_{suffix}", "Abcdefg!")
    t.assert_status("Reject password without digit", resp, 400)

    # Duplicate username
    resp = create_patient(f"testpat_{suffix}")
    t.assert_status("Reject duplicate patient username", resp, 400)


def test_caregiver_registration(t, suffix):
    """Test caregiver creation with valid and invalid inputs."""
    print("\n--- Caregiver Registration ---")

    resp = create_caregiver(f"testcg_{suffix}")
    t.assert_status("Create caregiver with valid credentials", resp, 200)

    # Duplicate username
    resp = create_caregiver(f"testcg_{suffix}")
    t.assert_status("Reject duplicate caregiver username", resp, 400)


def test_patient_login(t, suffix):
    """Test patient login success and failure cases."""
    print("\n--- Patient Login ---")

    # Successful login
    token, resp = login_patient(f"testpat_{suffix}")
    t.assert_status("Login patient with correct credentials", resp, 200)
    t.assert_true("Login returns a JWT token", token is not None and len(token) > 20,
                  f"token={token}")

    # Must logout before testing further logins
    logout(token)

    # Wrong password
    _, resp = login_patient(f"testpat_{suffix}", "WrongPass@1")
    t.assert_status("Reject login with wrong password", resp, 400)

    # Non-existent user
    _, resp = login_patient(f"ghost_user_{suffix}")
    t.assert_status("Reject login for non-existent user", resp, 400)


def test_caregiver_login(t, suffix):
    """Test caregiver login success and failure cases."""
    print("\n--- Caregiver Login ---")

    token, resp = login_caregiver(f"testcg_{suffix}")
    t.assert_status("Login caregiver with correct credentials", resp, 200)
    t.assert_true("Login returns a JWT token", token is not None and len(token) > 20,
                  f"token={token}")
    logout(token)

    _, resp = login_caregiver(f"testcg_{suffix}", "WrongPass@1")
    t.assert_status("Reject login with wrong password", resp, 400)


def test_logout(t, suffix):
    """Test logout behavior."""
    print("\n--- Logout ---")

    token, _ = login_patient(f"testpat_{suffix}")
    resp = logout(token)
    t.assert_status("Logout returns 200", resp, 200)


def test_protected_endpoint_without_token(t):
    """Test that protected endpoints reject unauthenticated requests."""
    print("\n--- Protected Endpoint Without Token ---")

    # No Authorization header at all
    resp = requests.get(f"{BASE_URL}/api/reservation/show_appointments")
    t.assert_status("Show appointments without token returns 400", resp, 400)
    t.assert_true("Error message mentions login",
                  "login" in resp.json().get("message", "").lower(),
                  f"message={resp.json().get('message')}")


def test_http_status_codes(t, suffix):
    """Verify that success returns 200 and errors return 400."""
    print("\n--- HTTP Status Code Verification ---")

    # Success case
    resp = create_patient(f"statustest_{suffix}")
    t.assert_eq("Success response has HTTP 200", resp.status_code, 200)
    t.assert_eq("Success body has status 200", resp.json()["status"], 200)

    # Error case
    resp = create_patient(f"statustest_{suffix}")  # duplicate
    t.assert_eq("Error response has HTTP 400", resp.status_code, 400)
    t.assert_eq("Error body has status 400", resp.json()["status"], 400)


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    suffix = random_suffix()
    t = TestResult("Authentication Tests")

    print(f"\nAuthentication Tests (suffix={suffix})")
    print(f"Target: {BASE_URL}")
    print("=" * 60)

    try:
        test_patient_registration(t, suffix)
        test_caregiver_registration(t, suffix)
        test_patient_login(t, suffix)
        test_caregiver_login(t, suffix)
        test_logout(t, suffix)
        test_protected_endpoint_without_token(t)
        test_http_status_codes(t, suffix)
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Cannot connect to {BASE_URL}. Is the application running?")
        sys.exit(1)

    success = t.summary()
    sys.exit(0 if success else 1)
