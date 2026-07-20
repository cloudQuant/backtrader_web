"""Regression tests for the workspace/unit/instance paper-runtime contract."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.alerts import Alert
from app.models.paper_runtime import LiveHandoffReview, PaperEquitySnapshot, RiskRule
from app.models.user import User
from app.models.workspace import StrategyUnit, Workspace
from app.services.paper_runtime_scheduler import PaperRuntimeSnapshotScheduler
from app.services.paper_runtime_service import PaperRuntimeService
from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def _create_runtime(user_id: str = "runtime-owner") -> tuple[str, str, str]:
    async with async_session_maker() as session:
        workspace = Workspace(id="runtime-workspace", user_id=user_id, name="Paper runtime")
        unit = StrategyUnit(
            id="runtime-unit",
            workspace_id=workspace.id,
            strategy_name="Runtime strategy",
            symbol="RB0",
            trading_mode="paper",
            trading_instance_id="runtime-instance",
        )
        session.add_all([workspace, unit])
        await session.commit()
    return user_id, workspace.id, unit.id


async def test_runtime_snapshot_is_owned_idempotent_and_downsampled():
    user_id, _, _ = await _create_runtime()
    service = PaperRuntimeService()
    observed_at = datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)

    first = await service.record_snapshot(
        user_id,
        "runtime-instance",
        {"observed_at": observed_at, "source": "initial", "total_equity": 100000},
    )
    retried = await service.record_snapshot(
        user_id,
        "runtime-instance",
        {"observed_at": observed_at, "source": "initial", "total_equity": 100100},
    )

    assert first is not None
    assert retried is not None
    assert first.id == retried.id
    assert retried.total_equity == 100100

    for minute in range(1, 8):
        await service.record_snapshot(
            user_id,
            "runtime-instance",
            {
                "observed_at": observed_at.replace(minute=minute),
                "source": "mark_to_market",
                "total_equity": 100100 + minute,
            },
        )

    points = await service.list_snapshots(user_id, "runtime-instance", max_points=3)
    assert points is not None
    assert len(points) == 3
    assert points[0].observed_at == observed_at.replace(tzinfo=None)
    assert points[-1].total_equity == 100107

    overview = await service.list_snapshot_page(user_id, "runtime-instance", max_points=3)
    assert overview is not None
    assert overview.sampled is True
    assert overview.sampling == "evenly_spaced_raw_points"
    assert overview.points[0].id == points[0].id
    raw_page = await service.list_snapshot_page(
        user_id,
        "runtime-instance",
        max_points=3,
        cursor=service._encode_cursor(overview.points[0]),
    )
    assert raw_page is not None
    assert raw_page.sampled is False
    assert len(raw_page.points) == 3
    assert raw_page.next_cursor is not None

    async with async_session_maker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(PaperEquitySnapshot)
            .where(PaperEquitySnapshot.instance_id == "runtime-instance")
        )
    assert count == 8


async def test_runtime_scopes_rules_alerts_and_handoff_to_owner():
    user_id, workspace_id, unit_id = await _create_runtime()
    service = PaperRuntimeService()

    rule = await service.create_rule(
        user_id,
        {
            "name": "Max drawdown",
            "rule_type": "max_drawdown",
            "config": {"max_pct": 10},
            "severity": "critical",
            "instance_id": "runtime-instance",
        },
    )
    alert = await service.emit_alert(
        user_id,
        "runtime-instance",
        alert_type="risk",
        severity="critical",
        title="Drawdown exceeded",
        message="Runtime drawdown exceeded the configured threshold.",
        dedupe_key="runtime-instance:drawdown",
    )
    duplicate = await service.emit_alert(
        user_id,
        "runtime-instance",
        alert_type="risk",
        severity="critical",
        title="Drawdown exceeded",
        message="Runtime drawdown exceeded the configured threshold.",
        dedupe_key="runtime-instance:drawdown",
    )
    handoff = await service.decide_handoff(
        user_id,
        "runtime-instance",
        {"decision": "requested_changes", "rationale": "Need a longer observation window."},
    )

    assert rule.workspace_id == workspace_id
    assert rule.unit_id == unit_id
    assert alert is not None
    assert duplicate is not None
    assert alert.id == duplicate.id
    assert handoff is not None
    assert handoff.decision == "requested_changes"
    assert await service.get_runtime("another-user", "runtime-instance") is None

    async with async_session_maker() as session:
        saved_rule = await session.get(RiskRule, rule.id)
        saved_alert = await session.get(Alert, alert.id)
        saved_handoff = await session.get(LiveHandoffReview, handoff.id)
    assert saved_rule is not None
    assert saved_alert is not None and saved_alert.instance_id == "runtime-instance"
    assert saved_handoff is not None and saved_handoff.decision == "requested_changes"


async def test_running_runtime_captures_due_mark_to_market_snapshot():
    user_id, _, unit_id = await _create_runtime()
    async with async_session_maker() as session:
        unit = await session.get(StrategyUnit, unit_id)
        assert unit is not None
        unit.run_status = "running"
        unit.unit_settings = {"initial_cash": 100000}
        unit.metrics_snapshot = {"initial_cash": 100000, "final_value": 101250}
        unit.trading_snapshot = {
            "position_pnl": 300,
            "cumulative_pnl": 1250,
            "long_market_value": 10000,
            "short_market_value": 0,
            "valuation_status": "confirmed",
        }
        await session.commit()

    service = PaperRuntimeService()
    first = await service.capture_mark_to_market_snapshot(
        user_id,
        "runtime-instance",
        force=True,
    )
    second = await service.capture_mark_to_market_snapshot(
        user_id,
        "runtime-instance",
        min_interval_seconds=60,
    )

    assert first is not None
    assert first.source == "mark_to_market"
    assert first.total_equity == 101250
    assert first.cash == 91250
    assert second is not None
    assert second.id == first.id


async def test_snapshot_retention_keeps_recent_raw_daily_closes_and_last_snapshot():
    user_id, _, _ = await _create_runtime()
    service = PaperRuntimeService()
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    points = [
        datetime(2025, 1, 1, 9, tzinfo=timezone.utc),
        datetime(2025, 1, 1, 10, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
        datetime(2026, 7, 1, 9, tzinfo=timezone.utc),
        datetime(2026, 7, 1, 10, tzinfo=timezone.utc),
    ]
    for index, observed_at in enumerate(points):
        await service.record_snapshot(
            user_id,
            "runtime-instance",
            {
                "observed_at": observed_at,
                "source": "mark_to_market",
                "total_equity": 100000 + index,
            },
        )

    result = await service.cleanup_snapshots(now=now)
    snapshots = await service.list_snapshots(user_id, "runtime-instance", max_points=100)

    assert result == {"deleted": 3, "daily_retained": 2, "failed": 0}
    assert snapshots is not None
    assert [item.observed_at.hour for item in snapshots] == [10, 9, 10]
    assert [item.observed_at.date().isoformat() for item in snapshots] == [
        "2026-01-01",
        "2026-07-01",
        "2026-07-01",
    ]


async def test_pretrade_risk_rejects_before_broker_submit_and_persists_alert():
    user_id, _, _ = await _create_runtime()
    service = PaperRuntimeService()
    rule = await service.create_rule(
        user_id,
        {
            "name": "Single order cap",
            "rule_type": "max_order_size",
            "config": {"max_order_size": 1000},
            "severity": "critical",
            "instance_id": "runtime-instance",
        },
    )
    called = False

    async def submit() -> dict[str, str]:
        nonlocal called
        called = True
        return {"order_id": "must-not-exist"}

    result = await service.submit_with_pretrade_risk(
        user_id,
        "runtime-instance",
        submit=submit,
        order_notional=1200,
        current_equity=100000,
    )
    updated = await service.update_rule(
        user_id,
        rule.id,
        {"config": {"max_order_size": 2000}},
    )

    assert result is None
    assert called is False
    assert updated is not None and updated.version == 2
    async with async_session_maker() as session:
        alerts = await session.scalars(
            select(Alert).where(Alert.instance_id == "runtime-instance", Alert.alert_type == "risk")
        )
        saved = list(alerts)
    assert len(saved) == 1
    assert saved[0].details == {"rule_id": rule.id, "rule_version": 1}


async def test_post_fill_risk_persists_deduplicated_drawdown_alert():
    user_id, _, _ = await _create_runtime()
    service = PaperRuntimeService()
    await service.create_rule(
        user_id,
        {
            "name": "Drawdown cap",
            "rule_type": "max_drawdown",
            "config": {"max_pct": 5},
            "severity": "critical",
            "instance_id": "runtime-instance",
        },
    )

    first = await service.evaluate_post_fill(
        user_id,
        "runtime-instance",
        current_equity=98000,
        position_value=30000,
        drawdown_pct=6,
    )
    second = await service.evaluate_post_fill(
        user_id,
        "runtime-instance",
        current_equity=98000,
        position_value=30000,
        drawdown_pct=6,
    )

    assert first.allowed is False
    assert second.rule_ids == first.rule_ids
    async with async_session_maker() as session:
        alerts = await session.scalars(
            select(Alert).where(Alert.instance_id == "runtime-instance", Alert.title == "模拟交易成交后风控告警")
        )
        saved = list(alerts)
    assert len(saved) == 1
    assert saved[0].details["phase"] == "post_fill"


async def test_pretrade_risk_api_rejects_uncovered_runtime(client):
    owner, headers = await register_and_login(client, username="paper-runtime-risk-owner")
    async with async_session_maker() as session:
        owner_id = await session.scalar(select(User.id).where(User.username == owner["username"]))
    assert owner_id is not None
    await _create_runtime(owner_id)

    response = await client.post(
        "/api/v1/paper-runtimes/runtime-instance/pre-order-check",
        headers=headers,
        json={"order_notional": 1000, "current_equity": 100000},
    )

    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert "no active risk rule" in response.json()["reason"]


async def test_snapshot_scheduler_stops_after_runtime_is_no_longer_active(monkeypatch):
    class StubRuntimeService:
        def __init__(self) -> None:
            self.calls = 0

        async def capture_mark_to_market_snapshot(self, *_args, **_kwargs):
            self.calls += 1
            return object() if self.calls == 1 else None

        async def emit_alert(self, *_args, **_kwargs):
            raise AssertionError("successful lifecycle must not emit an alert")

        async def cleanup_snapshots(self, **_kwargs):
            return {"deleted": 0, "daily_retained": 0, "failed": 0}

    scheduler = PaperRuntimeSnapshotScheduler(interval_seconds=1)
    stub = StubRuntimeService()
    scheduler._service = stub  # type: ignore[assignment]
    real_sleep = asyncio.sleep

    async def immediate_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.services.paper_runtime_scheduler.asyncio.sleep", immediate_sleep)
    scheduler.ensure_running("runtime-owner", "runtime-instance")
    await real_sleep(0)
    await real_sleep(0)

    assert stub.calls == 2
    assert "runtime-instance" not in scheduler._tasks


async def test_runtime_api_enforces_owner_scope_and_returns_utc_equity(client):
    owner, owner_headers = await register_and_login(client, username="paper-runtime-owner")
    _, other_headers = await register_and_login(client, username="paper-runtime-other")
    async with async_session_maker() as session:
        user_result = await session.execute(select(User).where(User.username == owner["username"]))
        owner_id = user_result.scalar_one().id

    await _create_runtime(owner_id)
    async with async_session_maker() as session:
        unit = await session.get(StrategyUnit, "runtime-unit")
        assert unit is not None
        unit.trading_snapshot = {
            "positions": [
                {
                    "data_name": "RB0",
                    "direction": "long",
                    "size": 2,
                    "market_value": 1000,
                    "api_key": "must-not-leak",
                }
            ],
            "orders": [{"order_id": "order-1", "status": "filled", "token": "must-not-leak"}],
            "trades": [{"id": "trade-1", "pnlcomm": 12.5, "secret": "must-not-leak"}],
            "signals": [{"symbol": "RB0", "signal": "buy", "credential": "must-not-leak"}],
        }
        await session.commit()
    service = PaperRuntimeService()
    await service.record_snapshot(
        owner_id,
        "runtime-instance",
        {
            "observed_at": datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc),
            "source": "initial",
            "total_equity": 100000,
        },
    )

    detail = await client.get("/api/v1/paper-runtimes/runtime-instance", headers=owner_headers)
    equity = await client.get(
        "/api/v1/paper-runtimes/runtime-instance/equity",
        headers=owner_headers,
    )
    forbidden = await client.get("/api/v1/paper-runtimes/runtime-instance", headers=other_headers)

    assert detail.status_code == 200
    assert detail.json()["unit_id"] == "runtime-unit"
    assert detail.json()["positions"] == [
        {"data_name": "RB0", "direction": "long", "size": 2, "market_value": 1000}
    ]
    assert "must-not-leak" not in str(detail.json())
    assert equity.status_code == 200
    assert equity.json()["points"][0]["observed_at"].endswith(("Z", "+00:00"))
    assert forbidden.status_code == 404


async def test_risk_alert_api_reads_durable_owner_scoped_alerts(client):
    owner, owner_headers = await register_and_login(client, username="paper-runtime-alert-owner")
    _, other_headers = await register_and_login(client, username="paper-runtime-alert-other")
    async with async_session_maker() as session:
        user_result = await session.execute(select(User).where(User.username == owner["username"]))
        owner_id = user_result.scalar_one().id
    await _create_runtime(owner_id)
    await PaperRuntimeService().emit_alert(
        owner_id,
        "runtime-instance",
        alert_type="risk",
        severity="critical",
        title="Persistent runtime alert",
        message="A durable risk event was recorded.",
        dedupe_key="runtime-instance:persistent-risk",
    )

    owner_alerts = await client.get(
        "/api/v1/risk-control/alerts?instance_id=runtime-instance",
        headers=owner_headers,
    )
    other_alerts = await client.get(
        "/api/v1/risk-control/alerts?instance_id=runtime-instance",
        headers=other_headers,
    )
    resolved = await client.delete(
        "/api/v1/risk-control/alerts?instance_id=runtime-instance",
        headers=owner_headers,
    )
    active_after_resolution = await client.get(
        "/api/v1/risk-control/alerts?instance_id=runtime-instance",
        headers=owner_headers,
    )

    assert owner_alerts.status_code == 200
    assert owner_alerts.json()["total"] == 1
    assert owner_alerts.json()["alerts"][0]["message"] == "A durable risk event was recorded."
    assert other_alerts.status_code == 200
    assert other_alerts.json()["total"] == 0
    assert resolved.status_code == 200
    assert resolved.json()["cleared"] == 1
    assert active_after_resolution.json()["total"] == 0
