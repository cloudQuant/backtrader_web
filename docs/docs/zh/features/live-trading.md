# 实盘交易

## 概述

连接真实券商进行实盘交易。

## 支持的券商

| 券商 | 类型 | 地区 |
|------|------|------|
| CTP | 期货 | 中国 |
| CCXT | 加密货币交易所 | 全球 |

## 功能特性

- **多账户** - 支持多个券商账户
- **网关管理** - 可配置的连接参数
- **实时数据** - 实时市场数据流
- **订单执行** - 市价单和限价单
- **风险控制** - 持仓限制、日内限制

## API 端点

### 网关管理

```http
# 列出网关
GET /api/v1/live-trading/gateways

# 添加网关
POST /api/v1/live-trading/gateways
{
  "broker": "ctp",
  "name": "我的CTP网关",
  "config": {
    "front": "tcp://127.0.0.1:41205",
    "broker_id": "9999",
    "user_id": "your_user_id"
  }
}
```

### 实盘会话

```http
# 创建会话
POST /api/v1/live-trading/sessions
{
  "gateway_id": 1,
  "strategy_id": 1,
  "symbols": ["rb2405"]
}

# 启动会话
POST /api/v1/live-trading/sessions/{id}/start

# 停止会话
POST /api/v1/live-trading/sessions/{id}/stop
```

### 监控状态

```http
GET /api/v1/live-trading/sessions/{id}/status
```

## 风险控制

| 控制项 | 说明 |
|--------|------|
| 单笔交易限额 | 每笔订单最大数量 |
| 日内交易限额 | 每日最大订单数 |
| 最大持仓 | 最大持仓比例 |
| 自动止损 | 自动执行止损 |

## ⚠️ 重要提示

1. **谨慎使用** - 实盘交易涉及真实资金
2. **先测试** - 先在模拟交易中充分测试
3. **风险管理** - 设置适当的风险控制
4. **密切关注** - 密切监控实盘会话
