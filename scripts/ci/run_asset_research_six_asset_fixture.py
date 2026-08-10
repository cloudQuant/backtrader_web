#!/usr/bin/env python3
"""Run six Iteration 191 asset tasks through a disposable MySQL schema.

This acceptance profile runs one deterministic fixture task for each public
asset type: bond, fund, futures, option, FX and crypto.  It deliberately
refuses shared schemas and never calls an external market-data provider.  Its
results prove persistence and lifecycle contracts only; they are not market
data, investment advice, model validation, or permission to trade.

The caller must create an empty disposable MySQL database, run
``alembic upgrade head`` against it, then pass that exact URL together with
``--confirm-disposable``.  This command never creates or drops schemas.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "src" / "backend"
DISPOSABLE_DATABASE_RE = re.compile(r"^codex_iter191_six_asset_[A-Za-z0-9_]{1,48}$")
SOURCE_ID = "iter191-six-asset-fixture-source"
FIXTURE_VERSION = "iter191-six-asset-fixture-v1"
ASSET_TYPES = ("bond", "fund", "futures", "option", "fx", "crypto")
REQUIRED_TABLES = frozenset(
    {
        "alembic_version",
        "asset_analysis_reports",
        "asset_analysis_tasks",
        "asset_data_source_registry",
        "asset_instruments",
        "asset_signal_outcomes",
        "asset_signal_predictions",
        "asset_signal_runs",
        "asset_source_snapshots",
        "users",
    }
)
EXPECTED_OUTCOME_KINDS = {
    "bond": {
        "bond.executable_total_return",
        "bond.valuation_total_return",
        "bond.credit_event",
    },
    "fund": {"fund.etf_market_return", "fund.dealing_event"},
    "futures": {
        "futures.contract_pnl",
        "futures.roll_aware_pnl",
        "futures.close_avoided_loss",
    },
    "option": {
        "option.underlying_direction",
        "option.iv_direction",
        "option.exact_contract_net_profit",
        "option.close_avoided_loss",
    },
    "fx": {"fx.direction_pnl", "fx.action_utility", "fx.risk_path"},
    "crypto": {"crypto.spot_pnl", "crypto.benchmark_excess", "crypto.risk_path"},
}


def validate_disposable_mysql_url(raw_url: str) -> str:
    """Return a safe disposable database name or reject the target."""
    url = make_url(raw_url)
    if url.get_backend_name() != "mysql":
        raise ValueError("six-asset fixture runner only accepts a MySQL database URL")
    database = url.database or ""
    if not DISPOSABLE_DATABASE_RE.fullmatch(database):
        raise ValueError(
            "six-asset fixture runner requires a disposable database named "
            "codex_iter191_six_asset_<suffix>"
        )
    return database


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
    return parser.parse_args()


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


def _content_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


async def _run_profile(database_url: str) -> dict[str, Any]:
    """Seed and execute the six real task lifecycle paths against fixture data."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy import func, inspect, select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.models.asset_research import (
        AssetAnalysisReport,
        AssetAnalysisTask,
        AssetDataSourceRegistry,
        AssetInstrument,
        AssetSignalOutcome,
        AssetSignalPrediction,
        AssetSignalRun,
        AssetSourceSnapshot,
    )
    from app.models.user import User
    from app.schemas.asset_research import (
        AssetAnalysisCreateRequest,
        BondIdentityDetails,
        CryptoProductIdentityDetails,
        FundIdentityDetails,
        FuturesIdentityDetails,
        FxIdentityDetails,
        InstrumentIdentity,
        OptionIdentityDetails,
        RawAssetSnapshot,
    )
    from app.services.asset_research.orchestrator import AssetResearchOrchestrator
    from app.services.asset_research.plugins.option.pricing import (
        OptionPricingInput,
        calculate_option_analytics,
    )
    from app.services.asset_research.task_runner import AssetResearchTaskRunner

    def identity_for(asset_type: str, *, cutoff_at: datetime) -> InstrumentIdentity:
        common: dict[str, Any] = {
            "canonical_id": f"{asset_type}:fixture:iter191",
            "display_symbol": f"{asset_type.upper()}-FIXTURE",
            "name": f"Iteration 191 {asset_type} fixture",
            "venue": "FIXTURE",
            "currency": "USD",
            "timezone": "UTC",
            "identifier_type": "FIXTURE",
            "identifier_value": f"{asset_type}-fixture",
            "product_type": asset_type.upper(),
            "metadata_version": FIXTURE_VERSION,
        }
        if asset_type == "bond":
            return InstrumentIdentity(
                asset_type="bond",
                identity_level="PRODUCT",
                details=BondIdentityDetails(
                    bond_identity_kind="LISTING",
                    issuer_id="fixture-issuer",
                    maturity_date=(cutoff_at + timedelta(days=365 * 4)).date(),
                    settlement_calendar_id="FIXTURE",
                ),
                **common,
            )
        if asset_type == "fund":
            return InstrumentIdentity(
                asset_type="fund",
                identity_level="PRODUCT",
                details=FundIdentityDetails(
                    fund_identity_kind="LISTING",
                    fund_id="fixture-fund",
                    share_class_id="fixture-share-class",
                    official_benchmark_id="fixture-benchmark",
                ),
                **common,
            )
        if asset_type == "futures":
            return InstrumentIdentity(
                asset_type="futures",
                identity_level="CONTRACT",
                details=FuturesIdentityDetails(
                    product_code="FUT",
                    contract_month="fixture",
                    expiry_at=cutoff_at + timedelta(days=120),
                    contract_multiplier=Decimal("300"),
                    trading_calendar_id="FIXTURE",
                ),
                **common,
            )
        if asset_type == "option":
            expiry_at = cutoff_at + timedelta(days=120)
            return InstrumentIdentity(
                asset_type="option",
                identity_level="CONTRACT",
                details=OptionIdentityDetails(
                    option_contract_id="option-fixture",
                    exchange="FIXTURE",
                    underlying_instrument_id="fixture-underlying",
                    underlying_contract_id="fixture-underlying-contract",
                    expiry_at=expiry_at,
                    last_trade_at=expiry_at,
                    strike=Decimal("100"),
                    option_right="CALL",
                    exercise_style="EUROPEAN",
                    contract_multiplier=Decimal("100"),
                    settlement_type="CASH",
                    deliverable="100 cash units",
                    quote_unit="USD_PER_UNIT",
                    tick_size=Decimal("0.01"),
                    trading_calendar_id="FIXTURE",
                    automatic_exercise_rule="EXERCISE_IF_ITM",
                    position_limit_rule="FIXTURE_LIMIT_V1",
                    margin_rule_version="FIXTURE_MARGIN_V1",
                ),
                **common,
            )
        if asset_type == "fx":
            return InstrumentIdentity(
                asset_type="fx",
                identity_level="PRODUCT",
                details=FxIdentityDetails(
                    base_currency="EUR",
                    quote_currency="USD",
                    settlement_type="SPOT",
                    settlement_currency="USD",
                    calendar_id="FX",
                    price_convention="EUR_PER_USD",
                ),
                **common,
            )
        return InstrumentIdentity(
            asset_type="crypto",
            identity_level="PRODUCT",
            details=CryptoProductIdentityDetails(
                base_asset_id="btc",
                quote_asset_id="usd",
                market_type="SPOT",
                linear_or_inverse="NOT_APPLICABLE",
            ),
            **common,
        )

    def option_chain_fields(cutoff_at: datetime, *, first_expiry: datetime) -> dict[str, Any]:
        policy: dict[str, float | int | str] = {
            "version": FIXTURE_VERSION,
            "min_expiries": 2,
            "min_strikes_per_expiry": 3,
            "min_calendar_pairs": 2,
            "max_quote_age_seconds": 60.0,
            "max_underlying_lag_seconds": 60.0,
            "max_relative_spread": 0.10,
            "min_visible_size": 1.0,
            "min_volume": 1.0,
            "min_open_interest": 1.0,
            "parity_tolerance": 0.02,
            "static_arbitrage_tolerance": 1e-8,
        }
        records: list[dict[str, float | str]] = []
        for expiry_index, expiry_at in enumerate((first_expiry, first_expiry + timedelta(days=90))):
            time_to_expiry = (expiry_at - cutoff_at).total_seconds() / (365.0 * 24 * 60 * 60)
            for strike in (90.0, 100.0, 110.0):
                for option_right in ("CALL", "PUT"):
                    analytics = calculate_option_analytics(
                        OptionPricingInput(
                            model="BSM",
                            option_right=option_right,
                            underlying_price=100.0,
                            strike=strike,
                            time_to_expiry_years=time_to_expiry,
                            risk_free_rate=0.05,
                            dividend_yield=0.0,
                            volatility=0.20 + 0.03 * expiry_index,
                        )
                    )
                    if analytics.theoretical_value is None:
                        raise RuntimeError("fixture option pricing returned no theoretical value")
                    records.append(
                        {
                            "expiry_at": expiry_at.isoformat(),
                            "strike": strike,
                            "option_right": option_right,
                            "bid": analytics.theoretical_value * 0.995,
                            "ask": analytics.theoretical_value * 1.005,
                            "bid_size": 100.0,
                            "ask_size": 100.0,
                            "volume": 500.0,
                            "open_interest": 1000.0,
                            "quote_at": cutoff_at.isoformat(),
                        }
                    )
        return {
            "chain_quality_policy": policy,
            "underlying_quote_at": cutoff_at.isoformat(),
            "cost_snapshot": {
                "cost_model_version": FIXTURE_VERSION,
                "commission_rate": 0.002,
                "exchange_fee_rate": 0.001,
                "entry_slippage_rate": 0.002,
                "exit_slippage_rate": 0.002,
                "funding_cost_rate": 0.001,
                "exercise_settlement_cost_rate": 0.001,
                "other_cost_rate": 0.001,
            },
            "chain": records,
        }

    def raw_for(identity: InstrumentIdentity, *, cutoff_at: datetime) -> RawAssetSnapshot:
        asset_type = identity.asset_type
        requirements = {
            "bond": ["price", "official_valuation", "curve", "cashflows"],
            "fund": ["official_nav", "benchmark"],
            "futures": ["price", "contract_calendar"],
            "option": ["price", "option_chain", "contract_terms"],
            "fx": ["price", "calendar", "price_convention"],
            "crypto": ["price", "venue"],
        }
        fields: dict[str, Any] = {
            "bond": {
                "bond": {
                    "maturity_date": (cutoff_at + timedelta(days=365 * 4)).date().isoformat(),
                    "cashflows": [
                        {
                            "date": (cutoff_at + timedelta(days=365 * 4)).date().isoformat(),
                            "amount": 100,
                        }
                    ],
                    "curve": "USD_GOVT_FIXTURE",
                    "benchmark": "FIXTURE_BOND_INDEX",
                }
            },
            "fund": {
                "fund": {
                    "fund_type": "ETF",
                    "official_nav": 101.0,
                    "benchmark": "FIXTURE_BENCHMARK",
                    "fee_schedule": "fixture",
                    "holdings_as_of": (cutoff_at - timedelta(days=1)).date().isoformat(),
                }
            },
            "futures": {"futures": {"contract_calendar": "FIXTURE", "contract_terms": "fixture"}},
            "fx": {"fx": {"completed_bar": True, "price_convention": "EUR_PER_USD"}},
            "crypto": {"crypto": {"venue_verified": True, "depth_1pct": 1_000_000}},
        }
        snapshot: dict[str, Any] = {"price": 102.0}
        if asset_type == "bond":
            snapshot.update({"official_valuation": 102.0, "bid": 101.9, "ask": 102.1})
        if asset_type in {"futures", "option", "fx", "crypto"}:
            snapshot.update({"bid": 101.9, "ask": 102.1})
        if asset_type == "option":
            details = identity.details
            if not isinstance(details, OptionIdentityDetails):
                raise RuntimeError("option fixture identity lost its contract terms")
            fields["option"] = {
                "option": {
                    "contract_terms": "fixture",
                    "underlying_price": 100.0,
                    "underlying_kind": "SPOT",
                    "risk_free_rate": 0.05,
                    "dividend_yield": 0.0,
                    "implied_volatility": 0.20,
                    **option_chain_fields(cutoff_at, first_expiry=details.expiry_at),
                }
            }
            snapshot.update(
                {
                    "price": 5.90,
                    "bid": 5.80,
                    "ask": 6.00,
                    "quote_at": cutoff_at.isoformat(),
                }
            )
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version=FIXTURE_VERSION,
            raw_fields={"snapshot": snapshot, **fields[asset_type]},
            history_rows=[
                {"date": (cutoff_at - timedelta(days=1)).date().isoformat(), "close": 100.0},
                {"date": cutoff_at.date().isoformat(), "close": 102.0},
            ],
            source_manifest={
                "source_id": SOURCE_ID,
                "provider": SOURCE_ID,
                "capabilities": requirements[asset_type],
                "fixture_only": True,
            },
            license_tags=["FIXTURE_ONLY"],
            content_hash=_content_hash(
                FIXTURE_VERSION,
                identity.canonical_id,
                cutoff_at.isoformat(),
            ),
        )

    class SixAssetFixtureData:
        """Server-declared deterministic source used only by this disposable profile."""

        declared_source_ids = (SOURCE_ID,)

        def __init__(self) -> None:
            self.collection_count = 0

        async def collect(
            self, identity: InstrumentIdentity, *, cutoff_at: datetime
        ) -> RawAssetSnapshot:
            self.collection_count += 1
            return raw_for(identity, cutoff_at=cutoff_at)

    engine = create_async_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    started_at = datetime.now(timezone.utc)
    try:
        async with engine.connect() as connection:
            table_names = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
            missing_tables = sorted(REQUIRED_TABLES - table_names)
            if missing_tables:
                raise RuntimeError(
                    "target schema is not migrated to the Iteration 191 head; missing tables: "
                    + ", ".join(missing_tables)
                )
            schema_revision = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one_or_none()
            mysql_version = (await connection.execute(text("SELECT VERSION()"))).scalar_one()

        async with session_maker() as db:
            existing_counts = {
                "tasks": int(
                    await db.scalar(select(func.count()).select_from(AssetAnalysisTask)) or 0
                ),
                "instruments": int(
                    await db.scalar(select(func.count()).select_from(AssetInstrument)) or 0
                ),
                "snapshots": int(
                    await db.scalar(select(func.count()).select_from(AssetSourceSnapshot)) or 0
                ),
                "predictions": int(
                    await db.scalar(select(func.count()).select_from(AssetSignalPrediction)) or 0
                ),
            }
            if any(existing_counts.values()):
                raise RuntimeError(
                    "target disposable schema is not empty for this acceptance profile: "
                    + json.dumps(existing_counts, sort_keys=True)
                )

            source = AssetDataSourceRegistry(
                source_id=SOURCE_ID,
                asset_types=list(ASSET_TYPES),
                jurisdictions=["GLOBAL"],
                license_status="RESEARCH_APPROVED",
                allowed_uses=["RESEARCH_ONLY"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy=FIXTURE_VERSION,
                effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                freshness_sla={},
                enabled=True,
            )
            user = User(
                username="iter191_six_asset_fixture",
                email="iter191-six-asset-fixture@example.test",
                hashed_password="fixture-not-a-secret",
            )
            db.add_all([source, user])
            await db.flush()

            data = SixAssetFixtureData()
            service = AssetResearchOrchestrator(db, data_adapter=data)
            identity_cutoff = datetime.now(timezone.utc)
            identities = {
                asset_type: identity_for(asset_type, cutoff_at=identity_cutoff)
                for asset_type in ASSET_TYPES
            }
            for identity in identities.values():
                await service.persist_identity(identity)
            tasks = []
            for asset_type, identity in identities.items():
                tasks.append(
                    await service.create_pending(
                        user_id=user.id,
                        request=AssetAnalysisCreateRequest(
                            asset_type=asset_type,
                            canonical_id=identity.canonical_id,
                        ),
                    )
                )
            await db.commit()

        task_ids = [task.id for task in tasks]
        runner = AssetResearchTaskRunner(
            session_maker=session_maker,
            orchestrator_factory=lambda db: AssetResearchOrchestrator(db, data_adapter=data),
            lease_seconds=60,
            max_batch=len(ASSET_TYPES),
            max_concurrency=3,
        )
        claimed_count = await runner.run_due(now=datetime.now(timezone.utc))

        async with session_maker() as db:
            tasks = list(
                (
                    await db.execute(
                        select(AssetAnalysisTask)
                        .where(AssetAnalysisTask.id.in_(task_ids))
                        .order_by(AssetAnalysisTask.asset_type)
                    )
                ).scalars()
            )
            reports = list(
                (
                    await db.execute(
                        select(AssetAnalysisReport).where(AssetAnalysisReport.task_id.in_(task_ids))
                    )
                ).scalars()
            )
            runs = list(
                (
                    await db.execute(
                        select(AssetSignalRun).where(AssetSignalRun.task_id.in_(task_ids))
                    )
                ).scalars()
            )
            prediction_ids = [run.prediction_id for run in runs if run.prediction_id]
            predictions = list(
                (
                    await db.execute(
                        select(AssetSignalPrediction).where(
                            AssetSignalPrediction.id.in_(prediction_ids)
                        )
                    )
                ).scalars()
            )
            outcomes = list(
                (
                    await db.execute(
                        select(AssetSignalOutcome).where(
                            AssetSignalOutcome.prediction_id.in_(prediction_ids)
                        )
                    )
                ).scalars()
            )
            snapshots = list(
                (
                    await db.execute(
                        select(AssetSourceSnapshot).where(
                            AssetSourceSnapshot.canonical_id.in_(
                                [identity.canonical_id for identity in identities.values()]
                            )
                        )
                    )
                ).scalars()
            )

        task_by_id = {task.id: task for task in tasks}
        prediction_by_id = {prediction.id: prediction for prediction in predictions}
        reports_by_task = {report.task_id: report for report in reports}
        runs_by_task = {run.task_id: run for run in runs if run.task_id is not None}
        outcomes_by_prediction: dict[str, set[str]] = defaultdict(set)
        for outcome in outcomes:
            outcomes_by_prediction[outcome.prediction_id].add(outcome.outcome_kind)
        snapshots_by_asset = {snapshot.asset_type: snapshot for snapshot in snapshots}

        violations: list[str] = []
        if claimed_count != len(ASSET_TYPES):
            violations.append(f"claimed_count={claimed_count}, expected={len(ASSET_TYPES)}")
        if len(task_by_id) != len(ASSET_TYPES):
            violations.append(f"task_count={len(task_by_id)}, expected={len(ASSET_TYPES)}")
        if len(runs) != len(ASSET_TYPES):
            violations.append(f"run_count={len(runs)}, expected={len(ASSET_TYPES)}")
        if len(predictions) != len(ASSET_TYPES):
            violations.append(f"prediction_count={len(predictions)}, expected={len(ASSET_TYPES)}")
        if len(reports) != len(ASSET_TYPES):
            violations.append(f"report_count={len(reports)}, expected={len(ASSET_TYPES)}")
        if len(snapshots) != len(ASSET_TYPES):
            violations.append(f"snapshot_count={len(snapshots)}, expected={len(ASSET_TYPES)}")

        asset_summaries: list[dict[str, Any]] = []
        for asset_type in ASSET_TYPES:
            task = next((item for item in tasks if item.asset_type == asset_type), None)
            if task is None:
                violations.append(f"{asset_type}: missing task")
                continue
            if task.status != "SUCCEEDED" or task.progress != 100 or task.error_code is not None:
                violations.append(
                    f"{asset_type}: task status={task.status}, progress={task.progress}, "
                    f"error={task.error_code}"
                )
            if task.completed_at is None or task.attempt_count != 1:
                violations.append(
                    f"{asset_type}: completed_at={task.completed_at}, "
                    f"attempt_count={task.attempt_count}"
                )
            if any(
                value is not None
                for value in (task.lease_token, task.lease_expires_at, task.lease_heartbeat_at)
            ):
                violations.append(f"{asset_type}: terminal task still holds a lease")

            report = reports_by_task.get(task.id)
            if report is None or not report.rendered_markdown or not report.sections_json:
                violations.append(f"{asset_type}: missing or empty report")
            run = runs_by_task.get(task.id)
            if run is None or run.status != "SUCCEEDED" or run.prediction_id is None:
                violations.append(f"{asset_type}: missing successful run with prediction")
                prediction = None
            else:
                prediction = prediction_by_id.get(run.prediction_id)
            if prediction is None:
                violations.append(f"{asset_type}: missing immutable prediction")
                outcome_kinds: set[str] = set()
                published: dict[str, Any] = {}
            else:
                outcome_kinds = outcomes_by_prediction[prediction.id]
                published = dict(prediction.published_decision_json or {})
                if prediction.quality_status != "ELIGIBLE":
                    violations.append(
                        f"{asset_type}: fixture quality status={prediction.quality_status}, "
                        "expected=ELIGIBLE"
                    )
                if (
                    asset_type not in {"fx", "crypto"}
                    and prediction.actionability != "RESEARCH_ONLY"
                ):
                    violations.append(
                        f"{asset_type}: fixture actionability={prediction.actionability}, "
                        "expected=RESEARCH_ONLY"
                    )
                if prediction.actionability == "ACTIONABLE":
                    violations.append(f"{asset_type}: fixture produced an actionable decision")
                if published.get("execution_disabled") is not True:
                    violations.append(f"{asset_type}: publication did not disable execution")
                if published.get("actionability") == "ACTIONABLE":
                    violations.append(f"{asset_type}: published decision is actionable")
                if outcome_kinds != EXPECTED_OUTCOME_KINDS[asset_type]:
                    violations.append(
                        f"{asset_type}: outcome kinds={sorted(outcome_kinds)}, "
                        f"expected={sorted(EXPECTED_OUTCOME_KINDS[asset_type])}"
                    )
            snapshot = snapshots_by_asset.get(asset_type)
            if snapshot is None:
                violations.append(f"{asset_type}: missing persisted raw snapshot")
                source_status = None
            else:
                source_status = (snapshot.source_manifest_json or {}).get("source_registry_status")
                if source_status != "ACTIVE":
                    violations.append(f"{asset_type}: source registry status={source_status}")
            asset_summaries.append(
                {
                    "asset_type": asset_type,
                    "task_status": task.status,
                    "run_status": run.status if run is not None else None,
                    "report_present": report is not None,
                    "prediction_actionability": prediction.actionability if prediction else None,
                    "published_recommendation": published.get("recommendation"),
                    "published_execution_disabled": published.get("execution_disabled"),
                    "outcome_kinds": sorted(outcome_kinds),
                    "source_registry_status": source_status,
                }
            )

        return {
            "iteration": 191,
            "profile": "SIX_ASSET_INTERACTIVE_TASK_FIXTURE",
            "passed": not violations,
            "violations": violations,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "timezone": "UTC",
            "database": {
                "vendor": "MySQL",
                "version": str(mysql_version),
                "schema_revision": str(schema_revision) if schema_revision is not None else None,
                "connection_pool": "NullPool",
                "disposable_schema": True,
            },
            "fixture": {
                "version": FIXTURE_VERSION,
                "source_id": SOURCE_ID,
                "source_mode": "in_memory_deterministic_fixture",
                "external_network_used": False,
                "market_data_used": False,
                "investment_advice": False,
                "execution_enabled": False,
            },
            "task_runner": {
                "asset_types": list(ASSET_TYPES),
                "claimed_count": claimed_count,
                "worker_concurrency": 3,
                "source_collections": data.collection_count,
                "task_status_counts": dict(Counter(task.status for task in tasks)),
                "run_status_counts": dict(Counter(run.status for run in runs)),
            },
            "records": {
                "tasks": len(tasks),
                "snapshots": len(snapshots),
                "predictions": len(predictions),
                "outcomes": len(outcomes),
                "reports": len(reports),
            },
            "assets": asset_summaries,
        }
    finally:
        await engine.dispose()


def main() -> int:
    args = _parse_args()
    try:
        validate_disposable_mysql_url(args.database_url)
        if not args.confirm_disposable:
            raise ValueError("--confirm-disposable is required")
        os.environ["DATABASE_URL"] = args.database_url
        os.environ["AI_CHAT_ENABLED"] = "false"
        result = asyncio.run(_run_profile(args.database_url))
        _write_result(result, args.output)
        if not result["passed"]:
            print(
                "six-asset fixture profile failed; inspect the JSON evidence above.",
                file=sys.stderr,
            )
            return 1
        return 0
    except Exception as exc:
        print(f"six-asset fixture profile could not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
