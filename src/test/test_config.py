"""Shared configuration and helpers for the API test suite.

Integration tests require VACCINE_TEST_BASE_URL when discovered by unittest.
The script entry points set it explicitly, defaulting to the local Compose URL.
"""

import argparse
import os
import re
import secrets
import sys
import unittest
from datetime import date, timedelta
from urllib.parse import urlsplit

import requests


BASE_URL_ENV = "VACCINE_TEST_BASE_URL"
TIMEOUT_ENV = "VACCINE_TEST_TIMEOUT"
DEFAULT_BASE_URL = "http://localhost"
DEFAULT_TIMEOUT = 15.0
PASSWORD = "Test@123!"


def positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def positive_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a positive number") from exc
    if not 0 < number < float("inf"):
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return number


class Settings:
    def __init__(self, base_url, timeout=DEFAULT_TIMEOUT):
        parsed = urlsplit(base_url)
        if (parsed.scheme not in ("http", "https") or not parsed.netloc
                or parsed.query or parsed.fragment or parsed.username is not None):
            raise ValueError("target must be an HTTP(S) URL without credentials, query, or fragment")
        self.base_url = base_url.rstrip("/")
        self.timeout = positive_float(timeout)

    @classmethod
    def from_env(cls):
        base_url = os.environ.get(BASE_URL_ENV)
        if not base_url:
            raise unittest.SkipTest(
                f"Set {BASE_URL_ENV} to run integration tests against a disposable instance"
            )
        return cls(base_url, os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT))


def add_target_arguments(parser):
    parser.add_argument(
        "--target", default=os.environ.get(BASE_URL_ENV, DEFAULT_BASE_URL),
        help="base URL of a disposable test instance (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout", type=positive_float,
        default=positive_float(os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT)),
        help="per-request timeout in seconds (default: %(default)s)",
    )


def configure_environment(target, timeout):
    settings = Settings(target, timeout)
    os.environ[BASE_URL_ENV] = settings.base_url
    os.environ[TIMEOUT_ENV] = str(settings.timeout)
    return settings


def run_module_cli(add_arguments=None, configure=None):
    """Run an individual unittest module while retaining unittest CLI options."""
    parser = argparse.ArgumentParser()
    add_target_arguments(parser)
    if add_arguments:
        add_arguments(parser)
    args, remaining = parser.parse_known_args()
    try:
        settings = configure_environment(args.target, args.timeout)
        if configure:
            configure(args)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))
    print(f"Integration test target: {settings.base_url}", flush=True)
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)


class ApiClient:
    """A client with an explicit target and timeout; do not share across threads."""

    def __init__(self, settings):
        self.settings = settings
        self.session = requests.Session()

    def close(self):
        self.session.close()

    def request(self, method, path, *, token=None, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return self.session.request(
            method, self.settings.base_url + path, headers=headers,
            timeout=self.settings.timeout, **kwargs,
        )

    def create(self, role, username, password=PASSWORD):
        return self.request("POST", f"/api/auth/create_{role}",
                            json={"username": username, "password": password})

    def login_response(self, role, username, password=PASSWORD):
        return self.request("POST", f"/api/auth/login_{role}",
                            json={"username": username, "password": password})

    def login(self, role, username, password=PASSWORD):
        response = self.login_response(role, username, password)
        body = require_status(response, 200, f"login {role} {username}")
        token = body.get("data")
        if not isinstance(token, str) or not token:
            raise AssertionError(f"login {role} returned no token")
        return token

    def logout(self, token):
        return self.request("POST", "/api/auth/logout", token=token)

    def upload_availability(self, token, day):
        return self.request("POST", "/api/caregiver/upload_availability",
                            token=token, json={"date": day})

    def add_doses(self, token, vaccine, number):
        return self.request("POST", "/api/caregiver/add_doses", token=token,
                            json={"vaccine": vaccine, "number": number})

    def search(self, token, day):
        return self.request("POST", "/api/reservation/search_caregiver_schedule",
                            token=token, json={"date": day})

    def reserve(self, token, day, vaccine):
        return self.request("POST", "/api/reservation/reserve", token=token,
                            json={"date": day, "vaccine": vaccine})

    def cancel(self, token, appointment_id):
        return self.request("POST", "/api/reservation/cancel", token=token,
                            params={"appointmentId": appointment_id})

    def appointments(self, token):
        return self.request("GET", "/api/reservation/show_appointments", token=token)


def response_body(response):
    try:
        body = response.json()
    except ValueError as exc:
        raise AssertionError(f"HTTP {response.status_code} response was not valid JSON") from exc
    if not isinstance(body, dict):
        raise AssertionError(f"HTTP {response.status_code} response was not a JSON object")
    return body


def require_status(response, expected, action):
    if response.status_code != expected:
        # Include only the message, never the data field which can contain a token.
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get("message"), str):
                detail = f" ({body['message'][:200]})"
        except ValueError:
            pass
        raise AssertionError(
            f"{action}: expected HTTP {expected}, got HTTP {response.status_code}{detail}"
        )
    body = response_body(response)
    if body.get("status") != expected:
        raise AssertionError(f"{action}: response status does not match HTTP {expected}")
    return body


def require_rejection(response, action, expected=None):
    expected = {400, 401, 403, 409, 422} if expected is None else set(expected)
    if response.status_code not in expected:
        raise AssertionError(
            f"{action}: expected a validation or authorization rejection, got HTTP {response.status_code}"
        )
    return response_body(response)


def reservation_details(response):
    body = require_status(response, 200, "reserve")
    message = body.get("data")
    if not isinstance(message, str):
        raise AssertionError("reservation response has no message")
    match = re.fullmatch(r"Appointment ID (\d+), Caregiver username (\S+)", message)
    if not match or int(match.group(1)) <= 0:
        raise AssertionError(f"malformed reservation response: {message!r}")
    return match.group(1), match.group(2)


def schedule_sections(response):
    body = require_status(response, 200, "search schedule")
    items = body.get("data")
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise AssertionError("schedule response data must be a list of strings")
    if not items or items[0] != "Caregivers:" or "Vaccines:" not in items:
        raise AssertionError("schedule response is missing its section headings")
    split = items.index("Vaccines:")
    caregivers = {item for item in items[1:split] if item != "No caregivers available"}
    vaccines = {}
    for item in items[split + 1:]:
        if item == "No vaccines available":
            continue
        try:
            name, count = item.rsplit(" ", 1)
            vaccines[name] = int(count)
        except (ValueError, TypeError) as exc:
            raise AssertionError(f"malformed vaccine entry: {item!r}") from exc
    return caregivers, vaccines


def empty_future_date(client, token):
    """Find a future date with no visible caregiver slots before creating fixtures."""
    for _ in range(30):
        day = (date.today() + timedelta(days=30 + secrets.randbelow(700))).isoformat()
        caregivers, _ = schedule_sections(client.search(token, day))
        if not caregivers:
            return day
    raise AssertionError("could not find an empty date; use an isolated test instance")


class IntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings.from_env()

    def setUp(self):
        self.client = ApiClient(self.settings)
        self.addCleanup(self.client.close)
        self.suffix = secrets.token_hex(8)
        self.active_appointments = {}
        self.addCleanup(self._cleanup_appointments)

    def name(self, prefix):
        return f"{prefix}_{self.suffix}"

    def create_user(self, role, prefix):
        username = self.name(prefix)
        require_status(self.client.create(role, username), 200, f"create {role} {username}")
        return username, self.client.login(role, username)

    def track_reservation(self, response, token):
        appointment_id, caregiver = reservation_details(response)
        self.active_appointments[appointment_id] = token
        return appointment_id, caregiver

    def cancel_tracked(self, appointment_id):
        token = self.active_appointments[appointment_id]
        response = self.client.cancel(token, appointment_id)
        require_status(response, 200, f"cancel appointment {appointment_id}")
        del self.active_appointments[appointment_id]

    def _cleanup_appointments(self):
        failures = []
        for appointment_id, token in list(self.active_appointments.items()):
            try:
                require_status(self.client.cancel(token, appointment_id), 200,
                               f"cleanup appointment {appointment_id}")
            except (AssertionError, requests.RequestException) as exc:
                failures.append(str(exc))
        if failures:
            raise AssertionError("failed to clean up test appointments: " + "; ".join(failures))
