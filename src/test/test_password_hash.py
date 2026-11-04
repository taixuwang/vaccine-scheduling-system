"""Run the Java password-hash regression vector without a database."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
UTIL_SOURCE = PROJECT_ROOT / "src/main/java/scheduler/util/Util.java"
PROBE_SOURCE = PROJECT_ROOT / "src/test/java/scheduler/util/PasswordHashProbe.java"


def java_commands():
    java_home = os.environ.get("VACCINE_TEST_JAVA_HOME") or os.environ.get("JAVA_HOME")
    if java_home:
        return str(Path(java_home) / "bin/java"), str(Path(java_home) / "bin/javac")
    return shutil.which("java"), shutil.which("javac")


class PasswordHashTests(unittest.TestCase):
    def test_pbkdf2_parameters_and_trailing_zero_hash(self):
        java, javac = java_commands()
        if not java or not javac:
            self.skipTest("Java 11 or newer JDK is required")
        try:
            version = subprocess.run([javac, "-version"], capture_output=True, text=True, timeout=10)
        except FileNotFoundError:
            self.skipTest("Java 11 or newer JDK is required")
        if version.returncode != 0:
            self.skipTest("Java 11 or newer JDK is required")

        with tempfile.TemporaryDirectory(prefix="vaccine-password-test-") as output_dir:
            subprocess.run([javac, "--release", "11", "-d", output_dir,
                            str(UTIL_SOURCE), str(PROBE_SOURCE)], check=True, timeout=30)
            subprocess.run([java, "-cp", output_dir, "scheduler.util.PasswordHashProbe"],
                           check=True, timeout=60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
