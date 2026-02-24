# API Guide

The backend is a FastAPI service. The interactive OpenAPI docs are available at:

- `http://localhost:8001/docs` (开发环境)

All API routes are mounted under `/api/v1`。前端通过 Vite proxy 将 `/api` 转发至后端。

> **Tip**: 以下端点列表从源码 `src/backend/app/api/` 自动提取，共 **15 个模块、80+ 端点**。

---

## 1. Auth（认证）

| Method | Path | Summary |
|--------|------|---------|
| POST | `/auth/register` | 用户注册 |
| POST | `/auth/login` | 用户登录（返回 JWT） |
| POST | `/auth/login` | 登录（含 refresh token） |
| POST | `/auth/refresh` | 刷新 token |
| POST | `/auth/logout` | 退出登录 |
| PUT | `/auth/change-password` | 修改密码 |
| GET | `/auth/me` | 获取当前用户信息 |

## 2. Strategy（策略管理）

| Method | Path | Summary |
|--------|------|---------|
| POST | `/strategy/` | 创建策略 |
| GET | `/strategy/` | 策略列表 |
| GET | `/strategy/templates` | 获取策略模板列表 |
| GET | `/strategy/templates/{id}` | 获取模板详情 |
| GET | `/strategy/templates/{id}/readme` | 获取模板 README |
| GET | `/strategy/templates/{id}/config` | 获取模板参数配置 |
| GET | `/strategy/{id}` | 获取策略详情 |
| PUT | `/strategy/{id}` | 更新策略 |
| DELETE | `/strategy/{id}` | 删除策略 |

## 3. Backtest（回测）

| Method | Path | Summary |
|--------|------|---------|
| POST | `/backtest/run` | 运行回测 |
| GET | `/backtest/` | 回测历史列表 |
| GET | `/backtest/{task_id}` | 获取回测结果 |
| GET | `/backtest/{task_id}/status` | 查询回测任务状态 |
| POST | `/backtest/{task_id}/cancel` | 取消回测任务 |
| DELETE | `/backtest/{task_id}` | 删除回测结果 |

## 4. Analytics（回测分析）

| Method | Path | Summary |
|--------|------|---------|
| GET | `/analytics/{task_id}/detail` | 回测详细分析数据 |
| GET | `/analytics/{task_id}/kline` | K线 + 交易信号数据 |
| GET | `/analytics/{task_id}/monthly-returns` | 月度收益率 |
| GET | `/analytics/{task_id}/optimization` | 优化结果分析 |
| GET | `/analytics/{task_id}/export` | 导出报告（HTML/PDF/Excel） |

## 5. Optimization（参数优化）

| Method | Path | Summary |
|--------|------|---------|
| GET | `/optimization/strategy-params/{id}` | 获取策略默认参数 |
| POST | `/optimization/submit` | 提交优化任务 |
| GET | `/optimization/progress/{task_id}` | 查询优化进度 |
| GET | `/optimization/results/{task_id}` | 获取优化结果 |
| POST | `/optimization/cancel/{task_id}` | 取消优化任务 |

## 6. Live Trading（实盘交易）

| Method | Path | Summary |
|--------|------|---------|
| GET | `/live-trading/` | 实盘实例列表 |
| POST | `/live-trading/` | 添加实盘实例 |
| GET | `/live-trading/{id}` | 实例详情 |
| DELETE | `/live-trading/{id}` | 删除实例 |
| POST | `/live-trading/{id}/start` | 启动实例 |
| POST | `/live-trading/{id}/stop` | 停止实例 |
| POST | `/live-trading/start-all` | 一键启动全部 |
| POST | `/live-trading/stop-all` | 一键停止全部 |
| GET | `/live-trading/{id}/detail` | 实盘分析详情 |
| GET | `/live-trading/{id}/kline` | 实盘 K 线数据 |
| GET | `/live-trading/{id}/monthly-returns` | 实盘月度收益 |

## 7. Portfolio（投资组合）

| Method | Path | Summary |
|--------|------|---------|
| GET | `/portfolio/overview` | 组合概览（总资产/盈亏/夏普等） |
| GET | `/portfolio/positions` | 聚合持仓 |
| GET | `/portfolio/trades` | 聚合交易记录 |
| GET | `/portfolio/equity` | 组合资金曲线 |
| GET | `/portfolio/allocation` | 策略资产配置 |

## 8. Enhanced Backtest（增强回测）

| Method | Path | Summary |
|--------|------|---------|
| POST | `/backtests/run` | 运行增强回测 |
| GET | `/backtests/{task_id}` | 获取结果 |
| GET | `/backtests/{task_id}/status` | 查询状态 |
| GET | `/backtests/` | 历史列表 |
| GET | `/backtests/{task_id}/report/html` | 导出 HTML 报告 |
| GET | `/backtests/{task_id}/report/pdf` | 导出 PDF 报告 |
| GET | `/backtests/{task_id}/report/excel` | 导出 Excel 报告 |
| WS | `/backtests/ws/backtest/{task_id}` | WebSocket 实时进度 |

## 9. Paper Trading（模拟交易）

| Method | Path | Summary |
|--------|------|---------|
| POST | `/paper-trading/accounts` | 创建模拟账户 |
| GET | `/paper-trading/accounts` | 账户列表 |
| POST | `/paper-trading/orders` | 下单 |
| GET | `/paper-trading/orders` | 订单列表 |
| GET | `/paper-trading/positions` | 持仓列表 |
| GET | `/paper-trading/trades` | 成交记录 |
| WS | `/paper-trading/ws/account/{id}` | WebSocket 账户推送 |

## 10. Comparison（策略对比）

| Method | Path | Summary |
|--------|------|---------|
| POST | `/comparisons/` | 创建对比任务 |
| GET | `/comparisons/` | 对比任务列表 |
| GET | `/comparisons/{id}` | 对比详情 |
| DELETE | `/comparisons/{id}` | 删除对比 |
| GET | `/comparisons/{id}/metrics` | 指标对比 |
| GET | `/comparisons/{id}/equity` | 资金曲线对比 |
| GET | `/comparisons/{id}/trades` | 交易对比 |
| GET | `/comparisons/{id}/drawdown` | 回撤对比 |

## 11. Strategy Version（策略版本控制）

| Method | Path | Summary |
|--------|------|---------|
| POST | `/strategy-versions/versions` | 创建版本 |
| GET | `/strategy-versions/strategies/{id}/versions` | 版本列表 |
| GET | `/strategy-versions/versions/{id}` | 版本详情 |
| PUT | `/strategy-versions/versions/{id}` | 更新版本 |
| POST | `/strategy-versions/versions/{id}/set-default` | 设为默认版本 |
| POST | `/strategy-versions/versions/{id}/activate` | 激活版本 |
| POST | `/strategy-versions/versions/compare` | 版本对比 |
| POST | `/strategy-versions/versions/rollback` | 版本回滚 |
| POST | `/strategy-versions/branches` | 创建分支 |
| GET | `/strategy-versions/strategies/{id}/branches` | 分支列表 |
| WS | `/strategy-versions/ws/strategies/{id}` | WebSocket 版本推送 |

## 12. Realtime Data（实时数据）

| Method | Path | Summary |
|--------|------|---------|
| POST | `/realtime/ticks/subscribe` | 订阅实时行情 |
| POST | `/realtime/ticks/unsubscribe` | 取消订阅 |
| GET | `/realtime/ticks` | 获取实时报价 |
| GET | `/realtime/ticks/batch` | 批量获取报价 |
| GET | `/realtime/ticks/historical` | 获取历史报价 |
| WS | `/realtime/ws/ticks/{broker_id}` | WebSocket 行情推送 |

## 13. Monitoring（监控告警）

| Method | Path | Summary |
|--------|------|---------|
| POST | `/monitoring/rules` | 创建告警规则 |
| GET | `/monitoring/rules` | 规则列表 |
| GET | `/monitoring/rules/{id}` | 规则详情 |
| PUT | `/monitoring/rules/{id}` | 更新规则 |
| DELETE | `/monitoring/rules/{id}` | 删除规则 |
| GET | `/monitoring/` | 告警列表 |
| GET | `/monitoring/{id}` | 告警详情 |
| PUT | `/monitoring/{id}/read` | 标记已读 |
| PUT | `/monitoring/{id}/resolve` | 解决告警 |
| PUT | `/monitoring/{id}/acknowledge` | 确认告警 |
| GET | `/monitoring/statistics/summary` | 告警统计概览 |
| GET | `/monitoring/statistics/by-type` | 按类型统计 |
| WS | `/monitoring/ws/alerts` | WebSocket 告警推送 |

## 14. Market Data（行情数据）

| Method | Path | Summary |
|--------|------|---------|
| GET | `/data/kline` | 查询 K 线数据 |

## 15. Crypto Trading（加密货币交易 - Legacy）

| Method | Path | Summary |
|--------|------|---------|
| POST | `/live-trading-crypto/live/submit` | 提交加密货币实盘 |
| GET | `/live-trading-crypto/live/tasks` | 任务列表 |
| GET | `/live-trading-crypto/live/tasks/{id}` | 任务状态 |
| POST | `/live-trading-crypto/live/tasks/{id}/stop` | 停止任务 |
| GET | `/live-trading-crypto/live/tasks/{id}/data` | 交易数据 |
| WS | `/live-trading-crypto/ws/live/{id}` | WebSocket 推送 |

---

## WebSocket 端点汇总

| Path | 用途 |
|------|------|
| `/backtests/ws/backtest/{task_id}` | 回测进度实时推送 |
| `/paper-trading/ws/account/{id}` | 模拟账户实时推送 |
| `/strategy-versions/ws/strategies/{id}` | 策略版本变更推送 |
| `/realtime/ws/ticks/{broker_id}` | 实时行情推送 |
| `/monitoring/ws/alerts` | 告警实时推送 |
| `/live-trading-crypto/ws/live/{id}` | 加密货币交易推送 |

---

## 请求/响应示例

### 登录获取 Token

```bash
curl -X POST http://localhost:8001/api/v1/auth/login \
  -d "username=testuser&password=Test123456"
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### 获取策略模板列表

```bash
curl http://localhost:8001/api/v1/strategy/templates \
  -H "Authorization: Bearer <token>"
```

```json
[
  {
    "id": "ma_cross",
    "name": "均线交叉策略",
    "category": "trend",
    "description": "双均线金叉死叉策略"
  }
]
```

### 提交回测任务

```bash
curl -X POST http://localhost:8001/api/v1/backtest/run \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "ma_cross",
    "symbol": "000001.SZ",
    "start_date": "2023-01-01T00:00:00",
    "end_date": "2024-01-01T00:00:00",
    "initial_cash": 100000,
    "commission": 0.001,
    "params": {"fast_period": 5, "slow_period": 20}
  }'
```

```json
{
  "task_id": "a1b2c3d4-...",
  "status": "pending",
  "message": "Backtest task created"
}
```

### 提交参数优化任务

```bash
curl -X POST http://localhost:8001/api/v1/optimization/submit \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "ma_cross",
    "symbol": "000001.SZ",
    "start_date": "2023-01-01T00:00:00",
    "end_date": "2024-01-01T00:00:00",
    "method": "grid",
    "param_ranges": {
      "fast_period": {"min": 3, "max": 15, "step": 2},
      "slow_period": {"min": 10, "max": 40, "step": 5}
    }
  }'
```

```json
{
  "task_id": "opt-e5f6g7...",
  "status": "pending"
}
```

### 添加实盘实例

```bash
curl -X POST http://localhost:8001/api/v1/live-trading/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "ma_cross",
    "symbol": "000001.SZ",
    "broker": "simulation",
    "initial_cash": 100000
  }'
```

```json
{
  "id": "lt-h8i9j0...",
  "status": "stopped",
  "strategy_id": "ma_cross"
}
```

---

## Examples

Scripts under `examples/` show end-to-end calls:

- `examples/backend_api_quickstart.py`
- `examples/backend_api_enhanced_backtest_demo.py`
- `examples/backend_api_paper_trading_demo.py`
- `examples/backend_api_market_data_demo.py`
- `examples/backend_api_portfolio_demo.py`
- `examples/backend_api_optimization_demo.py`
- `examples/backend_api_monitoring_demo.py`
- `examples/backend_api_comparison_demo.py`
- `examples/backend_api_realtime_data_demo.py`
- `examples/backend_api_strategy_version_demo.py`
- `examples/demo_custom_strategy.py`
- `examples/demo_webserver.py`
