"""Offline checks for safety and correctness of the integration-test helpers."""

import argparse
import asyncio
import csv
import io
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import requests
import test_concurrency

from test_concurrency import (
    Attempt,
    ConcurrentClient,
    add_concurrency_arguments,
    configure_concurrency,
    latency_summary,
    post_concurrently,
    problem_summary,
)
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

    def test_concurrency_defaults_match_the_contention_scenario(self):
        with patch.dict(os.environ, {}, clear=True):
            parser = argparse.ArgumentParser()
            add_concurrency_arguments(parser)
            args = parser.parse_args([])
        self.assertEqual((args.patients, args.doses, args.caregivers, args.runs),
                         (1000, 100, 100, 10))

    def test_reservation_latency_summary_includes_failed_attempts(self):
        results = [Attempt("", 200, {}, 0.01), Attempt("", 0, None, 0.10, "TimeoutError")]
        self.assertEqual(latency_summary(results),
                         {"avg": 55.0, "p50": 10.0, "p95": 100.0,
                          "p99": 100.0, "max": 100.0})
        with self.assertRaises(ValueError):
            latency_summary([])

    def test_error_summary_counts_repeated_errors_without_dumping_them(self):
        errors = ["transport error: ServerDisconnectedError"] * 367
        errors.append("transport error: TimeoutError")
        summary = problem_summary(errors)
        self.assertIn("368 errors", summary)
        self.assertIn("ServerDisconnectedError=367", summary)
        self.assertIn("TimeoutError=1", summary)
        self.assertLess(len(summary), 250)


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


class ConcurrentClientLifecycleTests(unittest.TestCase):
    def test_batches_share_session_and_loop_and_close_after_failure(self):
        sessions = []
        loops = []
        calls = []

        class Session:
            def __init__(self, **kwargs):
                self.closed = False
                self.connector = kwargs["connector"]
                sessions.append(self)
                loops.append(asyncio.get_running_loop())

            def post(self, url, **kwargs):
                calls.append((self, asyncio.get_running_loop(), url))
                if url.endswith("/offline"):
                    raise aiohttp.ServerDisconnectedError()
                return AsyncResponse()

            async def close(self):
                self.closed = True
                loops.append(asyncio.get_running_loop())

        class AsyncResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def json(self, **kwargs):
                # Every request in a batch can run before any response completes.
                await asyncio.sleep(0)
                return {"status": 200}

        with patch("test_concurrency.aiohttp.ClientSession", Session), \
                patch("test_concurrency.aiohttp.TCPConnector") as connector:
            with self.assertRaisesRegex(RuntimeError, "scenario failed"):
                with ConcurrentClient(Settings("http://example.test")) as transport:
                    for _ in range(2):
                        results = transport.post([("token", "/ok", {})] * 4
                                                 + [("token", "/offline", {})])
                        self.assertEqual([result.status_code for result in results],
                                         [200, 200, 200, 200, 0])
                        self.assertEqual(results[-1].error, "ServerDisconnectedError")
                    self.assertEqual(len(calls), 10, "failed POSTs must not be retried")
                    raise RuntimeError("scenario failed")
            connector.assert_called_once_with(limit=0, keepalive_timeout=120)

        self.assertEqual(len(sessions), 1)
        self.assertTrue(sessions[0].closed)
        self.assertTrue(all(session is sessions[0] and loop is loops[0]
                            for session, loop, _ in calls))
        self.assertIs(loops[0], loops[1])
        self.assertTrue(loops[0].is_closed())


class ConcurrencyScenarioTests(unittest.TestCase):
    def test_failed_round_is_cleaned_before_next_round(self):
        scenario = test_concurrency.ConcurrencyTests(
            "test_reservations_do_not_oversell_and_cancellations_restore_capacity")
        scenario.setUp = Mock()
        scenario.client = Mock()
        scenario.settings = Settings("http://example.test")
        scenario.active_appointments = {}
        scenario.create_user = Mock(return_value=("user", "token"))
        events = []

        def run_round(index, *args, **kwargs):
            events.append(f"round{index}")
            self.assertEqual(scenario.active_appointments, {})
            if index == 0:
                scenario.active_appointments["42"] = "token"
                scenario.fail("simulated round failure")

        def cleanup(requests_to_send):
            events.append("cleanup")
            self.assertEqual(requests_to_send[0][2]["params"], {"appointmentId": "42"})
            return [Attempt("token", 200, {"status": 200}, 0.001)]

        scenario._run_round = Mock(side_effect=run_round)
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.dict(os.environ, {"VACCINE_TEST_PATIENTS": "2", "VACCINE_TEST_DOSES": "1",
                                       "VACCINE_TEST_CAREGIVERS": "1", "VACCINE_TEST_RUNS": "2",
                                       "VACCINE_TEST_LATENCY_FILE": str(Path(temp_dir) / "latency.csv")}), \
                patch("test_concurrency.ConcurrentClient") as transport_type, \
                redirect_stdout(io.StringIO()):
            transport_type.return_value.__enter__.return_value.post.side_effect = cleanup
            result = unittest.TestResult()
            scenario.run(result)

        self.assertEqual(events, ["round0", "cleanup", "round1"])
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.errors, [])
        self.assertEqual(scenario.active_appointments, {})

    def test_two_rounds_reuse_accounts_and_record_every_reservation(self):
        scenario = test_concurrency.ConcurrencyTests(
            "test_reservations_do_not_oversell_and_cancellations_restore_capacity")
        scenario.client = Mock()
        scenario.settings = Settings("http://example.test")
        scenario.active_appointments = {}
        scenario.create_user = Mock(side_effect=lambda role, name: (name, f"secret-{name}"))
        scenario.name = lambda name: name
        scenario.track_reservation = Mock(return_value=("99", "con_c0"))
        scenario.cancel_tracked = Mock()
        success_response = Response(200, {"status": 200})
        scenario.client.upload_availability.return_value = success_response
        scenario.client.add_doses.return_value = success_response
        recorded_requests = []

        async def post(_settings, requests_to_send, session=None):
            if requests_to_send[0][1].endswith("/cancel"):
                return [Attempt(token, 200, {"status": 200}, 0.002)
                        for token, _, _ in requests_to_send]
            recorded_requests.append(requests_to_send)
            return [
                Attempt(requests_to_send[0][0], 200,
                        {"status": 200, "data": "Appointment ID 1, Caregiver username con_c0"},
                        0.012),
                Attempt(requests_to_send[1][0], 400,
                        {"status": 400, "message": "not enough doses"}, 0.034),
            ]

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "latency.csv"
            env = {"VACCINE_TEST_PATIENTS": "2", "VACCINE_TEST_DOSES": "1",
                   "VACCINE_TEST_CAREGIVERS": "1", "VACCINE_TEST_RUNS": "2",
                   "VACCINE_TEST_LATENCY_FILE": str(report_path)}
            schedules = [({"con_c0"}, {f"con_vaccine{round_index}": 1})
                         for round_index in range(2) for _ in range(2)]
            with patch.dict(os.environ, env, clear=True), \
                    patch("test_concurrency.empty_future_date", side_effect=["2030-01-01", "2030-01-02"]), \
                    patch("test_concurrency.schedule_sections", side_effect=schedules), \
                    patch("test_concurrency.post_concurrently", new_callable=AsyncMock, side_effect=post), \
                    redirect_stdout(io.StringIO()):
                scenario.test_reservations_do_not_oversell_and_cancellations_restore_capacity()

            self.assertEqual(scenario.create_user.call_count, 3)
            self.assertEqual([[request[0] for request in batch] for batch in recorded_requests],
                             [["secret-con_p0", "secret-con_p1"]] * 2)
            for round_index, batch in enumerate(recorded_requests):
                self.assertEqual({request[2]["json"]["vaccine"] for request in batch},
                                 {f"con_vaccine{round_index}"})
            report = report_path.read_text(encoding="utf-8")
            self.assertNotIn("secret-", report)
            rows = list(csv.DictReader(io.StringIO(report)))
            self.assertEqual([(row["round"], row["attempt"], row["elapsed_ms"],
                               row["http_status"], row["error"]) for row in rows],
                             [(str(round_number), str(attempt), latency, status, "")
                              for round_number in (1, 2)
                              for attempt, latency, status in ((1, "12.000", "200"),
                                                                (2, "34.000", "400"))])

    def test_transport_failure_is_saved_before_round_fails(self):
        scenario = test_concurrency.ConcurrencyTests(
            "test_reservations_do_not_oversell_and_cancellations_restore_capacity")
        scenario.client = Mock()
        scenario.settings = Settings("http://example.test")
        scenario.active_appointments = {}
        scenario.name = lambda name: name
        scenario.client.upload_availability.return_value = Response(200, {"status": 200})
        scenario.client.add_doses.return_value = Response(200, {"status": 200})
        output = io.StringIO()
        attempts = [Attempt("secret-patient", 0, None, 0.123, "TimeoutError")]
        with patch("test_concurrency.empty_future_date", return_value="2030-01-01"), \
                patch("test_concurrency.schedule_sections", return_value=({"cg"}, {"con_vaccine0": 1})), \
                patch("test_concurrency.post_concurrently", new_callable=AsyncMock, return_value=attempts), \
                redirect_stdout(io.StringIO()), self.assertRaisesRegex(AssertionError, "TimeoutError"):
            scenario._run_round(0, 1, ["secret-patient"], [("cg", "secret-cg")],
                                set(), csv.writer(output), output)
        self.assertEqual(list(csv.reader(io.StringIO(output.getvalue()))),
                         [["1", "1", "123.000", "0", "TimeoutError"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
