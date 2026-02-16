#!/usr/bin/env python3
"""
Enhanced backtest API demo.

This script demonstrates:
1) Register (best-effort)
2) Login (JWT)
3) Submit an enhanced backtest task
4) Optionally poll status until completion

Usage:
  python examples/backend_api_enhanced_backtest_demo.py --base-url http://localhost:8000
  python examples/backend_api_enhanced_backtest_demo.py --wait --timeout-sec 300
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid

import httpx


def _register(client: httpx.Client, username: str, password: str) -> None:
    payload = {"username": username, "email": f"{username}@example.com", "password": password}
    r = client.post("/api/v1/auth/register", json=payload)
    # May fail if user already exists; accept common conflict/validation statuses.
    if r.status_code not in (200, 201, 400, 409):
        r.raise_for_status()


def _login(client: httpx.Client, username: str, password: str) -> str:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError(f"login succeeded but access_token missing: {r.text}")
    return token


def _pick_strategy_id(client: httpx.Client, headers: dict[str, str]) -> str:
    r = client.get("/api/v1/strategy/templates", headers=headers)
    r.raise_for_status()
    templates = r.json().get("templates", [])
    if not templates:
        raise RuntimeError("no strategy templates found")
    return templates[0]["id"]


def _poll_status(
    client: httpx.Client,
    headers: dict[str, str],
    task_id: str,
    timeout_sec: int,
    interval_sec: float,
) -> str:
    deadline = time.time() + timeout_sec
    last_status = "unknown"
    while time.time() < deadline:
        r = client.get(f"/api/v1/backtests/{task_id}/status", headers=headers)
        r.raise_for_status()
        last_status = r.json().get("status", "unknown")
        print("status:", last_status)
        if last_status in {"completed", "failed", "cancelled"}:
            return last_status
        time.sleep(interval_sec)
    return last_status


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", default=f"demo_{uuid.uuid4().hex[:8]}")
    parser.add_argument("--password", default="Test12345678")
    parser.add_argument("--strategy-id", default="")
    parser.add_argument("--symbol", default="000001.SZ")
    parser.add_argument("--start", default="2023-01-01T00:00:00")
    parser.add_argument("--end", default="2023-12-31T00:00:00")
    parser.add_argument("--initial-cash", type=float, default=100000.0)
    parser.add_argument("--commission", type=float, default=0.001)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--interval-sec", type=float, default=2.0)
    args = parser.parse_args(argv)

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        health = client.get("/health")
        health.raise_for_status()
        print("health:", health.json())

        _register(client, args.username, args.password)
        token = _login(client, args.username, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        print("token acquired for:", args.username)

        strategy_id = args.strategy_id or _pick_strategy_id(client, headers)
        print("strategy_id:", strategy_id)

        payload = {
            "strategy_id": strategy_id,
            "symbol": args.symbol,
            "start_date": args.start,
            "end_date": args.end,
            "initial_cash": args.initial_cash,
            "commission": args.commission,
            "params": {},
        }
        r = client.post("/api/v1/backtests/run", headers=headers, json=payload)
        r.raise_for_status()
        resp = r.json()
        task_id = resp["task_id"]
        print("task_id:", task_id)
        print("initial status:", resp.get("status"))

        if not args.wait:
            print("tip: re-run with --wait to poll status, then GET the result:")
            print(f"  GET /api/v1/backtests/{task_id}")
            print(f"  GET /api/v1/backtests/{task_id}/report/html")
            return 0

        final_status = _poll_status(
            client,
            headers=headers,
            task_id=task_id,
            timeout_sec=args.timeout_sec,
            interval_sec=args.interval_sec,
        )

        if final_status != "completed":
            print("final status:", final_status)
            return 0

        result = client.get(f"/api/v1/backtests/{task_id}", headers=headers)
        result.raise_for_status()
        data = result.json()
        print("result keys:", sorted(data.keys()))
        print("total_return:", data.get("total_return"))
        print("sharpe_ratio:", data.get("sharpe_ratio"))
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

