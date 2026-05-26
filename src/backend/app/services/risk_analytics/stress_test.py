"""Stress testing service based on backtest equity curves."""

from datetime import date

from app.schemas.risk_analytics import StressScenario, StressScenarioResult, StressTestResult
from app.services.risk_analytics.scenarios import BUILT_IN_STRESS_SCENARIOS


class StressTestService:
    """Run stress scenarios against a backtest equity curve."""

    def run_scenarios(
        self,
        *,
        equity_curve: list[float],
        equity_dates: list[str],
        scenarios: list[dict | StressScenario] | None = None,
    ) -> StressTestResult:
        """Run selected scenarios against equity values."""
        selected_scenarios = self._normalize_scenarios(scenarios)
        points = self._normalize_points(equity_curve, equity_dates)
        results = [self._run_one(points, scenario) for scenario in selected_scenarios]
        status = "ok" if all(result.status == "ok" for result in results) else "degraded"
        return StressTestResult(status=status, scenario_count=len(results), results=results)

    @staticmethod
    def _normalize_scenarios(scenarios: list[dict | StressScenario] | None) -> list[StressScenario]:
        if not scenarios:
            return list(BUILT_IN_STRESS_SCENARIOS)
        return [scenario if isinstance(scenario, StressScenario) else StressScenario(**scenario) for scenario in scenarios]

    @staticmethod
    def _normalize_points(equity_curve: list[float], equity_dates: list[str]) -> list[tuple[date, float]]:
        points: list[tuple[date, float]] = []
        for raw_date, raw_value in zip(equity_dates, equity_curve, strict=False):
            try:
                points.append((date.fromisoformat(str(raw_date)[:10]), float(raw_value)))
            except (TypeError, ValueError):
                continue
        return points

    def _run_one(
        self,
        points: list[tuple[date, float]],
        scenario: StressScenario,
    ) -> StressScenarioResult:
        start = date.fromisoformat(scenario.start_date)
        end = date.fromisoformat(scenario.end_date)
        window = [(point_date, value) for point_date, value in points if start <= point_date <= end]
        if len(window) < 2:
            return StressScenarioResult(
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                status="degraded",
                start_date=scenario.start_date,
                end_date=scenario.end_date,
                observation_count=len(window),
                reason="scenario_not_covered",
            )

        values = [value for _, value in window]
        max_loss = min((value - values[0]) / values[0] for value in values[1:] if values[0] > 0)
        max_drawdown = self._max_drawdown(values)
        recovery_days = self._recovery_days(window)
        return StressScenarioResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            status="ok",
            start_date=scenario.start_date,
            end_date=scenario.end_date,
            observation_count=len(window),
            max_loss=round(max_loss, 6),
            max_drawdown=round(max_drawdown, 6),
            recovery_days=recovery_days,
        )

    @staticmethod
    def _max_drawdown(values: list[float]) -> float:
        peak = values[0]
        max_drawdown = 0.0
        for value in values:
            peak = max(peak, value)
            if peak > 0:
                max_drawdown = min(max_drawdown, (value - peak) / peak)
        return max_drawdown

    @staticmethod
    def _recovery_days(window: list[tuple[date, float]]) -> int | None:
        values = [value for _, value in window]
        peak_index = 0
        drawdown_peak_index = 0
        trough_index = 0
        peak_value = values[0]
        worst_drawdown = 0.0
        for index, value in enumerate(values):
            if value > peak_value:
                peak_value = value
                peak_index = index
            drawdown = (value - peak_value) / peak_value if peak_value > 0 else 0.0
            if drawdown < worst_drawdown:
                worst_drawdown = drawdown
                drawdown_peak_index = peak_index
                trough_index = index
        for index in range(trough_index + 1, len(values)):
            if values[index] >= values[drawdown_peak_index]:
                return (window[index][0] - window[drawdown_peak_index][0]).days
        return None
