#!/usr/bin/env python3
"""Run a disposable real AkShare T1 pilot through the asset-research schema.

This is not a T2 promotion evidence.  It imports the approved Iteration 192
manifest into a temporary SQLite schema, executes the real futures/bond
providers through PUBLIC_SHADOW schedules, and records whether each pilot
reached ``ELIGIBLE`` with executable bid/ask, curve, cashflows and calendar
evidence.  The script never overwrites existing evidence files.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "src" / "backend"
MANIFEST_PATH = REPO_ROOT / "config" / "asset_research_approved_manifest.json"
FIRE_AT = datetime(2026, 8, 7, 11, 10, tzinfo=timezone.utc)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT
        / "docs/iterations/迭代192-可信多资产研究收口与模型治理/evidence"
        / "2026-08-07-akshare-real-t1.json",
        help="New JSON evidence file; an existing file is never overwritten",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing generated evidence file during development",
    )
    return parser.parse_args()


def _write_result(result: dict[str, Any], output: Path, *, force: bool = False) -> None:
    resolved = output.resolve()
    if resolved.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing evidence file: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


async def _run_t1(database_path: Path) -> dict[str, Any]:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    os.environ["AI_CHAT_ENABLED"] = "false"
    os.environ["ASSET_RESEARCH_LLM_REPORT_ENABLED"] = "false"

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models  # noqa: F401  (populate Base.metadata)
    from app.db.database import Base, async_session_maker
    from app.models.asset_research import (
        AssetSignalPrediction,
        AssetSignalRun,
        AssetSignalSchedule,
        AssetSourceSnapshot,
    )
    from app.services.asset_research.importers.approved_manifest_importer import (
        ApprovedManifestImporter,
    )
    from app.services.asset_research.orchestrator import AssetResearchOrchestrator
    from app.services.asset_research.providers.akshare import AkShareCompositeProvider
    from app.services.asset_research.scheduler import AssetResearchScheduleRunner

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    manifest_payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    async with async_session_maker() as db:
        report = await ApprovedManifestImporter(db).import_payload(
            payload=manifest_payload,
            dry_run=False,
            valid_from=datetime(2026, 8, 7, 0, 0, tzinfo=timezone.utc),
        )
        if not report.passed:
            raise RuntimeError("approved manifest import failed: " + ", ".join(report.errors))
        schedules = list(
            (
                await db.execute(
                    select(AssetSignalSchedule).where(
                        AssetSignalSchedule.approved_manifest_id.is_not(None)
                    )
                )
            ).scalars()
        )
        for schedule in schedules:
            schedule.next_run_at = FIRE_AT
        await db.commit()

    provider = AkShareCompositeProvider()
    runner = AssetResearchScheduleRunner(
        session_maker=async_session_maker,
        orchestrator_factory=lambda db: AssetResearchOrchestrator(
            db,
            data_adapter=provider,
        ),
        max_batch=10,
        max_concurrency=1,
    )
    claimed = await runner.run_due(now=FIRE_AT)

    async with async_session_maker() as db:
        runs = list((await db.execute(select(AssetSignalRun))).scalars())
        predictions = list((await db.execute(select(AssetSignalPrediction))).scalars())
        snapshots = list((await db.execute(select(AssetSourceSnapshot))).scalars())

    assets: list[dict[str, Any]] = []
    violations: list[str] = []
    if claimed != 2:
        violations.append(f"claimed_count={claimed}, expected=2")
    if len(runs) != 2 or any(run.status != "SUCCEEDED" for run in runs):
        violations.append("schedule runs did not all succeed")
    if len(predictions) != 2 or any(
        prediction.quality_status != "ELIGIBLE" for prediction in predictions
    ):
        violations.append("predictions did not reach ELIGIBLE")
    if len(snapshots) != 2:
        violations.append("source snapshots did not persist for both pilots")

    by_asset = {prediction.asset_type: prediction for prediction in predictions}
    for asset_type in ("futures", "bond"):
        prediction = by_asset.get(asset_type)
        snapshot = next(
            (item for item in snapshots if item.asset_type == asset_type),
            None,
        )
        asset = {
            "asset_type": asset_type,
            "quality_status": prediction.quality_status if prediction else None,
            "reason_codes": (prediction.quality_json or {}).get("reason_codes", [])
            if prediction
            else [],
            "source_registry_status": (snapshot.source_manifest_json or {}).get(
                "source_registry_status"
            )
            if snapshot
            else None,
            "license_tags": snapshot.license_tags_json if snapshot else [],
            "source_id": (snapshot.source_manifest_json or {}).get("source_id")
            if snapshot
            else None,
            "raw_schema_version": snapshot.raw_schema_version if snapshot else None,
            "content_hash": snapshot.content_hash if snapshot else None,
        }
        if snapshot is not None:
            persisted = snapshot.raw_fields_json or {}
            raw = persisted.get("fields") or {}
            quote = raw.get("snapshot") or {}
            asset["quote"] = {
                key: quote.get(key)
                for key in ("price", "bid", "ask", "bid_volume", "ask_volume", "quote_at")
            }
            if asset_type == "futures":
                asset["calendar_id"] = (raw.get("calendar") or {}).get("calendar_id")
                asset["calendar_session_count"] = len(
                    (raw.get("calendar") or {}).get("sessions", [])
                )
            else:
                bond = raw.get("bond") or {}
                asset["cashflow_count"] = len(bond.get("cashflows", []))
                asset["curve_point_count"] = len(bond.get("curve", []))
                asset["benchmark_id"] = (bond.get("benchmark") or {}).get("benchmark_id")
                asset["calendar_id"] = (raw.get("calendar") or {}).get("calendar_id")
                asset["calendar_session_count"] = len(
                    (raw.get("calendar") or {}).get("sessions", [])
                )
            missing = [
                key
                for key in ("price", "bid", "ask")
                if quote.get(key) is None
            ]
            if missing:
                violations.append(f"{asset_type} missing quote fields: {missing}")
            if asset_type == "bond" and (
                not bond.get("cashflows") or not bond.get("curve") or not bond.get("benchmark")
            ):
                violations.append(f"{asset_type} missing cashflows/curve/benchmark")
        assets.append(asset)

    await engine.dispose()
    return {
        "profile": "AKSHARE-REAL-T1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not violations,
        "violations": violations,
        "manifest_evidence": {
            "path": str(MANIFEST_PATH.relative_to(REPO_ROOT)),
            "sha256": _file_sha256(MANIFEST_PATH),
        },
        "provider_evidence": {
            "path": "src/backend/app/services/asset_research/providers/akshare.py",
            "sha256": _file_sha256(
                BACKEND_DIR / "app" / "services" / "asset_research" / "providers" / "akshare.py"
            ),
        },
        "schedule_fire_at": FIRE_AT.isoformat(),
        "claimed_count": claimed,
        "run_count": len(runs),
        "run_status": sorted({run.status for run in runs}),
        "assets": assets,
    }


def main() -> int:
    args = _parse_args()
    try:
        with tempfile.TemporaryDirectory(prefix="iter192-akshare-t1-") as tmp:
            database_path = Path(tmp) / "iter192_akshare_t1.db"
            result = asyncio.run(_run_t1(database_path))
        _write_result(result, args.output, force=args.force)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))  # noqa: T201
        if not result["passed"]:
            print("T1 evidence failed; inspect violations above.", file=sys.stderr)  # noqa: T201
            return 1
        return 0
    except Exception as exc:
        print(f"T1 evidence could not run: {exc}", file=sys.stderr)  # noqa: T201
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
