#!/usr/bin/env python
"""C01: 验证登录测试账号通过柜台认证并完成账号登录"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
_REPO = _SUITE.parents[2]
for _p in (_SUITE, _REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from common import config as cfg, helpers  # noqa: E402
from common.result import CaseTimer  # noqa: E402
from common.runtime import record_runtime_events, started_store  # noqa: E402

CASE_META = {
    "case_id": "C01",
    "case_name": "验证登录测试账号通过柜台认证并完成账号登录",
    "category": "连通性",
    "optional": False,
}


def run(report_dir):
    """Run C01 connect and login test case.

    Args:
        report_dir: Directory for test reports and logs.
    """
    env_key = cfg.get_env_key()
    with CaseTimer(CASE_META["case_id"], CASE_META["case_name"], env_key) as timer:
        log_dir = report_dir / "logs"
        try:
            with started_store(env_key) as (store, config, ek):
                assert store.is_connected, "Store did not connect"
                print("✓ 宏源期货连接成功")
                record_runtime_events(store.get_notifications(), log_dir / "system.log")

            # Verify logs
            system_entries = helpers.read_json_lines(log_dir / "system.log")
            events = helpers.extract_event_type_set(system_entries)

            assert "store_auth_success" in events, "Missing store_auth_success event"
            assert "store_login_success" in events, "Missing store_login_success event"
            print("✓ system.log 包含 store_auth_success 和 store_login_success")

            auth_entry = next(
                (entry for entry in system_entries if entry.get("event_type") == "store_auth_success"),
                {},
            )
            auth_details = dict(auth_entry.get("details") or {})
            evidence = helpers.collect_evidence_files(log_dir)
            return timer.pass_result(
                evidence=evidence,
                details={
                    "events": sorted(events),
                    "front_id": auth_details.get("front_id"),
                    "session_id": auth_details.get("session_id"),
                    "trading_day": auth_details.get("trading_day"),
                },
            )

        except Exception as exc:
            evidence = helpers.collect_evidence_files(log_dir)
            return timer.fail_result(str(exc), evidence=evidence)


if __name__ == "__main__":
    from common.runtime import case_main
    case_main(run, CASE_META)
