"""Tests for gateway_preset_service and gateway_launch_builder modules."""

from unittest.mock import MagicMock

import pytest

from app.services.gateway_launch_builder import (
    build_ctp_gateway_runtime_kwargs,
    build_gateway_launch,
    build_ib_web_gateway_runtime_kwargs,
    build_mt5_gateway_runtime_kwargs,
    coerce_bool,
    coerce_float,
    get_gateway_params,
    normalize_gateway_asset_type,
    normalize_gateway_exchange_type,
    parse_json_dict,
)
from app.services.gateway_preset_service import get_gateway_presets


# ---- gateway_preset_service tests ----


class TestGetGatewayPresets:
    def test_returns_list(self):
        presets = get_gateway_presets()
        assert isinstance(presets, list)
        assert len(presets) > 0

    def test_each_preset_has_required_fields(self):
        for preset in get_gateway_presets():
            assert "id" in preset
            assert "name" in preset
            assert "params" in preset
            assert "gateway" in preset["params"]

    def test_preset_ids_unique(self):
        ids = [p["id"] for p in get_gateway_presets()]
        assert len(ids) == len(set(ids))

    def test_ctp_preset_exists(self):
        presets = {p["id"]: p for p in get_gateway_presets()}
        assert "ctp_futures_gateway" in presets
        ctp = presets["ctp_futures_gateway"]
        assert ctp["params"]["gateway"]["exchange_type"] == "CTP"

    def test_binance_preset_exists(self):
        presets = {p["id"]: p for p in get_gateway_presets()}
        assert "binance_swap_gateway" in presets


# ---- gateway_launch_builder helper tests ----


class TestNormalizeGatewayExchangeType:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("CTP", "CTP"),
            ("", "CTP"),
            ("IB", "IB_WEB"),
            ("IB_WEB", "IB_WEB"),
            ("IBWEB", "IB_WEB"),
            ("MT5", "MT5"),
            ("BINANCE", "BINANCE"),
        ],
    )
    def test_known_types(self, value, expected):
        assert normalize_gateway_exchange_type(value) == expected

    def test_provider_hint_ib_web(self):
        assert normalize_gateway_exchange_type("", "ib_web_gateway") == "IB_WEB"

    def test_provider_hint_mt5(self):
        assert normalize_gateway_exchange_type("", "mt5_gateway") == "MT5"


class TestNormalizeGatewayAssetType:
    def test_ib_web_default_stk(self):
        assert normalize_gateway_asset_type("IB_WEB", "") == "STK"

    def test_ib_web_future(self):
        assert normalize_gateway_asset_type("IB_WEB", "FUTURE") == "FUT"

    def test_ctp_default_future(self):
        assert normalize_gateway_asset_type("CTP", "") == "FUTURE"

    def test_mt5_default_otc(self):
        assert normalize_gateway_asset_type("MT5", "") == "OTC"

    def test_unknown_default_future(self):
        assert normalize_gateway_asset_type("UNKNOWN", "") == "FUTURE"


class TestCoerceBool:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (True, True),
            (False, False),
            ("true", True),
            ("false", False),
            ("0", False),
            ("1", True),
            ("yes", True),
            ("no", False),
            (None, False),
            ("", False),
        ],
    )
    def test_values(self, value, expected):
        assert coerce_bool(value) == expected

    def test_default_override(self):
        assert coerce_bool(None, default=True) is True


class TestCoerceFloat:
    def test_numeric_string(self):
        assert coerce_float("3.14") == 3.14

    def test_none_default(self):
        assert coerce_float(None) == 0.0

    def test_empty_string(self):
        assert coerce_float("") == 0.0

    def test_invalid_returns_default(self):
        assert coerce_float("not_a_number", default=5.0) == 5.0


class TestParseJsonDict:
    def test_dict_passthrough(self):
        d = {"key": "value"}
        assert parse_json_dict(d) is d

    def test_json_string(self):
        assert parse_json_dict('{"a": 1}') == {"a": 1}

    def test_invalid_json(self):
        assert parse_json_dict("not json") is None

    def test_none_input(self):
        assert parse_json_dict(None) is None

    def test_json_array_returns_none(self):
        assert parse_json_dict("[1, 2, 3]") is None


class TestGetGatewayParams:
    def test_basic_extraction(self):
        instance = {
            "params": {
                "gateway": {
                    "enabled": True,
                    "provider": "ctp_gateway",
                    "exchange_type": "CTP",
                    "asset_type": "FUTURE",
                    "account_id": "acc1",
                }
            }
        }
        result = get_gateway_params(instance, "tcp")
        assert result["enabled"] is True
        assert result["provider"] == "ctp_gateway"
        assert result["account_id"] == "acc1"

    def test_empty_params(self):
        result = get_gateway_params({}, "tcp")
        assert result["enabled"] is False

    def test_non_dict_params(self):
        result = get_gateway_params({"params": "invalid"}, "tcp")
        assert result == {"enabled": False}


# ---- CTP builder tests ----


class TestBuildCtpGatewayRuntimeKwargs:
    def test_complete_ctp_config(self):
        config = {
            "ctp": {
                "investor_id": "inv001",
                "broker_id": "9999",
                "password": "secret",
                "fronts": {
                    "simnow": {
                        "td_address": "tcp://182.254.243.31:30001",
                        "md_address": "tcp://182.254.243.31:30011",
                    }
                },
            },
            "live": {"network": "simnow"},
        }
        result = build_ctp_gateway_runtime_kwargs(
            config_data=config,
            env_data={},
            gateway_params={"account_id": "acc1"},
            default_transport="tcp",
        )
        assert result["investor_id"] == "inv001"
        assert result["account_id"] == "acc1"
        assert result["exchange_type"] == "CTP"
        assert result["transport"] == "tcp"

    def test_raises_on_missing_credentials(self):
        with pytest.raises(ValueError, match="CTP gateway requires"):
            build_ctp_gateway_runtime_kwargs(
                config_data={},
                env_data={},
                gateway_params={},
                default_transport="tcp",
            )

    def test_env_overrides_config(self):
        config = {
            "ctp": {
                "investor_id": "config_inv",
                "broker_id": "9999",
                "password": "config_pwd",
                "fronts": {
                    "simnow": {
                        "td_address": "tcp://td",
                        "md_address": "tcp://md",
                    }
                },
            },
            "live": {"network": "simnow"},
        }
        result = build_ctp_gateway_runtime_kwargs(
            config_data=config,
            env_data={"CTP_INVESTOR_ID": "env_inv", "CTP_PASSWORD": "env_pwd"},
            gateway_params={},
            default_transport="tcp",
        )
        assert result["investor_id"] == "env_inv"
        assert result["password"] == "env_pwd"
        assert result["transport"] == "tcp"


# ---- IB Web builder tests ----


class TestBuildIbWebGatewayRuntimeKwargs:
    def test_minimal_config(self):
        result = build_ib_web_gateway_runtime_kwargs(
            config_data={},
            env_data={},
            gateway_params={"account_id": "DU123"},
            default_transport="tcp",
        )
        assert result["account_id"] == "DU123"
        assert result["exchange_type"] == "IB_WEB"
        assert result["base_url"] == "https://localhost:5000"
        assert result["transport"] == "tcp"

    def test_raises_without_account_id(self):
        with pytest.raises(ValueError, match="IB_WEB gateway requires account_id"):
            build_ib_web_gateway_runtime_kwargs(
                config_data={},
                env_data={},
                gateway_params={},
                default_transport="tcp",
            )

    def test_cookie_config(self):
        result = build_ib_web_gateway_runtime_kwargs(
            config_data={},
            env_data={},
            gateway_params={
                "account_id": "DU123",
                "cookie_source": "browser",
                "cookies": {"sid": "abc"},
            },
            default_transport="tcp",
        )
        assert result["cookie_source"] == "browser"
        assert result["cookies"] == {"sid": "abc"}
        assert result["transport"] == "tcp"

    def test_local_base_url_disables_proxies(self):
        result = build_ib_web_gateway_runtime_kwargs(
            config_data={},
            env_data={},
            gateway_params={
                "account_id": "DU123",
                "base_url": "https://localhost:5000/v1/api",
            },
            default_transport="tcp",
        )
        assert result["proxies"] == {}
        assert result["async_proxy"] == ""
        assert result["transport"] == "tcp"


# ---- MT5 builder tests ----


class TestBuildMt5GatewayRuntimeKwargs:
    def test_minimal_config(self):
        result = build_mt5_gateway_runtime_kwargs(
            config_data={},
            env_data={},
            gateway_params={"login": "12345", "password": "secret"},
        )
        assert result["login"] == 12345
        assert result["exchange_type"] == "MT5"
        assert result["auto_reconnect"] is True

    def test_raises_without_credentials(self):
        with pytest.raises(ValueError, match="MT5 gateway requires"):
            build_mt5_gateway_runtime_kwargs(
                config_data={},
                env_data={},
                gateway_params={},
            )

    def test_symbol_map_from_config(self):
        result = build_mt5_gateway_runtime_kwargs(
            config_data={"mt5": {"login": "111", "password": "p", "symbol_map": {"EURUSD": "EURUSDm"}}},
            env_data={},
            gateway_params={"login": "111", "password": "p"},
        )
        assert result["symbol_map"] == {"EURUSD": "EURUSDm"}


# ---- build_gateway_launch integration test ----


class TestBuildGatewayLaunch:
    def test_dispatches_to_ctp(self):
        config = {
            "ctp": {
                "investor_id": "inv",
                "broker_id": "9999",
                "password": "pwd",
                "fronts": {"simnow": {"td_address": "tcp://td", "md_address": "tcp://md"}},
            },
            "live": {"network": "simnow"},
        }
        mock_config_cls = MagicMock()
        mock_runtime_cls = MagicMock()
        result = build_gateway_launch(
            config_data=config,
            env_data={},
            gateway_params={"exchange_type": "CTP"},
            gateway_config_cls=mock_config_cls,
            gateway_runtime_cls=mock_runtime_cls,
            default_transport="tcp",
        )
        assert result["runtime_cls"] is mock_runtime_cls
        mock_config_cls.from_kwargs.assert_called_once()

    def test_dispatches_to_ib_web(self):
        mock_config_cls = MagicMock()
        result = build_gateway_launch(
            config_data={},
            env_data={},
            gateway_params={"exchange_type": "IB_WEB", "account_id": "DU123"},
            gateway_config_cls=mock_config_cls,
            gateway_runtime_cls=MagicMock(),
            default_transport="tcp",
        )
        assert result["runtime_kwargs"]["exchange_type"] == "IB_WEB"

    def test_dispatches_to_mt5(self):
        mock_config_cls = MagicMock()
        result = build_gateway_launch(
            config_data={},
            env_data={},
            gateway_params={"exchange_type": "MT5", "login": "111", "password": "p"},
            gateway_config_cls=mock_config_cls,
            gateway_runtime_cls=MagicMock(),
            default_transport="tcp",
        )
        assert result["runtime_kwargs"]["exchange_type"] == "MT5"
