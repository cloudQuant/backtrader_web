# 参数优化指南

本文档介绍 Backtrader Web 的策略参数优化功能。

## 1. 概述

参数优化模块帮助你找到策略的最佳参数组合，支持两种优化方法：

| 方法 | 说明 | 适用场景 |
|------|------|---------|
| **网格搜索** | 遍历所有参数组合 | 参数空间较小（<1000 组合） |
| **贝叶斯优化** | 基于 Optuna 智能搜索 | 参数空间较大，需要高效搜索 |

## 2. 快速开始

### 2.1 访问优化页面

登录后访问 `/optimization` 页面。

### 2.2 基本流程

1. **选择策略** — 选择要优化的策略模板
2. **设置参数范围** — 为每个参数指定搜索范围和步长
3. **选择优化方法** — 网格搜索或贝叶斯优化
4. **提交任务** — 系统自动运行多组参数回测
5. **查看结果** — 查看最优参数和所有组合的性能对比

## 3. 参数范围配置

### 3.1 获取策略参数

```bash
# 查询策略可优化参数
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/optimization/strategy-params/002_dual_ma
```

返回示例：
```json
{
  "strategy_id": "002_dual_ma",
  "strategy_name": "双均线交叉策略",
  "params": [
    {"name": "short_period", "type": "int", "default": 5, "description": "短期均线周期"},
    {"name": "long_period", "type": "int", "default": 20, "description": "长期均线周期"}
  ]
}
```

### 3.2 设置搜索范围

| 字段 | 说明 | 示例 |
|------|------|------|
| `start` | 参数起始值 | 3 |
| `end` | 参数结束值 | 30 |
| `step` | 搜索步长 | 1 |
| `type` | 参数类型 | `int` / `float` |

**示例**：优化双均线策略

```json
{
  "strategy_id": "002_dual_ma",
  "param_ranges": {
    "short_period": {"start": 3, "end": 15, "step": 1, "type": "int"},
    "long_period": {"start": 10, "end": 60, "step": 5, "type": "int"}
  },
  "n_workers": 4
}
```

此配置将测试 13 × 11 = 143 种参数组合。

## 4. API 接口

### 4.1 提交优化任务

```bash
curl -X POST http://localhost:8000/api/v1/optimization/submit \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "002_dual_ma",
    "param_ranges": {
      "short_period": {"start": 3, "end": 15, "step": 1, "type": "int"},
      "long_period": {"start": 10, "end": 60, "step": 5, "type": "int"}
    },
    "n_workers": 4
  }'
```

返回：
```json
{
  "task_id": "opt_abc123",
  "total_combinations": 143,
  "message": "Optimization task submitted, total 143 parameter combinations, using 4 workers"
}
```

### 4.2 查询进度

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/optimization/progress/{task_id}
```

### 4.3 获取结果

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/optimization/results/{task_id}
```

### 4.4 增强版优化 API

```bash
# 网格搜索优化
curl -X POST http://localhost:8000/api/v1/backtests/optimization/grid \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "002_dual_ma",
    "method": "grid",
    "param_ranges": {...}
  }'

# 贝叶斯优化
curl -X POST http://localhost:8000/api/v1/backtests/optimization/bayesian \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "002_dual_ma",
    "method": "bayesian",
    "param_ranges": {...},
    "n_trials": 50
  }'
```

## 5. 结果解读

### 5.1 结果指标

优化结果按以下指标排序（默认按夏普比率）：

| 指标 | 说明 |
|------|------|
| 参数组合 | 该次运行使用的参数值 |
| 总收益率 | 该参数下的总回报 |
| 夏普比率 | 风险调整后收益（排序依据） |
| 最大回撤 | 最大亏损幅度 |
| 交易次数 | 策略执行的交易数量 |

### 5.2 选择最优参数

建议综合考虑以下因素：

1. **夏普比率最高** — 风险调整后收益最好
2. **最大回撤可接受** — 不超过你的风险承受能力
3. **交易次数合理** — 避免过度交易或交易过少
4. **参数稳健性** — 邻近参数是否也表现良好（避免过拟合）

## 6. 最佳实践

### 6.1 避免过拟合

- 使用样本外数据验证最优参数
- 将数据分为训练集和测试集
- 优先选择参数空间中表现稳定的区域

### 6.2 参数空间设计

- 先用粗粒度步长扫描，再用细粒度精确搜索
- 参数范围不要太大，保持在合理的策略逻辑范围内
- 注意参数间的逻辑约束（如 `short_period < long_period`）

### 6.3 性能建议

- 组合数量 <1000 时使用网格搜索
- 组合数量 >1000 时使用贝叶斯优化
- 适当增加 `n_workers` 利用多核 CPU

## 7. 相关文档

- [回测指南](BACKTEST_GUIDE.md) — 回测基础使用
- [策略开发](STRATEGY_DEVELOPMENT.md) — 编写自定义策略
- [API 文档](API.md) — 完整 API 接口说明
