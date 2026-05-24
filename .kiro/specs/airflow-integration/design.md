# 技术设计文档：Airflow 集成

## Overview

本设计将 Apache Airflow 集成到 backtrader_web 数据管理模块中，作为现有 APScheduler 的增强替代方案。核心设计理念是**编排后端抽象**——通过定义统一的 `OrchestratorBackend` 接口，使 APScheduler 和 Airflow 各自实现具体类，系统在启动时自动检测 Airflow 健康状态并选择后端，实现优雅降级。

**关键设计决策：**

1. **策略模式 + 自动检测**：`OrchestratorBackend` 抽象基类定义统一调度接口，`APSchedulerBackend` 和 `AirflowBackend` 分别实现。启动时通过健康检查自动选择。
2. **httpx 异步客户端**：Airflow Adapter 使用 `httpx.AsyncClient` 封装 REST API v1，支持连接池复用和超时控制。
3. **Jinja2 模板生成 DAG**：DAG Generator 从 DataScript 元数据读取信息，通过 Jinja2 模板渲染生成标准 DAG Python 文件。
4. **HTTP 回调同步结果**：DAG 中的任务通过 `on_success_callback` / `on_failure_callback` 向 backtrader_web 后端 POST 执行结果。
5. **数据源工厂模式**：根据 `DataScript.source` 字段动态选择数据提供者类（`AkshareToMySql`、`TushareToMySql` 等）。

## Architecture

### 系统架构图

```mermaid
graph TB
    subgraph "backtrader_web Backend (FastAPI)"
        API[API Layer<br/>/api/v1/data/tasks<br/>/api/v1/data/airflow/dags]
        SVC[AkshareSchedulerService]
        OB[OrchestratorBackend<br/>抽象接口]
        APB[APSchedulerBackend]
        AFB[AirflowBackend]
        ADA[AirflowAdapter<br/>httpx AsyncClient]
        DG[DAGGenerator<br/>Jinja2 模板]
        CB[CallbackRouter<br/>接收执行结果]
    end

    subgraph "Airflow Service"
        AW[Airflow Webserver]
        AS[Airflow Scheduler]
        AX[Airflow Worker]
        PG[PostgreSQL<br/>Airflow Metadata]
        DAGS[DAG Files<br/>共享卷]
    end

    subgraph "Data Layer"
        DB[(MySQL<br/>backtrader_web DB)]
        DW[(MySQL<br/>Akshare Data Warehouse)]
    end

    API --> SVC
    SVC --> OB
    OB --> APB
    OB --> AFB
    AFB --> ADA
    ADA -->|REST API v1| AW
    DG -->|生成 .py 文件| DAGS
    AS -->|读取| DAGS
    AX -->|执行任务| DW
    AX -->|HTTP 回调| CB
    CB --> DB
    APB -->|直接执行| DW
```

### 启动流程

```mermaid
sequenceDiagram
    participant App as FastAPI App
    participant Detect as BackendDetector
    participant AF as Airflow Health API
    participant OB as OrchestratorBackend

    App->>Detect: 检查 ORCHESTRATION_BACKEND 配置
    alt ORCHESTRATION_BACKEND = "airflow"
        Detect->>AF: GET /api/v1/health
        AF-->>Detect: 200 OK
        Detect->>OB: 实例化 AirflowBackend
    else ORCHESTRATION_BACKEND = "apscheduler"
        Detect->>OB: 实例化 APSchedulerBackend
    else ORCHESTRATION_BACKEND = "auto" (默认)
        Detect->>AF: GET /api/v1/health (timeout=5s)
        alt 健康检查成功
            Detect->>OB: 实例化 AirflowBackend
        else 健康检查失败/超时
            Detect->>OB: 实例化 APSchedulerBackend
        end
    end
    App->>OB: start()
```

## Components and Interfaces

### 1. OrchestratorBackend 抽象基类

```python
from abc import ABC, abstractmethod
from typing import Any

class OrchestratorBackend(ABC):
    """任务编排后端抽象接口。"""

    @abstractmethod
    async def start(self) -> None:
        """启动编排后端。"""

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭编排后端。"""

    @abstractmethod
    async def add_or_update_task(self, task_id: int) -> None:
        """添加或更新调度任务。"""

    @abstractmethod
    async def remove_task(self, task_id: int) -> None:
        """移除调度任务。"""

    @abstractmethod
    async def run_task_now(self, task_id: int, operator_id: str | None = None) -> Any:
        """立即执行任务。"""

    @abstractmethod
    async def reload_active_tasks(self) -> None:
        """重新加载所有活跃任务。"""

    @abstractmethod
    async def get_backend_status(self) -> dict[str, Any]:
        """获取后端状态信息。"""
```

### 2. APSchedulerBackend

现有 `AkshareScheduler` 类的适配包装，实现 `OrchestratorBackend` 接口。内部逻辑保持不变，仅增加接口适配层。

**文件位置：** `app/services/orchestration/apscheduler_backend.py`

### 3. AirflowBackend

通过 `AirflowAdapter` 与 Airflow REST API 交互，实现 `OrchestratorBackend` 接口。

**文件位置：** `app/services/orchestration/airflow_backend.py`

**关键行为：**
- `add_or_update_task()` → 调用 DAGGenerator 生成/更新 DAG 文件，然后通过 API 启用 DAG
- `run_task_now()` → 通过 API 触发 DAG Run，传入 `conf` 参数
- `remove_task()` → 暂停 DAG 并删除 DAG 文件

### 4. AirflowAdapter

封装 Airflow REST API v1 的异步 HTTP 客户端。

**文件位置：** `app/services/orchestration/airflow_adapter.py`

```python
class AirflowAdapter:
    """Airflow REST API v1 异步适配器。"""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            auth=(username, password),
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def health_check(self) -> bool: ...
    async def list_dags(self, limit: int = 100, offset: int = 0) -> dict: ...
    async def get_dag(self, dag_id: str) -> dict: ...
    async def trigger_dag_run(self, dag_id: str, conf: dict | None = None) -> dict: ...
    async def get_dag_run(self, dag_id: str, dag_run_id: str) -> dict: ...
    async def list_dag_runs(self, dag_id: str, limit: int = 25) -> dict: ...
    async def get_task_instances(self, dag_id: str, dag_run_id: str) -> dict: ...
    async def get_task_log(self, dag_id: str, dag_run_id: str, task_id: str, try_number: int = 1) -> str: ...
    async def pause_dag(self, dag_id: str) -> dict: ...
    async def unpause_dag(self, dag_id: str) -> dict: ...
    async def close(self) -> None: ...
```

### 5. DAGGenerator

从 DataScript 元数据生成 Airflow DAG Python 文件。

**文件位置：** `app/services/orchestration/dag_generator.py`

```python
class DAGGenerator:
    """从 DataScript 元数据生成 Airflow DAG 文件。"""

    def __init__(self, dag_output_dir: str, template_dir: str | None = None) -> None: ...

    def generate_dag(self, script: DataScript, task: ScheduledTask | None = None) -> str:
        """生成单个 DAG 文件，返回文件路径。"""

    def generate_grouped_dag(self, scripts: list[DataScript], category: str) -> str:
        """将同类脚本组合为一个多任务 DAG。"""

    def validate_dependencies(self, scripts: list[DataScript]) -> list[str]:
        """验证依赖关系，返回循环依赖错误列表。"""

    def remove_dag(self, script_id: str) -> bool:
        """删除 DAG 文件。"""
```

**Jinja2 模板示例（`dag_template.py.j2`）：**

```python
"""Auto-generated DAG for {{ script_id }}. DO NOT EDIT MANUALLY."""
from datetime import timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
import httpx

default_args = {
    "owner": "backtrader_web",
    "retries": {{ retries }},
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(seconds={{ timeout }}),
    {% if retry_exponential_backoff %}
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=60),
    {% endif %}
}

dag = DAG(
    dag_id="dag_{{ script_id }}",
    default_args=default_args,
    description="{{ description }}",
    schedule_interval="{{ schedule_interval }}",
    start_date=days_ago(1),
    catchup=False,
    tags=["{{ category }}", "auto-generated"],
)

def execute_script(**context):
    from app.data_fetch.providers.factory import get_data_provider
    provider = get_data_provider("{{ source }}")
    provider.fetch_data({{ parameters | tojson }})

def on_success(context):
    httpx.post("{{ callback_url }}/api/v1/data/airflow/callback", json={...})

def on_failure(context):
    httpx.post("{{ callback_url }}/api/v1/data/airflow/callback", json={...})

{% for task in tasks %}
task_{{ task.task_id }} = PythonOperator(
    task_id="{{ task.task_id }}",
    python_callable=execute_script,
    on_success_callback=on_success,
    on_failure_callback=on_failure,
    dag=dag,
)
{% endfor %}

{% for dep in dependencies %}
task_{{ dep.upstream }} >> task_{{ dep.downstream }}
{% endfor %}
```

### 6. DataProviderFactory

根据 `DataScript.source` 字段选择数据提供者类。

**文件位置：** `app/data_fetch/providers/factory.py`

```python
from typing import Any

_PROVIDER_REGISTRY: dict[str, type] = {}

def register_provider(source: str, provider_class: type) -> None:
    """注册数据提供者类。"""
    _PROVIDER_REGISTRY[source] = provider_class

def get_data_provider(source: str, db_config: dict[str, Any] | None = None) -> Any:
    """根据 source 字段获取数据提供者实例。"""
    provider_class = _PROVIDER_REGISTRY.get(source)
    if provider_class is None:
        raise ValueError(f"Unknown data source: {source}")
    return provider_class(db_config or _default_db_config())
```

### 7. BackendDetector

启动时自动检测 Airflow 可用性并选择后端。

**文件位置：** `app/services/orchestration/detector.py`

```python
class BackendDetector:
    """编排后端自动检测器。"""

    async def detect(self) -> OrchestratorBackend:
        """根据配置和健康检查结果选择后端。"""
```

### 8. CallbackRouter

接收 Airflow 任务执行回调的 API 端点。

**文件位置：** `app/api/airflow_callback.py`

```python
@router.post("/airflow/callback")
async def receive_callback(payload: AirflowCallbackPayload, db: AsyncSession = Depends(get_db)):
    """接收 Airflow 任务执行结果回调。"""
```

### 9. MigrationTool

将现有 APScheduler 任务迁移到 Airflow DAG 的命令行工具。

**文件位置：** `app/services/orchestration/migration.py`

## Data Models

### 新增配置项（Settings 类扩展）

```python
# Airflow 集成配置
AIRFLOW_API_BASE_URL: str = Field(
    default="", description="Airflow REST API base URL"
)
AIRFLOW_USERNAME: str = Field(default="admin", description="Airflow API username")
AIRFLOW_PASSWORD: str = Field(default="", description="Airflow API password")
ORCHESTRATION_BACKEND: str = Field(
    default="auto", description="Orchestration backend: airflow, apscheduler, auto"
)
AIRFLOW_DAG_OUTPUT_DIR: str = Field(
    default="./dags", description="Directory for generated DAG files"
)
AIRFLOW_CALLBACK_BASE_URL: str = Field(
    default="http://localhost:8000", description="Base URL for Airflow callbacks"
)
```

### TaskExecution 模型扩展

在现有 `TaskExecution` 模型中新增 Airflow 关联字段：

```python
# 新增字段
airflow_dag_id = Column(String(200), nullable=True, index=True)
airflow_run_id = Column(String(200), nullable=True, index=True)
airflow_task_id = Column(String(200), nullable=True)
```

### AirflowCallbackPayload Schema

```python
class AirflowCallbackPayload(BaseModel):
    """Airflow 回调请求体。"""
    execution_id: str
    dag_id: str
    dag_run_id: str
    task_id: str
    status: str  # "success" | "failed"
    start_time: datetime
    end_time: datetime
    duration: float
    error_message: str | None = None
    error_trace: str | None = None
    rows_before: int | None = None
    rows_after: int | None = None
    result: dict | None = None
```

### Docker Compose 配置（`docker-compose.airflow.yml`）

```yaml
version: "3.8"
services:
  airflow-postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - airflow-pg-data:/var/lib/postgresql/data

  airflow-webserver:
    image: apache/airflow:2.8.1
    depends_on:
      - airflow-postgres
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@airflow-postgres/airflow
      AIRFLOW__CORE__DAGS_FOLDER: /opt/airflow/dags
      AIRFLOW__CORE__DEFAULT_TIMEZONE: Asia/Shanghai
      AIRFLOW__API__AUTH_BACKENDS: airflow.api.auth.backend.basic_auth
      AKSHARE_DATA_DATABASE_URL: ${AKSHARE_DATA_DATABASE_URL}
    volumes:
      - ./dags:/opt/airflow/dags
      - ./src/backend:/opt/airflow/app
    ports:
      - "8080:8080"
    command: webserver
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  airflow-scheduler:
    image: apache/airflow:2.8.1
    depends_on:
      - airflow-postgres
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@airflow-postgres/airflow
      AIRFLOW__CORE__DAGS_FOLDER: /opt/airflow/dags
      AIRFLOW__CORE__DEFAULT_TIMEZONE: Asia/Shanghai
      AKSHARE_DATA_DATABASE_URL: ${AKSHARE_DATA_DATABASE_URL}
    volumes:
      - ./dags:/opt/airflow/dags
      - ./src/backend:/opt/airflow/app
    command: scheduler

volumes:
  airflow-pg-data:
```

### 目录结构

```
src/backend/app/services/orchestration/
├── __init__.py
├── base.py                  # OrchestratorBackend 抽象基类
├── apscheduler_backend.py   # APScheduler 实现
├── airflow_backend.py       # Airflow 实现
├── airflow_adapter.py       # Airflow REST API 客户端
├── dag_generator.py         # DAG 文件生成器
├── detector.py              # 后端自动检测
├── migration.py             # 迁移工具
└── templates/
    ├── dag_single.py.j2     # 单任务 DAG 模板
    └── dag_grouped.py.j2    # 多任务 DAG 模板

src/backend/app/data_fetch/providers/
├── factory.py               # 数据源工厂
├── akshare_to_mysql.py      # 现有 Akshare 提供者
└── tushare_to_mysql.py      # 未来 Tushare 提供者（预留）

src/backend/app/api/
├── airflow_callback.py      # 回调接收端点
└── airflow_dags.py          # Airflow DAG 管理端点
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: HTTP 错误转换为结构化异常

*For any* HTTP 错误状态码（4xx 或 5xx），AirflowAdapter 应当抛出包含错误码和描述信息的结构化异常，而非原始 HTTP 错误。

**Validates: Requirements 2.3**

### Property 2: 运行时参数透传

*For any* 有效的 `conf` 字典，调用 `trigger_dag_run(dag_id, conf)` 时，发送到 Airflow API 的请求体中应当包含该 `conf` 字典的完整内容。

**Validates: Requirements 2.6**

### Property 3: DAG 生成产出有效 Python 文件

*For any* 有效的 DataScript 元数据（包含 script_id、category、source、timeout），DAG Generator 生成的文件应当是语法正确的 Python 代码，且包含与 script_id 对应的 `dag_id`。

**Validates: Requirements 3.1**

### Property 4: 依赖关系解析为 DAG 操作符

*For any* 有效的依赖关系图（script_id 列表），生成的 DAG 文件应当包含对应的 `>>` 操作符链，正确表达上下游关系。当依赖列表为空时，DAG 应仅包含单个任务。

**Validates: Requirements 3.2, 3.3**

### Property 5: 元数据映射到 default_args

*For any* DataScript（含 timeout 字段）和 ScheduledTask（含 max_retries 字段），生成的 DAG 的 `default_args` 应当包含匹配的 `retries`、`retry_delay` 和 `execution_timeout` 值。

**Validates: Requirements 3.4**

### Property 6: DAG 文件命名规范

*For any* 有效的 script_id，生成的 DAG 文件路径应当以 `dag_{script_id}.py` 结尾。

**Validates: Requirements 3.5**

### Property 7: 同类脚本分组

*For any* 共享相同 category 的 DataScript 列表，`generate_grouped_dag` 应当生成一个包含与脚本数量相等的任务数的单一 DAG。

**Validates: Requirements 3.6**

### Property 8: 调度表达式转换

*For any* 有效的 ScheduledTask `schedule_expression`（cron、interval、daily 格式），转换结果应当是 Airflow 兼容的 cron 表达式或预定义调度字符串。

**Validates: Requirements 3.8, 10.2**

### Property 9: 循环依赖检测

*For any* 依赖关系图，`validate_dependencies` 应当返回错误当且仅当图中存在循环。对于无环图应返回空错误列表。

**Validates: Requirements 4.3**

### Property 10: 编排后端自动检测

*For any* `ORCHESTRATION_BACKEND` 配置值（`airflow`、`apscheduler`、`auto`）和健康检查结果（成功/失败/超时）的组合，BackendDetector 应当选择正确的后端实现：强制指定时使用指定后端，`auto` 模式下根据健康检查结果选择。

**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

### Property 11: 回调数据持久化

*For any* 有效的 AirflowCallbackPayload，回调处理器应当创建一条 TaskExecution 记录，其字段值（execution_id、status、start_time、end_time、duration、error_message、rows_before、rows_after）与 payload 一致。

**Validates: Requirements 7.2, 7.3**

### Property 12: 数据源工厂分发

*For any* 已注册的 source 字符串，`get_data_provider(source)` 应当返回对应的数据提供者类实例。对于未注册的 source 应当抛出 ValueError。

**Validates: Requirements 8.1, 8.2**

### Property 13: 迁移工具生成完整 DAG

*For any* 活跃的 ScheduledTask 列表，迁移工具应当为每个任务生成恰好一个 DAG 文件。

**Validates: Requirements 10.1**

### Property 14: 迁移参数映射

*For any* 有效的 ScheduledTask parameters JSON 字典，生成的 DAG 应当将这些参数包含在默认运行参数（`params`）中。

**Validates: Requirements 10.3**

### Property 15: 迁移报告准确性

*For any* 包含有效和无效任务的混合集合，迁移报告应当正确分类每个任务为成功或失败，并为失败任务提供原因说明。成功数 + 失败数应等于总任务数。

**Validates: Requirements 10.4**

## Error Handling

### 错误分层策略

| 层级 | 组件 | 错误处理方式 |
|------|------|-------------|
| Adapter 层 | AirflowAdapter | 将 HTTP 错误转换为 `AirflowAPIError` 异常，包含 status_code 和 detail |
| Service 层 | AirflowBackend | 捕获 `AirflowAPIError`，记录日志，返回 None/False 或重新抛出 |
| API 层 | Router | 将 Service 层异常转换为 HTTPException（503/502/500） |

### 异常类型定义

```python
class AirflowAPIError(Exception):
    """Airflow REST API 调用失败。"""
    def __init__(self, status_code: int, detail: str, endpoint: str):
        self.status_code = status_code
        self.detail = detail
        self.endpoint = endpoint

class AirflowConnectionError(AirflowAPIError):
    """Airflow 服务连接失败（超时或网络不可达）。"""

class AirflowDAGNotFoundError(AirflowAPIError):
    """请求的 DAG 不存在。"""

class CyclicDependencyError(ValueError):
    """依赖关系中存在循环引用。"""
    def __init__(self, cycle: list[str]):
        self.cycle = cycle

class DAGGenerationError(Exception):
    """DAG 文件生成失败。"""
```

### 关键错误场景

1. **Airflow 服务不可用**：AirflowAdapter 在 10 秒超时后抛出 `AirflowConnectionError`，API 层返回 503。
2. **DAG 生成失败**：模板渲染错误或文件写入失败时抛出 `DAGGenerationError`，不影响现有调度。
3. **循环依赖**：`validate_dependencies` 检测到环时抛出 `CyclicDependencyError`，API 返回 400。
4. **回调失败**：DAG 中的回调函数最多重试 3 次（间隔 10 秒），全部失败后记录错误日志但不影响任务状态。
5. **后端切换期间的请求**：如果 Airflow 运行时变为不可用，当前请求返回 502，记录 WARNING 日志，不自动切换后端。

### 重试策略

- **Airflow API 调用**：不在 Adapter 层重试（由调用方决定）
- **回调请求**：最多 3 次，间隔 10 秒，使用 tenacity 库
- **DAG 任务执行**：由 Airflow 内置重试机制处理（指数退避）

## Testing Strategy

### 测试框架选择

- **单元测试**：pytest + pytest-asyncio
- **属性测试**：hypothesis（Python PBT 库）
- **集成测试**：pytest + httpx（mock Airflow API）
- **前端测试**：Vitest + Playwright

### 双重测试方法

**单元测试**覆盖：
- 具体示例和边界条件（如空依赖、超时场景）
- 组件间集成点（如 Service 调用 Adapter）
- 错误处理路径（如 Airflow 不可用时的降级）
- 前端组件渲染和交互

**属性测试**覆盖：
- 所有 Correctness Properties（P1-P15）
- 每个属性测试最少运行 100 次迭代
- 使用 hypothesis 的 `@given` 装饰器和自定义 strategies

### 属性测试配置

```python
from hypothesis import given, settings, strategies as st

@settings(max_examples=100)
@given(status_code=st.integers(min_value=400, max_value=599))
def test_http_error_conversion(status_code):
    """Feature: airflow-integration, Property 1: HTTP 错误转换为结构化异常"""
    # ...
```

### 测试分层

| 层级 | 范围 | 工具 | 标记 |
|------|------|------|------|
| 单元测试 | 单个函数/类 | pytest + hypothesis | 无标记 |
| 集成测试 | 多组件协作 | pytest + httpx mock | `@pytest.mark.integration` |
| E2E 测试 | 完整 Airflow 流程 | pytest + docker | `@pytest.mark.e2e` |
| 前端测试 | Vue 组件 | Vitest | - |

### Mock 策略

- **AirflowAdapter 测试**：使用 `respx` 或 `httpx.MockTransport` mock HTTP 响应
- **DAGGenerator 测试**：使用临时目录（`tmp_path` fixture）验证文件生成
- **BackendDetector 测试**：mock 健康检查响应
- **回调测试**：使用 FastAPI TestClient 模拟回调请求

### 关键测试文件

```
src/backend/tests/
├── test_orchestration/
│   ├── test_airflow_adapter.py       # Adapter 单元测试 + 属性测试
│   ├── test_dag_generator.py         # DAG 生成器属性测试
│   ├── test_backend_detector.py      # 后端检测属性测试
│   ├── test_migration.py             # 迁移工具属性测试
│   ├── test_provider_factory.py      # 数据源工厂属性测试
│   └── test_callback.py             # 回调处理属性测试
├── test_orchestration_integration/
│   └── test_airflow_e2e.py          # Airflow 集成测试
```

