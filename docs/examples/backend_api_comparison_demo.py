#!/usr/bin/env python3
"""
Backend API strategy comparison demo.

This script demonstrates:
1) Register and login
2) Create a strategy with two versions
3) Run backtests on both versions
4) Compare backtest results side-by-side

Usage:
  python examples/backend_api_comparison_demo.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

import httpx


def _register_and_login(client: httpx.Client, username: str, password: str) -> str:
    """Register (best-effort) and login. Returns JWT token."""
    payload = {"username": username, "email": f"{username}@example.com", "password": password}
    client.post("/api/v1/auth/register", json=payload)
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Strategy comparison demo")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args(argv)

    username = f"demo_{uuid.uuid4().hex[:8]}"
    password = "Test12345678"

    with httpx.Client(base_url=args.base_url, timeout=60) as client:
        token = _register_and_login(client, username, password)
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[OK] Logged in as {username}")

        # Step 1: List available strategy templates
        tmpl_resp = client.get("/api/v1/strategy/templates", headers=headers)
        tmpl_resp.raise_for_status()
        templates = tmpl_resp.json().get("templates", [])
        print(f"[OK] Available templates: {len(templates)}")

        if len(templates) < 2:
            print("[SKIP] Need at least 2 templates to compare. Exiting.")
            return 0

        t1 = templates[0]
        t2 = templates[1]
        print(f"  Comparing: '{t1['name']}' vs '{t2['name']}'")

        # Step 2: Create a comparison task
        compare_resp = client.post(
            "/api/v1/comparisons/",
            headers=headers,
            json={
                "name": f"Compare {t1['name']} vs {t2['name']}",
                "description": "Demo comparison of two strategy templates",
                "strategies": [
                    {
                        "strategy_id": t1["id"],
                        "name": t1["name"],
                        "code": t1.get("code", ""),
                        "params": {},
                    },
                    {
                        "strategy_id": t2["id"],
                        "name": t2["name"],
                        "code": t2.get("code", ""),
                        "params": {},
                    },
                ],
                "backtest_config": {
                    "initial_cash": 100000,
                    "commission": 0.001,
                    "start_date": "2023-01-01",
                    "end_date": "2024-01-01",
                },
            },
        )
        if compare_resp.status_code == 200:
            comparison = compare_resp.json()
            print(f"[OK] Created comparison: {comparison.get('id', 'N/A')}")
        else:
            print(f"[INFO] Comparison creation returned {compare_resp.status_code}: {compare_resp.text[:200]}")

        # Step 3: List comparisons
        list_resp = client.get("/api/v1/comparisons/", headers=headers)
        if list_resp.status_code == 200:
            data = list_resp.json()
            total = data.get("total", len(data)) if isinstance(data, dict) else len(data)
            print(f"[OK] Total comparisons: {total}")
        else:
            print(f"[INFO] List comparisons returned {list_resp.status_code}")

    print("\n[DONE] Strategy comparison demo completed!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
