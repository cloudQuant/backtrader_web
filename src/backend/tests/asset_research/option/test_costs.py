"""Frozen all-in option-cost contracts for exact-contract outcome labels."""

from __future__ import annotations

import pytest

from app.services.asset_research.plugins.option.costs import parse_option_cost_snapshot


def _costs() -> dict[str, float | str]:
    return {
        "cost_model_version": "fixture-v1",
        "commission_rate": 0.002,
        "exchange_fee_rate": 0.001,
        "entry_slippage_rate": 0.002,
        "exit_slippage_rate": 0.002,
        "funding_cost_rate": 0.001,
        "exercise_settlement_cost_rate": 0.001,
        "other_cost_rate": 0.001,
    }


def test_cost_snapshot_requires_every_cost_component_and_has_a_replayable_total() -> None:
    costs, reason = parse_option_cost_snapshot(_costs())

    assert reason is None
    assert costs is not None
    assert costs.total_cost_rate == pytest.approx(0.01)
    assert costs.to_payload()["cost_model_version"] == "fixture-v1"


def test_cost_snapshot_refuses_to_assume_a_missing_cost_is_zero() -> None:
    raw = _costs()
    raw.pop("exercise_settlement_cost_rate")

    costs, reason = parse_option_cost_snapshot(raw)

    assert costs is None
    assert reason == "OPTION.COST_SNAPSHOT_INCOMPLETE"
