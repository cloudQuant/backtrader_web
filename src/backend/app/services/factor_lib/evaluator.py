"""Factor evaluation metrics."""

import math
import statistics

from app.schemas.factor_lib import FactorEvaluationResult


class FactorEvaluator:
    """Evaluate single-factor predictive quality."""

    def evaluate(
        self,
        *,
        factor_values: list[float | None],
        future_returns: list[float | None],
        quantiles: int = 5,
        min_observations: int = 2,
    ) -> FactorEvaluationResult:
        """Calculate IC/IR and long-short return for one cross-section."""
        pairs = [
            (float(factor), float(future_return))
            for factor, future_return in zip(factor_values, future_returns, strict=False)
            if factor is not None and future_return is not None
        ]
        if len(pairs) < min_observations:
            return FactorEvaluationResult(
                status="degraded",
                observation_count=len(pairs),
                reason="insufficient_observations",
            )

        factor_series = [pair[0] for pair in pairs]
        return_series = [pair[1] for pair in pairs]
        ic = self._spearman_correlation(factor_series, return_series)
        if ic is None:
            return FactorEvaluationResult(
                status="degraded",
                observation_count=len(pairs),
                reason="constant_values",
            )

        long_short_return = self._long_short_return(pairs, quantiles)
        return FactorEvaluationResult(
            status="ok",
            observation_count=len(pairs),
            ic_mean=round(ic, 6),
            ic_std=0.0,
            ic_ir=None,
            ic_t_stat=None,
            long_short_return=round(long_short_return, 6),
        )

    @staticmethod
    def _spearman_correlation(left: list[float], right: list[float]) -> float | None:
        left_ranks = _rank(left)
        right_ranks = _rank(right)
        left_std = statistics.pstdev(left_ranks)
        right_std = statistics.pstdev(right_ranks)
        if left_std <= 0 or right_std <= 0:
            return None
        left_mean = statistics.fmean(left_ranks)
        right_mean = statistics.fmean(right_ranks)
        covariance = statistics.fmean(
            (left_rank - left_mean) * (right_rank - right_mean)
            for left_rank, right_rank in zip(left_ranks, right_ranks, strict=False)
        )
        return covariance / (left_std * right_std)

    @staticmethod
    def _long_short_return(pairs: list[tuple[float, float]], quantiles: int) -> float:
        sorted_pairs = sorted(pairs, key=lambda item: item[0])
        bucket_size = max(1, math.ceil(len(sorted_pairs) / quantiles))
        short_bucket = sorted_pairs[:bucket_size]
        long_bucket = sorted_pairs[-bucket_size:]
        return statistics.fmean(item[1] for item in long_bucket) - statistics.fmean(
            item[1] for item in short_bucket
        )


def _rank(values: list[float]) -> list[float]:
    sorted_values = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(sorted_values):
        end = index + 1
        while end < len(sorted_values) and sorted_values[end][1] == sorted_values[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for original_index, _ in sorted_values[index:end]:
            ranks[original_index] = average_rank
        index = end
    return ranks
