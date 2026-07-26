"""Persistence and access control for workspace-based paper runtimes."""

from __future__ import annotations

import base64
import binascii
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, and_, func, or_, select

from app.db.database import async_session_maker
from app.models.alerts import Alert, AlertStatus
from app.models.paper_runtime import (
    LiveHandoffReview,
    PaperEquitySnapshot,
    PaperReviewReport,
    RiskRule,
)
from app.models.paper_trading import Account
from app.models.workspace import StrategyUnit, Workspace


@dataclass(frozen=True)
class PaperRuntimeRiskDecision:
    """The durable result of a fail-closed paper-runtime risk evaluation."""

    allowed: bool
    reason: str | None = None
    rule_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PaperRuntimeSnapshotPage:
    """Cursor or deterministic-sample response for an equity curve request."""

    points: list[PaperEquitySnapshot]
    next_cursor: str | None
    sampled: bool
    sampling: str


class PaperRuntimeService:
    """Own C-direction runtime state without mixing it with the account-only engine."""

    async def get_runtime(
        self, user_id: str, instance_id: str
    ) -> tuple[Workspace, StrategyUnit] | None:
        """Resolve an owned workspace/unit by canonical paper runtime instance ID."""
        async with async_session_maker() as session:
            result = await session.execute(self._runtime_query(user_id, instance_id))
            row = result.one_or_none()
            return (row[0], row[1]) if row is not None else None

    @staticmethod
    def _runtime_query(user_id: str, instance_id: str) -> Select[tuple[Workspace, StrategyUnit]]:
        return (
            select(Workspace, StrategyUnit)
            .join(StrategyUnit, StrategyUnit.workspace_id == Workspace.id)
            .where(
                Workspace.user_id == user_id,
                StrategyUnit.trading_instance_id == instance_id,
            )
        )

    async def latest_snapshot(self, user_id: str, instance_id: str) -> PaperEquitySnapshot | None:
        """Return the latest snapshot only if the runtime belongs to the user."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(PaperEquitySnapshot)
                .where(
                    PaperEquitySnapshot.user_id == user_id,
                    PaperEquitySnapshot.instance_id == instance_id,
                )
                .order_by(PaperEquitySnapshot.observed_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def record_snapshot(
        self,
        user_id: str,
        instance_id: str,
        payload: dict[str, Any],
    ) -> PaperEquitySnapshot | None:
        """Write an idempotent runtime snapshot; return None when not owned."""
        runtime = await self.get_runtime(user_id, instance_id)
        if runtime is None:
            return None
        workspace, unit = runtime
        observed_at = payload.get("observed_at") or datetime.now(timezone.utc)
        source = str(payload.get("source") or "mark_to_market")
        async with async_session_maker() as session:
            existing = await session.execute(
                select(PaperEquitySnapshot).where(
                    PaperEquitySnapshot.instance_id == instance_id,
                    PaperEquitySnapshot.source == source,
                    PaperEquitySnapshot.observed_at == observed_at,
                )
            )
            snapshot = existing.scalar_one_or_none()
            values = {
                "total_equity": float(payload["total_equity"]),
                "cash": float(payload.get("cash") or 0.0),
                "position_value": float(payload.get("position_value") or 0.0),
                "unrealized_pnl": float(payload.get("unrealized_pnl") or 0.0),
                "realized_pnl": float(payload.get("realized_pnl") or 0.0),
                "metadata_json": dict(payload.get("metadata") or {}),
            }
            if snapshot is None:
                snapshot = PaperEquitySnapshot(
                    user_id=user_id,
                    workspace_id=workspace.id,
                    unit_id=unit.id,
                    instance_id=instance_id,
                    observed_at=observed_at,
                    source=source,
                    **values,
                )
                session.add(snapshot)
            else:
                for key, value in values.items():
                    setattr(snapshot, key, value)
            await session.commit()
            await session.refresh(snapshot)
            return snapshot

    async def list_snapshots(
        self,
        user_id: str,
        instance_id: str,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        max_points: int = 1000,
    ) -> list[PaperEquitySnapshot] | None:
        """List owned snapshots, evenly down-sampling only after deterministic ordering."""
        if await self.get_runtime(user_id, instance_id) is None:
            return None
        async with async_session_maker() as session:
            query = select(PaperEquitySnapshot).where(
                PaperEquitySnapshot.user_id == user_id,
                PaperEquitySnapshot.instance_id == instance_id,
            )
            if start_at is not None:
                query = query.where(PaperEquitySnapshot.observed_at >= start_at)
            if end_at is not None:
                query = query.where(PaperEquitySnapshot.observed_at <= end_at)
            result = await session.execute(query.order_by(PaperEquitySnapshot.observed_at.asc()))
            points = list(result.scalars().all())
        if len(points) <= max_points:
            return points
        step = (len(points) - 1) / (max_points - 1) if max_points > 1 else len(points)
        indexes = {round(index * step) for index in range(max_points)}
        return [point for index, point in enumerate(points) if index in indexes]

    async def list_snapshot_page(
        self,
        user_id: str,
        instance_id: str,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        max_points: int = 1000,
        cursor: str | None = None,
    ) -> PaperRuntimeSnapshotPage | None:
        """Return a cursor page or a bounded full-window deterministic sample.

        The first request favors an evenly sampled overview. Supplying the
        opaque cursor switches to a stable, unsampled chronological page for
        inspection/export. This keeps the overview bounded without pretending
        that a reduced point set is the raw ledger.
        """
        if await self.get_runtime(user_id, instance_id) is None:
            return None
        limit = max(1, min(int(max_points), 1000))
        cursor_values = self._decode_cursor(cursor) if cursor else None
        async with async_session_maker() as session:
            query = select(PaperEquitySnapshot).where(
                PaperEquitySnapshot.user_id == user_id,
                PaperEquitySnapshot.instance_id == instance_id,
            )
            if start_at is not None:
                query = query.where(PaperEquitySnapshot.observed_at >= start_at)
            if end_at is not None:
                query = query.where(PaperEquitySnapshot.observed_at <= end_at)
            if cursor_values is not None:
                observed_at, snapshot_id = cursor_values
                query = query.where(
                    or_(
                        PaperEquitySnapshot.observed_at > observed_at,
                        and_(
                            PaperEquitySnapshot.observed_at == observed_at,
                            PaperEquitySnapshot.id > snapshot_id,
                        ),
                    )
                )
                result = await session.execute(
                    query.order_by(
                        PaperEquitySnapshot.observed_at.asc(),
                        PaperEquitySnapshot.id.asc(),
                    ).limit(limit + 1)
                )
                rows = list(result.scalars().all())
                has_more = len(rows) > limit
                points = rows[:limit]
                return PaperRuntimeSnapshotPage(
                    points=points,
                    next_cursor=self._encode_cursor(points[-1]) if has_more and points else None,
                    sampled=False,
                    sampling="none",
                )

            count = await session.scalar(select(func.count()).select_from(query.subquery()))
            total = int(count or 0)
            if total <= limit:
                result = await session.execute(
                    query.order_by(
                        PaperEquitySnapshot.observed_at.asc(),
                        PaperEquitySnapshot.id.asc(),
                    )
                )
                return PaperRuntimeSnapshotPage(
                    points=list(result.scalars().all()),
                    next_cursor=None,
                    sampled=False,
                    sampling="none",
                )

            offsets = (
                [0]
                if limit == 1
                else sorted({round(index * (total - 1) / (limit - 1)) for index in range(limit)})
            )
            points: list[PaperEquitySnapshot] = []
            ordered = query.order_by(
                PaperEquitySnapshot.observed_at.asc(),
                PaperEquitySnapshot.id.asc(),
            )
            for offset in offsets:
                row = await session.scalar(ordered.offset(offset).limit(1))
                if row is not None:
                    points.append(row)
            return PaperRuntimeSnapshotPage(
                points=points,
                next_cursor=None,
                sampled=True,
                sampling="evenly_spaced_raw_points",
            )

    async def cleanup_snapshots(
        self,
        *,
        now: datetime | None = None,
        raw_retention_days: int = 90,
        daily_retention_days: int = 365,
    ) -> dict[str, int]:
        """Retain raw points for 90 days and one daily close through 365 days.

        The operation is safe to retry: it only deletes rows that are neither
        the newest point for a runtime nor the latest point in a retained UTC
        day.  A scheduler may therefore re-run it after a partial failure
        without risking the last auditable equity value for any runtime.
        """
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        raw_cutoff = reference - timedelta(days=max(int(raw_retention_days), 1))
        daily_cutoff = reference - timedelta(
            days=max(int(daily_retention_days), raw_retention_days)
        )
        async with async_session_maker() as session:
            result = await session.execute(
                select(PaperEquitySnapshot).order_by(
                    PaperEquitySnapshot.instance_id.asc(),
                    PaperEquitySnapshot.observed_at.asc(),
                    PaperEquitySnapshot.id.asc(),
                )
            )
            rows = list(result.scalars().all())
            latest_ids_by_runtime: dict[str, str] = {}
            daily_close_ids_by_key: dict[tuple[str, date], str] = {}
            for snapshot in rows:
                observed_at = snapshot.observed_at
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=timezone.utc)
                key = (snapshot.instance_id, observed_at.astimezone(timezone.utc).date())
                if observed_at >= daily_cutoff:
                    # Ordering makes the final assignment for one key its daily close.
                    daily_close_ids_by_key[key] = snapshot.id
                latest_ids_by_runtime[snapshot.instance_id] = snapshot.id

            protected_ids = set(latest_ids_by_runtime.values()) | set(
                daily_close_ids_by_key.values()
            )
            deleted = 0
            daily_retained = len(daily_close_ids_by_key)
            for snapshot in rows:
                observed_at = snapshot.observed_at
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=timezone.utc)
                if snapshot.id in protected_ids or observed_at >= raw_cutoff:
                    continue
                await session.delete(snapshot)
                deleted += 1
            await session.commit()
        return {
            "deleted": deleted,
            "daily_retained": daily_retained,
            "failed": 0,
        }

    @staticmethod
    def _encode_cursor(snapshot: PaperEquitySnapshot) -> str:
        """Encode a stable UTC timestamp/id boundary without leaking SQL syntax."""
        observed_at = snapshot.observed_at
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        payload = json.dumps(
            {"observed_at": observed_at.astimezone(timezone.utc).isoformat(), "id": snapshot.id},
            separators=(",", ":"),
        ).encode()
        return base64.urlsafe_b64encode(payload).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, str]:
        """Decode and validate a cursor before it participates in an SQL filter."""
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode())
            observed_at = datetime.fromisoformat(str(payload["observed_at"]))
            snapshot_id = str(payload["id"])
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise ValueError("Invalid paper equity cursor") from exc
        if not snapshot_id:
            raise ValueError("Invalid paper equity cursor")
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        return observed_at.astimezone(timezone.utc), snapshot_id

    async def capture_mark_to_market_snapshot(
        self,
        user_id: str,
        instance_id: str,
        *,
        min_interval_seconds: int = 60,
        force: bool = False,
    ) -> PaperEquitySnapshot | None:
        """Persist one due valuation snapshot from the runtime's durable state.

        The workspace hydration path refreshes ``trading_snapshot`` from the
        runner. This method deliberately consumes that stored state so the
        background lifecycle can keep an auditable equity series without a UI
        request and without treating an account-engine balance as this unit's
        balance.
        """
        runtime = await self.get_runtime(user_id, instance_id)
        if runtime is None:
            return None
        _, unit = runtime
        if bool(unit.lock_running) or str(unit.run_status or "").lower() != "running":
            return None

        now = datetime.now(timezone.utc)
        latest = await self.latest_snapshot(user_id, instance_id)
        if not force and latest is not None:
            observed_at = latest.observed_at
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=timezone.utc)
            if (now - observed_at.astimezone(timezone.utc)).total_seconds() < min_interval_seconds:
                return latest

        return await self.record_valuation_snapshot(
            user_id,
            instance_id,
            trading_snapshot=dict(unit.trading_snapshot or {}),
            metrics_snapshot=dict(unit.metrics_snapshot or {}),
            unit_settings=dict(unit.unit_settings or {}),
            source="mark_to_market",
        )

    async def record_valuation_snapshot(
        self,
        user_id: str,
        instance_id: str,
        *,
        trading_snapshot: dict[str, Any],
        metrics_snapshot: dict[str, Any],
        unit_settings: dict[str, Any],
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> PaperEquitySnapshot | None:
        """Persist a snapshot from a just-observed runner valuation.

        This accepts the current hydration payload directly, so a post-fill
        write does not need to wait for the owning workspace session to commit
        its JSON snapshot before recording the durable equity event.
        """
        snapshot = dict(trading_snapshot or {})
        metrics = dict(metrics_snapshot or {})
        settings = dict(unit_settings or {})
        configured_initial_cash = self._number(settings.get("initial_cash"), 0.0)
        metric_initial_cash = self._number(metrics.get("initial_cash"), 0.0)
        initial_cash = configured_initial_cash or metric_initial_cash or 100000.0
        unrealized_pnl = self._number(snapshot.get("position_pnl"), 0.0)
        position_value = self._number(snapshot.get("long_market_value"), 0.0) + self._number(
            snapshot.get("short_market_value"), 0.0
        )
        cumulative_pnl = self._number(snapshot.get("cumulative_pnl"), unrealized_pnl)
        metric_final_value = self._number(metrics.get("final_value"), 0.0)
        metric_matches_runtime_cash = metric_initial_cash > 0 and abs(
            metric_initial_cash - initial_cash
        ) <= max(1.0, initial_cash * 0.000001)
        total_equity = (
            metric_final_value
            if metric_final_value > 0 and metric_matches_runtime_cash
            else initial_cash + cumulative_pnl
        )
        cash = max(total_equity - position_value, 0.0)
        return await self.record_snapshot(
            user_id,
            instance_id,
            {
                "observed_at": datetime.now(timezone.utc),
                "source": source,
                "total_equity": total_equity,
                "cash": cash,
                "position_value": position_value,
                "unrealized_pnl": unrealized_pnl,
                "realized_pnl": cumulative_pnl - unrealized_pnl,
                "metadata": {
                    "valuation_status": snapshot.get("valuation_status"),
                    "position_source": snapshot.get("position_source"),
                    "trading_day": snapshot.get("trading_day"),
                    **dict(metadata or {}),
                },
            },
        )

    @staticmethod
    def _number(value: Any, default: float) -> float:
        """Convert finite numeric payloads while retaining safe valuation defaults."""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return (
            number if number == number and number not in {float("inf"), float("-inf")} else default
        )

    async def list_rules(self, user_id: str, instance_id: str | None = None) -> list[RiskRule]:
        """List owned rules, optionally constrained to one runtime plus broad scopes."""
        runtime: tuple[Workspace, StrategyUnit] | None = None
        if instance_id:
            runtime = await self.get_runtime(user_id, instance_id)
            if runtime is None:
                return []
        workspace, unit = runtime if runtime is not None else (None, None)
        async with async_session_maker() as session:
            query = select(RiskRule).where(RiskRule.user_id == user_id)
            if instance_id and workspace is not None and unit is not None:
                query = query.where(
                    or_(
                        RiskRule.instance_id == instance_id,
                        and_(RiskRule.instance_id.is_(None), RiskRule.unit_id == unit.id),
                        and_(
                            RiskRule.instance_id.is_(None),
                            RiskRule.unit_id.is_(None),
                            RiskRule.workspace_id == workspace.id,
                        ),
                        and_(
                            RiskRule.instance_id.is_(None),
                            RiskRule.unit_id.is_(None),
                            RiskRule.workspace_id.is_(None),
                        ),
                    )
                )
            result = await session.execute(query.order_by(RiskRule.created_at.desc()))
            return list(result.scalars().all())

    async def create_rule(self, user_id: str, values: dict[str, Any]) -> RiskRule:
        """Persist a rule after binding absent scope fields to an owned runtime."""
        instance_id = str(values.get("instance_id") or "").strip()
        if instance_id:
            runtime = await self.get_runtime(user_id, instance_id)
            if runtime is None:
                raise LookupError("Runtime not found")
            workspace, unit = runtime
            if values.get("workspace_id") not in (None, workspace.id):
                raise LookupError("Workspace does not match runtime")
            if values.get("unit_id") not in (None, unit.id):
                raise LookupError("Unit does not match runtime")
            values["workspace_id"] = workspace.id
            values["unit_id"] = unit.id
        else:
            await self._validate_rule_scope(user_id, values)
        account_id = str(values.get("paper_account_id") or "").strip()
        if account_id:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Account.id).where(Account.id == account_id, Account.user_id == user_id)
                )
                if result.scalar_one_or_none() is None:
                    raise LookupError("Paper account not found")
        rule = RiskRule(user_id=user_id, **values)
        async with async_session_maker() as session:
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            return rule

    async def update_rule(
        self, user_id: str, rule_id: str, values: dict[str, Any]
    ) -> RiskRule | None:
        """Patch a user-owned risk rule."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(RiskRule).where(RiskRule.id == rule_id, RiskRule.user_id == user_id)
            )
            rule = result.scalar_one_or_none()
            if rule is None:
                return None
            changed = False
            for key, value in values.items():
                if value is not None:
                    changed = changed or getattr(rule, key) != value
                    setattr(rule, key, value)
            if changed:
                rule.version = int(rule.version or 0) + 1
            await session.commit()
            await session.refresh(rule)
            return rule

    async def _validate_rule_scope(self, user_id: str, values: dict[str, Any]) -> None:
        """Ensure non-runtime workspace/unit scopes belong to the requesting user."""
        workspace_id = str(values.get("workspace_id") or "").strip()
        unit_id = str(values.get("unit_id") or "").strip()
        if not workspace_id and not unit_id:
            return
        async with async_session_maker() as session:
            workspace: Workspace | None = None
            if workspace_id:
                workspace = await session.scalar(
                    select(Workspace).where(
                        Workspace.id == workspace_id, Workspace.user_id == user_id
                    )
                )
                if workspace is None:
                    raise LookupError("Workspace not found")
            if unit_id:
                result = await session.execute(
                    select(StrategyUnit, Workspace)
                    .join(Workspace, Workspace.id == StrategyUnit.workspace_id)
                    .where(StrategyUnit.id == unit_id, Workspace.user_id == user_id)
                )
                row = result.one_or_none()
                if row is None:
                    raise LookupError("Unit not found")
                if workspace is not None and row[1].id != workspace.id:
                    raise LookupError("Unit does not belong to workspace")

    async def evaluate_pre_order(
        self,
        user_id: str,
        instance_id: str,
        *,
        order_notional: float,
        current_equity: float,
        projected_position_value: float = 0.0,
        drawdown_pct: float = 0.0,
        daily_loss_pct: float = 0.0,
        daily_trade_count: int = 0,
    ) -> PaperRuntimeRiskDecision:
        """Evaluate active rules before broker submission and persist rejections.

        Missing/invalid active policy is treated as a failure, so a caller using
        this guard cannot submit an order merely because risk data was absent.
        """
        if await self.get_runtime(user_id, instance_id) is None:
            return PaperRuntimeRiskDecision(False, "Runtime not found")
        if current_equity <= 0:
            return await self._reject_risk(
                user_id,
                instance_id,
                "runtime-equity",
                "Risk check rejected an order because current equity is not positive.",
            )

        rules = [rule for rule in await self.list_rules(user_id, instance_id) if rule.is_active]
        if not rules:
            return await self._reject_risk(
                user_id,
                instance_id,
                "missing-policy",
                "Risk check rejected an order because no active risk rule is configured.",
            )

        rejected_rule_ids: list[str] = []
        messages: list[str] = []
        for rule in rules:
            exceeded, message = self._rule_exceeded(
                rule,
                order_notional=order_notional,
                current_equity=current_equity,
                projected_position_value=projected_position_value,
                drawdown_pct=drawdown_pct,
                daily_loss_pct=daily_loss_pct,
                daily_trade_count=daily_trade_count,
            )
            if not exceeded:
                continue
            rejected_rule_ids.append(rule.id)
            messages.append(message)
            await self.emit_alert(
                user_id,
                instance_id,
                alert_type="risk",
                severity=rule.severity,
                title="模拟交易风控拒单",
                message=message,
                details={"rule_id": rule.id, "rule_version": rule.version},
                dedupe_key=f"{instance_id}:risk-rule:{rule.id}:v{rule.version}",
            )

        if rejected_rule_ids:
            return PaperRuntimeRiskDecision(False, "; ".join(messages), tuple(rejected_rule_ids))
        return PaperRuntimeRiskDecision(True)

    async def submit_with_pretrade_risk(
        self,
        user_id: str,
        instance_id: str,
        *,
        submit: Callable[[], Awaitable[Any] | Any],
        order_notional: float,
        current_equity: float,
        projected_position_value: float = 0.0,
        drawdown_pct: float = 0.0,
        daily_loss_pct: float = 0.0,
        daily_trade_count: int = 0,
    ) -> Any | None:
        """Call a broker submit callback only after a durable fail-closed check."""
        decision = await self.evaluate_pre_order(
            user_id,
            instance_id,
            order_notional=order_notional,
            current_equity=current_equity,
            projected_position_value=projected_position_value,
            drawdown_pct=drawdown_pct,
            daily_loss_pct=daily_loss_pct,
            daily_trade_count=daily_trade_count,
        )
        if not decision.allowed:
            return None
        try:
            result = submit()
            return await result if inspect.isawaitable(result) else result
        except Exception as exc:
            await self.emit_alert(
                user_id,
                instance_id,
                alert_type="order",
                severity="error",
                title="模拟交易下单失败",
                message=f"Broker submit failed: {exc}",
                dedupe_key=f"{instance_id}:broker-submit-failed",
            )
            raise

    async def evaluate_post_fill(
        self,
        user_id: str,
        instance_id: str,
        *,
        current_equity: float,
        position_value: float,
        drawdown_pct: float,
        daily_loss_pct: float = 0.0,
    ) -> PaperRuntimeRiskDecision:
        """Check durable position/drawdown limits after a newly observed fill."""
        if await self.get_runtime(user_id, instance_id) is None:
            return PaperRuntimeRiskDecision(False, "Runtime not found")
        if current_equity <= 0:
            return await self._reject_risk(
                user_id,
                instance_id,
                "post-fill-equity",
                "Post-fill risk check found non-positive current equity.",
            )
        rejected: list[str] = []
        messages: list[str] = []
        for rule in await self.list_rules(user_id, instance_id):
            if not rule.is_active or rule.rule_type not in {
                "max_position_pct",
                "max_drawdown",
                "max_daily_loss",
            }:
                continue
            exceeded, message = self._rule_exceeded(
                rule,
                order_notional=0.0,
                current_equity=current_equity,
                projected_position_value=position_value,
                drawdown_pct=drawdown_pct,
                daily_loss_pct=daily_loss_pct,
                daily_trade_count=0,
            )
            if not exceeded:
                continue
            rejected.append(rule.id)
            messages.append(message)
            await self.emit_alert(
                user_id,
                instance_id,
                alert_type="risk",
                severity=rule.severity,
                title="模拟交易成交后风控告警",
                message=message,
                details={"rule_id": rule.id, "rule_version": rule.version, "phase": "post_fill"},
                dedupe_key=f"{instance_id}:post-fill-risk:{rule.id}:v{rule.version}",
            )
        if rejected:
            return PaperRuntimeRiskDecision(False, "; ".join(messages), tuple(rejected))
        return PaperRuntimeRiskDecision(True)

    async def _reject_risk(
        self,
        user_id: str,
        instance_id: str,
        reason_key: str,
        message: str,
    ) -> PaperRuntimeRiskDecision:
        """Write one durable rejection alert and return a failed decision."""
        await self.emit_alert(
            user_id,
            instance_id,
            alert_type="risk",
            severity="critical",
            title="模拟交易风控拒单",
            message=message,
            dedupe_key=f"{instance_id}:risk:{reason_key}",
        )
        return PaperRuntimeRiskDecision(False, message)

    @classmethod
    def _rule_exceeded(
        cls,
        rule: RiskRule,
        *,
        order_notional: float,
        current_equity: float,
        projected_position_value: float,
        drawdown_pct: float,
        daily_loss_pct: float,
        daily_trade_count: int,
    ) -> tuple[bool, str]:
        """Evaluate supported rules and fail closed for invalid/unknown policy."""
        config = dict(rule.config or {})
        rule_type = str(rule.rule_type or "").strip().lower()
        if rule_type in {"max_order_size", "max_order_notional"}:
            limit = cls._rule_limit(config, "max_order_size", "max_notional", "limit")
            actual = abs(order_notional)
            label = "order notional"
        elif rule_type == "max_position_pct":
            limit = cls._percent_limit(config, "max_pct", "limit_pct", "limit")
            actual = abs(projected_position_value) / current_equity * 100
            label = "projected position percentage"
        elif rule_type == "max_drawdown":
            limit = cls._percent_limit(config, "max_pct", "max_drawdown_pct", "limit_pct")
            actual = abs(drawdown_pct)
            label = "drawdown percentage"
        elif rule_type == "max_daily_loss":
            limit = cls._percent_limit(config, "max_pct", "max_daily_loss_pct", "limit_pct")
            actual = abs(daily_loss_pct)
            label = "daily loss percentage"
        elif rule_type == "max_daily_trades":
            limit = cls._rule_limit(config, "max_count", "max_daily_trades", "limit")
            actual = float(daily_trade_count + 1)
            label = "daily trade count"
        else:
            return True, f"Risk rule {rule.name} has unsupported type {rule.rule_type}."
        if limit is None:
            return True, f"Risk rule {rule.name} has no valid limit configuration."
        if actual <= limit:
            return False, ""
        return True, f"Risk rule {rule.name} rejected {label}: {actual:.4f} exceeds {limit:.4f}."

    @classmethod
    def _rule_limit(cls, config: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = cls._number(config.get(key), float("nan"))
            if value == value and value >= 0:
                return value
        return None

    @classmethod
    def _percent_limit(cls, config: dict[str, Any], *keys: str) -> float | None:
        limit = cls._rule_limit(config, *keys)
        if limit is None:
            return None
        return limit * 100 if 0 < limit <= 1 else limit

    async def list_alerts(
        self, user_id: str, instance_id: str, limit: int = 100
    ) -> list[Alert] | None:
        """Return durable alerts for one owned runtime."""
        if await self.get_runtime(user_id, instance_id) is None:
            return None
        async with async_session_maker() as session:
            result = await session.execute(
                select(Alert)
                .where(Alert.user_id == user_id, Alert.instance_id == instance_id)
                .order_by(Alert.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def emit_alert(
        self,
        user_id: str,
        instance_id: str,
        *,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        details: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
    ) -> Alert | None:
        """Persist a de-duplicated alert for an owned runtime."""
        runtime = await self.get_runtime(user_id, instance_id)
        if runtime is None:
            return None
        workspace, unit = runtime
        async with async_session_maker() as session:
            if dedupe_key:
                existing = await session.execute(
                    select(Alert).where(
                        Alert.user_id == user_id,
                        Alert.dedupe_key == dedupe_key,
                        Alert.status == AlertStatus.ACTIVE.value,
                    )
                )
                alert = existing.scalar_one_or_none()
                if alert is not None:
                    return alert
            alert = Alert(
                user_id=user_id,
                alert_type=alert_type,
                severity=severity,
                status=AlertStatus.ACTIVE.value,
                title=title,
                message=message,
                details=dict(details or {}),
                workspace_id=workspace.id,
                unit_id=unit.id,
                instance_id=instance_id,
                dedupe_key=dedupe_key,
                trigger_type="runtime",
            )
            session.add(alert)
            await session.commit()
            await session.refresh(alert)
            return alert

    async def create_review(
        self, user_id: str, instance_id: str, values: dict[str, Any]
    ) -> PaperReviewReport | None:
        """Persist a structured review for an owned runtime."""
        runtime = await self.get_runtime(user_id, instance_id)
        if runtime is None:
            return None
        workspace, unit = runtime
        review = PaperReviewReport(
            user_id=user_id,
            workspace_id=workspace.id,
            unit_id=unit.id,
            instance_id=instance_id,
            **values,
        )
        async with async_session_maker() as session:
            session.add(review)
            await session.commit()
            await session.refresh(review)
            return review

    async def decide_handoff(
        self, user_id: str, instance_id: str, values: dict[str, Any]
    ) -> LiveHandoffReview | None:
        """Record a three-state live-handoff decision for an owned runtime."""
        runtime = await self.get_runtime(user_id, instance_id)
        if runtime is None:
            return None
        workspace, unit = runtime
        now = datetime.now(timezone.utc)
        review = LiveHandoffReview(
            user_id=user_id,
            workspace_id=workspace.id,
            unit_id=unit.id,
            instance_id=instance_id,
            decided_by=user_id,
            decided_at=now,
            **values,
        )
        async with async_session_maker() as session:
            session.add(review)
            await session.commit()
            await session.refresh(review)
            return review

    async def pause_runtime(
        self, user_id: str, instance_id: str
    ) -> tuple[Workspace, StrategyUnit] | None:
        """Persist a pause first; a runner can safely observe the lock on its next cycle."""
        runtime = await self.get_runtime(user_id, instance_id)
        if runtime is None:
            return None
        workspace, unit = runtime
        async with async_session_maker() as session:
            result = await session.execute(
                select(StrategyUnit).where(
                    StrategyUnit.id == unit.id, StrategyUnit.workspace_id == workspace.id
                )
            )
            stored = result.scalar_one()
            stored.lock_running = True
            await session.commit()
        unit.lock_running = True
        return workspace, unit
