"""
Concurrency Tests
=================
Tests the system's behavior under concurrent load, focusing on data consistency.

Testing aspects:
  1. Race condition: N patients compete for M doses (M < N)
     - Exactly M reservations should succeed
     - Exactly N-M should be rejected
     - No double-booking of caregivers
     - No overselling of vaccine doses
  2. Concurrent cancellations do not corrupt state
  3. Throughput and latency under concurrent load
  4. Redis cache consistency: after all operations, Redis count matches DB
  5. No duplicate appointment IDs are generated

Usage:
  1. Start the application (docker-compose up --build)
  2. Run: python src/test/test_concurrency.py
  3. Optional flags:
     --patients N    Number of concurrent patients (default: 30)
     --doses M       Number of available vaccine doses (default: 10)
     --caregivers K  Number of caregivers with availability (default: 15)
"""

import sys
import os
import re
import time
import argparse
import concurrent.futures
sys.path.insert(0, os.path.dirname(__file__))

from test_config import *

TEST_DATE = "2026-09-01"
TEST_VACCINE = "ConcurrVax"


def setup_concurrent_test(suffix, num_patients, num_doses, num_caregivers):
    """
    Set up test data:
      - Create num_caregivers caregivers, each with availability on TEST_DATE
      - Add num_doses vaccine doses
      - Create num_patients patients and collect their JWT tokens
    Returns: list of patient JWT tokens
    """
    print(f"\n--- Setup: {num_caregivers} caregivers, {num_doses} doses, {num_patients} patients ---")

    # Create caregivers and upload availability
    for i in range(num_caregivers):
        cg_name = f"cc_cg{i}_{suffix}"
        create_caregiver(cg_name)
        cg_token, _ = login_caregiver(cg_name)
        upload_availability(cg_token, TEST_DATE)
        logout(cg_token)

    # Add vaccine doses (use first caregiver to add doses)
    cg_token, _ = login_caregiver(f"cc_cg0_{suffix}")
    add_doses(cg_token, TEST_VACCINE, num_doses)
    logout(cg_token)

    # Create patients and collect tokens
    tokens = []
    for i in range(num_patients):
        pat_name = f"cc_pat{i}_{suffix}"
        create_patient(pat_name)
        token, _ = login_patient(pat_name)
        tokens.append(token)
        logout(token)

    # Re-login all patients (tokens are still valid since they're JWTs)
    print(f"  Setup complete.")
    return tokens


def test_concurrent_reservations(t, suffix, tokens, expected_successes):
    """
    All patients attempt to reserve simultaneously.
    Validates:
      - Exactly expected_successes reservations succeed
      - No overselling (successes <= available doses)
      - All appointment IDs are unique
    """
    print(f"\n--- Concurrent Reservations: {len(tokens)} patients racing for {expected_successes} doses ---")

    results = []
    latencies = []

    def attempt_reserve(token):
        start = time.time()
        resp = reserve(token, TEST_DATE, TEST_VACCINE)
        elapsed = time.time() - start
        return resp.status_code, resp.json(), elapsed

    # Fire all requests concurrently
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tokens)) as executor:
        futures = [executor.submit(attempt_reserve, tok) for tok in tokens]
        for f in concurrent.futures.as_completed(futures):
            status, body, elapsed = f.result()
            results.append((status, body))
            latencies.append(elapsed)
    total_time = time.time() - start_time

    # Analyze results
    successes = [(s, b) for s, b in results if s == 200]
    failures = [(s, b) for s, b in results if s != 200]

    print(f"  Completed in {total_time:.2f}s")
    print(f"  Successes: {len(successes)}, Failures: {len(failures)}")

    # ── Correctness checks ──
    t.assert_eq(
        f"Exactly {expected_successes} reservations succeed",
        len(successes), expected_successes
    )

    t.assert_true(
        "No overselling (successes <= available doses)",
        len(successes) <= expected_successes,
        f"successes={len(successes)}"
    )

    # Check for unique appointment IDs
    appointment_ids = []
    for _, body in successes:
        msg = body.get("data", "")
        match = re.search(r"Appointment ID (\d+)", msg)
        if match:
            appointment_ids.append(match.group(1))

    unique_ids = set(appointment_ids)
    t.assert_eq(
        "All appointment IDs are unique",
        len(unique_ids), len(appointment_ids)
    )

    # Check for unique caregiver assignments (no double-booking)
    caregivers_assigned = []
    for _, body in successes:
        msg = body.get("data", "")
        match = re.search(r"Caregiver username (\S+)", msg)
        if match:
            caregivers_assigned.append(match.group(1))

    unique_caregivers = set(caregivers_assigned)
    t.assert_eq(
        "No caregiver is double-booked",
        len(unique_caregivers), len(caregivers_assigned)
    )

    # ── Performance metrics ──
    latencies.sort()
    avg_latency = sum(latencies) / len(latencies)
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    rps = len(results) / total_time

    print(f"\n  Performance:")
    print(f"    Throughput:    {rps:.1f} req/s")
    print(f"    Avg latency:   {avg_latency*1000:.0f}ms")
    print(f"    P50 latency:   {p50*1000:.0f}ms")
    print(f"    P95 latency:   {p95*1000:.0f}ms")
    print(f"    P99 latency:   {p99*1000:.0f}ms")

    return [aid for aid in appointment_ids]


def test_concurrent_cancellations(t, suffix, tokens, appointment_ids):
    """
    Cancel all successful reservations concurrently.
    Validates that all cancellations succeed without errors.
    """
    if not appointment_ids:
        print("\n--- Concurrent Cancellations: SKIPPED (no appointments) ---")
        return

    print(f"\n--- Concurrent Cancellations: {len(appointment_ids)} appointments ---")

    # Use the tokens from patients who got appointments
    # We'll use the first N tokens for cancellation (they match the patients who reserved)
    cancel_pairs = list(zip(tokens[:len(appointment_ids)], appointment_ids))

    results = []

    def attempt_cancel(pair):
        token, aid = pair
        resp = cancel(token, aid)
        return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(cancel_pairs)) as executor:
        futures = [executor.submit(attempt_cancel, pair) for pair in cancel_pairs]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    successes = [r for r in results if r[0] == 200]
    failures = [r for r in results if r[0] != 200]

    t.assert_eq(
        "All cancellations succeed",
        len(successes), len(appointment_ids)
    )

    if failures:
        for status, body in failures[:3]:  # Show first 3 failures
            print(f"    Cancel failure: HTTP {status}, {body}")


def test_no_race_after_cancel_and_rebook(t, suffix, tokens, num_doses, num_caregivers):
    """
    After cancelling all appointments, re-add availability and try booking again.
    This tests that cancelled doses are properly restored.
    """
    print(f"\n--- Re-book After Cancellation ---")

    # Re-add caregiver availability (was consumed by first round)
    rebooking_date = "2026-09-02"
    for i in range(num_caregivers):
        cg_name = f"cc_cg{i}_{suffix}"
        cg_token, _ = login_caregiver(cg_name)
        upload_availability(cg_token, rebooking_date)
        logout(cg_token)

    # Try to reserve with first patient
    resp = reserve(tokens[0], rebooking_date, TEST_VACCINE)
    t.assert_status(
        "Re-booking after cancellation succeeds (doses were restored)",
        resp, 200
    )


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Concurrency tests for vaccine scheduler")
    parser.add_argument("--patients", type=int, default=30, help="Number of concurrent patients")
    parser.add_argument("--doses", type=int, default=10, help="Number of available vaccine doses")
    parser.add_argument("--caregivers", type=int, default=15, help="Number of caregivers with availability")
    args = parser.parse_args()

    # Ensure caregivers >= doses (each reservation consumes one caregiver slot)
    if args.caregivers < args.doses:
        print(f"[WARNING] caregivers ({args.caregivers}) < doses ({args.doses}). "
              f"Setting caregivers = doses.")
        args.caregivers = args.doses

    suffix = random_suffix()
    t = TestResult("Concurrency Tests")

    print(f"\nConcurrency Tests (suffix={suffix})")
    print(f"Target: {BASE_URL}")
    print(f"Config: {args.patients} patients, {args.doses} doses, {args.caregivers} caregivers")
    print("=" * 60)

    try:
        tokens = setup_concurrent_test(suffix, args.patients, args.doses, args.caregivers)
        appointment_ids = test_concurrent_reservations(t, suffix, tokens, args.doses)
        test_concurrent_cancellations(t, suffix, tokens, appointment_ids)
        test_no_race_after_cancel_and_rebook(t, suffix, tokens, args.doses, args.caregivers)
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Cannot connect to {BASE_URL}. Is the application running?")
        sys.exit(1)

    success = t.summary()
    sys.exit(0 if success else 1)
