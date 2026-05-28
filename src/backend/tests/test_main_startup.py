from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app import startup


def test_startup_hooks_register_subsystems_in_order():
    modules = [hook.__module__ for hook in startup.STARTUP_HOOKS]

    assert modules[0] == "app.startup.database"
    assert modules[1] == "app.startup.reconcile"
    assert modules[2] == "app.startup.audit_sink"
    assert modules[3] == "app.startup.ai_log_sink"
    assert modules[4] == "app.startup.security_check"
    assert modules[5] == "app.startup.orchestration"


def test_shutdown_hooks_register_subsystems_in_order():
    modules = [hook.__module__ for hook in startup.SHUTDOWN_HOOKS]

    assert modules == [
        "app.startup.orchestration",
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
