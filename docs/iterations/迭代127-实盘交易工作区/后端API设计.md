# 迭代127 - 策略交易工作区 - 后端API设计

> **文档状态**: 优化版  
> **最后更新**: 2026-04-13  
> **核心策略**: 扩展现有 workspace API，新增交易专属路由组

## 1. API 设计原则

1. **扩展而非新建** — 在现有 `/api/v1/workspace` 路由组上扩展交易能力
2. **类型过滤** — 通过 `workspace_type` 查询参数区分策略研究和策略交易
3. **复用CRUD** — 工作区和策略单元的CRUD直接复用现有接口
4. **新增交易组** — 在 `/api/v1/workspace/{id}/trading/` 下新增交易专属端点

## 2. 现有接口扩展

### 2.1 工作区列表（扩展过滤参数）

```
GET /api/v1/workspace/
```

**新增查询参数:**

| 参数 | 类型 | 说明 |
|------|------|------|
| `workspace_type` | string | 可选，`research` / `trading`，不传则返回全部 |

**响应示例:**
```json
{
  "workspaces": [
    {
      "id": "ws-001",
      "name": "CTA策略实盘",
      "workspace_type": "trading",
      "trading_config": { "default_trading_mode": "live" },
      "status": "running",
      "unit_count": 5,
      "running_count": 3,
      "created_at": "2026-04-13T10:00:00"
    }
  ]
}
```

### 2.2 创建工作区（扩展交易类型）

```
POST /api/v1/workspace/
```

**请求体扩展:**
```json
{
  "name": "CTA策略实盘",
  "description": "商品期货CTA策略组合",
  "workspace_type": "trading",
  "trading_config": {
    "default_trading_mode": "simulate",
    "default_gateway_preset_id": "manual-ctp-089763"
  }
}
```

### 2.3 创建策略单元（扩展交易字段）

```
POST /api/v1/workspace/{workspace_id}/units
```

**请求体扩展:**
```json
{
  "strategy_id": "live/my_cta_strategy",
  "strategy_name": "CTA动量策略",
  "symbol": "rb2410",
  "symbol_name": "螺纹钢2410",
  "timeframe": "15m",
  "group_name": "黑色系",
  "trading_mode": "live",
  "gateway_config": {
    "preset_id": "manual-ctp-089763",
    "provider": "ctp",
    "exchange_type": "futures"
  },
  "data_config": { ... },
  "unit_settings": { ... },
  "params": { ... }
}
```

## 3. 新增交易专属接口

### 3.1 启动策略单元交易

```
POST /api/v1/workspace/{workspace_id}/trading/start
```

**请求体:**
```json
{
  "unit_ids": ["unit-001", "unit-002"],
  "parallel": false
}
```

**响应:**
```json
{
  "started": ["unit-001", "unit-002"],
  "failed": [],
  "errors": {}
}
```

**处理逻辑:**
1. 校验单元存在且 `lock_running == false`
2. 根据 `trading_mode` 调用对应服务：
   - `simulate` → `PaperTradingService.create_account()` + `submit_order()`
   - `live` → `LiveTradingService.submit_live_strategy()`
3. 更新 `StrategyUnit.trading_instance_id`
4. 在 `TradingRuntimeManager` 中初始化运行时状态
5. 更新 `StrategyUnit.run_status = 'running'`

### 3.2 停止策略单元交易

```
POST /api/v1/workspace/{workspace_id}/trading/stop
```

**请求体:**
```json
{
  "unit_ids": ["unit-001", "unit-002"]
}
```

**响应:**
```json
{
  "stopped": ["unit-001", "unit-002"],
  "failed": [],
  "errors": {}
}
```

**处理逻辑:**
1. 校验单元存在且 `lock_running == false`
2. 根据 `trading_mode` 调用对应服务停止：
   - `simulate` → `SimulationStore.stopInstance()`
   - `live` → `LiveTradingService.stop_live_strategy()`
3. 持久化最终 `trading_snapshot`
4. 更新 `run_status = 'idle'`
5. 清理 `TradingRuntimeManager` 中的运行时状态

### 3.3 获取交易运行时状态

```
GET /api/v1/workspace/{workspace_id}/trading/status
```

**查询参数:**

| 参数 | 类型 | 说明 |
|------|------|------|
| `unit_ids` | string | 可选，逗号分隔的单元ID，不传则返回所有运行中单元 |

**响应:**
```json
{
  "statuses": [
    {
      "unit_id": "unit-001",
      "is_running": true,
      "trading_mode": "live",
      "long_position": 10,
      "short_position": 0,
      "daily_pnl": 2580.50,
      "position_pnl": 15200.00,
      "total_pnl": 128500.00,
      "latest_price": 4520.00,
      "price_change_pct": 1.25,
      "long_market_value": 452000.00,
      "short_market_value": 0.00,
      "leverage": 0.45,
      "max_drawdown_rate": 3.25,
      "bar_count": 12500,
      "trading_days": 45,
      "lock_trading": false,
      "lock_running": false,
      "error": null,
      "started_at": "2026-04-13T09:00:00",
      "last_update": "2026-04-13T10:30:15"
    }
  ]
}
```

> **实现说明**: 从 `TradingRuntimeManager` 内存读取，不查数据库。

### 3.4 锁定/解锁单元

```
POST /api/v1/workspace/{workspace_id}/trading/lock
```

**请求体:**
```json
{
  "unit_ids": ["unit-001", "unit-002"],
  "lock_type": "trading",
  "locked": true
}
```

| lock_type | 说明 |
|-----------|------|
| `trading` | 锁定交易：阻止新订单下发 |
| `running` | 锁定运行：阻止启动/停止操作 |
| `all` | 同时锁定交易和运行 |

**响应:**
```json
{
  "updated": ["unit-001", "unit-002"],
  "message": "已锁定交易"
}
```

### 3.5 自动交易调度配置（P1）

#### 获取配置

```
GET /api/v1/workspace/{workspace_id}/trading/auto-config
```

**响应:**
```json
{
  "enabled": true,
  "buffer_minutes": 15,
  "scope": "all",
  "sessions": [
    { "name": "日盘", "open": "09:00", "close": "15:00" },
    { "name": "夜盘", "open": "21:00", "close": "23:00" }
  ]
}
```

#### 更新配置

```
PUT /api/v1/workspace/{workspace_id}/trading/auto-config
```

**请求体:**
```json
{
  "enabled": true,
  "buffer_minutes": 15,
  "scope": "live",
  "sessions": [
    { "name": "日盘", "open": "09:00", "close": "15:00" },
    { "name": "夜盘", "open": "21:00", "close": "23:00" }
  ]
}
```

#### 获取调度计划

```
GET /api/v1/workspace/{workspace_id}/trading/auto-schedule
```

**响应:**
```json
{
  "schedule": [
    {
      "session": "日盘",
      "start": "08:45 (buffer 15min)",
      "stop": "15:15 (buffer 15min)"
    },
    {
      "session": "夜盘",
      "start": "20:45 (buffer 15min)",
      "stop": "23:15 (buffer 15min)"
    }
  ]
}
```

### 3.6 头寸管理器

```
GET /api/v1/workspace/{workspace_id}/trading/positions
```

**响应:**
```json
{
  "positions": [
    {
      "unit_id": "unit-001",
      "unit_name": "螺纹钢CTA",
      "symbol": "rb2410",
      "symbol_name": "螺纹钢2410",
      "trading_mode": "live",
      "long_position": 10,
      "short_position": 0,
      "avg_price": 4480.00,
      "latest_price": 4520.00,
      "position_pnl": 4000.00,
      "market_value": 452000.00
    }
  ],
  "total_long_value": 452000.00,
  "total_short_value": 0.00,
  "total_pnl": 4000.00
}
```

### 3.7 交易日汇总（P1）

```
GET /api/v1/workspace/{workspace_id}/trading/daily-summary
```

**查询参数:**

| 参数 | 类型 | 说明 |
|------|------|------|
| `unit_id` | string | 可选，指定单元 |
| `start_date` | string | 可选，起始日期 YYYY-MM-DD |
| `end_date` | string | 可选，结束日期 YYYY-MM-DD |

**响应:**
```json
{
  "summaries": [
    {
      "trading_date": "2026-04-12",
      "daily_pnl": 5200.00,
      "trade_count": 8,
      "cumulative_pnl": 126000.00,
      "max_drawdown": 2.8
    }
  ]
}
```

## 4. WebSocket 增强（P1）

### 4.1 交易状态实时推送

```
WS /api/v1/ws/trading/{workspace_id}
```

**推送消息格式:**
```json
{
  "type": "trading_status_update",
  "data": {
    "unit_id": "unit-001",
    "long_position": 10,
    "daily_pnl": 2600.00,
    "latest_price": 4522.00,
    "price_change_pct": 1.30,
    "last_update": "2026-04-13T10:30:20"
  }
}
```

```json
{
  "type": "order_fill",
  "data": {
    "unit_id": "unit-001",
    "symbol": "rb2410",
    "side": "buy",
    "size": 5,
    "price": 4520.00,
    "time": "2026-04-13T10:30:15"
  }
}
```

```json
{
  "type": "unit_status_change",
  "data": {
    "unit_id": "unit-001",
    "old_status": "idle",
    "new_status": "running"
  }
}
```

## 5. 接口完整清单

### 5.1 复用接口（已有，本迭代扩展参数）

| 方法 | 路径 | 说明 | 变更 |
|------|------|------|------|
| GET | `/workspace/` | 工作区列表 | 新增 `workspace_type` 过滤 |
| POST | `/workspace/` | 创建工作区 | 新增 `workspace_type`、`trading_config` |
| GET | `/workspace/{id}` | 工作区详情 | 返回交易配置 |
| PUT | `/workspace/{id}` | 更新工作区 | 支持更新 `trading_config` |
| DELETE | `/workspace/{id}` | 删除工作区 | 无变更 |
| POST | `/workspace/{id}/units` | 创建单元 | 新增 `trading_mode`、`gateway_config` |
| PUT | `/workspace/{id}/units/{uid}` | 更新单元 | 支持交易字段 |
| DELETE | `/workspace/{id}/units/bulk-delete` | 批量删除 | 无变更 |
| POST | `/workspace/{id}/units/reorder` | 排序 | 无变更 |
| PUT | `/workspace/{id}/units/rename` | 重命名 | 无变更 |
| PUT | `/workspace/{id}/units/group-rename` | 组名重命名 | 无变更 |
| POST | `/workspace/{id}/run` | 运行单元 | 交易工作区重定向到交易启动 |

### 5.2 新增接口

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| POST | `/workspace/{id}/trading/start` | 启动交易 | P0 |
| POST | `/workspace/{id}/trading/stop` | 停止交易 | P0 |
| GET | `/workspace/{id}/trading/status` | 运行时状态 | P0 |
| POST | `/workspace/{id}/trading/lock` | 锁定/解锁 | P1 |
| GET | `/workspace/{id}/trading/auto-config` | 获取自动交易配置 | P1 |
| PUT | `/workspace/{id}/trading/auto-config` | 更新自动交易配置 | P1 |
| GET | `/workspace/{id}/trading/auto-schedule` | 获取调度计划 | P1 |
| GET | `/workspace/{id}/trading/positions` | 头寸管理器 | P1 |
| GET | `/workspace/{id}/trading/daily-summary` | 交易日汇总 | P1 |
| WS | `/ws/trading/{id}` | 实时推送 | P1 |

## 6. 后端服务层设计

### 6.1 新增 TradingWorkspaceService

文件: `src/backend/app/services/trading_workspace_service.py`

```python
class TradingWorkspaceService:
    """策略交易工作区编排服务"""
    
    def __init__(self):
        self.runtime_manager = TradingRuntimeManager()
    
    # --- 启停编排 ---
    async def start_units(
        self, workspace_id: str, unit_ids: list[str], parallel: bool = False
    ) -> dict:
        """启动策略单元交易"""
        # 1. 加载单元，校验 lock_running
        # 2. 按 trading_mode 分组
        # 3. simulate → PaperTradingService.create_account + run
        # 4. live → LiveTradingService.submit_live_strategy
        # 5. 更新 trading_instance_id, run_status
        # 6. 初始化 TradingRuntimeManager 状态
    
    async def stop_units(
        self, workspace_id: str, unit_ids: list[str]
    ) -> dict:
        """停止策略单元交易"""
        # 1. 校验 lock_running
        # 2. 调用对应服务停止
        # 3. 持久化最终快照
        # 4. 清理运行时状态
    
    # --- 锁定管理 ---
    async def lock_units(
        self, workspace_id: str, unit_ids: list[str],
        lock_type: str, locked: bool
    ) -> list[str]:
        """锁定/解锁单元"""
    
    # --- 状态查询 ---
    async def get_trading_status(
        self, workspace_id: str, unit_ids: list[str] | None = None
    ) -> list[dict]:
        """从 TradingRuntimeManager 获取运行时状态"""
    
    # --- 自动交易调度 ---
    async def get_auto_config(self, workspace_id: str) -> dict
    async def update_auto_config(self, workspace_id: str, config: dict) -> dict
    async def get_auto_schedule(self, workspace_id: str) -> list[dict]
    
    # --- 头寸管理 ---
    async def get_positions(self, workspace_id: str) -> dict
    
    # --- 定时任务 ---
    async def persist_snapshots(self):
        """定期将运行时状态持久化到 trading_snapshot"""
    
    async def check_auto_trading_schedule(self):
        """检查自动交易调度，按时启停"""
```

### 6.2 扩展 WorkspaceService

在现有 `workspace_service.py` 中扩展：

```python
# 新增方法
async def create_workspace(self, user_id, data) -> Workspace:
    # 支持 workspace_type='trading'
    
async def list_workspaces(self, user_id, workspace_type=None) -> list:
    # 支持按 workspace_type 过滤

async def create_unit(self, workspace_id, data) -> StrategyUnit:
    # 支持 trading_mode, gateway_config 字段
```

## 7. 错误处理

| 场景 | HTTP状态码 | 错误消息 |
|------|-----------|---------|
| 启动已锁定运行的单元 | 409 Conflict | "单元已锁定运行，请先解锁" |
| 启动已运行中的单元 | 409 Conflict | "单元已在运行中" |
| 实盘单元缺少网关配置 | 422 | "实盘交易单元必须配置网关" |
| 网关连接失败 | 502 | "网关连接失败: {detail}" |
| 交易工作区不存在 | 404 | "工作区不存在" |
| 单元不属于该工作区 | 404 | "单元不存在" |
| 锁定交易状态下下单 | 403 Forbidden | "交易已锁定" |
