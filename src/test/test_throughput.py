"""Opt-in load test for a disposable API instance.

The write workload measures complete reserve-and-cancel cycles so that it does
not silently turn into a benchmark of out-of-stock rejections after one request.
"""

import argparse
import math
import secrets
import statistics
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass

import requests

from test_config import (
    ApiClient,
    Settings,
    add_target_arguments,
    empty_future_date,
    positive_float,
    positive_int,
    require_rejection,
    require_status,
    reservation_details,
    schedule_sections,
)


class LoadTestResult:
    def __init__(self):
        self.lock = threading.Lock()
        self.latencies = []
        self.status_counts = Counter()
        self.transport_errors = 0
        self.error_samples = []

    def record(self, latency_ms, status_code=None, error=None):
        with self.lock:
            self.latencies.append(latency_ms)
            if error is not None:
                self.transport_errors += 1
                if len(self.error_samples) < 3:
                    self.error_samples.append(str(error))
            else:
                self.status_counts[status_code] += 1

    def report(self, elapsed):
        count = len(self.latencies)
        if not count:
            print("    No requests completed.")
            return
        ordered = sorted(self.latencies)

        def percentile(fraction):
            return ordered[max(0, math.ceil(count * fraction) - 1)]

        print(f"    Completed:     {count} ({count / elapsed:.1f} operations/s)")
        print(f"    Latency (ms):  avg={statistics.mean(ordered):.1f} "
              f"p50={percentile(.50):.1f} p95={percentile(.95):.1f} "
              f"p99={percentile(.99):.1f} max={ordered[-1]:.1f}")
        print(f"    HTTP statuses: {dict(sorted(self.status_counts.items()))}")
        print(f"    Request errors: {self.transport_errors}")
        for sample in self.error_samples:
            print(f"      {sample}")

    def passed(self, allow_rejections=False):
        success = sum(count for status, count in self.status_counts.items() if 200 <= status < 300)
        unexpected = sum(
            count for status, count in self.status_counts.items()
            if not 200 <= status < 300 and not (allow_rejections and 400 <= status < 500)
        )
        return bool(success) and not self.transport_errors and not unexpected


def run_load_test(name, settings, operation, num_threads, duration, allow_rejections=False):
    print(f"\n  [{name}] threads={num_threads}, duration={duration:g}s", flush=True)
    result = LoadTestResult()
    start_event = threading.Event()
    deadline = [0.0]

    def worker(index):
        try:
            client = ApiClient(settings)
        except Exception as exc:
            result.record(0, error=f"worker setup: {type(exc).__name__}: {exc}")
            return
        try:
            start_event.wait()
            while time.monotonic() < deadline[0]:
                started = time.monotonic()
                try:
                    response = operation(client, index)
                    result.record((time.monotonic() - started) * 1000, response.status_code)
                except Exception as exc:
                    result.record((time.monotonic() - started) * 1000,
                                  error=f"{type(exc).__name__}: {exc}")
        finally:
            client.close()

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(num_threads)]
    try:
        for thread in threads:
            thread.start()
    except RuntimeError:
        start_event.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join()
        raise
    started = time.monotonic()
    deadline[0] = started + duration
    start_event.set()
    for thread in threads:
        thread.join()
    result.report(time.monotonic() - started)
    return result.passed(allow_rejections=allow_rejections)


@dataclass
class LoadFixture:
    day: str
    vaccine: str
    patient_names: list
    patient_tokens: list


def setup_load_test_data(settings, num_threads):
    client = ApiClient(settings)
    suffix = secrets.token_hex(8)
    try:
        patient_names = []
        patient_tokens = []
        for index in range(num_threads):
            name = f"load_patient{index}_{suffix}"
            require_status(client.create("patient", name), 200, "create load-test patient")
            patient_names.append(name)
            patient_tokens.append(client.login("patient", name))
        day = empty_future_date(client, patient_tokens[0])
        caregiver_names = set()
        caregiver_tokens = []
        for index in range(num_threads):
            name = f"load_caregiver{index}_{suffix}"
            require_status(client.create("caregiver", name), 200, "create load-test caregiver")
            token = client.login("caregiver", name)
            require_status(client.upload_availability(token, day), 200, "upload availability")
            caregiver_names.add(name)
            caregiver_tokens.append(token)
        vaccine = f"load_vaccine_{suffix}"
        require_status(client.add_doses(caregiver_tokens[0], vaccine, num_threads),
                       200, "add load-test doses")
        available, vaccines = schedule_sections(client.search(patient_tokens[0], day))
        if available != caregiver_names or vaccines.get(vaccine) != num_threads:
            raise AssertionError("test fixtures are not isolated; use a disposable instance")
        return LoadFixture(day, vaccine, patient_names, patient_tokens)
    finally:
        client.close()


def reserve_and_cancel(client, fixture, index):
    token = fixture.patient_tokens[index]
    response = client.reserve(token, fixture.day, fixture.vaccine)
    if response.status_code != 200:
        body = require_rejection(response, "reserve during load test")
        message = str(body.get("message", "")).lower()
        if "not enough" not in message and "no caregiver" not in message:
            raise AssertionError(f"unexpected reservation rejection: {message}")
        return response
    appointment_id, _ = reservation_details(response)
    try:
        cancelled = client.cancel(token, appointment_id)
        require_status(cancelled, 200, f"cancel load-test appointment {appointment_id}")
        return cancelled
    except (requests.RequestException, AssertionError) as exc:
        raise RuntimeError(f"appointment {appointment_id} could not be cancelled: {exc}") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description="Load test a disposable vaccine scheduler instance")
    add_target_arguments(parser)
    parser.add_argument("--threads", type=positive_int, default=20)
    parser.add_argument("--duration", type=positive_float, default=10.0,
                        help="seconds per workload (default: %(default)s)")
    args = parser.parse_args(argv)
    try:
        settings = Settings(args.target, args.timeout)
        print(f"Target: {settings.base_url}; creating unique test accounts and inventory.", flush=True)
        fixture = setup_load_test_data(settings, args.threads)
        workloads = [
            ("login", lambda client, i: client.login_response("patient", fixture.patient_names[i]), False),
            ("search schedule", lambda client, i: client.search(fixture.patient_tokens[i], fixture.day), False),
            ("show appointments", lambda client, i: client.appointments(fixture.patient_tokens[i]), False),
            ("reserve and cancel cycle", lambda client, i: reserve_and_cancel(client, fixture, i), True),
        ]
        passed = True
        for name, operation, allow_rejections in workloads:
            outcome = run_load_test(name, settings, operation, args.threads, args.duration, allow_rejections)
            passed = outcome and passed
        if not passed:
            print("\nOne or more workloads had unexpected errors or no successful operations.")
        return 0 if passed else 1
    except (requests.RequestException, AssertionError, RuntimeError, ValueError) as exc:
        print(f"Load test failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
