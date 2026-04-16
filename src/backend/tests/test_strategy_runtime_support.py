"""Tests for strategy_runtime_support module."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.services import workspace_unit_runtime
from app.services.strategy_runtime_support import (
    _FLAT_LOG_FILENAMES,
    find_latest_log_dir,
    infer_gateway_params,
    load_strategy_config,
    load_strategy_env,
    resolve_strategy_dir,
)


class TestFindLatestLogDir:
    """Tests for find_latest_log_dir function."""

    def test_returns_none_when_no_logs_dir(self, tmp_path: Path):
        """Test returns None when logs directory doesn't exist."""
        result = find_latest_log_dir(tmp_path)
        assert result is None

    def test_returns_latest_subdir(self, tmp_path: Path):
        """Test returns the latest subdirectory in logs."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "2024-01-01").mkdir()
        (logs_dir / "2024-01-02").mkdir()
        (logs_dir / "2024-01-03").mkdir()
        (logs_dir / "2024-01-01" / "value.log").write_text("ok")
        (logs_dir / "2024-01-02" / "value.log").write_text("ok")
        (logs_dir / "2024-01-03" / "value.log").write_text("ok")

        result = find_latest_log_dir(tmp_path)
        assert result.endswith("2024-01-03")

    def test_returns_latest_subdir_by_mtime_for_task_dirs(self, tmp_path: Path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        older_dir = logs_dir / "task_zzzz-old"
        newer_dir = logs_dir / "task_aaaa-new"
        older_dir.mkdir()
        newer_dir.mkdir()
        (older_dir / "value.log").write_text("datetime\tvalue\tcash\n2024-01-01\t1\t1\n")
        (newer_dir / "value.log").write_text("datetime\tvalue\tcash\n2024-01-02\t1\t1\n")
        os.utime(older_dir, (1_700_000_000, 1_700_000_000))
        os.utime(newer_dir, (1_800_000_000, 1_800_000_000))

        result = find_latest_log_dir(tmp_path)
        assert result == str(newer_dir)

    def test_ignores_empty_subdir_and_falls_back_to_flat_logs(self, tmp_path: Path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "task-empty").mkdir()
        (logs_dir / "value.log").write_text("datetime\tvalue\tcash\n2024-01-01\t1\t1\n")

        result = find_latest_log_dir(tmp_path)
        assert result == str(logs_dir)

    def test_returns_logs_dir_when_flat_files_exist(self, tmp_path: Path):
        """Test returns logs directory when flat log files exist."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "value.log").touch()

        result = find_latest_log_dir(tmp_path)
        assert result == str(logs_dir)

    def test_returns_none_when_no_subdirs_or_flat_files(self, tmp_path: Path):
        """Test returns None when no subdirs or flat files."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "other.txt").touch()

        result = find_latest_log_dir(tmp_path)
        assert result is None


class TestLoadStrategyConfig:
    """Tests for load_strategy_config function."""

    def test_returns_empty_dict_when_no_config(self, tmp_path: Path):
        """Test returns empty dict when config.yaml doesn't exist."""
        result = load_strategy_config(tmp_path)
        assert result == {}

    def test_loads_yaml_config(self, tmp_path: Path):
        """Test loads config from YAML file."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("name: test_strategy\nversion: 1.0\n")

        result = load_strategy_config(tmp_path)
        assert result == {"name": "test_strategy", "version": 1.0}

    def test_returns_empty_dict_on_empty_file(self, tmp_path: Path):
        """Test returns empty dict for empty YAML file."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("")

        result = load_strategy_config(tmp_path)
        assert result == {}


class TestLoadStrategyEnv:
    """Tests for load_strategy_env function."""

    def test_returns_empty_dict_when_no_env_file(self, tmp_path: Path):
        """Test returns empty dict when no .env file exists."""
        result = load_strategy_env(tmp_path)
        assert result == {}

    def test_loads_env_from_strategy_dir(self, tmp_path: Path):
        """Test loads env from strategy directory."""
        env_path = tmp_path / ".env"
        env_path.write_text("API_KEY=secret123\nDEBUG=true\n")

        result = load_strategy_env(tmp_path)
        assert result == {"API_KEY": "secret123", "DEBUG": "true"}

    def test_skips_comments_and_empty_lines(self, tmp_path: Path):
        """Test skips comments and empty lines."""
        env_path = tmp_path / ".env"
        env_path.write_text("# Comment\n\nAPI_KEY=secret\n# Another comment\n")

        result = load_strategy_env(tmp_path)
        assert result == {"API_KEY": "secret"}

    def test_strips_quotes_from_values(self, tmp_path: Path):
        """Test strips quotes from values."""
        env_path = tmp_path / ".env"
        env_path.write_text("KEY1=\"value1\"\nKEY2='value2'\n")

        result = load_strategy_env(tmp_path)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_merges_multiple_env_files(self, tmp_path: Path):
        """Test merges env from strategy and project dirs."""
        strategy_env = tmp_path / ".env"
        strategy_env.write_text("KEY1=value1\nKEY2=value2\n")

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project_env = project_dir / ".env"
        project_env.write_text("KEY2=overridden\nKEY3=value3\n")

        result = load_strategy_env(tmp_path, backtrader_web_dir=project_dir)
        # Strategy dir env takes precedence
        assert result == {"KEY1": "value1", "KEY2": "value2", "KEY3": "value3"}


class TestResolveStrategyDir:
    """Tests for resolve_strategy_dir function."""

    def test_resolves_valid_strategy_id(self, tmp_path: Path):
        """Test resolves valid strategy ID."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()
        (strategies_dir / "my_strategy").mkdir()

        result = resolve_strategy_dir("my_strategy", strategies_dir)
        assert result == strategies_dir / "my_strategy"

    def test_raises_on_path_traversal(self, tmp_path: Path):
        """Test raises ValueError on path traversal attempt."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()

        with pytest.raises(ValueError, match="Invalid strategy_id"):
            resolve_strategy_dir("../escape", strategies_dir)

    def test_raises_on_absolute_path(self, tmp_path: Path):
        """Test raises ValueError on absolute path."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()

        with pytest.raises(ValueError, match="Invalid strategy_id"):
            resolve_strategy_dir("/etc/passwd", strategies_dir)

    def test_raises_on_backslash(self, tmp_path: Path):
        """Test raises ValueError on backslash in path."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()

        with pytest.raises(ValueError, match="Invalid strategy_id"):
            resolve_strategy_dir("path\\escape", strategies_dir)

    def test_raises_on_escape_from_base(self, tmp_path: Path):
        """Test raises ValueError when path escapes base directory."""
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()
        # Create a subdirectory to test escape
        (strategies_dir / "subdir").mkdir()

        # This path resolves outside but doesn't contain ".." directly in the input
        # However, the function checks for ".." first, so this tests the secondary check
        # For paths that would resolve outside after normalization
        # Since the function checks for ".." in input first, this tests that path
        with pytest.raises(ValueError):  # Either Invalid strategy_id or Strategy path escapes
            resolve_strategy_dir("subdir/../../..", strategies_dir)


class TestInferGatewayParams:
    """Tests for infer_gateway_params function."""

    def test_returns_none_when_no_config(self, tmp_path: Path):
        """Test returns None when no config.yaml exists."""
        result = infer_gateway_params(tmp_path)
        assert result is None

    def test_returns_none_when_gateway_disabled(self, tmp_path: Path):
        """Test returns None when gateway is disabled."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"gateway": {"enabled": False}}))

        result = infer_gateway_params(tmp_path)
        assert result is None

    def test_infer_from_enabled_gateway(self, tmp_path: Path):
        """Test infers params from enabled gateway config."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "gateway": {
                        "enabled": True,
                        "provider": "ctp_gateway",
                        "exchange_type": "CTP",
                        "asset_type": "FUTURE",
                    }
                }
            )
        )

        result = infer_gateway_params(tmp_path)
        assert result == {
            "enabled": True,
            "provider": "ctp_gateway",
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
        }

    def test_infer_from_ctp_config(self, tmp_path: Path):
        """Test infers params from legacy ctp config."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"ctp": {"userid": "test"}}))

        result = infer_gateway_params(tmp_path)
        assert result == {
            "enabled": True,
            "provider": "ctp_gateway",
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
        }

    def test_returns_none_on_invalid_yaml(self, tmp_path: Path):
        """Test returns None on invalid YAML."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("invalid: yaml: content:")

        result = infer_gateway_params(tmp_path)
        assert result is None

    def test_uses_defaults_for_missing_fields(self, tmp_path: Path):
        """Test uses defaults for missing gateway fields."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"gateway": {"enabled": True}}))

        result = infer_gateway_params(tmp_path)
        assert result == {
            "enabled": True,
            "provider": "ctp_gateway",
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
        }


class TestFlatLogFilenames:
    """Tests for _FLAT_LOG_FILENAMES constant."""

    def test_contains_expected_filenames(self):
        """Test contains expected log filenames."""
        expected = {
            "value.log",
            "data.log",
            "trade.log",
            "bar.log",
            "indicator.log",
            "position.log",
            "order.log",
            "system.log",
            "tick.log",
        }
        assert _FLAT_LOG_FILENAMES == expected

    def test_is_frozenset(self):
        """Test is a frozenset for immutability."""
        assert isinstance(_FLAT_LOG_FILENAMES, frozenset)


class TestWorkspaceUnitRuntime:
    def test_sync_unit_runtime_writes_config_and_run_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path / "workspace_units"
        )

        template_dir = tmp_path / "strategies" / "backtest" / "011_abberation"
        template_dir.mkdir(parents=True)
        (template_dir / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "strategy": {"name": "Abberation布林带突破策略"},
                    "params": {"boll_period": 200, "boll_mult": 2},
                    "data": {"symbol": "RB889", "data_type": "future"},
                    "backtest": {"initial_cash": 1000000, "commission": 0.0001},
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (template_dir / "strategy_abberation.py").write_text(
            "class Dummy: pass\n", encoding="utf-8"
        )

        monkeypatch.setattr(
            workspace_unit_runtime, "get_strategy_dir", lambda strategy_id: template_dir
        )

        unit = SimpleNamespace(
            id="unit-1",
            workspace_id="ws-1",
            group_name="布林带策略",
            strategy_id="backtest/011_abberation",
            strategy_name="Abberation布林带突破策略",
            symbol="AAPL",
            symbol_name="Apple",
            timeframe="1d",
            timeframe_n=1,
            category="外汇",
            data_config={
                "start_date": "2020-01-01T00:00:00Z",
                "end_date": "2021-01-01T00:00:00Z",
                "sample_count": 500,
            },
            unit_settings={"initial_cash": 250000, "commission": 0.0003},
            params={"boll_period": 20},
            optimization_config={},
        )
        workspace_settings = {
            "data_source": {
                "type": "csv",
                "csv": {"directory_path": str(tmp_path / "market_data")},
            }
        }

        runtime_dir = workspace_unit_runtime.sync_unit_runtime(unit, workspace_settings)

        assert runtime_dir == tmp_path / "workspace_units" / "ws-1" / "unit-1"
        assert (runtime_dir / "run.py").is_file()
        assert (runtime_dir / "config.yaml").is_file()

        config = yaml.safe_load((runtime_dir / "config.yaml").read_text(encoding="utf-8"))
        assert config["data"]["symbol"] == "AAPL"
        assert config["data"]["asset_type"] == "forex"
        assert Path(config["data"]["directory_path"]).name == "forex"
        assert config["params"]["boll_period"] == 20
        assert config["backtest"]["initial_cash"] == 250000
        assert config["workspace_unit"]["template_dir"] == str(template_dir)
        assert config["workspace_unit"]["strategy_module"] == "strategy_abberation.py"
