# Data Connector Registry 指南

这份指南说明迭代 170 引入的通用数据连接器注册中心如何工作、当前 MVP 提供了哪些 API，以及它与既有 AkShare 数据治理能力如何兼容。

## 当前目标

Data Connector Registry 解决三个问题：

- **统一 provider 元数据**：把 AkShare、Yahoo、FRED、CoinGecko、CBOE、CFTC、DBnomics、FMP 的 provider 信息统一入库。
- **统一 endpoint 元数据**：每个 endpoint 都记录 `function_path`、`params_schema`、`auth_type`、`rate_limit`、`cache_ttl_sec`、`target_table`、`incremental_sync_key`。
- **统一预览与任务入口**：先通过 preview 查看标准化输出，再创建 ingest job。

当前实现入口在：

- `src/backend/app/models/data_governance.py`
- `src/backend/app/services/data_connectors/executor.py`
- `src/backend/app/services/data_connectors/registry.py`
- `src/backend/app/api/data_governance.py`

## Provider 种子

当前 `DataGovernanceService.bootstrap()` 会确保以下 provider 存在：

| provider_id | 名称 | category | auth_type | api_key_env |
|---|---|---|---|---|
| `akshare` | AkShare | `china_market` | `none` | - |
| `yahoo` | Yahoo Finance | `global_market` | `none` | - |
| `fred` | FRED | `macro` | `api_key` | `FRED_API_KEY` |
| `coingecko` | CoinGecko | `crypto` | `none` | - |
| `cboe` | CBOE | `options` | `none` | - |
| `cftc` | CFTC | `futures` | `none` | - |
| `dbnomics` | DBnomics | `macro` | `none` | - |
| `fmp` | FMP | `fundamental` | `api_key` | `FMP_API_KEY` |

## Endpoint 种子

当前种子 endpoint 包含：

| provider | endpoint |
|---|---|
| `yahoo` | `quote`, `history` |
| `fred` | `DGS10`, `macro_series` |
| `coingecko` | `coin_price` |
| `cboe` | `option_chain` |
| `cftc` | `commitments_of_traders` |
| `dbnomics` | `dataset_series` |
| `fmp` | `company_profile` |

所有种子 endpoint 默认：

- 使用 `incremental_sync_key="date"`
- 默认 `params_schema` 为 `symbol` 可选字符串
- `target_database` 为 `akshare_data`

## AkShare 兼容层

当前实现不会删除旧的 AkShare 管理能力，而是做了两层兼容：

- **接口迁移**：`DataGovernanceService._migrate_akshare_interfaces()` 会把 `ak_data_interfaces` 中已有接口复制为 `dg_endpoints`，并记录 `legacy_interface_name`。
- **SQLite 兼容视图**：在 SQLite 下创建 `ak_data_interfaces_compat` view，避免旧查询直接失效。

这意味着：

- 旧 `/api/v1/data/*` 与 AkShare 相关能力继续保留。
- 新 `/api/v1/data-governance/*` 可以统一查看 AkShare 与新增 provider。

## 标准输出结构

`DataConnectorExecutor.preview()` 的标准输出为：

```json
{
  "columns": ["symbol", "date", "open", "close", "volume"],
  "rows": [
    {"symbol": "RB2510", "date": "2026-05-26", "open": 100.0, "close": 101.5, "volume": 1000}
  ],
  "metadata": {"function_path": "yahoo.quote"},
  "source_timestamp": "2026-05-26T00:00:00+00:00",
  "provider_latency_ms": 12,
  "quality_warnings": [],
  "provider_id": "yahoo",
  "endpoint_name": "quote"
}
```

当前 MVP 支持三类 payload 归一化：

- `list[dict]`
- `dict`
- 带 `to_dict(orient="records")` 的对象（例如 DataFrame 风格对象）

## 后端 API

### Bootstrap

```http
POST /api/v1/data-governance/bootstrap
```

返回：

```json
{
  "providers": 8,
  "seed_endpoints": 9,
  "akshare_migrated_endpoints": 1
}
```

### Provider 列表

```http
GET /api/v1/data-governance/providers
```

返回：

```json
{
  "items": [
    {
      "id": "...",
      "provider_id": "fred",
      "name": "FRED",
      "category": "macro",
      "auth_type": "api_key",
      "api_key_env": "FRED_API_KEY",
      "rate_limit": 60,
      "is_active": true
    }
  ],
  "total": 8
}
```

### Endpoint 列表

```http
GET /api/v1/data-governance/endpoints
GET /api/v1/data-governance/endpoints?provider_id=akshare
```

### Endpoint 预览

```http
POST /api/v1/data-governance/endpoints/{endpoint_id}/preview
Content-Type: application/json

{
  "params": {
    "symbol": "RB2510"
  }
}
```

### 创建任务

```http
POST /api/v1/data-governance/endpoints/{endpoint_id}/jobs
Content-Type: application/json

{
  "params": {
    "symbol": "RB2510"
  }
}
```

当前 MVP 中，任务创建会先做一次 preview，然后以 `completed` 状态写入 `dg_ingest_jobs`，并记录 `row_count`。

## 前端入口

当前最小前端入口：

- 路由：`/data/governance`
- 页面：`src/frontend/src/views/data/DataGovernancePage.vue`
- API wrapper：`src/frontend/src/api/dataGovernance.ts`

该页会执行：

1. `bootstrap()`
2. `listProviders()`
3. `listEndpoints()`

## 环境变量

如果启用需要 key 的 provider，至少需要以下占位变量：

```bash
FRED_API_KEY=replace-with-fred-api-key
FMP_API_KEY=replace-with-fmp-api-key
```

## 当前限制

- 还没有 provider / endpoint 的完整 CRUD UI。
- `create_job()` 当前是同步 preview 驱动的轻量任务，而非后台队列。
- 兼容视图当前只在 SQLite 下创建 `ak_data_interfaces_compat`，MySQL/PostgreSQL 的兼容迁移还需要后续 Alembic 收口。
- `normalization_profile`、`quality_profile` 已入模，但当前 MVP 仍以空字典为主。
