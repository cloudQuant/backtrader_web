#!/usr/bin/env python3
"""Run backend tests with a bounded wall-clock timeout."""

from pathlib import Path
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_tests():
    """Run pytest with timeout."""
    start_time = time.time()
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "src/backend/tests",
                "-v",
                "--tb=short",
                "-x",
                "-q",
            ],
            cwd=REPO_ROOT,
            timeout=120,
            capture_output=True,
            text=True,
        )
        elapsed = time.time() - start_time
        print(f"Tests completed in {elapsed:.1f}s")
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return result.returncode
    except subprocess.TimeoutExpired:
        print("Tests timed out after 120s")
        return 1
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
