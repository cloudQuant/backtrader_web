"""Tests for strategy_runtime_support module."""

from pathlib import Path

import pytest
import yaml

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

        result = find_latest_log_dir(tmp_path)
        assert result.endswith("2024-01-03")

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
        env_path.write_text('KEY1="value1"\nKEY2=\'value2\'\n')

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
        config_path.write_text(yaml.dump({
            "gateway": {
                "enabled": True,
                "provider": "ctp_gateway",
                "exchange_type": "CTP",
                "asset_type": "FUTURE",
            }
        }))

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
