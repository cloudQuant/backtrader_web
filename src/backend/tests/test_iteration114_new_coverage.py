from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_monitoring_update_alert_rule_starts_monitoring_when_activated():
    from app.services.monitoring_service import MonitoringService

    svc = MonitoringService()
    svc._start_monitoring = AsyncMock()

    rule_before = SimpleNamespace(id="r1", user_id="u1", is_active=False)
    rule_after = SimpleNamespace(id="r1", user_id="u1", is_active=True)

    svc.alert_rule_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=rule_before),
        update=AsyncMock(return_value=rule_after),
    )

    await svc.update_alert_rule(rule_id="r1", user_id="u1", update_data={"is_active": True})
    svc._start_monitoring.assert_awaited_once_with("r1")


@pytest.mark.asyncio
async def test_monitoring_triggers_rate_and_cross_and_threshold_branches():
    from app.services.monitoring_service import MonitoringService

    svc = MonitoringService()

    rule = SimpleNamespace(id="r1")

    # Threshold missing -> False
    assert await svc._check_threshold_trigger(rule, {}) is False

    # Rate trigger:
    # 1) first call stores state and returns False
    svc._get_current_metric_value = AsyncMock(return_value=0.0)
    assert await svc._check_rate_trigger(rule, {"threshold": 0.1}) is False
    # 2) prev == 0, pct change => inf, condition gt => True
    svc._get_current_metric_value = AsyncMock(return_value=1.0)
    assert (
        await svc._check_rate_trigger(rule, {"threshold": 0.1, "condition": "gt", "mode": "pct"})
        is True
    )
    # 3) abs mode path (no trigger)
    svc._get_current_metric_value = AsyncMock(return_value=1.5)
    assert (
        await svc._check_rate_trigger(rule, {"threshold": 10.0, "condition": "gt", "mode": "abs"})
        is False
    )

    # Cross trigger:
    # 1) first call stores diff and returns False
    assert await svc._check_cross_trigger(rule, {"value1": "0", "value2": "1"}) is False
    # 2) crosses up (prev <=0, diff > 0)
    assert (
        await svc._check_cross_trigger(rule, {"value1": "2", "value2": "1", "direction": "up"})
        is True
    )
    # 3) crosses down
    rule2 = SimpleNamespace(id="r2")
    assert await svc._check_cross_trigger(rule2, {"value1": "1", "value2": "0"}) is False
    assert (
        await svc._check_cross_trigger(rule2, {"value1": "-1", "value2": "0", "direction": "down"})
        is True
    )
    # 4) float conversion error path
    assert await svc._check_cross_trigger(rule, {"value1": None, "value2": "0"}) is False


@pytest.mark.asyncio
async def test_monitoring_send_notification_and_webhook_paths():
    from app.services.monitoring_service import MonitoringService

    svc = MonitoringService()
    svc._record_notification = AsyncMock()
    svc.alert_repo = SimpleNamespace(update=AsyncMock())

    alert = SimpleNamespace(
        id="a1",
        user_id="u1",
        alert_type=SimpleNamespace(value="account"),
        severity=SimpleNamespace(value="warning"),
        title="t",
        message="m",
        details={"x": 1},
        created_at=datetime.now(timezone.utc),
    )

    # send_notification: email/sms/push + webhook + final mark
    rule = SimpleNamespace(
        notification_enabled=True,
        notification_channels=["email", "sms", "push", "webhook"],
        trigger_config={"webhook": {"url": "http://example.invalid/webhook", "method": "POST"}},
    )

    with patch("app.services.monitoring_service.urllib.request.urlopen") as mock_urlopen:

        class _Resp:
            def __enter__(self):  # noqa: D401
                return self

            def __exit__(self, exc_type, exc, tb):  # noqa: D401
                return False

            def read(self):
                return b"ok"

        mock_urlopen.return_value = _Resp()
        await svc._send_notification(rule, alert)

    assert svc._record_notification.await_count >= 3
    svc.alert_repo.update.assert_awaited_once()

    # _send_webhook: missing url -> record failed
    svc._record_notification.reset_mock()
    rule_missing = SimpleNamespace(trigger_config={"webhook": {}})
    await svc._send_webhook(rule_missing, alert)
    svc._record_notification.assert_awaited()

    # _send_webhook: urlopen error -> record failed
    svc._record_notification.reset_mock()
    rule_err = SimpleNamespace(
        trigger_config={"webhook": {"url": "http://example.invalid/webhook"}}
    )
    from urllib.error import URLError

    with patch(
        "app.services.monitoring_service.urllib.request.urlopen", side_effect=URLError("boom")
    ):
        await svc._send_webhook(rule_err, alert)
    svc._record_notification.assert_awaited()


@pytest.mark.asyncio
async def test_monitoring_summary_and_metric_value_sources():
    from app.models.alerts import AlertType
    from app.services.monitoring_service import MonitoringService

    svc = MonitoringService()

    now = datetime.now(timezone.utc)
    alerts = [
        SimpleNamespace(
            id="a1",
            alert_type="account",
            severity="warning",
            status="active",
            title="t1",
            message="m1",
            created_at=now,
        ),
        SimpleNamespace(
            id="a2",
            alert_type="account",
            severity="error",
            status="resolved",
            title="t2",
            message="m2",
            created_at=now - timedelta(days=10),
        ),
        SimpleNamespace(
            id="a3",
            alert_type="system",
            severity="warning",
            status="active",
            title="t3",
            message="m3",
            created_at=None,
        ),
    ]
    svc.list_alerts = AsyncMock(return_value=(alerts, len(alerts)))
    summary = await svc.get_alert_summary(user_id="u1", recent_limit=2)
    assert summary["total_alerts"] == 3
    assert len(summary["recent"]) == 2

    stats = await svc.get_alerts_by_type(
        user_id="u1", start_dt=now - timedelta(days=1), end_dt=now + timedelta(days=1)
    )
    assert stats["by_type"].get("account") == 1

    # _get_current_metric_value: manual current_value success + parse error.
    rule = SimpleNamespace(alert_type=AlertType.ACCOUNT, user_id="u1")
    assert await svc._get_current_metric_value(rule, {"current_value": "1.25"}) == 1.25
    assert await svc._get_current_metric_value(rule, {"current_value": "not-a-number"}) is None

    # invalid alert type enum conversion path
    bad_rule = SimpleNamespace(alert_type="invalid", user_id="u1")
    assert await svc._get_current_metric_value(bad_rule, {}) is None

    # account: paper trading account path
    svc.paper_trading_service = SimpleNamespace(
        get_account=AsyncMock(return_value=SimpleNamespace(current_cash=123.0, total_equity=456.0))
    )
    assert (
        await svc._get_current_metric_value(rule, {"account_id": "acc1", "metric": "cash"}) == 123.0
    )
    assert (
        await svc._get_current_metric_value(rule, {"account_id": "acc1", "metric": "equity"})
        == 456.0
    )
    assert (
        await svc._get_current_metric_value(rule, {"account_id": "acc1", "metric": "unknown"})
        is None
    )

    # account: live trading path
    svc.live_trading_service = SimpleNamespace(
        get_task_status=AsyncMock(return_value={"cash": 10.0, "value": 20.0})
    )
    assert (
        await svc._get_current_metric_value(rule, {"live_task_id": "t1", "metric": "cash"}) == 10.0
    )
    assert (
        await svc._get_current_metric_value(rule, {"live_task_id": "t1", "metric": "equity"})
        == 20.0
    )

    # position: missing symbol
    pos_rule = SimpleNamespace(alert_type=AlertType.POSITION, user_id="u1")
    assert await svc._get_current_metric_value(pos_rule, {"account_id": "acc1"}) is None

    # position: paper positions path
    svc.paper_trading_service = SimpleNamespace(
        list_positions=AsyncMock(
            return_value=(
                [SimpleNamespace(market_value=100.0, unrealized_pnl=5.0, unrealized_pnl_pct=0.05)],
                1,
            )
        ),
        get_account=AsyncMock(),
    )
    assert (
        await svc._get_current_metric_value(
            pos_rule, {"account_id": "acc1", "symbol": "BTC/USDT", "metric": "market_value"}
        )
        == 100.0
    )
    assert (
        await svc._get_current_metric_value(
            pos_rule, {"account_id": "acc1", "symbol": "BTC/USDT", "metric": "unrealized_pnl"}
        )
        == 5.0
    )
    assert (
        await svc._get_current_metric_value(
            pos_rule, {"account_id": "acc1", "symbol": "BTC/USDT", "metric": "unrealized_pnl_pct"}
        )
        == 0.05
    )

    # position: live positions path
    svc.live_trading_service = SimpleNamespace(
        get_task_status=AsyncMock(
            return_value={"positions": [{"symbol": "BTC/USDT", "size": 2, "price": 50}]}
        )
    )
    assert (
        await svc._get_current_metric_value(
            pos_rule, {"live_task_id": "t1", "symbol": "BTC/USDT", "metric": "market_value"}
        )
        == 100.0
    )

    # strategy: backtest metrics path + unknown metric
    strat_rule = SimpleNamespace(alert_type=AlertType.STRATEGY, user_id="u1")
    svc.backtest_service = SimpleNamespace(
        get_result=AsyncMock(
            return_value=SimpleNamespace(
                sharpe_ratio=1.1, total_return=2.2, max_drawdown=3.3, win_rate=4.4
            )
        )
    )
    assert (
        await svc._get_current_metric_value(
            strat_rule, {"backtest_task_id": "bt1", "metric": "sharpe_ratio"}
        )
        == 1.1
    )
    assert (
        await svc._get_current_metric_value(
            strat_rule, {"backtest_task_id": "bt1", "metric": "total_return"}
        )
        == 2.2
    )
    assert (
        await svc._get_current_metric_value(
            strat_rule, {"backtest_task_id": "bt1", "metric": "max_drawdown"}
        )
        == 3.3
    )
    assert (
        await svc._get_current_metric_value(
            strat_rule, {"backtest_task_id": "bt1", "metric": "win_rate"}
        )
        == 4.4
    )
    assert (
        await svc._get_current_metric_value(
            strat_rule, {"backtest_task_id": "bt1", "metric": "unknown"}
        )
        is None
    )


@pytest.mark.asyncio
async def test_monitoring_remaining_branches_for_full_coverage():
    """Cover remaining small branches in monitoring_service for 100% app/* coverage."""
    from app.models.alerts import AlertType
    from app.services.monitoring_service import MonitoringService

    svc = MonitoringService()

    # _check_rate_trigger: current_value None + rule_id missing + prev_f != 0 pct path
    svc._get_current_metric_value = AsyncMock(return_value=None)
    assert await svc._check_rate_trigger(SimpleNamespace(id="r"), {"threshold": 0.1}) is False

    svc._get_current_metric_value = AsyncMock(return_value=1.0)
    assert await svc._check_rate_trigger(SimpleNamespace(id=None), {"threshold": 0.1}) is False

    rule = SimpleNamespace(id="r_pct")
    svc._get_current_metric_value = AsyncMock(return_value=1.0)
    assert await svc._check_rate_trigger(rule, {"threshold": 0.1}) is False  # seed prev
    svc._get_current_metric_value = AsyncMock(return_value=2.0)
    assert await svc._check_rate_trigger(rule, {"threshold": 0.5, "condition": "gt"}) is True

    # _check_cross_trigger: rule_id missing branch (after float parsing)
    assert (
        await svc._check_cross_trigger(SimpleNamespace(id=None), {"value1": "1", "value2": "0"})
        is False
    )

    # _send_webhook: headers update branch
    svc._record_notification = AsyncMock()
    alert = SimpleNamespace(
        id="a",
        user_id="u",
        alert_type=SimpleNamespace(value="account"),
        severity=SimpleNamespace(value="warning"),
        title="t",
        message="m",
        details={},
        created_at=datetime.now(timezone.utc),
    )
    rule = SimpleNamespace(
        trigger_config={"webhook": {"url": "http://example.invalid", "headers": {"X-Test": "1"}}}
    )
    with patch("app.services.monitoring_service.urllib.request.urlopen") as mock_urlopen:

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b""

        mock_urlopen.return_value = _Resp()
        await svc._send_webhook(rule, alert)
    svc._record_notification.assert_awaited()

    # Use a fresh instance for metric resolution branches (avoid previous method monkeypatches).
    svc = MonitoringService()

    # _get_current_metric_value: account not found
    acct_rule = SimpleNamespace(alert_type=AlertType.ACCOUNT, user_id="u1")
    svc.paper_trading_service = SimpleNamespace(get_account=AsyncMock(return_value=None))
    assert await svc._get_current_metric_value(acct_rule, {"account_id": "missing"}) is None

    # _get_current_metric_value: live status missing + unknown metric in live status
    svc.live_trading_service = SimpleNamespace(get_task_status=AsyncMock(return_value=None))
    assert (
        await svc._get_current_metric_value(acct_rule, {"live_task_id": "t1", "metric": "cash"})
        is None
    )
    svc.live_trading_service = SimpleNamespace(
        get_task_status=AsyncMock(return_value={"cash": 1.0, "value": 2.0})
    )
    assert (
        await svc._get_current_metric_value(acct_rule, {"live_task_id": "t1", "metric": "unknown"})
        is None
    )

    # _get_current_metric_value: position no positions + unknown metric
    pos_rule = SimpleNamespace(alert_type=AlertType.POSITION, user_id="u1")
    svc.paper_trading_service = SimpleNamespace(list_positions=AsyncMock(return_value=([], 0)))
    assert (
        await svc._get_current_metric_value(pos_rule, {"account_id": "acc", "symbol": "BTC/USDT"})
        is None
    )
    svc.paper_trading_service = SimpleNamespace(
        list_positions=AsyncMock(
            return_value=(
                [SimpleNamespace(market_value=1.0, unrealized_pnl=0.0, unrealized_pnl_pct=0.0)],
                1,
            )
        )
    )
    assert (
        await svc._get_current_metric_value(
            pos_rule, {"account_id": "acc", "symbol": "BTC/USDT", "metric": "unknown"}
        )
        is None
    )

    # _get_current_metric_value: live positions status missing + non-market_value metric return
    svc.live_trading_service = SimpleNamespace(get_task_status=AsyncMock(return_value=None))
    assert (
        await svc._get_current_metric_value(pos_rule, {"live_task_id": "t1", "symbol": "BTC/USDT"})
        is None
    )
    svc.live_trading_service = SimpleNamespace(
        get_task_status=AsyncMock(
            return_value={"positions": [{"symbol": "BTC/USDT", "size": 2, "price": 50}]}
        )
    )
    assert (
        await svc._get_current_metric_value(
            pos_rule, {"live_task_id": "t1", "symbol": "BTC/USDT", "metric": "unrealized_pnl"}
        )
        == 100.0
    )
    svc.live_trading_service = SimpleNamespace(
        get_task_status=AsyncMock(
            return_value={"positions": [{"symbol": "ETH/USDT", "size": 1, "price": 10}]}
        )
    )
    assert (
        await svc._get_current_metric_value(
            pos_rule, {"live_task_id": "t1", "symbol": "BTC/USDT", "metric": "market_value"}
        )
        is None
    )

    # _get_current_metric_value: backtest result missing
    strat_rule = SimpleNamespace(alert_type=AlertType.STRATEGY, user_id="u1")
    svc.backtest_service = SimpleNamespace(get_result=AsyncMock(return_value=None))
    assert (
        await svc._get_current_metric_value(
            strat_rule, {"backtest_task_id": "bt1", "metric": "sharpe_ratio"}
        )
        is None
    )


@pytest.mark.asyncio
async def test_strategy_version_service_additional_coverage():
    """Cover new permission branches, existing-branch early return, and performance diff."""
    from app.db import database as db
    from app.models.backtest import BacktestResultModel, BacktestTask
    from app.services.strategy_version_service import VersionControlService

    svc = VersionControlService()

    # _require_strategy_owner: permission error path
    svc.strategy_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id="s1", user_id="other"))
    )
    with pytest.raises(PermissionError):
        await svc._require_strategy_owner("s1", "u1")

    # list_versions: happy path with filters + response mapping
    svc.strategy_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id="s1", user_id="u1"))
    )
    svc.version_repo = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                SimpleNamespace(
                    id="v1",
                    strategy_id="s1",
                    version_number=1,
                    version_name="v1",
                    branch="dev",
                    status="draft",
                    tags=[],
                    description=None,
                    params={},
                    is_active=True,
                    is_default=False,
                    is_current=True,
                    parent_version_id=None,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ]
        ),
        count=AsyncMock(return_value=1),
    )
    items, total = await svc.list_versions(
        user_id="u1", strategy_id="s1", branch="dev", status="draft", limit=10, offset=0
    )
    assert total == 1
    assert items[0]["id"] == "v1"

    # update_version unauthorized returns None
    svc.version_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id="v2", created_by="x")),
        update=AsyncMock(),
    )
    assert (
        await svc.update_version(
            "v2",
            "u1",
            SimpleNamespace(
                code=None, params=None, description=None, tags=None, status=None, changelog=None
            ),
        )
        is None
    )

    # set_version_default / activate_version unauthorized
    svc.version_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id="v2", created_by="x")),
        update=AsyncMock(),
        list=AsyncMock(return_value=[]),
    )
    assert await svc.set_version_default("v2", "u1") is False
    assert await svc.activate_version("v2", "u1") is False

    # compare_versions forbidden
    svc.version_repo = SimpleNamespace(
        get_by_id=AsyncMock(
            side_effect=[SimpleNamespace(created_by="x"), SimpleNamespace(created_by="u1")]
        )
    )
    with pytest.raises(PermissionError):
        await svc.compare_versions("u1", "s1", "a", "b")

    # rollback_version: missing current version
    svc.strategy_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id="s1", user_id="u1"))
    )
    svc.version_repo = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(
                id="t1", created_by="u1", version_name="v1", code="x", params={}
            )
        )
    )
    svc._get_current_version = AsyncMock(return_value=None)
    with pytest.raises(ValueError):
        await svc.rollback_version("u1", "s1", "t1", "r")

    # rollback_version: current version forbidden
    svc._get_current_version = AsyncMock(return_value=SimpleNamespace(id="c1", created_by="x"))
    with pytest.raises(PermissionError):
        await svc.rollback_version("u1", "s1", "t1", "r")

    # rollback_version: target version forbidden
    svc.version_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id="t1", created_by="x"))
    )
    with pytest.raises(PermissionError):
        await svc.rollback_version("u1", "s1", "t1", "r")

    # create_branch: existing branch early return
    svc.branch_repo = SimpleNamespace(list=AsyncMock(return_value=[SimpleNamespace(id="b1")]))
    svc.strategy_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id="s1", user_id="u1"))
    )
    b = await svc.create_branch(
        user_id="u1", strategy_id="s1", branch_name="dev", parent_branch=None
    )
    assert b.id == "b1"

    # _generate_performance_diff: available True + diff computed
    async with db.async_session_maker() as session:
        # Minimal tasks/results for two versions.
        t_from = BacktestTask(
            id="t_from",
            user_id="u1",
            strategy_id="s1",
            strategy_version_id="v_from",
            symbol="X",
            status="completed",
            request_data={},
            created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        )
        r_from = BacktestResultModel(task_id="t_from", total_return=1.0, sharpe_ratio=1.0)
        t_to = BacktestTask(
            id="t_to",
            user_id="u1",
            strategy_id="s1",
            strategy_version_id="v_to",
            symbol="X",
            status="completed",
            request_data={},
            created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        r_to = BacktestResultModel(task_id="t_to", total_return=2.5, sharpe_ratio=1.5)
        session.add_all([t_from, r_from, t_to, r_to])
        await session.commit()

    svc2 = VersionControlService()
    diff = await svc2._generate_performance_diff("v_from", "v_to")
    assert diff["available"] is True
    assert diff["diff"]["total_return"] == 1.5
