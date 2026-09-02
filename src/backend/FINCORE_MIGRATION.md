# Fincore Integration Migration Guide

This document describes the fincore 0.5 integration and how to work with the
standardized financial metrics calculation system.

## Overview

The AI for Investor platform uses **fincore 0.5** for standardized return-based
metric calculations. Fincore 0.5 is a breaking, domain-oriented release: it
does not expose root-level metric functions or the old Empyrical/Pyfolio/
Alphalens facades. This integration therefore calls the owning metric modules
directly and never relies on removed compatibility surfaces.

## Architecture

### FincoreAdapter Pattern

The `FincoreAdapter` class (`app/services/backtest/analyzers.py`) provides a
unified interface for metric calculations:

```python
from app.services.backtest.analyzers import FincoreAdapter

# Create adapter (use_fincore=True enables fincore calculations)
adapter = FincoreAdapter(use_fincore=True)

# Calculate metrics
sharpe = adapter.calculate_sharpe_ratio(
    returns,
    risk_free_rate=0.0001,  # per-period risk-free return
    periods_per_year=252,
)
max_dd = adapter.calculate_max_drawdown(equity_curve)
total_return = adapter.calculate_total_returns(equity_curve)
annual_return = adapter.calculate_annual_returns(equity_curve, periods_per_year=252)
win_rate = adapter.calculate_win_rate(trades)
profit_factor = adapter.calculate_profit_factor(trades)
```

### Key Features

1. **Domain API**: Return metrics use fincore's focused 0.5 leaf modules.
2. **Explicit conversion**: The adapter converts platform equity curves into
   non-cumulative simple returns before calling fincore.
3. **Automatic fallback**: Python 3.10 or an unavailable/incompatible fincore
   installation uses the matching manual formulas.
4. **Accurate provenance**: `metrics_source` summarizes the four core return
   metrics; `metric_sources` records each core metric separately. Trade-level
   metrics remain `manual` because their inputs are platform trade records,
   not fincore return series.

### Fincore 0.5 API Boundary

The adapter calls only these canonical fincore 0.5 paths:

```python
from fincore.metrics.drawdown import max_drawdown
from fincore.metrics.ratios import sharpe_ratio
from fincore.metrics.returns import cum_returns_final, simple_returns
from fincore.metrics.yearly import annual_return
```

Do not import metrics from `fincore` itself. In 0.5 the package root is a
namespace index, and the former flat functions and facade packages were
removed.

## Available Metrics

### Basic Metrics

| Metric | Method | Description |
|--------|--------|-------------|
| Sharpe Ratio | `calculate_sharpe_ratio(returns, risk_free_rate, periods_per_year)` | Annualized risk-adjusted return |
| Max Drawdown | `calculate_max_drawdown(equity_curve)` | Peak-to-trough decline |
| Total Returns | `calculate_total_returns(equity_curve)` | Overall performance |
| Annual Returns | `calculate_annual_returns(equity_curve, periods_per_year)` | Yearly extrapolation |
| Win Rate | `calculate_win_rate(trades)` | Profitable trade percentage |

### Advanced Metrics

| Metric | Method | Description |
|--------|--------|-------------|
| Profit Factor | `calculate_profit_factor(trades)` | Win/loss ratio |
| Max Consecutive | `calculate_max_consecutive(trades, win=True/False)` | Win/loss streaks |
| Avg Holding Period | `calculate_avg_holding_period(trades)` | Mean trade duration |
| MDD with Duration | `calculate_max_drawdown_with_duration(equity_curve)` | Drawdown + time |

## Integration Points

### 1. BacktestService

The `BacktestService` uses `fincore_metrics_helper.calculate_metrics_from_log_data()`:

```python
from app.services.fincore_metrics_helper import calculate_metrics_from_log_data

metrics = calculate_metrics_from_log_data(log_result, use_fincore=True)
# Returns calculated metrics, `metrics_source`, and per-metric `metric_sources`.
```

### 2. AnalyticsService

The `AnalyticsService` uses `FincoreAdapter` directly:

```python
from app.services.analytics_service import AnalyticsService

service = AnalyticsService(use_fincore=True)
metrics = service.calculate_metrics(result_data)
```

### 3. Database Models

Results include `metrics_source` field:

```python
# BacktestResultModel.metrics_source = "fincore" or "manual"
# BacktestResult.metrics_source = "fincore" or "manual"
```

## Usage Examples

### Calculating Metrics from Raw Data

```python
from app.services.fincore_metrics_helper import calculate_metrics_from_log_data

# Prepare log data
log_data = {
    "equity_curve": [100000, 101000, 102000, ...],
    "trades": [{"pnlcomm": 100, "barlen": 5}, {"pnlcomm": -50, "barlen": 3}, ...],
}

# Calculate with fincore enabled
metrics = calculate_metrics_from_log_data(log_data, use_fincore=True)

print(f"Total Return: {metrics['total_return']}%")
print(f"Sharpe Ratio: {metrics['sharpe_ratio']}")
print(f"Max Drawdown: {metrics['max_drawdown']}%")
print(f"Win Rate: {metrics['win_rate']}%")
print(f"Source: {metrics['metrics_source']}")
print(f"Per-metric sources: {metrics['metric_sources']}")
```

### Comparing Calculation Methods

```python
from app.services.fincore_metrics_helper import compare_calculation_methods

comparison = compare_calculation_methods(log_data)

print(f"Manual Sharpe: {comparison['manual']['sharpe_ratio']}")
print(f"Fincore Sharpe: {comparison['fincore']['sharpe_ratio']}")
print(f"Difference: {comparison['differences']['sharpe_ratio']}")
print(f"Relative Error: {comparison['relative_errors']['sharpe_ratio']}%")
```

### Validating Consistency

```python
from app.services.fincore_metrics_helper import validate_calculation_consistency

# Validate that fincore and manual calculations are consistent
is_valid = validate_calculation_consistency(
    log_data,
    max_relative_error=0.01,  # 0.01% threshold
)
```

## Testing

### Run All Fincore Tests

```bash
# Run all fincore-related tests against the installed dependency
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_fincore_*.py -v

# Run with coverage
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest \
  tests/test_fincore_*.py \
  --cov=app.services.backtest.analyzers \
  --cov=app.services.fincore_metrics_helper
```

### Test Files

- `test_fincore_import.py` — Validates fincore installation
- `test_fincore_adapter.py` — Tests FincoreAdapter class (26 tests)
- `test_fincore_integration.py` — Tests backtest integration (18 tests)
- `test_fincore_advanced_metrics.py` — Tests advanced metrics (19 tests)

## Migration Checklist

When adding new metrics or modifying calculations:

- [ ] Add method to `FincoreAdapter` class
- [ ] Add Google-style docstring
- [ ] Add unit tests in `test_fincore_adapter.py`
- [ ] Add integration tests in `test_fincore_integration.py`
- [ ] Update `FINCORE_MIGRATION.md` documentation
- [ ] Verify backward compatibility

## Troubleshooting

### Issue: fincore import fails

**Solution**: The adapter automatically falls back to manual calculations.
fincore 0.5 requires Python 3.11 or newer. Check that the supported version is
installed:

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pip show fincore
```

### Issue: Metrics differ between methods

**Solution**: The manual fallback intentionally uses the same return conversion,
sample standard deviation, and annualization factor as fincore. Use
`compare_calculation_methods()` to detect a material drift.

### Issue: Performance degradation

**Solution**: The fincore calculations have minimal overhead. Profile with:

```python
import time

start = time.time()
metrics = calculate_metrics_from_log_data(log_data, use_fincore=True)
print(f"Calculation time: {time.time() - start:.4f}s")
```

## References

- **fincore Library**: https://github.com/cloudQuant/fincore
- **Fincore 0.5 migration notes**: https://github.com/cloudQuant/fincore/blob/master/CHANGELOG.md
- **FincoreAdapter**: `src/backend/app/services/backtest/analyzers.py`
- **Metrics Helper**: `src/backend/app/services/fincore_metrics_helper.py`
- **Backtest Service**: `src/backend/app/services/backtest_service.py`
- **Analytics Service**: `src/backend/app/services/analytics_service.py`

## Changelog

### Fincore 0.5 migration (2026-09-01)
- Pinned the Python 3.11+ dependency to `fincore>=0.5.0,<0.6.0`.
- Replaced import-only source marking with actual calls to fincore domain metrics.
- Converted equity curves to simple returns at the adapter boundary.
- Added per-metric provenance so trade-derived metrics remain explicitly manual.

### Story 1.1 (2024)
- Installed fincore v0.1.0
- Added dependency to pyproject.toml

### Story 1.2 (2024)
- Created FincoreAdapter class
- Implemented adapter pattern with fallback

### Story 1.3 (2024)
- Integrated FincoreAdapter into backtest service
- Added metrics_source tracking
- Created 18 integration tests

### Story 1.4 (2024)
- Extended FincoreAdapter with advanced metrics
- Integrated into AnalyticsService
- Created 19 advanced metrics tests

### Story 1.5 (2024)
- Documentation updates
- Migration guide creation
- Test coverage validation
