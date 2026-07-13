#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
页面遍历错误探测脚本

通过 Playwright 模拟浏览器登录后，遍历所有前端页面路由，捕获：
- 浏览器 console 错误/警告
- 未捕获的页面异常 (pageerror)
- 网络 API 4xx/5xx 响应

输出每个页面的错误汇总，用于定位需要修复的 bug。

Usage:
    python tests/e2e/explore_pages.py
    python tests/e2e/explore_pages.py --headed
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"
ADMIN = {"username": "admin", "password": "admin123"}

# 所有实际渲染组件的路由（排除 redirect）
PAGES = [
    "/login",
    "/register",
    "/",                          # Dashboard
    "/investment/strategies",
    "/investment/stock-analysis",
    "/research/strategies",
    "/research/workspaces",
    "/research/backtests/legacy",
    "/research/tools",
    "/ai/chat",
    "/ai/knowledge-base",
    "/config/data/scripts",
    "/config/data/tasks",
    "/config/data/executions",
    "/config/data/sync",
    "/config/data/interfaces",
    "/config/data/governance",
    "/config/data/airflow",
    "/config/ai/providers",
    "/config/ai/prompt-governance",
    "/config/ai/observability",
    "/config/gateways",
    "/ai-trading",
    "/backtest",
    "/backtest/legacy",
    "/data/market",
    "/data/quote",
    "/data/intelligence/news",
    "/data/intelligence/scanners",
    "/data/tables",
    "/data/topics",
    "/trading",
    "/trading/ai",
    "/portfolio",
    "/news-intelligence",
    "/scanners",
    "/quant-tools",
    "/settings",
    "/admin/settings",
    "/quote",
]


def login_via_ui(page):
    """通过 UI 在给定 page 上登录（sessionStorage 只在同一 tab 内有效，
    必须复用登录时的 page 进行后续导航）。"""
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
    # 等待用户名输入框渲染（Element Plus）
    page.wait_for_selector('input[placeholder="用户名"], input[placeholder*="用户名"], input[placeholder*="username" i]', timeout=15000)
    page.fill('input[placeholder="用户名"], input[placeholder*="用户名"], input[placeholder*="username" i]', ADMIN["username"])
    page.fill('input[type="password"]', ADMIN["password"])
    page.click('button:has-text("登录"), button[type="submit"]')
    # 等待跳转离开登录页
    page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
    page.wait_for_load_state("networkidle", timeout=10000)


def explore(headless: bool):
    results = []  # list of {page, url, console[], pageerror[], network[]}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1600, "height": 1000}, locale="zh-CN")

        # 复用同一个 page：先在该 page 上 UI 登录，再用它导航所有路由。
        # sessionStorage 只在同一个 tab 内有效，必须复用登录时的 page。
        page = context.new_page()
        login_via_ui(page)

        # 监听器只附加一次，写入共享列表，每轮快照后清空
        shared = {"console": [], "pageerror": [], "network": []}

        def on_console(msg):
            if msg.type in ("error", "warning"):
                shared["console"].append({"type": msg.type, "text": msg.text[:500]})

        def on_pageerror(err):
            shared["pageerror"].append({"message": str(err)[:500]})

        def on_response(response):
            url = response.url
            status = response.status
            if "/api/" in url and status >= 400:
                try:
                    body = response.text()[:300]
                except Exception:
                    body = ""
                shared["network"].append({"status": status, "url": url[:200], "body": body})

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)
        page.on("response", on_response)

        for path in PAGES:
            url = f"{BASE_URL}{path}"
            entry = {"page": path, "url": url, "final_url": "", "console": [], "pageerror": [], "network": []}
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)
                entry["final_url"] = page.url
            except Exception as e:
                entry["pageerror"].append({"message": f"NAVIGATION_ERROR: {str(e)[:300]}"})

            # 快照并清空共享列表
            entry["console"] = list(shared["console"])
            entry["pageerror"] = list(shared["pageerror"])
            entry["network"] = list(shared["network"])
            shared["console"].clear()
            shared["pageerror"].clear()
            shared["network"].clear()
            results.append(entry)

        page.close()
        browser.close()
    return results


def print_report(results):
    print("\n" + "=" * 80)
    print("页面遍历错误探测报告")
    print("=" * 80)

    total_pages = len(results)
    pages_with_errors = 0
    error_counts = defaultdict(int)

    for r in results:
        has_error = bool(r["pageerror"]) or any(
            m["type"] == "error" for m in r["console"]
        ) or bool(r["network"])
        if has_error:
            pages_with_errors += 1

        error_counts["pageerror"] += len(r["pageerror"])
        error_counts["console_error"] += sum(1 for m in r["console"] if m["type"] == "error")
        error_counts["console_warning"] += sum(1 for m in r["console"] if m["type"] == "warning")
        error_counts["network_4xx_5xx"] += len(r["network"])

    print(f"总页面数: {total_pages}")
    print(f"有错误/警告的页面数: {pages_with_errors}")
    print(f"未捕获异常 (pageerror): {error_counts['pageerror']}")
    print(f"console error: {error_counts['console_error']}")
    print(f"console warning: {error_counts['console_warning']}")
    print(f"网络 4xx/5xx: {error_counts['network_4xx_5xx']}")
    print("-" * 80)

    for r in results:
        if not (r["pageerror"] or r["console"] or r["network"]):
            continue
        print(f"\n【{r['page']}】")
        for e in r["pageerror"]:
            print(f"  ❌ PAGEERROR: {e['message']}")
        for m in r["console"]:
            icon = "❌" if m["type"] == "error" else "⚠️"
            print(f"  {icon} CONSOLE[{m['type']}]: {m['text']}")
        for n in r["network"]:
            print(f"  🌐 NET {n['status']}: {n['url']}")
            if n["body"]:
                print(f"        body: {n['body']}")

    # 保存 JSON 报告
    report_path = Path(__file__).parent / "explore_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细报告已保存: {report_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    results = explore(headless=not args.headed)
    print_report(results)


if __name__ == "__main__":
    main()
