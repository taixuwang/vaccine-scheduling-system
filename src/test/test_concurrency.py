"""Concurrent reservation and cancellation checks without global data cleanup."""

import asyncio
import os
import time
from collections import Counter
from dataclasses import dataclass

import aiohttp

from test_config import (
    IntegrationTestCase,
    empty_future_date,
    positive_int,
    require_status,
    reservation_details,
    run_module_cli,
    schedule_sections,
)


PATIENTS_ENV = "VACCINE_TEST_PATIENTS"
DOSES_ENV = "VACCINE_TEST_DOSES"
CAREGIVERS_ENV = "VACCINE_TEST_CAREGIVERS"
RUNS_ENV = "VACCINE_TEST_RUNS"


def add_concurrency_arguments(parser):
    parser.add_argument("--patients", type=positive_int,
                        default=positive_int(os.environ.get(PATIENTS_ENV, 30)))
    parser.add_argument("--doses", type=positive_int,
                        default=positive_int(os.environ.get(DOSES_ENV, 10)))
    parser.add_argument("--caregivers", type=positive_int,
                        default=positive_int(os.environ.get(CAREGIVERS_ENV, 10)))
    parser.add_argument("--runs", type=positive_int,
                        default=positive_int(os.environ.get(RUNS_ENV, 1)))


def configure_concurrency(args):
    if args.patients < args.doses or args.caregivers < args.doses:
        raise ValueError("patients and caregivers must each be at least the dose count")
    for key, value in ((PATIENTS_ENV, args.patients), (DOSES_ENV, args.doses),
                       (CAREGIVERS_ENV, args.caregivers), (RUNS_ENV, args.runs)):
        os.environ[key] = str(value)


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
        patients = positive_int(os.environ.get(PATIENTS_ENV, 30))
        doses = positive_int(os.environ.get(DOSES_ENV, 10))
        caregivers = positive_int(os.environ.get(CAREGIVERS_ENV, 10))
        runs = positive_int(os.environ.get(RUNS_ENV, 1))
        if patients < doses or caregivers < doses:
            self.fail("patients and caregivers must each be at least the dose count")
        for run in range(runs):
            with self.subTest(run=run + 1):
                self._run_round(run, patients, doses, caregivers)

    def _run_round(self, run, patient_count, dose_count, caregiver_count):
        _, first_patient = self.create_user("patient", f"con_p{run}_0")
        day = empty_future_date(self.client, first_patient)
        caregiver_names = set()
        caregiver_tokens = []
        for index in range(caregiver_count):
            name, token = self.create_user("caregiver", f"con_c{run}_{index}")
            caregiver_names.add(name)
            caregiver_tokens.append(token)
            require_status(self.client.upload_availability(token, day), 200, "upload availability")

        vaccine_count = min(5, dose_count)
        vaccines = [self.name(f"con_vaccine{run}_{index}") for index in range(vaccine_count)]
        doses_by_vaccine = Counter(vaccines[index % vaccine_count] for index in range(dose_count))
        for vaccine, count in doses_by_vaccine.items():
            require_status(self.client.add_doses(caregiver_tokens[0], vaccine, count),
                           200, "add concurrent test doses")
        tokens = [first_patient]
        for index in range(1, patient_count):
            _, token = self.create_user("patient", f"con_p{run}_{index}")
            tokens.append(token)

        visible_caregivers, visible_doses = schedule_sections(self.client.search(first_patient, day))
        self.assertEqual(visible_caregivers, caregiver_names,
                         "the selected date contains another caregiver; use an isolated instance")
        for vaccine, count in doses_by_vaccine.items():
            self.assertEqual(visible_doses.get(vaccine), count)

        requests_to_send = [
            (token, "/api/reservation/reserve",
             {"json": {"date": day, "vaccine": vaccines[index % vaccine_count]}})
            for index, token in enumerate(tokens)
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
            elif 400 <= result.status_code < 500 and isinstance(result.body, dict):
                message = str(result.body.get("message", "")).lower()
                if "not enough" not in message and "no caregiver" not in message:
                    problems.append(f"unexpected rejection: {message}")
            else:
                problems.append(f"unexpected HTTP {result.status_code} or malformed response")

        print(f"  concurrency round {run + 1}: {len(successes)}/{len(results)} reservations "
              f"in {elapsed:.2f}s", flush=True)
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
            self.client.reserve(first_patient, day, vaccines[0]), first_patient
        )
        self.assertIn(assigned_caregiver, caregiver_names)
        self.cancel_tracked(appointment_id)


if __name__ == "__main__":
    run_module_cli(add_concurrency_arguments, configure_concurrency)
