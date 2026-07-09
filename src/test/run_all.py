"""
Test Runner
===========
Runs all test suites sequentially and reports a combined summary.

Usage:
  1. Start the application (docker-compose up --build)
  2. Run: python src/test/run_all.py
"""

import subprocess
import sys
import os

TEST_DIR = os.path.dirname(os.path.abspath(__file__))

SUITES = [
    ("Authentication Tests",   "test_auth.py"),
    ("Reservation Flow Tests", "test_reservation.py"),
    ("Concurrency Tests",      "test_concurrency.py"),
]


def main():
    print("=" * 60)
    print("  Vaccine Scheduling System — Full Test Suite")
    print("=" * 60)

    results = []
    for name, script in SUITES:
        print(f"\n{'─'*60}")
        print(f"  Running: {name} ({script})")
        print(f"{'─'*60}")

        script_path = os.path.join(TEST_DIR, script)
        proc = subprocess.run(
            [sys.executable, script_path],
            cwd=os.path.join(TEST_DIR, "..", ".."),  # project root
        )
        passed = proc.returncode == 0
        results.append((name, passed))

    # ── Combined Summary ──
    print("\n" + "=" * 60)
    print("  Combined Results")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        icon = "+" if passed else "-"
        print(f"  [{icon}] {name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n  All test suites passed!\n")
    else:
        print("\n  Some test suites failed.\n")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
