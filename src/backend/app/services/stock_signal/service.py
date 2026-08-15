"""Persistence and user-facing reads for versioned stock-signal predictions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_signal import StockSignalPrediction, StockSignalRun
from app.services.asset_research.stock_dual_write import (
    DualWriteMode,
    DualWriteOutcome,
    StockDualWriteCoordinator,
)
from app.services.stock_signal.decision_policy import SignalPolicy
from app.services.stock_signal.features import calculate_features
from app.services.stock_signal.outcomes import OutcomeEvaluation, evaluate_outcome
from app.services.stock_signal.performance import build_performance_summary
from app.services.stock_signal.quality import DataQualityGate
from app.services.stock_signal.types import ACTION_LABELS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class StockSignalService:
    """Create immutable signal snapshots and expose scoped history/scorecards."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        policy: SignalPolicy | None = None,
        quality_gate: DataQualityGate | None = None,
    ) -> None:
        self.db = db
        self.policy = policy or SignalPolicy()
        self.quality_gate = quality_gate or DataQualityGate()

    @staticmethod
    def user_scope(user_id: str) -> str:
        return f"user:{user_id}"

    async def create_prediction(
        self,
        *,
        snapshot: dict[str, Any],
        symbol: str,
        market_type: str,
        as_of_date: date,
        owner_scope: str,
        source: str,
        universe_code: str,
        next_trading_date: date | None = None,
        run_id: str | None = None,
    ) -> StockSignalPrediction:
        """Persist exactly one deterministic prediction for a source/version/date key."""
        rows = (snapshot.get("history") or {}).get("rows") or []
        features = calculate_features(rows if isinstance(rows, list) else [])
        quality = self.quality_gate.assess(
            snapshot=snapshot,
            features=features,
            as_of_date=as_of_date,
        )
        decision = self.policy.decide(features=features, quality=quality)
        prediction_key = _digest(
            {
                "source": source,
                "owner_scope": owner_scope,
                "universe_code": universe_code,
                "symbol": symbol.upper(),
                "as_of_date": as_of_date.isoformat(),
                "feature_version": decision.feature_version,
                "decision_policy_version": decision.decision_policy_version,
                "model_version": decision.model_version,
            }
        )
        existing = await self.db.scalar(
            select(StockSignalPrediction).where(
                StockSignalPrediction.prediction_key == prediction_key
            )
        )
        if existing is not None:
            return existing

        now = _now()
        info = snapshot.get("info") or {}
        prediction = StockSignalPrediction(
            prediction_key=prediction_key,
            run_id=run_id,
            owner_scope=owner_scope,
            source=source,
            universe_code=universe_code,
            symbol=symbol.upper(),
            symbol_name=info.get("name") or (snapshot.get("quote") or {}).get("name"),
            market_type=market_type,
            as_of_date=as_of_date,
            as_of_at=now,
            available_at=now,
            next_trading_date=next_trading_date,
            signal_action=decision.action,
            confidence_score=decision.confidence_score,
            buy_probability=decision.buy_probability,
            sell_probability=decision.sell_probability,
            watch_probability=decision.watch_probability,
            expected_excess_return=decision.expected_excess_return,
            risk_score=decision.risk_score,
            eligibility_status=decision.eligibility_status,
            quality_reasons_json=list(decision.quality_reasons),
            data_freshness_json=quality.freshness,
            feature_version=decision.feature_version,
            decision_policy_version=decision.decision_policy_version,
            model_version=decision.model_version,
            feature_snapshot_json=features.snapshot(),
            policy_snapshot_json=decision.policy_snapshot,
            source_snapshot_hash=_digest(snapshot),
            outcome_status="pending",
        )
        try:
            async with self.db.begin_nested():
                self.db.add(prediction)
                await self.db.flush()
        except IntegrityError:
            existing = await self.db.scalar(
                select(StockSignalPrediction).where(
                    StockSignalPrediction.prediction_key == prediction_key
                )
            )
            if existing is not None:
                return existing
            raise
        return prediction

    async def create_prediction_with_shadow(
        self,
        *,
        snapshot: dict[str, Any],
        symbol: str,
        market_type: str,
        as_of_date: date,
        owner_scope: str,
        source: str,
        universe_code: str,
        next_trading_date: date | None = None,
        run_id: str | None = None,
        shadow_write: Callable[[StockSignalPrediction], Awaitable[None]],
        dual_write_mode: str = "OFF",
    ) -> tuple[StockSignalPrediction, DualWriteOutcome]:
        """Create a legacy prediction and apply OFF/SHADOW/ENFORCE shadow policy."""
        prediction = await self.create_prediction(
            snapshot=snapshot,
            symbol=symbol,
            market_type=market_type,
            as_of_date=as_of_date,
            owner_scope=owner_scope,
            source=source,
            universe_code=universe_code,
            next_trading_date=next_trading_date,
            run_id=run_id,
        )
        coordinator = StockDualWriteCoordinator(DualWriteMode(dual_write_mode.upper()))

        async def primary() -> StockSignalPrediction:
            return prediction

        outcome = await coordinator.write(
            primary_write=primary,
            shadow_write=lambda: shadow_write(prediction),
        )
        return prediction, outcome

    async def attach_report(self, *, prediction_id: str, report_id: str) -> None:
        prediction = await self.db.get(StockSignalPrediction, prediction_id)
        if prediction is not None and prediction.report_id is None:
            prediction.report_id = report_id
            await self.db.flush()

    async def get_visible_history(
        self,
        *,
        user_id: str,
        symbol: str,
        source: str | None = None,
        limit: int = 30,
        cursor: str | None = None,
    ) -> tuple[list[StockSignalPrediction], str | None]:
        statement = select(StockSignalPrediction).where(
            StockSignalPrediction.symbol == symbol.upper(),
            or_(
                StockSignalPrediction.owner_scope == "system",
                StockSignalPrediction.owner_scope == self.user_scope(user_id),
            ),
        )
        if source:
            statement = statement.where(StockSignalPrediction.source == source)
        if cursor:
            cursor_parts = cursor.split("|", 1)
            try:
                cursor_date = date.fromisoformat(cursor_parts[0])
            except ValueError:
                cursor_date = None
            if cursor_date is not None:
                if len(cursor_parts) == 2 and cursor_parts[1]:
                    statement = statement.where(
                        or_(
                            StockSignalPrediction.as_of_date < cursor_date,
                            and_(
                                StockSignalPrediction.as_of_date == cursor_date,
                                StockSignalPrediction.id < cursor_parts[1],
                            ),
                        )
                    )
                else:
                    # Preserve compatibility with date-only cursors issued before v1.1.
                    statement = statement.where(StockSignalPrediction.as_of_date < cursor_date)
        rows = list(
            (
                await self.db.execute(
                    statement.order_by(
                        desc(StockSignalPrediction.as_of_date), desc(StockSignalPrediction.id)
                    ).limit(max(1, min(limit, 100)) + 1)
                )
            )
            .scalars()
            .all()
        )
        visible = rows[:limit]
        next_cursor = (
            f"{visible[-1].as_of_date.isoformat()}|{visible[-1].id}"
            if len(rows) > limit and visible
            else None
        )
        return visible, next_cursor

    async def get_visible_summary(
        self, *, user_id: str, symbol: str, horizon: int = 20
    ) -> dict[str, Any]:
        statement = select(StockSignalPrediction).where(
            StockSignalPrediction.symbol == symbol.upper(),
            or_(
                StockSignalPrediction.owner_scope == "system",
                StockSignalPrediction.owner_scope == self.user_scope(user_id),
            ),
        )
        records = list((await self.db.execute(statement)).scalars().all())
        return build_performance_summary(records, symbol=symbol.upper(), horizon=horizon)

    async def latest_public_run(self) -> StockSignalRun | None:
        return await self.db.scalar(
            select(StockSignalRun)
            .where(StockSignalRun.owner_scope == "system")
            .order_by(desc(StockSignalRun.as_of_date), desc(StockSignalRun.created_at))
            .limit(1)
        )

    async def get_all_system_predictions(
        self,
        *,
        limit: int = 100,
    ) -> list[StockSignalPrediction]:
        """Return bounded legacy system records for structured compatibility audit."""
        return list(
            (
                await self.db.execute(
                    select(StockSignalPrediction)
                    .where(StockSignalPrediction.owner_scope == "system")
                    .order_by(
                        desc(StockSignalPrediction.as_of_date), desc(StockSignalPrediction.id)
                    )
                    .limit(max(1, min(limit, 1_000)))
                )
            )
            .scalars()
            .all()
        )

    async def opening_action_preview(
        self, *, held_symbols: list[str], as_of_date: date | None = None
    ) -> tuple[date, date | None, list[dict[str, Any]]]:
        target_date = as_of_date
        if target_date is None:
            target_date = await self.db.scalar(
                select(StockSignalPrediction.as_of_date)
                .where(StockSignalPrediction.owner_scope == "system")
                .order_by(desc(StockSignalPrediction.as_of_date))
                .limit(1)
            )
        if target_date is None:
            return date.today(), None, []
        records = list(
            (
                await self.db.execute(
                    select(StockSignalPrediction)
                    .where(
                        StockSignalPrediction.owner_scope == "system",
                        StockSignalPrediction.as_of_date == target_date,
                    )
                    .order_by(StockSignalPrediction.symbol)
                )
            )
            .scalars()
            .all()
        )
        held = {symbol.upper() for symbol in held_symbols}
        actions: list[dict[str, Any]] = []
        next_date = None
        for record in records:
            next_date = next_date or record.next_trading_date
            if record.eligibility_status != "eligible":
                action = "NO_ACTION"
            elif record.symbol in held and record.signal_action == "SELL":
                action = "SELL_AT_OPEN"
            elif record.symbol not in held and record.signal_action == "BUY":
                action = "BUY_AT_OPEN"
            else:
                action = "NO_ACTION"
            actions.append(
                {
                    "prediction_id": record.id,
                    "symbol": record.symbol,
                    "symbol_name": record.symbol_name,
                    "signal_action": record.signal_action,
                    "action_label": ACTION_LABELS[record.signal_action],
                    "suggested_action": action,
                    "next_trading_date": record.next_trading_date,
                    "decision_policy_version": record.decision_policy_version,
                    "model_version": record.model_version,
                    "eligibility_status": record.eligibility_status,
                }
            )
        return target_date, next_date, actions

    async def apply_outcome(
        self,
        *,
        prediction: StockSignalPrediction,
        price_rows: list[dict[str, Any]],
        benchmark_rows: list[dict[str, Any]],
    ) -> OutcomeEvaluation:
        """Apply a forward-only outcome to a prediction without touching its inputs."""
        evaluation = evaluate_outcome(
            prediction_action=prediction.signal_action,
            next_trading_date=prediction.next_trading_date,
            price_rows=price_rows,
            benchmark_rows=benchmark_rows,
            policy_snapshot=dict(prediction.policy_snapshot_json or {}),
        )
        prediction.outcome_status = evaluation.status
        prediction.outcome_reason = evaluation.reason
        prediction.entry_date = evaluation.entry_date
        prediction.entry_price = evaluation.entry_price
        for horizon in (1, 5, 20):
            setattr(
                prediction, f"horizon_{horizon}d_return", evaluation.horizon_returns.get(horizon)
            )
            setattr(
                prediction,
                f"benchmark_{horizon}d_return",
                evaluation.benchmark_returns.get(horizon),
            )
            setattr(prediction, f"excess_{horizon}d_return", evaluation.excess_returns.get(horizon))
        prediction.buy_is_correct_20d = evaluation.buy_is_correct_20d
        prediction.sell_is_correct_20d = evaluation.sell_is_correct_20d
        if evaluation.status in {"partial", "scored", "unscorable"}:
            prediction.scored_at = _now()
        await self.db.flush()
        return evaluation

    @staticmethod
    def record_payload(record: StockSignalPrediction) -> dict[str, Any]:
        return {
            "id": record.id,
            "source": record.source,
            "universe_code": record.universe_code,
            "symbol": record.symbol,
            "symbol_name": record.symbol_name,
            "market_type": record.market_type,
            "as_of_date": record.as_of_date,
            "available_at": record.available_at,
            "next_trading_date": record.next_trading_date,
            "signal_action": record.signal_action,
            "action_label": ACTION_LABELS[record.signal_action],
            "confidence_score": record.confidence_score,
            "risk_score": record.risk_score,
            "expected_excess_return": record.expected_excess_return,
            "eligibility_status": record.eligibility_status,
            "quality_reasons": list(record.quality_reasons_json or []),
            "feature_version": record.feature_version,
            "decision_policy_version": record.decision_policy_version,
            "model_version": record.model_version,
            "outcome_status": record.outcome_status,
            "outcome_reason": record.outcome_reason,
            "entry_date": record.entry_date,
            "entry_price": record.entry_price,
            "horizon_1d_return": record.horizon_1d_return,
            "horizon_5d_return": record.horizon_5d_return,
            "horizon_20d_return": record.horizon_20d_return,
            "benchmark_20d_return": record.benchmark_20d_return,
            "excess_20d_return": record.excess_20d_return,
            "buy_is_correct_20d": record.buy_is_correct_20d,
            "sell_is_correct_20d": record.sell_is_correct_20d,
        }
