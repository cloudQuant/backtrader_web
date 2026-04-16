# Parameter Optimization

## Overview

Find the optimal parameters for your strategies using various optimization algorithms.

## Supported Methods

### Grid Search

Systematically explores all parameter combinations within defined ranges.

```json
{
  "method": "grid",
  "parameters": {
    "fast_period": {"start": 5, "end": 20, "step": 5},
    "slow_period": {"start": 20, "end": 50, "step": 5}
  }
}
```

### Bayesian Optimization

Intelligent search using probabilistic models (recommended for large parameter spaces).

```json
{
  "method": "bayesian",
  "parameters": {
    "fast_period": {"min": 5, "max": 50},
    "slow_period": {"min": 20, "max": 100}
  },
  "n_trials": 100
}
```

## API Endpoints

### Submit Optimization Task

```http
POST /api/v1/optimization/submit
Content-Type: application/json

{
  "strategy_id": 1,
  "symbol": "000001.SZ",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "optimization_method": "grid",
  "parameters": {
    "fast_period": {"start": 5, "end": 20, "step": 5},
    "slow_period": {"start": 20, "end": 50, "step": 5}
  },
  "objective": "sharpe_ratio"
}
```

### List Tasks

```http
GET /api/v1/optimization/tasks?page=1&page_size=20
```

### Get Task Results

```http
GET /api/v1/optimization/tasks/{id}
```

### Cancel Task

```http
POST /api/v1/optimization/tasks/{id}/cancel
```

## Optimization Objectives

| Objective | Description |
|-----------|-------------|
| `total_return` | Total return |
| `sharpe_ratio` | Sharpe ratio |
| `max_drawdown` | Minimize max drawdown |
| `calmar_ratio` | Calmar ratio |
| `sortino_ratio` | Sortino ratio |

## Results Analysis

### Parameter Heatmap (2D)

Visualize parameter sensitivity with 2D heatmaps.

### Parameter Surface (3D)

Interactive 3D visualization of parameter combinations.

### Best Parameters

Automatically selected based on the optimization objective.

## ⚠️ Warning

> **Deprecation Notice**: Legacy endpoints `/api/v1/backtests/optimization/grid` and `/api/v1/backtests/optimization/bayesian` are deprecated. Please use `/api/v1/optimization/submit` instead.
