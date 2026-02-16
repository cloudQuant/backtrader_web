#!/usr/bin/env python3
"""
Monitoring/alerts API demo.

This script demonstrates:
1) Register (best-effort)
2) Login (JWT)
3) Create an alert rule
4) Fetch the rule by id
5) List rules and alerts
6) Delete the rule

Usage:
  python examples/backend_api_monitoring_demo.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import sys
import uuid

import httpx


def _register(client: httpx.Client, username: str, password: str) -> None:
    payload = {"username": username, "email": f"{username}@example.com", "password": password}
    r = client.post("/api/v1/auth/register", json=payload)
    if r.status_code not in (200, 201, 400, 409):
        r.raise_for_status()


def _login(client: httpx.Client, username: str, password: str) -> str:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError(f"login succeeded but access_token missing: {r.text}")
    return token


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", default=f"demo_{uuid.uuid4().hex[:8]}")
    parser.add_argument("--password", default="Test12345678")
    args = parser.parse_args(argv)

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        _register(client, args.username, args.password)
        token = _login(client, args.username, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        print("token acquired for:", args.username)

        create = client.post(
            "/api/v1/monitoring/rules",
            headers=headers,
            json={
                "name": "Demo Alert Rule",
                "description": "Demo rule created by examples/backend_api_monitoring_demo.py",
                "alert_type": "account",
                "severity": "warning",
                "trigger_type": "threshold",
                "trigger_config": {"threshold": 0.1},
                "notification_enabled": True,
                "notification_channels": ["web"],
            },
        )
        create.raise_for_status()
        rule = create.json()
        rule_id = rule["id"]
        print("created rule_id:", rule_id)

        r = client.get(f"/api/v1/monitoring/rules/{rule_id}", headers=headers)
        r.raise_for_status()
        print("get rule ok:", r.json().get("name"))

        r = client.get("/api/v1/monitoring/rules", headers=headers)
        r.raise_for_status()
        print("rules total:", r.json().get("total"))

        r = client.get("/api/v1/monitoring/", headers=headers)
        r.raise_for_status()
        print("alerts total:", r.json().get("total"))

        r = client.delete(f"/api/v1/monitoring/rules/{rule_id}", headers=headers)
        r.raise_for_status()
        print("deleted rule_id:", rule_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

