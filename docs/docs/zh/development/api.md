# API 参考

## 核心 API 模块

| 模块 | 端点前缀 | 说明 |
|------|----------|------|
| 认证 | `/api/v1/auth` | JWT 认证、注册、登录 |
| 策略 | `/api/v1/strategy` | CRUD、模板 |
| 回测 | `/api/v1/backtests` | **推荐** 增强回测 |
| 分析 | `/api/v1/analytics` | 回测数据分析 |
| 优化 | `/api/v1/optimization` | 参数优化 |
| 模拟交易 | `/api/v1/paper-trading` | 模拟账户 |
| 实盘交易 | `/api/v1/live-trading` | 实盘账户 |
| 行情数据 | `/api/v1/quote`, `/api/v1/realtime` | 行情数据 |
| 监控告警 | `/api/v1/monitoring` | 告警规则 |
| 工作区 | `/api/v1/workspace` | 工作区管理 |

## 认证

除非标记为公开，否则所有端点都需要 JWT 认证。

### 公开端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 注册用户 |
| POST | `/api/v1/auth/login` | 登录获取令牌 |

### 受保护端点

包含 `Authorization: Bearer <token>` 头。

## WebSocket 端点

| 端点 | 说明 |
|------|------|
| `/ws/backtest/{task_id}` | 回测进度 |
| `/ws/paper-trading/{session_id}` | 模拟交易更新 |
| `/ws/live-trading/{session_id}` | 实盘交易更新 |
| `/ws/realtime/{symbol}` | 实时行情 |

## 废弃说明

> ⚠️ 旧版端点已废弃。请迁移到推荐的端点：

| 旧版 | 推荐 |
|------|------|
| `/api/v1/backtest/*` | `/api/v1/backtests/*` |
| `/api/v1/live-trading-crypto/*` | `/api/v1/live-trading/*` |

## 限流

默认限流：
- **认证用户**：100 请求/分钟
- **公开端点**：20 请求/分钟

## 错误响应

```json
{
  "detail": "错误信息",
  "code": "ERROR_CODE"
}
```

| 状态码 | 说明 |
|--------|------|
| 400 | 错误请求 |
| 401 | 未授权 |
| 403 | 禁止访问 |
| 404 | 未找到 |
| 422 | 验证错误 |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |
