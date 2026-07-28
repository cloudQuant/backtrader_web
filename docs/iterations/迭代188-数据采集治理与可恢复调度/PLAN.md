# 数据采集治理与可恢复调度 Implementation Plan

> **状态：已废弃（2026-07-27）**
>
> 本计划将数据提供方、逻辑数据产品和物理存储目标耦合得过紧，且把三层建模、可靠发布、Airflow、APScheduler 回退、ClickHouse 和多提供方接入放进了同一迭代，范围过大。不得基于本文件启动实现；替代方案见 `docs/iterations/迭代189-三层数据平台基础/PLAN.md`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `data_fetch` 从脚本各自写库、FastAPI 进程内调度的模式，升级为有版本化数据契约、幂等发布、质量门禁，并以 Airflow 为首选、APScheduler 为受控故障回退的可恢复采集平台。

**Architecture:** 应用数据库保存端点目录、不可变契约版本、调度定义和统一的 `DgIngestJob` 运行事实；Airflow 通过两个固定 DAG 认领并执行任务。Airflow 不可用时，具备数据库租约的 APScheduler fallback 使用同一 job 状态机和幂等键继续调度；Airflow 恢复后，通过带 fencing token 的受控交接回到 Airflow，任何时间一个逻辑任务只由一个后端发布。

**Tech Stack:** Python 3.10+、FastAPI、SQLAlchemy 2.0、Alembic、MySQL、APScheduler、Apache Airflow 2.8、PostgreSQL（Airflow metadata）、Redis/Celery（生产 Airflow worker）、pytest、Docker Compose、Vue 3/TypeScript。

## Global Constraints

- Python 命令必须使用 `/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python ...`，禁止裸 `python` 或 `python3`。
- 不新增第四套数据源注册表；以 `DgProvider`、`DgEndpoint`、`DgQualityRule`、`DgIngestJob` 为控制面，并保持 `DataScript`、`ScheduledTask`、`TaskExecution` 的一个迭代兼容读路径。
- Airflow 是首选后端；`ORCHESTRATION_BACKEND=airflow` 或 `auto` 的 Airflow 不可达时必须自动切到 `apscheduler_fallback`，并在状态 API、日志和告警中显式显示降级，禁止静默回退。
- 回退和恢复不得制造双调度：所有任务都通过相同的数据库幂等键、任务认领和 scheduler lease；“至少一次执行、最多一次发布”是本迭代的正确性目标。
- Airflow 不直接以数据库配置生成为可执行 Python 代码；长期只保留固定 `data_ingest_dispatcher` 和 `data_ingest_run` DAG。
- 正式仓库表不得由非遗留 DataFrame 路径直接 `DROP TABLE`；必须执行“暂存 → 质量校验 → 原子发布 → 推进水位”。
- 密钥只由环境变量或部署密钥系统注入；契约清单、Airflow DAG、日志、测试夹具不得包含密码、token 或真实 API key。
- 所有时间写入 UTC，调度表达式按 `AKSHARE_SCHEDULER_TIMEZONE` 解释；每个 job 都持久化 `logical_date` 与 `business_date`。
- CI 使用隔离数据库、固定 fixture 与 mock provider；真实 AkShare/外部网络只作为 nightly 冒烟，不能代替 PR 的确定性测试。
- 本计划不授权在真实生产库、真实 Airflow 环境或真实外部数据源执行迁移、批量回填或回退演练。

---

## 1. 当前基线、目标边界与不可变决策

### 1.1 当前基线

| 领域 | 当前实现 | 本迭代处置 |
| --- | --- | --- |
| 数据目录 | `DgEndpoint` 已有参数、目标表、标准化、质量和增量字段，但没有不可变版本 | 扩展为 Endpoint + EndpointVersion；运行只引用版本 |
| 运行记录 | `DgIngestJob.idempotency_key` 非唯一，`TaskExecution` 偏 AkShare 脚本历史 | `DgIngestJob` 变为全局运行真源；`TaskExecution` 作为兼容投影 |
| 写入 | `AkshareDataService.persist_dataframe()` 可直接替换表 | 新发布器支持暂存、校验、原子替换/upsert/append |
| 调度 | `AkshareScheduler` 是 FastAPI 内存 APScheduler | Airflow 首选；APScheduler 仅由 lease 持有者作为降级后端运行 |
| Airflow | 有 Compose、REST adapter、callback、DAG generator，但 backend 操作仍为空实现 | 改为固定 DAG、真实 run 关联、回调幂等与对账 |
| 配置 | 脚本扫描和 provider factory 并存，存在遗留脚本直接写库 | P2 使用静态 manifest 编译为端点版本，遗留脚本经 adapter 接入 |

### 1.2 本迭代范围

Must：

- P0：版本化契约、统一 job 状态、幂等与安全发布、质量/水位、三类遗留试点。
- P1：Airflow 固定 DAG、Airflow 优先 + APScheduler 自动回退、可恢复交接、运行可观测性和灰度迁移。
- P2：静态 manifest、provider adapter 收敛、质量目录和运营管理界面。

非范围：

- 不一次性重写全部约 1100 个 `data_fetch` 脚本。
- 不把 Airflow metadata 库与应用 MySQL/Alembic schema 混用。
- 不为每一个 `ScheduledTask` 长期生成一份 Python DAG。
- 不承诺对不可幂等的外部 API 调用实现 exactly-once；只保证同一逻辑任务不重复发布正式数据。
- 不删除旧 `DataScript`、`ScheduledTask`、`TaskExecution` 表；删除要在独立后续迭代、迁移完成和保留期结束后处理。

### 1.3 调度故障回退决策

| 决策 | 固定方案 |
| --- | --- |
| 首选后端 | `airflow`；启动时先检查 Airflow REST `/health`、metadata database 和 scheduler 状态 |
| 启动时 Airflow 不可用 | 启动 `apscheduler_fallback`，状态为 `degraded`，记录原因和开始时间；应用本身仍可服务 |
| 运行时判定故障 | 连续 3 次健康检查失败，每次间隔 10 秒；任一次成功会清零失败计数 |
| 回退单实例 | 只有获取 `DgSchedulerLease` 的进程可启动 APScheduler；lease TTL 30 秒、每 10 秒续约 |
| 同一任务防重 | 以 `(endpoint_id, endpoint_version_id, business_date, params_hash)` 计算唯一幂等键，且 job 认领使用行锁与 lease epoch |
| Airflow 恢复 | 连续 3 次健康检查成功、冷却 120 秒后进入 `handoff_to_airflow`；回退后端停止认领新任务、等待执行中 job 完成或超时对账，再释放 lease |
| Airflow 恢复后处理 | Airflow dispatcher 获取新 epoch 的 lease，只认领 queued job；对 Airflow 旧 run 和 fallback running job 先 reconcile，不能重新发布 |
| 两端都不可用 | 状态为 `unavailable`，不伪造成功、不执行重复任务，产生高优先级告警；人工触发返回 503 并说明当前后端状态 |
| 强制模式 | `ORCHESTRATION_BACKEND=apscheduler` 为显式维护模式；其余模式均以 Airflow 优先并允许本计划规定的 fallback |

### 1.4 目标任务状态机

```text
queued
  -> dispatched
  -> running
  -> staged
  -> validated
  -> publishing
  -> published

queued/dispatched/running/staged/validated
  -> retry_wait
  -> queued

validated -> failed_quality
running   -> failed_terminal
queued    -> cancelled
```

`publishing` 表示已建立不可丢失的 publication journal，允许进程中断后由 reconciler 完成元数据提交。只有 `published` 可以写 `watermark_after`、更新 `DataTable` 的成功状态并对消费者声明新数据可用。`failed_quality`、`failed_terminal`、`cancelled` 和过期 lease 都不得更新水位。

---

## 2. 文件结构和职责边界

### 2.1 拟新增文件

```text
src/backend/
  alembic/versions/
    20260727_01_data_pipeline_contracts.py
    20260727_02_data_pipeline_publish.py
    20260727_03_orchestration_failover.py
  app/services/data_pipeline/
    __init__.py
    contracts.py             # endpoint version 解析、冻结和 manifest 校验
    job_service.py           # job 创建、认领、状态转换、幂等键
    publisher.py             # 暂存、质量后的发布、publication journal、watermark 提交
    quality.py               # 可配置质量规则和结构化结果
    scheduler_lease.py       # scheduler lease、epoch/fencing token
    reconciliation.py        # Airflow/fallback job 的对账与孤儿恢复
    legacy_adapter.py        # DataScript/AkshareToMySql 兼容适配
  airflow/dags/
    data_ingest_dispatcher.py
    data_ingest_run.py
  app/data_fetch/contracts/
    schema/endpoint-contract.schema.json
    providers/akshare.yaml
    endpoints/market/stock_daily_history.yaml
    endpoints/market/futures_daily.yaml
    endpoints/reference/trading_calendar.yaml
  tests/services/data_pipeline/
    test_contracts.py
    test_job_service.py
    test_publisher.py
    test_quality.py
    test_scheduler_lease.py
    test_reconciliation.py
    test_legacy_adapter.py
  tests/integration/
    test_data_ingest_pipeline.py
    test_airflow_failover.py
    test_airflow_recovery.py
  tests/airflow/
    test_data_ingest_dags.py
  docs/operations/akshare/
    airflow-failover-runbook.md
```

### 2.2 拟修改文件

| 文件 | 改造责任 |
| --- | --- |
| `src/backend/app/models/data_governance.py` | 添加 endpoint version、scheduler lease，扩展 job 字段与唯一约束 |
| `src/backend/app/models/akshare_mgmt.py` | `ScheduledTask` 增加后端归属；`TaskExecution` 关联 canonical job |
| `src/backend/app/services/data_connectors/registry.py` | 从 endpoint version 获取配置，创建真实 job，不再只有 preview 结果 |
| `src/backend/app/services/data_connectors/executor.py` | 变为 adapter 的受控执行入口，禁止任意动态 callable |
| `src/backend/app/services/akshare/data.py` | 旧 `persist_dataframe` 迁移至 publisher；保留遗留兼容入口 |
| `src/backend/app/services/akshare/script.py` | 经 `LegacyScriptAdapter` 运行，不能绕过 job/publisher |
| `src/backend/app/services/akshare/scheduler.py` | 仅实现 fallback 调度，不直接写正式数据或独立创建执行记录 |
| `src/backend/app/services/orchestration/*.py` | backend detector、Airflow backend、adapter 和 orchestration status 的真实实现 |
| `src/backend/app/api/airflow_callback.py` | 签名校验、job upsert、乱序/重复回调保护 |
| `src/backend/app/api/airflow_dags.py` | 暴露受权限保护的状态、运行、补数和日志代理接口 |
| `src/backend/app/startup/orchestration.py` | 启动 manager，不再通过异常分支静默启动 APScheduler |
| `src/backend/app/config.py`、`.env.example` | 后端优先级、健康检查、lease、回退和回切参数 |
| `docker/compose/airflow.yml` | 开发 Airflow、准确挂载路径、无硬编码凭据 |
| `docker/compose/airflow.production.yml` | CeleryExecutor、worker、Redis 连接和生产健康检查 |
| `src/frontend/src/api/airflow.ts` | orchestration 状态、job 列表、手工重跑/补数接口 |
| `src/frontend/src/views/...` | 数据管理页显示 active backend、降级原因、契约版本、质量与 run 链接 |

---

## 3. P0：数据契约、可靠发布与兼容试点

### Task 1: 版本化端点契约与数据库迁移

**Files:**
- Create: `src/backend/alembic/versions/20260727_01_data_pipeline_contracts.py`
- Modify: `src/backend/app/models/data_governance.py`
- Modify: `src/backend/app/models/akshare_mgmt.py`
- Create: `src/backend/tests/services/data_pipeline/test_contracts.py`

**Interfaces:**
- Consumes: `DgProvider`、`DgEndpoint`、`ScheduledTask`。
- Produces: `DgEndpointVersion`、`DgPublication`、`DgIngestJob.contract_version_id`、`DgIngestJob.idempotency_key` 的数据库唯一性，以及 `ScheduledTask.orchestrator_backend`。

- [ ] **Step 1: 写入失败测试，冻结 ORM 契约。**

```python
async def test_same_endpoint_version_and_logical_input_has_one_job(db_session):
    endpoint = await create_endpoint(db_session, endpoint_name="stock.daily_history")
    version = await publish_version(db_session, endpoint, version=1)
    await create_job(db_session, version.id, "2026-07-27", {"symbol": "000001"})
    with pytest.raises(IntegrityError):
        await create_job(db_session, version.id, "2026-07-27", {"symbol": "000001"})
```

- [ ] **Step 2: 运行测试确认当前模型未提供唯一运行契约。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_contracts.py::test_same_endpoint_version_and_logical_input_has_one_job -v`

Expected: FAIL，因为没有 `DgEndpointVersion`，或相同 `idempotency_key` 可重复写入。

- [ ] **Step 3: 定义模型、迁移和明确字段。**

```python
class DgEndpointVersion(Base):
    __tablename__ = "dg_endpoint_versions"
    id = Column(String(36), primary_key=True)
    endpoint_id = Column(String(36), ForeignKey("dg_endpoints.id"), nullable=False)
    version = Column(Integer, nullable=False)
    contract = Column(JSON, nullable=False)
    manifest_path = Column(String(255), nullable=True)
    manifest_sha256 = Column(String(64), nullable=False)
    status = Column(Enum(DgEndpointVersionStatus), nullable=False)
    published_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("endpoint_id", "version", name="uq_dg_endpoint_version"),)

class DgIngestJob(Base):
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_dg_ingest_job_idempotency"),)
    contract_version_id = Column(String(36), ForeignKey("dg_endpoint_versions.id"), nullable=False)
    logical_date = Column(DateTime, nullable=False)
    business_date = Column(Date, nullable=False)
    params_hash = Column(String(64), nullable=False)
    scheduler_backend = Column(String(32), nullable=False)
    scheduler_epoch = Column(Integer, nullable=False)

class DgPublication(Base):
    __tablename__ = "dg_publications"
    job_id = Column(String(36), ForeignKey("dg_ingest_jobs.id"), unique=True, nullable=False)
    target_table = Column(String(100), nullable=False)
    staging_table = Column(String(100), nullable=False)
    backup_table = Column(String(100), nullable=True)
    checksum = Column(String(64), nullable=False)
    state = Column(String(32), nullable=False)
```

迁移必须对已有 endpoint 创建 version `1`，由现有字段构造 contract JSON；已有 job 的 `contract_version_id` 关联到对应 endpoint 的 version `1`。`TaskExecution.ingest_job_id` 可空，以保证历史记录可升级。

- [ ] **Step 4: 运行迁移和模型测试。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_contracts.py -v`

Expected: PASS；重复逻辑输入被唯一约束拒绝，历史 endpoint 有可读取的 version `1`。

- [ ] **Step 5: 运行迁移三基线测试。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/migrations -v`

Expected: PASS；fresh、存量 Alembic 和 legacy `create_all` 三类库均到达单一 head。

- [ ] **Step 6: 提交本任务。**

```bash
git add src/backend/app/models/data_governance.py src/backend/app/models/akshare_mgmt.py src/backend/alembic/versions/20260727_01_data_pipeline_contracts.py src/backend/tests/services/data_pipeline/test_contracts.py
git commit -m "feat(data-governance): add versioned ingestion contracts"
```

### Task 2: Job 状态机、幂等键与原子认领

**Files:**
- Create: `src/backend/app/services/data_pipeline/job_service.py`
- Create: `src/backend/tests/services/data_pipeline/test_job_service.py`
- Modify: `src/backend/app/services/data_connectors/registry.py`

**Interfaces:**
- Consumes: `DgEndpointVersion.contract` 与 Task 1 的 `DgIngestJob`。
- Produces: `DataIngestJobService.create_or_get_job()`、`claim_job()`、`transition()` 和 `mark_retryable_failure()`。

- [ ] **Step 1: 写入并发认领失败测试。**

```python
async def test_only_one_worker_claims_a_queued_job(db_session_factory):
    job = await queued_job(db_session_factory)
    left, right = await asyncio.gather(
        claim_once(db_session_factory, job.id, "airflow", 7),
        claim_once(db_session_factory, job.id, "apscheduler_fallback", 8),
    )
    assert sorted([left, right]) == [False, True]
```

- [ ] **Step 2: 运行测试确认没有统一认领语义。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_job_service.py::test_only_one_worker_claims_a_queued_job -v`

Expected: FAIL，因为现有代码没有 `claim_job` 或两个执行路径能同时开始。

- [ ] **Step 3: 实现状态转换表与行锁认领。**

```python
ALLOWED_TRANSITIONS = {
    "queued": {"dispatched", "cancelled"},
    "dispatched": {"running", "retry_wait", "failed_terminal"},
    "running": {"staged", "retry_wait", "failed_terminal"},
    "staged": {"validated", "failed_quality", "retry_wait"},
    "validated": {"published", "failed_quality"},
    "retry_wait": {"queued", "failed_terminal"},
}

async def claim_job(self, job_id: str, backend: str, epoch: int) -> DgIngestJob | None:
    job = await self._select_for_update(job_id)
    if job.status != DgJobStatus.QUEUED:
        return None
    job.status = DgJobStatus.DISPATCHED
    job.scheduler_backend = backend
    job.scheduler_epoch = epoch
    return job
```

`create_or_get_job()` 使用 canonical JSON 序列化参数、SHA-256 计算 `params_hash` 和幂等键；发生唯一键冲突时重新读取已有 job，不能生成第二条任务。

- [ ] **Step 4: 运行 job service 测试。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_job_service.py -v`

Expected: PASS；并发认领只有一个成功，非法状态转换抛出 `InvalidJobTransitionError`。

- [ ] **Step 5: 接入 connector registry 的手工触发入口。**

```python
job = await job_service.create_or_get_job(
    endpoint_version=published_version,
    logical_date=utcnow(),
    business_date=resolved_business_date,
    params=request.params,
    trigger="manual",
)
return job_service.to_response(job)
```

该入口只能创建 job；执行由 P1 的 backend manager 决定，禁止 registry 直接写入数据表。

- [ ] **Step 6: 提交本任务。**

```bash
git add src/backend/app/services/data_pipeline/job_service.py src/backend/app/services/data_connectors/registry.py src/backend/tests/services/data_pipeline/test_job_service.py
git commit -m "feat(data-pipeline): add idempotent job state machine"
```

### Task 3: 暂存发布、upsert 与水位提交

**Files:**
- Create: `src/backend/alembic/versions/20260727_02_data_pipeline_publish.py`
- Create: `src/backend/app/services/data_pipeline/publisher.py`
- Modify: `src/backend/app/services/akshare/data.py`
- Create: `src/backend/tests/services/data_pipeline/test_publisher.py`

**Interfaces:**
- Consumes: `DgIngestJob`、endpoint contract 中的 `target`、`primary_key`、`write_mode`、`watermark`。
- Produces: `DataPublisher.stage()`、`validate_publishable()`、`publish()`，以及 `PublishResult`。

- [ ] **Step 1: 写入“质量失败不替换正式表”的失败测试。**

```python
async def test_failed_quality_keeps_previous_published_table(publisher, existing_table):
    staged = await publisher.stage(job_id="job-1", dataframe=bad_dataframe())
    with pytest.raises(QualityGateError):
        await publisher.publish(staged, quality_result={"passed": False})
    assert await existing_table.rows() == [{"symbol": "000001", "trade_date": "2026-07-26"}]
```

- [ ] **Step 2: 运行测试确认现有路径会覆盖正式表。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_publisher.py::test_failed_quality_keeps_previous_published_table -v`

Expected: FAIL，或无法导入 `DataPublisher`。

- [ ] **Step 3: 实现三种发布模式。**

```python
class DataPublisher:
    async def stage(self, job_id: str, dataframe: pd.DataFrame) -> StagedDataset: ...

    async def publish(self, staged: StagedDataset, quality_result: QualityResult) -> PublishResult:
        if not quality_result.passed:
            raise QualityGateError(quality_result.failures)
        if staged.write_mode == "snapshot_replace":
            await self._atomic_rename(staged.staging_table, staged.target_table)
        elif staged.write_mode == "upsert":
            await self._upsert_by_primary_key(staged)
        elif staged.write_mode == "append":
            await self._append_deduplicated(staged)
        else:
            raise UnsupportedWriteModeError(staged.write_mode)
        return PublishResult(table_name=staged.target_table, row_count=staged.row_count)
```

MySQL `snapshot_replace` 先创建唯一的 `DgPublication(state="prepared")` 记录；若 target 已存在，执行单条原子 DDL `RENAME TABLE target TO backup, staging TO target`，否则执行 `RENAME TABLE staging TO target`。DDL 后将 journal 写为 `renamed`，再在应用数据库事务中更新 `DataTable`、watermark 和 job 状态 `published`。MySQL DDL 会隐式提交，因此元数据写失败时不得删除 backup 或再次盲目替换；保留 `renamed` journal，由 Task 9 的 reconciler 按 table 名和 checksum 完成提交。`upsert` 只接受契约声明的主键，并建立唯一索引；`append` 必须有事件去重键。

- [ ] **Step 4: 用 DataPublisher 重构非遗留 `persist_dataframe`。**

`AkshareDataService.persist_dataframe()` 保留公共签名，但创建临时 contract 并委托 `DataPublisher`；删除其中直接对正式表执行 `DROP TABLE IF EXISTS` 的路径。遗留脚本先保留 `sync_existing_table_metadata()`，由 Task 5 接管。

- [ ] **Step 5: 运行发布和历史回归测试。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_publisher.py tests/services/akshare/test_data.py -v`

Expected: PASS；失败质量、不完整历史数据、重复 upsert 和 snapshot replace 均不丢失已发布数据。

- [ ] **Step 6: 提交本任务。**

```bash
git add src/backend/app/services/data_pipeline/publisher.py src/backend/app/services/akshare/data.py src/backend/alembic/versions/20260727_02_data_pipeline_publish.py src/backend/tests/services/data_pipeline/test_publisher.py
git commit -m "feat(data-pipeline): publish staged data atomically"
```

### Task 4: 可配置质量规则与水位语义

**Files:**
- Create: `src/backend/app/services/data_pipeline/quality.py`
- Create: `src/backend/tests/services/data_pipeline/test_quality.py`
- Modify: `src/backend/app/services/market_data_coverage_service.py`
- Modify: `src/backend/app/services/market_data_precheck_service.py`

**Interfaces:**
- Consumes: contract 的 `schema`、`primary_key`、`quality_rules`、`watermark`。
- Produces: `QualityResult(passed, warnings, failures, metrics)` 和消费者可读取的 freshness/coverage 状态。

- [ ] **Step 1: 写入主键重复和 freshness 失败测试。**

```python
def test_quality_rejects_duplicate_primary_key_and_stale_business_date():
    result = evaluate_quality(
        dataframe=duplicate_rows(),
        contract=stock_contract(max_staleness_days=1),
        business_date=date(2026, 7, 27),
    )
    assert result.passed is False
    assert {failure.code for failure in result.failures} == {"duplicate_primary_key", "stale_data"}
```

- [ ] **Step 2: 运行测试确认硬编码覆盖配置无法满足端点质量契约。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_quality.py::test_quality_rejects_duplicate_primary_key_and_stale_business_date -v`

Expected: FAIL，因为 `evaluate_quality` 尚不存在。

- [ ] **Step 3: 实现固定规则集合与结构化结果。**

```python
QUALITY_RULES = {
    "schema": validate_schema,
    "non_empty": validate_non_empty,
    "primary_key_unique": validate_primary_key_unique,
    "row_count_threshold": validate_row_count,
    "freshness": validate_freshness,
    "business_date_coverage": validate_business_date_coverage,
}

def evaluate_quality(dataframe: pd.DataFrame, contract: dict, business_date: date) -> QualityResult:
    results = [QUALITY_RULES[item["type"]](dataframe, item, business_date) for item in contract["quality_rules"]]
    return QualityResult.from_rule_results(results)
```

将 `market_data_coverage_service` 中的表名硬编码逐步改为读取已发布 contract 的 coverage profile；`market_data_precheck_service` 读取最后一次 `published` job 的质量结果，而不是仅看表是否存在。

- [ ] **Step 4: 运行质量、覆盖率和预检测试。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_quality.py tests/services/market_data -v`

Expected: PASS；失败 quality 不推进 watermark，消费者能区分“无数据”“旧数据”“最新发布失败”。

- [ ] **Step 5: 提交本任务。**

```bash
git add src/backend/app/services/data_pipeline/quality.py src/backend/app/services/market_data_coverage_service.py src/backend/app/services/market_data_precheck_service.py src/backend/tests/services/data_pipeline/test_quality.py
git commit -m "feat(data-quality): make ingestion quality contract-driven"
```

### Task 5: 遗留脚本适配与 P0 三类试点

**Files:**
- Create: `src/backend/app/services/data_pipeline/legacy_adapter.py`
- Modify: `src/backend/app/services/akshare/script.py`
- Create: `src/backend/tests/services/data_pipeline/test_legacy_adapter.py`
- Create: `src/backend/tests/integration/test_data_ingest_pipeline.py`

**Interfaces:**
- Consumes: `DataScript`、`AkshareToMySql`、`DataIngestJobService`、`DataPublisher`。
- Produces: `LegacyScriptAdapter.execute(job_id)`，为 legacy 和 DataFrame 脚本返回相同 `ExecutionDataset`。

- [ ] **Step 1: 写入三种脚本形态的兼容测试。**

```python
@pytest.mark.parametrize("kind", ["dataframe", "legacy_mysql_writer", "incremental_history"])
async def test_legacy_adapter_returns_canonical_execution_dataset(kind, adapter, job):
    dataset = await adapter.execute(job, fixture_script(kind))
    assert dataset.table_name
    assert dataset.row_count >= 0
    assert dataset.source_metadata["kind"] == kind
```

- [ ] **Step 2: 运行测试确认现有 `run_script` 会绕过统一 job/publisher。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_legacy_adapter.py -v`

Expected: FAIL，因为不存在 adapter，且 legacy 与 DataFrame 返回路径不一致。

- [ ] **Step 3: 实现 adapter 和脚本服务委托。**

```python
class LegacyScriptAdapter:
    async def execute(self, job: DgIngestJob, script: DataScript) -> ExecutionDataset:
        callable_obj = await self._resolve_approved_callable(script)
        result = await self._execute_with_timeout(callable_obj, job.params, script.timeout)
        if self._is_legacy_writer(callable_obj):
            return await self._inspect_legacy_output(job, script, result)
        return ExecutionDataset.from_dataframe(self._coerce_dataframe(result))
```

`AkshareScriptService.run_script()` 先创建/读取 canonical job，再委托 adapter；DataFrame 输出进入 Task 3 publisher，legacy writer 只允许在试点阶段通过 metadata inspection 完成，不能同时由两个路径发布同一表。

- [ ] **Step 4: 为三个试点建立确定性 fixture 和端到端断言。**

```python
async def test_retry_of_same_logical_day_publishes_once(test_pipeline):
    first = await test_pipeline.run("stock.daily_history", "2026-07-27", {"symbol": "000001"})
    second = await test_pipeline.run("stock.daily_history", "2026-07-27", {"symbol": "000001"})
    assert first.job_id == second.job_id
    assert await test_pipeline.published_row_count() == first.rows_after
```

- [ ] **Step 5: 运行 P0 完整验收。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline tests/integration/test_data_ingest_pipeline.py -v`

Expected: PASS；三类脚本均能重复运行、失败不会覆盖旧数据、质量成功后才更新水位。

- [ ] **Step 6: 提交本任务。**

```bash
git add src/backend/app/services/data_pipeline/legacy_adapter.py src/backend/app/services/akshare/script.py src/backend/tests/services/data_pipeline/test_legacy_adapter.py src/backend/tests/integration/test_data_ingest_pipeline.py
git commit -m "feat(data-pipeline): route legacy scripts through canonical jobs"
```

---

## 4. P1：Airflow 首选与 APScheduler 受控回退

### Task 6: Airflow 部署、健康契约和运行配置

**Files:**
- Modify: `docker/compose/airflow.yml`
- Create: `docker/compose/airflow.production.yml`
- Modify: `src/backend/app/config.py`
- Modify: `src/backend/.env.example`
- Create: `src/backend/tests/test_orchestration/test_airflow_configuration.py`

**Interfaces:**
- Consumes: `AIRFLOW_API_BASE_URL`、应用数据库连接、Airflow metadata PostgreSQL。
- Produces: `OrchestrationSettings` 和可验证的 `AirflowHealth(status, checked_at, detail)`。

- [ ] **Step 1: 写入配置默认值与故障阈值测试。**

```python
def test_orchestration_settings_default_to_airflow_preferred_with_fallback():
    settings = Settings(ORCHESTRATION_BACKEND="auto")
    assert settings.ORCHESTRATION_FALLBACK_BACKEND == "apscheduler"
    assert settings.ORCHESTRATION_AIRFLOW_FAILURE_THRESHOLD == 3
    assert settings.ORCHESTRATION_AIRFLOW_SUCCESS_THRESHOLD == 3
    assert settings.ORCHESTRATION_SCHEDULER_LEASE_TTL_SECONDS == 30
```

- [ ] **Step 2: 运行测试确认没有完整的 failover 参数。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_orchestration/test_airflow_configuration.py -v`

Expected: FAIL，因为设置尚未定义。

- [ ] **Step 3: 增加固定配置并安全化 Compose。**

```python
ORCHESTRATION_FALLBACK_BACKEND: Literal["apscheduler"] = "apscheduler"
ORCHESTRATION_AIRFLOW_FAILURE_THRESHOLD: int = 3
ORCHESTRATION_AIRFLOW_SUCCESS_THRESHOLD: int = 3
ORCHESTRATION_HEALTH_CHECK_INTERVAL_SECONDS: int = 10
ORCHESTRATION_HANDOFF_COOLDOWN_SECONDS: int = 120
ORCHESTRATION_SCHEDULER_LEASE_TTL_SECONDS: int = 30
```

`docker/compose/airflow.yml` 仅用于开发，使用 `LocalExecutor`，将 DAG 挂载为 `../src/backend/airflow/dags:/opt/airflow/dags:ro`，应用包挂载为 `../src/backend:/opt/airflow/app:ro`。管理员密码、Airflow API 凭据、callback secret 必须用 `${VAR:?required}` 注入；不保留 `admin/admin`。`airflow.production.yml` 设为 `CeleryExecutor`，添加 `airflow-worker`，使用受控 Redis 和独立 Airflow PostgreSQL。

- [ ] **Step 4: 实现严格 health check。**

```python
@dataclass(frozen=True)
class AirflowHealth:
    status: Literal["healthy", "unhealthy"]
    checked_at: datetime
    detail: str

    @property
    def healthy(self) -> bool:
        return self.status == "healthy"

async def health_check(self) -> AirflowHealth:
    payload = await self._client.get("/health")
    healthy = (
        payload.status_code == 200
        and payload.json()["metadatabase"]["status"] == "healthy"
        and payload.json()["scheduler"]["status"] == "healthy"
    )
    return AirflowHealth(status="healthy" if healthy else "unhealthy", checked_at=utcnow(), detail=payload.text[:200])
```

- [ ] **Step 5: 运行配置和 Compose 解析验证。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_orchestration/test_airflow_configuration.py -v`

Run: `cd docker && docker compose -f docker-compose.yml -f compose/airflow.yml config --quiet`

Expected: PASS；Compose 可解析，开发与生产凭据都不在版本控制文本中。

- [ ] **Step 6: 提交本任务。**

```bash
git add docker/compose/airflow.yml docker/compose/airflow.production.yml src/backend/app/config.py src/backend/.env.example src/backend/tests/test_orchestration/test_airflow_configuration.py
git commit -m "feat(airflow): add secure health and failover configuration"
```

### Task 7: Scheduler lease、Airflow 优先检测与 APScheduler fallback

**Files:**
- Create: `src/backend/alembic/versions/20260727_03_orchestration_failover.py`
- Create: `src/backend/app/services/data_pipeline/scheduler_lease.py`
- Modify: `src/backend/app/services/orchestration/detector.py`
- Modify: `src/backend/app/services/orchestration/airflow_backend.py`
- Modify: `src/backend/app/services/orchestration/apscheduler_backend.py`
- Modify: `src/backend/app/services/akshare/scheduler.py`
- Modify: `src/backend/app/startup/orchestration.py`
- Create: `src/backend/tests/services/data_pipeline/test_scheduler_lease.py`
- Create: `src/backend/tests/integration/test_airflow_failover.py`

**Interfaces:**
- Consumes: Task 2 的 `claim_job()`，Task 6 的 health check。
- Produces: `SchedulerLeaseService.acquire()`、`renew()`、`release()`；`OrchestrationManager.start()` 和 `OrchestrationStatus`。

- [ ] **Step 1: 写入“两个应用副本只能有一个 fallback 调度器”的失败测试。**

```python
async def test_only_one_process_can_hold_fallback_scheduler_lease(session_factory):
    service_a = SchedulerLeaseService(session_factory, owner_id="api-a")
    service_b = SchedulerLeaseService(session_factory, owner_id="api-b")
    first = await service_a.acquire("apscheduler_fallback", ttl_seconds=30)
    second = await service_b.acquire("apscheduler_fallback", ttl_seconds=30)
    assert first is not None
    assert second is None
```

- [ ] **Step 2: 运行测试确认当前 APScheduler 可在多个进程内同时启动。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_scheduler_lease.py::test_only_one_process_can_hold_fallback_scheduler_lease -v`

Expected: FAIL，因为 lease 服务和表不存在。

- [ ] **Step 3: 实现 lease 与 fencing token。**

```python
class DgSchedulerLease(Base):
    __tablename__ = "dg_scheduler_leases"
    lease_name = Column(String(64), primary_key=True)
    owner_id = Column(String(128), nullable=False)
    backend = Column(String(32), nullable=False)
    epoch = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)

async def acquire(self, backend: str, ttl_seconds: int) -> SchedulerLease | None:
    lease = await self._select_lease_for_update("data_ingestion")
    if lease and lease.expires_at > utcnow() and lease.owner_id != self.owner_id:
        return None
    return await self._write_new_epoch(backend, ttl_seconds)
```

`epoch` 每次持有者变化递增。所有 `claim_job()` 和 `publish()` 都比较 job 的 `scheduler_epoch` 与当前 lease epoch；不匹配的陈旧 worker 可以结束采集，但不得发布。

- [ ] **Step 4: 实现 failover manager，禁止异常分支静默启动 scheduler。**

```python
async def choose_backend(self) -> OrchestrationStatus:
    health = await self.airflow_adapter.health_check()
    if health.healthy:
        return await self._activate_airflow_if_handoff_safe()
    return await self._activate_fallback(
        reason=health.detail,
        required_failures=self.settings.ORCHESTRATION_AIRFLOW_FAILURE_THRESHOLD,
    )
```

启动时 Airflow healthy 则持有 `airflow` lease 并启动 `AirflowBackend`；启动时 unhealthy 则尝试 `apscheduler_fallback` lease 并启动 fallback。运行时健康监控连续失败三次才切换，连续成功三次并冷却完成才回切。当前 `startup/orchestration.py` 的 broad `except` fallback 改为调用该 manager；任何状态改变写结构化日志和审计事件。

- [ ] **Step 5: 将 APScheduler 收敛为 fallback backend。**

```python
async def run_task_now(self, task_id: int, operator_id: str | None = None) -> DgIngestJob:
    job = await self.job_service.create_or_get_job_for_scheduled_task(task_id, operator_id)
    lease = await self.lease_service.current()
    claimed = await self.job_service.claim_job(job.id, "apscheduler_fallback", lease.epoch)
    if claimed is None:
        return job
    return await self.pipeline.execute(claimed.id, lease.epoch)
```

fallback 不再调用 `AkshareScriptService.run_script()` 后立即独立写 `TaskExecution`；它必须走 canonical job、adapter、quality、publisher。

- [ ] **Step 6: 运行 lease 与回退测试。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_scheduler_lease.py tests/integration/test_airflow_failover.py -v`

Expected: PASS；Airflow 启动不可达时 fallback 被显式启用；两个 API 实例只有一个 scheduler；同一 logical job 不重复执行。

- [ ] **Step 7: 提交本任务。**

```bash
git add src/backend/alembic/versions/20260727_03_orchestration_failover.py src/backend/app/services/data_pipeline/scheduler_lease.py src/backend/app/services/orchestration src/backend/app/services/akshare/scheduler.py src/backend/app/startup/orchestration.py src/backend/tests/services/data_pipeline/test_scheduler_lease.py src/backend/tests/integration/test_airflow_failover.py
git commit -m "feat(orchestration): fail over safely to apscheduler"
```

### Task 8: 固定 Airflow dispatcher 与 execution DAG

**Files:**
- Create: `src/backend/airflow/dags/data_ingest_dispatcher.py`
- Create: `src/backend/airflow/dags/data_ingest_run.py`
- Create: `src/backend/tests/airflow/test_data_ingest_dags.py`
- Modify: `src/backend/app/services/orchestration/airflow_adapter.py`
- Modify: `src/backend/app/services/orchestration/airflow_backend.py`
- Modify: `src/backend/app/services/orchestration/dag_generator.py`
- Modify: `src/backend/app/services/orchestration/migration.py`

**Interfaces:**
- Consumes: `DataIngestJobService.claim_due_jobs()`、lease epoch、published endpoint version。
- Produces: 固定 DAG `data_ingest_dispatcher` 与 `data_ingest_run`，并将 Airflow `dag_run_id` 写入 job。

- [ ] **Step 1: 写入 DAG 结构测试。**

```python
def test_dispatcher_and_run_dags_have_expected_ids(dagbag):
    assert dagbag.get_dag("data_ingest_dispatcher") is not None
    run_dag = dagbag.get_dag("data_ingest_run")
    assert [task.task_id for task in run_dag.tasks] == [
        "load_job", "extract", "normalize", "stage", "quality", "publish", "finalize"
    ]
```

- [ ] **Step 2: 运行测试确认仓库没有固定生产 DAG。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/airflow/test_data_ingest_dags.py::test_dispatcher_and_run_dags_have_expected_ids -v`

Expected: FAIL，因为 DAG 文件和任务图不存在。

- [ ] **Step 3: 实现 dispatcher DAG。**

```python
with DAG(
    dag_id="data_ingest_dispatcher",
    schedule="*/1 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["data-ingestion", "dispatcher"],
) as dispatcher:
    @task
    def claim_due_job_confs() -> list[dict[str, str]]:
        job_ids = run_async(DataIngestJobService.from_settings().claim_due_jobs("airflow"))
        return [{"job_id": job_id} for job_id in job_ids]

    TriggerDagRunOperator.partial(
        task_id="trigger_ingest_run",
        trigger_dag_id="data_ingest_run",
        wait_for_completion=False,
    ).expand(conf=claim_due_job_confs())
```

实现时不得在 DAG parse 阶段访问应用数据库；数据库查询只能发生在 task runtime。dispatcher 未持有 `airflow` lease 时返回空列表。

- [ ] **Step 4: 实现 execution DAG 和可重试边界。**

```python
@task(retries=3, retry_delay=timedelta(minutes=5), execution_timeout=timedelta(minutes=5))
def extract(job_id: str) -> DatasetRef:
    return run_async(PipelineExecutor.from_settings().extract(job_id))

@task(retries=0)
def publish(job_id: str, quality: QualityResult) -> PublishResult:
    return run_async(PipelineExecutor.from_settings().publish(job_id, quality))
```

`extract`、`normalize`、`stage` 可按 contract 的 retry policy 重试；`quality` 与 `publish` 不由 Airflow 盲重试，而由 job 状态机和幂等发布器决定。每个 provider 使用 Airflow Pool，例如 `akshare_pool`，并发上限由 contract 的 provider policy 映射。

- [ ] **Step 5: 替换动态 DAG 主路径。**

`DAGGenerator` 和 `MigrationTool` 改为生成迁移报告：校验所有任务能映射到 endpoint version、标出不兼容脚本、设置其 `orchestrator_backend`，但不再写 `dag_<script>.py`。`AirflowBackend.run_task_now()` 触发 `data_ingest_run`，conf 只包含已创建的 `job_id`。

- [ ] **Step 6: 运行 DAG 与 adapter 测试。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/airflow/test_data_ingest_dags.py tests/test_orchestration/test_airflow_adapter.py -v`

Expected: PASS；DAG 可被 DagBag 解析，手工 trigger 只传 job ID，旧动态 DAG 不再是调度主路径。

- [ ] **Step 7: 提交本任务。**

```bash
git add src/backend/airflow/dags src/backend/tests/airflow src/backend/app/services/orchestration/airflow_adapter.py src/backend/app/services/orchestration/airflow_backend.py src/backend/app/services/orchestration/dag_generator.py src/backend/app/services/orchestration/migration.py
git commit -m "feat(airflow): add fixed ingestion dags"
```

### Task 9: Callback 幂等、Airflow 对账和安全回切

**Files:**
- Modify: `src/backend/app/api/airflow_callback.py`
- Modify: `src/backend/app/schemas/airflow.py`
- Create: `src/backend/app/services/data_pipeline/reconciliation.py`
- Create: `src/backend/tests/services/data_pipeline/test_reconciliation.py`
- Create: `src/backend/tests/integration/test_airflow_recovery.py`

**Interfaces:**
- Consumes: Airflow DAG callback、`airflow_run_id`、scheduler lease epoch。
- Produces: `IngestionReconciler.reconcile()`、signed `AirflowCallbackPayload` 和 `handoff_to_airflow()`。

- [ ] **Step 1: 写入重复回调和旧 epoch 的失败测试。**

```python
async def test_duplicate_callback_updates_one_job_and_stale_epoch_cannot_publish(client, job):
    first = await signed_callback(client, job, status="success", epoch=9)
    duplicate = await signed_callback(client, job, status="success", epoch=9)
    stale = await signed_callback(client, job, status="success", epoch=8)
    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert stale.status_code == 409
    assert await count_jobs(job.idempotency_key) == 1
```

- [ ] **Step 2: 运行测试确认 callback 会直接新增 `TaskExecution`。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_reconciliation.py -v`

Expected: FAIL，因为 callback 没有签名、epoch 校验或 job upsert。

- [ ] **Step 3: 扩展 callback payload 并实现 HMAC 验证。**

```python
class AirflowCallbackPayload(BaseModel):
    job_id: str
    dag_id: str
    dag_run_id: str
    task_id: str
    status: Literal["running", "success", "failed", "retrying", "skipped", "cancelled"]
    scheduler_epoch: int
    occurred_at: datetime
    result: dict[str, Any] | None = None

def verify_callback_signature(raw_body: bytes, signature: str, secret: str) -> None:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="invalid_airflow_callback_signature")
```

callback 按 `job_id` 加锁更新，不创建第二个运行记录；在 `TaskExecution` 中只写兼容投影。请求 job 的 `scheduler_epoch`、DAG ID 和 run ID 不一致时返回 409。

- [ ] **Step 4: 实现对账和自动回切。**

```python
async def handoff_to_airflow(self) -> OrchestrationStatus:
    await self.fallback.stop_accepting_new_jobs()
    await self.reconciler.reconcile_running_jobs()
    if await self.job_service.has_active_jobs("apscheduler_fallback"):
        return OrchestrationStatus.handoff_waiting()
    await self.lease_service.release("apscheduler_fallback")
    lease = await self.lease_service.acquire("airflow", ttl_seconds=30)
    return OrchestrationStatus.airflow_active(lease.epoch)
```

对账逻辑优先读取 Airflow REST 的 dag run/task instance；找不到 run 的 `dispatched` job 在 lease 到期后回到 `queued`，已 `staged` 的 job 先检查 staging checksum 和 quality result，再决定重新执行或标记 `failed_terminal`。回切前 fallback 不认领新任务，保证没有两个后端竞争发布。

- [ ] **Step 5: 运行 recovery 集成测试。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_reconciliation.py tests/integration/test_airflow_recovery.py -v`

Expected: PASS；重复/乱序 callback 安全，Airflow 恢复只在 fallback 无 active job 后接管，stale worker 无法发布。

- [ ] **Step 6: 提交本任务。**

```bash
git add src/backend/app/api/airflow_callback.py src/backend/app/schemas/airflow.py src/backend/app/services/data_pipeline/reconciliation.py src/backend/tests/services/data_pipeline/test_reconciliation.py src/backend/tests/integration/test_airflow_recovery.py
git commit -m "feat(airflow): reconcile runs and hand off safely"
```

### Task 10: 后端 API、灰度迁移、运行状态与回退演练

**Files:**
- Modify: `src/backend/app/api/airflow_dags.py`
- Modify: `src/backend/app/services/akshare/scheduler_service.py`
- Modify: `src/backend/app/services/orchestration/migration.py`
- Modify: `src/frontend/src/api/airflow.ts`
- Modify: `src/frontend/src/views/investment/` 中的数据管理相关页面
- Create: `src/backend/tests/test_orchestration/test_failover_api.py`
- Create: `docs/operations/akshare/airflow-failover-runbook.md`

**Interfaces:**
- Consumes: `OrchestrationStatus`、`DgIngestJob`、`ScheduledTask.orchestrator_backend`。
- Produces: `/api/v1/data/airflow/orchestration/status` 的受认证状态响应、受权限保护的重跑/补数请求和回退操作手册。

- [ ] **Step 1: 写入降级状态 API 测试。**

```python
async def test_status_reports_explicit_apscheduler_fallback(client, auth_headers, manager):
    manager.force_status("apscheduler_fallback", reason="airflow_healthcheck_timeout", epoch=12)
    response = await client.get("/api/v1/data/airflow/orchestration/status", headers=auth_headers)
    assert response.json() == {
        "backend_type": "apscheduler_fallback",
        "state": "degraded",
        "reason": "airflow_healthcheck_timeout",
        "scheduler_epoch": 12,
    }
```

- [ ] **Step 2: 运行测试确认前端/API 仅能看到 backend 类型或隐藏 fallback。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_orchestration/test_failover_api.py -v`

Expected: FAIL，因为响应没有降级语义和 epoch。

- [ ] **Step 3: 实现状态、重跑和补数 API。**

```python
class OrchestrationStatusResponse(BaseModel):
    backend_type: Literal["airflow", "apscheduler_fallback", "unavailable"]
    state: Literal["active", "degraded", "handoff_waiting", "unavailable"]
    reason: str | None
    scheduler_epoch: int | None
    last_airflow_healthcheck_at: datetime | None
```

手工重跑和补数只创建携带指定 `business_date` 的 canonical job；若 `backend_type == "unavailable"`，返回 503。页面显示当前后端、降级原因、开始时间、活跃任务数、契约版本和 Airflow run 链接；未授权用户不能触发、暂停或查看原始失败堆栈。

- [ ] **Step 4: 实施灰度迁移工具。**

```python
async def migrate_task(task_id: int) -> MigrationResult:
    task = await self._load_task(task_id)
    version = await self._resolve_published_version(task.script_id)
    await self._validate_task_contract(task, version)
    await self._set_backend(task, "airflow_shadow")
    return MigrationResult(task_id=task_id, endpoint_version_id=version.id, state="shadow_ready")
```

迁移顺序固定为：导出任务清单 → contract 校验 → shadow 暂存运行 → 行数/schema/日期范围比较 → 暂停该任务 APScheduler → 设置 `airflow` → 完整周期观察。回滚固定为：暂停 Airflow 认领 → 运行中 job 对账 → 设置该任务 `apscheduler` → 启动 fallback 重载；禁止两个后端同时为同一 task 设 active。

- [ ] **Step 5: 编写并验证 runbook。**

runbook 必须包含：启动时 fallback、运行时 Airflow 故障、Airflow 恢复回切、两端不可用、单任务灰度、单任务回滚、如何通过 job ID、idempotency key、lease epoch 和 Airflow run ID 收集证据。

- [ ] **Step 6: 运行 API、前端和手工演练的自动化覆盖。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_orchestration/test_failover_api.py tests/integration/test_airflow_failover.py tests/integration/test_airflow_recovery.py -v`

Run: `cd src/frontend && npm run test -- --run src/__tests__/api/airflow.test.ts`

Expected: PASS；切换、回切、单任务回滚和不可用状态均可从 API/UI 观察。

- [ ] **Step 7: 提交本任务。**

```bash
git add src/backend/app/api/airflow_dags.py src/backend/app/services/akshare/scheduler_service.py src/backend/app/services/orchestration/migration.py src/backend/tests/test_orchestration/test_failover_api.py src/frontend/src/api/airflow.ts src/frontend/src/views/investment docs/operations/akshare/airflow-failover-runbook.md
git commit -m "feat(orchestration): expose failover status and migration controls"
```

---

## 5. P2：静态配置、Provider 收敛与运营治理

### Task 11: 静态 manifest、schema 校验和发布编译

**Files:**
- Create: `src/backend/app/data_fetch/contracts/schema/endpoint-contract.schema.json`
- Create: `src/backend/app/data_fetch/contracts/providers/akshare.yaml`
- Create: `src/backend/app/data_fetch/contracts/endpoints/market/stock_daily_history.yaml`
- Create: `src/backend/app/data_fetch/contracts/endpoints/market/futures_daily.yaml`
- Create: `src/backend/app/data_fetch/contracts/endpoints/reference/trading_calendar.yaml`
- Create: `src/backend/app/services/data_pipeline/contracts.py`
- Create: `src/backend/tests/services/data_pipeline/test_contracts.py`（扩展）
- Create: `src/backend/tests/contracts/test_contract_manifest.py`

**Interfaces:**
- Consumes: YAML manifest、JSON Schema、已存在 provider registry。
- Produces: `ContractCompiler.load_and_validate(path)` 与 `publish_manifest(path, actor_id)`。

- [ ] **Step 1: 写入 schema 违规测试。**

```python
def test_manifest_rejects_missing_primary_key_for_upsert(tmp_path):
    path = write_manifest(tmp_path, write_mode="upsert", primary_key=[])
    with pytest.raises(ContractValidationError, match="target.primary_key"):
        ContractCompiler().load_and_validate(path)
```

- [ ] **Step 2: 运行测试确认当前配置不能由静态文件校验。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/contracts/test_contract_manifest.py::test_manifest_rejects_missing_primary_key_for_upsert -v`

Expected: FAIL，因为 compiler 和 schema 不存在。

- [ ] **Step 3: 固化 manifest 结构。**

```yaml
endpoint: market.stock_daily_history
provider: akshare
adapter: akshare.stock_zh_a_hist
target:
  database: akshare_data
  table: market_stock_daily
  write_mode: upsert
  primary_key: [symbol, trade_date]
watermark:
  column: trade_date
quality_rules:
  - type: schema
  - type: primary_key_unique
  - type: freshness
execution:
  timeout_seconds: 300
  retries: 3
  pool: akshare_pool
```

compiler 解析 YAML 后以 canonical JSON 计算 SHA-256，将内容写入新的 `DgEndpointVersion`；相同 hash 不创建重复版本。manifest 中出现 `password`、`secret`、`token`、`api_key` 字段时必须拒绝。

- [ ] **Step 4: 运行 schema 和发布版本测试。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/contracts/test_contract_manifest.py tests/services/data_pipeline/test_contracts.py -v`

Expected: PASS；三个试点 manifest 可发布，非法 schema 和敏感字段被拒绝。

- [ ] **Step 5: 提交本任务。**

```bash
git add src/backend/app/data_fetch/contracts src/backend/app/services/data_pipeline/contracts.py src/backend/tests/contracts src/backend/tests/services/data_pipeline/test_contracts.py
git commit -m "feat(data-contracts): compile validated endpoint manifests"
```

### Task 12: ProviderAdapter 收敛与遗留 provider 隔离

**Files:**
- Modify: `src/backend/app/services/data_connectors/executor.py`
- Modify: `src/backend/app/data_fetch/providers/factory.py`
- Modify: `src/backend/app/data_fetch/providers/akshare_provider.py`
- Modify: `src/backend/app/data_fetch/providers/akshare_to_mysql.py`
- Create: `src/backend/app/services/data_pipeline/provider_adapter.py`
- Create: `src/backend/tests/services/data_pipeline/test_provider_adapter.py`

**Interfaces:**
- Consumes: manifest 的 `provider`、`adapter` 和 execution policy。
- Produces: `ProviderAdapter.extract()`、`normalize()`、`classify_error()`、`health_check()`。

- [ ] **Step 1: 写入 allowlist 与错误分类测试。**

```python
async def test_adapter_rejects_unregistered_function_path(adapter_registry):
    with pytest.raises(UnapprovedAdapterError):
        await adapter_registry.resolve("os.system")

def test_rate_limit_error_is_retryable():
    assert classify_error(RateLimitError("429")) == ProviderFailure(retryable=True, code="rate_limited")
```

- [ ] **Step 2: 运行测试确认 executor 允许任意动态 import。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_provider_adapter.py -v`

Expected: FAIL，因为 registry/错误分类契约不存在。

- [ ] **Step 3: 实现受控 adapter registry。**

```python
class ProviderAdapter(Protocol):
    async def extract(self, params: dict[str, Any]) -> pd.DataFrame: ...
    def normalize(self, dataframe: pd.DataFrame, contract: dict[str, Any]) -> pd.DataFrame: ...
    def classify_error(self, exc: Exception) -> ProviderFailure: ...

APPROVED_ADAPTERS = {
    "akshare.stock_zh_a_hist": AkshareStockHistoryAdapter,
    "akshare.futures_daily": AkshareFuturesDailyAdapter,
    "akshare.trading_calendar": AkshareTradingCalendarAdapter,
}
```

只有 `APPROVED_ADAPTERS` 能由 manifest 引用。`AkshareToMySql` 保留为 `LegacyScriptAdapter` 内部实现，不再对新 endpoint 暴露“脚本自己建表/写表”的 API。

- [ ] **Step 4: 运行 provider、P0 pipeline 和安全回归。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline/test_provider_adapter.py tests/services/data_pipeline/test_legacy_adapter.py tests/integration/test_data_ingest_pipeline.py -v`

Expected: PASS；未登记 adapter 不可执行，429/timeout 可重试，schema 错误不可重试。

- [ ] **Step 5: 提交本任务。**

```bash
git add src/backend/app/services/data_pipeline/provider_adapter.py src/backend/app/services/data_connectors/executor.py src/backend/app/data_fetch/providers src/backend/tests/services/data_pipeline/test_provider_adapter.py
git commit -m "refactor(data-providers): route sources through approved adapters"
```

### Task 13: 数据治理运营界面、质量可视化和审计

**Files:**
- Modify: `src/backend/app/api/airflow_dags.py`
- Modify: `src/backend/app/services/data_connectors/registry.py`
- Modify: `src/frontend/src/api/airflow.ts`
- Create: `src/frontend/src/api/dataGovernance.ts`
- Modify: 数据管理相关 Vue 页面和 Pinia store
- Create: `src/backend/tests/test_api/test_data_governance_runs.py`
- Create: `src/frontend/src/__tests__/views/DataGovernancePage.test.ts`

**Interfaces:**
- Consumes: endpoint version、job、quality result、orchestration status。
- Produces: endpoint catalogue、job list/detail、手工补数/重跑请求和只读 Airflow log 链接。

- [ ] **Step 1: 写入 job detail API 和降级 UI 测试。**

```python
async def test_job_detail_exposes_contract_quality_and_backend(client, auth_headers, published_job):
    response = await client.get(f"/api/v1/data/governance/jobs/{published_job.id}", headers=auth_headers)
    payload = response.json()
    assert payload["contract_version"] == 3
    assert payload["quality_result"]["passed"] is True
    assert payload["scheduler_backend"] == "airflow"
```

```ts
it('shows an explicit degraded banner when APScheduler is active', async () => {
  mockOrchestrationStatus({ backend_type: 'apscheduler_fallback', state: 'degraded' })
  render(DataGovernancePage)
  expect(await screen.findByText('调度已降级到 APScheduler')).toBeVisible()
})
```

- [ ] **Step 2: 运行测试确认当前界面没有统一 job/质量/降级信息。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_api/test_data_governance_runs.py -v`

Run: `cd src/frontend && npm run test -- --run src/__tests__/views/DataGovernancePage.test.ts`

Expected: FAIL，因为 API 和页面契约不存在。

- [ ] **Step 3: 实现最小运营页面和审计边界。**

页面必须展示 endpoint、active contract version、最近成功时间、watermark、最新质量结果、运行后端、降级原因、job ID、Airflow run 链接。重跑、补数、暂停操作必须显示确认框，并由后端保存 actor、请求 ID、前后状态和结果；原始 exception trace 仅向有数据运维权限的角色返回。

- [ ] **Step 4: 运行 API、组件和权限回归。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_api/test_data_governance_runs.py tests/test_orchestration/test_failover_api.py -v`

Run: `cd src/frontend && npm run typecheck && npm run test -- --run src/__tests__/views/DataGovernancePage.test.ts src/__tests__/api/airflow.test.ts`

Expected: PASS；普通用户不能操作或读取敏感错误，降级和质量状态对授权用户清晰可见。

- [ ] **Step 5: 提交本任务。**

```bash
git add src/backend/app/api/airflow_dags.py src/backend/app/services/data_connectors/registry.py src/backend/tests/test_api/test_data_governance_runs.py src/frontend/src/api/airflow.ts src/frontend/src/api/dataGovernance.ts src/frontend/src/__tests__/views/DataGovernancePage.test.ts src/frontend/src/views
git commit -m "feat(data-governance): expose jobs quality and failover status"
```

### Task 14: 端到端验收、发布门和操作文档收口

**Files:**
- Modify: `docs/operations/akshare/airflow-failover-runbook.md`
- Create: `docs/iterations/迭代188-数据采集治理与可恢复调度/ACCEPTANCE.md`
- Modify: `docs/iterations/迭代188-数据采集治理与可恢复调度/PLAN.md`
- Modify: CI workflow 中与后端、前端、Docker Compose 相关的 job

**Interfaces:**
- Consumes: P0/P1/P2 的测试资产、Airflow Compose、运行状态 API。
- Produces: 可复现验收矩阵、PR 确定性检查和 nightly 外部 provider 冒烟。

- [ ] **Step 1: 写入故障矩阵测试。**

```python
@pytest.mark.parametrize(
    ("scenario", "expected_backend", "expected_publish_count"),
    [
        ("airflow_unavailable_at_start", "apscheduler_fallback", 1),
        ("airflow_fails_while_idle", "apscheduler_fallback", 1),
        ("airflow_recovers_after_fallback", "airflow", 1),
        ("duplicate_callback", "airflow", 1),
        ("stale_worker_epoch", "airflow", 0),
    ],
)
async def test_orchestration_recovery_matrix(scenario, expected_backend, expected_publish_count):
    result = await run_recovery_scenario(scenario)
    assert result.backend == expected_backend
    assert result.publish_count == expected_publish_count
```

- [ ] **Step 2: 运行矩阵确认每一项都是自动化证据。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/integration/test_airflow_failover.py tests/integration/test_airflow_recovery.py -v`

Expected: PASS；每个场景有确定性结果，不依赖真实外部 provider。

- [ ] **Step 3: 组成 PR 和 nightly 验收门。**

PR 必跑：模型/迁移、P0 service tests、Airflow DAG parse、回退/回切矩阵、API 权限、前端类型检查和单元测试、`git diff --check`。Nightly 才运行三个已批准 manifest 的真实 provider 冒烟；nightly 输出 endpoint version、请求时间、行数、质量结果和 Airflow run ID。

- [ ] **Step 4: 完整运行验收命令。**

Run: `cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_pipeline tests/airflow tests/integration/test_data_ingest_pipeline.py tests/integration/test_airflow_failover.py tests/integration/test_airflow_recovery.py tests/test_orchestration -v`

Run: `cd src/frontend && npm run typecheck && npm run test`

Run: `cd docker && docker compose -f docker-compose.yml -f compose/airflow.yml config --quiet`

Expected: PASS；测试报告、Alembic head、DAG parse 和 Compose 配置均为绿色。

- [ ] **Step 5: 执行发布前人工演练记录。**

按 runbook 在隔离环境完成：Airflow 启动不可达、运行时故障、3 次健康失败后的 fallback、3 次成功和 120 秒冷却后的回切、worker 失联、重复 callback、单任务灰度、单任务回滚。每次记录 job ID、idempotency key、lease epoch、Airflow run ID、发布行数和质量结果。

- [ ] **Step 6: 写入验收矩阵并提交收口文档。**

```bash
git add docs/operations/akshare/airflow-failover-runbook.md docs/iterations/迭代188-数据采集治理与可恢复调度/ACCEPTANCE.md docs/iterations/迭代188-数据采集治理与可恢复调度/PLAN.md .github
git commit -m "docs(data-ingestion): add recovery acceptance evidence"
```

---

## 6. 执行顺序、关键路径和 Cut Line

| 波次 | 工作包 | Exit 条件 |
| --- | --- | --- |
| Wave 0 | Task 1、Task 2 | 数据模型、版本、job 状态和幂等键通过迁移/并发测试 |
| Wave 1 | Task 3、Task 4、Task 5 | 三类试点经安全发布和质量门禁通过；旧表不被失败任务覆盖 |
| Wave 2 | Task 6、Task 7、Task 8 | Airflow 配置、lease、fallback、固定 DAG 通过确定性测试 |
| Wave 3 | Task 9、Task 10 | 回调/对账、自动回切、灰度迁移和状态 UI 可用 |
| Wave 4 | Task 11、Task 12、Task 13 | 三个静态 manifest、approved adapter、质量/运营管理闭环完成 |
| Release | Task 14 | 所有自动验收和隔离环境回退演练有证据 |

关键路径：

```text
Task 1 -> Task 2 -> Task 3 -> Task 5 -> Task 7 -> Task 8 -> Task 9 -> Task 10 -> Task 14
                     \-> Task 4 ---------------------------/
Task 1 -> Task 11 -> Task 12 -> Task 13 --------------------/
```

如果时间不足，只允许将 P2 的第二、第三个 provider manifest 迁出；P0 可靠发布、P1 Airflow/fallback 闭环、一个完整试点 endpoint 和 Task 14 的回退矩阵均为不可迁出的发布门。

---

## 7. 完成定义

本迭代只有同时满足以下条件才能标记完成：

- `DgIngestJob` 对相同端点版本、逻辑日期和参数只存在一个 canonical job，重复请求返回同一 job。
- 非遗留采集在质量失败、进程退出或重试后均不覆盖已发布数据；成功发布后才更新水位。
- Airflow healthy 时为唯一首选调度者；启动/运行时不可用时 APScheduler 以明确 `degraded` 状态接管。
- fallback 由数据库 lease 限制为单实例；Airflow 恢复后通过 health hysteresis、活跃 job 对账和 epoch fencing 回切，且发布数不重复。
- 两端不可用时系统可观测且拒绝新执行，而非假装成功或无限重试。
- 固定 DAG 可解析、能执行三个试点 endpoint；不依赖单任务动态 Python DAG 文件。
- manifest、adapter、质量规则和 endpoint version 可追溯，凭据不进入仓库。
- PR 确定性测试、前端 typecheck/test、Airflow Compose 解析和隔离环境回退矩阵全部通过；nightly 外部冒烟另有一次成功证据。

## 8. 计划自检

- 覆盖性：P0 对应 Task 1-5；Airflow 首选、自动 fallback、回切、回调、灰度迁移对应 Task 6-10；静态配置、provider、治理 UI 对应 Task 11-13；发布验收对应 Task 14。
- 回退需求：启动不可用、运行时故障、单实例 lease、幂等、stale epoch、自动回切、双端不可用、手工灰度回滚均有明确实现任务和测试。
- 类型一致性：`DgEndpointVersion`、`DgIngestJob`、`DataIngestJobService`、`DataPublisher`、`SchedulerLeaseService`、`OrchestrationStatus` 在后续任务中使用同一名称和职责。
- 禁止事项：计划不包含未决实现项、临时秘密、真实生产执行授权或动态任意代码执行路径。
