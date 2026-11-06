"""Offline checks for safety and correctness of the integration-test helpers."""

import argparse
import io
import os
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import aiohttp
import requests

from test_concurrency import configure_concurrency, post_concurrently
from test_config import (
    ApiClient,
    BASE_URL_ENV,
    Settings,
    positive_float,
    require_rejection,
    require_status,
    reservation_details,
    schedule_sections,
)
from test_throughput import (
    LoadFixture,
    LoadTestResult,
    ReservationCleanupError,
    reserve_and_cancel,
    run_load_test,
    setup_load_test_data,
)


class Response:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class ConfigurationTests(unittest.TestCase):
    def test_discovery_does_not_enable_integration_tests_implicitly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(unittest.SkipTest):
                Settings.from_env()

    def test_target_validation_and_timeout(self):
        settings = Settings("https://example.test/proxy/", 2)
        self.assertEqual(settings.base_url, "https://example.test/proxy")
        self.assertEqual(settings.timeout, 2)
        for target in ("example.test", "file:///tmp/test", "https://user:pass@example.test",
                       "http://example.test/?key=1", "http://:80", "http://example.test:abc",
                       "http://example.test:65536", "http://example.test\n.evil.test",
                       "http://example.test\\@evil.test"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                Settings(target)
        for value in (0, -1, "nan", "inf"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                positive_float(value)

    def test_concurrency_requires_enough_patients_and_caregivers(self):
        options = argparse.Namespace(patients=1, caregivers=2, doses=3, runs=1)
        with self.assertRaises(ValueError):
            configure_concurrency(options)


class ClientTests(unittest.TestCase):
    def test_request_uses_the_selected_target_timeout_and_token(self):
        settings = Settings("https://test.example/api-proxy", 3)
        with patch("test_config.requests.Session") as session_type:
            client = ApiClient(settings)
            client.add_doses("test-token", "unique-vaccine", 2)
            session_type.return_value.request.assert_called_once_with(
                "POST", "https://test.example/api-proxy/api/caregiver/add_doses",
                headers={"Authorization": "Bearer test-token"}, timeout=3,
                json={"vaccine": "unique-vaccine", "number": 2},
            )
            client.close()
            session_type.return_value.close.assert_called_once_with()

    def test_rejections_do_not_accept_server_errors(self):
        require_rejection(Response(400, {"status": 400, "message": "invalid"}), "bad request")
        with self.assertRaises(AssertionError):
            require_rejection(Response(500, {"message": "server error"}), "bad request")
        with self.assertRaises(AssertionError):
            require_rejection(Response(200, {"status": 200}), "bad request")
        with self.assertRaises(AssertionError):
            require_rejection(Response(404, {"message": "endpoint not found"}), "bad request")
        with self.assertRaises(AssertionError):
            require_rejection(Response(401, {"message": "unauthorized"}), "invalid input", {400, 422})
        for body in ({"message": "invalid"}, {"status": 200, "message": "invalid"}):
            with self.subTest(body=body), self.assertRaises(AssertionError):
                require_rejection(Response(400, body), "bad request")

    def test_error_diagnostics_do_not_print_response_data(self):
        response = Response(400, {"message": "login failed", "data": "private-token"})
        with self.assertRaises(AssertionError) as failure:
            require_status(response, 200, "login")
        self.assertIn("login failed", str(failure.exception))
        self.assertNotIn("private-token", str(failure.exception))

    def test_malformed_or_missing_reservation_details_fail(self):
        for message in ("", "Appointment ID 0, Caregiver username cg", "Appointment ID 7"):
            with self.subTest(message=message), self.assertRaises(AssertionError):
                reservation_details(Response(200, {"status": 200, "data": message}))
        self.assertEqual(
            reservation_details(Response(200, {"status": 200,
                                               "data": "Appointment ID 12, Caregiver username cg"})),
            ("12", "cg"),
        )

    def test_schedule_parser_handles_empty_sections_and_names_with_spaces(self):
        response = Response(200, {"status": 200, "data": [
            "Caregivers:", "No caregivers available", "Vaccines:", "Vaccine A 3",
        ]})
        self.assertEqual(schedule_sections(response), (set(), {"Vaccine A": 3}))
        with self.assertRaises(AssertionError):
            schedule_sections(Response(200, {"status": 200, "data": ["Vaccines:"]}))


class LoadTestHarnessTests(unittest.TestCase):
    def test_errors_and_rejections_are_counted_separately(self):
        result = LoadTestResult()
        result.record(1, 200)
        result.record(2, 400)
        self.assertFalse(result.passed())
        self.assertTrue(result.passed(allow_rejections=True))
        result.record(3, error="connection failed")
        self.assertFalse(result.passed(allow_rejections=True))
        self.assertEqual(result.transport_errors, 1)
        self.assertEqual(result.status_counts[400], 1)
        server_failure = LoadTestResult()
        server_failure.record(1, 200)
        server_failure.record(2, 500)
        self.assertFalse(server_failure.passed(allow_rejections=True))

    def test_write_workload_cancels_each_successful_reservation(self):
        client = Mock()
        client.reserve.return_value = Response(
            200, {"status": 200, "data": "Appointment ID 42, Caregiver username cg"}
        )
        client.cancel.return_value = Response(200, {"status": 200, "data": "cancelled"})
        fixture = LoadFixture("2030-01-01", "vax", ["patient"], ["token"])
        reserve_and_cancel(client, fixture, 0)
        client.cancel.assert_called_once_with("token", "42")
        client.cancel.return_value = Response(400, {"status": 400, "message": "failed"})
        with self.assertRaisesRegex(ReservationCleanupError, "42"):
            reserve_and_cancel(client, fixture, 0)

    def test_unknown_reservation_outcome_stops_write_workload(self):
        client = Mock()
        fixture = LoadFixture("2030-01-01", "vax", ["patient"], ["token"])
        client.reserve.side_effect = requests.Timeout("request timed out")
        with self.assertRaises(ReservationCleanupError):
            reserve_and_cancel(client, fixture, 0)
        client.cancel.assert_not_called()

        client.reserve.side_effect = None
        for response in (Response(200, {"status": 200, "data": "malformed"}),
                         Response(500, {"status": 500, "message": "server error"}),
                         Response(400, {"status": 400, "message": "unexpected"})):
            with self.subTest(status=response.status_code), \
                    self.assertRaises(ReservationCleanupError):
                client.reserve.return_value = response
                reserve_and_cancel(client, fixture, 0)
        client.cancel.assert_not_called()

        rejection = Response(400, {"status": 400, "message": "not enough doses"})
        client.reserve.return_value = rejection
        self.assertIs(reserve_and_cancel(client, fixture, 0), rejection)

    def test_workers_wait_for_initialization_and_stop_on_cleanup_error(self):
        second_initializing = threading.Event()
        finish_initialization = threading.Event()
        lock = threading.Lock()
        initializations = []
        attempts = []
        outcomes = []

        def new_client(_settings):
            with lock:
                initializations.append(1)
                is_second = len(initializations) == 2
            if is_second:
                second_initializing.set()
                if not finish_initialization.wait(5):
                    raise RuntimeError("test timed out waiting for initialization")
            return Mock()

        def operation(_client, index):
            attempts.append(index)
            raise ReservationCleanupError("reservation may still be active")

        def run():
            outcomes.append(run_load_test("test", Settings("http://example.test"),
                                          operation, 2, 1))

        with patch("test_throughput.ApiClient", side_effect=new_client), \
                redirect_stdout(io.StringIO()):
            runner = threading.Thread(target=run)
            runner.start()
            try:
                self.assertTrue(second_initializing.wait(5))
                self.assertEqual(attempts, [])
            finally:
                finish_initialization.set()
                runner.join(5)
            self.assertFalse(runner.is_alive())

        self.assertEqual(sorted(attempts), [0, 1])
        self.assertEqual(outcomes, [False])

    def test_load_setup_uses_the_same_explicit_target(self):
        settings = Settings("http://example.test:8081", 2)
        with patch("test_throughput.ApiClient") as client_type, \
                patch("test_throughput.secrets.token_hex", return_value="unique"), \
                patch("test_throughput.empty_future_date", return_value="2030-01-01"), \
                patch("test_throughput.schedule_sections", return_value=(
                    {"load_caregiver0_unique"}, {"load_vaccine_unique": 1}
                )):
            client = client_type.return_value
            client.create.return_value = Response(200, {"status": 200})
            client.login.return_value = "token"
            client.upload_availability.return_value = Response(200, {"status": 200})
            client.add_doses.return_value = Response(200, {"status": 200})
            setup_load_test_data(settings, 1)
            client_type.assert_called_once_with(settings)


class ConcurrentTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_target_responses_and_connection_errors_are_preserved(self):
        calls = []

        class AsyncResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def json(self, **kwargs):
                return {"status": 200, "data": "ok"}

        class Session:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def post(self, url, **kwargs):
                calls.append((url, kwargs))
                if url.endswith("/offline"):
                    raise aiohttp.ClientConnectionError("offline")
                return AsyncResponse()

        with patch("test_concurrency.aiohttp.ClientSession", Session), \
                patch("test_concurrency.aiohttp.TCPConnector", return_value=None):
            results = await post_concurrently(Settings("https://target.example", 2), [
                ("token-a", "/ok", {"json": {"value": 1}}),
                ("token-b", "/offline", {}),
            ])

        self.assertEqual([result.status_code for result in results], [200, 0])
        self.assertEqual(results[1].error, "ClientConnectionError")
        self.assertEqual(calls[0][0], "https://target.example/ok")
        self.assertEqual(calls[0][1]["headers"]["Authorization"], "Bearer token-a")


if __name__ == "__main__":
    unittest.main(verbosity=2)
