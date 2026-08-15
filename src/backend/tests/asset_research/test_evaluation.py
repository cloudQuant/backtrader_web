"""Purge/embargo model-evaluation contracts for asset research."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.asset_research.evaluation import (
    EvaluationResult,
    EvaluationSample,
    deflated_sharpe,
    evaluate_samples,
    walk_forward_folds,
)


def _sample(index: int) -> EvaluationSample:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prediction_time = base + timedelta(days=index)
    actual_label = "UP" if index % 3 != 0 else "DOWN"
    probability = 0.65 if index % 3 != 0 else 0.35
    return EvaluationSample(
        prediction_time=prediction_time,
        evaluation_time=prediction_time + timedelta(days=5),
        labels=("UP", "DOWN"),
        probabilities=(probability, 1.0 - probability),
        actual_label=actual_label,
        net_utility=0.01 if actual_label == "UP" else -0.01,
        asset_identifier="IF2609",
        market_regime="TREND" if index % 2 == 0 else "RANGE",
    )


def test_walk_forward_folds_are_purged_and_embargoed() -> None:
    samples = [_sample(index) for index in range(40)]

    folds = walk_forward_folds(
        samples,
        n_splits=3,
        test_size=10,
        purge_horizon="4D",
        embargo="1D",
    )

    assert len(folds) == 3
    assert all(fold.train_indices for fold in folds)
    assert all(len(fold.test_indices) == 10 for fold in folds)


def test_evaluate_samples_returns_promotion_ready_metrics() -> None:
    samples = [_sample(index) for index in range(40)]

    result = evaluate_samples(
        samples,
        head_spec_hash="a" * 64,
        baseline_probability=0.5,
        n_bootstrap=20,
    )

    assert isinstance(result, EvaluationResult)
    assert result.sample_count == 40
    assert result.unique_evaluation_days == 40
    assert result.market_regime_count == 2
    assert result.overlap_purged is True
    assert result.embargo_applied is True
    assert result.brier_score >= 0
    assert result.baseline_brier_score > 0
    assert result.expected_calibration_error >= 0


def test_deflated_sharpe_rejects_insufficient_returns() -> None:
    with pytest.raises(ValueError, match="EVALUATION_RETURNS_INSUFFICIENT"):
        deflated_sharpe([0.01], n_trials=1)


def test_deflated_sharpe_accepts_correlated_trial_count() -> None:
    value = deflated_sharpe([0.01, 0.02, -0.01, 0.03], n_trials=10)
    assert value is not None
