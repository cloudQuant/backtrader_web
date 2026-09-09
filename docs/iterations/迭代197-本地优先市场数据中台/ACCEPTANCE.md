# 迭代 197 验收文档：本地优先市场数据中台

> 文档状态：196/197 集成候选，本地回归已完成（2026-09-09）
> 适用工作树：`codex/iteration-197-acceptance`
> 当前结论：**尚未达到发布验收条件。** 迭代 196 已冻结并接入本候选；本文仍把本地自动化、真实环境和页面灰度证据分开记录，没有命令输出、数据库快照或外部回执的项目不得标记为 `PASS`。本次 OpenBB yfinance fork 记录是文档与离线构件候选更新：没有安装扩展、构建镜像、创建 permit/route、发起真实 OpenBB/yfinance 网络调用或写入市场数据。

## 1. 验收目的、边界与判定语言

本验收确认迭代 197 所定义的本地优先读取链路是否满足以下结果：

1. 对一个完整、精确且已注册的市场数据请求，先从规范化本地库读取；本地证据完整时不调用网络。
2. 本地缺数据、字段不足或交易日历证据未知时，只能按服务端批准的来源策略补齐；不得通过样例、附近代码、相近合约、模糊匹配或未批准提供方伪造结果。
3. 成功的外部结果必须先在**事务 A**写入来源回执、不可变观测修订及 pending publication；事务 A 提交后，才在**事务 B**写入可见性回执并重新从本地库读取。API 不能直接把提供方响应当作结果返回。
4. 严格研究和回测只能读取具有 hash 匹配、`published_at <= knowledge_cutoff` 的 post-commit 可见性回执所对应的主数据、日历和观测事实；事务 A 已提交但事务 B 未完成的事实必须保持不可见。
5. 研究/回测只能消费由服务端签发、精确绑定到 research workspace/unit/intent 的严格本地工件；页面生产开关仍须等待独立的真实数据、浏览器和部署验收。
6. 对按事件判断完整性的 `bars` 请求，覆盖完整必须由 `(market, data_kind, frequency, event timestamp)` 显式日历网格证明；任何其它频率、交易时段或周末规则都不能替代该网格。

本文件使用下列状态，且不把“测试文件存在”当作测试通过：

| 状态 | 定义 | 能否作为上线依据 |
| --- | --- | --- |
| `PASS` | 已在记录的代码版本、环境和命令下执行，退出码为 0，且保留了足以复核的输出或工件。 | 可以，仍须同时满足其余闸门。 |
| `FAIL` | 已执行且断言、迁移、检查或实际行为不符合预期。 | 不可以。 |
| `NOT_RUN` | 尚未执行，或因本次只具备离线替身而没有真实环境证据。 | 不可以。 |
| `BLOCKED` | 执行需要尚未具备的外部前置条件，例如迭代 196 合并、生产数据库副本、来源凭据或许可确认。 | 不可以，必须解除阻塞。 |

本地 `pytest`、静态检查或前端构建只证明对应执行瞬间的代码；在待合并提交或候选 tag 上完成复跑前，均不构成发布签收。发布前必须在冻结候选上重新执行第 4 节的命令，并把命令、版本和输出摘要填入第 5 节。

## 2. 验收对象与明确不包含的事项

### 2.1 本次验收对象

| 编号 | 验收对象 | 主要实现/证据位置 |
| --- | --- | --- |
| AO-01 | 逻辑数据目录与主存储解析 | `dg_datasets`、`dg_storage_targets`、`dg_dataset_storages`；`test_catalog.py` |
| AO-02 | 冻结 identity projection、版本化精确主数据与物化 lookup key | `asset_instruments`、`md_instrument_identity_revisions`、`md_instrument_lookup_keys`；`test_identity.py`、`test_lookup_materializer.py` |
| AO-03 | 规范化不可变事实、pending/post-commit publication、恢复和交易日历 | `md_data_series`、`md_source_snapshots`、`md_observation_revisions`、`md_publications`、`md_calendar_*`；`test_storage_models.py`、`test_store.py`、`test_publication_recovery.py` |
| AO-04 | 严格公共查询契约和请求解析 | `MarketDataQueryRequest`、`MarketDataQueryResolver`；`test_query_contract.py`、`test_query_resolution.py` |
| AO-05 | 本地读取、覆盖规划、受控补齐、durable fetch lease 与重新读取 | `CoveragePlanner`、`MarketDataStore`、`MarketDataQueryService`、`MdFetchLease`；`test_coverage.py`、`test_fetch_lease.py`、`test_store.py`、`test_query_service.py` |
| AO-06 | AkShare 显式路由与 OpenBB 隔离、索引和 interval 协议 | `akshare_provider.py`、`providers.py`、`openbb_market_data_runner.py`；`test_akshare_provider.py`、`test_openbb_provider.py` |
| AO-07 | 关闭默认开关的 v2 HTTP 接口、遗留接口兼容、fail-closed 回退、受限策略缓存补齐与前端游标聚合 | `POST /api/v1/data/queries`、`useDataPage.ts`、`useStrategyPage.ts`、`test_query_api.py`、`marketData.test.ts`、`DataPage.test.ts`、`StrategyPage.test.ts` |
| AO-08 | 迭代 196 的策略研究/回测桥接、页面灰度和单头迁移整合 | 集成分支、`20260909_ai_research_market_data_merge`、真实环境证据；页面灰度仍未开启 |
| AO-09 | 21 个家族合同与当前 UI/API 输入的冻结基线范围清单 | `scope_manifest.py`、`generate_iteration197_scope_manifest.py`、`test_scope_manifest.py`、[SCOPE_MANIFEST.md](SCOPE_MANIFEST.md)；附带 196 冻结收据和当前候选 manifest |
| AO-10 | B1 单记录产品的逻辑目录、精确 family contract、来源路由与控制面选择 | `bootstrap.py`、`dataset_contracts.py`、`legacy_contract.py`、`akshare_provider.py`、`queries.py`、`test_dataset_contracts.py`、`test_akshare_provider.py`、`test_query_service.py`、`DataPage.test.ts`；`stock.liquidity`、`fund.liquidity`、`fx.range` 为候选代码开通，其余八个 B1 family 仍不提供事实读取 |
| AO-11 | 严格研究数据绑定、服务器侧 consumer scope、当前授权重放、撤销、trusted runtime 路径和文件读取完整性 | `md_research_data_bindings`、`md_research_data_binding_scopes`、`md_research_data_binding_consumers`、`md_research_data_binding_revocations`、`research_binding.py`、`workspace_unit_runtime.py`、`backtest/service.py`、`backtest_enhanced.py`、`test_research_binding.py`、`test_strategy_runtime_support.py`、`test_backtest_service.py` |

### 2.2 不可由本次离线自动化证明的事项

- 实际 AkShare、OpenBB 扩展及各上游数据源在某日可用、返回的数据质量、频率限制、账户权限或商业许可。
- MySQL/PostgreSQL 生产或准生产库的真实 Alembic 升级、回滚治理和性能表现。
- `/data/market` 与 `/investment/strategies` 的真实浏览器行为、真实用户权限、数据初始化完成后的页面展示。
- MySQL/PostgreSQL 与真实页面环境中的 196/197 工件链行为；本地单头迁移和绑定测试不能替代这些环境证据。
- `md_fetch_leases` 的代码级 owner/fence/expiry 协议在候选中已实现，但 SQLite/替身回归不能证明真实多 Web worker、多个进程/pod、数据库时钟、故障接管或零重复 provider 调用。
- 日历导入锁只串行化同一 `calendar_code` 的 calendar manifest 导入；它不是 observation/source snapshot 的多进程 writer lease，也不能证明并发写入的 ownership、fencing、接管或零重复网络调用。
- OpenBB 运行器在独立 service account/container 中的文件系统、挂载和凭据隔离；环境变量白名单与受控 `cwd` 不能证明该边界。
- fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` / `openbb-yfinance 1.6.3.post1` 的完整动态扩展导入闭包、不可变镜像、AGPL-3.0-only 许可证审查和最小出网审计；静态构件清单或离线 fork 测试都不能证明这些事项。
- 每个连接的 MySQL/PostgreSQL UTC session time zone、真实跨连接 PIT 行为和恢复后的时间比较。MySQL `DATETIME` 不保存时区，SQLite 时间行为不能替代。

这些事项必须在第 7 至第 10 节完成，不能用 mock、fixture、SQLite 或历史日志替代。

## 3. 验收前置条件

### 3.1 代码与环境前置条件

1. 验收在单独的 196/197 集成候选工作树或其待合并提交执行，不能在用户正在编辑的 `dev` 工作树中混跑。
2. Python 命令使用项目约定环境：

   ```bash
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python ...
   ```

3. 后端依赖、Alembic、测试依赖和数据库驱动已安装；测试数据库为一次性、可销毁的隔离库。
4. 验收记录必须保存：Git 提交 SHA、`git status --short`、Python/依赖版本、数据库方言和命令的退出码。未提交文件只能用于开发回归，不能作为发布候选的唯一证据。
5. 除第 8 节的受控外部验证外，测试不得读取或输出密钥、Cookie、数据库密码、OpenBB token 或真实用户数据。

### 3.2 数据与治理前置条件

1. 每个待启用逻辑数据集已注册唯一活动主存储；不存在歧义主绑定。
2. 请求所涉 canonical identity、已发布的冻结 identity projection、版本化主数据和精确 `(asset_type, market, symbol)` lookup key 均已导入并通过审核；strict resolver 的 PIT 证据是已发布 projection，不是可变 authority 行或单独 lookup key。
3. 对按事件判断完整性的 `bars` 或 `reference_series` 请求，窗口已具备冻结交易日历和对应 `(market, data_kind, frequency)` 的显式事件网格，或系统明确返回 `unknown_calendar` / `CALENDAR_GRID_UNAVAILABLE`；不得把空日历、周末规则、另一数据种类/频率的 session 或缺少日历的窗口当成完整覆盖。
4. 每个准备启用的来源策略均有经过审核的提供方、路由、数据许可、允许用途、字段/口径和保留策略记录。用于证明覆盖的每个 calendar manifest 还必须声明已注册的 `source_registry_id`、冻结治理描述符和 `VERIFIED` 状态；该 source ID 必须属于对应请求当前授权的 route source allow-list，否则 calendar 只能返回 `unknown_calendar`。
5. 参与 v2 灰度的用户已通过独立、经过批准的 RBAC provisioning 获得 `data:read`。当前注册流程不自动写入角色；不得为了开启市场数据读取而修改注册语义或把“已登录”视为授权。
6. 线上开关默认保持关闭：`MARKET_DATA_QUERY_V2_ENABLED=false`、`MARKET_DATA_ONLINE_FETCH_ENABLED=false`、`MARKET_DATA_RESEARCH_CACHE_FILL_ENABLED=false`、`VITE_MARKET_DATA_QUERY_V2_ENABLED=false`、`VITE_MARKET_DATA_QUERY_BUNDLE_ENABLED=false` 和 `VITE_MARKET_DATA_STRATEGY_BRIDGE_ENABLED=false`。前端 bundle 只能作为已启用页面 v2 的子开关；策略页 bridge 还必须等待 196/197 集成候选。`research_cache_fill` 还需要独立的后端开关、当前研究用途授权和本节其它 v2 前置条件；浏览器 flag 不构成写入授权。若开启 v2，运维管理的 `MARKET_DATA_CURSOR_SIGNING_KEY` 必须存在且至少 32 bytes；不得记录其值。只有完成本文件相应闸门后才可按灰度计划开启。
7. 若需启用 OpenBB，`OPENBB_MARKET_DATA_RUNNER`、恰为 `yfinance` 的 `OPENBB_ALLOWED_PROVIDERS`、独立且绝对存在的 `OPENBB_RUNNER_HOME` 与 `OPENBB_RUNNER_WORKDIR` 已由 runner 运维方审核；后二者不可缺失、回退为临时目录/主应用 HOME/工作树，主应用进程也不能把自身的数据库凭据、项目工作树或服务账户权限作为 runner 前置条件。当前 permit matrix 为空。fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` / `openbb-yfinance 1.6.3.post1` 仅是 `1d`、UTC 日对齐、最长 3650 天、包含式 OpenBB 日终到排他 yfinance `end` 的构件候选；在完整隔离导入闭包、不可变镜像、AGPL-3.0-only 许可证和最小出网审计完成前，正常请求必须在动态扩展导入前拒绝，不能用这些配置启用 route。
8. 启用 `MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_ENABLED` 前，必须有独立签名 key、受控 artifact root、当前 `data:read` 和 source registry/backtest 许可。通用 workspace create/batch API 不得接受任何 `market_data_binding_*` 字段；仅 AI 研究编排可在 unit 创建后写入服务器侧 consumer receipt。公共 `/api/v1/backtests/run` 与通用 `BacktestService.run_backtest` 不得接受客户端 `runtime_dir`；workspace unit 只能通过 server-only preflight 执行。

## 4. 必须执行的自动化回归

在 `src/backend/` 下执行。下述命令是候选版本的最小自动化门槛；可按故障定位拆分运行，但最终须至少有一次全量命令通过。

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q \
  tests/market_data_platform tests/test_config.py
```

建议在相同候选版本补充静态检查；若项目将 Ruff 放在该环境中：

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check \
  app/api/data app/models/market_data_platform.py app/schemas/market_data_platform.py \
  app/services/market_data scripts tests/market_data_platform tests/test_config.py
```

页面桥接的候选回归还须在 `src/frontend/` 执行：

```bash
npm run typecheck
npm run test -- --run \
  src/__tests__/api/marketData.test.ts \
  src/__tests__/views/DataPage.test.ts \
  src/__tests__/views/StrategyPage.test.ts
npm run build
npm run lint
```

自动化范围说明：AkShare 测试使用受控假函数，OpenBB 测试使用临时 JSON runner 与离线 fork 参数替身，数据库迁移测试使用 SQLite 和离线方言渲染。它们能证明边界契约、拒绝逻辑、单进程日历网格/字段可用修订/singleflight，以及 durable lease 的 owner/follower/接管/fence 单元语义；不能证明真实第三方服务、真实 OpenBB/yfinance 网络请求、完整动态扩展导入闭包、不可变镜像、AGPL-3.0-only 许可证、操作系统级 OpenBB 隔离、真实跨 worker 去重或生产数据库。

## 5. 自动化验收矩阵与执行记录

### 5.1 当前可复现证据状态

| 记录 ID | 命令/工件 | 覆盖范围 | 正式候选状态 | 可接受的 PASS 证据 |
| --- | --- | --- | --- | --- |
| E-197-01 | 第 4 节完整 `pytest` 命令 | AO-01 至 AO-07 与中台配置的离线契约 | `NOT_RUN` | 候选提交上的完整 stdout 摘要、退出码 0、测试总数。 |
| E-197-02 | 第 4 节 Ruff 命令 | 新增/修改的中台模块和测试 | `NOT_RUN` | 候选提交上的退出码 0；若工具未安装，应记录为 `BLOCKED`，不得静默跳过。 |
| E-197-03 | `alembic heads` 与升级后 schema 审计 | 196/197 整合后的单 head 和 binding scope/consumer/revocation 表 | `NOT_RUN`（正式候选） | 输出恰有一个 head，临时隔离库升级后存在四张 binding receipt 表；MySQL/PostgreSQL 仍需独立演练。 |
| E-197-04 | 真实 AkShare 受控探测 | 实时路由及三个 B1 候选路由的字段、时间窗、回执和写回 | `FAIL`（已执行 `stock.liquidity`；其它真实 AkShare 路线仍为 `NOT_RUN`） | 第 8.1 节的匿名化请求/响应摘要、来源回执和本地复读证据。 |
| E-197-05 | 真实 OpenBB 隔离运行器探测 | runner 环境、协议、上游许可与写回 | `BLOCKED` | 第 8.2 节的隔离进程、镜像/动态导入闭包、许可证/出网审计、协议日志摘要、原始载荷 hash、回执和本地复读证据；当前 permit matrix 为空。fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` / `openbb-yfinance 1.6.3.post1` 只是 `1d` daily end-bound 构件候选，正常请求在动态扩展导入前拒绝，不能记为成功验证。 |
| E-197-06 | `/data/market`、`/investment/strategies` 端到端回归 | 页面灰度、授权、回退防护、196 工件绑定 | `NOT_RUN` | 保存浏览器/API/数据库三方一致证据；196 冻结和桥接不等于浏览器或真实数据通过。 |
| E-197-07 | MySQL/PostgreSQL UTC session、PIT 与 exact-identity collation 演练 | 时区、跨连接写入/读取、迁移、恢复及 `RB0`/`rb0` 精确身份 | `NOT_RUN` | 每个新连接的会话时区输出、边界时间写入/读取、迁移和恢复记录，以及 authority/projection/lookup 的 MySQL `utf8mb4_bin`、PostgreSQL `C` 实际列审计和 case-distinct lookup 回归。 |
| E-197-08 | 多 worker/多进程同缺口及事实写入并发 | 跨进程 writer lease/fencing、故障接管和零重复外部访问 | `NOT_RUN` | L-197-10 已在 disposable PostgreSQL 以两个 OS 进程和确定性 provider 证明一个精确缺口只有一次调用，且 follower 从本地重读；仍需真实 AkShare/OpenBB、应用 HTTP worker、故障接管与崩溃恢复证据。当前 AkShare thread timeout 不能杀死底层同步调用，故超时后的零重复 I/O 为 `NO-GO`，直至可终止 runner 或租约 heartbeat 设计通过验收。calendar import lock 不适用于 observation 写入。 |
| E-197-09 | OpenBB 操作系统级隔离 | service account/container、挂载、凭据与工作目录 | `NOT_RUN` | runner 账户/容器配置、挂载清单、权限审计和一次实际小窗口回填。 |
| E-197-10 | 策略页 `research_cache_fill` 灰度 | 显式用户动作、后端写入开关、研究用途授权、receipt 与 196 工件隔离 | `NOT_RUN` | 前端显式预检、后端开关与已批准研究用途 source registry、浏览器/API/数据库三方证据。 |
| E-197-11 | 严格 research binding 安全回归 | AO-11：scope/consumer、fresh-snapshot 授权重放、撤销、trusted runtime、运行时文件读取 | `NOT_RUN`（正式候选） | 绑定、复制 token、撤销 `data:read`、来源拒绝、证据漂移、撤销 receipt、workspace 改为 trading、排队重试/子进程前撤销、客户端 `runtime_dir`、路径替换/符号链接的回归均通过；不得以此替代真实 provider 或浏览器运行。 |

`E-197-01`、`E-197-02`、`E-197-03` 与 `E-197-11` 的状态仅表示正式候选；本地工作树回归单列于下节。`E-197-04` 已有一次真实子用例失败，不能以其它离线通过记录覆盖为 `NOT_RUN` 或 `PASS`。本地命令退出码、冻结收据和已合并的 Alembic 图均不能升级为真实环境或发布签收。

### 5.1.1 当前本地执行记录（不改变正式候选状态）

以下结果来自独立迭代 197 候选提交（均为 2026-09-09），仅作为可复核的本地开发证据；它们不替代第 4 节的正式候选、真实环境或 196 整合回归。若记录包含已经执行的真实子用例，其失败结果必须如 L-197-11 一样同步反映在上表，不能被其它 `NOT_RUN` / `BLOCKED` 记录掩盖。

| 记录 ID | 时间快照与命令范围 | 本地结果 | 对正式验收的含义 |
| --- | --- | --- | --- |
| L-197-01 | 2026-09-09，`/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform tests/test_config.py`，候选提交 `8a2be6b7`。 | `PASS`：416 passed、45 warnings，85.31s。 | 覆盖 AO-01 至 AO-07 与中台配置、PIT visibility anchor、当前读取授权、来源回执证据、calendar 同源授权和 SQLite 来源治理迁移的离线后端开发回归；不能将 E-197-01 或任一 AC 改为正式 `PASS`。 |
| L-197-02 | 2026-09-09，第 4 节列出的中台目标 Ruff 命令与 `python -m compileall -q` 目标模块检查，候选提交 `8a2be6b7`。 | `PASS`：两个命令退出码均为 0，未报告目标范围内的 Ruff 违规或编译错误。 | 只证明该工作树的目标静态检查；不能将 E-197-02 改为正式 `PASS`。 |
| L-197-03 | 2026-09-09，`npm run typecheck`、三个 v2 测试文件、`npm run build`、`npm run lint`，候选提交 `8a2be6b7`。 | `PASS`：typecheck 退出码 0；v2 测试 144 passed；build 退出码 0；lint 为 0 errors、1,208 条既有 warnings。 | 仅支持前端开发回归；未执行真实浏览器 E2E。1,208 条 warning 不等于零告警或生产质量签收，且不证明浏览器灰度、真实 API 或 196 整合。 |
| L-197-04 | 2026-09-09，当前独立 197 候选工作树执行 `/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform tests/test_config.py`。 | `PASS`：445 passed、62 warnings，95.41s；包括 durable fetch lease、family binding、legacy exact-echo、SQLite exact-identity migration，以及 authority、projection 和 lookup 三层 `RB0`/`rb0` 的 fail-closed 回归。 | 这是离线开发回归，不是 MySQL/PostgreSQL 排序规则或真实多 worker、第三方 provider、196 集成的通过证据；E-197-01、E-197-07、E-197-08 保持原状态。 |
| L-197-05 | 历史快照（2026-09-09）：`alembic -c alembic.ini heads` 与临时 SQLite `alembic upgrade head`。 | `PASS`：当时独立 197 链只有 `20260909_market_data_exact_identity_collation` 一个 head；临时库升级至该 revision，`asset_instruments`、`md_fetch_leases`、lookup 和 frozen identity 表存在。 | 此记录不描述当前 head；只证明当时独立链和 SQLite 默认 `BINARY` 路径，196 合并单 head 与 MySQL/PostgreSQL DDL/排序规则仍未运行。 |
| L-197-06 | 2026-09-09，`npm run test -- --run src/__tests__/api/marketData.test.ts src/__tests__/views/DataPage.test.ts src/__tests__/views/StrategyPage.test.ts`、`npm run typecheck`、`npm run build`、`npm run lint`。 | `PASS`：154 tests、typecheck/build 退出码 0、lint 0 errors/1,208 warnings。 | 仅支持页面适配与默认关闭的策略 sidecar 开关；Vitest 的组件 stub、Browserslist/构建 chunk 警告和既有 lint warnings 不构成真实浏览器或部署验收。 |
| L-197-07 | 历史快照（2026-09-09），候选提交 `1b1c74f3`：`/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform tests/test_config.py`、目标 Ruff、`alembic heads`、三份 v2 前端测试、`npm run typecheck`、`npm run build`、`npm run lint`。 | `PASS`：后端 453 passed/62 warnings（98.23s），目标 Ruff 通过；当时独立链 head 为 `20260909_market_data_exact_identity_collation`，前端 157 tests/typecheck/build 通过，lint 为 0 errors/1,225 warnings。 | 此记录不描述当前 head；覆盖 B1-0 逻辑目录与精确 family shape、`research_cache_fill` 授权/开关、AkShare provenance hash 修复以及页面控制面展示；仍只是提交前后同一代码快照的本地开发回归，不能把 E-197-01 至 E-197-10 或 AC-197-023 标为正式通过。 |
| L-197-08 | 历史快照（2026-09-09），代码候选 `c29d2d72`（包含前端 `0289dfdd`）执行完整后端命令、全中台 Ruff/`compileall`、`alembic heads`、一次性 SQLite `upgrade head`，以及三份 v2 前端测试、typecheck、build、lint。 | `PASS`：后端 `468 passed, 62 warnings`（107.08s）；Ruff 与 `compileall` 退出码 0；当时独立链唯一 head 为 `20260909_market_data_exact_identity_collation`，临时 SQLite 升级到该 revision 且 `asset_instruments`、`md_fetch_leases`、identity/lookup 表存在；前端 163 tests、typecheck/build 通过，lint 为 0 errors/1,225 warnings。 | 此记录不描述当前 head；覆盖 B1 三个候选 family 的精确 route/合同、reference-series calendar-grid 上限、`DATA_KIND_COVERAGE_UNSUPPORTED` 的多记录拒绝、市场页显式选择/在途请求作废/必填字段拒绝及范围清单。它仍只是独立工作树中的离线开发证据；E-197-01 至 E-197-10、真实 provider/多方言/多 worker、浏览器灰度和 196 整合状态均不变。 |
| L-197-09 | 历史快照（2026-09-09），候选代码提交 `a37f0514`、`b3c52283`、`b978b3a7`：完整后端命令、目标 Ruff/`compileall`、`alembic heads`、临时 SQLite `upgrade head`，以及三份 v2 前端测试、typecheck、build、lint。 | `PASS`：后端 `473 passed, 62 warnings`（99.83s）；Ruff 与 `compileall` 退出码 0；当时独立链唯一 head 为 `20260909_market_data_exact_identity_collation`，临时 SQLite 升级到该 revision 且 `asset_instruments`、`md_fetch_leases`、`md_instrument_lookup_keys`、`md_observation_revisions` 存在。 | 此记录不描述当前 head，也不覆盖随后发现并修复的 OpenBB P1；不得据此推断当前候选没有 P0/P1。其余覆盖范围与外部 `NOT_RUN` 边界保持历史记录所述。 |
| L-197-10 | 2026-09-09，代码候选提交 `58def33f`（含 `97fbb4d9`）：完整后端回归、目标 Ruff/`compileall`、`alembic heads`、`verify_iteration197_postgres_acceptance.py --apply`，以及三份 v2 前端测试、typecheck、build、lint。 | `PASS`：后端 `517 passed, 64 warnings`（107.33s）；Ruff/`compileall` 通过；独立 197 链 head 为 `20260909_market_data_constraint_name_portability`；在此代码提交上 disposable PostgreSQL fresh 与 predecessor→head 演练均通过，两个连接为 UTC，两个 OS 进程竞争一个精确缺口仅 1 次确定性 provider 调用，follower `local_only` 读取 2 条事实且 0 次调用，3 个截断历史 CHECK 名迁移为 portable 名，source/calendar sentinel 各 1 条保留，短 SHA 被拒绝，临时库 cleanup 完成；前端 166 tests、typecheck/build 通过，lint 为 0 errors/1,225 条既有 warnings。OpenBB `--self-check` 无网络地报告空 permit matrix 和 `OPENBB_YFINANCE_OUTBOUND_END_BOUND_UNATTESTED`；AkShare 验收脚本默认返回 `LIVE_CONFIRMATION_REQUIRED`，未发起网络或写库。 | 这是当前独立候选的本地、disposable PostgreSQL 与前端开发证据；其中 provider 为确定性 fixture，不能替代真实 AkShare/OpenBB、MySQL、HTTP/deployment worker、故障接管、OS 隔离、浏览器 E2E 或 196 整合。它不决定后续真实子用例的状态；L-197-11 已单列记录 E-197-04 的失败。 |
| L-197-11 | 2026-09-09，代码候选提交 `bea8835d`：焦点离线命令 `/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform/test_akshare_live_acceptance_harness.py`、目标 Ruff/`compileall`，以及显式实时命令 `/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python scripts/accept_iteration197_akshare_stock_liquidity.py --live --trading-date 2024-09-02`。 | 焦点回归 `PASS`：8 passed；Ruff/`compileall` 通过。实时子用例 `FAIL`（退出码 1）：`stock.liquidity` / `akshare-stock-liquidity-primary-v1` / `reference_series` / `1d` 发起 1 次 provider 调用，安全计数为 `result_count=1`、`response_row_count=0`、`normalized_observation_count=0`；临时库内 persisted fetch/receipt 为 1，观测、passing、failed 均为 0，coverage 为 `incomplete`，无 warning；临时数据库删除成功，未输出原始载荷或凭据。 | 这证明本次适配器看到的响应行数为零，且没有出现字段、身份、时间窗验证或持久化拒绝；它不证明请求日期或上游语义本身正确。没有形成可用 observation revision、完整覆盖或独立 `local_only` 复读证据。因此 E-197-04 为 `FAIL`（该子用例），其它 AkShare 路线、真实许可和成功写回验收仍未执行。 |
| L-197-12 | 2026-09-09，196/197 集成候选工作树：`pytest -q tests/market_data_platform/test_research_binding.py tests/test_strategy_runtime_support.py tests/test_workspace_service.py`、目标 Ruff、`alembic heads`、一次性 SQLite `upgrade head`，以及 scope manifest `--validate`。 | `PASS`：72 passed、1 warning；Ruff 通过；唯一 head 为 `20260909_market_data_research_binding_consumers`；隔离 SQLite 已升级并确认 `bindings`、`scopes`、`consumers`、`revocations` 四张表；scope manifest 返回 `SCOPE_MANIFEST_VALID`。 | 证明本候选的 strict binding、迁移图和冻结范围输入在本地可复核；不替代 MySQL/PostgreSQL、真实 provider、浏览器或部署验收。 |
| L-197-13 | 2026-09-09，196/197 集成候选源提交 `974b7237`：`pytest -q tests/market_data_platform/test_research_binding.py tests/market_data_platform/test_research_binding_migrations.py tests/test_ai_strategy_research_service.py tests/test_strategy_runtime_support.py tests/test_workspace_service.py tests/test_workspace_reconciliation.py tests/test_backtest_service.py tests/test_backtest_enhanced.py tests/test_task_lifecycle_contract.py`；`pytest -q tests/market_data_platform tests/test_config.py`；工作区/Copilot 公开入口回归；目标 Ruff；`alembic heads`、新 SQLite `upgrade head` 与 scope manifest `--validate`。 | `PASS`（仅本地）：严格绑定候选 398 passed、29 warnings（395.25s）；工作区/Copilot 36 passed、1 warning；中台/配置 556 passed、88 warnings（163.62s）；Ruff 通过；唯一 head 为 `20260909_market_data_research_binding_consumers`；新 SQLite 已确认 `bindings`、`scopes`、`consumers`、`revocations` 四张表；scope manifest 返回 `SCOPE_MANIFEST_VALID`。 | 证明当前集成候选的本地代码、迁移图和 strict binding 回归可复核。当前检出没有 `vue-tsc`/`vite` 可执行文件，前端 typecheck/build 为 `NOT_RUN`；真实 MySQL/PostgreSQL、真实 provider、浏览器和部署验收仍不因此变为通过。 |

`L-197-01` 包含 identity projection、observation PIT、pending publication 恢复、来源回执、同一 provider 的一次性 request ID 唯一性和 calendar 同源授权、SQLite 来源治理升级/降级保护、MySQL `DATETIME(6)` DDL/fsp=0 拒绝、相邻 calendar segment/import lock，以及 OpenBB 预规范化原始封套和进程组回收的离线断言。本地可观察语义如下；T0/T1/T2 仅描述 SQLite fixture 内的逻辑可见性，不表示真实多连接数据库已验收：

1. **冻结 identity projection**：T0 为事务 A 已提交、事务 B 尚未发布；即使 cutoff 晚于计划的 publication instant，resolver 仍返回 `IDENTITY_NOT_FOUND`。事务 B 后在 `published_at - 1 microsecond` 返回 `IDENTITY_NOT_KNOWN_AT_CUTOFF`（T1），在 `published_at` 返回冻结 projection（T2）。
2. **observation PIT**：提供方自报时间为 T0=10:00，平台本地收据时间为 T1=14:00；测试在 13:00（已晚于 T0、仍早于 T1）和 T1 恰好时读取均为空，事务 B 将可见性推进至 T2=14:00:00.000001 后才返回观测。这证明来源自报时间不能回填本地可见性。
3. **滚动日历与锁**：本地依次导入 `[2026-09-01, 2026-09-03)` 与 `[2026-09-03, 2026-09-05)` 两个已发布 segment；读取获得 `KNOWN` 的 composed calendar、四个连续 event，并在 `md_calendar_import_locks` 中只保留一条 `CN-SSE` sentinel。重叠 window 仍由独立测试拒绝。

### 5.2 契约级验收案例

| 验收 ID | 验收场景与操作 | 预期可观察结果 | 关联测试/证据 | 正式候选状态 |
| --- | --- | --- | --- | --- |
| AC-197-001 | 解析目录时仅使用活动、唯一的逻辑数据集主绑定；注入缺失、失活、歧义或损坏绑定。 | 返回稳定目录错误；不会根据遗留表名或端点猜测存储。 | `test_catalog.py` | `NOT_RUN` |
| AC-197-002 | 升级目录和事实迁移，并在含有遗留 AkShare 元数据/事实的测试库检查前后状态。 | 新表、索引、约束完整；遗留表/行不被重写；有数据时降级受治理保护。 | `test_catalog.py`、`test_storage_models.py` | `NOT_RUN` |
| AC-197-003 | 用 canonical ID 或完整精确三元组解析主数据；尝试邻近代码、大小写近似、过期/重叠版本和高基数市场。对 MySQL/PG 实例分别登记 `RB0`/`rb0`，并用错误大小写请求 legacy contract。 | strict resolver 只接受一条精确、有效、完整且已发布的冻结 identity projection；两个合法 case-distinct 标识各自解析，错误大小写稳定失败，绝不替换为附近标的。 | `test_identity.py`、`test_lookup_materializer.py`、`test_legacy_contract.py`、`test_storage_models.py`；真实方言 E-197-07 | `NOT_RUN` |
| AC-197-004 | 在严格截止点后才写入或尚处于 pending publication 的 identity projection、calendar snapshot 或观测修订，尝试用于更早的研究/回测查询。 | 返回不可见/稳定失败；只有 `published_at <= knowledge_cutoff` 的 hash 匹配 receipt 可见，晚回填不能穿越 cutoff。 | `test_identity.py`、`test_store.py`、`test_query_service.py`；L-197-01 | `NOT_RUN` |
| AC-197-005 | 校验公共 DTO 的 selector 互斥、UTC 时间、半开区间、频率、字段集合、用途/一致性和语义指纹；再提交缺少 family binding 的 `option_chain` 与 `crypto bars` 原始请求，以及绑定到未配置 `option.derivative` 的请求。 | 无歧义请求被规范化；符号单独输入、重复字段、朴素时间、错误 strict 设置在 API 前失败。公共 HTTP 缺少 binding 在 catalog/identity/provider 前以 schema HTTP 422 拒绝；抵达 resolver 的任何未绑定内部规范化请求以 `DATA_FAMILY_BINDING_REQUIRED` 拒绝。未配置家族以 `DATA_FAMILY_UNCONFIGURED` 拒绝，不能静默按 `bars` 或其他产品执行。 | `test_query_contract.py`、`test_query_resolution.py`、`test_query_api.py` | `NOT_RUN` |
| AC-197-006 | 对完整、缺头/中间/尾、空和无日历的本地数据运行覆盖规划；同一市场导入日线、周线、月线和缺失分钟网格。 | 只有请求对应的冻结、范围充分、显式频率网格能证明 `complete`；其它情况返回精确 gaps 或 `unknown_calendar` / `CALENDAR_GRID_UNAVAILABLE`，不会由另一个频率推断。 | `test_coverage.py`、`test_calendar_importer.py`、`test_store.py` | `NOT_RUN` |
| AC-197-007 | 对同一 event 先写入完整字段修订，再写入较新的窄字段修订，并以宽/窄字段集和两个知识截止点读取。 | 来源回执和修订追加保留；宽请求仍选择旧的完整可用修订，窄请求可选择更新修订；早 cutoff 不见晚提交修订；不同修订字段不拼接。 | `test_store.py` | `NOT_RUN` |
| AC-197-008 | 本地完整、local-only 缺口、local-first 缺口、日历未知、在线关闭和严格历史查询分别执行。 | 完整本地不触网；`local_only` 永不触网；成功补齐后只从本地返回；未知日历不声称完整；严格历史不以实时获取污染回放。 | `test_query_service.py` | `NOT_RUN` |
| AC-197-009 | 提供方返回的 provider ID、关联请求、时间窗、事件或来源回执与路由/原始请求不一致。 | 结果不持久化；返回稳定 warning/error；后续批准路由可在仍有真实缺口时按优先级尝试。 | `test_query_service.py`、`test_store.py`、`test_openbb_provider.py` | `NOT_RUN` |
| AC-197-010 | 使用假 AkShare SDK 返回正确/错误代码、不同市场、越界时间、超大表、超时和不支持语义；另对股票/ETF流动性和 FX range 验证精确 route ID、字段与口径。 | 显式路由只接受批准的资产/市场/口径；`stock.liquidity` 与 `fund.liquidity` 只能走其 `reference_series` route，`fx.range` 必须保留完整 OHLC；响应被截为半开区间；不支持项快速失败，不走样例或其它资产。 | `test_akshare_provider.py` | `NOT_RUN` |
| AC-197-011 | 使用临时 OpenBB JSON runner 验证正常协议、错配 request ID、未配置或非法 runner 命令、无界/朴素请求、stdout/stderr 超限、预规范化原始封套/hash、受控 HOME/工作目录，以及 timeout 后的子进程回收；对真实 runner 只执行无网络 `--self-check` 和一条表面合法 yfinance DTO 的导入前拒绝。 | 主进程只交互 JSON；协议错配、缺/非法 runner、非法 HOME/cwd、任一输出流越过上限、无 `format`/records 映射封套、自洽摘要替代原始 records、hash 不一致均失败关闭；POSIX timeout/cancel 终止 runner 专属进程组，即使 leader 已退出而后代仍持有管道。`--self-check` 不导入 OpenBB、不联网、不输出密钥、绝对包路径或文件哈希，只给出协议/包元数据摘要、构件候选状态、空 permit coverage 和非敏感配置摘要。环境 provider 列表必须恰为 `yfinance`，扩展 token 拒绝。当前无 permit/route，且构件清单仍为 `candidate`；即使包文件匹配，候选、未封装或与清单不匹配的环境均以 `OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED` 在动态扩展导入前拒绝。静态构件自检不能升级为安装、许可或网络验证。 | `test_openbb_provider.py` | `NOT_RUN` |
| AC-197-012 | 在后端和浏览器 v2 开关关闭/开启的替身服务下调用 `POST /api/v1/data/queries`，并检查遗留数据路由和前端 v2 合约桥接。 | 浏览器 v2 关闭时，行情页不请求 contract、bundle 或事实接口，策略页不请求 bridge；默认后端为 503 稳定码。开启后默认选择 `<asset_type>.realtime`；只有 bundle 已签发且用户明确选择本资产的 `ready + calendar_grid + 无维度` 的 `bars/reference_series` family 时，contract 才带该精确 binding。流动性显示声明字段表，`fx.range` 才使用 OHLC/K线；`crypto.realtime` 未配置时页面不执行事实或 legacy 数据读取来伪装 v2。输入错误在服务执行前 422；遗留接口仍注册。bundle 已签发后，v2 binding/必填字段/执行错误不能静默回退旧接口；普通行情查询使用 v2 `local_first`，`refresh` 仅由明确操作发出。 | `test_query_api.py`、`marketData.test.ts`、`DataPage.test.ts`、`StrategyPage.test.ts` | `NOT_RUN` |
| AC-197-013 | 两个同一 Web 进程、同一事件循环内的等价 `local_first` 缺口并发到达；并发 `refresh` 请求单列。 | 只有 `local_first` leader 发起一次 provider 调用并提交；follower 在独立 session 上复读持久化结果；`refresh` 保持各自执行语义而不复用 `local_first` follower；leader 取消/失败不遗留后台事务。 | `test_query_api.py`、本地优先持久化回归 | `NOT_RUN` |
| AC-197-014 | 多 Web worker/多进程的同一缺口或事实写入并发到达；分别模拟 follower、到期接管、陈旧 owner 写事实、事务 A 后 B 前失去 fence、release 丢失、通用 recovery 跳过 fenced pending receipt、provider 计数和 AkShare timeout 后同步线程仍运行。 | 候选代码以 `md_fetch_leases` 保证 exact-gap owner/follower、递增 fence、事实/可见性双栅栏；follower 不调用 provider，generic recovery 不会发布任何 fenced source receipt。真实 MySQL/PostgreSQL 多进程、数据库时间、崩溃/接管和零重复调用计数未完成前保持 `NOT_RUN`；AkShare timeout 的零重复 I/O 在可终止 runner 或心跳租约设计完成前为 `NO-GO`，不可因 SQLite 或单进程测试改写为 `PASS`。 | `test_fetch_lease.py`、`test_store.py`、`test_query_service.py`；真实多 worker 压测 | `NOT_RUN` |
| AC-197-015 | 在事务 A 写入 source snapshot、observation revisions 和 pending `MdPublication` 后模拟提交、读取、进程中断/恢复。分别覆盖普通 calendar/identity receipt 与带 lease generation 的 source receipt。 | A 已提交但无 `published_at` 的事实 durable-but-hidden；coverage、API 和 strict replay 均不可见。非 source-fenced receipt 可由受控通用恢复完成事务 B。带 lease generation 的 source receipt 只能由未过期的 exact owner/fence 协调路径完成 B；通用 recovery 必须跳过它。owner 已丢失、到期或崩溃时该 receipt 只保留审计证据，新的 owner 必须重新获取并写入新 receipt，不能发布旧事实。 | `publication.py`、`test_store.py`、`test_publication_recovery.py`；observation T0/T1/T2 见 L-197-01 | `NOT_RUN` |
| AC-197-016 | 先后导入首尾相接的 calendar manifest，再导入重叠 manifest；并发导入同一 `calendar_code`，并在事务 A/B 间读取。 | 已发布且时区一致的相邻 segments 可连续覆盖窗口；孔洞、重叠、重复 event 或缺少频率 grid 返回 typed unknown。`md_calendar_import_locks` 串行化同代码导入，pending segment 在 publication 前不可见。 | `test_calendar_importer.py`、`test_store.py`；相邻 segments/单 lock 见 L-197-01；MySQL/PostgreSQL 并发演练 | `NOT_RUN` |
| AC-197-017 | 发布 identity projection 后修改可变 `asset_instruments` authority；另写入 pending projection 并以两个 cutoff 严格解析。 | strict resolver 不因可变 authority/裸 lookup key 改写历史；只按已发布 frozen revision、有效期和 cutoff 解析。pending projection 不可见，发布后才在合适 cutoff 出现。 | `test_identity.py`、`identity_projection.py`；identity T0/T1/T2 见 L-197-01 | `NOT_RUN` |
| AC-197-018 | 让行情页 v2 返回超过 500 条的多页响应（当前开发回归为 17 页、516 条），并注入 query ID、identity/observation knowledge cutoff、revision 不一致、重复 cursor、篡改签名或不同 HMAC key 签发的 token。 | helper 持续收集至 `next_cursor=null`，不以 500 条或固定页数截断；任何分页完整性不一致 fail closed。签名不符在本地读取、provider 调用或写入前以 `CURSOR_SIGNATURE_INVALID` 拒绝。 | `src/__tests__/views/DataPage.test.ts`、`test_query_service.py`；见 L-197-01、L-197-03 | `NOT_RUN` |
| AC-197-019 | 对 date-indexed OpenBB `OBBject` 和离线 yfinance fork 参数转换请求 UTC 日对齐的 `1d` 半开边界、最长 3650 天边界、超长窗口、`1w`/`1mo`、分钟和非日对齐窗口；真实 runner 只允许验证导入前拒绝。 | 离线代码以 `to_df(index=None)` 保留 event 时间。fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` / `openbb-yfinance 1.6.3.post1` 只允许 `1d`：由父 `[start,end)` 的最后一个 UTC 日得到 OpenBB 包含式 `end_date`，并以 `period=None` 向 yfinance 传递该日期加一天的排他 `end`；保存结果仍裁剪回父窗口。`1w`、`1mo`、分钟、非 UTC 日对齐和超过 3650 天的窗口必须在扩展导入前拒绝。离线 fork 测试不证明真实出站请求、返回数据或许可。未来还必须证明完整隔离导入闭包、不可变镜像、AGPL-3.0-only 许可证、出网审计、static permit/source-policy/provider DTO/runner mirror 的逐轴一致性；当前 permit 为空，正常请求不得导入扩展或测试网络。 | `test_openbb_provider.py`、fork 离线测试；第 8.2 节真实运行器演练 | `BLOCKED` |
| AC-197-020 | 用无 `data:read` 用户访问 `query-bundle`、`query-contract` 和事实查询；再分别使用失效/未授权主来源、仍获准 fallback、本地旧/compatibility 来源、撤权 calendar、授权变更后的 cursor、provider 请求期间撤销角色/registry、同一 provider 的重复 request ID、以及 provider DTO hash 错配执行查询/写入。 | 无读取权在家族、目录、主数据、calendar 或事实 I/O 前 403；只允许当前 registry 批准的 route source、`VERIFIED` `MdSourceSnapshot` 和位于同一 allow-list 的 `VERIFIED` calendar 参与读取。成功获取分别保存静态 policy 摘要、动态 access-grant 摘要和冻结 source authorization；无 grant 不能触发在线写入，显式 compatibility 回执不进入 v2 结果。网络返回后的 current/locking recheck、旧 cursor 或 follower 重读若发现角色/registry 改变均失败关闭；同一 provider 的重复 request ID 与错误 request evidence 均不落库。 | `test_access_authorization.py`、`test_query_service.py`、`test_store.py`、`test_storage_models.py`、`test_calendar_importer.py`、`test_query_api.py` | `NOT_RUN` |
| AC-197-021 | 对同一 snapshot 的多条 `option_chain`（不同 expiry/strike/right）和同一 report date 的多条 `position_report`（不同 reporting entity/rank）发起请求；分别尝试未绑定和绑定到目前未配置家族的路径。 | **NO-GO：当前不把这类请求视为可执行的数据产品。** 公共 HTTP 未绑定请求在 catalog/identity/provider 前以 schema HTTP 422 拒绝；抵达 resolver 的未绑定内部请求以 `DATA_FAMILY_BINDING_REQUIRED` 拒绝；已绑定的未配置家族以 `DATA_FAMILY_UNCONFIGURED` 拒绝。任何未来启用必须先证明稳定 record key、事实唯一性/读取/分页/provenance、slice/report completeness 及同一时间多行 `provider → store → PIT replay`；本地单行或空响应不能作为通过证据。 | `test_query_resolution.py`、`test_query_api.py`；未来多记录端到端回归 | `BLOCKED` |
| AC-197-022 | 自动输入预检和用户明确策略预检分别执行；后者尝试手工构造错误 mode/consistency/cutoff/cursor、关闭后端开关、display-only source、research-only source、成功 receipt 与不完整响应。 | 自动预检只能 `local_only + research + strict` 且不触网。显式补齐只能 `local_first + research_cache_fill + display`，无 cutoff/cursor；后端开关关闭时以 `MARKET_DATA_RESEARCH_CACHE_FILL_DISABLED` 拒绝，display-only source 不可借用。成功时只保存带该 purpose 的中台 receipt/revision 并本地复读，页面不得把它改写为迭代 196 precheck 通过、研究/回测/审批工件或 PIT 证据。 | `test_query_contract.py`、`test_query_api.py`、`test_access_authorization.py`、`test_store.py`、`StrategyPage.test.ts`；真实 E-197-10 | `BLOCKED` |
| AC-197-023 | 对 11 个 B1 单记录 family 读取 bundle；分别执行 `stock.liquidity`、`fund.liquidity`、`fx.range` 的精确 contract/route 离线检查，执行 `stock.liquidity` 的 provider→store→local reread 共享 calendar-grid 链路，并尝试用 DTO、静态卡片、dataset code 或 source policy 交叉升级其它 family。 | 六个逻辑 dataset 保留独立 schema/字段/资产范围并共用不可变 revision binding；DTO/registry/路由逐轴核对精确 family shape。三个候选 B1 的 `adjustment`、`price_basis`、`currency`、`unit` 都是必传的精确值：FX 的 `null` 轴必须保留在 JSON 中，省略或变更任一轴在 provider I/O 前稳定拒绝。只有上述三个 B1 family 可在候选代码中由用户显式选择：两个流动性 family 使用各自的 `reference_series` AkShare route，FX range 使用完整 OHLC route。其余八个 B1 family 仍为 `unconfigured`，不能产生 provider 调用或事实读取；B2 多记录 family 仍稳定拒绝。真实来源、日历、写回和每个 family 的 `provider → store → local_only` 证据完成前，三个候选开通项也不得标为正式可用。 | `test_bootstrap.py`、`test_dataset_contracts.py`、`test_legacy_contract.py`、`test_akshare_provider.py`、`test_query_service.py`、`marketData.test.ts`、`DataPage.test.ts`；未来逐项 B1 端到端验收 | `NOT_RUN` |
| AC-197-024 | 对已绑定 research unit 依次尝试复制 token 到另一 unit、修改 workspace 为 trading、撤销 `data:read`、拒绝/变更当前 source evidence、在 fresh replay 后禁用 sealed source registry、在长 replay 间提交撤销 receipt、篡改 unit binding 字段、客户端传入 `runtime_dir`、排队重试或子进程启动前撤销、同一 unit 的两个合法 OOS 请求并发运行、停止发生在 preflight/task promotion 边界、延迟 poller 回写，以及替换 CSV 路径或插入 symlink。 | 浏览器 create/batch 在写 unit 前以 `MARKET_DATA_BINDING_CONSUMER_CREATE_FORBIDDEN` 拒绝；仅私有 AI 编排可建立 exact `(binding,user,intent,workspace,unit)` consumer。每次任务创建、并发槽重试和子进程启动前都必须在 fresh session 重读 unit、重放当前 strict `local_only + backtest + PIT` 查询并逐条比较 sealed evidence；最终 current-read fence 锁定 sealed snapshots 与 registry 并重新授权。严格绑定 unit 必须先由数据库 CAS 取得唯一租约，竞争请求不读绑定、不写 runtime、不创建第二 task；task 仅在租约原子提升为 task ID 后调度，取消/轮询/终态写入只能 CAS 当前 owner，未知/超时观察不得释放运行权。任何 scope/consumer、权限、来源、撤销、身份、窗口、HMAC、artifact hash、租约或 fd-path-chain 失败均不创建或执行 runtime/backtest，并使被拒绝的 bound runtime 不可执行；若共享确定性目录仍可能属于新 lease，失败路径不得删除或覆写它，以避免 ABA。公共 API/通用 service 以 `BACKTEST_RUNTIME_DIR_CLIENT_FORBIDDEN` 拒绝客户端目录。读取 CSV 使用同一已验证 `O_NOFOLLOW` 文件描述符，路径替换不能改变 pandas 读取的 inode。 | `test_research_binding.py`、`test_strategy_runtime_support.py`、`test_workspace_service.py`、`test_backtest_service.py`、`test_backtest_enhanced.py`；最终候选本地记录 | `NOT_RUN`（正式候选） |

## 6. 数据中台专项验收

### 6.1 本地优先与可追溯性

对每个将启用的 `(dataset_code, canonical_id, data_kind, frequency, adjustment, price_basis, currency, unit, source_policy_id)` 组合执行下列试验，并保存结果：

1. **本地命中**：准备覆盖完整的本地版本、合格字段和请求频率的冻结显式网格；调用 `local_first`。数据库和适配器审计必须显示零外部请求，响应含对应数据系列、来源快照/修订标识及 `complete` 覆盖。随后写入一条较新的窄字段修订并重试宽字段请求，确认旧的完整修订仍可被选择而不触网。
2. **精确缺口补齐**：删除或隔离一个明确事件，调用相同请求。只允许批准路由收到该缺口的半开窗口；成功后查询 `md_source_snapshots`、`md_observation_revisions`、原始载荷 hash 和来源回执，再重复相同 `local_only` 请求。第二次请求必须零外部调用，且返回保存后的本地事实而非内存中的适配器对象。
3. **拒绝路径**：提供错误标的、错误 provider receipt、越界 event、字段不足、原始载荷 hash 错配或缺少请求频率 grid 的日历。检查没有错误来源回执/观测进入事实表，并且 API 只返回稳定机器码、覆盖状态或 warning，不输出堆栈和凭据。
4. **同进程并发**：让两个等价 `local_first` 请求在同一事件循环同时命中同一缺口。记录 provider 调用数、来源回执数、leader/follower 记录和两个独立数据库 session 的结果。此试验只验收单进程行为，不能替代 E-197-08 的多 worker 验收。
5. **publication 恢复**：在事务 A 提交、事务 B 写入 `published_at` 前停止调用方。对 calendar/identity 等非 source-fenced receipt，可由受控通用恢复程序继续 pending publication；记录事实/receipt 的 ID、hash、A/B 时间、恢复前后的 `local_only` / strict 读取。对带 lease generation 的 source receipt，通用恢复必须保持其 hidden；只有仍未过期的 exact owner/fence 协调路径可完成 B。若 owner 已丢失或到期，记录旧 receipt 仍不可见，并由新 owner 重新获取生成新 receipt。任何恢复后可见的事实都只能在合适 cutoff 可读。

验收人应记录每次试验的 query fingerprint、source snapshot ID、revision ID、执行时间、数据库计数前后变化和网络调用计数。仅保存屏幕截图而不保留这些可关联标识不足以证明回填链路。

### 6.2 全资产与数据类型覆盖清单

用户要求的范围是当前两个页面已经支持的全部数据类型。对下表每一行，必须选择一个经过批准的 representative canonical identity 和时间窗；若首批不具备安全、精确、有界的来源实现，也必须证明其返回明确“不支持/未配置”状态，而不是改查其它标的或静默返回空成功。

| 资产类型 | 目标数据类型 | 本地命中 | 受控缺口补齐 | 不支持/未配置的显式状态 | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| `stock` | `bars`、必要行情/估值字段 | 必做 | 必做 | 必做 | `NOT_RUN` |
| `futures` | `bars`、结算、持仓量 | 必做 | 必做 | 必做 | `NOT_RUN` |
| `bond` | 行情、收益率、参考序列 | 必做 | 必做 | 必做 | `NOT_RUN` |
| `fund` | 净值、ETF 行情、参考序列 | 必做 | 必做 | 必做 | `NOT_RUN` |
| `option` | 合约行情、`option_chain` | 必做 | 必做 | 必做 | `NOT_RUN` |
| `fx` | 汇率 `bars` / 快照 | 必做 | 必做 | 必做 | `NOT_RUN` |
| `crypto` | 交易对 `bars` / 快照 | 必做 | 必做 | 必做 | `NOT_RUN` |

这里的“覆盖”不表示所有类型都必须由 AkShare 成功返回真实数据。验收通过的前提是：每种组合要么有可追溯且通过质量规则的批准来源，要么明确为未配置/不支持；不得因为当前来源能力不足而降低身份、时间、字段、频率、口径或许可证约束。

当前候选有九个 `ready` family：六个 `*.realtime` 的 `market.bars`，以及 `stock.liquidity`、`fund.liquidity` 两个日线 `reference_series` 和 `fx.range` 的完整 OHLC 日线。后面三个只在行情页明确选择、server bundle/contract 精确绑定、来源策略匹配时进入候选代码路径；它们没有扩展策略页的 strict bars/PIT 预检。其它八个 B1 family、快照和 B2 多记录产品仍为 `unconfigured`。本表的“本地命中/受控缺口补齐”仍是正式验收要求，**不是当前真实环境通过声明**；AC-197-021 保持 `BLOCKED` / NO-GO，直到多记录事实模型和完整性规划已实现并完成真实端到端证据。

### 6.3 严格研究与回测专项

对 `purpose=research` 和 `purpose=backtest` 至少各运行一个真实的已批准数据集：

1. 请求必须为 `consistency=strict` 且携带含时区的 `knowledge_cutoff`；回测截止点不得晚于请求结束时间。
2. 在截止点后新增修订或回填主数据版本，再以原截止点重放。重放不得看到新增事实，也不得因在线刷新改变历史结果。
3. 保存已解析 canonical identity、metadata version、冻结 identity projection、数据系列、来源策略、日历版本、查询 fingerprint、知识截止点、source/calendar/identity publication receipt、来源快照和修订 ID 至研究/回测工件。
4. 同一候选数据集进行两次本地重放，输出行、字段哈希和工件指纹应一致；不一致必须按 `FAIL` 处理，不能以“数据源更新”解释。

此专项与迭代 196 的最终工件格式存在依赖，当前为 `BLOCKED`，详见第 9 节。

## 7. 数据库迁移与灾备验收

### 7.1 候选数据库演练

在生产拓扑等价的、可恢复的 MySQL/PostgreSQL 副本上执行：

1. 记录升级前 schema、Alembic revision、遗留 AkShare 表行数及抽样校验和。
2. 在已完成 196/197 合并链的候选版本上执行 `alembic heads`，结果必须只有一个 head；若多 head，状态为 `FAIL`，不可人工任选一条链继续上线。
3. 执行 `alembic upgrade head`，重新审计 `dg_*`、`md_*` 的列、外键、唯一约束、检查约束和索引。任何 MySQL 执行 `20260909_market_data_constraint_name_portability` 时，都必须先停止全部 market-data writer，并在本次命令明确设置 `MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_MAINTENANCE_FENCE=confirmed`；即使当前反射结果看似无需改动也不能跳过，以免检查与 DDL 间发生 TOCTOU。该 revision 的有限等待 `GET_LOCK` 只串行化迁移执行者，不能替代 writer drain。
4. 在每个新建和复用的应用连接记录时区：MySQL 记录 `@@session.time_zone`（应为 UTC 等价值），PostgreSQL 记录 `SHOW TIME ZONE`（应为 `UTC`）。当前候选没有可替代这项检查的自动 session-time-zone 证据；若任何连接不符合，停止验收并先补齐部署/连接初始化合同。
5. 使用带偏移的边界 timestamp（包括交易日和 `knowledge_cutoff` 临界前后）在事务 A 写入来源回执、观测与 pending publication，先从第二个连接重读 `local_only` 与 `strict` 请求，再以事务 B 写入 `published_at` 后重复读取。MySQL 与 PostgreSQL 都必须证明 UTC 归一化、A/B 间的不可见性、发布后的 PIT 可见性和字段选择未因连接时区偏移；SQLite 不可替代。
6. 验证遗留 AkShare 表定义、行数和抽样校验和未被迁移改写；验证新表初始为空或只含受控引导数据。
7. 在新表写入一条受控测试来源回执后，确认降级路径不会静默删除带证据的数据。需要回退时执行已批准的导出/治理过程，而不是强制 `downgrade`。
8. 做一次备份恢复演练，恢复后重复 `local_only` 读取、来源链追溯、时区检查和 schema 审计。

### 7.2 当前状态

| 项目 | 状态 | 阻塞原因/所需证据 |
| --- | --- | --- |
| SQLite 升级/降级与离线方言渲染的自动化契约 | `PASS`（独立候选开发回归） | L-197-04/L-197-05 已覆盖目标测试、单 head 和临时 SQLite `upgrade head`；这不替代 MySQL/PostgreSQL 真实方言与 UTC/PIT 演练。 |
| MySQL 准生产升级、UTC session、PIT 与恢复演练 | `NOT_RUN` | 需要经授权的可恢复数据库副本、每连接 UTC 验证、维护窗口和跨连接证据；任何执行 portability revision 的 MySQL upgrade 均须先 drain writer 并显式设置 `MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_MAINTENANCE_FENCE=confirmed`，MySQL `DATETIME` 时区语义不能靠 SQLite 推定。 |
| PostgreSQL 准生产升级、UTC session、PIT 与恢复演练 | `NOT_RUN` | L-197-10 已在 disposable PostgreSQL 证明 fresh 与 predecessor→head 升级、两个 UTC session、截断 CHECK 名修复和清理；仍需要经授权的可恢复副本、PIT A/B publication、exact-identity 真实列审计与恢复演练。 |
| 多进程 calendar import lock 与 observation/source writer 并发 | `NOT_RUN` | L-197-10 已以真实 PostgreSQL 的两个 OS 进程、确定性 provider 和 durable lease 验证一个精确缺口仅一次调用及 follower 本地重读；calendar lock 的跨连接行为、真实 provider、故障接管和连续分段导入仍需真实方言演练。 |
| 196/197 Alembic 单 head 合并 | `PASS`（本地隔离 SQLite） | `20260909_ai_research_market_data_merge` 后唯一 head 为 `20260909_market_data_research_binding_consumers`；L-197-12 已完成 empty SQLite `upgrade head` 和 binding receipt 表审计。MySQL/PostgreSQL 仍为 `NOT_RUN`。 |

## 8. 真实提供方验收

### 8.1 AkShare 受控实时验证

仅在数据许可、访问条款和网络访问已获确认的环境执行。每次调用使用小窗口、最小字段集和非敏感公开标的，遵守上游限频：

1. 为每个实际启用路由选择精确 canonical identity，验证请求符号、市场、函数路由、复权、价格口径、币种、单位与来源策略完全一致。
2. 验证 AkShare 若使用含结束日的接口，适配器仍只保存 `[start, end)` 内事件；请求窗口外的记录不能写入。
3. 验证返回标的与请求身份不一致时，适配器拒绝结果且本地不写入来源回执。
4. 验证超时、并发槽耗尽、超大响应和不支持的资产/数据类型产生稳定码，不绕过限制调用另一函数或返回样例。
5. 成功案例必须保留匿名化的请求语义、`provider_id`、source revision、source snapshot ID、行数、字段哈希和后续 `local_only` 复读证据；不得记录账户凭据或完整未授权原始载荷。

当前状态：`FAIL`（已执行的 `stock.liquidity` 子用例）。离线 AkShare 假函数测试只能证明代码契约，不能证明实时服务或许可。2026-09-09 的受限 `stock_zh_a_hist("600000")` 小窗口探测返回一个 `ProviderFetchResult`，但安全计数为 `response_row_count=0`、`normalized_observation_count=0`：临时库内有 1 条 persisted fetch/receipt，却没有 observation revision、完整覆盖或后续 `local_only` 复读；临时数据库随后已删除，未保留可复核的 snapshot/revision ID。此前 `forex_hist_em("USDCNH")` 的受限探测只是无成功链的历史线索，未附本候选命令、版本和输出，故不改变该 route 的正式 `NOT_RUN`。这些记录不能用来宣称三个 B1 family 的真实来源通过；除 `stock.liquidity` 的失败子用例外，其它实际启用 AkShare 路线仍为 `NOT_RUN`。

### 8.2 OpenBB 隔离运行器验证

仅在单独的、可销毁的 OpenBB 运行环境执行；FastAPI/主应用进程不得安装或导入未经审核的 OpenBB 扩展以满足测试。

当前静态 permit matrix 为**空**，`MARKET_DATA_OPENBB_ALLOWED_MARKETS` 不会生成 route、legacy contract 或 provider fallback。fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` 的 `openbb-yfinance 1.6.3.post1` 仅是待封装构件候选：它把 daily route 的 OpenBB 包含式 `end_date` 转为 yfinance 的排他 `end=end_date + 1 UTC calendar day`，并使用 `period=None`。候选只定义 `1d`、UTC 日对齐、最长 3650 天的父半开窗口；它不批准 `1w`、`1mo`、分钟、非日对齐或超长窗口。构件清单的版本/包内哈希检查只能证明期望构件一致性，不能证明可导入、可联网、可使用或获许可。

在完整隔离动态扩展导入闭包、不可变运行镜像、AGPL-3.0-only 许可证书面审查和最小出网审计完成前，任何正常 OpenBB 请求必须在**动态扩展导入前**拒绝。本轮不得执行真实 OpenBB/yfinance 网络调用或把 `--self-check` 称为来源验收；只可运行无网络自检，其输出不得含密钥、环境变量值、绝对包路径或文件哈希。当前构件清单的 `candidate` 状态、未封装环境或与清单不匹配环境都应返回 `OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED`；不得把清单数据改写为启用状态，未来必须由新的执行认证代码和独立验收解除该拒绝。该机器码不能被解释为已安装或已通过运行审计。

解除该阻断必须在独立变更中同时完成并留下可复核证据：

1. 固定隔离镜像（digest）和完整动态 OpenBB 扩展/传递依赖导入闭包；证明主应用进程没有导入这些扩展。候选 fork commit、`openbb-yfinance 1.6.3.post1`、所有被验证发行版和包内文件哈希必须与该镜像逐项一致。
2. 完成 AGPL-3.0-only 许可证书面审查，覆盖 fork、镜像分发、服务部署、源代码提供义务、动态扩展闭包和与本项目组合方式；同时完成所有上游数据访问、再分发和商用许可审查。
3. 设置经运维审核的 `OPENBB_MARKET_DATA_RUNNER`、恰为 `yfinance` 的 `OPENBB_ALLOWED_PROVIDERS`、独立绝对存在的 runner `HOME` 与 `OPENBB_RUNNER_WORKDIR`。记录实际 `cwd`、镜像 digest、允许 provider、挂载和启动命令哈希，但不记录密钥；任何 HOME/workdir 临时回退、主应用工作树、主应用 HOME 或秘密挂载均失败关闭。
4. 审计 service account/container 的 UID、文件挂载、环境变量、网络策略和出网目的地/端口/限流。它不得读取主应用数据库凭据、项目工作树、应用 `.env`、数据库 volume/socket 或其它应用密钥；环境白名单、受控 cwd 或静态构件哈希不能替代该审计。
5. 逐项验证协议版本、request ID、请求 DTO、输出大小、超时、非零退出、无效 JSON、错配 ID、重复事件和越界事件均按稳定码失败关闭；再验证缺失原始 records 封套、hash 格式错误和父进程复算 hash 不一致也不落库。
6. 在隔离镜像内对一个受批准、精确的小窗口验证：只有 `1d`、UTC 日对齐且不超过 3650 天可到达 daily helper；捕获或可审计地证明 helper 以 `period=None` 向 yfinance 传入排他 `end`，该 `end` 恰为 OpenBB 包含式结束日的下一 UTC 日。之后验证返回 records 被裁剪回父 `[start,end)`。
7. 以一个成功的小窗口完成“网络获取 → `md_source_snapshots`/`md_observation_revisions` 持久化 → `local_only` 复读”，并证明 API 返回的是本地修订 ID、来源回执和经父进程验证的原始载荷 hash。该步骤必须使用独立清理后的验收库，且不记录未经授权原始载荷。
8. 仅在上述前置条件全部通过后，以独立变更逐轴添加一个精确 permit。static permit、source-policy route、provider DTO 和 runner mirror 的 route ID、family、provider、asset、market、kind、frequency、四个语义轴及 endpoint 必须逐项相同；故意替换 sibling family 或 endpoint 必须在导入 OpenBB 前拒绝，runner 仅按 `(asset_type, endpoint)` 的静态映射调用。

当前状态：`BLOCKED` / `NO-GO`。本次记录只确认了 fork 候选及其日终转换意图，没有安装、镜像、动态导入、许可证、出网或真实网络证据。permit matrix 仍为空，因此没有可执行的 OpenBB route，也没有 OpenBB 持久化或 `local_only` 回读的成功证据。临时 fake runner、离线 fork 参数测试和 `--self-check` 不等同于本机 OpenBB、`openbb-docs`、`agents-for-openbb` checkout 或 GitHub 社区仓库中的任一扩展已安装、可用、获授权或可安全部署。


## 9. 迭代 196 整合闸门

迭代 196 已冻结并作为本候选的基线。迁移图以 `20260909_ai_research_market_data_merge` 显式合并 196 研究审批 head 和 197 数据中台 head，随后依次追加 `20260909_market_data_research_bindings` 与 `20260909_market_data_research_binding_consumers`。本地 `alembic heads` 已证明唯一 head；它不能替代可恢复 MySQL/PostgreSQL 副本或真实页面环境。

| 整合闸门 | 通过条件 | 当前状态 |
| --- | --- | --- |
| IG-196-01：接口冻结 | 196 的研究、策略、回测输入输出与数据工件 schema 已冻结，并有冻结收据。 | `PASS`（集成基线） |
| IG-196-02：迁移单头 | 196 与 197 的 Alembic 链已合并，`alembic heads` 恰一个 head，隔离升级演练通过。 | `PASS`（L-197-12；MySQL/PostgreSQL 仍 `NOT_RUN`） |
| IG-196-03：工件绑定 | AI 研究的 strict local artifact 含 canonical identity、metadata version、数据系列、来源策略、PIT、revision/source snapshot、manifest/CSV hash，且绑定到 exact workspace/unit/intent。 | `PASS`（本地安全回归；真实数据仍 `NOT_RUN`） |
| IG-196-04：页面灰度 | `/data/market` 在功能开关下使用 v2，`/investment/strategies` 在严格工件链可用后消费 v2；两个页面均无旧样例/模糊回退。 | `NOT_RUN` |
| IG-196-05：端到端回归 | 相同用户权限、相同请求在灰度前后均可解释；开关关闭可回到受支持的旧接口，不删除 197 的证据事实。 | `NOT_RUN` |

页面和在线读取开关保持关闭，直到 IG-196-04/05 具备前端 build、浏览器用例、API trace、数据库回执与冻结 196 工件的一致性证据。不能通过 `stamp`、忽略 head 或历史独立工作树记录代替该验证。

## 10. 上线/灰度验收与回退

### 10.1 建议顺序

1. 冻结 196、创建含 merge/rebase 的 196/197 候选后，先记录候选 SHA、`git status --short`、数据库备份标识，并在空库执行：

   ```bash
   cd src/backend
   alembic heads
   alembic upgrade head
   ```

   `alembic heads` 不是“至少包含一个 head”的检查，输出必须恰有一个。随后在可恢复 MySQL/PostgreSQL 副本重复，并完成第 7 节的每连接 UTC 与 PIT 演练。

2. 迁移已通过后，先运行所有导入器的 rollback dry-run，审阅 JSON 输出，再在同一候选和维护窗口执行 `--apply`。示例操作顺序如下，`<...>` 必须替换为经审核的本地 manifest 路径：

   ```bash
   cd src/backend
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/bootstrap_market_data_platform.py
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/bootstrap_market_data_platform.py --apply
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/import_market_data_master_data.py <master-data.json>
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/import_market_data_master_data.py --apply <master-data.json>
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/backfill_market_data_lookup_keys.py --batch-size 500 --max-batches 1
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/backfill_market_data_lookup_keys.py --apply --batch-size 500 --max-batches 1
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/import_market_data_calendar.py <calendar-grid.json>
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/import_market_data_calendar.py --apply <calendar-grid.json>
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/recover_market_data_publications.py --limit 100
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/recover_market_data_publications.py --apply --limit 100
   ```

   对 lookup-key 回填按返回游标重复受限批次，直到处理结果为零；先审阅 pending publication 恢复 dry-run 的 JSON 摘要，再执行 `--apply`，并保留恢复前后本地读取证据。该通用恢复脚本只允许处理 calendar、identity 等非 source-fenced pending receipt；它必须跳过任何带 lease generation 的 source receipt。每个已启用 `(market, data_kind, frequency)` 都需单独审核、导入和记录 calendar grid。不得使用脚本或页面代码自行创建缺失 identity、频率事件或来源许可。

3. 保持 `MARKET_DATA_QUERY_V2_ENABLED=false` 和 `MARKET_DATA_ONLINE_FETCH_ENABLED=false`，仅用 `local_only` 验证导入后的 identity、字段可用修订、日历网格、PIT 和来源链。单进程 concurrent case 可作为开发回归；若要在 E-197-08 仍为 `NOT_RUN` 时灰度 v2，部署范围必须显式限制为单一 Web worker，并记录该限制和回退动作。
4. 完成第 8 节某一已许可来源的真实回填、原始载荷 hash 和 OpenBB service-account/container 审计后，才针对该来源策略和小范围 identity 开启 `local_first`。OpenBB 还必须先完成完整动态扩展导入闭包、不可变镜像、AGPL-3.0-only 许可证及出网审计，并在独立变更中添加精确 permit；fork 构件候选或自检不允许绕过这些步骤。
5. 196 整合闸门全部通过后，灰度迁移 `/data/market`，再迁移 `/investment/strategies` 的严格研究/回测消费。

### 10.2 运行时拒绝条件

以下任一情况须停止扩大灰度，并将相关策略或页面切回关闭状态：

- 返回了 canonical identity 不同、时间窗越界、字段/口径不符或无来源回执的数据；
- `complete` 覆盖由未知/不充分日历得出；
- 严格查询读取到 cutoff 后新增的身份或观测修订；
- 发生 provider receipt 错配、来源策略绕过、OpenBB 协议/构件认证错配、未批准动态扩展导入、未审计出网或泄漏原始异常；
- 缺少请求频率的日历 grid，却返回 `complete`，或新窄字段修订使已缓存的完整字段重新触网；
- 在多 worker 环境将同进程 singleflight 作为零重复网络请求的证明；
- Alembic 多 head、迁移修改遗留 AkShare 事实、或恢复演练失败；
- 196 工件未带完整数据谱系，策略页却将结果标为可回测。

### 10.3 回退原则

关闭 `MARKET_DATA_QUERY_V2_ENABLED` 和 `MARKET_DATA_ONLINE_FETCH_ENABLED` 是首选的可逆回退动作。不得为了回退静默删除 `md_source_snapshots`、`md_observation_revisions` 或日历证据；需要迁移回退时按第 7 节的导出、备份和治理程序操作。关闭在线获取不应破坏已持久化本地数据的 `local_only` 可读性。

## 11. 最终签收清单

只有下列全部满足，迭代 197 才能从“实现完成”提升为“可上线验收通过”：

- [ ] 候选提交无未解释的工作树改动，且第 4 节全量 `pytest` 为 `PASS`。
- [ ] 静态检查为 `PASS`，或有经过批准、可追踪的例外。
- [ ] 所有 AC-197-001 至 AC-197-024 均有对应证据；开发回归、候选验收和真实验证的边界清楚可查。
- [ ] 七类资产和当前页面已支持数据类型都有经过验证的本地命中/受控补齐，或稳定的明确不支持/未配置状态。
- [ ] 真实 AkShare/OpenBB 验证、数据许可、来源策略登记、OpenBB 原始载荷 hash、完整动态扩展导入闭包、不可变镜像、AGPL-3.0-only 许可证与独立 service account/container/出网审计完成，或未启用对应在线路由。
- [ ] 每个已启用频率都有审核后的显式 calendar grid、连续 calendar segment 和导入锁证据；MySQL/PostgreSQL 候选迁移、每连接 UTC/PIT A/B publication 与恢复演练、`utf8mb4_bin`/`C` 精确身份列审计和单 head 检查完成。
- [ ] 实际部署已二选一：要么限制 v2 市场数据请求到一个经验证的 Web worker 并记录容量/回退边界，要么已完成多 worker/多进程的数据库 lease、接管和并发调用计数验收；不得把同进程 singleflight 表述为全局去重。
- [ ] IG-196-01 至 IG-196-05 均具备对应证据，并完成页面端到端灰度证据。
- [ ] AO-09 已使用经审查的 `iter196-market-data-baseline-v1` 冻结基线生成并验证范围清单；清单仍仅作为集成输入，不能单独开启策略页生产读取。
- [ ] 开关、告警、审计指标和回退程序经过演练；无凭据或敏感原始载荷进入测试输出、日志或文档。

在上述任一项未满足时，最终签收状态为 **`NOT_ACCEPTED`**；可继续保留为独立工作树中的实现/验证候选，但不得表述为生产可用的数据中台。
