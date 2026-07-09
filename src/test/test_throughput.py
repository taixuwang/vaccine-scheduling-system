"""
Throughput & Latency Load Test
==============================
A pure-Python load test that hammers endpoints with sustained concurrent
requests and measures throughput (req/s) and latency distribution.

Unlike test_concurrency.py (which validates correctness), this script
focuses purely on PERFORMANCE METRICS under sustained load.

Testing aspects:
  1. Sustained throughput (requests/second) over a configurable duration
  2. Latency distribution: min, avg, p50, p95, p99, max
  3. Error rate under load
  4. Comparison across endpoints (login, search schedule, reserve)
  5. Scalability: how throughput changes as concurrency increases

Usage:
  1. Start the application (docker-compose up --build)
  2. Run: python src/test/test_throughput.py
  3. Optional flags:
     --threads N      Number of concurrent threads (default: 20)
     --duration S     Test duration in seconds per endpoint (default: 10)
     --target URL     Override base URL (default: http://localhost)

Example:
  python src/test/test_throughput.py --threads 50 --duration 15
"""

import sys
import os
import time
import argparse
import threading
import statistics
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from test_config import *


class LoadTestResult:
    """Thread-safe collector for load test metrics."""

    def __init__(self):
        self.lock = threading.Lock()
        self.latencies = []
        self.status_counts = defaultdict(int)
        self.errors = 0
        self.total = 0

    def record(self, latency_ms, status_code):
        with self.lock:
            self.latencies.append(latency_ms)
            self.status_counts[status_code] += 1
            self.total += 1
            if status_code >= 500:
                self.errors += 1

    def report(self, duration_s):
        if not self.latencies:
            print("  No requests completed.")
            return

        self.latencies.sort()
        n = len(self.latencies)

        rps = n / duration_s
        avg = statistics.mean(self.latencies)
        p50 = self.latencies[int(n * 0.50)]
        p95 = self.latencies[int(n * 0.95)]
        p99 = self.latencies[int(n * 0.99)]
        mn = self.latencies[0]
        mx = self.latencies[-1]

        print(f"    Requests:      {n}")
        print(f"    Throughput:    {rps:.1f} req/s")
        print(f"    Latency (ms):  min={mn:.0f}  avg={avg:.0f}  "
              f"p50={p50:.0f}  p95={p95:.0f}  p99={p99:.0f}  max={mx:.0f}")
        print(f"    Status codes:  {dict(self.status_counts)}")
        if self.errors:
            print(f"    5xx errors:    {self.errors} ({self.errors/n*100:.1f}%)")


def run_load_test(name, request_fn, num_threads, duration_s):
    """
    Run a sustained load test by repeatedly calling request_fn from
    num_threads threads for duration_s seconds.
    """
    print(f"\n  [{name}]  threads={num_threads}, duration={duration_s}s")

    result = LoadTestResult()
    stop_event = threading.Event()

    def worker():
        while not stop_event.is_set():
            start = time.time()
            try:
                resp = request_fn()
                latency_ms = (time.time() - start) * 1000
                result.record(latency_ms, resp.status_code)
            except Exception:
                latency_ms = (time.time() - start) * 1000
                result.record(latency_ms, 0)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(num_threads)]

    start_time = time.time()
    for th in threads:
        th.start()

    time.sleep(duration_s)
    stop_event.set()

    for th in threads:
        th.join(timeout=5)

    actual_duration = time.time() - start_time
    result.report(actual_duration)
    return result


def setup_load_test_data(suffix):
    """Create test users and data for load testing."""
    print("\n--- Setup ---")

    # Create a caregiver with availability
    create_caregiver(f"lt_cg_{suffix}")
    cg_token, _ = login_caregiver(f"lt_cg_{suffix}")

    # Add many availability slots and doses
    for day in range(1, 28):
        upload_availability(cg_token, f"2026-10-{day:02d}")
    add_doses(cg_token, "LoadTestVax", 10000)
    logout(cg_token)

    # Create a patient for read-heavy tests
    create_patient(f"lt_pat_{suffix}")
    pat_token, _ = login_patient(f"lt_pat_{suffix}")
    logout(pat_token)

    print("  Setup complete.")
    return suffix


def main():
    parser = argparse.ArgumentParser(description="Throughput load test for vaccine scheduler")
    parser.add_argument("--threads", type=int, default=20, help="Concurrent threads")
    parser.add_argument("--duration", type=int, default=10, help="Seconds per test")
    parser.add_argument("--target", type=str, default=None, help="Override BASE_URL")
    args = parser.parse_args()

    if args.target:
        global BASE_URL
        BASE_URL = args.target

    suffix = random_suffix()

    print("=" * 60)
    print("  Throughput & Latency Load Test")
    print(f"  Target: {BASE_URL}")
    print(f"  Threads: {args.threads}  |  Duration: {args.duration}s per endpoint")
    print("=" * 60)

    try:
        setup_load_test_data(suffix)
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Cannot connect to {BASE_URL}. Is the application running?")
        sys.exit(1)

    # ── Test 1: Login throughput ──────────────────────────────────────────
    # Measures auth overhead (password hashing + JWT generation)
    print("\n" + "─" * 60)
    print("  Test 1: Login Throughput")
    print("  Aspect: Password hashing (PBKDF2) + JWT generation speed")
    print("─" * 60)

    run_load_test(
        name="POST /api/auth/login_patient",
        request_fn=lambda: requests.post(
            f"{BASE_URL}/api/auth/login_patient",
            json={"username": f"lt_pat_{suffix}", "password": "Test@123!"}
        ),
        num_threads=args.threads,
        duration_s=args.duration
    )

    # ── Test 2: Search schedule throughput (read-heavy) ──────────────────
    # Measures DB read performance under load
    print("\n" + "─" * 60)
    print("  Test 2: Search Schedule Throughput (Read-Heavy)")
    print("  Aspect: PostgreSQL read performance + connection pool behavior")
    print("─" * 60)

    pat_token, _ = login_patient(f"lt_pat_{suffix}")

    run_load_test(
        name="POST /api/reservation/search_caregiver_schedule",
        request_fn=lambda: requests.post(
            f"{BASE_URL}/api/reservation/search_caregiver_schedule",
            json={"date": "2026-10-15"},
            headers=auth_header(pat_token)
        ),
        num_threads=args.threads,
        duration_s=args.duration
    )

    logout(pat_token)

    # ── Test 3: Show appointments throughput (read-heavy) ────────────────
    print("\n" + "─" * 60)
    print("  Test 3: Show Appointments Throughput (Read-Heavy)")
    print("  Aspect: Simple DB query throughput under connection pool pressure")
    print("─" * 60)

    pat_token, _ = login_patient(f"lt_pat_{suffix}")

    run_load_test(
        name="GET /api/reservation/show_appointments",
        request_fn=lambda: requests.get(
            f"{BASE_URL}/api/reservation/show_appointments",
            headers=auth_header(pat_token)
        ),
        num_threads=args.threads,
        duration_s=args.duration
    )

    logout(pat_token)

    # ── Test 4: Reserve throughput (write-heavy) ─────────────────────────
    # Measures the full reservation path: Redis DECR → DB transaction → commit
    print("\n" + "─" * 60)
    print("  Test 4: Reserve Throughput (Write-Heavy)")
    print("  Aspect: Redis DECR + PostgreSQL FOR UPDATE + transaction commit")
    print("  Note: Many requests will fail (no caregiver / duplicate patient)")
    print("─" * 60)

    # Create many patients for write test
    write_tokens = []
    for i in range(min(args.threads, 50)):
        name = f"lt_wpat{i}_{suffix}"
        create_patient(name)
        tok, _ = login_patient(name)
        write_tokens.append(tok)
        logout(tok)

    token_idx = [0]
    token_lock = threading.Lock()

    def reserve_request():
        with token_lock:
            tok = write_tokens[token_idx[0] % len(write_tokens)]
            token_idx[0] += 1
        return requests.post(
            f"{BASE_URL}/api/reservation/reserve",
            json={"date": "2026-10-15", "vaccine": "LoadTestVax"},
            headers=auth_header(tok)
        )

    run_load_test(
        name="POST /api/reservation/reserve",
        request_fn=reserve_request,
        num_threads=args.threads,
        duration_s=args.duration
    )

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Load test complete.")
    print("  Compare results across endpoints to identify bottlenecks.")
    print("  Typical bottleneck order: reserve > login > search > show")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
