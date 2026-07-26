"""Direction B contract tests added by iteration 184."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.database import async_session_maker
from app.models.backtest import BacktestResultModel, BacktestTask
from app.schemas.ai_strategy_research import AIStrategyResearchRunRequest
from app.services import ai_strategy_research_service as research_module
from app.services.analytics_service import AnalyticsService
from app.services.backtest.service import BacktestService
from app.services.metrics_service import get_metrics_service


def test_required_robustness_normalizes_to_enabled_validation():
    request = AIStrategyResearchRunRequest(
        symbol="RB0",
        require_robustness_validation=True,
        robustness_validation=False,
    )

    assert request.robustness_validation is True
    assert request.require_robustness_validation is True


def test_production_paper_promotion_cannot_bypass_robustness(monkeypatch):
    """The service boundary, not only request validation, owns production enforcement."""
    request = AIStrategyResearchRunRequest(
        symbol="RB0",
        start_paper_trading=True,
        robustness_validation=False,
        require_robustness_validation=False,
    )

    class ProductionSettings:
        DEBUG = False
        model_fields_set = {"DEBUG"}

    monkeypatch.setattr(research_module, "get_settings", lambda: ProductionSettings())
    guarded = research_module._apply_production_promotion_guards(request)

    assert guarded.robustness_validation is True
    assert guarded.require_robustness_validation is True
    assert request.robustness_validation is False


@pytest.mark.asyncio
async def test_production_ai_research_requires_server_side_data_precheck(monkeypatch):
    request = AIStrategyResearchRunRequest(
        symbol="RB0", start_date="2024-01-01", end_date="2024-02-01"
    )

    class ProductionSettings:
        DEBUG = False
        model_fields_set = {"DEBUG"}

    class PrecheckService:
        async def precheck(self, _: object):
            return type(
                "Precheck",
                (),
                {
                    "passed": True,
                    "model_dump": lambda self, **__: {"passed": True, "status": "pass"},
                },
            )()

    monkeypatch.setattr(research_module, "get_settings", lambda: ProductionSettings())
    monkeypatch.setattr(
        research_module, "get_market_data_precheck_service", lambda: PrecheckService()
    )

    guarded = await research_module._apply_production_data_precheck(request)

    assert guarded.data_config["data_precheck"] == {"passed": True, "status": "pass"}


@pytest.mark.asyncio
async def test_production_ai_research_fails_closed_when_data_precheck_fails(monkeypatch):
    request = AIStrategyResearchRunRequest(symbol="RB0")

    class ProductionSettings:
        DEBUG = False
        model_fields_set = {"DEBUG"}

    class PrecheckService:
        async def precheck(self, _: object):
            raise RuntimeError("coverage service unavailable")

    monkeypatch.setattr(research_module, "get_settings", lambda: ProductionSettings())
    monkeypatch.setattr(
        research_module, "get_market_data_precheck_service", lambda: PrecheckService()
    )

    with pytest.raises(ValueError, match="precheck is unavailable"):
        await research_module._apply_production_data_precheck(request)


@pytest.mark.asyncio
async def test_summary_uses_nested_canonical_metrics_without_large_payloads():
    task = BacktestTask(
        id="summary-task",
        user_id="summary-user",
        strategy_id="summary-strategy",
        symbol="RB0",
        status="completed",
        request_data={"data_precheck": {"status": "pass"}},
        created_at=datetime.now(timezone.utc),
    )
    result = BacktestResultModel(
        id="summary-result",
        task_id=task.id,
        standard_metrics={
            "total_return": 12.5,
            "annual_return": 6.2,
            "sharpe_ratio": 1.4,
            "max_drawdown": -4.1,
            "win_rate": 55.0,
            "total_trades": 7,
            "profit_loss_ratio": 1.7,
        },
        equity_curve=[100000.0] * 10001,
        equity_dates=["2026-01-01"] * 10001,
        trades=[{"pnl": 1}] * 1001,
    )
    async with async_session_maker() as session:
        session.add_all([task, result])
        await session.commit()

    summary = await BacktestService().get_result_summary(task.id, user_id=task.user_id)

    assert summary is not None
    assert summary.metrics.total_return == 12.5
    assert summary.metrics.total_trades == 7
    assert "equity_curve" not in summary.model_dump()
    assert "trades" not in summary.model_dump()


def test_analytics_adapter_uses_metrics_service_canonical_values():
    fixture = {
        "equity_curve": [
            {"date": "2026-01-01", "total_assets": 100000.0},
            {"date": "2026-01-02", "total_assets": 110000.0},
        ],
        "trades": [{"pnl": 1000.0}, {"pnl": -500.0}],
    }
    canonical = get_metrics_service().calculate_from_log_data(
        {
            "equity_curve": [100000.0, 110000.0],
            "equity_dates": ["2026-01-01", "2026-01-02"],
            "trades": fixture["trades"],
        }
    )
    adapted = AnalyticsService().calculate_metrics(fixture)

    assert adapted.total_return == pytest.approx(canonical["total_return"] / 100.0)
    assert adapted.trade_count == canonical["total_trades"]
    assert adapted.profit_factor == canonical["profit_loss_ratio"]
