import datetime as dt
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.schemas.backtest_enhanced import BacktestRequest, get_strategy_params
from app.schemas.strategy import ParamSpec


def _base_payload(**overrides):
    """Create a base backtest request payload with optional overrides."""
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
    """Test that timezone is normalized to UTC."""
    req = BacktestRequest(**_base_payload())
    assert req.start_date.tzinfo is not None
    assert req.end_date.tzinfo is not None
    assert req.start_date.tzinfo == dt.timezone.utc
    assert req.end_date.tzinfo == dt.timezone.utc


def test_backtest_request_rejects_end_date_before_start_date():
    """Test that end_date before start_date is rejected."""
    with pytest.raises(ValidationError) as e:
        BacktestRequest(**_base_payload(end_date="2022-12-31T00:00:00"))
    assert "must be later than start_date" in str(e.value).lower()


def test_backtest_request_rejects_range_more_than_10_years():
    """Test that range > 10 years is rejected."""
    with pytest.raises(ValidationError) as e:
        BacktestRequest(
            **_base_payload(
                start_date="2000-01-01T00:00:00",
                end_date="2011-01-02T00:00:00",
            )
        )
    assert "10" in str(e.value) and ("year" in str(e.value).lower() or "range" in str(e.value).lower())


def test_backtest_request_rejects_future_end_date():
    """Test that future end_date is rejected."""
    now = dt.datetime.now(dt.timezone.utc)
    start = (now - dt.timedelta(days=60)).replace(microsecond=0).isoformat()
    end = (now + dt.timedelta(days=1)).replace(microsecond=0).isoformat()
    with pytest.raises(ValidationError) as e:
        BacktestRequest(**_base_payload(start_date=start, end_date=end))
    assert "future" in str(e.value).lower()


def test_backtest_request_rejects_too_short_period():
    """Test that range < 30 days is rejected."""
    with pytest.raises(ValidationError) as e:
        BacktestRequest(
            **_base_payload(
                start_date="2023-01-01T00:00:00",
                end_date="2023-01-15T00:00:00",
            )
        )
    assert "30" in str(e.value) and ("day" in str(e.value).lower())


def test_backtest_request_validate_params_unknown_param():
    """Test that unknown parameters are rejected."""
    with patch("app.schemas.backtest_enhanced.get_strategy_params", return_value={"period": ParamSpec(type="int", default=10)}):
        with pytest.raises(ValidationError) as e:
            BacktestRequest(**_base_payload(params={"unknown": 1}))
        assert "unknown" in str(e.value).lower() or "extra" in str(e.value).lower()


def test_backtest_request_validate_params_type_and_bounds():
    """Test parameter type and bounds validation."""
    specs = {
        "period": ParamSpec(type="int", default=10, min=5, max=50),
        "ratio": ParamSpec(type="float", default=0.5, min=0.0, max=1.0),
        "mode": ParamSpec(type="string", default="a", options=["a", "b"]),
        "enabled": ParamSpec(type="bool", default=True),
    }

    with patch("app.schemas.backtest_enhanced.get_strategy_params", return_value=specs):
        # Valid request
        BacktestRequest(**_base_payload(params={"period": 10, "ratio": 0.7, "mode": "a", "enabled": True}))

        # Invalid requests
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
    """Test enum parameter validation."""
    specs = {
        "choice": ParamSpec(type="enum", default="a", options=["a", "b"]),
    }
    with patch("app.schemas.backtest_enhanced.get_strategy_params", return_value=specs):
        with pytest.raises(ValidationError) as e:
            BacktestRequest(**_base_payload(params={"choice": "c"}))
        assert "option" in str(e.value).lower() or "valid" in str(e.value).lower()


def test_get_strategy_params_found_and_not_found(monkeypatch):
    """Test get_strategy_params with found and not found cases."""
    dummy = SimpleNamespace(id="t1", params={"p": ParamSpec(type="int", default=1)})
    monkeypatch.setattr(
        "app.services.strategy_service.get_all_strategy_templates",
        lambda: [dummy],
        raising=True,
    )

    assert "p" in get_strategy_params("t1")
    assert get_strategy_params("missing") == {}
