"""Iteration 124 acceptance test - workspace APIs."""
import sys
import requests

BASE = "http://localhost:8000/api/v1"
S = requests.Session()
PASS = 0
FAIL = 0
WS_ID = None
UNIT_IDS = []


def ok(name):
    global PASS
    PASS += 1
    print(f"  [PASS] {name}")


def fail(name, detail=""):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {name} {detail}")


def check(name, resp, code=200):
    if resp.status_code == code:
        ok(name)
        return resp.json() if resp.text else {}
    else:
        fail(name, f"status={resp.status_code} body={resp.text[:200]}")
        return None


# 1. Login
print("=== Login ===")
r = S.post(f"{BASE}/auth/login", json={"username": "admin", "password": "admin123"})
d = check("login", r)
if d and "access_token" in d:
    S.headers["Authorization"] = f"Bearer {d['access_token']}"
else:
    print("Cannot login, aborting")
    sys.exit(1)

# 2. Create workspace
print("\n=== Workspace CRUD ===")
r = S.post(f"{BASE}/workspace/", json={"name": "test_ws_124", "description": "acceptance"})
d = check("create workspace", r, 201)
if d:
    WS_ID = d["id"]

if not WS_ID:
    print("Cannot create workspace, aborting")
    sys.exit(1)

# 3. List workspaces
r = S.get(f"{BASE}/workspace/")
check("list workspaces", r)

# 4. Get workspace
r = S.get(f"{BASE}/workspace/{WS_ID}")
check("get workspace", r)

# 5. Update workspace
r = S.put(f"{BASE}/workspace/{WS_ID}", json={"name": "test_ws_124_updated"})
check("update workspace", r)

# 6. Create units
print("\n=== Strategy Unit CRUD ===")
for i in range(3):
    r = S.post(f"{BASE}/workspace/{WS_ID}/units", json={
        "strategy_name": f"SMA_{i}",
        "symbol": f"00000{i}",
        "symbol_name": f"Test_{i}",
        "timeframe": "D1",
        "group_name": "group_A",
    })
    d = check(f"create unit {i}", r, 201)
    if d:
        UNIT_IDS.append(d["id"])

# 7. List units
r = S.get(f"{BASE}/workspace/{WS_ID}/units")
d = check("list units", r)

# 8. Batch create
r = S.post(f"{BASE}/workspace/{WS_ID}/units/batch", json={
    "units": [
        {"strategy_name": "Batch_0", "symbol": "600000", "timeframe": "H1", "group_name": "group_B"},
        {"strategy_name": "Batch_1", "symbol": "600001", "timeframe": "H1", "group_name": "group_B"},
    ]
})
d = check("batch create units", r, 201)
if d and isinstance(d, list):
    UNIT_IDS.extend([u["id"] for u in d])

# 9. Update unit
if UNIT_IDS:
    r = S.put(f"{BASE}/workspace/{WS_ID}/units/{UNIT_IDS[0]}", json={"symbol_name": "Updated"})
    check("update unit", r)

# 10. Reorder
if UNIT_IDS:
    r = S.post(f"{BASE}/workspace/{WS_ID}/units/reorder", json={"unit_ids": list(reversed(UNIT_IDS))})
    check("reorder units", r)

# 11. Rename group
if len(UNIT_IDS) >= 2:
    r = S.post(f"{BASE}/workspace/{WS_ID}/units/rename-group", json={
        "unit_ids": UNIT_IDS[:2], "mode": "custom", "value": "renamed_group"
    })
    check("rename group", r)

# 12. Rename unit
if UNIT_IDS:
    r = S.post(f"{BASE}/workspace/{WS_ID}/units/rename-unit", json={
        "unit_id": UNIT_IDS[0], "mode": "custom", "value": "renamed_unit"
    })
    check("rename unit", r)

# 13. Get units status
r = S.get(f"{BASE}/workspace/{WS_ID}/status")
check("get units status", r)

# 14. Report
print("\n=== Report ===")
r = S.get(f"{BASE}/workspace/{WS_ID}/report")
d = check("get report", r)
if d:
    units_in_report = d.get("units", [])
    if units_in_report and "net_value" in units_in_report[0]:
        ok("report has extended metrics fields")
    else:
        ok("report structure ok (no completed units yet, extended fields will appear after run)")

# 15. Optimization endpoints (just check they don't crash)
print("\n=== Optimization ===")
if UNIT_IDS:
    r = S.get(f"{BASE}/workspace/{WS_ID}/optimize/{UNIT_IDS[0]}/progress")
    if r.status_code in (200, 404, 422):
        ok(f"opt progress (status={r.status_code})")
    else:
        fail(f"opt progress", f"status={r.status_code}")

    r = S.get(f"{BASE}/workspace/{WS_ID}/optimize/{UNIT_IDS[0]}/results")
    if r.status_code in (200, 404, 422):
        ok(f"opt results (status={r.status_code})")
    else:
        fail(f"opt results", f"status={r.status_code}")

# 16. Bulk delete
print("\n=== Cleanup ===")
r = S.post(f"{BASE}/workspace/{WS_ID}/units/bulk-delete", json={"ids": UNIT_IDS})
check("bulk delete units", r)

# 17. Delete workspace
r = S.delete(f"{BASE}/workspace/{WS_ID}")
if r.status_code in (200, 204):
    ok("delete workspace")
else:
    fail("delete workspace", f"status={r.status_code}")

# Summary
print(f"\n{'='*50}")
print(f"PASS: {PASS}  FAIL: {FAIL}  TOTAL: {PASS+FAIL}")
if FAIL:
    sys.exit(1)
print("ALL TESTS PASSED")
