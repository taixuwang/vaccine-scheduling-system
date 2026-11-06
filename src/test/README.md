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
python3 src/test/test_concurrency.py --target http://localhost --patients 1000 --doses 100 --caregivers 100 --runs 10
```

These script entry points default to `VACCINE_TEST_BASE_URL`, or
`http://localhost` if it is unset. They accept `--timeout` in seconds, defaulting
to `VACCINE_TEST_TIMEOUT` or 15 seconds. For standard discovery, explicitly set
the target to enable integration tests:

```sh
VACCINE_TEST_BASE_URL=http://localhost python3 -m unittest discover -s src/test -v
```

The concurrency defaults are 1,000 patients, 100 doses, 100 caregivers, and ten
rounds. All patients compete for the same vaccine in each round. `--patients`
and `--caregivers` must each be at least `--doses`. The
corresponding environment variables are `VACCINE_TEST_PATIENTS`,
`VACCINE_TEST_DOSES`, `VACCINE_TEST_CAREGIVERS`, and `VACCINE_TEST_RUNS`.
Each round checks API-visible capacity,
appointment IDs, caregiver assignments, cancellation, and rebooking. It does
not compare PostgreSQL and Redis directly. The default workload creates 1,100
accounts and 1,000 doses across the ten rounds. Fixture setup can take a long
time because registration and login use password hashing. A 1,000-connection
burst can also hit client or server resource limits or the per-request timeout;
timeouts may leave an appointment whose ID is unknown to the test.

Each round prints the average, P50, P95, P99 and maximum reservation latency in
milliseconds, including unsuccessful attempts. Individual reservation attempts
are saved as CSV in the current directory under a unique
`concurrency-latency-<random>.csv` name. The columns are `round`, `attempt`,
`elapsed_ms`, `http_status` (0 for a transport error), and `error` (the error
type, if any). Cancellation requests are not included. Use `--latency-file` or
`VACCINE_TEST_LATENCY_FILE` to choose a different path; the file is created
exclusively and an existing file will not be overwritten. The path is printed
at the start and each round is flushed before its assertions.

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
