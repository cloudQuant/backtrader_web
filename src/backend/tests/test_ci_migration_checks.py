"""Regression coverage for CI migration checks used by Iteration 191."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_ci_script(name: str) -> ModuleType:
    path = REPO_ROOT / "scripts" / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_alembic_heads_check_targets_the_repository_backend_and_current_interpreter(monkeypatch):
    module = _load_ci_script("check_alembic_heads")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="head", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.BACKEND_DIR == REPO_ROOT / "src" / "backend"
    assert module.run_alembic_command(["heads"]) == (0, "head", "")
    assert captured["command"] == [sys.executable, "-m", "alembic", "heads"]
    assert captured["kwargs"]["cwd"] == str(REPO_ROOT / "src" / "backend")


def test_orm_drift_check_runs_alembic_with_its_current_interpreter(monkeypatch, tmp_path):
    module = _load_ci_script("check_orm_schema_drift")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module._run_alembic_upgrade(tmp_path / "drift.db")

    assert captured["command"] == [sys.executable, "-m", "alembic", "upgrade", "head"]
    assert captured["kwargs"]["cwd"] == module.BACKEND_SRC
