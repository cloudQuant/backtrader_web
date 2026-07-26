"""Execution-model normalization tests."""

from app.services.backtest.execution_model import ExecutionModel


def test_execution_model_uses_asset_spec_then_explicit_overrides():
    model = ExecutionModel.from_asset_spec(
        {
            "asset_type": "futures",
            "symbol": "RB0",
            "contract_multiplier": 10,
            "margin_rate": 0.1,
            "min_order_size": 1,
            "commission_rate": 0.0001,
        },
        overrides={"slippage_bps": 2, "commission_rate": 0.0002},
    )

    assert model.contract_multiplier == 10
    assert model.margin_rate == 0.1
    assert model.commission_rate == 0.0002
    assert model.to_backtest_config()["multiplier"] == 10


def test_execution_model_safely_normalizes_invalid_or_negative_size_inputs():
    model = ExecutionModel.from_asset_spec(
        {"symbol": "RB0", "min_order_size": "bad", "lot_size": -1, "multiplier": -3}
    )

    assert model.min_order_size == 1
    assert model.lot_size == 0
    assert model.contract_multiplier == 0
