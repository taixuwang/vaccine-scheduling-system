"""
Shared configuration and helper utilities for all test scripts.

Provides:
  - BASE_URL configuration (defaults to http://localhost for Nginx, or http://localhost:8080 for direct)
  - Helper functions for common API calls (register, login, setup test data)
  - Colored console output for test results
"""

import requests
import sys
import time
import random
import string

BASE_URL = "http://localhost"  # Nginx load balancer (use http://localhost:8080 for direct)

# ─── Helper Functions ────────────────────────────────────────────────────────

def random_suffix():
    """Generate a random suffix to avoid username collisions between test runs."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))


def create_patient(username, password="Test@123!"):
    """Register a new patient. Returns the response."""
    return requests.post(f"{BASE_URL}/api/auth/create_patient",
                         json={"username": username, "password": password})


def create_caregiver(username, password="Test@123!"):
    """Register a new caregiver. Returns the response."""
    return requests.post(f"{BASE_URL}/api/auth/create_caregiver",
                         json={"username": username, "password": password})


def login_patient(username, password="Test@123!"):
    """Login as patient. Returns (token, response)."""
    resp = requests.post(f"{BASE_URL}/api/auth/login_patient",
                         json={"username": username, "password": password})
    token = resp.json().get("data") if resp.status_code == 200 else None
    return token, resp


def login_caregiver(username, password="Test@123!"):
    """Login as caregiver. Returns (token, response)."""
    resp = requests.post(f"{BASE_URL}/api/auth/login_caregiver",
                         json={"username": username, "password": password})
    token = resp.json().get("data") if resp.status_code == 200 else None
    return token, resp


def auth_header(token):
    """Build Authorization header dict from a JWT token."""
    return {"Authorization": f"Bearer {token}"}


def logout(token):
    """Logout the current user."""
    return requests.post(f"{BASE_URL}/api/auth/logout", headers=auth_header(token))


def upload_availability(token, date):
    """Upload caregiver availability for a given date."""
    return requests.post(f"{BASE_URL}/api/caregiver/upload_availability",
                         json={"date": date}, headers=auth_header(token))


def add_doses(token, vaccine, number):
    """Add vaccine doses (caregiver only)."""
    return requests.post(f"{BASE_URL}/api/caregiver/add_doses",
                         json={"vaccine": vaccine, "number": number},
                         headers=auth_header(token))


def reserve(token, date, vaccine):
    """Reserve an appointment (patient only)."""
    return requests.post(f"{BASE_URL}/api/reservation/reserve",
                         json={"date": date, "vaccine": vaccine},
                         headers=auth_header(token))


def cancel(token, appointment_id):
    """Cancel an appointment by ID."""
    return requests.post(f"{BASE_URL}/api/reservation/cancel",
                         params={"appointmentId": appointment_id},
                         headers=auth_header(token))


def search_schedule(token, date):
    """Search caregiver schedule for a given date."""
    return requests.post(f"{BASE_URL}/api/reservation/search_caregiver_schedule",
                         json={"date": date}, headers=auth_header(token))


def show_appointments(token):
    """Show appointments for the logged-in user."""
    return requests.get(f"{BASE_URL}/api/reservation/show_appointments",
                        headers=auth_header(token))


# ─── Test Result Formatting ─────────────────────────────────────────────────

class TestResult:
    def __init__(self, name):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, description):
        self.passed += 1
        print(f"  [PASS] {description}")

    def fail(self, description, detail=""):
        self.failed += 1
        msg = f"  [FAIL] {description}"
        if detail:
            msg += f" -- {detail}"
        self.errors.append(msg)
        print(msg)

    def assert_eq(self, description, actual, expected):
        if actual == expected:
            self.ok(description)
        else:
            self.fail(description, f"expected={expected}, actual={actual}")

    def assert_true(self, description, condition, detail=""):
        if condition:
            self.ok(description)
        else:
            self.fail(description, detail)

    def assert_status(self, description, response, expected_status):
        if response.status_code == expected_status:
            self.ok(description)
        else:
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
            self.fail(description, f"HTTP {response.status_code}, body={body}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"  {self.name}: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print(f"\n  Failures:")
            for e in self.errors:
                print(f"    {e}")
        print(f"{'='*60}\n")
        return self.failed == 0
