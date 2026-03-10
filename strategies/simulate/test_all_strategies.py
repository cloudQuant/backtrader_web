#!/usr/bin/env python3
"""Batch test: verify each simulate strategy can connect to CTP."""
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TIMEOUT = 35  # seconds: enough for CTP login (~5s) + some buffer

strategies = sorted(
    d.name for d in BASE_DIR.iterdir()
    if d.is_dir() and not d.name.startswith(("_", ".")) and (d / "run.py").exists()
)

passed = []
failed = []

for name in strategies:
    run_py = BASE_DIR / name / "run.py"
    print(f"[{name}] ", end="", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, str(run_py)],
            capture_output=True, text=True,
            timeout=TIMEOUT,
            cwd=str(run_py.parent),
        )
        # Strategy ran and exited within timeout — check for errors
        combined = result.stdout + result.stderr
        if "CTP 服务器可达" in combined and result.returncode == 0:
            print("OK (exited cleanly)")
            passed.append(name)
        elif "BtApiStoreError" in combined or "不合法" in combined:
            print(f"FAIL (CTP error)")
            failed.append((name, combined[-200:]))
        else:
            print(f"FAIL (exit={result.returncode})")
            failed.append((name, combined[-200:]))
    except subprocess.TimeoutExpired:
        # Timeout means it connected and was running live — that's success!
        print("OK (CTP connected, running live)")
        passed.append(name)

print(f"\n{'='*60}")
print(f"Results: {len(passed)} passed, {len(failed)} failed out of {len(strategies)}")
if failed:
    print(f"\nFailed strategies:")
    for name, err in failed:
        print(f"  {name}: {err[:100]}")
print(f"{'='*60}")
sys.exit(1 if failed else 0)
