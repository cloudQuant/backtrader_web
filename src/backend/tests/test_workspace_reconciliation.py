import pytest


@pytest.mark.asyncio
async def test_reconcile_orphaned_run_statuses_skips_trading_workspaces():
    from app.db.database import async_session_maker
    from app.models.user import User
    from app.models.workspace import StrategyUnit, Workspace
    from app.services.workspace.reconciliation import reconcile_orphaned_run_statuses

    user = User(id="u1", username="u1", email="u1@example.com", hashed_password="x")
    trading_ws = Workspace(
        id="trading-ws",
        user_id="u1",
        name="交易工作区",
        workspace_type="trading",
    )
    research_ws = Workspace(
        id="research-ws",
        user_id="u1",
        name="研究工作区",
        workspace_type="research",
    )
    trading_unit = StrategyUnit(
        id="trading-unit",
        workspace_id="trading-ws",
        strategy_id="simulate/gateway_dual_ma",
        run_status="running",
        trading_instance_id="inst-1",
    )
    research_unit = StrategyUnit(
        id="research-unit",
        workspace_id="research-ws",
        strategy_id="demo",
        run_status="running",
    )

    async with async_session_maker() as session:
        session.add_all([user, trading_ws, research_ws, trading_unit, research_unit])
        await session.commit()

    changed = await reconcile_orphaned_run_statuses()

    async with async_session_maker() as session:
        refreshed_trading = await session.get(StrategyUnit, "trading-unit")
        refreshed_research = await session.get(StrategyUnit, "research-unit")

    assert changed == 1
    assert refreshed_trading.run_status == "running"
    assert refreshed_research.run_status == "idle"
