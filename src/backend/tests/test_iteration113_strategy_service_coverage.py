from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from datetime import datetime, timezone


def test_scan_strategies_folder_when_dir_missing(monkeypatch, tmp_path):
    from app.services import strategy_service as ss

    monkeypatch.setattr(ss, "STRATEGIES_DIR", tmp_path / "missing", raising=True)
    assert ss._scan_strategies_folder() == []


def test_scan_strategies_folder_skips_when_no_code_files(monkeypatch, tmp_path):
    from app.services import strategy_service as ss

    strategies_dir = tmp_path / "strategies"
    s1 = strategies_dir / "s1"
    s1.mkdir(parents=True)
    (s1 / "config.yaml").write_text("strategy:\n  name: s1\n", encoding="utf-8")
    monkeypatch.setattr(ss, "STRATEGIES_DIR", strategies_dir, raising=True)

    # No strategy_*.py -> continue branch.
    assert ss._scan_strategies_folder() == []


def test_scan_strategies_folder_handles_bad_yaml(monkeypatch, tmp_path):
    from app.services import strategy_service as ss

    strategies_dir = tmp_path / "strategies"
    s1 = strategies_dir / "s1"
    s1.mkdir(parents=True)
    (s1 / "config.yaml").write_text(":\n:bad\n", encoding="utf-8")
    (s1 / "strategy_x.py").write_text("print('x')\n", encoding="utf-8")
    monkeypatch.setattr(ss, "STRATEGIES_DIR", strategies_dir, raising=True)

    assert ss._scan_strategies_folder() == []


def test_get_strategy_readme_reads_file(monkeypatch, tmp_path):
    from app.services import strategy_service as ss

    strategies_dir = tmp_path / "strategies"
    s1 = strategies_dir / "s1"
    s1.mkdir(parents=True)
    (s1 / "README.md").write_text("# hi\n", encoding="utf-8")
    monkeypatch.setattr(ss, "STRATEGIES_DIR", strategies_dir, raising=True)

    assert ss.get_strategy_readme("s1") == "# hi\n"
    assert ss.get_strategy_readme("missing") is None


@pytest.mark.asyncio
async def test_strategy_service_update_strategy_field_branches(monkeypatch):
    from app.services.strategy_service import StrategyService
    from app.schemas.strategy import StrategyUpdate, ParamSpec

    svc = StrategyService()
    svc.strategy_repo = AsyncMock()
    svc.strategy_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id="s1", user_id="u1"))
    svc.strategy_repo.update = AsyncMock(return_value=SimpleNamespace(
        id="s1",
        user_id="u1",
        name="n",
        description="d",
        code="c",
        params={"p": {"type": "int", "default": 1}},
        category="cat",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))

    upd = StrategyUpdate(
        name="n",
        description="d",
        code="c",
        params={"p": ParamSpec(type="int", default=1)},
        category="cat",
    )
    out = await svc.update_strategy("s1", "u1", upd)
    assert out is not None


def test_strategy_service_to_response_handles_non_dict_params():
    from app.services.strategy_service import StrategyService

    svc = StrategyService()
    strategy = SimpleNamespace(
        id="s1",
        user_id="u1",
        name="n",
        description="d",
        code="c",
        params={"p": 1},  # non-dict branch
        category="cat",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    out = svc._to_response(strategy)
    assert out.params["p"].default == 1
