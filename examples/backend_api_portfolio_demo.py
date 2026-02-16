#!/usr/bin/env python3
"""
Portfolio aggregation API demo.

This script demonstrates:
1) Register (best-effort)
2) Login (JWT)
3) Call portfolio endpoints:
   - GET /api/v1/portfolio/overview
   - GET /api/v1/portfolio/positions
   - GET /api/v1/portfolio/trades

Note: These endpoints aggregate live trading logs. If you have no live instances/logs,
you may see empty/zero results.
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
    parser.add_argument("--trades-limit", type=int, default=50)
    args = parser.parse_args(argv)

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        _register(client, args.username, args.password)
        token = _login(client, args.username, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        print("token acquired for:", args.username)

        r = client.get("/api/v1/portfolio/overview", headers=headers)
        r.raise_for_status()
        overview = r.json()
        print("total_assets:", overview.get("total_assets"))
        print("strategy_count:", overview.get("strategy_count"))

        r = client.get("/api/v1/portfolio/positions", headers=headers)
        r.raise_for_status()
        print("positions_total:", r.json().get("total"))

        r = client.get("/api/v1/portfolio/trades", headers=headers, params={"limit": args.trades_limit})
        r.raise_for_status()
        print("trades_total:", r.json().get("total"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

