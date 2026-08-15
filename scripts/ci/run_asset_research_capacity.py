#!/usr/bin/env python3
"""Run Iteration 191's fixed 100-instrument CAPACITY profile on disposable MySQL.

The command deliberately refuses shared schemas.  Its caller must first create
an empty disposable MySQL database, run ``alembic upgrade head`` there, and
then pass that exact URL with ``--confirm-disposable``.  This script never
creates or drops tables: migration compatibility has a separate gate.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import re
import resource
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "src" / "backend"
DISPOSABLE_DATABASE_RE = re.compile(r"^codex_iter191_capacity_[A-Za-z0-9_]{1,48}$")
REQUIRED_TABLES = frozenset(
    {
        "asset_instruments",
        "asset_data_source_registry",
        "asset_schedule_manifests",
        "asset_signal_schedules",
        "asset_signal_runs",
        "asset_signal_predictions",
        "asset_signal_outcomes",
    }
)
SOURCE_ID = "capacity-fixture-source"
FIXTURE_VERSION = "iter191-capacity-fixture-v1"
FIRE_AT = datetime(2030, 1, 2, 11, 10, tzinfo=timezone.utc)


def validate_disposable_mysql_url(raw_url: str) -> str:
    """Return a safe database name or reject any non-disposable target."""
    url = make_url(raw_url)
    if url.get_backend_name() != "mysql":
        raise ValueError("CAPACITY runner only accepts a MySQL database URL")
    database = url.database or ""
    if not DISPOSABLE_DATABASE_RE.fullmatch(database):
        raise ValueError(
            "CAPACITY runner requires a disposable database named "
            "codex_iter191_capacity_<suffix>"
        )
    return database


def nearest_rank_percentile(values: list[float], quantile: float) -> float:
    """Return a deterministic nearest-rank percentile for positive sample counts."""
    if not values:
        raise ValueError("values must not be empty")
    if not 0.0 < quantile <= 1.0:
        raise ValueError("quantile must be in (0, 1]")
    ordered = sorted(values)
    index = max(1, math.ceil(len(ordered) * quantile)) - 1
    return ordered[index]


def file_sha256(path: Path) -> str:
    """Return the SHA-256 for one exact source file used by the profile."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True, help="Disposable MySQL schema URL")
    parser.add_argument(
        "--confirm-disposable",
        action="store_true",
        help="Acknowledge that the target is an empty, disposable schema",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional new JSON evidence file; an existing file is never overwritten",
    )
    parser.add_argument(
        "--source-delay-ms",
        type=float,
        default=20.0,
        help="Deterministic fixture source delay used to exercise concurrency (default: 20)",
    )
    return parser.parse_args()


def _commit_sha() -> str | None:
    """Read a CI-provided revision without executing a process or trusting PATH."""
    value = os.environ.get("GIT_COMMIT_SHA", "").strip().lower()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def _resource_snapshot() -> dict[str, Any]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "cpu_user_seconds": usage.ru_utime,
        "cpu_system_seconds": usage.ru_stime,
        "max_rss": usage.ru_maxrss,
        "max_rss_unit": "bytes" if sys.platform == "darwin" else "KiB",
    }


def _write_result(result: dict[str, Any], output: Path | None) -> None:
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    print(payload)
    if output is None:
        return
    resolved = output.resolve()
    if resolved.exists():
        raise FileExistsError(f"refusing to overwrite existing evidence file: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(payload + "\n", encoding="utf-8")


async def _run_profile(database_url: str, source_delay_seconds: float) -> dict[str, Any]:
    """Execute the bounded fixture through the real schedule persistence path."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy import func, inspect, select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.models.asset_research import (
        AssetAnalysisReport,
        AssetAnalysisTask,
        AssetDataSourceRegistry,
        AssetSignalOutcome,
        AssetSignalRun,
        AssetSignalSchedule,
    )
    from app.schemas.asset_research import (
        ApprovedScheduleManifestCreateRequest,
        ApprovedScheduleManifestEntry,
        AssetSignalScheduleCreateRequest,
        FuturesIdentityDetails,
        InstrumentIdentity,
        RawAssetSnapshot,
    )
    from app.services.asset_research.concurrency import AssetResearchSourceConcurrencyLimiter
    from app.services.asset_research.orchestrator import AssetResearchOrchestrator
    from app.services.asset_research.scheduler import AssetResearchScheduleRunner, ClaimedSchedule

    class CapacityFuturesData:
        """Deterministic approved provider that records source concurrency."""

        declared_source_ids = (SOURCE_ID,)

        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0
            self.collection_count = 0

        async def collect(
            self, identity: InstrumentIdentity, *, cutoff_at: datetime
        ) -> RawAssetSnapshot:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.collection_count += 1
            try:
                await asyncio.sleep(source_delay_seconds)
                return RawAssetSnapshot(
                    identity=identity,
                    cutoff_at=cutoff_at,
                    retrieved_at=cutoff_at,
                    raw_schema_version=FIXTURE_VERSION,
                    raw_fields={
                        "snapshot": {"price": 101, "bid": 100.9, "ask": 101.1},
                        "futures": {"contract_price": 101, "spot_price": 100},
                    },
                    history_rows=[{"date": "2029-12-31", "close": 101}],
                    source_manifest={
                        "provider": SOURCE_ID,
                        "capabilities": ["price", "contract_calendar"],
                    },
                    license_tags=[],
                    content_hash=hashlib.sha256(
                        f"{FIXTURE_VERSION}:{identity.canonical_id}:{cutoff_at.isoformat()}".encode()
                    ).hexdigest(),
                )
            finally:
                self.active -= 1

    class MeasuringScheduleRunner(AssetResearchScheduleRunner):
        """Record complete schedule-run durations without changing worker semantics."""

        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.active = 0
            self.max_active = 0
            self.claim_durations_seconds: list[float] = []
            self.recovery_error_codes: list[str] = []

        async def _run_claim(self, claim: ClaimedSchedule, *, claim_time: datetime) -> None:
            started_at = perf_counter()
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                await super()._run_claim(claim, claim_time=claim_time)
            finally:
                self.claim_durations_seconds.append(perf_counter() - started_at)
                self.active -= 1

        async def _recover_unhandled_claim(
            self, claim: ClaimedSchedule, *, error_code: str
        ) -> None:
            self.recovery_error_codes.append(error_code)
            await super()._recover_unhandled_claim(claim, error_code=error_code)

    def identity_for(index: int) -> InstrumentIdentity:
        contract_code = f"IF{2700 + index:04d}"
        return InstrumentIdentity(
            asset_type="futures",
            identity_level="CONTRACT",
            canonical_id=f"futures:CFFEX:{contract_code}:CNY",
            display_symbol=contract_code,
            name=f"容量夹具沪深300期货{contract_code}",
            venue="CFFEX",
            currency="CNY",
            timezone="Asia/Shanghai",
            identifier_type="CONTRACT_CODE",
            identifier_value=contract_code,
            product_type="FUTURE",
            metadata_version=FIXTURE_VERSION,
            details=FuturesIdentityDetails(
                product_code="IF",
                contract_month=contract_code[-4:],
                expiry_at="2031-09-18T07:15:00+00:00",
                contract_multiplier="300",
                trading_calendar_id="CFFEX",
            ),
        )

    engine = create_async_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    started_wall = datetime.now(timezone.utc)
    resources_before = _resource_snapshot()
    try:
        async with engine.connect() as connection:
            table_names = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
            missing_tables = sorted(REQUIRED_TABLES - table_names)
            if missing_tables:
                raise RuntimeError(
                    "target schema is not migrated to Iteration 191 head; missing tables: "
                    + ", ".join(missing_tables)
                )
            schema_revision = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one_or_none()
            mysql_version = (await connection.execute(text("SELECT VERSION()"))).scalar_one()
            threads_connected_before_row = (
                await connection.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
            ).first()

        data = CapacityFuturesData()
        source_limiter = AssetResearchSourceConcurrencyLimiter(max_per_source=2)
        async with session_maker() as db:
            registry = await db.get(AssetDataSourceRegistry, SOURCE_ID)
            if registry is None:
                db.add(
                    AssetDataSourceRegistry(
                        source_id=SOURCE_ID,
                        asset_types=["futures"],
                        jurisdictions=["GLOBAL"],
                        license_status="APPROVED",
                        allowed_uses=["RESEARCH_ONLY"],
                        redistribution_policy="NO_REDISTRIBUTION",
                        derived_data_policy="ALLOWED",
                        retention_policy=FIXTURE_VERSION,
                        effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                        freshness_sla={},
                        enabled=True,
                    )
                )
                await db.flush()

            service = AssetResearchOrchestrator(
                db,
                data_adapter=data,
                source_limiter=source_limiter,
            )
            entries: list[ApprovedScheduleManifestEntry] = []
            for index in range(100):
                instrument = await service.persist_identity(identity_for(index))
                entries.append(
                    ApprovedScheduleManifestEntry(
                        entry_key=f"capacity-{index:03d}",
                        schedule=AssetSignalScheduleCreateRequest(
                            asset_type="futures",
                            canonical_id=instrument.canonical_id,
                            cron_expression="10 19 * * 1-5",
                            timezone="Asia/Shanghai",
                            cutoff_policy="futures-complete-session-v1",
                        ),
                    )
                )
            manifest = await service.create_approved_schedule_manifest(
                actor_id="capacity-fixture-admin",
                request=ApprovedScheduleManifestCreateRequest(
                    manifest_key="capacity-public-shadow",
                    manifest_version=FIXTURE_VERSION,
                    owner_scope="PUBLIC_SHADOW",
                    approval_reference="CAPACITY-FIXTURE-ONLY",
                    evidence_uri="evidence://iter191/capacity-fixture",
                    evidence_content_hash="c" * 64,
                    entries=entries,
                ),
            )
            schedules = list(
                (
                    await db.execute(
                        select(AssetSignalSchedule)
                        .where(AssetSignalSchedule.approved_manifest_id == manifest.id)
                        .order_by(AssetSignalSchedule.manifest_entry_key)
                    )
                ).scalars()
            )
            for schedule in schedules:
                schedule.next_run_at = FIRE_AT
            await db.commit()

        schedule_ids = [schedule.id for schedule in schedules]
        scheduled_fire_at = FIRE_AT.replace(minute=FIRE_AT.minute + 1)
        runner = MeasuringScheduleRunner(
            session_maker=session_maker,
            orchestrator_factory=lambda db: AssetResearchOrchestrator(
                db,
                data_adapter=data,
                source_limiter=source_limiter,
            ),
            max_batch=100,
            max_concurrency=4,
        )
        batch_started = perf_counter()
        claimed_count = await runner.run_due(now=scheduled_fire_at)
        batch_elapsed_seconds = perf_counter() - batch_started

        async with session_maker() as db:
            persisted_schedules = list(
                (
                    await db.execute(
                        select(AssetSignalSchedule).where(AssetSignalSchedule.id.in_(schedule_ids))
                    )
                ).scalars()
            )
            runs = list(
                (
                    await db.execute(
                        select(AssetSignalRun).where(AssetSignalRun.schedule_id.in_(schedule_ids))
                    )
                ).scalars()
            )
            pending_outcomes = await db.scalar(
                select(func.count())
                .select_from(AssetSignalOutcome)
                .join(AssetSignalRun, AssetSignalRun.prediction_id == AssetSignalOutcome.prediction_id)
                .where(AssetSignalRun.schedule_id.in_(schedule_ids))
                .where(AssetSignalOutcome.status == "PENDING")
            )
            due_remaining = await db.scalar(
                select(func.count())
                .select_from(AssetSignalSchedule)
                .where(AssetSignalSchedule.id.in_(schedule_ids))
                .where(AssetSignalSchedule.next_run_at <= scheduled_fire_at)
            )
            task_count = await db.scalar(select(func.count()).select_from(AssetAnalysisTask))
            report_count = await db.scalar(select(func.count()).select_from(AssetAnalysisReport))

        async with engine.connect() as connection:
            threads_connected_after_row = (
                await connection.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
            ).first()

        status_counts = Counter(run.status for run in runs)
        resources_after = _resource_snapshot()
        recovery_counts = Counter(runner.recovery_error_codes)
        leased_count = sum(schedule.lease_token is not None for schedule in persisted_schedules)
        retry_pending_count = sum(
            schedule.retry_of_run_id is not None for schedule in persisted_schedules
        )
        nonterminal_count = sum(run.status in {"QUEUED", "RUNNING"} for run in runs)
        violations: list[str] = []
        if claimed_count != 100:
            violations.append(f"claimed_count={claimed_count}, expected=100")
        if len(persisted_schedules) != 100:
            violations.append(f"persisted_schedule_count={len(persisted_schedules)}, expected=100")
        if len(runs) != 100 or status_counts != {"SUCCEEDED": 100}:
            violations.append(f"run_status_counts={dict(status_counts)}")
        if leased_count:
            violations.append(f"leased_count={leased_count}")
        if retry_pending_count:
            violations.append(f"retry_pending_count={retry_pending_count}")
        if nonterminal_count:
            violations.append(f"nonterminal_run_count={nonterminal_count}")
        if due_remaining:
            violations.append(f"due_remaining={due_remaining}")
        if task_count or report_count:
            violations.append(f"schedule_created_tasks={task_count}, reports={report_count}")
        if runner.max_active != 4:
            violations.append(f"worker_peak={runner.max_active}, expected=4")
        if data.max_active != 2:
            violations.append(f"source_peak={data.max_active}, expected=2")
        if recovery_counts:
            violations.append(f"worker_recovery_errors={dict(recovery_counts)}")
        if batch_elapsed_seconds > 30 * 60:
            violations.append(f"batch_elapsed_seconds={batch_elapsed_seconds:.3f}, limit=1800")

        return {
            "iteration": 191,
            "profile": "CAPACITY",
            "passed": not violations,
            "violations": violations,
            "commit_sha": _commit_sha(),
            "source_files_sha256": {
                "scripts/ci/run_asset_research_capacity.py": file_sha256(Path(__file__)),
                "src/backend/app/config.py": file_sha256(BACKEND_DIR / "app" / "config.py"),
                "src/backend/app/services/asset_research/concurrency.py": file_sha256(
                    BACKEND_DIR / "app" / "services" / "asset_research" / "concurrency.py"
                ),
                "src/backend/app/services/asset_research/orchestrator.py": file_sha256(
                    BACKEND_DIR / "app" / "services" / "asset_research" / "orchestrator.py"
                ),
                "src/backend/app/services/asset_research/scheduler.py": file_sha256(
                    BACKEND_DIR / "app" / "services" / "asset_research" / "scheduler.py"
                ),
            },
            "started_at": started_wall.isoformat(),
            "timezone": "UTC",
            "host": {
                "os": platform.platform(),
                "python": sys.version.split()[0],
                "cpu_count": os.cpu_count(),
            },
            "database": {
                "vendor": "MySQL",
                "version": str(mysql_version),
                "schema_revision": str(schema_revision) if schema_revision is not None else None,
                "connection_pool": "NullPool",
                "threads_connected_before": (
                    int(threads_connected_before_row[1])
                    if threads_connected_before_row is not None
                    else None
                ),
                "threads_connected_after": (
                    int(threads_connected_after_row[1])
                    if threads_connected_after_row is not None
                    else None
                ),
            },
            "fixture": {
                "version": FIXTURE_VERSION,
                "instrument_count": 100,
                "llm": "deterministic-none",
                "cache": {"applicable": False, "reason": "fixed in-memory provider fixture"},
            },
            "configuration": {
                "schedule_max_batch": 100,
                "worker_concurrency": 4,
                "per_source_concurrency": 2,
                "config_hash_without_secrets": hashlib.sha256(
                    b"schedule_max_batch=100;worker_concurrency=4;per_source_concurrency=2"
                ).hexdigest(),
            },
            "latency_seconds": {
                "warmup_count": 0,
                "measured_count": len(runner.claim_durations_seconds),
                "batch": batch_elapsed_seconds,
                "p50": nearest_rank_percentile(runner.claim_durations_seconds, 0.50),
                "p95": nearest_rank_percentile(runner.claim_durations_seconds, 0.95),
                "p99": nearest_rank_percentile(runner.claim_durations_seconds, 0.99),
                "max": max(runner.claim_durations_seconds),
                "error_rate": status_counts.get("FAILED", 0) / 100,
            },
            "resources": {
                "before": resources_before,
                "after": resources_after,
                "cpu_user_seconds_delta": resources_after["cpu_user_seconds"]
                - resources_before["cpu_user_seconds"],
                "cpu_system_seconds_delta": resources_after["cpu_system_seconds"]
                - resources_before["cpu_system_seconds"],
            },
            "concurrency": {
                "worker_peak": runner.max_active,
                "source_peak": data.max_active,
                "source_collections": data.collection_count,
            },
            "queue": {
                "claimed_count": claimed_count,
                "due_remaining": int(due_remaining or 0),
                "leased_count": leased_count,
                "retry_pending_count": retry_pending_count,
                "nonterminal_run_count": nonterminal_count,
                "run_status_counts": dict(status_counts),
                "pending_outcome_count": int(pending_outcomes or 0),
            },
            "side_effects": {
                "interactive_task_count": int(task_count or 0),
                "report_count": int(report_count or 0),
            },
        }
    finally:
        await engine.dispose()


def main() -> int:
    args = _parse_args()
    try:
        validate_disposable_mysql_url(args.database_url)
        if not args.confirm_disposable:
            raise ValueError("--confirm-disposable is required")
        if args.source_delay_ms <= 0:
            raise ValueError("--source-delay-ms must be positive")
        # Settings are imported only inside _run_profile, after this explicit
        # target URL is placed in the process environment.
        os.environ["DATABASE_URL"] = args.database_url
        os.environ["AI_CHAT_ENABLED"] = "false"
        result = asyncio.run(_run_profile(args.database_url, args.source_delay_ms / 1000.0))
        _write_result(result, args.output)
        if not result["passed"]:
            print("CAPACITY profile failed; inspect the JSON evidence above.", file=sys.stderr)
            return 1
        return 0
    except Exception as exc:
        print(f"CAPACITY profile could not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
