from __future__ import annotations

import numpy as np
import pytest
from purgedcv import deflated_sharpe_ratio

from app.services.asset_research.evaluation import deflated_sharpe
from app.services.research.statistics import calculate_deflated_sharpe


def test_deflated_sharpe_uses_variance_of_complete_trial_sharpes_not_return_variance() -> None:
    returns = [0.01, -0.004, 0.015, 0.002, -0.003, 0.008]
    trial_sharpes = [0.1, 0.3, 0.45, 0.2]
    expected = deflated_sharpe_ratio(
        np.asarray(returns),
        n_trials=4,
        var_sharpe=float(np.var(trial_sharpes, ddof=1)),
        bars_per_year=252,
    )

    result = calculate_deflated_sharpe(
        returns,
        trial_sharpes=trial_sharpes,
        bars_per_year=252,
    )
    adapter_result = deflated_sharpe(
        returns,
        n_trials=4,
        trial_sharpes=trial_sharpes,
        bars_per_year=252,
    )

    assert result == pytest.approx(expected)
    assert adapter_result == pytest.approx(expected)


def test_deflated_sharpe_fails_closed_when_complete_trial_sharpes_are_missing() -> None:
    with pytest.raises(ValueError, match="EVALUATION_TRIAL_SHARPES_REQUIRED"):
        calculate_deflated_sharpe([0.01, -0.01], trial_sharpes=[])
    with pytest.raises(ValueError, match="EVALUATION_TRIAL_SHARPES_REQUIRED"):
        deflated_sharpe([0.01, -0.01], n_trials=2)
