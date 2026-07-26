#!/usr/bin/env python3
"""
Backend API strategy version control demo.

This script demonstrates:
1) Register and login
2) Create a user strategy
3) Create strategy versions
4) List versions
5) Compare two versions
6) Create a branch
7) Rollback to a previous version

Usage:
  python examples/backend_api_strategy_version_demo.py --base-url http://localhost:8000
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
    parser = argparse.ArgumentParser(description="Strategy version control demo")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args(argv)

    username = f"demo_{uuid.uuid4().hex[:8]}"
    password = "Test12345678"

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        token = _register_and_login(client, username, password)
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[OK] Logged in as {username}")

        # Step 1: Create a user strategy
        strat_resp = client.post(
            "/api/v1/strategy/",
            headers=headers,
            json={
                "name": "SMA Crossover",
                "description": "Simple SMA crossover strategy",
                "code": "class SMA(bt.Strategy):\n    pass\n",
                "params": {},
                "category": "trend",
            },
        )
        strat_resp.raise_for_status()
        strategy_id = strat_resp.json()["id"]
        print(f"[OK] Created strategy: {strategy_id}")

        # Step 2: Create version v1.0.0
        v1_resp = client.post(
            "/api/v1/strategy-versions/versions",
            headers=headers,
            json={
                "strategy_id": strategy_id,
                "version_name": "v1.0.0",
                "code": "class SMA(bt.Strategy):\n    params = (('fast', 10), ('slow', 30))\n",
                "params": {"fast": 10, "slow": 30},
                "branch": "main",
                "tags": ["initial"],
                "changelog": "Initial release",
                "is_default": True,
            },
        )
        v1_resp.raise_for_status()
        v1_id = v1_resp.json()["id"]
        print(f"[OK] Created version v1.0.0: {v1_id}")

        # Step 3: Create version v1.1.0 with updated params
        v2_resp = client.post(
            "/api/v1/strategy-versions/versions",
            headers=headers,
            json={
                "strategy_id": strategy_id,
                "version_name": "v1.1.0",
                "code": "class SMA(bt.Strategy):\n    params = (('fast', 5), ('slow', 20))\n",
                "params": {"fast": 5, "slow": 20},
                "branch": "main",
                "tags": ["latest"],
                "changelog": "Tuned parameters for better performance",
                "is_default": False,
            },
        )
        v2_resp.raise_for_status()
        v2_id = v2_resp.json()["id"]
        print(f"[OK] Created version v1.1.0: {v2_id}")

        # Step 4: List all versions
        list_resp = client.get(
            f"/api/v1/strategy-versions/strategies/{strategy_id}/versions",
            headers=headers,
        )
        list_resp.raise_for_status()
        versions = list_resp.json()
        print(f"[OK] Listed versions: total={versions['total']}")

        # Step 5: Compare two versions
        compare_resp = client.post(
            "/api/v1/strategy-versions/versions/compare",
            headers=headers,
            json={
                "strategy_id": strategy_id,
                "from_version_id": v1_id,
                "to_version_id": v2_id,
                "comparison_type": "code",
            },
        )
        compare_resp.raise_for_status()
        comparison = compare_resp.json()
        print(f"[OK] Compared versions: comparison_id={comparison.get('comparison_id')}")

        # Step 6: Create a feature branch
        branch_resp = client.post(
            "/api/v1/strategy-versions/branches",
            headers=headers,
            json={
                "strategy_id": strategy_id,
                "branch_name": "feature/adaptive-sma",
                "parent_branch": "main",
            },
        )
        branch_resp.raise_for_status()
        branch = branch_resp.json()
        print(f"[OK] Created branch: {branch['branch_name']}")

        # Step 7: Rollback to v1.0.0
        rollback_resp = client.post(
            "/api/v1/strategy-versions/versions/rollback",
            headers=headers,
            json={
                "strategy_id": strategy_id,
                "target_version_id": v1_id,
                "reason": "v1.1.0 had worse performance in testing",
            },
        )
        rollback_resp.raise_for_status()
        rolled_back = rollback_resp.json()
        print(f"[OK] Rolled back to v1.0.0, new version: {rolled_back['id']}")

    print("\n[DONE] Strategy version control demo completed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
