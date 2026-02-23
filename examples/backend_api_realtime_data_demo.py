#!/usr/bin/env python3
"""
Backend API realtime data demo.

This script demonstrates:
1) Register and login
2) Subscribe to real-time data feeds
3) Query available data sources
4) Manage data subscriptions

Usage:
  python examples/backend_api_realtime_data_demo.py --base-url http://localhost:8000
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
    parser = argparse.ArgumentParser(description="Realtime data demo")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args(argv)

    username = f"demo_{uuid.uuid4().hex[:8]}"
    password = "Test12345678"

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        token = _register_and_login(client, username, password)
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[OK] Logged in as {username}")

        # Step 1: List available data sources
        sources_resp = client.get("/api/v1/realtime/sources", headers=headers)
        if sources_resp.status_code == 200:
            sources = sources_resp.json()
            print(f"[OK] Available data sources: {json.dumps(sources, indent=2)[:500]}")
        else:
            print(f"[INFO] Data sources endpoint returned {sources_resp.status_code}")

        # Step 2: Create a subscription
        sub_resp = client.post(
            "/api/v1/realtime/subscriptions",
            headers=headers,
            json={
                "symbols": ["000001.SZ", "600519.SH"],
                "data_type": "tick",
                "source": "default",
            },
        )
        if sub_resp.status_code == 200:
            sub = sub_resp.json()
            sub_id = sub.get("id", sub.get("subscription_id", "N/A"))
            print(f"[OK] Created subscription: {sub_id}")
        else:
            print(f"[INFO] Subscription endpoint returned {sub_resp.status_code}: {sub_resp.text[:200]}")

        # Step 3: List active subscriptions
        list_resp = client.get("/api/v1/realtime/subscriptions", headers=headers)
        if list_resp.status_code == 200:
            subs = list_resp.json()
            total = subs.get("total", len(subs)) if isinstance(subs, dict) else len(subs)
            print(f"[OK] Active subscriptions: {total}")
        else:
            print(f"[INFO] List subscriptions returned {list_resp.status_code}")

        # Step 4: Get latest snapshot
        snapshot_resp = client.get(
            "/api/v1/realtime/snapshot",
            headers=headers,
            params={"symbol": "000001.SZ"},
        )
        if snapshot_resp.status_code == 200:
            snapshot = snapshot_resp.json()
            print(f"[OK] Latest snapshot: {json.dumps(snapshot, indent=2)[:300]}")
        else:
            print(f"[INFO] Snapshot endpoint returned {snapshot_resp.status_code}")

    print("\n[DONE] Realtime data demo completed!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
