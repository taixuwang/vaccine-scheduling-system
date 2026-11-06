"""Concurrent reservation and cancellation checks without global data cleanup."""

import asyncio
import csv
import math
import os
import secrets
import statistics
import time
from collections import Counter
from dataclasses import dataclass

import aiohttp

from test_config import (
    IntegrationTestCase,
    empty_future_date,
    positive_int,
    require_rejection,
    require_status,
    reservation_details,
    run_module_cli,
    schedule_sections,
)


PATIENTS_ENV = "VACCINE_TEST_PATIENTS"
DOSES_ENV = "VACCINE_TEST_DOSES"
CAREGIVERS_ENV = "VACCINE_TEST_CAREGIVERS"
RUNS_ENV = "VACCINE_TEST_RUNS"
LATENCY_FILE_ENV = "VACCINE_TEST_LATENCY_FILE"
DEFAULT_PATIENTS = 1000
DEFAULT_DOSES = 100
DEFAULT_CAREGIVERS = 100
DEFAULT_RUNS = 10


def add_concurrency_arguments(parser):
    parser.add_argument("--patients", type=positive_int,
                        default=positive_int(os.environ.get(PATIENTS_ENV, DEFAULT_PATIENTS)))
    parser.add_argument("--doses", type=positive_int,
                        default=positive_int(os.environ.get(DOSES_ENV, DEFAULT_DOSES)))
    parser.add_argument("--caregivers", type=positive_int,
                        default=positive_int(os.environ.get(CAREGIVERS_ENV, DEFAULT_CAREGIVERS)))
    parser.add_argument("--runs", type=positive_int,
                        default=positive_int(os.environ.get(RUNS_ENV, DEFAULT_RUNS)))
    parser.add_argument("--latency-file", default=os.environ.get(LATENCY_FILE_ENV),
                        help="new CSV path for per-request latency (default: unique file in current directory)")


def configure_concurrency(args):
    if args.patients < args.doses or args.caregivers < args.doses:
        raise ValueError("patients and caregivers must each be at least the dose count")
    for key, value in ((PATIENTS_ENV, args.patients), (DOSES_ENV, args.doses),
                       (CAREGIVERS_ENV, args.caregivers), (RUNS_ENV, args.runs)):
        os.environ[key] = str(value)
    latency_file = getattr(args, "latency_file", None)
    if latency_file is not None:
        if not latency_file.strip():
            raise ValueError("latency file path must not be empty")
        os.environ[LATENCY_FILE_ENV] = latency_file
    else:
        os.environ.pop(LATENCY_FILE_ENV, None)


@dataclass
class Attempt:
    token: str
    status_code: int
    body: object
    elapsed: float
    error: str = ""

    def json(self):
        if not isinstance(self.body, dict):
            raise ValueError("response is not a JSON object")
        return self.body


def latency_summary(results):
    """Summarize all attempts, including failed requests, in milliseconds.

    Percentiles use the nearest-rank method, consistent with the load test.
    """
    values = sorted(result.elapsed * 1000 for result in results)
    if not values:
        raise ValueError("at least one request is required to calculate latency")

    def percentile(fraction):
        return values[math.ceil(len(values) * fraction) - 1]

    return {
        "avg": statistics.mean(values),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
        "max": values[-1],
    }


async def post_concurrently(settings, requests_to_send):
    """Return every response, including transport errors, without dropping tasks."""
    timeout = aiohttp.ClientTimeout(total=settings.timeout)
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        async def send(token, path, payload):
            start = time.monotonic()
            try:
                async with session.post(
                    settings.base_url + path, headers={"Authorization": f"Bearer {token}"},
                    **payload,
                ) as response:
                    try:
                        body = await response.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError):
                        body = None
                    return Attempt(token, response.status, body, time.monotonic() - start)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                return Attempt(token, 0, None, time.monotonic() - start, type(exc).__name__)

        return await asyncio.gather(*(send(*request) for request in requests_to_send))


class ConcurrencyTests(IntegrationTestCase):
    def test_reservations_do_not_oversell_and_cancellations_restore_capacity(self):
        patients = positive_int(os.environ.get(PATIENTS_ENV, DEFAULT_PATIENTS))
        doses = positive_int(os.environ.get(DOSES_ENV, DEFAULT_DOSES))
        caregivers = positive_int(os.environ.get(CAREGIVERS_ENV, DEFAULT_CAREGIVERS))
        runs = positive_int(os.environ.get(RUNS_ENV, DEFAULT_RUNS))
        if patients < doses or caregivers < doses:
            self.fail("patients and caregivers must each be at least the dose count")
        path = os.environ.get(LATENCY_FILE_ENV) or f"concurrency-latency-{secrets.token_hex(8)}.csv"
        # Exclusive creation protects an existing report from accidental overwrite.
        with open(path, "x", newline="", encoding="utf-8") as latency_file:
            writer = csv.writer(latency_file)
            writer.writerow(("round", "attempt", "elapsed_ms", "http_status", "error"))
            latency_file.flush()
            print(f"  reservation latency CSV: {os.path.abspath(path)}", flush=True)
            tokens = [self.create_user("patient", f"con_p{index}")[1]
                      for index in range(patients)]
            caregivers_by_name = [self.create_user("caregiver", f"con_c{index}")
                                  for index in range(caregivers)]
            used_days = set()
            for run in range(runs):
                with self.subTest(run=run + 1):
                    self._run_round(run, doses, tokens, caregivers_by_name, used_days,
                                    writer, latency_file)

    def _run_round(self, run, dose_count, tokens, caregivers_by_name, used_days,
                   writer, latency_file):
        first_patient = tokens[0]
        for _ in range(30):
            day = empty_future_date(self.client, first_patient)
            if day not in used_days:
                break
        else:
            raise AssertionError("could not find a distinct date for this round")
        used_days.add(day)
        caregiver_names = set()
        for name, token in caregivers_by_name:
            caregiver_names.add(name)
            require_status(self.client.upload_availability(token, day), 200, "upload availability")

        vaccine = self.name(f"con_vaccine{run}")
        require_status(self.client.add_doses(caregivers_by_name[0][1], vaccine, dose_count),
                       200, "add concurrent test doses")
        doses_by_vaccine = {vaccine: dose_count}

        visible_caregivers, visible_doses = schedule_sections(self.client.search(first_patient, day))
        self.assertEqual(visible_caregivers, caregiver_names,
                         "the selected date contains another caregiver; use an isolated instance")
        for vaccine, count in doses_by_vaccine.items():
            self.assertEqual(visible_doses.get(vaccine), count)

        requests_to_send = [
            (token, "/api/reservation/reserve", {"json": {"date": day, "vaccine": vaccine}})
            for token in tokens
        ]
        started = time.monotonic()
        results = asyncio.run(post_concurrently(self.settings, requests_to_send))
        elapsed = time.monotonic() - started
        successes = []
        problems = []
        for request, result in zip(requests_to_send, results):
            if result.error:
                problems.append(f"transport error: {result.error}")
            elif result.status_code == 200:
                try:
                    appointment_id, caregiver = reservation_details(result)
                    self.active_appointments[appointment_id] = result.token
                    successes.append((appointment_id, caregiver, result.token,
                                      request[2]["json"]["vaccine"]))
                except AssertionError as exc:
                    problems.append(str(exc))
            else:
                try:
                    body = require_rejection(result, "concurrent reservation", {400, 409, 422})
                    message = str(body.get("message", "")).lower()
                    if "not enough" not in message and "no caregiver" not in message:
                        problems.append(f"unexpected rejection: {message}")
                except AssertionError as exc:
                    problems.append(str(exc))

        # Track successful appointments before writing, so cleanup still runs if
        # the report cannot be written (for example, the disk is full).
        for index, result in enumerate(results, start=1):
            writer.writerow((run + 1, index, f"{result.elapsed * 1000:.3f}",
                             result.status_code, result.error))
        latency_file.flush()

        print(f"  concurrency round {run + 1}: {len(successes)}/{len(results)} reservations "
              f"in {elapsed:.2f}s", flush=True)
        if results:
            latency = latency_summary(results)
            print("  reservation latency (ms; all attempts, including errors): "
                  + " ".join(f"{name}={value:.1f}" for name, value in latency.items()),
                  flush=True)
        self.assertFalse(problems, "; ".join(problems[:5]))
        self.assertEqual(len(successes), dose_count, "available doses should be fully booked")
        ids = [appointment_id for appointment_id, _, _, _ in successes]
        assigned = [caregiver for _, caregiver, _, _ in successes]
        self.assertEqual(len(set(ids)), len(successes), "appointment IDs must be unique")
        self.assertEqual(len(set(assigned)), len(successes), "caregivers must not be double-booked")
        self.assertTrue(set(assigned).issubset(caregiver_names))
        self.assertEqual(Counter(vaccine for _, _, _, vaccine in successes), doses_by_vaccine,
                         "each vaccine should be booked up to its own available count")

        cancel_requests = [
            (token, "/api/reservation/cancel", {"params": {"appointmentId": appointment_id}})
            for appointment_id, _, token, _ in successes
        ]
        cancelled = asyncio.run(post_concurrently(self.settings, cancel_requests))
        cancellation_errors = []
        for (appointment_id, _, _, _), result in zip(successes, cancelled):
            try:
                if result.error:
                    raise AssertionError(f"transport error: {result.error}")
                require_status(result, 200, f"cancel appointment {appointment_id}")
                del self.active_appointments[appointment_id]
            except AssertionError as exc:
                cancellation_errors.append(str(exc))
        self.assertFalse(cancellation_errors, "; ".join(cancellation_errors[:5]))

        available, visible_doses = schedule_sections(self.client.search(first_patient, day))
        self.assertEqual(available, caregiver_names)
        for vaccine, count in doses_by_vaccine.items():
            self.assertEqual(visible_doses.get(vaccine), count)
        appointment_id, assigned_caregiver = self.track_reservation(
            self.client.reserve(first_patient, day, vaccine), first_patient
        )
        self.assertIn(assigned_caregiver, caregiver_names)
        self.cancel_tracked(appointment_id)


if __name__ == "__main__":
    run_module_cli(add_concurrency_arguments, configure_concurrency)
