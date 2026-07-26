#!/usr/bin/env python3
"""Fail when sensitive-looking runtime files are tracked without classification."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


SENSITIVE_PATH_RE = re.compile(
    r"(^|/)(\.env|.*\.env|.*cookies\.json|.*\.(pem|key|p12|jks|db|sqlite|sqlite3|zip))$",
    re.IGNORECASE,
)

ALLOWLIST: dict[str, str] = {
    "src/clientportal.gw/root/demo.zip": "Vendored IBKR Client Portal Gateway demo archive.",
    "src/clientportal.gw/root/vertx.jks": "Vendored IBKR Client Portal Gateway demo keystore.",
}

PLACEHOLDER_REQUIRED: dict[str, str] = {}

IBKR_COOKIES_EXAMPLE = Path("src/bt_api_py/configs/ibkr_cookies.example.json")
IBKR_COOKIE_PLACEHOLDERS = {
    "SBID": "replace-with-local-ibkr-cookie",
    "device.info": "replace-with-local-device-info",
    "TABID": "replace-with-local-ibkr-cookie",
    "XYZAB_AM.LOGIN": "replace-with-local-ibkr-cookie",
    "XYZAB": "replace-with-local-ibkr-cookie",
}


def tracked_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def check_ibkr_cookie_example() -> str | None:
    """Ensure the committed IBKR cookie template cannot contain live credentials."""
    try:
        content = IBKR_COOKIES_EXAMPLE.read_text(encoding="utf-8")
        payload = json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        return f"{IBKR_COOKIES_EXAMPLE} is not a readable JSON example: {exc}"

    if payload != IBKR_COOKIE_PLACEHOLDERS:
        return f"{IBKR_COOKIES_EXAMPLE} must contain only the approved placeholder schema"
    return None


def main() -> int:
    failures: list[str] = []
    candidates = [path for path in tracked_files() if SENSITIVE_PATH_RE.search(path)]

    for path in candidates:
        reason = ALLOWLIST.get(path)
        if not reason:
            failures.append(f"{path} is sensitive-looking and not allowlisted")
            continue

        required = PLACEHOLDER_REQUIRED.get(path)
        if required:
            try:
                content = open(path, encoding="utf-8").read()
            except OSError as exc:
                failures.append(f"{path} could not be read for placeholder check: {exc}")
                continue
            if required not in content:
                failures.append(f"{path} is allowlisted but does not contain placeholder marker")

    ibkr_example_failure = check_ibkr_cookie_example()
    if ibkr_example_failure:
        failures.append(ibkr_example_failure)

    if failures:
        print("Sensitive tracked file check failed:")
        for item in failures:
            print(f"- {item}")
        print("\nAllowlist intentional examples in scripts/ci/check_sensitive_tracked_files.py.")
        return 1

    print(
        f"Sensitive tracked file check passed ({len(candidates)} classified candidate files; "
        "IBKR cookie example validated)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
