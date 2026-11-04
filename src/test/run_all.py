"""Run the offline checks and integration suite against a disposable instance."""

import argparse
import sys
import unittest

import test_auth
import test_concurrency
import test_harness
import test_reservation
from test_config import add_target_arguments, configure_environment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_target_arguments(parser)
    test_concurrency.add_concurrency_arguments(parser)
    parser.add_argument("--skip-concurrency", action="store_true",
                        help="run authentication and reservation integration tests only")
    args = parser.parse_args(argv)
    try:
        settings = configure_environment(args.target, args.timeout)
        test_concurrency.configure_concurrency(args)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"Target: {settings.base_url}")
    print("Tests create unique accounts, availability and inventory; use a disposable instance.", flush=True)
    modules = [test_harness, test_auth, test_reservation]
    if not args.skip_concurrency:
        modules.append(test_concurrency)
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite(loader.loadTestsFromModule(module) for module in modules)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
