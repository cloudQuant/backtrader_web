# 验收测试计划：Airflow 集成

## 概述

本文档定义 Airflow 集成功能的验收标准和测试用例。每个需求对应一组测试用例，明确测试方法、前置条件、操作步骤和预期结果。

## 测试环境要求

| 环境 | 配置 | 用途 |
|------|------|------|
| 本地开发 | macOS/Linux, Python 3.10+, pip install apache-airflow | 单元测试 + 集成测试 |
| Docker | docker-compose.airflow.yml | E2E 测试 |
| CI | GitHub Actions, 无 Airflow | 降级模式测试 |

## 测试分层

- **L1 单元测试**：pytest，mock 外部依赖，验证单个组件逻辑
- **L2 集成测试**：pytest + 本地 Airflow 实例，验证组件间交互
- **L3 E2E 测试**：Docker Compose 全栈，验证端到端流程
- **L4 手动验收**：人工操作前端界面，验证用户体验

---

## 需求 1：Airflow 服务部署与配置

### AT-1.1 本地安装验证

**级别：** L2 集成测试
**前置条件：** Python 3.10+ 环境
**步骤：**
1. 执行 `pip install apache-airflow==2.8.1`
2. 执行 `airflow db init`
3. 执行 `airflow users create --username admin --password admin --role Admin --firstname A --lastname B --email a@b.com`
4. 执行 `airflow webserver -p 8080 -D` 和 `airflow scheduler -D`
5. 访问 `http://localhost:8080/api/v1/health`

**预期结果：** 返回 `{"metadatabase":{"status":"healthy"},"scheduler":{"status":"healthy"}}`

### AT-1.2 Docker Compose 部署验证

**级别：** L3 E2E
**前置条件：** Docker + Docker Compose 已安装
**步骤：**
1. 执行 `docker compose -f docker-compose.airflow.yml up -d`
2. 等待 60 秒
3. 执行 `curl http://localhost:8080/api/v1/health`

**预期结果：** 返回健康状态 JSON，所有组件 status=healthy

### AT-1.3 DAG 目录挂载验证

**级别：** L3 E2E
**步骤：**
1. 在 `./dags/` 目录创建 `test_dag.py`（包含简单 DAG 定义）
2. 等待 30 秒（Airflow 扫描间隔）
3. 调用 `GET /api/v1/dags/test_dag`

**预期结果：** 返回 DAG 信息，`dag_id=test_dag`

---

## 需求 2：Airflow REST API 适配层

### AT-2.1 健康检查成功

**级别：** L1 单元测试
**代码：**
```python
async def test_health_check_success(mock_airflow_server):
    adapter = AirflowAdapter("http://localhost:8080/api/v1", "admin", "admin")
    result = await adapter.health_check()
    assert result is True
```

### AT-2.2 健康检查超时

**级别：** L1 单元测试
**代码：**
```python
async def test_health_check_timeout(slow_server):
    adapter = AirflowAdapter("http://localhost:9999/api/v1", "admin", "admin")
    result = await adapter.health_check()
    assert result is False  # 10秒超时后返回 False
```

### AT-2.3 HTTP 错误转换

**级别：** L1 单元测试
**代码：**
```python
async def test_http_error_conversion(mock_airflow_404):
    adapter = AirflowAdapter(...)
    with pytest.raises(AirflowDAGNotFoundError) as exc_info:
        await adapter.get_dag("nonexistent_dag")
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()
```

### AT-2.4 触发 DAG Run 带参数

**级别：** L2 集成测试
**代码：**
```python
async def test_trigger_dag_with_conf(airflow_adapter, sample_dag):
    conf = {"symbol": "000001", "start_date": "2024-01-01"}
    result = await airflow_adapter.trigger_dag_run("dag_stock_zh_a_hist", conf=conf)
    assert result["dag_run_id"] is not None
    assert result["conf"] == conf
```

### AT-2.5 连接池复用

**级别：** L1 单元测试
**代码：**
```python
async def test_connection_pool_reuse(mock_airflow_server):
    adapter = AirflowAdapter(...)
    await adapter.list_dags()
    await adapter.list_dags()
    # 验证底层只创建了一个连接
    assert adapter._client._pool._connections_count <= 1
```

---

## 需求 3：DAG 自动生成

### AT-3.1 单任务 DAG 生成

**级别：** L1 单元测试
**代码：**
```python
def test_generate_single_task_dag(tmp_path, sample_script):
    generator = DAGGenerator(dag_output_dir=str(tmp_path))
    path = generator.generate_dag(sample_script)
    assert path.endswith("dag_stock_zh_a_hist.py")
    # 验证生成的文件是有效 Python
    compile(open(path).read(), path, "exec")
    content = open(path).read()
    assert 'dag_id="dag_stock_zh_a_hist"' in content
    assert "PythonOperator" in content
```

### AT-3.2 依赖关系生成

**级别：** L1 单元测试
**代码：**
```python
def test_generate_dag_with_dependencies(tmp_path):
    script_a = DataScript(script_id="get_stock_list", dependencies=[])
    script_b = DataScript(script_id="get_stock_hist", dependencies=["get_stock_list"])
    generator = DAGGenerator(dag_output_dir=str(tmp_path))
    path = generator.generate_grouped_dag([script_a, script_b], "stocks")
    content = open(path).read()
    assert "task_get_stock_list >> task_get_stock_hist" in content
```

### AT-3.3 循环依赖检测

**级别：** L1 单元测试
**代码：**
```python
def test_cyclic_dependency_detection():
    scripts = [
        DataScript(script_id="a", dependencies=["b"]),
        DataScript(script_id="b", dependencies=["c"]),
        DataScript(script_id="c", dependencies=["a"]),  # 循环!
    ]
    generator = DAGGenerator(...)
    errors = generator.validate_dependencies(scripts)
    assert len(errors) > 0
    assert "cyclic" in errors[0].lower() or "循环" in errors[0]
```

### AT-3.4 调度表达式转换

**级别：** L1 单元测试
**代码：**
```python
@pytest.mark.parametrize("input_expr,expected", [
    ("0 8 * * *", "0 8 * * *"),       # cron 直接透传
    ("18:00", "0 18 * * *"),           # HH:MM → cron
    ("30m", "*/30 * * * *"),           # interval 分钟
    ("2h", "0 */2 * * *"),             # interval 小时
])
def test_schedule_expression_conversion(input_expr, expected):
    result = DAGGenerator._convert_schedule(input_expr)
    assert result == expected
```

### AT-3.5 default_args 映射

**级别：** L1 单元测试
**代码：**
```python
def test_default_args_from_metadata(tmp_path):
    script = DataScript(script_id="test", timeout=600)
    task = ScheduledTask(max_retries=5, schedule_expression="0 8 * * *")
    generator = DAGGenerator(dag_output_dir=str(tmp_path))
    path = generator.generate_dag(script, task)
    content = open(path).read()
    assert '"retries": 5' in content
    assert "timedelta(seconds=600)" in content
```

---

## 需求 4：任务依赖关系管理

### AT-4.1 依赖关系 CRUD

**级别：** L2 集成测试
**代码：**
```python
async def test_update_dependencies_regenerates_dag(client, auth_headers, sample_scripts):
    # 更新依赖
    resp = await client.patch(
        "/api/v1/data/scripts/get_stock_hist",
        json={"dependencies": ["get_stock_list"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    # 验证 DAG 文件已重新生成
    dag_path = Path(settings.AIRFLOW_DAG_OUTPUT_DIR) / "dag_get_stock_hist.py"
    assert dag_path.exists()
    assert "get_stock_list" in dag_path.read_text()
```

### AT-4.2 上游失败阻止下游

**级别：** L3 E2E（需要运行中的 Airflow）
**步骤：**
1. 创建 DAG：task_a → task_b，task_a 设计为必定失败
2. 触发 DAG Run
3. 等待执行完成
4. 查询 task_b 状态

**预期结果：** task_b 状态为 `upstream_failed`

---

## 需求 5：前端任务管理界面

### AT-5.1 DAG 列表展示

**级别：** L4 手动验收
**步骤：**
1. 登录系统，进入数据管理页面
2. 切换到 "Airflow DAGs" 标签

**预期结果：** 展示 DAG 列表，每行包含名称、调度表达式、启用状态、最近运行状态

### AT-5.2 手动触发执行

**级别：** L4 手动验收
**步骤：**
1. 在 DAG 列表中点击某个 DAG 的"执行"按钮
2. 在弹出的参数对话框中填入参数（可选）
3. 点击确认

**预期结果：** 提示"已触发执行"，刷新后可看到新的 DAG Run 记录

### AT-5.3 查看执行日志

**级别：** L4 手动验收
**步骤：**
1. 进入某个 DAG 的执行历史
2. 点击某次运行的某个任务
3. 点击"查看日志"

**预期结果：** 弹出日志对话框，展示任务执行的完整日志内容

---

## 需求 6：编排后端自动检测与优雅降级

### AT-6.1 自动检测选择 Airflow

**级别：** L2 集成测试
**前置条件：** 本地 Airflow 运行中，`ORCHESTRATION_BACKEND=auto`
**代码：**
```python
async def test_auto_detect_selects_airflow(running_airflow):
    detector = BackendDetector()
    backend = await detector.detect()
    assert isinstance(backend, AirflowBackend)
    status = await backend.get_backend_status()
    assert status["type"] == "airflow"
```

### AT-6.2 自动检测回退 APScheduler

**级别：** L1 单元测试
**前置条件：** 无 Airflow 运行，`ORCHESTRATION_BACKEND=auto`
**代码：**
```python
async def test_auto_detect_fallback_to_apscheduler(no_airflow):
    detector = BackendDetector()
    backend = await detector.detect()
    assert isinstance(backend, APSchedulerBackend)
    status = await backend.get_backend_status()
    assert status["type"] == "apscheduler"
```

### AT-6.3 强制指定后端

**级别：** L1 单元测试
**代码：**
```python
@pytest.mark.parametrize("config_value,expected_type", [
    ("airflow", AirflowBackend),
    ("apscheduler", APSchedulerBackend),
])
async def test_forced_backend_selection(config_value, expected_type, monkeypatch):
    monkeypatch.setenv("ORCHESTRATION_BACKEND", config_value)
    detector = BackendDetector()
    backend = await detector.detect()
    assert isinstance(backend, expected_type)
```

### AT-6.4 编排状态 API

**级别：** L2 集成测试
**代码：**
```python
async def test_orchestration_status_endpoint(client, auth_headers):
    resp = await client.get("/api/v1/data/orchestration/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["backend_type"] in ("airflow", "apscheduler")
    assert "connected" in data or "running" in data
```

### AT-6.5 Airflow 端点在 APScheduler 模式下返回 503

**级别：** L1 单元测试
**代码：**
```python
async def test_airflow_endpoints_503_in_apscheduler_mode(client_apscheduler_mode, auth_headers):
    resp = await client_apscheduler_mode.get(
        "/api/v1/data/airflow/dags", headers=auth_headers
    )
    assert resp.status_code == 503
    assert "Airflow" in resp.json()["detail"]
```

---

## 需求 7：任务执行与回调

### AT-7.1 回调写入 TaskExecution

**级别：** L1 单元测试
**代码：**
```python
async def test_callback_creates_execution_record(client, db):
    payload = {
        "execution_id": "exec_001",
        "dag_id": "dag_stock_zh_a_hist",
        "dag_run_id": "run_20240101",
        "task_id": "fetch_data",
        "status": "success",
        "start_time": "2024-01-01T08:00:00Z",
        "end_time": "2024-01-01T08:05:00Z",
        "duration": 300.0,
        "rows_before": 1000,
        "rows_after": 1500,
    }
    resp = await client.post("/api/v1/data/airflow/callback", json=payload)
    assert resp.status_code == 200
    # 验证数据库记录
    execution = await db.scalar(
        select(TaskExecution).where(TaskExecution.execution_id == "exec_001")
    )
    assert execution is not None
    assert execution.airflow_dag_id == "dag_stock_zh_a_hist"
    assert execution.status == TaskStatus.COMPLETED
    assert execution.rows_after == 1500
```

### AT-7.2 回调失败不影响任务状态

**级别：** L2 集成测试（需要 Airflow）
**步骤：**
1. 配置回调 URL 为不可达地址
2. 触发 DAG 执行
3. 等待任务完成

**预期结果：** 任务本身成功完成（数据已写入），回调失败仅记录日志

---

## 需求 8：数据源扩展支持

### AT-8.1 工厂模式分发

**级别：** L1 单元测试
**代码：**
```python
def test_provider_factory_akshare():
    provider = get_data_provider("akshare")
    assert isinstance(provider, AkshareToMySql)

def test_provider_factory_unknown_raises():
    with pytest.raises(ValueError, match="Unknown data source"):
        get_data_provider("nonexistent")
```

### AT-8.2 新数据源注册

**级别：** L1 单元测试
**代码：**
```python
def test_register_new_provider():
    class MockProvider:
        pass
    register_provider("mock_source", MockProvider)
    provider = get_data_provider("mock_source")
    assert isinstance(provider, MockProvider)
```

---

## 需求 9：错误处理与告警

### AT-9.1 Airflow 服务离线提示

**级别：** L1 单元测试
**代码：**
```python
async def test_airflow_offline_returns_503(client_airflow_mode, auth_headers, stop_airflow):
    resp = await client_airflow_mode.get(
        "/api/v1/data/airflow/dags", headers=auth_headers
    )
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()
```

### AT-9.2 指数退避重试

**级别：** L2 集成测试（需要 Airflow）
**步骤：**
1. 创建一个会失败 2 次然后成功的 DAG 任务
2. 设置 `retries=3, retry_exponential_backoff=True`
3. 触发执行
4. 查询执行历史

**预期结果：** 任务最终成功，retry_count=2，重试间隔递增

---

## 需求 10：迁移工具

### AT-10.1 迁移生成 DAG 文件

**级别：** L1 单元测试
**代码：**
```python
async def test_migration_generates_dags(tmp_path, db_with_tasks):
    tool = MigrationTool(dag_output_dir=str(tmp_path))
    report = await tool.migrate_all()
    # 验证每个活跃任务都生成了 DAG
    assert report["success_count"] == 3  # 假设有 3 个活跃任务
    assert report["failure_count"] == 0
    dag_files = list(tmp_path.glob("dag_*.py"))
    assert len(dag_files) == 3
```

### AT-10.2 迁移报告准确性

**级别：** L1 单元测试
**代码：**
```python
async def test_migration_report_accuracy(tmp_path, db_with_mixed_tasks):
    tool = MigrationTool(dag_output_dir=str(tmp_path))
    report = await tool.migrate_all()
    assert report["success_count"] + report["failure_count"] == report["total_count"]
    for failure in report["failures"]:
        assert "reason" in failure
        assert "task_id" in failure
```

### AT-10.3 迁移参数映射

**级别：** L1 单元测试
**代码：**
```python
async def test_migration_maps_parameters(tmp_path, db_with_parameterized_task):
    tool = MigrationTool(dag_output_dir=str(tmp_path))
    await tool.migrate_all()
    dag_content = (tmp_path / "dag_stock_zh_a_hist.py").read_text()
    assert '"symbol"' in dag_content  # 参数被映射到 DAG params
```

### AT-10.4 DAG 文件可被 Airflow 解析

**级别：** L2 集成测试
**步骤：**
1. 运行迁移工具生成 DAG 文件
2. 执行 `airflow dags list` 或调用 `GET /api/v1/dags`

**预期结果：** 所有生成的 DAG 出现在列表中，无解析错误

---

## 端到端验收场景

### E2E-1：完整数据抓取流程（Airflow 模式）

**级别：** L3 E2E
**前置条件：** Airflow 运行中，数据仓库可用
**步骤：**
1. 系统启动，自动检测到 Airflow → 使用 Airflow 后端
2. 通过前端创建定时任务（stock_zh_a_hist，每天 18:00）
3. 系统自动生成 DAG 文件
4. 手动触发执行
5. 查看执行状态和日志
6. 验证数据已写入数据仓库

**预期结果：** 全流程无错误，数据正确写入

### E2E-2：优雅降级流程

**级别：** L3 E2E
**步骤：**
1. 停止 Airflow 服务
2. 重启 backtrader_web 后端
3. 检查日志输出
4. 通过 API 创建定时任务
5. 手动触发执行

**预期结果：**
- 日志显示 "Airflow unavailable, falling back to APScheduler"
- 任务通过 APScheduler 正常执行
- `/api/v1/data/orchestration/status` 返回 `{"backend_type": "apscheduler"}`
- `/api/v1/data/airflow/dags` 返回 503

### E2E-3：Airflow 恢复后切换

**级别：** L3 E2E
**步骤：**
1. 系统以 APScheduler 模式运行
2. 启动 Airflow 服务
3. 重启 backtrader_web 后端（或等待下次健康检查）
4. 检查编排状态

**预期结果：** 系统切换到 Airflow 模式，现有任务继续正常调度

---

## 测试覆盖率目标

| 组件 | 目标覆盖率 | 测试类型 |
|------|-----------|---------|
| AirflowAdapter | ≥90% | L1 单元 + 属性测试 |
| DAGGenerator | ≥90% | L1 单元 + 属性测试 |
| BackendDetector | ≥95% | L1 单元测试 |
| APSchedulerBackend | ≥85% | L1 单元测试 |
| AirflowBackend | ≥80% | L1 + L2 |
| CallbackRouter | ≥90% | L1 单元测试 |
| MigrationTool | ≥85% | L1 单元测试 |
| DataProviderFactory | ≥95% | L1 单元测试 |
| API 路由 | ≥80% | L2 集成测试 |
| 前端组件 | ≥70% | Vitest |

## 验收通过标准

1. 所有 L1 单元测试通过（`pytest tests/test_orchestration/ -v`）
2. 所有 L2 集成测试通过（需本地 Airflow：`pytest -m integration`）
3. E2E-1、E2E-2、E2E-3 三个端到端场景手动验证通过
4. 前端 DAG 管理界面功能可用（L4 手动验收）
5. 无 Airflow 环境下系统正常运行（降级模式）
6. 代码 lint 通过（`ruff check`）
7. TypeScript 类型检查通过（`npm run typecheck`）
