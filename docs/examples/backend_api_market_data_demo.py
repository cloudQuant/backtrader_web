#!/usr/bin/env python3
"""
Market data API demo (AkShare-backed).

This script demonstrates:
1) Register (best-effort)
2) Login (JWT)
3) Fetch A-share kline data via /api/v1/data/kline

Usage:
  python examples/backend_api_market_data_demo.py --base-url http://localhost:8000
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
    parser.add_argument("--symbol", default="000001.SZ")
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date", default="2023-03-31")
    parser.add_argument("--period", default="daily", choices=["daily", "weekly", "monthly"])
    args = parser.parse_args(argv)

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        health = client.get("/health")
        health.raise_for_status()
        print("health:", health.json())

        _register(client, args.username, args.password)
        token = _login(client, args.username, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        print("token acquired for:", args.username)

        r = client.get(
            "/api/v1/data/kline",
            headers=headers,
            params={
                "symbol": args.symbol,
                "start_date": args.start_date,
                "end_date": args.end_date,
                "period": args.period,
            },
        )
        r.raise_for_status()
        data = r.json()
        print("symbol:", data.get("symbol"))
        print("count:", data.get("count"))
        records = data.get("records", [])
        if records:
            print("first:", records[0])
            print("last:", records[-1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

