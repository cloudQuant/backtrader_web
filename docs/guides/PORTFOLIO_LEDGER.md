# Portfolio Ledger 指南

这份指南说明迭代 170 引入的独立组合账本 MVP 如何工作、它和旧 `/portfolio/*` 聚合接口有什么区别，以及当前 API/数据口径是什么。

## 为什么需要独立账本

旧组合接口：

```text
/api/v1/portfolio/*
```

主要聚合的是策略运行 / 实盘日志视角的数据。

新的组合账本接口：

```text
/api/v1/portfolio-ledger/*
```

面向的是**独立组合账户**：

- 自己创建组合
- 导入交易流水
- 计算持仓
- 回填 NAV 快照

这两条路径在迭代 170 并存，互不替代。

## 当前实现位置

- `src/backend/app/services/portfolio_ledger.py`
- `src/backend/app/api/portfolio_ledger.py`
- `src/backend/tests/test_portfolio_ledger.py`
- `src/frontend/src/api/portfolioLedger.ts`
- `src/frontend/src/views/PortfolioLedgerPage.vue`

## 当前数据模型

当前 MVP 还没有落到数据库表，先使用内存服务：

### `PortfolioLedger`

字段：

- `id`
- `user_id`
- `name`
- `base_currency`
- `source_type`
- `transactions`
- `import_keys`

### `LedgerTransaction`

字段：

- `symbol`
- `trade_type`
- `quantity`
- `price`
- `trade_date`

## 支持的来源类型

当前 `create_portfolio()` 允许：

- `manual`
- `imported`
- `broker_linked`

但当前前后端最小页面默认使用：

- `manual`

## API

### 创建组合

```http
POST /api/v1/portfolio-ledger
Content-Type: application/json

{
  "name": "核心组合",
  "base_currency": "CNY",
  "source_type": "manual"
}
```

返回：

```json
{
  "id": "...",
  "name": "核心组合",
  "base_currency": "CNY",
  "source_type": "manual"
}
```

### 导入交易

```http
POST /api/v1/portfolio-ledger/{portfolio_id}/import
Content-Type: application/json

{
  "format": "json",
  "idempotency_key": "sha256-demo",
  "transactions": [
    {
      "symbol": "RB2510",
      "trade_type": "buy",
      "quantity": 2,
      "price": 3500,
      "trade_date": "2026-05-26"
    }
  ]
}
```

返回：

```json
{
  "duplicate": false,
  "imported_count": 1
}
```

如果同一个 `idempotency_key` 重复导入，返回：

```json
{
  "duplicate": true,
  "imported_count": 0
}
```

### 查看持仓

```http
GET /api/v1/portfolio-ledger/{portfolio_id}/holdings
```

返回：

```json
{
  "items": [
    {
      "symbol": "RB2510",
      "quantity": 1,
      "cost_basis": 3600
    }
  ],
  "total": 1
}
```

当前持仓口径：

- `buy` 记正数量
- 非 `buy` 记负数量
- `cost_basis` 当前取最后一笔该 symbol 的价格

### 回填快照

```http
POST /api/v1/portfolio-ledger/{portfolio_id}/snapshots/backfill
```

返回：

```json
{
  "items": [
    {
      "date": "2026-05-26",
      "snapshot_index": 1,
      "cash_flow": -7000.0,
      "nav": 993000.0
    }
  ],
  "total": 1
}
```

当前快照口径：

- 基准起始净值固定为 `1_000_000`
- `buy` 现金流为负
- `sell` 现金流为正
- `nav = 1_000_000 + cumulative_cash_flow`

## 风险自由利率

迭代 170 已单独抽出：

- `src/backend/app/services/risk_free_rate.py`

当前组合账本服务尚未直接消费它，但后续 Sharpe / Sortino / benchmark 对比应统一接入这个服务，避免在不同模块硬编码利率。

环境变量占位：

```bash
RISK_FREE_RATE_DEFAULT=0.04
```

## 前端入口

当前最小入口：

- 路由：`/portfolio-ledger`
- 页面：`PortfolioLedgerPage.vue`

页面会执行：

1. 创建一个示例组合
2. 导入两笔示例交易
3. 拉取持仓
4. 拉取快照

## 与旧接口的兼容关系

迭代 170 要求旧接口保持可用。当前测试已验证：

```http
GET /api/v1/portfolio/overview
```

仍然返回 200 且包含 `strategy_count` 字段。

## 当前限制

- 账本仍是内存态，重启后不会保留。
- `format` 字段当前仅作为请求契约占位，导入逻辑还没有做 CSV/JSON 解析分支。
- `dividend`、`fee`、`split_adjustment` 等交易类型尚未细化口径。
- 绩效归因、VaR/CVaR、benchmark metrics 还没有直接接入账本页面。
