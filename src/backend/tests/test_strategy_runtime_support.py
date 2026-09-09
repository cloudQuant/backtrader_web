"""Tests for strategy_runtime_support module."""

import hashlib
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml

from app.services import workspace_unit_runtime
from app.services.strategy import runtime_support as runtime_support_module
from app.services.strategy.runtime_support import (
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

    def test_default_project_root_points_to_repository_root(self):
        assert (
            runtime_support_module._PROJECT_ROOT / "src" / "backend" / "pyproject.toml"
        ).is_file()
        assert (runtime_support_module._PROJECT_ROOT / "scripts" / "diagnostics").is_dir()

    def test_returns_empty_dict_when_no_env_file(self, tmp_path: Path):
        """Test returns empty dict when no .env file exists."""
        result = load_strategy_env(tmp_path, project_dir=tmp_path / "project")
        assert result == {}

    def test_loads_env_from_strategy_dir(self, tmp_path: Path):
        """Test loads env from strategy directory."""
        env_path = tmp_path / ".env"
        env_path.write_text("API_KEY=secret123\nDEBUG=true\n")

        result = load_strategy_env(tmp_path, project_dir=tmp_path / "project")
        assert result == {"API_KEY": "secret123", "DEBUG": "true"}

    def test_skips_comments_and_empty_lines(self, tmp_path: Path):
        """Test skips comments and empty lines."""
        env_path = tmp_path / ".env"
        env_path.write_text("# Comment\n\nAPI_KEY=secret\n# Another comment\n")

        result = load_strategy_env(tmp_path, project_dir=tmp_path / "project")
        assert result == {"API_KEY": "secret"}

    def test_strips_quotes_from_values(self, tmp_path: Path):
        """Test strips quotes from values."""
        env_path = tmp_path / ".env"
        env_path.write_text("KEY1=\"value1\"\nKEY2='value2'\n")

        result = load_strategy_env(tmp_path, project_dir=tmp_path / "project")
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_merges_multiple_env_files(self, tmp_path: Path):
        """Test merges env from strategy and project dirs."""
        strategy_env = tmp_path / ".env"
        strategy_env.write_text("KEY1=value1\nKEY2=value2\n")

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project_env = project_dir / ".env"
        project_env.write_text("KEY2=overridden\nKEY3=value3\n")

        result = load_strategy_env(tmp_path, project_dir=project_dir)
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
    @staticmethod
    def _signed_binding_data(tmp_path: Path) -> tuple[Path, bytes, str, dict[str, object]]:
        """Create a sealed binding envelope without a database or provider."""
        from app.services.market_data.research_binding import (
            build_market_data_binding_signature_payload,
            sign_market_data_binding_payload,
        )

        signing_key = "test-market-data-binding-signing-key-32-bytes"
        binding_hash = "a" * 64
        root = tmp_path / "server-owned-artifacts"
        artifact_path = root / "bindings" / binding_hash / "data.csv"
        artifact_path.parent.mkdir(parents=True)
        content = (
            b"datetime,open,high,low,close,volume,openinterest\n"
            b"2024-01-01T00:00:00Z,1,1,1,1,1,0\n"
            b"2024-01-02T00:00:00Z,1,1,1,1,1,0\n"
            b"2024-01-03T00:00:00Z,1,1,1,1,1,0\n"
        )
        artifact_path.write_bytes(content)
        query_semantics: dict[str, object] = {
            "asset_type": "stock",
            "symbol": "000001.SZ",
            "timeframe": "1d",
            "timeframe_n": 1,
            "full_window_start": "2024-01-01T00:00:00.000000Z",
            "full_window_end": "2024-01-03T00:00:00.000000Z",
            "canonical_id": "equity.cn.000001.SZ",
            "dataset_code": "equity.cn.bars",
            "family_id": "stock.realtime",
            "family_contract_version": "v1",
            "data_kind": "bars",
            "frequency": "1d",
            "source_policy_id": "market-default-v1",
            "instrument_metadata_version": "v1",
            "query_fingerprint": "d" * 64,
        }
        payload = build_market_data_binding_signature_payload(
            binding_id="binding-1",
            binding_hash=binding_hash,
            owner_user_id="user-1",
            artifact_relative_path=f"bindings/{binding_hash}/data.csv",
            artifact_sha256=hashlib.sha256(content).hexdigest(),
            artifact_size_bytes=len(content),
            query_semantics=query_semantics,
        )
        metadata: dict[str, object] = {
            "binding_id": "binding-1",
            "binding_hash": binding_hash,
            "owner_user_id": "user-1",
            "signature": sign_market_data_binding_payload(payload, signing_key),
            "artifact_relative_path": f"bindings/{binding_hash}/data.csv",
            "artifact_sha256": hashlib.sha256(content).hexdigest(),
            "artifact_size_bytes": len(content),
            "manifest_hash": "b" * 64,
            "query_semantics": query_semantics,
        }
        return root, content, signing_key, metadata

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
        run_text = (runtime_dir / "run.py").read_text(encoding="utf-8")
        assert "ComminfoFuturesFixed" in run_text
        assert "ComminfoFuturesInverse" in run_text
        assert "ComminfoFuturesMixed" in run_text
        assert "_apply_commission_info(cerebro, config, name)" in run_text
        assert "contract_metadata" in run_text
        assert "margin_amount=margin_amount_param" in run_text
        assert "meta.get('max_leverage')" in run_text
        assert "meta.get('trade_contract_size')" in run_text
        assert "meta.get('ctVal')" in run_text
        assert "_is_inverse_contract(meta)" in run_text
        assert "close_yesterday_commission=close_yesterday_rate" in run_text
        assert "close_yesterday_commission_amount=close_yesterday_amount" in run_text

    def test_sync_unit_runtime_uses_default_csv_root_for_empty_workspace_setting(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path / "workspace_units"
        )

        template_dir = tmp_path / "strategies" / "backtest" / "sa_trend"
        template_dir.mkdir(parents=True)
        (template_dir / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "strategy": {"name": "SA trend"},
                    "params": {},
                    "data": {"symbol": "sa", "data_type": "future"},
                    "backtest": {"initial_cash": 100000},
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (template_dir / "strategy_sa.py").write_text("class Dummy: pass\n", encoding="utf-8")
        monkeypatch.setattr(
            workspace_unit_runtime, "get_strategy_dir", lambda strategy_id: template_dir
        )

        unit = SimpleNamespace(
            id="unit-sa",
            workspace_id="ws-sa",
            group_name="SA",
            strategy_id="backtest/sa_trend",
            strategy_name="SA trend",
            symbol="sa",
            symbol_name="纯碱",
            timeframe="1h",
            timeframe_n=1,
            category="trend",
            data_config={"start_date": "2024-01-01", "end_date": "2024-12-31"},
            unit_settings={},
            params={},
            optimization_config={},
        )
        workspace_settings = {"data_source": {"type": "csv", "csv": {"directory_path": ""}}}

        runtime_dir = workspace_unit_runtime.sync_unit_runtime(unit, workspace_settings)
        config = yaml.safe_load((runtime_dir / "config.yaml").read_text(encoding="utf-8"))

        assert Path(config["data"]["directory_path"]).as_posix().endswith("data/datas/future")
        assert config["data"]["symbol"] == "sa"
        run_text = (runtime_dir / "run.py").read_text(encoding="utf-8")
        assert "_candidate_patterns(symbol, suffix)" in run_text
        assert "BACKTRADER_DATA_DIR" in run_text

    def test_bound_unit_uses_only_server_resolved_artifact_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A research binding cannot be redirected by workspace or unit CSV settings."""
        monkeypatch.setattr(
            workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path / "workspace_units"
        )
        template_dir = tmp_path / "strategies" / "bound" / "demo"
        template_dir.mkdir(parents=True)
        (template_dir / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "strategy": {"name": "bound"},
                    "data": {
                        "directory_path": "/template-controlled-by-client",
                        "provider": "untrusted-template-provider",
                        "canonical_id": "untrusted-template-canonical-id",
                    },
                }
            ),
            encoding="utf-8",
        )
        (template_dir / "strategy_bound.py").write_text("class Dummy: pass\n", encoding="utf-8")
        monkeypatch.setattr(
            workspace_unit_runtime, "get_strategy_dir", lambda _strategy_id: template_dir
        )

        binding_hash = "a" * 64
        artifact_directory = tmp_path / "server-owned" / "bindings" / binding_hash
        artifact_directory.mkdir(parents=True)
        artifact_path = artifact_directory / "data.csv"
        artifact_path.write_text(
            "datetime,open,high,low,close,volume\n2024-01-01,1,1,1,1,1\n",
            encoding="utf-8",
        )
        binding = SimpleNamespace(
            binding_id="binding-1",
            binding_hash=binding_hash,
            user_id="user-1",
            signature="server-issued-signature",
            artifact_directory=artifact_directory,
            artifact_path=artifact_path,
            artifact_relative_path=f"bindings/{binding_hash}/data.csv",
            artifact_sha256="b" * 64,
            artifact_size_bytes=artifact_path.stat().st_size,
            manifest_hash="c" * 64,
            query_semantics={
                "asset_type": "stock",
                "symbol": "000001.SZ",
                "timeframe": "1d",
                "timeframe_n": 1,
            },
        )
        unit = SimpleNamespace(
            id="bound-unit",
            workspace_id="bound-workspace",
            group_name="",
            strategy_id="bound/demo",
            strategy_name="bound",
            symbol="000001.SZ",
            symbol_name="Ping An",
            timeframe="1d",
            timeframe_n=1,
            # A mutable category must not alter the server-verified binding
            # contract or select a different workspace data root.
            category="future",
            data_config={
                "range_type": "date",
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-01-02T00:00:00Z",
                "directory_path": str(tmp_path / "client-controlled"),
                "provider": "client-provider",
                "canonical_id": "client-canonical-id",
                "market_data_binding_required": True,
                "market_data_binding_id": "binding-1",
                "market_data_binding_hash": binding_hash,
                "market_data_binding_signature": "client-copy-is-not-used",
            },
            unit_settings={},
            params={},
            optimization_config={},
        )
        workspace_csv_root = tmp_path / "workspace-csv"

        runtime_dir = workspace_unit_runtime.sync_unit_runtime(
            unit,
            {"data_source": {"type": "csv", "csv": {"directory_path": str(workspace_csv_root)}}},
            market_data_binding=binding,
        )

        config = yaml.safe_load((runtime_dir / "config.yaml").read_text(encoding="utf-8"))
        data = config["data"]
        assert data["directory_path"] == str(artifact_directory.resolve())
        assert data["directory_path"] != str((workspace_csv_root / "stock").resolve())
        assert data["asset_type"] == "stock"
        assert data["market_data_binding_required"] is True
        assert data["market_data_binding"]["binding_id"] == "binding-1"
        assert data["market_data_binding"]["artifact_relative_path"] == (
            f"bindings/{binding_hash}/data.csv"
        )
        assert "provider" not in data
        assert "canonical_id" not in data
        assert "market_data_binding_id" not in data
        assert config["workspace_unit"]["data_source_type"] == "market_data_binding"
        assert config["workspace_unit"]["data_root"] == str(artifact_directory.resolve())

    def test_bound_unit_runtime_defers_materialization_until_revalidation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Create/update cannot emit a generic runtime before async revalidation."""
        monkeypatch.setattr(
            workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path / "workspace_units"
        )
        template_dir = tmp_path / "strategies" / "bound" / "missing"
        template_dir.mkdir(parents=True)
        (template_dir / "config.yaml").write_text("strategy: {}\n", encoding="utf-8")
        monkeypatch.setattr(
            workspace_unit_runtime, "get_strategy_dir", lambda _strategy_id: template_dir
        )
        unit = SimpleNamespace(
            id="bound-unit",
            workspace_id="bound-workspace",
            group_name="",
            strategy_id="bound/missing",
            strategy_name="bound",
            symbol="000001.SZ",
            symbol_name="",
            timeframe="1d",
            timeframe_n=1,
            category="stock",
            data_config={"market_data_binding_required": True},
            unit_settings={},
            params={},
            optimization_config={},
        )
        stale_runtime_dir = workspace_unit_runtime.unit_dir(unit.workspace_id, unit.id)
        stale_runtime_dir.mkdir(parents=True)
        (stale_runtime_dir / "config.yaml").write_text(
            "data:\n  directory_path: /stale-client-data\n",
            encoding="utf-8",
        )
        (stale_runtime_dir / "run.py").write_text("raise AssertionError\n", encoding="utf-8")

        runtime_dir = workspace_unit_runtime.sync_workspace_unit_runtime(unit, {}, "trading")

        assert runtime_dir.is_dir()
        assert not (runtime_dir / "config.yaml").exists()
        assert not (runtime_dir / "run.py").exists()

    def test_generated_runner_reads_only_the_verified_binding_csv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """The generated loader bypasses all legacy directory/fuzzy-file paths when bound."""
        import app.config as config_module

        root, _content, signing_key, metadata = self._signed_binding_data(tmp_path)
        monkeypatch.setattr(
            config_module,
            "get_settings",
            lambda: SimpleNamespace(MARKET_DATA_RESEARCH_ARTIFACT_SIGNING_KEY=signing_key),
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "_market_data_binding_artifact_root",
            lambda: root.resolve(),
        )
        poison_dir = tmp_path / "client-controlled-csv"
        poison_dir.mkdir()
        monkeypatch.setenv("BACKTRADER_DATA_DIR", str(poison_dir))
        module_name = "bound_runner_test"
        runner_module = ModuleType(module_name)
        runner_module.__file__ = str(tmp_path / "workspace_units" / "ws" / "unit" / "run.py")
        sys.modules[module_name] = runner_module
        try:
            exec(workspace_unit_runtime._UNIT_RUN_PY, runner_module.__dict__)
            resolve_data_file = runner_module.__dict__["resolve_data_file"]
            assert callable(resolve_data_file)
            resolved = resolve_data_file(
                {
                    "data": {
                        "market_data_binding_required": True,
                        "market_data_binding": metadata,
                        "directory_path": str(poison_dir),
                        "symbol": "attacker-symbol",
                    }
                }
            )
        finally:
            sys.modules.pop(module_name, None)
        assert resolved == root / "bindings" / ("a" * 64) / "data.csv"
        loader_start = workspace_unit_runtime._UNIT_RUN_PY.index("def load_dataframe")
        loader_end = workspace_unit_runtime._UNIT_RUN_PY.index("def _import_strategy_module")
        bound_loader = workspace_unit_runtime._UNIT_RUN_PY[loader_start:loader_end]
        assert "open_verified_market_data_binding_file(data)" in bound_loader
        assert "pd.read_csv(csv_handle)" in bound_loader

    def test_generated_runner_keeps_date_only_bound_end_inclusive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A date-only OOS end keeps its user-facing inclusive calendar-day meaning."""
        import app.config as config_module

        root, _content, signing_key, metadata = self._signed_binding_data(tmp_path)
        monkeypatch.setattr(
            config_module,
            "get_settings",
            lambda: SimpleNamespace(MARKET_DATA_RESEARCH_ARTIFACT_SIGNING_KEY=signing_key),
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "_market_data_binding_artifact_root",
            lambda: root.resolve(),
        )
        module_name = "bound_runner_date_filter_test"
        runner_module = ModuleType(module_name)
        runner_module.__file__ = str(tmp_path / "workspace_units" / "ws" / "unit" / "run.py")
        sys.modules[module_name] = runner_module
        try:
            exec(workspace_unit_runtime._UNIT_RUN_PY, runner_module.__dict__)
            original_read_csv = runner_module.__dict__["pd"].read_csv
            csv_sources: list[object] = []

            def guarded_read_csv(source: object, *args: object, **kwargs: object) -> object:
                csv_sources.append(source)
                assert hasattr(source, "read")
                assert not isinstance(source, (str, Path))
                return original_read_csv(source, *args, **kwargs)

            monkeypatch.setattr(runner_module.__dict__["pd"], "read_csv", guarded_read_csv)
            dataframe, _csv_path = runner_module.__dict__["load_dataframe"](
                {
                    "data": {
                        "market_data_binding_required": True,
                        "market_data_binding": metadata,
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-02",
                        "use_end_date": True,
                    }
                }
            )
        finally:
            sys.modules.pop(module_name, None)

        assert list(dataframe.index.strftime("%Y-%m-%d")) == ["2024-01-01", "2024-01-02"]
        assert len(csv_sources) == 1

    def test_verified_binding_descriptor_survives_path_replacement(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A post-verification rename cannot make the caller read a new pathname target."""
        import app.config as config_module

        root, content, signing_key, metadata = self._signed_binding_data(tmp_path)
        monkeypatch.setattr(
            config_module,
            "get_settings",
            lambda: SimpleNamespace(MARKET_DATA_RESEARCH_ARTIFACT_SIGNING_KEY=signing_key),
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "_market_data_binding_artifact_root",
            lambda: root.resolve(),
        )
        binding_hash = "a" * 64
        artifact_path = root / "bindings" / binding_hash / "data.csv"
        replacement = tmp_path / "replacement.csv"
        replacement.write_bytes(content.replace(b",1,0\n", b",9,0\n"))

        with workspace_unit_runtime.open_verified_market_data_binding_file(
            {"market_data_binding_required": True, "market_data_binding": metadata}
        ) as (handle, resolved_path):
            replacement.replace(artifact_path)

            assert resolved_path == artifact_path
            assert handle.read() == content

        assert artifact_path.read_bytes() != content

    @pytest.mark.parametrize(
        ("tamper", "expected_code"),
        [
            ("path", "MARKET_DATA_BINDING_SIGNATURE_INVALID"),
            ("bytes", "MARKET_DATA_BINDING_ARTIFACT_DIGEST_MISMATCH"),
            ("symlink", "MARKET_DATA_BINDING_ARTIFACT_PATH_INVALID"),
            ("symlink-directory", "MARKET_DATA_BINDING_ARTIFACT_PATH_INVALID"),
        ],
    )
    def test_bound_runtime_rejects_tampered_binding_before_csv_selection(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        tamper: str,
        expected_code: str,
    ):
        """Path, artifact hash, and symlink tampering fail before pandas reads the CSV."""
        import app.config as config_module

        root, content, signing_key, metadata = self._signed_binding_data(tmp_path)
        monkeypatch.setattr(
            config_module,
            "get_settings",
            lambda: SimpleNamespace(MARKET_DATA_RESEARCH_ARTIFACT_SIGNING_KEY=signing_key),
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "_market_data_binding_artifact_root",
            lambda: root.resolve(),
        )
        binding_hash = "a" * 64
        artifact_path = root / "bindings" / binding_hash / "data.csv"
        if tamper == "path":
            metadata["artifact_relative_path"] = f"bindings/{binding_hash}/not-data.csv"
        elif tamper == "bytes":
            artifact_path.write_bytes(content.replace(b",1,0\n", b",2,0\n"))
        elif tamper == "symlink":
            outside = tmp_path / "outside.csv"
            outside.write_bytes(content)
            artifact_path.unlink()
            artifact_path.symlink_to(outside)
        else:
            bindings_dir = root / "bindings"
            outside_dir = tmp_path / "outside-bindings"
            bindings_dir.replace(outside_dir)
            bindings_dir.symlink_to(outside_dir, target_is_directory=True)

        with pytest.raises(
            workspace_unit_runtime.MarketDataBindingRuntimeError,
            match=expected_code,
        ):
            workspace_unit_runtime.resolve_verified_market_data_binding_file(
                {
                    "market_data_binding_required": True,
                    "market_data_binding": metadata,
                    "directory_path": str(tmp_path / "client-controlled-csv"),
                }
            )

    @pytest.mark.asyncio
    async def test_required_binding_revalidation_reloads_bound_unit_and_normalizes_oos_subset(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """The core receives current persisted scope/intent, never stale ORM binding data."""
        import app.services.market_data.research_binding as research_binding

        calls: list[dict[str, object]] = []
        expected_binding = object()

        class FakeBindingService:
            async def resolve_runtime_binding(self, **kwargs: object) -> object:
                calls.append(kwargs)
                return expected_binding

        current_unit = SimpleNamespace(
            id="unit-1",
            workspace_id="workspace-1",
            symbol="000001.SZ",
            timeframe="1d",
            timeframe_n=1,
            data_config={
                "market_data_binding_required": True,
                "market_data_binding_id": "binding-1",
                "market_data_binding_hash": "a" * 64,
                "market_data_binding_signature": "server-token",
                "market_data_binding_intent_id": "research-task-1",
                "range_type": "date",
                "start_date": "2024-01-02",
                "end_date": "2024-01-03",
            },
        )

        class FakeDb:
            def __init__(self) -> None:
                self.get_calls: list[tuple[object, str]] = []

            async def get(self, model: object, unit_id: str) -> object | None:
                self.get_calls.append((model, unit_id))
                return current_unit if unit_id == "unit-1" else None

        db = FakeDb()
        fake_service = FakeBindingService()
        monkeypatch.setattr(
            research_binding,
            "build_market_data_research_binding_service",
            lambda passed_db: fake_service if passed_db is db else None,
        )
        unit = SimpleNamespace(
            id="unit-1",
            workspace_id="workspace-1",
            symbol="STALE-SYMBOL",
            timeframe="1h",
            timeframe_n=99,
            data_config={
                "market_data_binding_required": True,
                "market_data_binding_id": "stale-binding",
                "market_data_binding_hash": "b" * 64,
                "market_data_binding_signature": "stale-token",
                "market_data_binding_intent_id": "stale-intent",
                "range_type": "date",
                "start_date": "2020-01-01",
                "end_date": "2020-01-02",
            },
        )

        resolved = await workspace_unit_runtime.resolve_required_market_data_binding(
            unit,
            "user-1",
            db=db,
        )

        assert resolved is expected_binding
        assert db.get_calls == [(workspace_unit_runtime.StrategyUnit, "unit-1")]
        assert calls == [
            {
                "user_id": "user-1",
                "binding_id": "binding-1",
                "binding_hash": "a" * 64,
                "signature": "server-token",
                "workspace_id": "workspace-1",
                "unit_id": "unit-1",
                "intent_id": "research-task-1",
                "symbol": "000001.SZ",
                "timeframe": "1d",
                "timeframe_n": 1,
                "start": "2024-01-02T00:00:00.000000Z",
                "end": "2024-01-04T00:00:00.000000Z",
            }
        ]
        assert unit.data_config["market_data_binding_id"] == "stale-binding"
        assert unit.data_config["market_data_binding_intent_id"] == "stale-intent"

    @pytest.mark.asyncio
    async def test_required_binding_revalidation_rejects_missing_current_unit(self) -> None:
        """A stale unit object cannot authorize a deleted or replaced DB row."""

        class FakeDb:
            async def get(self, _model: object, _unit_id: str) -> None:
                return None

        unit = SimpleNamespace(
            id="unit-1",
            workspace_id="workspace-1",
            data_config={"market_data_binding_required": True},
        )

        with pytest.raises(
            workspace_unit_runtime.MarketDataBindingRuntimeError,
            match="MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED",
        ):
            await workspace_unit_runtime.resolve_required_market_data_binding(
                unit,
                "user-1",
                db=FakeDb(),
            )

    @pytest.mark.asyncio
    async def test_unbound_unit_skips_binding_session_lookup(self) -> None:
        """Legacy units preserve their prior no-binding runtime path exactly."""
        unit = SimpleNamespace(
            id="legacy-unit",
            workspace_id="workspace-1",
            data_config={"directory_path": "/legacy/csv"},
        )

        assert await workspace_unit_runtime.resolve_required_market_data_binding(
            unit,
            "user-1",
            db=object(),
        ) is None

    @pytest.mark.asyncio
    async def test_parallel_bound_runs_use_distinct_revalidation_sessions_before_submission(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Parallel units must not share the workspace session for DB-backed binding checks."""
        from app.services.workspace import run_ops as workspace_run_ops
        from app.services.workspace_service import WorkspaceService

        units = [
            SimpleNamespace(
                id=f"unit-{index}",
                workspace_id="workspace-1",
                run_status="idle",
                run_count=0,
                data_config={"market_data_binding_required": True},
            )
            for index in range(2)
        ]

        class FakeSession:
            async def execute(self, _statement: object) -> object:
                return SimpleNamespace(
                    scalars=lambda: SimpleNamespace(all=lambda: list(units))
                )

            async def commit(self) -> None:
                return None

        class FakeSessionContext:
            def __init__(self, session: FakeSession) -> None:
                self.session = session

            async def __aenter__(self) -> FakeSession:
                return self.session

            async def __aexit__(self, *_args: object) -> None:
                return None

        class FakeSessionMaker:
            def __init__(self) -> None:
                self.sessions: list[FakeSession] = []

            def __call__(self) -> FakeSessionContext:
                session = FakeSession()
                self.sessions.append(session)
                return FakeSessionContext(session)

        session_maker = FakeSessionMaker()
        binding_sessions: list[FakeSession] = []
        sync_calls: list[object] = []
        backtest_calls: list[object] = []

        async def fake_load_workspace(*_args: object, **_kwargs: object) -> object:
            return SimpleNamespace(settings={}, workspace_type="research")

        async def fake_get_unit(
            _session: object, _workspace_id: str, unit_id: str
        ) -> object | None:
            return next((unit for unit in units if unit.id == unit_id), None)

        async def fake_resolve_binding(
            _unit: object,
            _user_id: str,
            *,
            db: FakeSession,
        ) -> object:
            binding_sessions.append(db)
            raise workspace_unit_runtime.MarketDataBindingRuntimeError(
                "MARKET_DATA_BINDING_NOT_FOUND"
            )

        class FakeBacktestService:
            async def run_workspace_unit_backtest(
                self,
                *_args: object,
                runtime_preflight: object,
                **_kwargs: object,
            ) -> object:
                assert callable(runtime_preflight)
                await runtime_preflight()
                backtest_calls.append(object())
                raise AssertionError("A failed binding must not submit a backtest")

        monkeypatch.setattr(workspace_run_ops, "async_session_maker", session_maker)
        monkeypatch.setattr(WorkspaceService, "_load_workspace", staticmethod(fake_load_workspace))
        monkeypatch.setattr(WorkspaceService, "_get_unit", staticmethod(fake_get_unit))
        monkeypatch.setattr(
            WorkspaceService,
            "_build_backtest_request",
            staticmethod(lambda _unit: SimpleNamespace()),
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "resolve_required_market_data_binding",
            fake_resolve_binding,
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "sync_unit_runtime",
            lambda *_args, **_kwargs: sync_calls.append(object()),
        )
        import app.services.backtest.service as backtest_service_module

        monkeypatch.setattr(backtest_service_module, "BacktestService", FakeBacktestService)

        results = await WorkspaceService().run_units(
            "workspace-1",
            "user-1",
            [unit.id for unit in units],
            parallel=True,
        )

        assert len(binding_sessions) == 2
        assert len({id(session) for session in binding_sessions}) == 2
        assert session_maker.sessions[0] not in binding_sessions
        assert all(item["status"] == "failed" for item in results)
        assert all(item["error"] == "MARKET_DATA_BINDING_NOT_FOUND" for item in results)
        assert sync_calls == []
        assert backtest_calls == []

    @pytest.mark.asyncio
    async def test_bound_retry_revalidates_after_queue_wait_and_removes_stale_runtime(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A revoked binding cannot reuse a runtime written before a full queue retry."""
        from app.services.workspace import run_ops as workspace_run_ops
        from app.services.workspace_service import WorkspaceService

        unit = SimpleNamespace(
            id="bound-unit",
            workspace_id="workspace-1",
            run_status="idle",
            run_count=0,
            data_config={"market_data_binding_required": True},
        )

        class FakeSession:
            async def execute(self, _statement: object) -> object:
                return SimpleNamespace(
                    scalars=lambda: SimpleNamespace(all=lambda: [unit])
                )

            async def commit(self) -> None:
                return None

        class FakeSessionContext:
            def __init__(self, session: FakeSession) -> None:
                self.session = session

            async def __aenter__(self) -> FakeSession:
                return self.session

            async def __aexit__(self, *_args: object) -> None:
                return None

        class FakeSessionMaker:
            def __init__(self) -> None:
                self.sessions: list[FakeSession] = []

            def __call__(self) -> FakeSessionContext:
                session = FakeSession()
                self.sessions.append(session)
                return FakeSessionContext(session)

        resolve_calls: list[FakeSession] = []
        sync_calls: list[object] = []
        cleanup_calls: list[tuple[str, str]] = []
        task_creation_calls: list[object] = []

        async def fake_load_workspace(*_args: object, **_kwargs: object) -> object:
            return SimpleNamespace(settings={}, workspace_type="research")

        async def fake_get_unit(*_args: object, **_kwargs: object) -> object:
            return unit

        async def fake_resolve_binding(
            _unit: object,
            _user_id: str,
            *,
            db: FakeSession,
        ) -> object:
            resolve_calls.append(db)
            if len(resolve_calls) == 1:
                return SimpleNamespace()
            raise workspace_unit_runtime.MarketDataBindingRuntimeError(
                "MARKET_DATA_BINDING_RUNTIME_REVOKED"
            )

        class FakeBacktestService:
            async def run_workspace_unit_backtest(
                self,
                *_args: object,
                runtime_preflight: object,
                **_kwargs: object,
            ) -> object:
                assert callable(runtime_preflight)
                await runtime_preflight()
                task_creation_calls.append(object())
                raise ValueError("concurrent task limit")

        async def no_wait(_seconds: float) -> None:
            return None

        session_maker = FakeSessionMaker()
        monkeypatch.setattr(workspace_run_ops, "async_session_maker", session_maker)
        monkeypatch.setattr(WorkspaceService, "_load_workspace", staticmethod(fake_load_workspace))
        monkeypatch.setattr(WorkspaceService, "_get_unit", staticmethod(fake_get_unit))
        monkeypatch.setattr(
            WorkspaceService,
            "_build_backtest_request",
            staticmethod(lambda _unit: SimpleNamespace()),
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "resolve_required_market_data_binding",
            fake_resolve_binding,
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "sync_unit_runtime",
            lambda *_args, **_kwargs: sync_calls.append(object()),
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "remove_unit_dir",
            lambda workspace_id, unit_id: cleanup_calls.append((workspace_id, unit_id)),
        )
        monkeypatch.setattr(workspace_run_ops.asyncio, "sleep", no_wait)
        import app.services.backtest.service as backtest_service_module

        monkeypatch.setattr(backtest_service_module, "BacktestService", FakeBacktestService)

        results = await WorkspaceService().run_units(
            "workspace-1",
            "user-1",
            [unit.id],
        )

        assert len(resolve_calls) == 2
        assert len(task_creation_calls) == 1
        assert len(sync_calls) == 1
        assert cleanup_calls == [
            ("workspace-1", "bound-unit"),
            ("workspace-1", "bound-unit"),
        ]
        assert results == [
            {
                "unit_id": "bound-unit",
                "task_id": None,
                "status": "failed",
                "error": "MARKET_DATA_BINDING_RUNTIME_REVOKED",
            }
        ]
        assert unit.run_status == "failed"
        assert unit.run_count == 1

    @pytest.mark.asyncio
    async def test_bound_preflight_materializes_current_valid_oos_window(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stale outer unit cannot overwrite a newer valid OOS runtime window."""
        from app.services.workspace import run_ops as workspace_run_ops
        from app.services.workspace_service import WorkspaceService

        outer_unit = SimpleNamespace(
            id="bound-unit",
            workspace_id="workspace-1",
            run_status="idle",
            data_config={
                "market_data_binding_required": True,
                "range_type": "date",
                "start_date": "2024-01-01",
                "end_date": "2024-01-10",
            },
        )
        current_unit = SimpleNamespace(
            id="bound-unit",
            workspace_id="workspace-1",
            run_status="idle",
            run_count=0,
            last_task_id=None,
            data_config={
                "market_data_binding_required": True,
                "range_type": "date",
                "start_date": "2024-02-01",
                "end_date": "2024-02-15",
            },
        )

        class FakeSession:
            async def execute(self, _statement: object) -> object:
                return SimpleNamespace(
                    scalars=lambda: SimpleNamespace(all=lambda: [outer_unit])
                )

            async def commit(self) -> None:
                return None

        class FakeSessionContext:
            def __init__(self, session: FakeSession) -> None:
                self.session = session

            async def __aenter__(self) -> FakeSession:
                return self.session

            async def __aexit__(self, *_args: object) -> None:
                return None

        class FakeSessionMaker:
            def __init__(self) -> None:
                self.sessions: list[FakeSession] = []

            def __call__(self) -> FakeSessionContext:
                session = FakeSession()
                self.sessions.append(session)
                return FakeSessionContext(session)

        current_read_sessions: list[FakeSession] = []
        resolve_units: list[object] = []
        resolve_sessions: list[FakeSession] = []
        binding = SimpleNamespace(binding_id="binding-1")
        runtime_dir = tmp_path / "workspace-runtime"

        async def fake_load_workspace(*_args: object, **_kwargs: object) -> object:
            return SimpleNamespace(settings={}, workspace_type="research")

        async def fake_get_unit(
            session: FakeSession, _workspace_id: str, _unit_id: str
        ) -> object:
            current_read_sessions.append(session)
            return current_unit

        async def fake_resolve_binding(
            unit: object,
            _user_id: str,
            *,
            db: FakeSession,
        ) -> object:
            resolve_units.append(unit)
            resolve_sessions.append(db)
            return binding

        def fake_sync_unit_runtime(
            unit: object,
            _workspace_settings: dict[str, object],
            *,
            market_data_binding: object | None = None,
        ) -> Path:
            assert unit is current_unit
            assert market_data_binding is binding
            runtime_dir.mkdir()
            (runtime_dir / "config.yaml").write_text(
                yaml.safe_dump(
                    {
                        "data": {
                            "start_date": unit.data_config["start_date"],
                            "end_date": unit.data_config["end_date"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            return runtime_dir

        class FakeBacktestService:
            async def run_workspace_unit_backtest(
                self,
                *_args: object,
                runtime_preflight: object,
                **_kwargs: object,
            ) -> object:
                assert callable(runtime_preflight)
                await runtime_preflight()
                return SimpleNamespace(task_id="")

        monkeypatch.setattr(workspace_run_ops, "async_session_maker", FakeSessionMaker())
        monkeypatch.setattr(WorkspaceService, "_load_workspace", staticmethod(fake_load_workspace))
        monkeypatch.setattr(WorkspaceService, "_get_unit", staticmethod(fake_get_unit))
        monkeypatch.setattr(
            WorkspaceService,
            "_build_backtest_request",
            staticmethod(lambda _unit: SimpleNamespace()),
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "resolve_required_market_data_binding",
            fake_resolve_binding,
        )
        monkeypatch.setattr(
            workspace_unit_runtime,
            "sync_unit_runtime",
            fake_sync_unit_runtime,
        )
        import app.services.backtest.service as backtest_service_module

        monkeypatch.setattr(backtest_service_module, "BacktestService", FakeBacktestService)

        results = await WorkspaceService().run_units(
            "workspace-1",
            "user-1",
            [outer_unit.id],
        )

        assert results == [{"unit_id": "bound-unit", "task_id": "", "status": "running"}]
        assert resolve_units == [current_unit]
        assert current_read_sessions[0] is resolve_sessions[0]
        runtime_config = yaml.safe_load((runtime_dir / "config.yaml").read_text(encoding="utf-8"))
        assert runtime_config["data"] == {
            "start_date": "2024-02-01",
            "end_date": "2024-02-15",
        }

    @pytest.mark.asyncio
    async def test_trading_bound_unit_fails_closed_without_starting_runtime(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """A historical research binding never authorizes a paper/live start."""
        from app.services.workspace import run_ops as workspace_run_ops
        from app.services.workspace_service import WorkspaceService

        unit = SimpleNamespace(
            id="bound-trading-unit",
            workspace_id="trading-workspace",
            run_status="idle",
            data_config={"market_data_binding_required": True},
        )

        class FakeSession:
            def __init__(self) -> None:
                self.commits = 0

            async def execute(self, _statement: object) -> object:
                return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [unit]))

            async def commit(self) -> None:
                self.commits += 1

        class FakeSessionContext:
            def __init__(self, session: FakeSession) -> None:
                self.session = session

            async def __aenter__(self) -> FakeSession:
                return self.session

            async def __aexit__(self, *_args: object) -> None:
                return None

        class FakeSessionMaker:
            def __init__(self) -> None:
                self.session = FakeSession()

            def __call__(self) -> FakeSessionContext:
                return FakeSessionContext(self.session)

        start_calls: list[object] = []

        class FakeTradingService:
            def default_snapshot(self, **kwargs: object) -> dict[str, object]:
                return {
                    "status": kwargs["instance_status"],
                    "error": kwargs["error"],
                }

            async def start_units(self, *_args: object, **_kwargs: object) -> object:
                start_calls.append(object())
                raise AssertionError("A bound research unit must not start trading")

        async def fake_load_workspace(*_args: object, **_kwargs: object) -> object:
            return SimpleNamespace(settings={}, workspace_type="trading")

        session_maker = FakeSessionMaker()
        monkeypatch.setattr(workspace_run_ops, "async_session_maker", session_maker)
        monkeypatch.setattr(WorkspaceService, "_load_workspace", staticmethod(fake_load_workspace))
        service = WorkspaceService()
        service.trading_service = FakeTradingService()

        results = await service.run_units(
            "trading-workspace",
            "user-1",
            [unit.id],
        )

        assert results == [
            {
                "unit_id": "bound-trading-unit",
                "task_id": None,
                "status": "failed",
                "error": "MARKET_DATA_BINDING_TRADING_UNSUPPORTED",
            }
        ]
        assert unit.run_status == "failed"
        assert unit.trading_snapshot == {
            "status": "error",
            "error": "MARKET_DATA_BINDING_TRADING_UNSUPPORTED",
        }
        assert session_maker.session.commits == 1
        assert start_calls == []
