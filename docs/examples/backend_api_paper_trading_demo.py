#!/usr/bin/env python3
"""
Paper trading API demo.

This script demonstrates:
1) Register (best-effort)
2) Login (JWT)
3) Create a paper trading account
4) Submit a market order
5) List orders / positions / trades

Usage:
  python examples/backend_api_paper_trading_demo.py --base-url http://localhost:8000
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
    parser.add_argument("--account-name", default="Demo Paper Account")
    parser.add_argument("--symbol", default="000001.SZ")
    parser.add_argument("--size", type=int, default=100)
    args = parser.parse_args(argv)

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        health = client.get("/health")
        health.raise_for_status()
        print("health:", health.json())

        _register(client, args.username, args.password)
        token = _login(client, args.username, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        print("token acquired for:", args.username)

        r = client.post(
            "/api/v1/paper-trading/accounts",
            headers=headers,
            json={
                "name": args.account_name,
                "initial_cash": 100000.0,
                "commission_rate": 0.001,
                "slippage_rate": 0.001,
            },
        )
        r.raise_for_status()
        account = r.json()
        account_id = account["id"]
        print("account_id:", account_id)
        print("total_equity:", account.get("total_equity"))

        r = client.post(
            "/api/v1/paper-trading/orders",
            headers=headers,
            json={
                "account_id": account_id,
                "symbol": args.symbol,
                "order_type": "market",
                "side": "buy",
                "size": args.size,
            },
        )
        r.raise_for_status()
        order = r.json()
        print("order_id:", order["id"])
        print("order_status:", order.get("status"))

        orders = client.get("/api/v1/paper-trading/orders", headers=headers, params={"account_id": account_id})
        orders.raise_for_status()
        print("orders_total:", orders.json().get("total"))

        positions = client.get("/api/v1/paper-trading/positions", headers=headers, params={"account_id": account_id})
        positions.raise_for_status()
        print("positions_total:", positions.json().get("total"))

        trades = client.get("/api/v1/paper-trading/trades", headers=headers, params={"account_id": account_id})
        trades.raise_for_status()
        print("trades_total:", trades.json().get("total"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

