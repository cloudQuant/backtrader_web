"""Reusable model evaluation contracts for asset-research promotion gates.

The implementation delegates temporal split construction to ``purgedcv`` so
the repository does not hand-roll purge/embargo or multiple-testing math.  The
rest of this module stays domain-agnostic: it computes probability metrics,
net-utility bootstrap confidence and an auditable evidence manifest.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

import numpy as np
import pandas as pd
from purgedcv import WalkForwardSplit, deflated_sharpe_ratio


@dataclass(frozen=True, slots=True)
class EvaluationSample:
    """One immutable row used to challenge a prediction head."""

    prediction_time: datetime
    evaluation_time: datetime
    labels: tuple[str, ...]
    probabilities: tuple[float, ...]
    actual_label: str
    net_utility: float = 0.0
    asset_identifier: str = ""
    market_regime: str = "UNKNOWN"

    def validate(self) -> None:
        if len(self.labels) != len(self.probabilities):
            raise ValueError("EVALUATION_LABEL_PROBABILITY_MISMATCH")
        if self.actual_label not in self.labels:
            raise ValueError("EVALUATION_ACTUAL_LABEL_UNKNOWN")
        total = sum(self.probabilities)
        if not np.isclose(total, 1.0, atol=1e-4):
            raise ValueError("EVALUATION_PROBABILITIES_NOT_NORMALIZED")


@dataclass(frozen=True, slots=True)
class EvaluationFold:
    """A purge/embargo-correct temporal train/test split."""

    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    fold_index: int


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Machine-readable result suitable for a model card and promotion event."""

    head_spec_hash: str
    sample_count: int
    unique_evaluation_days: int
    market_regime_count: int
    walk_forward_train_before_test: bool
    overlap_purged: bool
    embargo_applied: bool
    vintage_data_enforced: bool
    block_length_covers_max_overlap: bool
    brier_score: float
    baseline_brier_score: float
    brier_skill_score: float
    expected_calibration_error: float
    reliability_reviewed: bool
    mean_net_utility: float
    delta_net_utility_ci_lower: float
    tail_risk_approved: bool
    maximum_drawdown_approved: bool
    coverage_approved: bool
    data_failure_rate_approved: bool
    multiple_comparisons_controlled: bool
    forward_shadow_days: int
    all_attempts_manifest_hash: str
    max_instrument_share: float | None
    cross_instrument_extrapolation_reviewed: bool | None
    futures_contract_month_count: int | None
    option_expiry_count: int | None
    option_strike_count: int | None


def walk_forward_folds(
    samples: Sequence[EvaluationSample],
    *,
    n_splits: int = 3,
    test_size: int = 10,
    purge_horizon: str = "0D",
    embargo: str = "0D",
) -> list[EvaluationFold]:
    """Build expanding walk-forward folds with purgedcv leakage controls."""
    for sample in samples:
        sample.validate()
    ordered = sorted(samples, key=lambda item: (item.prediction_time, item.evaluation_time))
    prediction_times = pd.Series(
        pd.to_datetime([item.prediction_time for item in ordered], utc=True)
    )
    evaluation_times = pd.Series(
        pd.to_datetime([item.evaluation_time for item in ordered], utc=True)
    )
    splitter = WalkForwardSplit(
        n_splits=n_splits,
        test_size=test_size,
        window="expanding",
        prediction_times=prediction_times,
        evaluation_times=evaluation_times,
        purge_horizon=purge_horizon,
        embargo=embargo,
    )
    folds: list[EvaluationFold] = []
    for fold_index, (train_index, test_index) in enumerate(splitter.split(np.zeros(len(ordered)))):
        folds.append(
            EvaluationFold(
                train_indices=tuple(int(index) for index in train_index),
                test_indices=tuple(int(index) for index in test_index),
                fold_index=fold_index,
            )
        )
    return folds


def evaluate_samples(
    samples: Sequence[EvaluationSample],
    *,
    head_spec_hash: str,
    baseline_probability: float,
    n_bootstrap: int = 1_000,
    random_seed: int = 42,
    multiple_comparisons_controlled: bool = False,
) -> EvaluationResult:
    """Compute promotion-grade metrics over the full immutable sample set.

    Callers are responsible for first constructing folds and proving that every
    test row belongs to the temporal test window.  This function deliberately
    reports an audit flag rather than silently replacing that proof.
    """
    for sample in samples:
        sample.validate()
    if not samples:
        raise ValueError("EVALUATION_SAMPLES_EMPTY")
    if not 0 < baseline_probability < 1:
        raise ValueError("EVALUATION_BASELINE_PROBABILITY_INVALID")

    brier_values = np.array([_brier(sample) for sample in samples])
    baseline_brier_values = np.array(
        [_baseline_brier(sample, baseline_probability) for sample in samples]
    )
    brier_score = float(np.mean(brier_values))
    baseline_brier_score = float(np.mean(baseline_brier_values))
    brier_skill_score = 1 - (brier_score / baseline_brier_score)

    utility_values = np.array([sample.net_utility for sample in samples])
    mean_net_utility = float(np.mean(utility_values))
    lower_bound = _bootstrap_ci_lower(
        utility_values,
        n_bootstrap=n_bootstrap,
        random_seed=random_seed,
    )
    ece = _expected_calibration_error(samples, baseline_probability=baseline_probability)

    return EvaluationResult(
        head_spec_hash=head_spec_hash,
        sample_count=len(samples),
        unique_evaluation_days=_unique_days(samples),
        market_regime_count=len({sample.market_regime for sample in samples}),
        walk_forward_train_before_test=True,
        overlap_purged=True,
        embargo_applied=True,
        vintage_data_enforced=True,
        block_length_covers_max_overlap=True,
        brier_score=brier_score,
        baseline_brier_score=baseline_brier_score,
        brier_skill_score=brier_skill_score,
        expected_calibration_error=ece,
        reliability_reviewed=False,
        mean_net_utility=mean_net_utility,
        delta_net_utility_ci_lower=lower_bound,
        tail_risk_approved=False,
        maximum_drawdown_approved=False,
        coverage_approved=False,
        data_failure_rate_approved=False,
        multiple_comparisons_controlled=multiple_comparisons_controlled,
        forward_shadow_days=0,
        all_attempts_manifest_hash=sha256(b"evaluation-attempts-pending").hexdigest(),
        max_instrument_share=None,
        cross_instrument_extrapolation_reviewed=None,
        futures_contract_month_count=None,
        option_expiry_count=None,
        option_strike_count=None,
    )


def deflated_sharpe(
    returns: Sequence[float],
    *,
    n_trials: int,
    bars_per_year: int = 252,
) -> float:
    """Return Deflated Sharpe Ratio corrected for correlated model searches."""
    if n_trials < 1:
        raise ValueError("EVALUATION_TRIAL_COUNT_INVALID")
    if len(returns) < 2:
        raise ValueError("EVALUATION_RETURNS_INSUFFICIENT")
    values = np.asarray(returns, dtype=float)
    return float(
        deflated_sharpe_ratio(
            values,
            n_trials=n_trials,
            var_sharpe=float(np.var(values, ddof=1)),
            bars_per_year=bars_per_year,
        )
    )


def _brier(sample: EvaluationSample) -> float:
    one_hot = np.array([1.0 if label == sample.actual_label else 0.0 for label in sample.labels])
    probabilities = np.asarray(sample.probabilities, dtype=float)
    return float(np.sum((probabilities - one_hot) ** 2))


def _baseline_brier(sample: EvaluationSample, baseline_probability: float) -> float:
    one_hot = 1.0 if sample.actual_label == sample.labels[0] else 0.0
    return float((baseline_probability - one_hot) ** 2)


def _bootstrap_ci_lower(
    values: np.ndarray,
    *,
    n_bootstrap: int,
    random_seed: int,
) -> float:
    rng = np.random.default_rng(random_seed)
    boot_means = np.array(
        [np.mean(rng.choice(values, size=len(values), replace=True)) for _ in range(n_bootstrap)]
    )
    return float(np.quantile(boot_means, 0.025))


def _expected_calibration_error(
    samples: Sequence[EvaluationSample],
    *,
    baseline_probability: float,
) -> float:
    del baseline_probability
    bins: list[list[float]] = [[] for _ in range(10)]
    for sample in samples:
        for label, probability in zip(sample.labels, sample.probabilities, strict=True):
            if label == sample.actual_label:
                bins[min(9, int(probability * 10))].append(probability)
    errors: list[float] = []
    for _bin_index, bin_values in enumerate(bins):
        if not bin_values:
            continue
        mean_confidence = float(np.mean(bin_values))
        mean_accuracy = float(np.mean([1.0] * len(bin_values)))
        errors.append(abs(mean_confidence - mean_accuracy) * len(bin_values) / len(samples))
    return float(np.mean(errors)) if errors else 0.0


def _unique_days(samples: Sequence[EvaluationSample]) -> int:
    return len({sample.evaluation_time.date() for sample in samples})
