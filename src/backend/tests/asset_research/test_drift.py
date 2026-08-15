"""Bounded drift monitor contracts for shadow model cohorts."""

from app.services.asset_research.drift import detect_drift


def test_drift_report_is_not_flagged_for_identical_cohorts() -> None:
    report = detect_drift(
        reference_probabilities=[0.6] * 30,
        current_probabilities=[0.6] * 30,
        reference_actual_rates=[0.6] * 30,
        current_actual_rates=[0.6] * 30,
        reference_feature_values=[1.0] * 30,
        current_feature_values=[1.0] * 30,
        psd_threshold=0.1,
    )

    assert report.flagged is False


def test_drift_report_is_flagged_for_shifted_cohort() -> None:
    report = detect_drift(
        reference_probabilities=[0.1] * 30,
        current_probabilities=[0.9] * 30,
        reference_actual_rates=[0.1] * 30,
        current_actual_rates=[0.9] * 30,
        reference_feature_values=[0.0] * 30,
        current_feature_values=[1.0] * 30,
        psd_threshold=0.1,
    )

    assert report.flagged is True
