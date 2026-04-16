# 模拟交易

## 概述

模拟交易提供模拟交易环境，使用真实市场数据，让您在不承担真实风险的情况下测试策略。

## 功能特性

- **账户管理** - 多个模拟交易账户
- **订单类型** - 市价单、限价单、止损单、止盈单
- **持仓跟踪** - 实时持仓和盈亏
- **交易历史** - 完整的审计跟踪
- **WebSocket 更新** - 订单/持仓实时更新

## API 端点

### 创建会话

```http
POST /api/v1/paper-trading/sessions
Content-Type: application/json

{
  "name": "我的模拟账户",
  "initial_cash": 100000,
  "commission": 0.001
}
```

### 列出会话

```http
GET /api/v1/paper-trading/sessions
```

### 启动会话

```http
POST /api/v1/paper-trading/sessions/{id}/start
```

### 停止会话

```http
POST /api/v1/paper-trading/sessions/{id}/stop
```

### 下单

```http
POST /api/v1/paper-trading/orders
Content-Type: application/json

{
  "session_id": 1,
  "symbol": "000001.SZ",
  "direction": "long",
  "order_type": "market",
  "quantity": 100,
  "price": null
}
```

### 获取持仓

```http
GET /api/v1/paper-trading/sessions/{id}/positions
```

### 获取交易

```http
GET /api/v1/paper-trading/sessions/{id}/trades
```

## WebSocket 实时更新

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/paper-trading/{session_id}');
ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  // 处理: order_update, position_update, trade_update
};
```
