# 功能介绍

Backtrader Web 提供全面的量化交易功能。

## 核心模块

| 模块 | 端点前缀 | 说明 |
|------|----------|------|
| 认证 | `/api/v1/auth` | JWT 认证、注册、登录 |
| 策略 | `/api/v1/strategy` | CRUD、模板 |
| 回测 | `/api/v1/backtests` | **推荐** 增强回测 |
| 分析 | `/api/v1/analytics` | 回测数据分析 |
| 优化 | `/api/v1/optimization` | 参数优化 |
| 模拟交易 | `/api/v1/paper-trading` | 模拟账户、订单 |
| 实盘交易 | `/api/v1/live-trading` | 实盘账户、订单 |
| 行情数据 | `/api/v1/quote`, `/api/v1/realtime` | 实时行情 |
| 监控告警 | `/api/v1/monitoring` | 告警规则 |
| 工作区 | `/api/v1/workspace` | 工作区管理 |

## 功能详情

- [回测](./backtesting.md) - 基于 fincore 指标的历史数据回测
- [策略管理](./strategy-management.md) - CRUD、版本控制、模板
- [模拟交易](./paper-trading.md) - 模拟交易环境
- [实盘交易](./live-trading.md) - 真实券商对接
- [参数优化](./optimization.md) - 网格搜索、贝叶斯优化

> ⚠️ **废弃说明**：旧版 `/api/v1/backtest/*` 端点已废弃，请迁移至 `/api/v1/backtests/*`
