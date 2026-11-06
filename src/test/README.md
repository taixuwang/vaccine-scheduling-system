# Test guide

Run the commands below from the repository root. The suite uses Python's
`unittest`, requires Python 3.9+, and uses the packages in `requirements.txt`:

```sh
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
```

Use `venv/bin/python` in place of `python3` in the following commands if using
that virtual environment. The password-hash regression also requires a Java 11+
JDK; it is skipped when a suitable compiler is unavailable. Set
`VACCINE_TEST_JAVA_HOME` (or `JAVA_HOME`) if the JDK is not on `PATH`.

## Test inventory

| File | Purpose | Needs a running API? |
| --- | --- | --- |
| `test_harness.py` | Configuration, HTTP helpers, response parsing, concurrency transport, and load-test bookkeeping. Uses mocks. | No |
| `test_password_hash.py` and `java/scheduler/util/PasswordHashProbe.java` | Compile the Java password utility and check a deterministic PBKDF2 vector, including a hash ending in zero. | No |
| `test_auth.py` | Registration, login, password policy, token validation, and logout. | Yes |
| `test_reservation.py` | Reservation and cancellation, access control, invalid input, availability, and inventory recovery. | Yes |
| `test_concurrency.py` | Concurrent bookings, capacity and assignment invariants, cancellation, and rebooking. | Yes |
| `test_throughput.py` | Opt-in throughput and latency workloads; this is a script, not a `unittest` test case. | Yes |
| `test_config.py` | Shared API client, settings, fixtures, and assertions; not a test suite. | No |
| `run_all.py` | Runs offline, authentication, reservation, and concurrency tests; excludes the load test. | Yes |

## Offline checks

```sh
python3 -m unittest discover -s src/test -v
```

Discovery skips integration test classes unless `VACCINE_TEST_BASE_URL` is set.
The password test reports a separate skip if a suitable JDK is unavailable.
Check the skip messages as well as the final result when interpreting a run.

## Integration tests and isolation

Run against a **disposable instance with its own PostgreSQL and Redis**. Tests
create users, caregiver availability, and vaccine inventory through the API. The
application cannot delete these fixtures, so they remain after the run. The
tests attempt to cancel successful reservations and report cleanup failures;
they never truncate tables or flush Redis. Fixture setup requires caregiver
registration to be enabled. The tests choose a future date with no visible
caregivers, but cannot prevent another process from changing it concurrently.

```sh
python3 src/test/run_all.py --target http://localhost
python3 src/test/run_all.py --target http://localhost --skip-concurrency
python3 src/test/test_auth.py --target http://localhost
python3 src/test/test_reservation.py --target http://localhost
python3 src/test/test_concurrency.py --target http://localhost --patients 30 --doses 10 --caregivers 10 --runs 1
```

These script entry points default to `VACCINE_TEST_BASE_URL`, or
`http://localhost` if it is unset. They accept `--timeout` in seconds, defaulting
to `VACCINE_TEST_TIMEOUT` or 15 seconds. For standard discovery, explicitly set
the target to enable integration tests:

```sh
VACCINE_TEST_BASE_URL=http://localhost python3 -m unittest discover -s src/test -v
```

The concurrency defaults are 30 patients, 10 doses, 10 caregivers, and one
run. `--patients` and `--caregivers` must each be at least `--doses`. The
corresponding environment variables are `VACCINE_TEST_PATIENTS`,
`VACCINE_TEST_DOSES`, `VACCINE_TEST_CAREGIVERS`, and `VACCINE_TEST_RUNS`.
Each round uses up to five vaccine names and checks API-visible capacity,
appointment IDs, caregiver assignments, cancellation, and rebooking. It does
not compare PostgreSQL and Redis directly.

The logout, negative inventory, and booked-date re-upload regressions document
known backend defects and may fail until those defects are fixed. They are not
marked as expected failures: a failure remains visible in the test result.

## Load test

```sh
python3 src/test/test_throughput.py --target http://localhost --threads 20 --duration 10
```

The script runs login, schedule search, appointment listing, and complete
reserve-and-cancel workloads, each for the requested duration. It reports
operations per second, latency percentiles, HTTP statuses, and request errors.
Temporary capacity rejections in the write workload are counted separately.
The script checks for unexpected errors and successful operations, but sets no
performance threshold. Setup and all workloads use the same target and timeout.
For HTTPS targets, use Python linked against a supported OpenSSL version.
