# 迭代189：三层数据目录最小落地

> **状态：待评审**
>
> 本方案替代已废弃的迭代 188。它只建立三层数据目录并迁入三个已验证的 AkShare/MySQL 表，不改写采集执行、调度、数据库引擎或前端页面。

**目标：** 把当前“AkShare 脚本直接写 `akshare_data`”的现实结构登记为清晰、可扩展的数据目录：来源层、逻辑数据集层和物理存储层彼此独立。完成后，同一个逻辑数据集可以由多个来源提供，也可以落在多个 MySQL 或 ClickHouse 存储中，但本迭代只启用现有 AkShare→MySQL 链路。

**非目标：** 不接入 TuShare、Baostock、ClickHouse 或 Airflow；不实现 Airflow/ APScheduler 回退；不迁移全部 AkShare 脚本；不变更已有表、脚本写入 SQL 或生产调度。

## 1. 重新研究后的结论

当前代码已经有来源目录和 AkShare 运行目录，但它们把不同职责混在了一起：

| 现状 | 证据 | 问题 |
| --- | --- | --- |
| `DgProvider`、`DgEndpoint` 记录 provider 和接口 | `src/backend/app/models/data_governance.py` | `DgEndpoint` 同时保存 `target_database`、`target_table`，来源与存储耦合 |
| 数据仓库默认是 `akshare_data` | `src/backend/app/data_fetch/configs/db_config.py` | 新 provider 或第二个存储引擎无法独立配置 |
| `DataTable` 是当前库表的运行元数据 | `src/backend/app/models/akshare_mgmt.py` | 它不知道这张表对应哪个逻辑数据产品 |
| 现有脚本直接写物理表 | `stock_zh_a_hist.py`、`daily_market_data.py`、`shfe_delivery_data.py` | 业务代码和物理表名强绑定 |

这不是先上 Airflow 或 ClickHouse 能解决的问题。第一步应先建立目录边界；否则每增加一个 provider、数据库或调度器，都会继续向脚本和 `DgEndpoint` 中叠加条件分支。

## 2. 三层模型与核心规则

```text
来源层（谁提供、怎么取）
  DgProvider: akshare
  DgEndpoint: stock_zh_a_hist
          │ produces
          ▼
逻辑数据集层（数据是什么，消费者依赖什么）
  DgDataset: market.stock_daily
          │ materialized as
          ▼
物理存储层（放在哪里、哪张表）
  DgStorageTarget: mysql_akshare_data
  DgDatasetStorage: STOCK_ZH_A_HIST
```

### 2.1 三层职责

| 层 | 模型 | 只负责 | 明确不负责 |
| --- | --- | --- | --- |
| 来源层 | 现有 `DgProvider`、`DgEndpoint` | provider、接口、鉴权环境变量名、接口参数 | 数据库、物理表名、调度状态 |
| 逻辑数据集层 | 新增 `DgDataset` | 稳定 dataset code、业务名称、规范字段和逻辑主键 | provider SDK、连接串、物理表名 |
| 物理存储层 | 新增 `DgStorageTarget`、`DgDatasetStorage` | 引擎、连接环境变量名、库名、表名、写入模式 | 采集调用和数据源选择策略 |

### 2.2 必须遵守的规则

- `DgEndpoint.target_database` 和 `DgEndpoint.target_table` 保留为兼容字段，但任何新增代码都不能用它们解析物理表。
- 一条 `DgEndpoint` 最多指向一个 `DgDataset`；一个 `DgDataset` 可由多个 endpoint 提供。
- 一个 `DgDataset` 可有多个 `DgDatasetStorage`。例如同一个 `market.stock_daily` 未来可同时存在于 `mysql_akshare_data` 和 `clickhouse_market_serving`。
- `DgStorageTarget` 是具体存储实例，不等同于 provider。因而同一个 AkShare 来源可以有多个 MySQL/ClickHouse 存储；同一个 MySQL 实例也可承载多个来源的数据集。
- catalog 中仅保存环境变量名，如 `AKSHARE_DATA_DATABASE_URL`，不得保存 URL、账号、密码、token。
- 本迭代仅描述现有原始 MySQL 表，不强制把物理列改成规范字段，也不创建跨源合并表。

### 2.3 本轮首批登记项

| provider | script ID | 逻辑 dataset | 当前存储 | 物理表 | 逻辑主键 |
| --- | --- | --- | --- | --- | --- |
| `akshare` | `stock_zh_a_hist` | `market.stock_daily` | `mysql_akshare_data` | `STOCK_ZH_A_HIST` | `symbol,data_date` |
| `akshare` | `daily_market_data` | `market.futures_daily` | `mysql_akshare_data` | `FUTURES_DAILY_MARKET` | `MARKET,SYMBOL,TRADE_DATE` |
| `akshare` | `shfe_delivery_data` | `reference.shfe_delivery_monthly` | `mysql_akshare_data` | `FUTURES_DELIVERY_SHFE` | `PRODUCT_NAME,TRADE_MONTH` |

`mysql_akshare_data` 的固定初始属性为：`engine=mysql`、`url_env=AKSHARE_DATA_DATABASE_URL`、`database_name=akshare_data`、`role=raw`。

## 3. 迭代范围与交付物

### 必须完成

- 建立三层模型和兼容迁移。
- 将当前 AkShare/MySQL 及上表三个数据集幂等写入 catalog。
- 提供仅供后端使用的 catalog 查询服务，按 `dataset_code` 解析物理存储。
- 将三个已存在的 `DataTable` 运行元数据安全关联到对应 binding。
- 用隔离数据库、无网络测试证明三层独立性和三个试点映射。

### 明确不做

- 不创建新的 REST API、管理页面或前端表格；这些放到迭代 190，等模型稳定后再展示。
- 不增加通用 writer、schema 转换、质量规则、回填和数据源选择。
- 不创建 ClickHouse 库表、不安装 TuShare/Baostock SDK、不读取它们的凭据。
- 不修改 `AkshareToMySql`、`AkshareDataService` 的写入语义，包括历史 `DROP TABLE` 行为。
- 不改 APScheduler，也不新增 Airflow 容器、DAG 或 fallback 逻辑。

## 4. 文件与数据契约

### 4.1 拟修改/新增文件

```text
src/backend/
  alembic/versions/20260727_three_layer_data_catalog.py
  app/models/data_governance.py                     # 新模型、DgEndpoint.dataset_id
  app/models/akshare_mgmt.py                        # DataTable.dataset_storage_id
  app/services/data_catalog/__init__.py
  app/services/data_catalog/bootstrap.py            # 首批静态登记项
  app/services/data_catalog/resolver.py             # dataset -> storage binding
  app/services/data_catalog/sync.py                 # DataTable 关联
  app/services/data_connectors/registry.py          # 启动 bootstrap
  app/services/akshare/data.py                      # metadata 成功后非阻断关联
  tests/services/data_catalog/test_schema.py
  tests/services/data_catalog/test_bootstrap.py
  tests/services/data_catalog/test_resolver.py
  tests/services/data_catalog/test_sync.py
  tests/integration/test_akshare_mysql_catalog_pilots.py
docs/
  architecture/three-layer-data-catalog.md
  iterations/迭代189-三层数据平台基础/ACCEPTANCE.md
```

### 4.2 新模型

```python
class DgDataset(Base):
    __tablename__ = "dg_datasets"

    id: str
    dataset_code: str       # 例如 market.stock_daily，全局唯一
    display_name: str
    domain: str             # market、reference 等
    canonical_schema: dict  # 逻辑字段说明，不在本轮强制转换物理列
    primary_key: list[str]
    is_active: bool


class DgStorageTarget(Base):
    __tablename__ = "dg_storage_targets"

    id: str
    storage_id: str         # 例如 mysql_akshare_data，全局唯一
    engine: str             # mysql、clickhouse；本轮只有 mysql
    url_env: str            # 例如 AKSHARE_DATA_DATABASE_URL
    database_name: str
    role: str               # raw、curated、serving
    is_active: bool


class DgDatasetStorage(Base):
    __tablename__ = "dg_dataset_storages"

    id: str
    dataset_id: str
    storage_target_id: str
    physical_table: str
    write_mode: str         # 本轮三个表均为 legacy
    is_primary: bool
```

兼容字段只新增，不删除：

```python
DgEndpoint.dataset_id: str | None
DataTable.dataset_storage_id: str | None
```

`DgIngestJob` 本轮不修改，因为它当前只是 connector preview 记录，尚不是统一采集运行契约。

### 4.3 唯一性与解析规则

- `DgDataset.dataset_code` 唯一。
- `DgStorageTarget.storage_id` 唯一。
- `(storage_target_id, physical_table)` 唯一，防止同一物理表被登记为两个不同 dataset。
- 每个 dataset 最多一个 `is_primary=True` binding；这项跨 MySQL/SQLite 的约束由 bootstrap 与 service 显式校验，并由测试覆盖。
- `resolve_dataset_storage(dataset_code, storage_id=None)` 只查 active dataset、active storage target 和 binding。未指定 `storage_id` 时选择 primary binding；指定 `storage_id` 时选择该 storage 的唯一 binding；无结果时抛明确的 `DatasetStorageNotFoundError`。
- resolver 禁止读取 `DgEndpoint.target_database/target_table`；这样才能证明来源层不再决定存储层。

## 5. 实施计划

### P0：目录模型与兼容迁移

**目标：** 先让三个层次可以独立存储，不改变任何已有 AkShare 表和脚本。

1. 在 `data_governance.py` 中新增 `DgDataset`、`DgStorageTarget`、`DgDatasetStorage`，并补齐双向 relationship。
2. 给 `DgEndpoint` 增加 nullable `dataset_id`；给 `DataTable` 增加 nullable `dataset_storage_id`。现有行全部保持 `NULL`，不能从旧 `target_database/target_table` 批量猜测映射。
3. 编写 `20260727_three_layer_data_catalog.py`：仅创建表、索引和外键；upgrade/downgrade 均不得碰现有物理行情表。
4. 建立 `test_schema.py`，在临时 SQLite 或已有隔离 MySQL fixture 上执行迁移并断言新表、索引、外键存在，同时断言既有 `dg_endpoints`、`ak_data_tables` 行仍可读取。
5. 增加模型关系测试：一个 endpoint 指向一个 dataset；同一个 dataset 能绑定一个 MySQL storage；无 endpoint 的 dataset 也可以存在。

验证命令：

```bash
cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_catalog/test_schema.py -v
cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_data_governance_compat.py -v
```

通过条件：迁移只新增 catalog 元数据；现有 endpoint 兼容读取不变；不连接真实 AkShare 或生产 MySQL。

### P1：AkShare/MySQL 首批 catalog 与解析服务

**目标：** 用唯一、可审计的静态配置登记当前真实情况，并让新代码从逻辑 dataset 解析物理表。

1. 在 `app/services/data_catalog/bootstrap.py` 定义 `CURRENT_AKSHARE_MYSQL_CATALOG`，内容仅限 2.3 的三个试点。每条配置必须同时包含 `provider_id`、`script_id`、`dataset_code`、物理表、逻辑主键和 `canonical_schema`。
2. 实现 `bootstrap_current_akshare_mysql_catalog(session)`：
   - create-or-get `DgProvider(provider_id="akshare")`；
   - create-or-get `DgStorageTarget(storage_id="mysql_akshare_data")`；
   - create-or-get 三个 dataset 与 binding；
   - 当已有 AkShare endpoint 的 `legacy_interface_name` 或 `endpoint_name` 与 `script_id` 一致时，填入 `dataset_id`；没有对应 endpoint 时只登记 dataset/binding，不伪造接口或函数路径。
3. 在 `DataGovernanceService.bootstrap()` 的原有 provider/endpoint 同步完成之后调用该方法，并保证整个过程重复执行不产生重复记录。
4. 新增 `DataCatalogResolver`。它返回 `dataset_code`、`storage_id`、`engine`、`database_name`、`physical_table`、`write_mode` 的只读 DTO；本轮不创建连接、不检查表结构、不分派 writer。
5. 编写 bootstrap/resolver 测试：
   - 连续两次 bootstrap 后只存在一个 storage target 和三个 binding；
   - 故意将 `DgEndpoint.target_table` 写成错误值，resolver 仍返回 binding 中的正确物理表；
   - 指定未知 dataset 或未配置 storage 时返回明确错误，不能默默落回 `akshare_data`。

验证命令：

```bash
cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_catalog/test_bootstrap.py tests/services/data_catalog/test_resolver.py -v
cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_data_governance_compat.py -v
```

通过条件：`market.stock_daily` 的存储定位完全来自 `DgDatasetStorage`；旧 target 字段仍能被旧代码读取，但不再是新路径的权威信息。

### P2：运行元数据关联与三试点验收

**目标：** 不动脚本运行逻辑，只把已经写入的当前 MySQL 表与 catalog 连接起来，形成可回归证据。

1. 实现 `DataCatalogSyncService.link_data_table(table)`。当前 `DataTable` 只描述 `akshare_data`，因此它按 `mysql_akshare_data + table_name` 查找 binding；匹配时设置 `dataset_storage_id`，未匹配时原样返回。
2. 在 `AkshareDataService._upsert_table_metadata()` 成功持久化 `DataTable` 后调用该服务，使 `persist_dataframe()` 和 `sync_existing_table_metadata()` 都经过同一关联点。catalog 查询失败只能记录 warning，不能把一次已经成功的 AkShare 采集标记为失败。
3. 编写 `test_sync.py`：三个试点 `DataTable` 均会得到 binding；未映射表的 `dataset_storage_id` 保持 `NULL`；重复同步不改写无关 metadata。
4. 编写不联网的 pilot 测试，逐项验证 script ID、provider、dataset、storage、table 与逻辑主键。测试不得执行脚本、请求 AkShare 或新建/删除 MySQL 表。
5. 输出 `three-layer-data-catalog.md` 和 `ACCEPTANCE.md`，记录字段含义、三个试点、兼容字段和本迭代未做的事项。

验证命令：

```bash
cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/services/data_catalog/test_sync.py tests/integration/test_akshare_mysql_catalog_pilots.py -v
cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_akshare_script_service.py tests/test_akshare_management_api.py tests/test_market_data_coverage_service.py -v
cd src/backend && /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m ruff check app/models/data_governance.py app/models/akshare_mgmt.py app/services/data_catalog app/services/data_connectors/registry.py app/services/akshare/data.py
```

通过条件：三个现有脚本仍走原有路径，但各自可被反查为 `provider → dataset → mysql_akshare_data.table`；任何未映射表和脚本不受影响。

## 6. 验收标准

- 数据库中存在独立的 provider、dataset、storage target 和 dataset-storage binding 记录。
- 当前 `akshare_data` 被清楚登记为 `mysql_akshare_data`，而不是硬编码为所有 provider 的默认目标。
- 三个试点的映射完全可由 catalog 恢复，且没有修改 `STOCK_ZH_A_HIST`、`FUTURES_DAILY_MARKET`、`FUTURES_DELIVERY_SHFE` 的 schema 或数据。
- 同一个逻辑 dataset 在数据模型上能够绑定第二个 MySQL 或 ClickHouse storage；本迭代不实际连通它。
- 新 resolver 从 binding 而不是 endpoint legacy target 字段决定表位置。
- 未映射的 AkShare script、`DataTable`、APScheduler 和现有 API 继续可用。
- 全部新增测试使用 mock、SQLite 或隔离 MySQL；不依赖真实网络和生产库。

## 7. 后续迭代边界

| 后续迭代 | 前置条件 | 仅在该迭代进入的工作 |
| --- | --- | --- |
| 迭代 190 | 189 的模型、三个试点和回归测试稳定 | catalog 查询 API/UI、更多 AkShare 表批量映射、通用执行器设计 |
| 迭代 191 | 统一 run 契约确定 | Airflow 为首选调度器、APScheduler 受控回退、租约和幂等发布 |
| 迭代 192 | 运行契约与隔离测试环境具备 | TuShare/Baostock adapter、第二个 storage target、ClickHouse writer 与跨源质量校验 |

这条顺序的关键是：先稳定“数据是什么、来自哪里、放在哪里”，再处理“何时执行、如何容错、怎样切换调度器”。
