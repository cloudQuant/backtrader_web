import datetime as dt
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.schemas.backtest_enhanced import BacktestRequest, get_strategy_params
from app.schemas.strategy import ParamSpec


def _base_payload(**overrides):
    payload = {
        "strategy_id": "001_ma_cross",
        "symbol": "000001.SZ",
        "start_date": "2023-01-01T00:00:00",
        "end_date": "2023-06-30T00:00:00",
        "initial_cash": 100000,
        "commission": 0.001,
        "params": {},
    }
    payload.update(overrides)
    return payload


def test_backtest_request_normalizes_timezone_to_utc():
    req = BacktestRequest(**_base_payload())
    assert req.start_date.tzinfo is not None
    assert req.end_date.tzinfo is not None
    assert req.start_date.tzinfo == dt.timezone.utc
    assert req.end_date.tzinfo == dt.timezone.utc


def test_backtest_request_rejects_end_date_before_start_date():
    with pytest.raises(ValidationError) as e:
        BacktestRequest(**_base_payload(end_date="2022-12-31T00:00:00"))
    assert "end_date 必须晚于 start_date" in str(e.value)


def test_backtest_request_rejects_range_more_than_10_years():
    with pytest.raises(ValidationError) as e:
        BacktestRequest(
            **_base_payload(
                start_date="2000-01-01T00:00:00",
                end_date="2011-01-02T00:00:00",
            )
        )
    assert "回测时间范围不能超过 10 年" in str(e.value)


def test_backtest_request_rejects_future_end_date():
    now = dt.datetime.now(dt.timezone.utc)
    start = (now - dt.timedelta(days=60)).replace(microsecond=0).isoformat()
    end = (now + dt.timedelta(days=1)).replace(microsecond=0).isoformat()
    with pytest.raises(ValidationError) as e:
        BacktestRequest(**_base_payload(start_date=start, end_date=end))
    assert "end_date 不能是未来日期" in str(e.value)


def test_backtest_request_rejects_too_short_period():
    with pytest.raises(ValidationError) as e:
        BacktestRequest(
            **_base_payload(
                start_date="2023-01-01T00:00:00",
                end_date="2023-01-15T00:00:00",
            )
        )
    assert "回测时间范围不能少于 30 天" in str(e.value)


def test_backtest_request_validate_params_unknown_param():
    with patch("app.schemas.backtest_enhanced.get_strategy_params", return_value={"period": ParamSpec(type="int", default=10)}):
        with pytest.raises(ValidationError) as e:
            BacktestRequest(**_base_payload(params={"unknown": 1}))
        assert "未知参数" in str(e.value)


def test_backtest_request_validate_params_type_and_bounds():
    specs = {
        "period": ParamSpec(type="int", default=10, min=5, max=50),
        "ratio": ParamSpec(type="float", default=0.5, min=0.0, max=1.0),
        "mode": ParamSpec(type="string", default="a", options=["a", "b"]),
        "enabled": ParamSpec(type="bool", default=True),
    }

    with patch("app.schemas.backtest_enhanced.get_strategy_params", return_value=specs):
        BacktestRequest(**_base_payload(params={"period": 10, "ratio": 0.7, "mode": "a", "enabled": True}))

        with pytest.raises(ValidationError):
            BacktestRequest(**_base_payload(params={"period": "10"}))
        with pytest.raises(ValidationError):
            BacktestRequest(**_base_payload(params={"period": 1}))
        with pytest.raises(ValidationError):
            BacktestRequest(**_base_payload(params={"period": 999}))
        with pytest.raises(ValidationError):
            BacktestRequest(**_base_payload(params={"ratio": "0.1"}))
        with pytest.raises(ValidationError):
            BacktestRequest(**_base_payload(params={"ratio": -0.1}))
        with pytest.raises(ValidationError):
            BacktestRequest(**_base_payload(params={"ratio": 999.0}))
        with pytest.raises(ValidationError):
            BacktestRequest(**_base_payload(params={"mode": 1}))
        with pytest.raises(ValidationError):
            BacktestRequest(**_base_payload(params={"mode": "c"}))
        with pytest.raises(ValidationError):
            BacktestRequest(**_base_payload(params={"enabled": "true"}))


def test_backtest_request_validate_params_generic_options_branch():
    specs = {
        "choice": ParamSpec(type="enum", default="a", options=["a", "b"]),
    }
    with patch("app.schemas.backtest_enhanced.get_strategy_params", return_value=specs):
        with pytest.raises(ValidationError) as e:
            BacktestRequest(**_base_payload(params={"choice": "c"}))
        assert "必须是以下之一" in str(e.value)


def test_get_strategy_params_found_and_not_found(monkeypatch):
    dummy = SimpleNamespace(id="t1", params={"p": ParamSpec(type="int", default=1)})
    monkeypatch.setattr("app.services.strategy_service.STRATEGY_TEMPLATES", [dummy], raising=True)

    assert "p" in get_strategy_params("t1")
    assert get_strategy_params("missing") == {}
