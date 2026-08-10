"""Lightweight drift monitors for shadow model cohorts and scorecards."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from scipy.stats import ks_2samp


@dataclass(frozen=True, slots=True)
class DriftReport:
    """Machine-readable drift result with a fail-closed promotion signal."""

    reference_count: int
    current_count: int
    prediction_drift_psd: float
    calibration_drift_psd: float
    data_drift_psd: float
    psd_threshold: float
    flagged: bool


def detect_drift(
    *,
    reference_probabilities: Sequence[float],
    current_probabilities: Sequence[float],
    reference_actual_rates: Sequence[float],
    current_actual_rates: Sequence[float],
    reference_feature_values: Sequence[float],
    current_feature_values: Sequence[float],
    psd_threshold: float = 0.1,
) -> DriftReport:
    """Detect drift using bounded two-sample PSI-style distances.

    The implementation uses Kolmogorov-Smirnov p-values converted to a stable
    1 - p distance.  It never returns an unbounded value and always reports a
    boolean flag so a model owner cannot silently skip a review.
    """
    prediction_distance = _psd(reference_probabilities, current_probabilities)
    calibration_distance = _psd(reference_actual_rates, current_actual_rates)
    data_distance = _psd(reference_feature_values, current_feature_values)
    flagged = max(
        prediction_distance,
        calibration_distance,
        data_distance,
    ) > psd_threshold
    return DriftReport(
        reference_count=len(reference_probabilities),
        current_count=len(current_probabilities),
        prediction_drift_psd=prediction_distance,
        calibration_drift_psd=calibration_distance,
        data_drift_psd=data_distance,
        psd_threshold=psd_threshold,
        flagged=flagged,
    )


def _psd(reference: Sequence[float], current: Sequence[float]) -> float:
    if not reference or not current:
        return 1.0
    try:
        result = ks_2samp(reference, current)
        return max(0.0, min(1.0, 1.0 - result.pvalue))
    except (TypeError, ValueError):
        return 1.0
