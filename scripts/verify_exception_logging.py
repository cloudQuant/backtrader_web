#!/usr/bin/env python3
"""Verify exception logging improvements."""

import subprocess
import sys

def run_ruff_check():
    """Run Ruff check on modified files."""
    files = [
        "src/backend/app/api/metrics.py",
        "src/backend/app/api/backtest_enhanced.py",
        "src/backend/app/api/paper_trading.py",
    ]
    result = subprocess.run(
        ["ruff", "check"] + files,
        capture_output=True,
        text=True,
    )
    print("Ruff check result:")
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode

def main():
    """Main verification."""
    print("=== Verifying Exception Logging Improvements ===\n")
    
    # Run Ruff check
    ruff_result = run_ruff_check()
    
    if ruff_result == 0:
        print("\n✅ All Ruff checks passed!")
    else:
        print(f"\n❌ Ruff check failed with code {ruff_result}")
        return 1
    
    print("\n=== Verification Complete ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
