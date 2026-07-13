#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""调试单页：打印所有网络请求/响应、最终URL、console消息，确认登录与API调用。"""
import sys
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"
ADMIN = {"username": "admin", "password": "admin123"}
TARGET = sys.argv[1] if len(sys.argv) > 1 else "/"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000}, locale="zh-CN")

        # UI login
        page = context.new_page()
        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector('input[placeholder="用户名"]', timeout=15000)
        page.fill('input[placeholder="用户名"]', ADMIN["username"])
        page.fill('input[type="password"]', ADMIN["password"])
        page.click('button:has-text("登录")')
        try:
            page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
        except Exception as e:
            print(f"LOGIN FAILED (still on /login): {e}")
            print("Current URL:", page.url)
            print("Page content snippet:", page.content()[:1000])
            browser.close()
            return
        print("LOGIN OK, landed on:", page.url)

        # Now visit target with full logging
        all_requests = []
        all_responses = []
        all_console = []

        def on_request(req):
            if "/api/" in req.url:
                all_requests.append(f"{req.method} {req.url}")

        def on_response(resp):
            if "/api/" in resp.url:
                all_responses.append(f"{resp.status} {resp.url}")

        def on_console(msg):
            all_console.append(f"[{msg.type}] {msg.text[:200]}")

        def on_pageerror(err):
            all_console.append(f"[PAGEERROR] {str(err)[:300]}")

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        page.goto(f"{BASE_URL}{TARGET}", wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

        print(f"\n=== After visiting {TARGET} ===")
        print("Final URL:", page.url)
        print(f"\n--- API Requests ({len(all_requests)}) ---")
        for r in all_requests:
            print(" ", r)
        print(f"\n--- API Responses ({len(all_responses)}) ---")
        for r in all_responses:
            print(" ", r)
        print(f"\n--- Console ({len(all_console)}) ---")
        for c in all_console:
            print(" ", c)
        browser.close()


if __name__ == "__main__":
    main()
