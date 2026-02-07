#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
End-to-end Playwright test: verify backtest can run successfully via the browser UI.

Prerequisites:
  - Backend running on http://localhost:8000
  - Frontend running on http://localhost:3000
  - pip install playwright && python -m playwright install chromium

Usage:
  python tests/test_backtest_e2e.py          # headed (visible browser)
  python tests/test_backtest_e2e.py --headless  # headless
"""
import sys
import time
import requests
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"
TEST_USER = {"username": "test_e2e", "email": "test_e2e@test.com", "password": "test1234"}
STRATEGY_ID = "002_dual_ma"


def preflight_checks():
    """Verify backend and frontend are reachable, register test user."""
    # Check backend
    try:
        r = requests.get(f"{API_URL}/api/v1/strategy/templates", timeout=5)
        data = r.json()
        print(f"  Backend OK — {data['total']} strategy templates loaded")
    except Exception as e:
        print(f"  ✗ Backend not reachable: {e}")
        sys.exit(1)

    # Check frontend
    try:
        r = requests.get(BASE_URL, timeout=5)
        assert r.status_code == 200
        print("  Frontend OK")
    except Exception as e:
        print(f"  ✗ Frontend not reachable: {e}")
        sys.exit(1)

    # Register test user (ignore conflict)
    try:
        requests.post(f"{API_URL}/api/v1/auth/register", json=TEST_USER, timeout=5)
    except Exception:
        pass

    # Login and verify token works
    try:
        r = requests.post(f"{API_URL}/api/v1/auth/login",
                          json={"username": TEST_USER["username"], "password": TEST_USER["password"]},
                          timeout=5)
        token = r.json().get("access_token")
        assert token, "Login failed"
        print(f"  Auth OK — token obtained")
        return token
    except Exception as e:
        print(f"  ✗ Auth failed: {e}")
        sys.exit(1)


def test_backtest_run():
    """
    E2E test: login → backtest page → select strategy → run → verify success.
    """
    headless = "--headless" in sys.argv

    print("\n[0/6] Preflight checks...")
    token = preflight_checks()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # Capture console errors for diagnostics
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # ── Step 1: Login ──
        print("\n[1/6] Logging in...")
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")

        page.locator("input[placeholder='用户名']").fill(TEST_USER["username"])
        page.locator("input[placeholder='密码']").fill(TEST_USER["password"])
        page.locator("button:has-text('登录')").click()

        page.wait_for_url(lambda url: "/login" not in url, timeout=10000)
        print(f"  ✓ Logged in → {page.url}")

        # ── Step 2: Navigate to backtest page ──
        print("\n[2/6] Navigating to backtest page...")
        page.goto(f"{BASE_URL}/backtest?strategy={STRATEGY_ID}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        # ── Step 3: Ensure strategy is selected ──
        print("\n[3/6] Verifying strategy selection...")

        # Check how many templates loaded in store
        tmpl_count = page.evaluate("""() => {
            try {
                const app = document.getElementById('app').__vue_app__;
                const pinia = app.config.globalProperties.$pinia;
                return pinia.state.value.strategy?.templates?.length || 0;
            } catch(e) { return -1; }
        }""")
        print(f"  Templates in store: {tmpl_count}")

        # Check if ?strategy= query param set form.strategy_id, if not, force-set it
        form_strategy = page.evaluate("""() => {
            try {
                // Read the select's model value via the hidden input or aria
                const sel = document.querySelector('.el-select');
                // Check if any option is selected by looking at the displayed text
                const selected = sel?.querySelector('.el-select__selected-item, .el-input__inner');
                return selected?.textContent?.trim() || selected?.value || '';
            } catch(e) { return ''; }
        }""")
        print(f"  Select display text: '{form_strategy}'")

        if not form_strategy or form_strategy == '选择策略':
            print(f"  ⚠ Query param didn't auto-select, clicking option manually...")
            # Open dropdown
            page.locator(".el-select").first.click()
            page.wait_for_timeout(1000)
            # Look for the option with the target text
            target_option = page.locator(".el-select-dropdown__item").filter(has_text="双均线交叉策略")
            if target_option.count() > 0:
                target_option.first.click()
                page.wait_for_timeout(500)
                print("  ✓ Strategy selected from dropdown")
            else:
                print(f"  ⚠ Option not found, scrolling dropdown...")
                # The dropdown may need scrolling; type to filter
                page.keyboard.type("双均线")
                page.wait_for_timeout(800)
                filtered = page.locator(".el-select-dropdown__item").filter(has_text="双均线")
                if filtered.count() > 0:
                    filtered.first.click()
                    page.wait_for_timeout(500)
                    print("  ✓ Strategy selected via filter")
                else:
                    print("  ✗ Could not select strategy")
                    page.screenshot(path="tests/backtest_no_strategy.png")
                    browser.close()
                    sys.exit(1)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        # ── Step 4: Verify form ──
        print("\n[4/6] Verifying form...")
        symbol_val = page.locator("input[placeholder='如: 000001.SZ']").input_value()
        print(f"  Symbol: {symbol_val}")
        page.screenshot(path="tests/before_run.png")

        # ── Step 5: Click Run ──
        print("\n[5/6] Running backtest...")
        run_button = page.locator("button:has-text('运行回测')")
        run_button.click()
        page.wait_for_timeout(2000)

        # Check if we got a warning (no strategy selected)
        warning = page.locator(".el-message--warning")
        if warning.count() > 0:
            warn_text = warning.first.text_content()
            print(f"  ⚠ Warning: {warn_text}")
            page.screenshot(path="tests/backtest_warning.png")
            print("  Screenshot: tests/backtest_warning.png")
            browser.close()
            sys.exit(1)

        # Wait for task submission confirmation
        try:
            page.wait_for_selector(".el-message--success", timeout=15000)
            print("  ✓ Backtest task submitted")
        except Exception:
            err = page.locator(".el-message--error")
            if err.count() > 0:
                print(f"  ✗ Error: {err.first.text_content()}")
            page.screenshot(path="tests/backtest_submit_fail.png")
            print("  Screenshot: tests/backtest_submit_fail.png")
            browser.close()
            sys.exit(1)

        # ── Step 6: Wait for completion ──
        print("\n[6/6] Waiting for backtest result (max 120s)...")
        start = time.time()
        max_wait = 120
        result = None

        while time.time() - start < max_wait:
            # Check for result metrics card
            if page.locator("text=总收益率").count() > 0:
                result = "success"
                break

            # Check for error notification
            err_msg = page.locator(".el-message--error")
            if err_msg.count() > 0:
                result = f"failed: {err_msg.first.text_content()}"
                break

            page.wait_for_timeout(2000)

        elapsed = time.time() - start

        if result == "success":
            print(f"  ✓ Backtest completed in {elapsed:.1f}s")

            # Verify key metrics are displayed
            for metric in ["总收益率", "夏普比率", "最大回撤", "总交易次数"]:
                assert page.locator(f"text={metric}").count() > 0, f"Metric '{metric}' not found"
            print("  ✓ All result metrics displayed")

            page.screenshot(path="tests/backtest_success.png")
            print("  Screenshot: tests/backtest_success.png")

            if console_errors:
                print(f"\n  ⚠ Console errors ({len(console_errors)}):")
                for e in console_errors[:5]:
                    print(f"    {e[:100]}")

            print("\n══════════════════════════════════")
            print("  TEST PASSED ✓")
            print("══════════════════════════════════")
        else:
            reason = result or f"timeout after {max_wait}s"
            print(f"\n  ✗ {reason}")
            page.screenshot(path="tests/backtest_failed.png")
            print("  Screenshot: tests/backtest_failed.png")

            # Print backend logs for diagnostics
            print("\n  Backend log tail:")
            try:
                import subprocess
                logs = subprocess.check_output(
                    ["tail", "-20", "logs/backend.log"],
                    cwd="/Users/yunjinqi/Documents/量化交易框架/backtrader_web",
                    text=True, timeout=3
                )
                for line in logs.strip().split("\n"):
                    if "error" in line.lower() or "fail" in line.lower():
                        print(f"    {line[:120]}")
            except Exception:
                pass

            print("\n══════════════════════════════════")
            print("  TEST FAILED ✗")
            print("══════════════════════════════════")
            browser.close()
            sys.exit(1)

        browser.close()


if __name__ == "__main__":
    test_backtest_run()
