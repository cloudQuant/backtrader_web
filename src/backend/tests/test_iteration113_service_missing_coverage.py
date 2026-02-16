import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _new_service_without_init(cls):
    obj = cls.__new__(cls)
    return obj


@pytest.mark.asyncio
async def test_backtest_service_execute_backtest_missing_branches(tmp_path: Path, monkeypatch):
    """Cover _execute_backtest branches: tmp_logs cleanup, custom params write, parse_all_logs empty, persist copy, cleanup except."""
    from app.services.backtest_service import BacktestService
    from app.schemas.backtest import BacktestRequest, TaskStatus

    svc = BacktestService()

    # Build strategy dir with run.py, config.yaml and logs/ to trigger tmp_logs cleanup.
    strategies_dir = tmp_path / "strategies"
    strategy_dir = strategies_dir / "s1"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "run.py").write_text("print('ok')\n")
    (strategy_dir / "config.yaml").write_text("params:\n  p: 1\n")
    (strategy_dir / "logs").mkdir()

    # datas dir exists to potentially symlink (safe).
    (tmp_path / "datas").mkdir()

    req = BacktestRequest(
        strategy_id="s1",
        symbol="000001.SZ",
        start_date="2024-01-01T00:00:00",
        end_date="2024-06-30T00:00:00",
        initial_cash=200000,  # custom params branch
        commission=0.001,
        params={"p": 2},
    )

    # Stub out subprocess run + parsing to avoid heavy ops.
    monkeypatch.setattr(svc, "_run_strategy_subprocess", AsyncMock(return_value={"stdout": "x"}))

    # Ensure tmp log dir exists so persist copytree branch executes.
    tmp_log_dir = tmp_path / "tmp_logs_persist"
    tmp_log_dir.mkdir()

    log_result_ok = {
        "total_return": 1.0,
        "log_dir": str(tmp_log_dir),
        "equity_curve": [],
        "equity_dates": [],
        "drawdown_curve": [],
        "trades": [],
    }

    with patch("app.services.strategy_service.STRATEGIES_DIR", strategies_dir):
        with patch("app.services.log_parser_service.parse_all_logs", return_value=log_result_ok):
            with patch.object(svc.result_repo, "create", new=AsyncMock()):
                with patch.object(svc.task_repo, "update", new=AsyncMock()):
                    with patch("app.services.backtest_service.ws_manager") as mock_ws:
                        mock_ws.send_to_task = AsyncMock()
                        # observe internal calls: tmp_logs cleanup, config overwrite, persist copytree
                        with patch("shutil.rmtree") as mock_rmtree:
                            with patch("shutil.copytree") as mock_copytree:
                                await svc._execute_backtest("t1", "u1", req)
                                assert mock_rmtree.called  # tmp_logs cleanup executed
                                assert mock_copytree.called  # persist copy executed

    # parse_all_logs empty -> raises -> status FAILED (covers the raise ValueError branch).
    req2 = BacktestRequest(
        strategy_id="s1",
        symbol="000001.SZ",
        start_date="2024-01-01T00:00:00",
        end_date="2024-06-30T00:00:00",
    )
    with patch("app.services.strategy_service.STRATEGIES_DIR", strategies_dir):
        with patch("app.services.log_parser_service.parse_all_logs", return_value={}):
            with patch.object(svc.task_repo, "update", new=AsyncMock()) as mock_update:
                with patch("app.services.backtest_service.ws_manager") as mock_ws:
                    mock_ws.send_to_task = AsyncMock()
                    await svc._execute_backtest("t2", "u1", req2)
                    last = mock_update.call_args_list[-1]
                    assert last.args[1]["status"] == TaskStatus.FAILED

    # Cleanup finally: simulate shutil.rmtree raising to cover exception swallow.
    with patch("app.services.strategy_service.STRATEGIES_DIR", strategies_dir):
        with patch.object(svc, "_run_strategy_subprocess", AsyncMock(side_effect=RuntimeError("x"))):
            with patch.object(svc.task_repo, "update", new=AsyncMock()):
                with patch("app.services.backtest_service.ws_manager") as mock_ws:
                    mock_ws.send_to_task = AsyncMock()

                    real_rmtree = __import__("shutil").rmtree

                    def _rmtree_side_effect(path, *args, **kwargs):
                        # Only raise on the cleanup rmtree which passes ignore_errors=True.
                        if kwargs.get("ignore_errors") is True:
                            raise RuntimeError("cleanup failed")
                        return real_rmtree(path, *args, **kwargs)

                    with patch("shutil.rmtree", side_effect=_rmtree_side_effect):
                        await svc._execute_backtest("t3", "u1", req2)


def test_comparison_service_compare_equity_default_initial():
    """Cover _compare_equity default initial capital branch when curve starts after the earliest date."""
    from app.services.comparison_service import ComparisonService

    svc = _new_service_without_init(ComparisonService)
    backtest_results = {
        "a": {"equity_dates": ["2026-01-02"], "equity_curve": [101000.0]},
        "b": {"equity_dates": ["2026-01-01"], "equity_curve": [100000.0]},
    }
    out = svc._compare_equity(backtest_results)
    assert out["curves"]["a"][0] == 100000.0


@pytest.mark.asyncio
async def test_comparison_service_update_comparison_with_description_and_backtest_ids():
    """Cover update_comparison branches setting description and regenerating comparison_data."""
    from app.services.comparison_service import ComparisonService
    from app.schemas.comparison import ComparisonUpdate

    svc = _new_service_without_init(ComparisonService)
    svc.comparison_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id="c1", user_id="u1", type="equity")),
        update=AsyncMock(return_value=SimpleNamespace(id="c1", user_id="u1", type="equity")),
    )
    svc.backtest_service = SimpleNamespace(
        get_result=AsyncMock(return_value=SimpleNamespace(
            strategy_id="s1",
            total_return=1.0,
            sharpe_ratio=1.0,
            max_drawdown=-1.0,
            win_rate=50.0,
            equity_curve=[1.0],
            equity_dates=["2026-01-01"],
            drawdown_curve=[0.0],
        ))
    )
    svc._generate_comparison_data = AsyncMock(return_value={"ok": True})
    svc._to_response = MagicMock(return_value={"id": "c1"})

    upd = ComparisonUpdate(description="d", backtest_task_ids=["t1"])
    out = await svc.update_comparison("c1", "u1", upd)
    assert out["id"] == "c1"


@pytest.mark.asyncio
async def test_live_trading_manager_missing_branches(tmp_path: Path, monkeypatch):
    """Cover LiveTradingManager: _find_latest_log_dir return None, list_instances refresh, stop_instance kill branch, start_all/stop_all branches, _wait_process exception paths."""
    from app.services import live_trading_manager as m

    # _find_latest_log_dir: logs dir exists but contains no subdir.
    sdir = tmp_path / "s1"
    (sdir / "logs").mkdir(parents=True)
    (sdir / "logs" / "file.txt").write_text("x")
    assert m._find_latest_log_dir(sdir) is None

    # list_instances refresh running->stopped if pid dead
    monkeypatch.setattr(m, "_load_instances", lambda: {"iid": {"strategy_id": "s1", "status": "running", "pid": None, "user_id": "u1"}})
    monkeypatch.setattr(m, "_save_instances", lambda _data: None)
    monkeypatch.setattr(m, "_is_pid_alive", lambda _pid: False)
    with patch.object(m, "STRATEGIES_DIR", tmp_path):
        mgr = m.LiveTradingManager()
        out = mgr.list_instances(user_id="u1")
        assert out[0]["status"] == "stopped"

    # stop_instance: proc.terminate then wait fails -> proc.kill called.
    fake_proc = SimpleNamespace(returncode=None, terminate=MagicMock(), kill=MagicMock())

    async def _wait_raises():
        raise RuntimeError("wait fail")

    fake_proc.wait = _wait_raises
    monkeypatch.setattr(mgr, "_processes", {"iid": fake_proc})
    monkeypatch.setattr(m, "_load_instances", lambda: {"iid": {"strategy_id": "s1", "status": "running", "pid": 123, "user_id": "u1"}})
    monkeypatch.setattr(m, "_save_instances", lambda _data: None)
    monkeypatch.setattr(m, "_is_pid_alive", lambda _pid: True)
    monkeypatch.setattr(mgr, "_kill_pid", MagicMock())
    await mgr.stop_instance("iid")
    assert fake_proc.kill.called

    # start_all: skip already running & alive
    monkeypatch.setattr(m, "_load_instances", lambda: {"a": {"strategy_id": "s1", "status": "running", "pid": 1}, "b": {"strategy_id": "s1", "status": "stopped", "pid": None}})
    monkeypatch.setattr(m, "_is_pid_alive", lambda _pid: True)

    started = []

    async def _start_instance(iid):
        started.append(iid)
        return {"id": iid}

    monkeypatch.setattr(mgr, "start_instance", _start_instance)
    res = await mgr.start_all()
    assert "b" in started
    assert all(d["id"] != "a" for d in res["details"] if d["result"] == "started")

    # stop_all: skip non-running; raise for one -> failed path
    monkeypatch.setattr(m, "_load_instances", lambda: {"a": {"strategy_id": "s1", "status": "stopped"}, "b": {"strategy_id": "s1", "status": "running"}})

    async def _stop_instance(iid):
        raise RuntimeError("nope")

    monkeypatch.setattr(mgr, "stop_instance", _stop_instance)
    res2 = await mgr.stop_all()
    assert res2["failed"] == 1

    # _wait_process: proc.wait raises (except pass), stderr.read raises (except pass)
    class _BadStderr:
        async def read(self):
            raise RuntimeError("read fail")

    class _BadProc:
        returncode = 1
        stderr = _BadStderr()

        async def wait(self):
            raise RuntimeError("wait fail")

    monkeypatch.setattr(m, "_load_instances", lambda: {"iid": {"strategy_id": "s1", "status": "running"}})
    monkeypatch.setattr(m, "_save_instances", lambda _data: None)
    with patch.object(m, "STRATEGIES_DIR", tmp_path):
        await mgr._wait_process("iid", _BadProc())


@pytest.mark.asyncio
async def test_monitoring_service_missing_branches(monkeypatch):
    """Cover monitoring_service: early return, trigger path, all sleep branches, and POSITION gt threshold."""
    from app.services.monitoring_service import MonitoringService
    from app.models.alerts import AlertType

    svc = _new_service_without_init(MonitoringService)
    svc.alert_rule_repo = SimpleNamespace(get_by_id=AsyncMock())

    # early return when rule not active
    svc.alert_rule_repo.get_by_id.return_value = SimpleNamespace(is_active=False)
    await svc._monitor_task("r1")

    # Loop: make it run one iteration for each sleep branch then cancel via sleep raising CancelledError.
    async def _sleep_cancel(_):
        raise asyncio.CancelledError()

    import asyncio
    monkeypatch.setattr(asyncio, "sleep", _sleep_cancel)

    rule = SimpleNamespace(id="r2", is_active=True, alert_type=AlertType.SYSTEM, trigger_type="manual", trigger_config={}, triggered_count=0)
    svc.alert_rule_repo.get_by_id = AsyncMock(return_value=rule)
    svc._check_trigger = AsyncMock(return_value=True)
    svc._trigger_alert = AsyncMock()
    await svc._monitor_task("r2")

    # ACCOUNT/POSITION branch
    rule.alert_type = AlertType.ACCOUNT
    await svc._monitor_task("r2")
    rule.alert_type = AlertType.POSITION
    await svc._monitor_task("r2")

    # STRATEGY branch
    rule.alert_type = AlertType.STRATEGY
    await svc._monitor_task("r2")

    # else branch (ORDER)
    rule.alert_type = AlertType.ORDER
    await svc._monitor_task("r2")

    # POSITION threshold condition gt branch
    rule.alert_type = AlertType.POSITION
    rule.trigger_type = "threshold"
    rule.trigger_config = {"current_value": 2.0, "threshold": 1.0, "condition": "gt", "metric": "unrealized_pnl", "symbol": "X"}
    ok = await svc._check_threshold_trigger(rule, rule.trigger_config)
    assert ok is True


@pytest.mark.asyncio
async def test_optimization_service_missing_branches(monkeypatch):
    """Cover optimization_service: grid warning branch, objective metric branches, _wait_for_backtest loop completed path."""
    from app.services.optimization_service import OptimizationService
    from app.schemas.backtest_enhanced import OptimizationRequest, BacktestRequest, TaskStatus

    svc = _new_service_without_init(OptimizationService)
    svc.backtest_service = SimpleNamespace(run_backtest=AsyncMock(), get_task_status=AsyncMock(), get_result=AsyncMock())

    # run_grid_search: backtest completed not satisfied -> warning branch line 98
    bt_req = BacktestRequest(
        strategy_id="s",
        symbol="000001.SZ",
        start_date="2024-01-01T00:00:00",
        end_date="2024-02-15T00:00:00",
        initial_cash=100000,
        commission=0.001,
    )
    opt_req = OptimizationRequest(
        strategy_id="s",
        backtest_config=bt_req,
        param_grid={"p": [1]},
        metric="sharpe_ratio",
        param_bounds={"p": {"type": "int", "min": 1, "max": 1}},
        n_trials=10,
    )
    svc.backtest_service.run_backtest.return_value = SimpleNamespace(task_id="t1")
    svc._wait_for_backtest = AsyncMock(return_value=SimpleNamespace(status=TaskStatus.FAILED))
    out = await OptimizationService.run_grid_search(svc, "u1", opt_req)
    assert out.n_trials == 0

    # run_bayesian_optimization: cover metric branches in objective and failure return.
    class DummyTrial:
        def suggest_int(self, name, a, b):
            return a

        def suggest_float(self, name, a, b):
            return a

        def suggest_categorical(self, name, choices):
            return choices[0]

        @property
        def params(self):
            return {}

    class DummyStudy:
        def __init__(self):
            self.best_params = {"p": 1}
            self.best_trial = SimpleNamespace(value=-1.0)
            self.trials = [SimpleNamespace(params={"p": 1}, value=-1.0)]

        def optimize(self, objective, n_trials):
            objective(DummyTrial())

    dummy_optuna = types.SimpleNamespace(create_study=lambda direction: DummyStudy())
    monkeypatch.setitem(sys.modules, "optuna", dummy_optuna)

    completed = SimpleNamespace(status=TaskStatus.COMPLETED, sharpe_ratio=2.0, total_return=3.0, max_drawdown=-4.0, annual_return=0.0, win_rate=0.0, error_message="")
    failed = SimpleNamespace(status=TaskStatus.FAILED, sharpe_ratio=0.0, total_return=0.0, max_drawdown=0.0, annual_return=0.0, win_rate=0.0, error_message="err")

    svc._run_single_backtest = AsyncMock(return_value=completed)

    # COMPLETED + max_drawdown (lines 175-176)
    def _run_coroutine_threadsafe_returning(result_obj):
        def _run_coroutine_threadsafe(coro, _loop):
            coro.close()
            return SimpleNamespace(result=lambda: result_obj)

        return _run_coroutine_threadsafe

    req2 = OptimizationRequest(strategy_id="s", backtest_config=bt_req, param_grid={"p": [1]}, metric="max_drawdown", param_bounds={"p": {"type": "int", "min": 1, "max": 2}}, n_trials=10)
    with patch("asyncio.run_coroutine_threadsafe", new=_run_coroutine_threadsafe_returning(completed)):
        await OptimizationService.run_bayesian_optimization(svc, "u", req2)

    # COMPLETED + total_return (lines 177-178)
    req3 = OptimizationRequest(strategy_id="s", backtest_config=bt_req, param_grid={"p": [1]}, metric="total_return", param_bounds={"p": {"type": "int", "min": 1, "max": 2}}, n_trials=10)
    with patch("asyncio.run_coroutine_threadsafe", new=_run_coroutine_threadsafe_returning(completed)):
        await OptimizationService.run_bayesian_optimization(svc, "u", req3)

    # COMPLETED + fallback metric (lines 179-180)
    req4 = SimpleNamespace(
        strategy_id="s",
        backtest_config=bt_req,
        metric="other",
        param_bounds={"p": {"type": "int", "min": 1, "max": 2}},
        n_trials=10,
    )
    with patch("asyncio.run_coroutine_threadsafe", new=_run_coroutine_threadsafe_returning(completed)):
        await OptimizationService.run_bayesian_optimization(svc, "u", req4)

    # FAILED -> worst value return (lines 182-183)
    req5 = OptimizationRequest(strategy_id="s", backtest_config=bt_req, param_grid={"p": [1]}, metric="sharpe_ratio", param_bounds={"p": {"type": "int", "min": 1, "max": 2}}, n_trials=10)
    with patch("asyncio.run_coroutine_threadsafe", new=_run_coroutine_threadsafe_returning(failed)):
        await OptimizationService.run_bayesian_optimization(svc, "u", req5)

    # _wait_for_backtest: loop returns COMPLETED path (line 330)
    svc.backtest_service.get_task_status = AsyncMock(side_effect=[TaskStatus.PENDING, TaskStatus.COMPLETED])
    svc.backtest_service.get_result = AsyncMock(return_value=completed)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    got = await OptimizationService._wait_for_backtest(svc, "t", timeout=2)
    assert got.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_param_optimization_service_missing_branches(tmp_path: Path, monkeypatch):
    """Cover param_optimization_service: trial cleanup exception, cancellation branches, thread exception, finally cleanup exception."""
    from app.services import param_optimization_service as p

    # _run_single_trial: trigger cleanup exception path (lines 145-146).
    base = tmp_path / "base"
    base.mkdir()

    def _copytree(_src, dst, dirs_exist_ok=False):
        Path(dst).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(p.shutil, "copytree", _copytree)
    monkeypatch.setattr(p.subprocess, "run", MagicMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(p.shutil, "rmtree", MagicMock(side_effect=RuntimeError("rm boom")))
    out = p._run_single_trial("sdir", {"p": 1}, 0, str(base))
    assert out["success"] is False

    # _run_optimization_thread: cancelled before submit loop -> break (line 338)
    t = {"status": "cancelled", "failed": 0}
    monkeypatch.setattr(p, "_get_task", lambda _tid: t)
    monkeypatch.setattr(p, "_update_task", lambda *a, **k: None)

    class DummyExecutor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            raise AssertionError("should not submit")

    monkeypatch.setattr(p, "ProcessPoolExecutor", lambda max_workers: DummyExecutor())
    monkeypatch.setattr(p, "as_completed", lambda futures: [])
    p._run_optimization_thread("tid", "sdir", [{"p": 1}], 1)

    # cancelled during as_completed: cancel pending futures (lines 349-351)
    class DummyFuture:
        def __init__(self):
            self.cancel = MagicMock()

        def result(self, timeout=None):
            return {"success": True, "params": {"p": 1}, "metrics": {"annual_return": 1.0}}

    futures_created = []

    class DummyExecutor2(DummyExecutor):
        def submit(self, fn, *args, **kwargs):
            fut = DummyFuture()
            futures_created.append(fut)
            return fut

    # Return running during submission checks, then cancelled when collecting results.
    call_count = {"n": 0}

    def _get_task_cancel_on_collect(_tid):
        call_count["n"] += 1
        # First two calls happen in the submission loop for a 2-item grid.
        if call_count["n"] <= 2:
            return {"status": "running", "failed": 0}
        return {"status": "cancelled", "failed": 0}

    monkeypatch.setattr(p, "_get_task", _get_task_cancel_on_collect)
    monkeypatch.setattr(p, "ProcessPoolExecutor", lambda max_workers: DummyExecutor2())
    monkeypatch.setattr(p, "as_completed", lambda futures: list(futures)[:1])

    p._run_optimization_thread("tid2", "sdir", [{"p": 1}, {"p": 2}], 1)
    assert any(f.cancel.called for f in futures_created)

    # Exception path (lines 374-376) + finally rmtree exception (lines 380-381)
    def _boom_executor(_max_workers):
        raise RuntimeError("executor boom")

    monkeypatch.setattr(p, "ProcessPoolExecutor", _boom_executor)
    monkeypatch.setattr(p, "tempfile", SimpleNamespace(mkdtemp=lambda prefix: str(tmp_path / "tb")))
    monkeypatch.setattr(p.shutil, "rmtree", MagicMock(side_effect=RuntimeError("rmtree boom")))
    p._run_optimization_thread("tid3", "sdir", [{"p": 1}], 1)


@pytest.mark.asyncio
async def test_paper_trading_service_missing_branches():
    """Cover paper_trading_service: short unrealized pnl branch, short close realized pnl branch, and get_order."""
    from app.services.paper_trading_service import PaperTradingService
    from app.models.paper_trading import OrderSide

    svc = _new_service_without_init(PaperTradingService)
    svc.position_repo = SimpleNamespace(update=AsyncMock(), create=AsyncMock(), list=AsyncMock(return_value=[]))
    svc.trade_repo = SimpleNamespace(update=AsyncMock())
    svc.order_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(id="o1")))
    svc.account_repo = SimpleNamespace(update=AsyncMock())
    svc._notify_account_update = AsyncMock()
    svc._notify_position_update = AsyncMock()
    svc._get_last_trade = AsyncMock(return_value=SimpleNamespace(id="t1"))

    account = SimpleNamespace(
        id="a1",
        user_id="u1",
        initial_cash=1000.0,
        current_cash=1000.0,
        total_equity=1000.0,
        profit_loss=0.0,
        profit_loss_pct=0.0,
        is_active=True,
    )

    # Existing short position; sell more -> new_size negative => unrealized_pnl short branch.
    pos = SimpleNamespace(id="p1", account_id="a1", symbol="X", size=-1, avg_price=10.0, market_value=-10.0)
    svc._get_position = AsyncMock(return_value=pos)
    order_sell = SimpleNamespace(id="o1", account_id="a1", symbol="X", side=OrderSide.SELL, size=1, status="filled")
    await PaperTradingService._update_position(svc, account, order_sell, price=9.0, commission=0.0)

    # Close short: buy enough -> realized pnl short close branch.
    pos2 = SimpleNamespace(id="p2", account_id="a1", symbol="X", size=-2, avg_price=10.0, market_value=-20.0)
    svc._get_position = AsyncMock(return_value=pos2)
    order_buy = SimpleNamespace(id="o2", account_id="a1", symbol="X", side=OrderSide.BUY, size=2, status="filled")
    await PaperTradingService._update_position(svc, account, order_buy, price=8.0, commission=0.0)

    got = await PaperTradingService.get_order(svc, "o1")
    assert got.id == "o1"


def test_strategy_service_to_response_paramspec_and_inference():
    """Cover strategy_service._to_response ParamSpec passthrough and type inference branches."""
    from app.services.strategy_service import StrategyService
    from app.schemas.strategy import ParamSpec

    svc = _new_service_without_init(StrategyService)

    strat = SimpleNamespace(
        id="s1",
        user_id="u1",
        name="n",
        description="d",
        code="c",
        category="cat",
        created_at="2026-02-15T00:00:00",
        updated_at="2026-02-15T00:00:00",
        params={
            "p_spec": ParamSpec(type="int", default=1, description="p"),
            "p_bool": True,
            "p_float": 1.5,
            "p_str": "x",
        },
    )
    resp = StrategyService._to_response(svc, strat)
    assert resp.params["p_spec"].default == 1
    assert resp.params["p_bool"].type == "bool"
    assert resp.params["p_float"].type == "float"
    assert resp.params["p_str"].type == "string"


@pytest.mark.asyncio
async def test_strategy_version_service_missing_branches(monkeypatch):
    """Cover strategy_version_service: parent_version_id, update_dict fields, changelog set, get_current, unset default/active loops."""
    from app.services.strategy_version_service import VersionControlService
    from app.schemas.strategy_version import VersionUpdate
    from app.models.strategy_version import VersionStatus

    svc = _new_service_without_init(VersionControlService)
    svc.strategy_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(id="s1", user_id="u1")))
    svc.version_repo = SimpleNamespace(create=AsyncMock(), list=AsyncMock(), update=AsyncMock())
    svc.branch_repo = SimpleNamespace(get_by_id=AsyncMock(), create=AsyncMock(), update=AsyncMock())

    svc._get_or_create_branch = AsyncMock(return_value=SimpleNamespace(id="b1"))
    svc._get_next_version_number = AsyncMock(return_value=2)
    svc._unset_default_versions = AsyncMock()
    svc._update_branch = AsyncMock()

    last = SimpleNamespace(id="v_last")
    svc._get_latest_version = AsyncMock(return_value=last)

    created = await VersionControlService.create_version(
        svc,
        user_id="u1",
        strategy_id="s1",
        version_name="v2",
        code="x",
        params={},
        branch="main",
        tags=[],
        changelog="c",
        is_default=False,
    )
    # version_repo.create gets a version whose parent_version_id was set.
    args, _kwargs = svc.version_repo.create.call_args
    assert getattr(args[0], "parent_version_id", None) == "v_last"

    # update_version: params/description/tags/status/changelog branches
    version_obj = SimpleNamespace(id="v1", strategy_id="s1", status=VersionStatus.DRAFT, changelog=None, is_active=True, is_default=False, created_by="u1")
    svc.version_repo.get_by_id = AsyncMock(return_value=version_obj)
    svc.version_repo.update = AsyncMock(return_value=version_obj)
    from app.services.strategy_version_service import ws_manager
    monkeypatch.setattr(ws_manager, "send_to_task", AsyncMock())

    upd = VersionUpdate(params={"p": 1}, description="d", tags=["t"], status=VersionStatus.STABLE, changelog="cl")
    got = await VersionControlService.update_version(svc, "v1", "u1", upd)
    assert got.id == "v1"
    upd_dict = svc.version_repo.update.call_args.args[1]
    assert upd_dict["params"] == {"p": 1}
    assert upd_dict["description"] == "d"
    assert upd_dict["tags"] == ["t"]
    assert upd_dict["status"] == VersionStatus.STABLE
    assert upd_dict["changelog"] == "cl"

    # _get_current_version (lines 621-629)
    svc.version_repo.list = AsyncMock(return_value=[SimpleNamespace(id="vcur")])
    cur = await VersionControlService._get_current_version(svc, "s1")
    assert cur.id == "vcur"

    # _unset_default_versions loop (line 683)
    svc.version_repo.list = AsyncMock(return_value=[SimpleNamespace(id="v1"), SimpleNamespace(id="v2")])
    await VersionControlService._unset_default_versions(svc, "s1", "main")
    assert svc.version_repo.update.called

    # _unset_active_versions loop (line 706)
    svc.version_repo.update.reset_mock()
    svc.version_repo.list = AsyncMock(return_value=[SimpleNamespace(id="v1")])
    await VersionControlService._unset_active_versions(svc, "s1", "main")
    svc.version_repo.update.assert_called()


def test_live_trading_service_import_and_run_branches(tmp_path: Path, monkeypatch):
    """Cover live_trading_service: sys.path insert, import success, _run_live_trading body + exception, and params default set."""
    # Prepare a fake HOME so BACKTRADER_PATH.exists() is True.
    fake_home = tmp_path / "home"
    (fake_home / "Documents" / "backtrader").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))

    # Build a fake backtrader package tree in sys.modules.
    bt = types.ModuleType("backtrader")

    class _BTStrategy:
        pass

    class _Broker:
        def __init__(self):
            self._cash = 0.0
            self.orders = []

        def setcash(self, v):
            self._cash = v

        def getcash(self):
            return self._cash

        def getvalue(self):
            return self._cash

        def getposition(self, _data):
            return None

    class _Cerebro:
        def __init__(self):
            self.broker = _Broker()
            self.datas = []

        def adddata(self, data):
            self.datas.append(data)

        def addstrategy(self, _strategy):
            return None

        def setbroker(self, _broker):
            self.broker = _broker

        def addobserver(self, _obs):
            return None

        def run(self):
            raise RuntimeError("run fail")

        def stop(self):
            return None

    bt.Strategy = _BTStrategy
    bt.Cerebro = _Cerebro

    brokers_ccxt = types.ModuleType("backtrader.brokers.ccxtbroker")
    brokers_ccxt.CCXTBroker = object
    brokers_ccxt.CCXTStore = object

    feeds_ccxt = types.ModuleType("backtrader.feeds.ccxtdata")

    class _CCXTData:
        def __init__(self, dataname, name, timeframe, fromdate, todate):
            self._name = dataname

    feeds_ccxt.CCXTData = _CCXTData

    observers_broker = types.ModuleType("backtrader.observers.broker")
    observers_broker.BrokerObserver = object

    stores_ccxt = types.ModuleType("backtrader.stores.ccxtstore")

    class _CCXTStore:
        def __init__(self, **_kwargs):
            pass

        def getbroker(self):
            return _Broker()

    stores_ccxt.CCXTStore = _CCXTStore

    for name, mod in {
        "backtrader": bt,
        "backtrader.brokers.ccxtbroker": brokers_ccxt,
        "backtrader.feeds.ccxtdata": feeds_ccxt,
        "backtrader.observers.broker": observers_broker,
        "backtrader.stores.ccxtstore": stores_ccxt,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)

    # Reload module to execute import-time branches.
    mod = importlib.reload(importlib.import_module("app.services.live_trading_service"))

    svc = mod.LiveTradingService()

    # Run submit_live_strategy but force thread target to run inline (avoid actual threading).
    targets = []

    class _DeferredThread:
        def __init__(self, target, daemon=True):
            self._target = target
            self.daemon = daemon

        def start(self):
            targets.append(self._target)

    monkeypatch.setattr(mod.threading, "Thread", _DeferredThread)

    svc.tasks = {}
    task_id = asyncio.run(svc.submit_live_strategy(
        user_id="u1",
        strategy_code=(
            "import backtrader as bt\n"
            "class PObj:\n"
            "  def __init__(self):\n"
            "    self.default = None\n"
            "class Params:\n"
            "  def __init__(self):\n"
            "    self._m = {'p': PObj()}\n"
            "  def _get(self, k):\n"
            "    return self._m[k]\n"
            "class S(bt.Strategy):\n"
            "  params = Params()\n"
        ),
        exchange="binance",
        symbols=["BTC/USDT"],
        api_key="k",
        secret="s",
        strategy_params={"p": 1},
        sandbox=False,
    ))
    assert task_id in svc.tasks
    assert len(targets) == 1
    targets[0]()  # run inline after task record exists
    assert svc.tasks[task_id]["status"] in ("running", "failed")

    # _load_strategy_from_code: cover params default set branch (lines 182-183).
    code = (
        "import backtrader as bt\n"
        "class PObj:\n"
        "  def __init__(self):\n"
        "    self.default = None\n"
        "class Params:\n"
        "  def __init__(self):\n"
        "    self._m = {'p': PObj()}\n"
        "  def _get(self, k):\n"
        "    return self._m[k]\n"
        "class S(bt.Strategy):\n"
        "  params = Params()\n"
    )
    strat_cls = svc._load_strategy_from_code(code, {"p": 123})
    assert strat_cls.params._get("p").default == 123
