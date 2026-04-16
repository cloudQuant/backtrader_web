# 参数优化

## 概述

使用各种优化算法为您的策略寻找最优参数。

## 支持的方法

### 网格搜索

系统地探索定义范围内的所有参数组合。

```json
{
  "method": "grid",
  "parameters": {
    "fast_period": {"start": 5, "end": 20, "step": 5},
    "slow_period": {"start": 20, "end": 50, "step": 5}
  }
}
```

### 贝叶斯优化

使用概率模型进行智能搜索（推荐用于大参数空间）。

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

## API 端点

### 提交优化任务

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

### 列出任务

```http
GET /api/v1/optimization/tasks?page=1&page_size=20
```

### 获取任务结果

```http
GET /api/v1/optimization/tasks/{id}
```

### 取消任务

```http
POST /api/v1/optimization/tasks/{id}/cancel
```

## 优化目标

| 目标 | 说明 |
|------|------|
| `total_return` | 总收益率 |
| `sharpe_ratio` | 夏普比率 |
| `max_drawdown` | 最小化最大回撤 |
| `calmar_ratio` | 卡玛比率 |
| `sortino_ratio` | 索提诺比率 |

## 结果分析

### 参数热力图 (2D)

使用 2D 热力图可视化参数敏感性。

### 参数曲面图 (3D)

参数组合的交互式 3D 可视化。

### 最优参数

根据优化目标自动选择。

## ⚠️ 警告

> **废弃说明**：旧版端点 `/api/v1/backtests/optimization/grid` 和 `/api/v1/backtests/optimization/bayesian` 已废弃。请改用 `/api/v1/optimization/submit`。
