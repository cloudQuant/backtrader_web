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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial_status", "expected_status"),
    [
        ("materializing", "failed"),
        ("cancelling", "cancelled"),
    ],
)
async def test_restart_reconciliation_releases_orphaned_runtime_lease(
    monkeypatch: pytest.MonkeyPatch,
    initial_status: str,
    expected_status: str,
):
    """A dead owner cannot leave an internal runtime lease non-claimable forever."""
    from app.db.database import async_session_maker
    from app.models.user import User
    from app.models.workspace import StrategyUnit, Workspace
    from app.services.workspace import run_ops as workspace_run_ops
    from app.services.workspace.reconciliation import reconcile_orphaned_run_statuses
    from app.services.workspace_service import WorkspaceService

    suffix = initial_status
    user_id = f"reconcile-lease-user-{suffix}"
    workspace_id = f"reconcile-lease-workspace-{suffix}"
    unit_id = f"reconcile-lease-unit-{suffix}"
    lease_token = f"lease-reconcile-{suffix}"
    async with async_session_maker() as session:
        session.add_all(
            [
                User(
                    id=user_id,
                    username=f"reconcile_lease_{suffix}",
                    email=f"reconcile_lease_{suffix}@example.com",
                    hashed_password="hash",
                ),
                Workspace(
                    id=workspace_id,
                    user_id=user_id,
                    name="Restart reconciliation lease",
                    workspace_type="research",
                    settings={},
                ),
                StrategyUnit(
                    id=unit_id,
                    workspace_id=workspace_id,
                    strategy_id="reconcile-lease-strategy",
                    data_config={"market_data_binding_required": True},
                    run_status=initial_status,
                    last_task_id=lease_token,
                ),
            ]
        )
        await session.commit()

    assert await reconcile_orphaned_run_statuses() == 1

    async with async_session_maker() as session:
        unit = await session.get(StrategyUnit, unit_id)
        assert unit is not None
        assert unit.run_status == expected_status
        assert unit.last_task_id is None

    # The exact lease was cleared, so a fresh server-side claim can proceed.
    monkeypatch.setattr(workspace_run_ops, "async_session_maker", async_session_maker)
    next_lease, duplicate = await WorkspaceService()._claim_research_unit_run(workspace_id, unit_id)
    assert next_lease is not None
    assert duplicate is None


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_status", ["materializing", "cancelling"])
@pytest.mark.parametrize("task_status", ["pending", "running"])
async def test_reconciliation_keeps_fenced_unit_with_real_active_task(
    initial_status: str,
    task_status: str,
):
    """A restart observer must not release a real task merely because it is fenced."""
    from app.db.database import async_session_maker
    from app.models.backtest import BacktestTask
    from app.models.user import User
    from app.models.workspace import StrategyUnit, Workspace
    from app.services.workspace.reconciliation import reconcile_orphaned_run_statuses

    suffix = f"{initial_status}-{task_status}"
    user_id = f"reconcile-active-user-{suffix}"
    workspace_id = f"reconcile-active-workspace-{suffix}"
    unit_id = f"reconcile-active-unit-{suffix}"
    task_id = f"reconcile-active-task-{suffix}"
    async with async_session_maker() as session:
        session.add_all(
            [
                User(
                    id=user_id,
                    username=f"reconcile_active_{initial_status}_{task_status}",
                    email=f"reconcile_active_{initial_status}_{task_status}@example.com",
                    hashed_password="hash",
                ),
                Workspace(
                    id=workspace_id,
                    user_id=user_id,
                    name="Restart reconciliation active task",
                    workspace_type="research",
                    settings={},
                ),
                StrategyUnit(
                    id=unit_id,
                    workspace_id=workspace_id,
                    strategy_id="reconcile-active-strategy",
                    data_config={"market_data_binding_required": True},
                    run_status=initial_status,
                    last_task_id=task_id,
                ),
                BacktestTask(
                    id=task_id,
                    user_id=user_id,
                    strategy_id="reconcile-active-strategy",
                    symbol="000001.SZ",
                    status=task_status,
                ),
            ]
        )
        await session.commit()

    assert await reconcile_orphaned_run_statuses() == 0

    async with async_session_maker() as session:
        unit = await session.get(StrategyUnit, unit_id)
        assert unit is not None
        assert unit.run_status == initial_status
        assert unit.last_task_id == task_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial_status", "task_status", "expected_status"),
    [
        ("materializing", "completed", "completed"),
        ("cancelling", "completed", "cancelled"),
    ],
)
async def test_reconciliation_finishes_fenced_real_task_without_losing_identity(
    initial_status: str,
    task_status: str,
    expected_status: str,
):
    """Terminal task recovery keeps task identity for later result/bar-count reads."""
    from app.db.database import async_session_maker
    from app.models.backtest import BacktestTask
    from app.models.user import User
    from app.models.workspace import StrategyUnit, Workspace
    from app.services.workspace.reconciliation import reconcile_orphaned_run_statuses

    suffix = f"{initial_status}-{task_status}"
    user_id = f"reconcile-terminal-user-{suffix}"
    workspace_id = f"reconcile-terminal-workspace-{suffix}"
    unit_id = f"reconcile-terminal-unit-{suffix}"
    task_id = f"reconcile-terminal-task-{suffix}"
    async with async_session_maker() as session:
        session.add_all(
            [
                User(
                    id=user_id,
                    username=f"reconcile_terminal_{initial_status}_{task_status}",
                    email=f"reconcile_terminal_{initial_status}_{task_status}@example.com",
                    hashed_password="hash",
                ),
                Workspace(
                    id=workspace_id,
                    user_id=user_id,
                    name="Restart reconciliation terminal task",
                    workspace_type="research",
                    settings={},
                ),
                StrategyUnit(
                    id=unit_id,
                    workspace_id=workspace_id,
                    strategy_id="reconcile-terminal-strategy",
                    data_config={"market_data_binding_required": True},
                    run_status=initial_status,
                    last_task_id=task_id,
                ),
                BacktestTask(
                    id=task_id,
                    user_id=user_id,
                    strategy_id="reconcile-terminal-strategy",
                    symbol="000001.SZ",
                    status=task_status,
                ),
            ]
        )
        await session.commit()

    assert await reconcile_orphaned_run_statuses() == 1

    async with async_session_maker() as session:
        unit = await session.get(StrategyUnit, unit_id)
        assert unit is not None
        assert unit.run_status == expected_status
        assert unit.last_task_id == task_id
