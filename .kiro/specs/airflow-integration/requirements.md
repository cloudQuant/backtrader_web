# Requirements Document

## Introduction

将 Apache Airflow 集成到 backtrader_web 项目的数据管理模块中，作为现有 APScheduler 内存调度器的增强替代方案。系统采用**优雅降级**策略：当 Airflow 可用时优先使用 Airflow 进行任务编排（支持 DAG 依赖、分布式执行、可视化监控）；当 Airflow 不可用时自动回退到现有 APScheduler，确保系统始终可用。支持本地开发环境直接安装调试和 Docker 容器化生产部署两种模式。

## Glossary

- **Airflow_Service**: 独立部署的 Apache Airflow 服务实例（Docker 容器），提供任务编排和执行能力
- **Airflow_REST_API**: Airflow 提供的 REST API 接口（Stable API v1），用于外部系统与 Airflow 交互
- **DAG**: 有向无环图（Directed Acyclic Graph），Airflow 中定义任务依赖关系的核心概念
- **DAG_Run**: DAG 的一次具体执行实例
- **Task_Instance**: DAG 中单个任务的一次执行实例
- **Airflow_Adapter**: backtrader_web 后端中封装 Airflow REST API 调用的服务层组件
- **DAG_Generator**: 将 DataScript 元数据和依赖关系转换为 Airflow DAG Python 文件的组件
- **DataScript**: 现有的数据抓取脚本元数据模型（`ak_data_scripts` 表）
- **ScheduledTask**: 现有的定时任务模型（`ak_scheduled_tasks` 表）
- **AkshareToMySql**: 数据抓取脚本的基类，提供 `fetch_ak_data()` 和 `save_to_mysql()` 方法
- **Orchestration_Backend**: 任务编排后端的抽象概念，支持 APScheduler 和 Airflow 两种实现，运行时自动检测并选择可用后端

## Requirements

### Requirement 1: Airflow 服务部署与配置

**User Story:** 作为开发者/运维人员，我希望能在本地开发环境直接安装 Airflow 进行调试，也能通过 Docker Compose 部署生产环境，以便灵活适配不同场景。

#### Acceptance Criteria

1. THE 项目文档 SHALL 提供本地安装 Airflow 的步骤说明（pip install apache-airflow），包含初始化数据库、创建用户和启动服务的命令
2. THE Docker_Compose_Configuration SHALL 包含 Airflow Webserver、Scheduler、Worker 和 PostgreSQL 元数据库的服务定义，作为生产部署方案
3. THE Docker_Compose_Configuration SHALL 通过共享卷将 DAG 文件目录挂载到 Airflow_Service 容器中
4. THE Airflow_Service SHALL 在启动后 60 秒内通过健康检查端点返回正常状态
5. THE Airflow_Service SHALL 通过环境变量接收数据仓库连接信息（`AKSHARE_DATA_DATABASE_URL`）
6. WHEN Airflow_Service 启动时，THE Airflow_Service SHALL 自动加载 DAG 文件目录中的所有 DAG 定义
7. THE 配置 SHALL 支持 `AIRFLOW_API_BASE_URL`（默认 `http://localhost:8080/api/v1`）和认证凭据环境变量
8. THE Airflow_Service SHALL 将时区设置为 `Asia/Shanghai`
9. THE 本地开发模式 SHALL 使用 SQLite 作为 Airflow 元数据库和 SequentialExecutor，简化依赖

### Requirement 2: Airflow REST API 适配层

**User Story:** 作为后端开发者，我希望有一个统一的适配层封装 Airflow REST API 调用，以便 backtrader_web 后端能可靠地与 Airflow 交互。

#### Acceptance Criteria

1. THE Airflow_Adapter SHALL 封装 Airflow Stable REST API v1 的 DAG、DAG_Run 和 Task_Instance 相关端点
2. THE Airflow_Adapter SHALL 使用配置中的 `AIRFLOW_API_BASE_URL` 和认证凭据连接 Airflow_Service
3. WHEN Airflow_REST_API 返回 HTTP 错误码时，THE Airflow_Adapter SHALL 将错误转换为结构化的异常信息，包含错误码和描述
4. WHEN Airflow_REST_API 连接超时时，THE Airflow_Adapter SHALL 在 10 秒超时后返回连接失败错误
5. THE Airflow_Adapter SHALL 提供以下操作方法：列出 DAG、触发 DAG_Run、查询 DAG_Run 状态、查询 Task_Instance 列表和状态、暂停/恢复 DAG
6. WHEN 调用 Airflow_Adapter 的触发方法时，THE Airflow_Adapter SHALL 支持传入运行时参数（`conf` 字典）
7. THE Airflow_Adapter SHALL 实现连接池复用，避免每次请求创建新的 HTTP 连接

### Requirement 3: DAG 自动生成

**User Story:** 作为数据管理员，我希望系统能根据 DataScript 元数据自动生成 Airflow DAG 文件，以便无需手动编写 DAG 代码即可将现有脚本纳入 Airflow 调度。

#### Acceptance Criteria

1. THE DAG_Generator SHALL 读取 `ak_data_scripts` 表中的脚本元数据，生成符合 Airflow 规范的 DAG Python 文件
2. THE DAG_Generator SHALL 将 DataScript 的 `dependencies` JSON 字段解析为 DAG 中的任务依赖关系（上下游 `>>` 操作符）
3. WHEN DataScript 的 `dependencies` 字段为空时，THE DAG_Generator SHALL 生成仅包含单个任务的独立 DAG
4. THE DAG_Generator SHALL 为每个生成的 DAG 设置 `default_args`，包含 `retries`（来自 ScheduledTask.max_retries）、`retry_delay`（5 分钟）和 `execution_timeout`（来自 DataScript.timeout）
5. THE DAG_Generator SHALL 将生成的 DAG 文件写入 Airflow DAG 目录，文件名格式为 `dag_{script_id}.py`
6. WHEN DataScript 的 `category` 字段相同时，THE DAG_Generator SHALL 支持将同类脚本组合为一个包含多任务的 DAG
7. THE DAG_Generator SHALL 在 DAG 文件中使用 PythonOperator 调用现有的 `AkshareToMySql` 子类的 `fetch_data()` 方法
8. THE DAG_Generator SHALL 为每个 DAG 设置 `schedule_interval`，基于 ScheduledTask 的 `schedule_expression` 转换为 Airflow cron 表达式

### Requirement 4: 任务依赖关系管理

**User Story:** 作为数据管理员，我希望能定义数据抓取任务之间的依赖关系（如先获取股票列表再获取历史数据），以便系统按正确顺序执行任务。

#### Acceptance Criteria

1. THE DataScript 模型 SHALL 使用 `dependencies` JSON 字段存储上游依赖的 `script_id` 列表
2. WHEN 用户通过 API 更新 DataScript 的 `dependencies` 字段时，THE DAG_Generator SHALL 重新生成对应的 DAG 文件以反映新的依赖关系
3. IF 依赖关系形成循环引用，THEN THE Airflow_Adapter SHALL 在 DAG 生成阶段检测并返回循环依赖错误
4. WHEN 上游任务执行失败时，THE Airflow_Service SHALL 阻止下游依赖任务的执行，并将下游任务标记为 `upstream_failed` 状态
5. THE 前端界面 SHALL 提供可视化的依赖关系编辑功能，允许用户通过选择上游脚本来配置依赖
6. WHEN 查询 DAG 详情时，THE Airflow_Adapter SHALL 返回完整的任务依赖拓扑结构（节点和边的列表）

### Requirement 5: 前端任务管理界面

**User Story:** 作为数据管理员，我希望通过 backtrader_web 前端界面管理和监控 Airflow 任务，以便无需直接访问 Airflow Web UI 即可完成日常操作。

#### Acceptance Criteria

1. THE 前端界面 SHALL 展示所有 DAG 的列表，包含 DAG 名称、调度表达式、启用状态和最近运行状态
2. THE 前端界面 SHALL 提供 DAG 的启用/暂停切换功能
3. THE 前端界面 SHALL 提供手动触发 DAG 执行的按钮，支持传入运行时参数
4. THE 前端界面 SHALL 展示 DAG_Run 的执行历史列表，包含运行 ID、开始时间、结束时间、持续时长和最终状态
5. THE 前端界面 SHALL 展示单次 DAG_Run 中各 Task_Instance 的执行状态（成功、失败、运行中、跳过、上游失败）
6. THE 前端界面 SHALL 提供任务执行日志的查看功能，通过 Airflow REST API 获取 Task_Instance 的日志内容
7. WHEN Task_Instance 执行失败时，THE 前端界面 SHALL 提供重试单个失败任务的操作按钮
8. THE 前端界面 SHALL 提供 DAG 依赖关系的图形化展示（DAG 拓扑图）

### Requirement 6: 编排后端自动检测与优雅降级

**User Story:** 作为系统管理员，我希望系统在 Airflow 可用时自动使用 Airflow，不可用时自动回退到 APScheduler，以便在任何环境下都能正常运行定时任务。

#### Acceptance Criteria

1. THE 后端 SHALL 在启动时自动检测 Airflow_Service 是否可用（通过健康检查端点 `GET /api/v1/health`）
2. WHEN Airflow_Service 健康检查成功时，THE 后端 SHALL 自动将 `ORCHESTRATION_BACKEND` 设置为 `airflow`，使用 Airflow_Adapter 处理所有调度操作
3. WHEN Airflow_Service 健康检查失败或未配置 `AIRFLOW_API_BASE_URL` 时，THE 后端 SHALL 自动回退到 `apscheduler` 模式，使用现有 APScheduler 处理调度
4. THE 后端 SHALL 支持通过 `ORCHESTRATION_BACKEND` 环境变量强制指定后端（`airflow`、`apscheduler`、`auto`），默认值为 `auto`（自动检测）
5. WHEN 运行时 Airflow_Service 变为不可用时，THE 后端 SHALL 记录 WARNING 日志并在下次调度操作时尝试重新连接，但不自动切换到 APScheduler（避免状态不一致）
6. THE 后端 SHALL 保留现有的 `/api/v1/data/tasks` 系列端点，根据当前活跃的编排后端路由到对应实现
7. THE 后端 SHALL 新增 `/api/v1/data/airflow/dags` 系列端点，仅在 Airflow 模式下可用；在 APScheduler 模式下访问这些端点返回 503 Service Unavailable
8. THE 后端 SHALL 提供 `/api/v1/data/orchestration/status` 端点，返回当前编排后端类型、连接状态和版本信息

### Requirement 7: 任务执行与回调

**User Story:** 作为系统管理员，我希望 Airflow 任务执行结果能同步回 backtrader_web 数据库，以便在统一界面查看完整的执行历史。

#### Acceptance Criteria

1. WHEN Airflow Task_Instance 执行完成时，THE DAG 定义 SHALL 通过回调机制（`on_success_callback` / `on_failure_callback`）向 backtrader_web 后端发送执行结果
2. THE 回调 SHALL 将执行结果写入 `ak_task_executions` 表，包含 execution_id、状态、开始时间、结束时间、持续时长和错误信息
3. THE 回调 SHALL 记录数据变更信息（`rows_before` 和 `rows_after`），与现有 TaskExecution 模型保持一致
4. WHEN 回调请求失败时，THE DAG 定义 SHALL 重试回调最多 3 次，间隔 10 秒
5. THE Airflow_Adapter SHALL 提供轮询方法，定期同步 Airflow 中的执行状态到本地数据库，作为回调机制的补充
6. THE TaskExecution 模型 SHALL 新增 `airflow_dag_id`、`airflow_run_id` 和 `airflow_task_id` 字段，关联 Airflow 执行信息

### Requirement 8: 数据源扩展支持

**User Story:** 作为数据管理员，我希望系统架构支持未来集成其他数据源（如 tushare、wind），以便在同一调度框架下管理多种数据源的抓取任务。

#### Acceptance Criteria

1. THE DAG_Generator SHALL 通过 DataScript 的 `source` 字段区分不同数据源，生成对应的任务执行逻辑
2. THE DAG 定义 SHALL 使用工厂模式根据 `source` 字段实例化对应的数据提供者类（如 `AkshareToMySql`、`TushareToMySql`）
3. THE DataScript 模型的 `source` 字段 SHALL 支持 `akshare`、`tushare`、`wind` 和 `custom` 四种值
4. WHEN 新增数据源类型时，THE DAG_Generator SHALL 无需修改核心生成逻辑，仅需注册新的数据提供者类

### Requirement 9: 错误处理与告警

**User Story:** 作为系统管理员，我希望系统能在任务失败时提供详细的错误信息和告警通知，以便快速定位和解决问题。

#### Acceptance Criteria

1. WHEN Task_Instance 执行失败时，THE Airflow_Service SHALL 记录完整的错误堆栈信息和执行上下文
2. WHEN Task_Instance 连续失败达到 `max_retries` 次数时，THE Airflow_Service SHALL 将任务标记为最终失败状态
3. THE Airflow_Service SHALL 支持配置指数退避重试策略（`retry_exponential_backoff=True`），避免对数据源造成过大压力
4. WHEN DAG_Run 中存在失败的 Task_Instance 时，THE 前端界面 SHALL 在任务列表中以醒目标识展示失败状态
5. IF Airflow_Service 连接不可用，THEN THE Airflow_Adapter SHALL 返回服务不可用错误，前端界面展示 Airflow 服务离线提示

### Requirement 10: 迁移工具

**User Story:** 作为运维人员，我希望有自动化工具将现有的 APScheduler 任务配置迁移到 Airflow DAG，以便平滑过渡到新的调度系统。

#### Acceptance Criteria

1. THE 迁移工具 SHALL 读取 `ak_scheduled_tasks` 表中所有活跃任务，为每个任务生成对应的 Airflow DAG 文件
2. THE 迁移工具 SHALL 将 ScheduledTask 的 `schedule_expression` 转换为 Airflow 兼容的 cron 表达式
3. THE 迁移工具 SHALL 将 ScheduledTask 的 `parameters` JSON 字段映射为 DAG 的默认运行参数（`params`）
4. THE 迁移工具 SHALL 生成迁移报告，列出成功迁移和失败的任务及失败原因
5. WHEN 迁移完成后，THE 迁移工具 SHALL 提供验证命令，检查生成的 DAG 文件是否能被 Airflow 正确解析
