"""Safety contracts for the six-asset disposable acceptance runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "ci"
    / "run_asset_research_six_asset_fixture.py"
)


def _load_script() -> object:
    spec = importlib.util.spec_from_file_location("six_asset_fixture_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql+aiomysql://fixture:fixture@127.0.0.1/codex_iter191_six_asset_acceptance",
        "mysql+aiomysql://fixture:fixture@127.0.0.1/codex_iter191_six_asset_20260803",
    ],
)
def test_six_asset_fixture_runner_accepts_only_its_disposable_mysql_namespace(
    database_url: str,
) -> None:
    script = _load_script()

    assert script.validate_disposable_mysql_url(database_url).startswith("codex_iter191_six_asset_")


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql+aiomysql://fixture:fixture@127.0.0.1/backtrader_web",
        "mysql+aiomysql://fixture:fixture@127.0.0.1/codex_iter191_capacity_acceptance",
        "postgresql+asyncpg://fixture:fixture@127.0.0.1/codex_iter191_six_asset_acceptance",
    ],
)
def test_six_asset_fixture_runner_rejects_shared_or_non_mysql_targets(database_url: str) -> None:
    script = _load_script()

    with pytest.raises(ValueError):
        script.validate_disposable_mysql_url(database_url)
