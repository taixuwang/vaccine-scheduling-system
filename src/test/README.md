# API test suite

Install the dependencies from the project root with `python3 -m pip install -r requirements.txt`.
Python 3.9 or newer is required.

## Safety and isolation

Integration and load tests create users, vaccine doses, and caregiver availability
through the API. The application has no API to remove those fixtures, so they
remain after the run. Successful test reservations are cancelled when possible.
Use a disposable instance with its own PostgreSQL and Redis: tests select an empty
future date and verify the available caregivers before booking, but cannot
prevent another process from modifying that date concurrently.

The suite never truncates tables or flushes Redis. No test automatically destroys
or resets data. Run `python3 -m unittest discover -s src/test -v` for offline
harness checks; it skips integration tests unless `VACCINE_TEST_BASE_URL` is set.
Fixture setup assumes the disposable instance permits caregiver registration.
For HTTPS targets, use a Python build with a supported OpenSSL version.

## Integration tests

Start a disposable instance first, then run from the project root:

```sh
python3 src/test/run_all.py --target http://localhost
python3 src/test/run_all.py --target http://localhost --skip-concurrency
python3 src/test/test_auth.py --target http://localhost
python3 src/test/test_reservation.py --target http://localhost
python3 src/test/test_concurrency.py --target http://localhost --patients 30 --doses 10 --caregivers 10 --runs 1
```

Each script accepts `--target` and `--timeout` (seconds). The target defaults to
`http://localhost`, or to `VACCINE_TEST_BASE_URL` if set. `VACCINE_TEST_TIMEOUT`
sets the default timeout. For standard unittest discovery, set the base URL
explicitly to enable integration tests:

```sh
VACCINE_TEST_BASE_URL=http://localhost python3 -m unittest discover -s src/test -v
```

The concurrency test defaults to 30 patients, 10 doses, 10 caregivers, and one
run. Patients and caregivers must each be at least the number of doses. Each run
uses up to five new vaccine names and verifies response IDs, caregiver assignments,
capacity per vaccine, cancellation, and rebooking. The suite does not claim to
compare Redis and PostgreSQL directly; it checks their externally visible behavior.

The regression tests assert that logout invalidates a token, negative inventory
updates are rejected, and re-uploading a booked date cannot prevent cancellation.
These cases currently expose known backend defects and are expected to fail
until the application is corrected. Failed cancellation cleanup is also reported;
the affected fixtures may remain in the disposable instance.

## Load test

```sh
python3 src/test/test_throughput.py --target http://localhost --threads 20 --duration 10
```

This opt-in workload reports status counts, request errors, throughput, and
latency percentiles for login, search, appointment listing, and complete
reserve-and-cancel cycles. Temporary capacity rejections in the write workload
are reported separately. Setup and every workload use the same target and timeout.
