# Implementation Plan: Airflow 集成

## Overview

将 Apache Airflow 集成到 backtrader_web 数据管理模块，实现编排后端抽象（OrchestratorBackend）、Airflow REST API 适配、DAG 自动生成、回调机制、迁移工具和前端管理界面。采用增量实现策略，从基础抽象接口开始，逐步构建各组件并最终集成。

## Tasks

- [ ] 1. 基础设施：配置项、异常类和抽象接口
  - [ ] 1.1 扩展 Settings 配置类，新增 Airflow 相关配置项
    - 在 `app/config.py` 中添加 `AIRFLOW_API_BASE_URL`、`AIRFLOW_USERNAME`、`AIRFLOW_PASSWORD`、`ORCHESTRATION_BACKEND`、`AIRFLOW_DAG_OUTPUT_DIR`、`AIRFLOW_CALLBACK_BASE_URL` 配置字段
    - 设置合理的默认值（`ORCHESTRATION_BACKEND` 默认 `auto`）
    - _Requirements: 1.7, 6.4_

  - [ ] 1.2 创建 orchestration 模块目录结构和异常类
    - 创建 `app/services/orchestration/__init__.py`
    - 创建 `app/services/orchestration/exceptions.py`，定义 `AirflowAPIError`、`AirflowConnectionError`、`AirflowDAGNotFoundError`、`CyclicDependencyError`、`DAGGenerationError`
    - _Requirements: 2.3, 9.1_

  - [ ] 1.3 定义 OrchestratorBackend 抽象基类
    - 创建 `app/services/orchestration/base.py`
    - 定义 `start()`、`shutdown()`、`add_or_update_task()`、`remove_task()`、`run_task_now()`、`reload_active_tasks()`、`get_backend_status()` 抽象方法
    - _Requirements: 6.1, 6.6_

  - [ ] 1.4 扩展 TaskExecution 模型，新增 Airflow 关联字段
    - 在现有 TaskExecution 模型中添加 `airflow_dag_id`、`airflow_run_id`、`airflow_task_id` 字段（nullable, indexed）
    - _Requirements: 7.6_

  - [ ] 1.5 创建 AirflowCallbackPayload Pydantic Schema
    - 在 `app/schemas/` 下创建 `airflow.py`，定义 `AirflowCallbackPayload` 请求体模型
    - 包含 `execution_id`、`dag_id`、`dag_run_id`、`task_id`、`status`、`start_time`、`end_time`、`duration`、`error_message`、`rows_before`、`rows_after`、`result` 字段
    - _Requirements: 7.2, 7.3_

- [ ] 2. APScheduler 适配：包装现有调度器为 OrchestratorBackend 实现
  - [ ] 2.1 实现 APSchedulerBackend 类
    - 创建 `app/services/orchestration/apscheduler_backend.py`
    - 将现有 `AkshareScheduler` 类包装为 `OrchestratorBackend` 接口实现
    - 实现所有抽象方法，内部委托给现有 `AkshareScheduler` 逻辑
    - `get_backend_status()` 返回 `{"type": "apscheduler", "running": bool, "job_count": int}`
    - _Requirements: 6.3, 6.6_

  - [ ]* 2.2 编写 APSchedulerBackend 单元测试
    - 测试接口适配是否正确委托到底层 AkshareScheduler
    - 测试 `get_backend_status()` 返回格式
    - _Requirements: 6.3, 6.6_

- [ ] 3. Airflow Adapter：httpx 异步客户端封装 REST API
  - [ ] 3.1 实现 AirflowAdapter 类
    - 创建 `app/services/orchestration/airflow_adapter.py`
    - 使用 `httpx.AsyncClient` 封装 Airflow REST API v1
    - 实现连接池复用（`max_connections=20, max_keepalive_connections=10`）和超时控制（10 秒）
    - 实现方法：`health_check()`、`list_dags()`、`get_dag()`、`trigger_dag_run()`、`get_dag_run()`、`list_dag_runs()`、`get_task_instances()`、`get_task_log()`、`pause_dag()`、`unpause_dag()`、`close()`
    - HTTP 错误码转换为结构化 `AirflowAPIError` 异常
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 3.2 编写属性测试：HTTP 错误转换为结构化异常
    - **Property 1: HTTP 错误转换为结构化异常**
    - 使用 hypothesis 生成 4xx/5xx 状态码，验证 AirflowAdapter 抛出包含错误码和描述的 `AirflowAPIError`
    - **Validates: Requirements 2.3**

  - [ ]* 3.3 编写属性测试：运行时参数透传
    - **Property 2: 运行时参数透传**
    - 使用 hypothesis 生成任意 `conf` 字典，验证 `trigger_dag_run()` 请求体包含完整 `conf` 内容
    - **Validates: Requirements 2.6**

  - [ ]* 3.4 编写 AirflowAdapter 单元测试
    - 使用 `respx` 或 `httpx.MockTransport` mock HTTP 响应
    - 测试连接超时、认证失败、正常响应等场景
    - _Requirements: 2.3, 2.4, 2.7_

- [ ] 4. Checkpoint - 确保基础组件测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. DAG Generator：Jinja2 模板 + 生成逻辑
  - [ ] 5.1 创建 Jinja2 DAG 模板文件
    - 创建 `app/services/orchestration/templates/` 目录
    - 创建 `dag_single.py.j2`（单任务 DAG 模板）
    - 创建 `dag_grouped.py.j2`（多任务分组 DAG 模板）
    - 模板包含 `default_args`、`schedule_interval`、`PythonOperator`、回调函数、依赖关系操作符
    - _Requirements: 3.1, 3.7_

  - [ ] 5.2 实现 DAGGenerator 类核心逻辑
    - 创建 `app/services/orchestration/dag_generator.py`
    - 实现 `generate_dag()`：从 DataScript 元数据生成单个 DAG 文件
    - 实现 `generate_grouped_dag()`：将同类脚本组合为多任务 DAG
    - 实现 `validate_dependencies()`：检测循环依赖（拓扑排序）
    - 实现 `remove_dag()`：删除 DAG 文件
    - 实现调度表达式转换逻辑（cron/interval/daily → Airflow cron）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8_

  - [ ]* 5.3 编写属性测试：DAG 生成产出有效 Python 文件
    - **Property 3: DAG 生成产出有效 Python 文件**
    - 使用 hypothesis 生成有效 DataScript 元数据，验证生成文件是语法正确的 Python 且包含正确 `dag_id`
    - **Validates: Requirements 3.1**

  - [ ]* 5.4 编写属性测试：依赖关系解析为 DAG 操作符
    - **Property 4: 依赖关系解析为 DAG 操作符**
    - 验证依赖关系图正确转换为 `>>` 操作符链，空依赖时仅包含单任务
    - **Validates: Requirements 3.2, 3.3**

  - [ ]* 5.5 编写属性测试：元数据映射到 default_args
    - **Property 5: 元数据映射到 default_args**
    - 验证 timeout 和 max_retries 正确映射到 `default_args` 中的 `retries`、`retry_delay`、`execution_timeout`
    - **Validates: Requirements 3.4**

  - [ ]* 5.6 编写属性测试：DAG 文件命名规范
    - **Property 6: DAG 文件命名规范**
    - 验证生成的文件路径以 `dag_{script_id}.py` 结尾
    - **Validates: Requirements 3.5**

  - [ ]* 5.7 编写属性测试：同类脚本分组
    - **Property 7: 同类脚本分组**
    - 验证同 category 的脚本列表生成包含等量任务的单一 DAG
    - **Validates: Requirements 3.6**

  - [ ]* 5.8 编写属性测试：调度表达式转换
    - **Property 8: 调度表达式转换**
    - 验证各种格式的 schedule_expression 正确转换为 Airflow 兼容表达式
    - **Validates: Requirements 3.8, 10.2**

  - [ ]* 5.9 编写属性测试：循环依赖检测
    - **Property 9: 循环依赖检测**
    - 验证有环图返回错误，无环图返回空错误列表
    - **Validates: Requirements 4.3**

- [ ] 6. 数据源工厂与后端检测器
  - [ ] 6.1 实现 DataProviderFactory（数据源工厂）
    - 创建 `app/data_fetch/providers/factory.py`
    - 实现 `register_provider()` 和 `get_data_provider()` 函数
    - 注册现有 `AkshareToMySql` 为 `akshare` 数据源
    - 未注册 source 抛出 `ValueError`
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ] 6.2 实现 BackendDetector（后端自动检测器）
    - 创建 `app/services/orchestration/detector.py`
    - 实现 `detect()` 方法：根据 `ORCHESTRATION_BACKEND` 配置和健康检查结果选择后端
    - `auto` 模式：尝试健康检查（5 秒超时），成功用 Airflow，失败用 APScheduler
    - 强制模式：直接实例化指定后端
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 6.3 编写属性测试：编排后端自动检测
    - **Property 10: 编排后端自动检测**
    - 验证所有配置值和健康检查结果组合下，BackendDetector 选择正确的后端
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

  - [ ]* 6.4 编写属性测试：数据源工厂分发
    - **Property 12: 数据源工厂分发**
    - 验证已注册 source 返回正确实例，未注册 source 抛出 ValueError
    - **Validates: Requirements 8.1, 8.2**

- [ ] 7. AirflowBackend 实现与回调机制
  - [ ] 7.1 实现 AirflowBackend 类
    - 创建 `app/services/orchestration/airflow_backend.py`
    - 实现 `OrchestratorBackend` 接口，内部使用 `AirflowAdapter` 和 `DAGGenerator`
    - `add_or_update_task()` → 生成/更新 DAG 文件 + 启用 DAG
    - `run_task_now()` → 触发 DAG Run（传入 conf 参数）
    - `remove_task()` → 暂停 DAG + 删除 DAG 文件
    - `get_backend_status()` → 返回 Airflow 连接状态和版本信息
    - _Requirements: 2.5, 2.6, 6.2_

  - [ ] 7.2 实现回调接收端点
    - 创建 `app/api/airflow_callback.py`
    - 实现 `POST /api/v1/data/airflow/callback` 端点
    - 接收 `AirflowCallbackPayload`，写入 TaskExecution 记录
    - 记录数据变更信息（rows_before、rows_after）
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 7.3 编写属性测试：回调数据持久化
    - **Property 11: 回调数据持久化**
    - 验证有效 payload 创建的 TaskExecution 记录字段值与 payload 一致
    - **Validates: Requirements 7.2, 7.3**

- [ ] 8. Checkpoint - 确保核心后端逻辑测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. API 路由：Airflow DAG 管理端点
  - [ ] 9.1 实现 Airflow DAG 管理 API 路由
    - 创建 `app/api/airflow_dags.py`
    - 实现端点：`GET /api/v1/data/airflow/dags`（列出 DAG）、`GET /api/v1/data/airflow/dags/{dag_id}`（DAG 详情）
    - 实现端点：`POST /api/v1/data/airflow/dags/{dag_id}/trigger`（触发执行）
    - 实现端点：`PATCH /api/v1/data/airflow/dags/{dag_id}/pause`（暂停/恢复）
    - 实现端点：`GET /api/v1/data/airflow/dags/{dag_id}/runs`（执行历史）
    - 实现端点：`GET /api/v1/data/airflow/dags/{dag_id}/runs/{run_id}/tasks`（任务实例列表）
    - 实现端点：`GET /api/v1/data/airflow/dags/{dag_id}/runs/{run_id}/tasks/{task_id}/logs`（任务日志）
    - 非 Airflow 模式下返回 503
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.7_

  - [ ] 9.2 实现编排状态端点
    - 在 `app/api/airflow_dags.py` 中添加 `GET /api/v1/data/orchestration/status` 端点
    - 返回当前编排后端类型、连接状态和版本信息
    - _Requirements: 6.8_

  - [ ] 9.3 注册新路由到主路由器
    - 在 `app/api/router.py` 中注册 `airflow_callback` 和 `airflow_dags` 路由
    - _Requirements: 6.6, 6.7_

  - [ ]* 9.4 编写 API 路由集成测试
    - 使用 FastAPI TestClient 测试各端点
    - 测试 Airflow 模式和 APScheduler 模式下的行为差异
    - 测试 503 响应（非 Airflow 模式）
    - _Requirements: 6.7_

- [ ] 10. 迁移工具：APScheduler → Airflow
  - [ ] 10.1 实现迁移工具核心逻辑
    - 创建 `app/services/orchestration/migration.py`
    - 实现 `MigrationTool` 类
    - 读取所有活跃 ScheduledTask，为每个任务调用 DAGGenerator 生成 DAG 文件
    - 转换 `schedule_expression` 为 Airflow cron 表达式
    - 映射 `parameters` JSON 为 DAG 默认运行参数
    - 生成迁移报告（成功/失败分类及失败原因）
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 10.2 编写属性测试：迁移工具生成完整 DAG
    - **Property 13: 迁移工具生成完整 DAG**
    - 验证每个活跃任务生成恰好一个 DAG 文件
    - **Validates: Requirements 10.1**

  - [ ]* 10.3 编写属性测试：迁移参数映射
    - **Property 14: 迁移参数映射**
    - 验证 parameters JSON 正确包含在 DAG 默认运行参数中
    - **Validates: Requirements 10.3**

  - [ ]* 10.4 编写属性测试：迁移报告准确性
    - **Property 15: 迁移报告准确性**
    - 验证成功数 + 失败数 = 总任务数，失败任务包含原因说明
    - **Validates: Requirements 10.4**

- [ ] 11. Docker Compose：生产部署配置
  - [ ] 11.1 创建 Airflow Docker Compose 配置文件
    - 创建 `docker-compose.airflow.yml`
    - 定义 `airflow-postgres`（PostgreSQL 15 元数据库）、`airflow-webserver`、`airflow-scheduler` 服务
    - 配置共享卷挂载 DAG 文件目录
    - 配置环境变量（`AKSHARE_DATA_DATABASE_URL`、时区 `Asia/Shanghai`、LocalExecutor）
    - 配置健康检查（60 秒启动期）
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.8_

  - [ ] 11.2 更新 .env.example 添加 Airflow 配置示例
    - 添加 `AIRFLOW_API_BASE_URL`、`AIRFLOW_USERNAME`、`AIRFLOW_PASSWORD`、`ORCHESTRATION_BACKEND`、`AIRFLOW_DAG_OUTPUT_DIR`、`AIRFLOW_CALLBACK_BASE_URL` 示例值
    - _Requirements: 1.7_

- [ ] 12. 前端界面：DAG 管理和监控
  - [ ] 12.1 创建 Airflow API 请求封装
    - 在 `src/frontend/src/api/` 下创建 `airflow.ts`
    - 封装所有 Airflow DAG 管理端点的请求方法
    - _Requirements: 5.1_

  - [ ] 12.2 创建 Airflow Store（Pinia）
    - 在 `src/frontend/src/stores/` 下创建 `useAirflowStore.ts`
    - 管理 DAG 列表、DAG Run 历史、Task Instance 状态等响应式数据
    - _Requirements: 5.1, 5.4, 5.5_

  - [ ] 12.3 实现 DAG 列表页面
    - 创建 `src/frontend/src/views/data/AirflowDags.vue`
    - 展示 DAG 列表（名称、调度表达式、启用状态、最近运行状态）
    - 提供启用/暂停切换、手动触发按钮
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 12.4 实现 DAG 详情与执行历史页面
    - 创建 `src/frontend/src/views/data/AirflowDagDetail.vue`
    - 展示 DAG Run 执行历史列表（运行 ID、时间、持续时长、状态）
    - 展示 Task Instance 状态列表（成功、失败、运行中、跳过、上游失败）
    - 提供任务日志查看功能
    - 提供失败任务重试按钮
    - _Requirements: 5.4, 5.5, 5.6, 5.7_

  - [ ] 12.5 实现 DAG 依赖关系拓扑图组件
    - 创建 `src/frontend/src/components/data/DagTopology.vue`
    - 使用图形化方式展示 DAG 任务依赖关系
    - _Requirements: 5.8, 4.5_

  - [ ] 12.6 实现编排状态指示器组件
    - 创建 `src/frontend/src/components/data/OrchestrationStatus.vue`
    - 展示当前编排后端类型和连接状态
    - Airflow 离线时显示提示信息
    - _Requirements: 6.8, 9.5_

  - [ ] 12.7 注册前端路由
    - 在前端路由配置中添加 Airflow DAG 管理相关页面路由
    - _Requirements: 5.1_

  - [ ]* 12.8 编写前端组件单元测试
    - 测试 DAG 列表渲染、状态切换、触发执行等交互
    - 测试编排状态指示器在不同模式下的显示
    - _Requirements: 5.1, 5.2_

- [ ] 13. 集成与连接：将所有组件串联
  - [ ] 13.1 实现应用启动时的后端初始化逻辑
    - 在 `app/main.py` 的 startup 事件中集成 BackendDetector
    - 根据检测结果初始化对应的 OrchestratorBackend 实例
    - 替换现有 AkshareSchedulerService 中的直接调度调用为 OrchestratorBackend 接口调用
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 13.2 更新 AkshareSchedulerService 使用 OrchestratorBackend
    - 修改 `app/services/akshare_scheduler_service.py`
    - 将调度操作委托给当前活跃的 OrchestratorBackend 实例
    - 保持现有 API 接口不变
    - _Requirements: 6.6_

  - [ ]* 13.3 编写集成测试
    - 测试完整的后端检测 → 初始化 → 调度操作流程
    - 测试 Airflow 模式和 APScheduler 模式的切换
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 14. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (P1-P15 from design document)
- Unit tests validate specific examples and edge cases
- 前端组件使用 Vue 3 Composition API + TypeScript + Element Plus
- 后端使用 Python 3.10+ + FastAPI + SQLAlchemy 2.0 + Pydantic
- 属性测试使用 hypothesis 库，每个属性至少 100 次迭代

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"] },
    { "id": 1, "tasks": ["2.1", "3.1", "5.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "3.3", "3.4", "5.2"] },
    { "id": 3, "tasks": ["5.3", "5.4", "5.5", "5.6", "5.7", "5.8", "5.9", "6.1", "6.2"] },
    { "id": 4, "tasks": ["6.3", "6.4", "7.1", "7.2"] },
    { "id": 5, "tasks": ["7.3", "9.1", "9.2", "10.1"] },
    { "id": 6, "tasks": ["9.3", "9.4", "10.2", "10.3", "10.4", "11.1", "11.2"] },
    { "id": 7, "tasks": ["12.1", "13.1"] },
    { "id": 8, "tasks": ["12.2", "13.2"] },
    { "id": 9, "tasks": ["12.3", "12.4", "12.5", "12.6", "12.7", "13.3"] },
    { "id": 10, "tasks": ["12.8"] }
  ]
}
```
