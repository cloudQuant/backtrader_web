# 策略管理

## 概述

Backtrader Web 提供全面的策略管理功能，支持类似 Git 的版本控制。

## 内置模板

118 个内置策略模板，包括：

### 趋势跟踪
- 双均线
- MACD
- 海龟交易法
- Supertrend

### 均值回归
- 布林带反转
- KDJ
- RSI
- 随机指标

### 套利
- 期现套利
- 跨期套利

### 期权
- 恐慌指数
- 看跌看涨比

### 高频策略
- R-Breaker
- Dual Thrust
- 菲阿里四价

## API 端点

### 策略 CRUD

```http
# 创建策略
POST /api/v1/strategy/
Content-Type: application/json

{
  "name": "我的策略",
  "description": "自定义均值回归策略",
  "code": "...",
  "parameters": {"period": 20}
}

# 列出策略
GET /api/v1/strategy/

# 获取策略
GET /api/v1/strategy/{id}

# 更新策略
PUT /api/v1/strategy/{id}

# 删除策略
DELETE /api/v1/strategy/{id}
```

### 模板

```http
GET /api/v1/strategy/templates
```

## 版本控制

### 创建版本

```http
POST /api/v1/strategy-versions/versions
{
  "strategy_id": 1,
  "version_name": "v1.0",
  "message": "初始版本"
}
```

### 列出版本

```http
GET /api/v1/strategy-versions/strategies/{strategy_id}/versions
```

### 对比版本

```http
POST /api/v1/strategy-versions/versions/compare
{
  "strategy_id": 1,
  "version_a": "v1.0",
  "version_b": "v1.1"
}
```

### 回滚

```http
POST /api/v1/strategy-versions/versions/rollback
{
  "strategy_id": 1,
  "target_version": "v1.0"
}
```

## 分支管理

```http
# 创建分支
POST /api/v1/strategy-versions/branches
{
  "strategy_id": 1,
  "branch_name": "experiment",
  "base_version": "v1.0"
}
```
