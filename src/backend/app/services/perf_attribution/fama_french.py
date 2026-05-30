"""Fama-French three-factor attribution."""

import statistics

from app.schemas.perf_attribution import FamaFrenchAttributionResult


class FamaFrenchAttributionService:
    """Estimate alpha and factor betas with ordinary least squares."""

    def calculate(
        self,
        *,
        strategy_returns: list[float],
        market_returns: list[float],
        smb_returns: list[float],
        hml_returns: list[float],
        min_observations: int = 4,
    ) -> FamaFrenchAttributionResult:
        """Run y = alpha + b_mkt*mkt + b_smb*smb + b_hml*hml."""
        observation_count = min(
            len(strategy_returns), len(market_returns), len(smb_returns), len(hml_returns)
        )
        if observation_count < min_observations:
            return FamaFrenchAttributionResult(
                status="degraded",
                observation_count=observation_count,
                reason="insufficient_observations",
            )

        x_rows = [
            [
                1.0,
                float(market_returns[index]),
                float(smb_returns[index]),
                float(hml_returns[index]),
            ]
            for index in range(observation_count)
        ]
        y_values = [float(strategy_returns[index]) for index in range(observation_count)]
        try:
            coefficients = _solve_normal_equations(x_rows, y_values)
        except ValueError:
            return FamaFrenchAttributionResult(
                status="degraded",
                observation_count=observation_count,
                reason="singular_matrix",
            )

        predictions = [
            sum(coef * value for coef, value in zip(coefficients, row, strict=False))
            for row in x_rows
        ]
        y_mean = statistics.fmean(y_values)
        ss_total = sum((value - y_mean) ** 2 for value in y_values)
        ss_residual = sum(
            (actual - predicted) ** 2
            for actual, predicted in zip(y_values, predictions, strict=False)
        )
        r_squared = 1.0 if ss_total == 0 else 1 - ss_residual / ss_total
        return FamaFrenchAttributionResult(
            status="ok",
            observation_count=observation_count,
            alpha=round(coefficients[0], 6),
            market_beta=round(coefficients[1], 6),
            smb_beta=round(coefficients[2], 6),
            hml_beta=round(coefficients[3], 6),
            r_squared=round(r_squared, 6),
        )


def _solve_normal_equations(x_rows: list[list[float]], y_values: list[float]) -> list[float]:
    size = len(x_rows[0])
    matrix = [[0.0 for _ in range(size)] for _ in range(size)]
    vector = [0.0 for _ in range(size)]
    for row, y_value in zip(x_rows, y_values, strict=False):
        for left in range(size):
            vector[left] += row[left] * y_value
            for right in range(size):
                matrix[left][right] += row[left] * row[right]
    return _gaussian_solve(matrix, vector)


def _gaussian_solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row_index: abs(augmented[row_index][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("singular matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        for item_index in range(column, size + 1):
            augmented[column][item_index] /= pivot_value
        for row_index in range(size):
            if row_index == column:
                continue
            factor = augmented[row_index][column]
            for item_index in range(column, size + 1):
                augmented[row_index][item_index] -= factor * augmented[column][item_index]
    return [augmented[index][size] for index in range(size)]
