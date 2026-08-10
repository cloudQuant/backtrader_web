#!/usr/bin/env python3
"""Controlled AkShare online smoke for Iteration 192 pilot assets.

This is not a T1 acceptance pass.  It records provider structure and explicitly
marks quality gates that remain BLOCKED because approved bid/ask, curve,
cashflows and calendar evidence are not available.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import akshare as ak


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_futures_smoke() -> dict[str, object]:
    frame = ak.futures_zh_daily_sina(symbol="IF2609")
    latest = frame.tail(1).iloc[0]
    return {
        "asset_type": "futures",
        "symbol": "IF2609",
        "provider": "akshare_futures_zh_daily_sina",
        "structure_ok": True,
        "latest_date": str(latest["date"]),
        "latest_close": float(latest["close"]),
        "latest_volume": int(latest["volume"]),
        "quality_gate": "BLOCKED",
        "blocked_reason": [
            "FUTURES.BID_ASK_MISSING",
            "COMMON.CALENDAR_UNAVAILABLE",
        ],
    }


def _run_bond_smoke() -> dict[str, object]:
    frame = ak.bond_zh_hs_daily(symbol="sh019547")
    latest = frame.tail(1).iloc[0]
    return {
        "asset_type": "bond",
        "symbol": "019547",
        "provider": "akshare_bond_zh_hs_daily",
        "structure_ok": True,
        "latest_date": str(latest["date"]),
        "latest_close": float(latest["close"]),
        "latest_volume": int(latest["volume"]),
        "quality_gate": "BLOCKED",
        "blocked_reason": [
            "BOND.CASHFLOWS_MISSING",
            "BOND.CURVE_MISSING",
            "COMMON.BENCHMARK_MISSING",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "docs/iterations/迭代192-可信多资产研究收口与模型治理/evidence/"
            "2026-08-07-akshare-online-smoke.json"
        ),
    )
    args = parser.parse_args()
    payload = {
        "profile": "ONLINE-SMOKE",
        "generated_at": _utc_now(),
        "note": "结构冒烟，不是 T1 或 T2 验收通过",
        "assets": [_run_futures_smoke(), _run_bond_smoke()],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

