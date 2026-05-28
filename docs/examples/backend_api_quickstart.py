#!/usr/bin/env python3
"""
Backend API quickstart demo.

This script demonstrates:
1) Register (best-effort)
2) Login (JWT)
3) Call a protected endpoint (strategy templates)

Usage:
  python examples/backend_api_quickstart.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import sys
import uuid

import httpx


def _register(client: httpx.Client, username: str, password: str) -> None:
    # Registration may fail if the user already exists; this is fine for a demo script.
    payload = {"username": username, "email": f"{username}@example.com", "password": password}
    try:
        r = client.post("/api/v1/auth/register", json=payload)
        if r.status_code not in (200, 201, 400, 409):
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"register failed: {e}") from e


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
        # Public endpoints
        health = client.get("/health")
        health.raise_for_status()
        print("health:", health.json())

        _register(client, args.username, args.password)
        token = _login(client, args.username, args.password)
        print("token acquired for:", args.username)

        # Protected endpoint
        headers = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/v1/strategy/templates", headers=headers)
        r.raise_for_status()
        data = r.json()
        templates = data.get("templates", [])
        print("templates:", len(templates))
        if templates:
            t0 = templates[0]
            print("first template id:", t0.get("id"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

