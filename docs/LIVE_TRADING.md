# 实盘交易指南

本文档介绍 Backtrader Web 的实盘交易功能。

## 1. 概述

实盘交易模块基于 Backtrader 架构，通过 Cerebro + Store + Broker 模式对接多个交易所和券商，支持加密货币（CCXT）和国内期货（CTP）。

### 1.1 支持的交易所/券商

| 类型 | 交易所 | 协议 |
|------|--------|------|
| 加密货币 | Binance, OKEx, Huobi | CCXT |
| 国内期货 | 中金所, 上期所, 大商所, 郑商所 | CTP |
| 模拟交易 | 内置模拟环境 | Paper Trading |

## 2. 快速开始

### 2.1 访问实盘页面

登录后，通过侧边栏点击「实盘交易」或直接访问 `/live-trading`。

### 2.2 基本流程

1. **添加策略** — 点击「添加策略」选择要实盘运行的策略
2. **配置参数** — 设置交易参数（资金、标的、策略参数）
3. **启动运行** — 点击启动，策略开始执行
4. **监控状态** — 实时查看订单、持仓、盈亏
5. **停止策略** — 需要时可随时停止

## 3. API 接口

### 3.1 实例管理

```bash
# 列出所有实盘实例
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/live-trading/

# 添加实盘实例
curl -X POST http://localhost:8000/api/v1/live-trading/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "002_dual_ma",
    "params": {
      "symbol": "000001.SZ",
      "short_period": 5,
      "long_period": 20
    }
  }'

# 获取实例详情
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/live-trading/{instance_id}

# 删除实例
curl -X DELETE -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/live-trading/{instance_id}
```

### 3.2 启停控制

```bash
# 启动实例
curl -X POST -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/live-trading/{instance_id}/start

# 停止实例
curl -X POST -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/live-trading/{instance_id}/stop
```

### 3.3 查询订单和持仓

```bash
# 查询订单
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/live-trading/{instance_id}/orders

# 查询持仓
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/live-trading/{instance_id}/positions
```

## 4. 投资组合管理

实盘实例可通过投资组合页面 (`/portfolio`) 汇总查看。

### 4.1 组合概览

| 指标 | 说明 |
|------|------|
| 组合总资产 | 所有策略的资产总和 |
| 总盈亏 | 所有策略的盈亏汇总 |
| 策略数量 | 运行中的策略数 |
| 胜率 | 各策略的综合胜率 |

### 4.2 组合 API

```bash
# 组合概览
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/portfolio/overview

# 当前持仓
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/portfolio/positions

# 交易记录
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/portfolio/trades

# 资金曲线
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/portfolio/equity-curve

# 资产配置
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/portfolio/allocation
```

## 5. 批量操作

实盘页面支持批量启停：

- **一键启动** — 启动所有已停止的策略实例
- **一键停止** — 停止所有运行中的策略实例

## 6. 监控告警

### 6.1 告警规则

通过监控 API 设置告警规则：

```bash
# 创建告警规则
curl -X POST http://localhost:8000/api/v1/monitoring/alerts \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "最大回撤告警",
    "condition": "max_drawdown > 10",
    "action": "notify"
  }'
```

### 6.2 WebSocket 实时推送

```javascript
// 连接 WebSocket 获取实时更新
const ws = new WebSocket('ws://localhost:8000/api/v1/realtime/ws');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('实时数据:', data);
};
```

## 7. 风险提示

1. **实盘交易有真实资金风险**，请先在模拟环境充分测试
2. 确保网络连接稳定，避免因网络中断导致无法执行止损
3. 设置合理的仓位管理和止损规则
4. 定期检查策略运行状态和日志
5. 不建议在未经回测验证的策略上直接实盘

## 8. 相关文档

- [策略开发](STRATEGY_DEVELOPMENT.md) — 编写交易策略
- [回测指南](BACKTEST_GUIDE.md) — 回测验证策略
- [参数优化](OPTIMIZATION.md) — 优化策略参数
- [运维手册](OPERATIONS.md) — 系统监控和维护
