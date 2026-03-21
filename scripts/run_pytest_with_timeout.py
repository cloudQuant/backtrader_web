import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tests", nargs="+", help="pytest targets")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--pytest-args", nargs=argparse.REMAINDER, default=[])
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    cmd = [sys.executable, "-m", "pytest", *args.tests, *args.pytest_args]

    try:
        completed = subprocess.run(cmd, cwd=str(cwd), timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print(f"PYTEST_TIMEOUT {args.timeout}")
        return 124
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
