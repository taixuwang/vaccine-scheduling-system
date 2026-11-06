"""Offline checks for request-context isolation; requires a Java 11+ JDK."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_SOURCE = PROJECT_ROOT / "src/main/java/scheduler/context/UserContext.java"

# UserContext only stores these model objects. Minimal types allow testing the
# production context class without initializing PostgreSQL or Spring.
PROBE = r"""
import scheduler.context.UserContext;
import scheduler.model.Caregiver;
import scheduler.model.Patient;

public class ContextProbe {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        Caregiver caregiver = new Caregiver();
        Patient patient = new Patient();
        UserContext.setCaregiver(caregiver);
        UserContext.setPatient(patient);
        UserContext.setToken("parent");

        Throwable[] failure = new Throwable[1];
        Thread child = new Thread(() -> {
            try {
                check(UserContext.getCaregiver() == null, "caregiver leaked to child");
                check(UserContext.getPatient() == null, "patient leaked to child");
                check(UserContext.getToken() == null, "token leaked to child");
                UserContext.setToken("child");
                UserContext.clear();
                check(UserContext.getToken() == null, "child token was not cleared");
            } catch (Throwable error) {
                failure[0] = error;
            }
        });
        child.start();
        child.join();
        if (failure[0] != null) throw new AssertionError("child failed", failure[0]);
        check(UserContext.getCaregiver() == caregiver, "child changed parent caregiver");
        check(UserContext.getPatient() == patient, "child changed parent patient");
        check("parent".equals(UserContext.getToken()), "child changed parent token");

        UserContext.clear();
        check(UserContext.getCaregiver() == null, "caregiver was not cleared");
        check(UserContext.getPatient() == null, "patient was not cleared");
        check(UserContext.getToken() == null, "token was not cleared");
    }
}
"""


class UserContextTests(unittest.TestCase):
    def test_context_is_thread_local_and_clear_removes_all_values(self):
        java_home = os.environ.get("JAVA_HOME")
        java = str(Path(java_home) / "bin/java") if java_home else shutil.which("java")
        javac = str(Path(java_home) / "bin/javac") if java_home else shutil.which("javac")
        if not java or not javac:
            self.skipTest("Java 11 or newer JDK is required")
        try:
            version = subprocess.run([javac, "-version"], capture_output=True, text=True, timeout=10)
        except FileNotFoundError:
            self.skipTest("Java 11 or newer JDK is required")
        match = re.search(r"\bjavac\s+(\d+)(?:\.(\d+))?", version.stdout + version.stderr)
        if version.returncode != 0 or not match:
            self.skipTest("Java 11 or newer JDK is required")
        major = int(match.group(2)) if match.group(1) == "1" and match.group(2) else int(match.group(1))
        if major < 11:
            self.skipTest("Java 11 or newer JDK is required")

        with tempfile.TemporaryDirectory(prefix="vaccine-context-test-") as temp:
            root = Path(temp)
            sources = []
            for name in ("Caregiver", "Patient"):
                source = root / f"{name}.java"
                source.write_text(f"package scheduler.model; public class {name} {{}}\n")
                sources.append(str(source))
            probe = root / "ContextProbe.java"
            probe.write_text(PROBE)
            subprocess.run([javac, "--release", "11", "-d", temp, str(CONTEXT_SOURCE),
                            *sources, str(probe)], check=True, timeout=30)
            subprocess.run([java, "-cp", temp, "ContextProbe"], check=True, timeout=30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
