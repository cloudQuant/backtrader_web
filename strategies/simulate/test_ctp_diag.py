#!/usr/bin/env python3
"""Detailed CTP connection diagnostic for bt_api_py."""
import sys
import time

print("=" * 60, flush=True)
print("CTP Connection Diagnostic (bt_api_py)", flush=True)
print("=" * 60, flush=True)

from bt_api_py.ctp.client import MdClient, TraderClient

# SimNow Group 2 addresses
MD_FRONT = "tcp://182.254.243.31:30012"
TD_FRONT = "tcp://182.254.243.31:30002"
BROKER_ID = "9999"
INVESTOR_ID = "089763"
PASSWORD = "yunjinqi2015!"
APP_ID = "simnow_client_test"
AUTH_CODE = "0000000000000000"

# ---- Test 1: MdClient ----
print(f"\n[Test 1] MdClient -> {MD_FRONT}", flush=True)
md_errors = []
md_connected_time = None
md_login_time = None

def md_on_error(info):
    msg = f"ErrorID={info.ErrorID}, ErrorMsg={info.ErrorMsg}" if info else "None"
    md_errors.append(msg)
    print(f"  [MD ERROR] {msg}", flush=True)

def md_on_login(info):
    global md_login_time
    md_login_time = time.time()
    try:
        print(f"  [MD LOGIN OK] TradingDay={info.TradingDay}", flush=True)
    except Exception:
        print("  [MD LOGIN OK]", flush=True)

md = MdClient(MD_FRONT, BROKER_ID, INVESTOR_ID, PASSWORD)
md.on_error = md_on_error
md.on_login = md_on_login

print("  Starting MdClient...", flush=True)
t0 = time.time()
md.start(block=False)

for i in range(20):
    time.sleep(1)
    if not md_connected_time and md._connected:
        md_connected_time = time.time()
    status = (
        f"  t={i+1:2d}s  connected={md._connected}  "
        f"loggedin={md._loggedin}"
    )
    if md_errors:
        status += f"  errors={md_errors}"
    print(status, flush=True)
    if md._loggedin:
        break

if md._loggedin:
    ct = md_connected_time - t0 if md_connected_time else "?"
    lt = md_login_time - t0 if md_login_time else "?"
    print(f"  [RESULT] MD OK (connect={ct:.1f}s, login={lt:.1f}s)", flush=True)
else:
    print(f"  [RESULT] MD FAILED", flush=True)
    if not md._connected:
        print("    -> OnFrontConnected never called", flush=True)
    else:
        print("    -> Connected but login failed", flush=True)

# ---- Test 2: TraderClient ----
print(f"\n[Test 2] TraderClient -> {TD_FRONT}", flush=True)
td_errors = []
td_connected_time = None
td_login_time = None

def td_on_error(info):
    msg = f"ErrorID={info.ErrorID}, ErrorMsg={info.ErrorMsg}" if info else "None"
    td_errors.append(msg)
    print(f"  [TD ERROR] {msg}", flush=True)

def td_on_login(info):
    global td_login_time
    td_login_time = time.time()
    try:
        print(f"  [TD LOGIN OK] TradingDay={info.TradingDay}", flush=True)
    except Exception:
        print("  [TD LOGIN OK]", flush=True)

td = TraderClient(
    TD_FRONT, BROKER_ID, INVESTOR_ID, PASSWORD,
    app_id=APP_ID, auth_code=AUTH_CODE,
)
td.on_error = td_on_error
td.on_login = td_on_login

print("  Starting TraderClient...", flush=True)
t0 = time.time()
td.start(block=False)

for i in range(25):
    time.sleep(1)
    if not td_connected_time and td._connected:
        td_connected_time = time.time()
    # Check internal state
    ready = getattr(td, '_ready', None)
    authed = getattr(td, '_authed', None)
    loggedin = getattr(td, '_loggedin', None)
    status = (
        f"  t={i+1:2d}s  connected={td._connected}  "
        f"authed={authed}  loggedin={loggedin}  ready={ready}"
    )
    if td_errors:
        status += f"  errors={td_errors}"
    print(status, flush=True)
    if ready:
        break

if getattr(td, '_ready', False):
    ct = td_connected_time - t0 if td_connected_time else "?"
    lt = td_login_time - t0 if td_login_time else "?"
    print(f"  [RESULT] TD OK (connect={ct:.1f}s, login={lt:.1f}s)", flush=True)
else:
    print(f"  [RESULT] TD FAILED", flush=True)
    if not td._connected:
        print("    -> OnFrontConnected never called", flush=True)
    elif not getattr(td, '_authed', False):
        print("    -> Connected but auth failed (app_id/auth_code issue?)", flush=True)
    elif not getattr(td, '_loggedin', False):
        print("    -> Authed but login failed (credential issue?)", flush=True)
    else:
        print("    -> Logged in but settlement not confirmed", flush=True)

# Cleanup
print("\nStopping clients...", flush=True)
try:
    md.stop()
except Exception:
    pass
try:
    td.stop()
except Exception:
    pass
print("Done.", flush=True)
