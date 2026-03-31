# 任务状态统一契约

> 迭代 123-A T1+T2 产出物

## 1. 状态集合

所有异步任务（回测、参数优化）共享同一组状态值，定义于 `app.schemas.backtest.TaskStatus`：

| 状态值 | 枚举 | 含义 |
|--------|------|------|
| `pending` | `TaskStatus.PENDING` | 任务已创建，尚未开始执行 |
| `running` | `TaskStatus.RUNNING` | 任务正在执行中 |
| `completed` | `TaskStatus.COMPLETED` | 任务执行成功，结果已持久化 |
| `failed` | `TaskStatus.FAILED` | 任务执行失败，`error_message` 中包含原因 |
| `cancelled` | `TaskStatus.CANCELLED` | 任务被用户主动取消 |

## 2. 状态流转

```
pending ──→ running ──→ completed
  │            │
  │            ├──→ failed
  │            │
  │            └──→ cancelled
  │
  └──→ cancelled
```

**合法流转**：
- `pending → running`：执行开始
- `pending → cancelled`：用户在执行开始前取消
- `running → completed`：执行成功
- `running → failed`：执行异常
- `running → cancelled`：用户主动取消

**不合法流转**：
- 终态（`completed`/`failed`/`cancelled`）不可再变更
- 不允许从 `running` 回退到 `pending`

## 3. 统一返回字段

### 3.1 进度查询返回

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `str` | 任务唯一标识 |
| `status` | `TaskStatus` | 当前状态 |
| `progress` | `float` | 进度百分比 (0-100)，仅 running 时有意义 |
| `error_message` | `str \| None` | 失败或取消时的描述信息 |

### 3.2 回测任务附加字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `strategy_id` | `str` | 策略标识 |
| `symbol` | `str` | 交易标的 |
| `created_at` | `datetime` | 创建时间 |

### 3.3 参数优化任务附加字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `strategy_id` | `str` | 策略标识 |
| `total` | `int` | 参数组合总数 |
| `completed` | `int` | 已完成数 |
| `failed` | `int` | 失败数 |
| `n_workers` | `int` | 并行工作进程数 |
| `created_at` | `str` | 创建时间 |

## 4. 取消语义

### 4.1 通用规则

- 仅 `pending` 和 `running` 状态的任务可被取消
- 取消成功后状态变为 `cancelled`
- 已完成（`completed`/`failed`/`cancelled`）的任务取消请求应返回失败

### 4.2 回测任务取消

- **pending 任务**：直接在 DB 中标记为 `cancelled`
- **running 任务**：需要本进程持有执行句柄（asyncio.Task 或 subprocess.Popen）
  - 若本进程持有句柄：取消 asyncio task + kill subprocess → 标记 DB 为 `cancelled`
  - 若本进程不持有句柄（重启后）：无法取消，返回 `False`
- **限制**：重启后丢失进程句柄的 running 任务，当前无法远程取消

### 4.3 参数优化任务取消

- 在 DB 中标记为 `cancelled`
- 工作线程在每次试验前检查 DB 中的取消标志
- 进程内 `_tasks` 字典同步更新为 `cancelled`
- **优势**：支持跨实例取消（通过 DB 标志）

## 5. 查询语义

### 5.1 任务不存在

- 返回 `None`，API 层转换为 HTTP 404

### 5.2 重启后的状态

- **回测**：DB 中 `pending`/`running` 的任务在重启后保持原状态
  - 需要外部机制（如启动时扫描）将孤立 running 任务标记为 `failed`
- **参数优化**：DB 中记录了任务状态，重启后可从 DB 恢复查询
  - 进程内 `_tasks` 字典丢失，但 DB 数据可用

## 6. 错误字段

| 场景 | `error_message` 内容 |
|------|---------------------|
| 执行成功 | `None` |
| 子进程失败 | stderr 输出或异常描述 |
| 超时 | 超时描述信息 |
| 用户取消 | `"User cancelled task"` 或类似描述 |

## 7. 收敛前差异清单（T1 产出）

### 7.1 状态值差异

| 维度 | 回测任务 | 参数优化任务（收敛前） |
|------|---------|---------------------|
| 状态类型 | `TaskStatus` 枚举 | 原始字符串 |
| 失败状态 | `"failed"` | `"error"` ← **不一致** |
| 初始状态 | `"pending"` | `"running"`（跳过 pending）← **不一致** |
| 状态来源 | DB 为唯一真相源 | DB + 进程内 `_tasks` 字典双写 ← **不一致** |

### 7.2 字段命名差异

| 维度 | 回测任务 | 参数优化任务 |
|------|---------|-------------|
| 进度 | WebSocket 推送，无 DB 字段 | `completed`/`total` 比率 |
| 错误信息 | `error_message`（DB 字段） | `error`（进程内）+ `error_message`（DB） |

### 7.3 取消语义差异

| 维度 | 回测任务 | 参数优化任务 |
|------|---------|-------------|
| 取消机制 | 本进程句柄 kill | DB 标志 + 进程内标志 |
| 跨实例取消 | 不支持 | 支持（通过 DB） |

## 8. 收敛措施

1. **统一状态值**：参数优化从 `"error"` 改为 `"failed"`（T4）
2. **统一初始状态**：参数优化增加 `"pending"` 初始状态（T4）
3. **类型安全**：参数优化改用 `TaskStatus` 枚举值（T4）
4. **文档对齐**：回测取消语义限制明确记录（T5）
5. **契约测试**：覆盖所有状态流转路径（T3）
