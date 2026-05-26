"""Factor correlation analysis."""

import statistics

from app.schemas.factor_lib import FactorCorrelationResult, HighCorrelationPair


class FactorCorrelationService:
    """Analyze correlation between factor value series."""

    def analyze(
        self,
        factor_values: dict[str, list[float | None]],
        *,
        threshold: float = 0.8,
        min_observations: int = 2,
    ) -> FactorCorrelationResult:
        """Calculate Pearson correlation matrix and high-correlation pairs."""
        factor_names = list(factor_values.keys())
        if len(factor_names) < 2:
            return FactorCorrelationResult(
                status="degraded",
                factor_count=len(factor_names),
                reason="insufficient_factors",
            )

        matrix: dict[str, dict[str, float]] = {name: {} for name in factor_names}
        high_pairs: list[HighCorrelationPair] = []
        max_observations = 0
        for left_index, left_name in enumerate(factor_names):
            for right_index, right_name in enumerate(factor_names):
                if left_name == right_name:
                    correlation = 1.0
                    observation_count = len([value for value in factor_values[left_name] if value is not None])
                else:
                    correlation, observation_count = self._correlate(
                        factor_values[left_name], factor_values[right_name], min_observations
                    )
                max_observations = max(max_observations, observation_count)
                matrix[left_name][right_name] = round(correlation, 6)
                if right_index > left_index and abs(correlation) >= threshold:
                    high_pairs.append(
                        HighCorrelationPair(
                            factor_a=left_name,
                            factor_b=right_name,
                            correlation=round(correlation, 6),
                        )
                    )

        return FactorCorrelationResult(
            status="ok",
            factor_count=len(factor_names),
            observation_count=max_observations,
            matrix=matrix,
            high_correlation_pairs=high_pairs,
        )

    @staticmethod
    def _correlate(
        left: list[float | None],
        right: list[float | None],
        min_observations: int,
    ) -> tuple[float, int]:
        pairs = [
            (float(left_value), float(right_value))
            for left_value, right_value in zip(left, right, strict=False)
            if left_value is not None and right_value is not None
        ]
        if len(pairs) < min_observations:
            return 0.0, len(pairs)
        left_values = [pair[0] for pair in pairs]
        right_values = [pair[1] for pair in pairs]
        left_std = statistics.pstdev(left_values)
        right_std = statistics.pstdev(right_values)
        if left_std <= 0 or right_std <= 0:
            return 0.0, len(pairs)
        left_mean = statistics.fmean(left_values)
        right_mean = statistics.fmean(right_values)
        covariance = statistics.fmean(
            (left_value - left_mean) * (right_value - right_mean)
            for left_value, right_value in pairs
        )
        return covariance / (left_std * right_std), len(pairs)
