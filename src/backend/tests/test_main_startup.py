from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app import startup
from app.startup import asset_research


def test_startup_hooks_register_subsystems_in_order():
    modules = [hook.__module__ for hook in startup.STARTUP_HOOKS]

    assert modules[0] == "app.startup.database"
    assert modules[1] == "app.startup.reconcile"
    assert modules[2] == "app.startup.audit_sink"
    assert modules[3] == "app.startup.ai_log_sink"
    assert modules[4] == "app.startup.security_check"
    assert modules[5] == "app.startup.orchestration"
    assert modules[6] == "app.startup.asset_research"


def test_shutdown_hooks_register_subsystems_in_order():
    modules = [hook.__module__ for hook in startup.SHUTDOWN_HOOKS]

    assert modules == [
        "app.startup.orchestration",
        "app.startup.asset_research",
        "app.startup.stock_signal",
        "app.startup.paper_runtime",
        "app.startup.reconcile",
        "app.startup.audit_sink",
        "app.startup.ai_log_sink",
    ]


@pytest.mark.asyncio
async def test_run_startup_calls_hooks_in_order(monkeypatch):
    calls: list[tuple[str, FastAPI, SimpleNamespace]] = []

    async def first(app: FastAPI, settings: SimpleNamespace) -> None:
        calls.append(("first", app, settings))

    async def second(app: FastAPI, settings: SimpleNamespace) -> None:
        calls.append(("second", app, settings))

    monkeypatch.setattr(startup, "STARTUP_HOOKS", (first, second))
    app = FastAPI()
    settings = SimpleNamespace()

    await startup.run_startup(app, settings)

    assert [name for name, *_ in calls] == ["first", "second"]
    assert all(call[1] is app for call in calls)
    assert all(call[2] is settings for call in calls)


@pytest.mark.asyncio
async def test_run_shutdown_calls_hooks_in_order(monkeypatch):
    calls: list[tuple[str, FastAPI, SimpleNamespace]] = []

    async def first(app: FastAPI, settings: SimpleNamespace) -> None:
        calls.append(("first", app, settings))

    async def second(app: FastAPI, settings: SimpleNamespace) -> None:
        calls.append(("second", app, settings))

    monkeypatch.setattr(startup, "SHUTDOWN_HOOKS", (first, second))
    app = FastAPI()
    settings = SimpleNamespace()

    await startup.run_shutdown(app, settings)

    assert [name for name, *_ in calls] == ["first", "second"]
    assert all(call[1] is app for call in calls)
    assert all(call[2] is settings for call in calls)


@pytest.mark.asyncio
async def test_asset_research_startup_and_shutdown_manage_all_durable_workers(monkeypatch):
    calls: list[str] = []

    class FakeRunner:
        def __init__(self, name: str) -> None:
            self.name = name

        async def start(self) -> bool:
            calls.append(f"start:{self.name}")
            return True

        async def shutdown(self) -> None:
            calls.append(f"shutdown:{self.name}")

    task_runner = FakeRunner("task")
    schedule_runner = FakeRunner("schedule")
    outcome_runner = FakeRunner("outcome")
    monkeypatch.setattr(
        asset_research,
        "get_asset_research_task_runner",
        lambda: task_runner,
    )
    monkeypatch.setattr(
        asset_research,
        "get_asset_research_schedule_runner",
        lambda: schedule_runner,
    )
    monkeypatch.setattr(
        asset_research,
        "get_asset_research_outcome_runner",
        lambda: outcome_runner,
    )
    app = FastAPI()
    settings = SimpleNamespace(
        ASSET_RESEARCH_TASK_RUNNER_ENABLED=True,
        ASSET_RESEARCH_SCHEDULE_ENABLED=True,
        ASSET_RESEARCH_OUTCOME_EVALUATOR_ENABLED=True,
    )

    await asset_research.register(app, settings)
    await asset_research.shutdown(app, settings)

    assert calls == [
        "start:task",
        "start:schedule",
        "start:outcome",
        "shutdown:task",
        "shutdown:schedule",
        "shutdown:outcome",
    ]
