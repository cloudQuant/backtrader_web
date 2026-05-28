#!/usr/bin/env python3
"""
Parameter optimization API demo.

This script demonstrates:
1) Register (best-effort)
2) Login (JWT)
3) Pick a strategy template
4) Fetch strategy param specs
5) Submit an optimization task for one parameter
6) Optionally poll progress

Usage:
  python examples/backend_api_optimization_demo.py --base-url http://localhost:8000
  python examples/backend_api_optimization_demo.py --wait --timeout-sec 60
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


def _poll_progress(
    client: httpx.Client,
    headers: dict[str, str],
    task_id: str,
    timeout_sec: int,
    interval_sec: float,
) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        r = client.get(f"/api/v1/optimization/progress/{task_id}", headers=headers)
        if r.status_code == 404:
            print("progress: task not found yet")
        else:
            r.raise_for_status()
            data = r.json()
            print("progress:", data.get("status"), data.get("progress"))
            if data.get("status") in {"completed", "failed", "cancelled"}:
                return
        time.sleep(interval_sec)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", default=f"demo_{uuid.uuid4().hex[:8]}")
    parser.add_argument("--password", default="Test12345678")
    parser.add_argument("--strategy-id", default="")
    parser.add_argument("--param-name", default="")
    parser.add_argument("--start", type=float, default=5)
    parser.add_argument("--end", type=float, default=15)
    parser.add_argument("--step", type=float, default=5)
    parser.add_argument("--type", default="int", choices=["int", "float"])
    parser.add_argument("--n-workers", type=int, default=2)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--interval-sec", type=float, default=2.0)
    args = parser.parse_args(argv)

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        _register(client, args.username, args.password)
        token = _login(client, args.username, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        print("token acquired for:", args.username)

        strategy_id = args.strategy_id or _pick_strategy_id(client, headers)
        print("strategy_id:", strategy_id)

        specs = client.get(f"/api/v1/optimization/strategy-params/{strategy_id}", headers=headers)
        specs.raise_for_status()
        params = specs.json().get("params", [])
        if not params:
            raise RuntimeError("selected template has no params; pass --strategy-id for another template")

        param_name = args.param_name or params[0]["name"]
        print("param_name:", param_name)

        submit = client.post(
            "/api/v1/optimization/submit",
            headers=headers,
            json={
                "strategy_id": strategy_id,
                "param_ranges": {
                    param_name: {
                        "start": args.start,
                        "end": args.end,
                        "step": args.step,
                        "type": args.type,
                    }
                },
                "n_workers": args.n_workers,
            },
        )
        submit.raise_for_status()
        resp = submit.json()
        task_id = resp["task_id"]
        print("task_id:", task_id)
        print("total_combinations:", resp.get("total_combinations"))

        if not args.wait:
            return 0

        _poll_progress(
            client,
            headers=headers,
            task_id=task_id,
            timeout_sec=args.timeout_sec,
            interval_sec=args.interval_sec,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

