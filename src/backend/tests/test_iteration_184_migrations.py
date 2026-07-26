"""Isolated migration coverage for iteration 184's expand-only revisions."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

import app.config as app_config
from alembic import command
from app.db.database import Base

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_BASELINE = "20260705_b_data_backtest_trust"
_HEAD = "21d572b67d8e"
_PRE_TRUST_BASELINE = "0015_add_workspace_listing_indexes"


def _config(database_url: str) -> Config:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _set_migration_database(monkeypatch, database_url: str) -> None:
    """Make Alembic's app-config override point at this test-only database."""
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))


def _tables(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _columns(database_url: str, table_name: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return {column["name"] for column in inspect(engine).get_columns(table_name)}
    finally:
        engine.dispose()


def _column_length(database_url: str, table_name: str, column_name: str) -> int | None:
    engine = create_engine(database_url)
    try:
        columns = {column["name"]: column for column in inspect(engine).get_columns(table_name)}
        return getattr(columns[column_name]["type"], "length", None)
    finally:
        engine.dispose()


def _create_all(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()


def _upgrade(config: Config, database_url: str, target: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, target)
    finally:
        engine.dispose()


def test_iteration_184_has_one_linear_alembic_head():
    script = ScriptDirectory.from_config(_config("sqlite+aiosqlite://"))
    assert script.get_heads() == [_HEAD]


def test_iteration_184_migrations_upgrade_fresh_current_and_legacy_create_all(
    tmp_path, monkeypatch
):
    """Exercise fresh, current-head, and create_all legacy baselines in isolated files."""
    required = {
        "investment_mandates",
        "research_pipeline_events",
        "ai_strategy_research_versions",
        "ai_strategy_research_version_comparisons",
        "broker_connection_profiles",
        "paper_review_reports",
        "live_handoff_reviews",
        "risk_rules",
        "paper_equity_snapshots",
        "strategy_scores",
    }
    for name, preparation in (
        ("fresh", "head"),
        ("current", "baseline"),
        ("legacy", "create_all"),
    ):
        database_url = f"sqlite:///{tmp_path / f'{name}.db'}"
        _set_migration_database(monkeypatch, database_url)
        config = _config(database_url)
        if preparation == "head":
            _upgrade(config, database_url, "head")
        elif preparation == "baseline":
            _upgrade(config, database_url, _BASELINE)
            _upgrade(config, database_url, "head")
        else:
            _create_all(database_url)
            engine = create_engine(database_url)
            try:
                with engine.begin() as connection:
                    config.attributes["connection"] = connection
                    command.stamp(config, _BASELINE)
            finally:
                engine.dispose()
            _upgrade(config, database_url, "head")
        assert required <= _tables(database_url), name
        engine = create_engine(database_url)
        try:
            indexes = inspect(engine).get_indexes("strategy_units")
        finally:
            engine.dispose()
        identity_index = next(
            (
                index
                for index in indexes
                if index["name"] == "uq_strategy_units_trading_instance_id"
            ),
            None,
        )
        assert identity_index is not None, name
        assert bool(identity_index["unique"]), name


def test_pre_trust_create_all_database_upgrades_to_head(tmp_path, monkeypatch):
    """A create_all database at revision 0015 can safely apply later migrations."""
    database_url = f"sqlite:///{tmp_path / 'pre_trust.db'}"
    _set_migration_database(monkeypatch, database_url)
    config = _config(database_url)

    _upgrade(config, database_url, _PRE_TRUST_BASELINE)
    _create_all(database_url)
    _upgrade(config, database_url, "head")

    assert {
        "average_holding_bars",
        "max_consecutive_wins",
        "max_consecutive_losses",
        "profit_loss_ratio",
        "standard_metrics",
        "result_summary",
    } <= _columns(database_url, "backtest_results")
    assert _column_length(database_url, "alembic_version", "version_num") == 255
