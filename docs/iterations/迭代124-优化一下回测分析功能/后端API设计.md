# 迭代124 - 后端 API 设计

> **文档状态**: 已对齐优化版实施计划  
> **最后更新**: 2026-03-15  
> **核心变更**: API 标注 P0/P1/P2 优先级；WebSocket 采用轮询优先+增强方案；结果读取改为引用模式

## 1. 新增路由注册

在 `src/backend/app/api/router.py` 中新增:

```python
from app.api.workspace_api import router as workspace_router
api_router.include_router(workspace_router, prefix="/workspace", tags=["Workspace"])
```

## 2. 工作区 CRUD API [P0]

**文件**: `src/backend/app/api/workspace_api.py`

### 2.1 工作区管理

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| POST | `/` | 创建工作区 | P0 |
| GET | `/` | 获取工作区列表 | P0 |
| GET | `/{workspace_id}` | 获取工作区详情 | P0 |
| PUT | `/{workspace_id}` | 更新工作区 | P0 |
| DELETE | `/{workspace_id}` | 删除工作区 | P0 |
| PUT | `/{workspace_id}/settings` | 更新工作区全局设置（并行线程等） | P1 |

> **注意**: 工作区列表响应中的 `status` 字段由后端从子单元聚合计算，不直接读库。

#### POST `/` — 创建工作区

**请求体:**
```json
{
  "name": "黄金策略研究",
  "description": "au000 多策略多周期回测"
}
```

**响应:**
```json
{
  "id": "uuid-xxx",
  "name": "黄金策略研究",
  "description": "au000 多策略多周期回测",
  "status": "idle",
  "settings": { "serial_threads": 32, "parallel_threads": 32, "parallel_task_threads": 1 },
  "unit_count": 0,
  "created_at": "2026-03-15T15:00:00",
  "updated_at": "2026-03-15T15:00:00"
}
```

#### GET `/` — 工作区列表

**查询参数:**
- `page` (int, default=1)
- `page_size` (int, default=20)
- `status` (str, optional)

**响应:**
```json
{
  "items": [
    {
      "id": "uuid-xxx",
      "name": "黄金策略研究",
      "description": "...",
      "status": "idle",
      "unit_count": 6,
      "completed_count": 4,
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20
}
```

## 3. 策略单元 API [P0]

### 3.1 策略单元 CRUD

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| POST | `/{workspace_id}/units` | 创建策略单元（支持批量） | P0 |
| GET | `/{workspace_id}/units` | 获取工作区内策略单元列表 | P0 |
| GET | `/{workspace_id}/units/{unit_id}` | 获取策略单元详情 | P0 |
| PUT | `/{workspace_id}/units/{unit_id}` | 更新策略单元 | P0 |
| DELETE | `/{workspace_id}/units/{unit_id}` | 删除策略单元 | P0 |

### 3.2 批量操作

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| POST | `/{workspace_id}/units/batch-delete` | 批量删除策略单元 | P0 |
| POST | `/{workspace_id}/units/import` | 导入策略单元（先只支持 JSON） | P1 |
| GET | `/{workspace_id}/units/{unit_id}/export` | 导出策略单元 | P1 |
| PUT | `/{workspace_id}/units/reorder` | 批量调整排序 | P0 |
| PUT | `/{workspace_id}/units/rename-group` | 批量组名重命名 | P1 |
| PUT | `/{workspace_id}/units/{unit_id}/rename` | 单元重命名 | P1 |

> **范围控制**: 导入导出先只支持 JSON，XML 导入顺延至 P2。

### 3.3 数据源与设置 [P0]

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| PUT | `/{workspace_id}/units/{unit_id}/data-config` | 更新数据源设置 | P0 |
| PUT | `/{workspace_id}/units/{unit_id}/unit-settings` | 更新策略单元设置 | P0 |
| PUT | `/{workspace_id}/units/{unit_id}/params` | 更新策略参数 | P0 |
| PUT | `/{workspace_id}/units/{unit_id}/optimization-config` | 更新优化参数设置 | P0 |

#### POST `/{workspace_id}/units` — 创建策略单元

**请求体（批量模式）:**
```json
{
  "create_mode": "batch",
  "group_name": "myunit",
  "symbols": [
    { "code": "au000", "name": "黄金加权0" }
  ],
  "strategy_id": "www_2021_bowling",
  "timeframe": "15m",
  "timeframe_n": 3,
  "data_config": {
    "range_type": "date",
    "start_date": "2025/03/15 14:25:28",
    "end_date": "2026/03/15 14:25:28",
    "use_end_date": true,
    "adjust_type": "none",
    "split_type": "natural",
    "data_range": "all"
  },
  "add_formulas": false,
  "split_as_independent": false
}
```

**响应:**
```json
{
  "created": [
    {
      "id": "uuid-unit-1",
      "group_name": "myunit",
      "strategy_id": "www_2021_bowling",
      "strategy_name": "www_2021_bowling",
      "symbol": "au000",
      "symbol_name": "黄金加权0",
      "timeframe": "15m",
      "sort_order": 1,
      "run_status": "idle",
      "created_at": "..."
    }
  ],
  "count": 1
}
```

## 4. 运行管理 API [P0]

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| POST | `/{workspace_id}/run` | 运行选中策略单元 | P0 |
| POST | `/{workspace_id}/run-parallel` | 并行运行选中策略单元 | P0 |
| POST | `/{workspace_id}/stop` | 终止选中策略单元 | P0 |
| POST | `/{workspace_id}/reload-strategy` | 重新加载策略 | P1 |
| GET | `/{workspace_id}/run-status` | 获取运行状态（轮询接口，WebSocket增强） | P0 |

> **并发控制**: 并行运行需增加并发上限（建议默认4，可通过工作区 settings 配置）。

#### POST `/{workspace_id}/run` — 运行选中策略单元

**请求体:**
```json
{
  "unit_ids": ["uuid-unit-1", "uuid-unit-2"],
  "mode": "serial"
}
```

**响应:**
```json
{
  "message": "已提交 2 个策略单元运行任务",
  "tasks": [
    { "unit_id": "uuid-unit-1", "task_id": "task-xxx-1" },
    { "unit_id": "uuid-unit-2", "task_id": "task-xxx-2" }
  ]
}
```

**执行流程:**
1. 遍历 `unit_ids`，为每个单元组装 `BacktestRequest`（映射规则见实施计划阶段0）
2. 调用 `BacktestService.run_backtest()` 复用现有执行引擎
3. 更新 `strategy_units.run_status` / `last_task_id`
4. 回测完成后，提取关键指标写入 `unit_backtest_results.metrics_snapshot`（引用模式，不复制全量数据）
5. 更新 `strategy_units.run_count` / `last_run_time`
6. 前端通过轮询 `GET /run-status` 刷新状态（WebSocket 增强版后续补充）

## 5. 优化 API [P0 基础 / P1 增强]

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| POST | `/{workspace_id}/units/{unit_id}/optimize` | 启动参数优化 | P0 |
| GET | `/{workspace_id}/units/{unit_id}/optimize/progress` | 优化进度 | P0 |
| GET | `/{workspace_id}/units/{unit_id}/optimize/results` | 优化结果 | P0 |
| POST | `/{workspace_id}/units/{unit_id}/optimize/cancel` | 取消优化 | P0 |
| POST | `/{workspace_id}/units/{unit_id}/optimize/apply-best` | 应用最佳参数 | P1 |

> **复用边界**: 优化执行完全委托给现有 `param_optimization_service`，工作区 API 只负责配置转换和结果引用。

#### POST `/{workspace_id}/units/{unit_id}/optimize` — 启动优化

**请求体:**
```json
{
  "objective": "sharpe_max",
  "max_display": 5000,
  "initial_cash": 1000000,
  "calculation_method": "geometric",
  "param_layers": [
    {
      "params": [
        {
          "param_name": "y",
          "optimize_setting": "equal_diff:100,2000,50"
        },
        {
          "param_name": "m",
          "optimize_setting": "equal_diff:1,4,0.5"
        }
      ]
    }
  ],
  "n_workers": 4
}
```

**执行流程:**
1. 解析 `optimize_setting` 为 `param_ranges`
2. 调用 `submit_optimization()` 复用现有优化引擎
3. 记录 `optimization_task_id` 到 `unit_optimization_results`
4. 完成后提取 `best_params` + `best_metrics` 写入摘要（引用模式）
5. 完整结果列表通过 `task_id` 从现有优化任务读取

#### GET `/{workspace_id}/units/{unit_id}/optimize/results` — 优化结果

**响应（参考TBQuant参数优化结果表）:**
```json
{
  "unit_id": "uuid-unit-1",
  "status": "completed",
  "total_combinations": 266,
  "completed": 266,
  "stat_start_date": "2025/08/14",
  "stat_end_date": "2026/03/13",
  "rows": [
    {
      "rank": 1,
      "params": { "y": 10, "m": 80 },
      "initial_cash": 1000000,
      "net_value": 1208160,
      "net_profit": 356530.70,
      "annual_return": 35.06,
      "max_leverage": 0.0,
      "max_market_value": 120964.66,
      "max_drawdown_value": 0.87,
      "max_drawdown_rate": 1.4035,
      "sharpe_ratio": 1.4026,
      "adjusted_return_risk": 6.3265,
      "trade_count": 77,
      "win_rate": 42.86,
      "avg_profit": 0.0658,
      "avg_profit_rate": 3977.37,
      "total_profit": 615826.36,
      "total_loss": -287245.66,
      "profit_loss_ratio": 2.9979,
      "profit_factor": 2.1450,
      "profit_rate_factor": 0.0,
      "win_odds": 0.0,
      "daily_avg_return": 0.0,
      "daily_max_loss": 0.0,
      "daily_max_profit": 0.0,
      "weekly_avg_return": 0.0,
      "weekly_max_loss": 0.0,
      "weekly_max_profit": 0.0,
      "monthly_avg_return": 0.0,
      "monthly_max_loss": 0.0,
      "monthly_max_profit": 0.0,
      "trade_cost": 0.0,
      "trading_days": 0
    }
  ],
  "best": { "y": 10, "m": 80 },
  "chart_data": {
    "line": [],
    "area": []
  }
}
```

## 6. 组合报告 API [P1/可顺延]

> **范围控制**: 本组 API 属于 P1/可顺延。基础版先支持创建、查看、删除、重算。

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| POST | `/{workspace_id}/report` | 创建组合报告 | P1 |
| GET | `/{workspace_id}/report` | 获取报告列表 | P1 |
| GET | `/{workspace_id}/report/{report_id}` | 获取报告详情 | P1 |
| DELETE | `/{workspace_id}/report/{report_id}` | 删除报告 | P1 |
| POST | `/{workspace_id}/report/{report_id}/calculate` | 重新计算报告 | P1 |
| PUT | `/{workspace_id}/report/{report_id}/clear` | 清空报告 | P2 |

#### POST `/{workspace_id}/report` — 创建组合报告

**请求体:**
```json
{
  "name": "策略报告1",
  "unit_ids": ["uuid-unit-1", "uuid-unit-2", "uuid-unit-3"],
  "stat_start_date": "2024/04/16 14:00:00",
  "stat_end_date": "2026/03/13 14:59:59",
  "max_invest_cash": 600,
  "calculation_method": "arithmetic",
  "report_weight": "equal"
}
```

**响应（参考TBQuant策略报告表）:**
```json
{
  "id": "uuid-report-1",
  "workspace_id": "uuid-ws-1",
  "units": [
    {
      "rank": 1,
      "report_unit": "www_2021_bowling@au000_M15",
      "source": "www_2021_bowling",
      "data_source": "au000 M...",
      "start_time": "2025/08/15 09:45:00",
      "max_invest_cash": 1000000,
      "net_value": 1.3426,
      "net_profit": 342658.34,
      "annual_return": 34.06,
      "max_leverage": 0.8631,
      "max_market_value": 1152200,
      "max_drawdown_value": 121.73,
      "max_drawdown_rate": 8.34,
      "sharpe_ratio": 1.8690,
      "adjusted_return_risk": 4.1086,
      "trade_count": 9,
      "win_rate": 9.9921,
      "profit_loss_ratio": 77.78,
      "trade_cost": 5000,
      "trading_days": 38.03
    }
  ],
  "summary": {
    "max_invest_cash": 6000000,
    "net_value": 1.4489,
    "net_profit": 2355434.26,
    "annual_return": 23.51,
    "max_drawdown_rate": 1.0839,
    "sharpe_ratio": 6.353600049,
    "trade_count": 688,
    "win_rate": 38.95,
    "trading_days": 3152900
  },
  "status": "completed"
}
```

## 7. 状态刷新方案

### 7.1 基础方案：轮询（P0 首版必须实现）

前端定时（3-5秒）调用 `GET /{workspace_id}/run-status` 获取所有单元最新状态。

**响应:**
```json
{
  "units": [
    {
      "unit_id": "uuid-unit-1",
      "run_status": "running",
      "task_id": "task-xxx",
      "progress": 60,
      "elapsed_time": 12.5,
      "estimated_remaining": 8.3
    }
  ],
  "workspace_status": "running"
}
```

### 7.2 增强方案：WebSocket（P1 可选增强）

新增 WebSocket 路由 `/ws/workspace/{workspace_id}` 用于推送:
- 策略单元运行进度
- 优化任务进度
- 报告计算进度

消息格式:
```json
{
  "type": "unit_progress",
  "unit_id": "uuid-unit-1",
  "task_id": "task-xxx",
  "progress": 60,
  "message": "Running backtest...",
  "elapsed_time": 12.5,
  "estimated_remaining": 8.3
}
```

> **降级策略**: 首版优先保证轮询闭环可用。WebSocket 作为增强，连接失败时自动回退到轮询。

## 8. Service 层设计

### 新增文件: `src/backend/app/services/workspace_service.py`

```python
class WorkspaceService:
    """工作区业务逻辑服务"""
    
    async def create_workspace(user_id, data) -> Workspace
    async def list_workspaces(user_id, page, page_size) -> list[Workspace]
    async def get_workspace(workspace_id, user_id) -> Workspace
    async def update_workspace(workspace_id, user_id, data) -> Workspace
    async def delete_workspace(workspace_id, user_id) -> bool
    
    async def create_unit(workspace_id, user_id, data) -> list[StrategyUnit]
    async def list_units(workspace_id, user_id) -> list[StrategyUnit]
    async def update_unit(unit_id, user_id, data) -> StrategyUnit
    async def delete_unit(unit_id, user_id) -> bool
    async def batch_delete_units(unit_ids, user_id) -> int
    async def reorder_units(workspace_id, unit_orders) -> bool
    async def rename_group(workspace_id, old_name, new_name, method) -> int
    
    async def run_units(workspace_id, unit_ids, mode, user_id) -> list[dict]
    async def stop_units(workspace_id, unit_ids, user_id) -> int
    
    async def run_optimization(unit_id, config, user_id) -> dict
    async def get_optimization_results(unit_id, user_id) -> dict
    async def apply_best_params(unit_id, user_id) -> StrategyUnit
    
    async def create_report(workspace_id, data, user_id) -> WorkspaceReport
    async def calculate_report(report_id, user_id) -> WorkspaceReport
    async def get_report(report_id, user_id) -> WorkspaceReport
```

**关键设计:**
- `run_units()` 内部循环调用 `BacktestService.run_backtest()` 复用现有回测引擎
- `run_optimization()` 内部调用 `submit_optimization()` 复用现有优化引擎
- `calculate_report()` 读取多个单元的 `unit_backtest_results`，聚合计算组合指标
