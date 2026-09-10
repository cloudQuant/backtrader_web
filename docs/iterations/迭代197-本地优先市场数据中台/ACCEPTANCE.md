# 迭代 197 验收文档：本地优先市场数据中台

> 文档状态：196/197 当前 `dev` 候选；历史本地回归与本轮开发回归均已记录（2026-09-10）
> 适用工作树：当前 `dev`；文中较早候选 SHA、分支名与测试计数均为历史快照
> 当前结论：**尚未达到发布验收条件。** 迭代 196 已冻结并接入 `dev`；本地自动化只记录当前候选的开发回归，真实环境和页面灰度证据仍须独立记录。没有命令输出、数据库快照或外部回执的项目不得标记为 `PASS`。本次 OpenBB yfinance fork 记录是文档与离线构件候选更新：没有安装扩展、构建镜像、创建 permit/route、发起真实 OpenBB/yfinance 网络调用或写入市场数据。

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
| AO-10 | B1 单记录产品的逻辑目录、精确 family contract、来源路由与控制面选择 | `bootstrap.py`、`dataset_contracts.py`、`legacy_contract.py`、`akshare_provider.py`、`queries.py`、`test_dataset_contracts.py`、`test_akshare_provider.py`、`test_query_service.py`、`DataPage.test.ts`；`stock.liquidity`、`fund.liquidity`、`fund.nav`、`fx.range` 为候选代码开通。`fund.nav` 仅限 CN ETF `LISTING`，且 frozen identity 同时为 `product_type=ETF` 与 `fund_identity_kind=LISTING`；policy、compatibility bridge 和 adapter 均在 I/O 前拒绝不匹配身份。其语义固定为 `source_reported + nav + CNY + fund_share`，其余七个 B1 family 仍不提供事实读取 |
| AO-11 | 严格研究数据绑定、服务器侧 consumer scope、当前授权重放、撤销、trusted runtime 路径和文件读取完整性 | `md_research_data_bindings`、`md_research_data_binding_scopes`、`md_research_data_binding_consumers`、`md_research_data_binding_revocations`、`research_binding.py`、`workspace_unit_runtime.py`、`backtest/service.py`、`backtest_enhanced.py`、`test_research_binding.py`、`test_strategy_runtime_support.py`、`test_backtest_service.py` |

| AO-12 | 默认关闭的 CFFEX 日结内部批采集候选、全量回执验证、授权/lease 绑定与部分发布报告 | `cffex_settlement_collector.py`、`collect_iteration197_cffex_settlement.py`、`test_cffex_settlement_collector.py`；不注册公开 `futures.settlement` route |
| AO-13 | 默认关闭的私有 A 股估值 capture snapshot 候选 | `market.stock_valuation_captured_snapshot / valuation_snapshot / snapshot`、`stock_valuation_collector.py`、`test_stock_valuation_collector.py`；固定 AkShare capture envelope、递归冻结、精确 capture instant、unknown quarantine、2 MiB/10 MiB/16-target 写前限制、一份 canonical UTF-8 shared payload、target receipt hash 重建和部分发布。公开 `stock.valuation` route 仍未注册。本地聚焦回归为 `PASS`，真实环境验收仍未运行。 |

### 2.2 不可由本次离线自动化证明的事项

- 实际 AkShare、OpenBB 扩展及各上游数据源在某日可用、返回的数据质量、频率限制、账户权限或商业许可。
- MySQL/PostgreSQL 生产或准生产库的真实 Alembic 升级、回滚治理和性能表现。
- `/data/market` 与 `/investment/strategies` 的真实浏览器行为、真实用户权限、数据初始化完成后的页面展示。
- MySQL/PostgreSQL 与真实页面环境中的 196/197 工件链行为；本地单头迁移和绑定测试不能替代这些环境证据。
- `md_fetch_leases` 的代码级 owner/fence/expiry 协议在候选中已实现，但 SQLite/替身回归不能证明真实多 Web worker、多个进程/pod、数据库时钟、故障接管或零重复 provider 调用。
- 日历导入锁只串行化同一 `calendar_code` 的 calendar manifest 导入；它不是 observation/source snapshot 的多进程 writer lease，也不能证明并发写入的 ownership、fencing、接管或零重复网络调用。
- OpenBB 运行器在独立 service account/container 中的文件系统、挂载和凭据隔离；环境变量白名单与受控 `cwd` 不能证明该边界。
- fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` / `openbb-yfinance 1.6.3.post1` 的完整动态扩展导入闭包、不可变镜像、AGPL-3.0-only 许可证审查和最小出网审计；静态构件清单或离线 fork 测试都不能证明这些事项。
- CFFEX 的经 HTTPS/证书验证来源、transport evidence、来源许可/限流、审批 scheduler 身份、真实 calendar/identity/source registry、跨合约部分发布/取消后的生产对账与 MySQL/PostgreSQL 恢复。当前 AkShare HTTP route 已硬禁用；默认 CLI 与离线 source seam 都不构成这些证据。
- 私有 A 股估值 capture snapshot 候选的真实上游调用、scheduler 身份、访问条款、冻结 identity 导入、日线 calendar coverage、真实 raw receipt、跨数据库部分发布恢复和页面/策略验证。离线 fixture 已验证 shared receipt 的本地存储与重建边界，但不能将公开 `stock.valuation` family 从 `NOT_CONFIGURED` 升级。

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
6. 线上开关默认保持关闭：`MARKET_DATA_QUERY_V2_ENABLED=false`、`MARKET_DATA_ONLINE_FETCH_ENABLED=false`、`MARKET_DATA_RESEARCH_CACHE_FILL_ENABLED=false` 和 `MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_ENABLED=false`。参与灰度的已授权用户必须从 `GET /api/v1/data/market-data/capabilities` 读到相同的有效状态；浏览器 VITE 变量不得启用、关闭或遮蔽 bundle、v2、bridge 或 cache-fill。`research_cache_fill` 还要求有效能力 `query_v2_enabled && online_fetch_enabled && research_cache_fill_enabled`、当前研究用途授权和本节其它 v2 前置条件。若开启 v2，运维管理的 `MARKET_DATA_CURSOR_SIGNING_KEY` 必须存在且至少 32 bytes；不得记录其值。只有完成本文件相应闸门后才可按灰度计划开启。
7. 若需启用 OpenBB，`OPENBB_MARKET_DATA_RUNNER`、恰为 `yfinance` 的 `OPENBB_ALLOWED_PROVIDERS`、独立且绝对存在的 `OPENBB_RUNNER_HOME` 与 `OPENBB_RUNNER_WORKDIR` 已由 runner 运维方审核；后二者不可缺失、回退为临时目录/主应用 HOME/工作树，主应用进程也不能把自身的数据库凭据、项目工作树或服务账户权限作为 runner 前置条件。当前 permit matrix 为空。fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` / `openbb-yfinance 1.6.3.post1` 仅是 `1d`、UTC 日对齐、最长 3650 天、包含式 OpenBB 日终到排他 yfinance `end` 的构件候选；在完整隔离导入闭包、不可变镜像、AGPL-3.0-only 许可证和最小出网审计完成前，正常请求必须在动态扩展导入前拒绝，不能用这些配置启用 route。
8. 启用 `MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_ENABLED` 前，必须有独立签名 key、受控 artifact root、当前 `data:read` 和 source registry/backtest 许可。通用 workspace create/batch API 不得接受 `market_data_asset_type`、精确 `market_data_binding` 或任何 `market_data_binding_*` 字段；仅 AI 研究编排可在 unit 创建后写入服务器侧 consumer receipt。公共 `/api/v1/backtests/run` 与通用 `BacktestService.run_backtest` 不得接受客户端 `runtime_dir`；workspace unit 只能通过 server-only preflight 执行。

## 4. 必须执行的自动化回归

在 `src/backend/` 下执行。下述命令是候选版本的最小自动化门槛；可按故障定位拆分运行，但最终须至少有一次全量命令通过。

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q \
  tests/market_data_platform tests/test_config.py
```

同一冻结候选还必须执行 capability、cache-fill 与策略 bridge guard 回归；它补足上面的中台 suite，不能被历史计数替代：

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q \
  tests/market_data_platform/test_query_api.py
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q \
  tests/test_ai_strategy_research_service.py \
  -k 'task_manager_rejects_disabled_market_data_bridge_before_snapshot_or_dispatch or direct_research_service_rejects_market_data_markers_when_bridge_disabled or direct_research_service_treats_bridge_as_disabled_when_v2_is_off or ai_research_apis_report_disabled_bridge_before_sync_or_async_work or run_continuation_rebinds_old_record_binding_before_snapshot or run_continuation_rejects_old_record_binding_when_bridge_disabled or task_snapshot_continuation'
```

同一候选还必须执行以下目标静态检查：

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check \
  app/api/data/queries.py app/api/strategy/base.py \
  app/schemas/market_data_platform.py \
  app/services/ai_strategy_research_service.py \
  app/services/ai_strategy_research_task_manager.py \
  app/services/research/continuation.py \
  tests/market_data_platform/test_query_api.py \
  tests/test_ai_strategy_research_service.py
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
| E-197-04 | 真实 AkShare 受控探测 | 实时路由及四个 B1 候选路由的字段、时间窗、回执和写回 | `FAIL`（已执行 `stock.liquidity`；`fund.liquidity`、`fund.nav`、`fx.range` 等其它真实 AkShare 路线仍为 `NOT_RUN`） | 第 8.1 节的匿名化请求/响应摘要、来源回执和本地复读证据。 |
| E-197-05 | 真实 OpenBB 隔离运行器探测 | runner 环境、协议、上游许可与写回 | `BLOCKED` | 第 8.2 节的隔离进程、镜像/动态导入闭包、许可证/出网审计、协议日志摘要、原始载荷 hash、回执和本地复读证据；当前 permit matrix 为空。fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` / `openbb-yfinance 1.6.3.post1` 只是 `1d` daily end-bound 构件候选，正常请求在动态扩展导入前拒绝，不能记为成功验证。 |
| E-197-06 | `/data/market`、`/investment/strategies` 端到端回归 | 页面灰度、授权、回退防护、196 工件绑定 | `NOT_RUN` | 保存浏览器/API/数据库三方一致证据；196 冻结和桥接不等于浏览器或真实数据通过。 |
| E-197-07 | MySQL/PostgreSQL UTC session、PIT 与 exact-identity collation 演练 | 时区、跨连接写入/读取、迁移、恢复及 `RB0`/`rb0` 精确身份 | `NOT_RUN` | 每个新连接的会话时区输出、边界时间写入/读取、迁移和恢复记录，以及 authority/projection/lookup 的 MySQL `utf8mb4_bin`、PostgreSQL `C` 实际列审计和 case-distinct lookup 回归。 |
| E-197-08 | 多 worker/多进程同缺口及事实写入并发 | 跨进程 writer lease/fencing、故障接管和零重复外部访问 | `NOT_RUN` | L-197-10 已在 disposable PostgreSQL 以两个 OS 进程和确定性 provider 证明一个精确缺口只有一次调用，且 follower 从本地重读；仍需真实 AkShare/OpenBB、应用 HTTP worker、故障接管与崩溃恢复证据。普通 AkShare provider 的同步 thread timeout 不能杀死底层调用，故超时后的零重复 I/O 为 `NO-GO`，直至可终止 runner 或租约 heartbeat 设计通过验收；CFFEX HTTP source 当前已硬禁用。calendar import lock 不适用于 observation 写入。 |
| E-197-09 | OpenBB 操作系统级隔离 | service account/container、挂载、凭据与工作目录 | `NOT_RUN` | runner 账户/容器配置、挂载清单、权限审计和一次实际小窗口回填。 |
| E-197-10 | 策略页 `research_cache_fill` 灰度 | 显式用户动作、后端写入开关、研究用途授权、receipt 与 196 工件隔离 | `NOT_RUN` | 前端显式预检、后端开关与已批准研究用途 source registry、浏览器/API/数据库三方证据。 |
| E-197-11 | 严格 research binding 安全回归 | AO-11：scope/consumer、fresh-snapshot 授权重放、撤销、trusted runtime、运行时文件读取 | `NOT_RUN`（正式候选） | 绑定、复制 token、撤销 `data:read`、来源拒绝、证据漂移、撤销 receipt、workspace 改为 trading、排队重试/子进程前撤销、客户端 `runtime_dir`、路径替换/符号链接的回归均通过；不得以此替代真实 provider 或浏览器运行。 |
| E-197-12 | CFFEX 日结内部采集候选 | AO-12：默认不联网 CLI、明文 transport 硬拒绝、语义/当前 registry 预检查、全批验证、部分发布与取消边界 | `NOT_RUN`（正式候选） | 在已批准 scheduler、真实 CFFEX identity/calendar/source registry、HTTPS/certificate transport evidence 和可恢复验收库上保留匿名化 source receipt、lease、每 target publication、quarantine、部分发布对账和 `local_only` 复读证据。 |
| E-197-13 | capability、显式 cache-fill 与策略 bridge guard 增量 | 服务端 effective capability、v2/cache 错误码、bridge 关闭的同步/异步持久化前拒绝、同一提交 symbol 快照的前端 marker | `NOT_RUN`（本次完成候选） | 本节新增后端命令、三份前端 v2 回归、目标 Ruff 输出和冻结候选 SHA；缓存补齐 bridge=false 的正例只证明缓存/本地复读，不构成回测工件或浏览器 E2E。 |
| E-197-14 | 统一矩阵验收运行器 | 离线 socket guard、JUnit、dirty candidate allowlist、scope/Alembic 预检、G1/G2/G3 分片和 live source-manifest/批准闸门 | `PARTIAL`：`AC-01:fund:G1` slice 为 `PASS`，但进程状态为 `NOT_RUN`（G2 pending）；`AC-15:fund:G3` 按批准闸门为 `BLOCKED` | 运行器结果必须保留 schema、case/asset/gate、test case、network audit、scope hash 和剩余 gates；一个 G1 slice 不能升级整个正式 case 或给进程返回成功。 |
| E-197-15 | large-file ratchet | 变更前的代码体积与既有 baseline 对照 | `BLOCKED / NO-GO` | 当前命令退出码 1，发现 38 项超限；在闸门恢复通过或维护者调整并审核 baseline 前，不得把本候选作为发布签收。 |
| E-197-16 | 私有 A 股估值 capture snapshot 候选 | 固定 batch envelope/hash、零 fetch/HTTP、冻结 identity、精确 `collector_observed` capture instant（`source_event_time/source_as_of=null`）、unknown quarantine、递归冻结、2 MiB source / 10 MiB 完整 receipt / 16 target 写前边界、同源批次一份 canonical UTF-8 BLOB、target manifest 重建 hash、部分发布与 Store 复读 | `PASS`（本地开发回归）：2026-09-10 在 SQLite fixture 执行专属 collector、snapshot importer、AkShare route isolation、bootstrap 与 dataset-contract tests，`139 passed, 1 warning`；正式候选、真实来源、daily calendar、MySQL/PostgreSQL、浏览器与策略验收仍 `NOT_RUN`。 |


`E-197-01`、`E-197-02`、`E-197-03` 与 `E-197-11` 的状态仅表示正式候选；本地工作树回归单列于下节。`E-197-04` 已有一次真实子用例失败，不能以其它离线通过记录覆盖为 `NOT_RUN` 或 `PASS`。`E-197-14` 的局部 G1 通过只证明离线 test slice；`E-197-15` 的失败阻断发布签收，但不改变用户已授权的候选提交与 `dev` 合并。任何本地命令退出码、冻结收据和已合并的 Alembic 图均不能升级为真实环境或发布签收。

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
| L-197-14 | 2026-09-09，独立持续候选工作树：CFFEX 定向回归、OpenBB/Store/compatibility 焦点回归、完整 `pytest -q tests/market_data_platform tests/test_config.py`、目标 Ruff/`py_compile`/`git diff --check`、`alembic heads`、OpenBB `--self-check`、CFFEX 默认和 `--live` CLI，以及新建 backend wheel 内容审计。 | `PASS`（仅本地回归与默认拒绝）：CFFEX 36 passed、焦点 195 passed/1 warning（51.27s）、完整 612 passed/88 warnings（183.01s）；Ruff、`py_compile`、diff 检查通过，唯一 head 为 `20260909_market_data_research_binding_consumers`。OpenBB 自检稳定为 `blocked`、空 permit matrix 和 `OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED`；CFFEX 默认 CLI 返回 `NOT_RUN`，`--live` 返回 `BLOCKED`，均声明 `network_called=false`、`database_written=false`。新 wheel 包含 CFFEX collector 与两份 OpenBB runtime manifest。 | 这证明当前提交前候选的离线拒绝、取消/lease durable-prefix 契约和打包内容可复核，不证明真实 OpenBB/CFFEX 传输、证书链、scheduler、生产数据库、跨进程恢复、浏览器或部署可用；相应正式项保持 `NOT_RUN` / `NO-GO`。 |
| L-197-15 | 2026-09-10，待提交且静止的 completion candidate：`pytest -q tests/market_data_platform -p no:cacheprovider --tb=short`、完整 `test_ai_strategy_research_service.py`、工作区/运行时管理器/策略 API/Direction A 套件、目标前端四文件、typecheck、build、Ruff 与 `git diff --check`。 | `PASS`（仅本地）：市场数据平台 616 passed/88 warnings；研究服务 210 passed/21 warnings；工作区、运行时管理器、策略 API、Direction A 合计 259 passed/1 warning；前端 230 passed、typecheck/build 退出码 0；Ruff 与 diff 检查通过。研究 fake 在首次物化前复用生产 `data_config` 归一化，消除了缺省 `end_date` 跨秒造成的测试摘要漂移。 | 这是冻结提交前的独立本地回归，不替代第 4 节要求的全量组合命令、真实 AkShare/OpenBB、MySQL/PostgreSQL、浏览器 E2E 或生产部署验收；外部项继续保持 `NOT_RUN` / `BLOCKED` / `NO-GO`。 |
| L-197-16 | 2026-09-10，较早的 `dev` 候选：8 个市场数据焦点文件执行 `pytest -q ... -p no:cacheprovider --tb=short`，验收运行器测试，scope manifest 重新生成/验证，以及最终代码下 socket-guarded `AC-01:fund:G1`。 | `PARTIAL`（局部离线）：市场数据焦点 249 passed/7 warnings（67.86s）；运行器 21 passed/9 warnings（5.61s）；scope hash 为 `24f142337cf01f59e14afeb4401d97c0f2f45c750aedc1c3daa953681b94ec29`。`AC-01:fund:G1` 的 2 条测试均通过、0 failures/errors/skips、`network_attempt_count=0`，其 `mode_slice_status=PASS`；但因 G2 pending，CLI 返回 exit 3 / `NOT_RUN`，result SHA-256 为 `cd79277d6ca8e292c24c54a9230f426a28409e96fe0a1409f7e309d786fa4463`。 | 仅证明当时的离线 fixture、ETF NAV identity guard 和 runner 防出网边界。该 case 的 G2 尚未运行，整体 case 仍为 `NOT_RUN`；不能推断真实 AkShare、OpenBB、数据库或浏览器验收。 |
| L-197-17 | 2026-09-10，最终代码下 `scripts/acceptance/iteration197_data_platform.py --mode live --case AC-15 --asset-type fund`，未提供 external approval 或受审核 source manifest。 | `BLOCKED`（预期）：CLI result SHA-256 为 `e9d2a4f2a48d111e539e20357694f86ff302ed6f8d533791a8eb582bd4a23735`，返回 `ACCEPTANCE_EXTERNAL_APPROVAL_REQUIRED`；没有执行外部 command 或网络调用。 | 这是 live gate 的 fail-closed 证据，不能被理解为 `fund.nav` 的真实 provider 验收。 |
| L-197-18 | 2026-09-10，`/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python scripts/ci/large_file_ratchet.py`。 | `BLOCKED / NO-GO`：退出码 1，发现 38 项超限；包括当前 `useDataPage.ts` 为 3,672 行，而 baseline 为 2,024 行。 | 这是全仓 CI 候选质量闸门，未在本次重写 baseline；修复/拆分或经维护者审核的 baseline 更新前，不得给出发布签收。 |
| L-197-19 | 2026-09-10，较早 `dev` 候选的完整 `pytest -q tests/market_data_platform tests/test_config.py -p no:cacheprovider --tb=short`、运行器测试/目标 Ruff，以及行情页两份前端测试、typecheck、build、lint。 | `PASS`（本地）：后端 646 passed/88 warnings（184.39s）；运行器 21 passed/9 warnings（5.61s）且目标 Ruff 通过；前端 71 passed、typecheck/build 退出码 0、lint 0 errors/1,357 warnings。 | 覆盖本轮 ETF NAV identity restriction、coverage 状态文案、scope/runner 与前端绑定的本地回归；runner 的完整 case exit 和 G2/G3/G4 gate map 均已被回归为 fail-closed。此记录不消除 L-197-18 的质量 NO-GO，也不替代真实 provider、浏览器、数据库或生产验收。 |

| L-197-20 | 2026-09-10，较早私有估值 capture snapshot 候选：`pytest -q tests/market_data_platform/test_stock_valuation_collector.py tests/market_data_platform/test_snapshot_importer.py tests/market_data_platform/test_akshare_provider.py tests/market_data_platform/test_bootstrap.py tests/market_data_platform/test_dataset_contracts.py -p no:cacheprovider --tb=short`；随后完整 `pytest -q tests/market_data_platform tests/test_config.py -p no:cacheprovider --tb=short`；目标 Ruff；scope manifest 重新生成并验证。 | `PASS`（本地）：聚焦 139 passed/1 warning（33.12s）；完整中台/配置 669 passed/88 warnings（199.06s）；目标 Ruff 通过；manifest SHA-256 为 `d1dd587a1d199c2b155789d1c24d53eb3c0e320165b62daf5c57fc55d3544cd1` 并返回 `SCOPE_MANIFEST_VALID`。 | 这是 shared payload/ref 增量前的 collector 证据，只证明私有数据集、capture envelope、时间语义、quarantine、递归冻结、写前预算和当时中台离线契约；不覆盖后续 shared BLOB 重建或其迁移。没有真实 AkShare/OpenBB、scheduler、MySQL/PostgreSQL、浏览器或发布验收；L-197-18 的质量 `NO-GO` 保持。 |
| L-197-21 | 2026-09-10，当前未提交 shared-payload 候选：`pytest -q tests/market_data_platform/test_store.py tests/market_data_platform/test_stock_valuation_collector.py tests/market_data_platform/test_storage_models.py tests/test_config.py -p no:cacheprovider --tb=short`；随后完整 `pytest -q tests/market_data_platform tests/test_config.py -p no:cacheprovider --tb=short`、四个研究/资产迁移文件及 `test_iteration197_acceptance_runner.py`；目标 Ruff、`alembic heads`、scope manifest `--validate` 与 `git diff --check`。 | `PASS`（仅本地）：聚焦 113 passed、45 warnings（35.71s）；完整中台/配置 680 passed（202.28s）；迁移兼容 252 passed（139.73s）；验收运行器 21 passed（5.77s）；Ruff 与 diff 检查通过；唯一 Alembic head 为 `20260910_market_data_shared_source_payloads`；scope manifest 返回 `SCOPE_MANIFEST_VALID`，SHA-256 为 `d1dd587a1d199c2b155789d1c24d53eb3c0e320165b62daf5c57fc55d3544cd1`。覆盖一份 BLOB/N 个 refs、不同 bytes 不复用、receipt 重建 hash、非法 descriptor、跨 Session 已存 BLOB 篡改、SQLite foreign-keys-on child-table upgrade、非空 downgrade 拒绝、MySQL BLOB/LONGBLOB drift、PostgreSQL downgrade 排他锁顺序和 MySQL/PostgreSQL 离线 DDL。 | 证明当前候选的本地 SQLite、离线方言、迁移链和静态契约；不证明真实 AkShare/OpenBB、scheduler、MySQL/PostgreSQL 副本、浏览器、策略或生产验收。L-197-18 的质量 `NO-GO` 保持。 |

### 5.1.2 统一矩阵验收运行器、ID 映射和可复核构件

运行器位于 `src/backend/scripts/acceptance/iteration197_data_platform.py`，结果 schema 为 `iteration197-data-platform-acceptance-result-v2`。它的正式矩阵来自相邻设计包的 [统一验收文档](../迭代197-统一数据中台与OpenBB本地优先集成/ACCEPTANCE.md)，而不是本文件的 `AC-197-001` 至 `AC-197-028` 叙事编号。两套编号不可互换：运行器的 `AC-01:fund:G1` 映射为 `AC-197-MATRIX-001`，`AC-15:fund:G3` 映射为 `AC-197-MATRIX-015`；结果同时记录 `mode_slice_status`、`overall_case_status` 和 remaining gates，避免把局部 G1 当作整个 case 的通过。

本轮保留了可审计的原始 JSON：[离线 G1 结果](evidence/2026-09-10-acceptance-runner-offline-ac01-fund.json) 与 [live 闸门结果](evidence/2026-09-10-acceptance-runner-live-ac15-fund.json)。前者在 dirty candidate allowlist、scope/Alembic 预检、JUnit 和 socket audit 下运行，2 条测试本身通过；但其完整 AC 仍缺 G2，因此 runner 顶层返回 exit 3 / `NOT_RUN`。后者因没有外部批准和 approved source manifest 而在调用任何 provider 前 `BLOCKED`。离线 selector 只执行明确映射的 pytest node；未知 case 不会展开成全量执行，mode 不兼容时只回显稳定错误码。

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
| AC-197-010 | 使用假 AkShare SDK 返回正确/错误代码、不同市场、越界时间、超大表、超时和不支持语义；另对股票/ETF 流动性、ETF NAV 和 FX range 验证精确 route ID、字段与口径。 | 显式路由只接受批准的资产/市场/口径；`stock.liquidity` 与 `fund.liquidity` 只能走其 `reference_series` route，`fund.nav` 只能走 CN ETF `LISTING` 的 `fund_etf_fund_info_em`，并要求 `product_type=ETF` 与 `fund_identity_kind=LISTING`，保留 `source_reported + nav + CNY + fund_share`；`fx.range` 必须保留完整 OHLC。响应被截为半开区间；不支持项快速失败，不走样例或其它资产。 | `test_akshare_provider.py` | `NOT_RUN` |
| AC-197-011 | 使用临时 OpenBB JSON runner 验证正常协议、错配 request ID、未配置或非法 runner 命令、无界/朴素请求、stdout/stderr 超限、预规范化原始封套/hash、受控 HOME/工作目录，以及 timeout 后的子进程回收；对真实 runner 只执行无网络 `--self-check` 和一条表面合法 yfinance DTO 的导入前拒绝。 | 主进程只交互 JSON；协议错配、缺/非法 runner、非法 HOME/cwd、任一输出流越过上限、无 `format`/records 映射封套、自洽摘要替代原始 records、hash 不一致均失败关闭；POSIX timeout/cancel 终止 runner 专属进程组，即使 leader 已退出而后代仍持有管道。`--self-check` 不导入 OpenBB、不联网、不输出密钥、绝对包路径或文件哈希，只给出协议/包元数据摘要、构件候选状态、空 permit coverage 和非敏感配置摘要。环境 provider 列表必须恰为 `yfinance`，扩展 token 拒绝。当前无 permit/route，且构件清单仍为 `candidate`；即使包文件匹配，候选、未封装或与清单不匹配的环境均以 `OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED` 在动态扩展导入前拒绝。静态构件自检不能升级为安装、许可或网络验证。 | `test_openbb_provider.py` | `NOT_RUN` |
| AC-197-012 | 在服务端 capability 关闭/开启、缺失和格式无效的替身服务下调用 `POST /api/v1/data/queries`，并检查遗留数据路由和前端 v2 合约桥接；再设置相反的浏览器 VITE 值。 | 两页只按已授权 capability 行动：无效/不可用/显式关闭时，行情页不请求 contract、bundle 或事实接口，策略页不发送 bridge marker，默认后端为 503 稳定码；相反的浏览器 VITE 值不得改变这一点。开启后默认选择 `<asset_type>.realtime`；行情页探测 bundle，只有旧服务的明确兼容错误才改走无 bundle v2 contract。只有 bundle 已签发且用户明确选择本资产的 `ready + calendar_grid + 无维度` 的 `bars/reference_series` family 时，contract 才带该精确 binding。初始化、路由 tab 与资产切换只发 `local_only`，显式查询才发 `local_first`；只要 coverage 不是 `complete`，即使服务端已返回非空 receipt，页面也必须显示“本地覆盖不足”而不得伪称缓存命中、已获取或已入库。流动性和 NAV 显示声明字段表，`fund.nav` 不得以 price/close/K 线替代；`fx.range` 才使用 OHLC/K线；`crypto.realtime` 未配置时页面不执行事实或 legacy 数据读取来伪装 v2。输入错误在服务执行前 422；遗留接口仍注册。bundle 已签发后，v2 binding/必填字段/执行错误不能静默回退旧接口。 | `test_query_api.py`、`marketData.test.ts`、`DataPage.test.ts`、`StrategyPage.test.ts` | `NOT_RUN` |
| AC-197-013 | 两个同一 Web 进程、同一事件循环内的等价 `local_first` 缺口并发到达；并发 `refresh` 请求单列。 | 只有 `local_first` leader 发起一次 provider 调用并提交；follower 在独立 session 上复读持久化结果；`refresh` 保持各自执行语义而不复用 `local_first` follower；leader 取消/失败不遗留后台事务。 | `test_query_api.py`、本地优先持久化回归 | `NOT_RUN` |
| AC-197-014 | 多 Web worker/多进程的同一缺口或事实写入并发到达；分别模拟 follower、到期接管、陈旧 owner 写事实、事务 A 后 B 前失去 fence、release 丢失、通用 recovery 跳过 fenced pending receipt、provider 计数和 AkShare timeout 后同步线程仍运行。 | 候选代码以 `md_fetch_leases` 保证 exact-gap owner/follower、递增 fence、事实/可见性双栅栏；follower 不调用 provider，generic recovery 不会发布任何 fenced source receipt。真实 MySQL/PostgreSQL 多进程、数据库时间、崩溃/接管和零重复调用计数未完成前保持 `NOT_RUN`；AkShare timeout 的零重复 I/O 在可终止 runner 或心跳租约设计完成前为 `NO-GO`，不可因 SQLite 或单进程测试改写为 `PASS`。 | `test_fetch_lease.py`、`test_store.py`、`test_query_service.py`；真实多 worker 压测 | `NOT_RUN` |
| AC-197-015 | 在事务 A 写入 source snapshot、observation revisions 和 pending `MdPublication` 后模拟提交、读取、进程中断/恢复。分别覆盖普通 calendar/identity receipt 与带 lease generation 的 source receipt。 | A 已提交但无 `published_at` 的事实 durable-but-hidden；coverage、API 和 strict replay 均不可见。非 source-fenced receipt 可由受控通用恢复完成事务 B。带 lease generation 的 source receipt 只能由未过期的 exact owner/fence 协调路径完成 B；通用 recovery 必须跳过它。owner 已丢失、到期或崩溃时该 receipt 只保留审计证据，新的 owner 必须重新获取并写入新 receipt，不能发布旧事实。 | `publication.py`、`test_store.py`、`test_publication_recovery.py`；observation T0/T1/T2 见 L-197-01 | `NOT_RUN` |
| AC-197-016 | 先后导入首尾相接的 calendar manifest，再导入重叠 manifest；并发导入同一 `calendar_code`，并在事务 A/B 间读取。 | 已发布且时区一致的相邻 segments 可连续覆盖窗口；孔洞、重叠、重复 event 或缺少频率 grid 返回 typed unknown。`md_calendar_import_locks` 串行化同代码导入，pending segment 在 publication 前不可见。 | `test_calendar_importer.py`、`test_store.py`；相邻 segments/单 lock 见 L-197-01；MySQL/PostgreSQL 并发演练 | `NOT_RUN` |
| AC-197-017 | 发布 identity projection 后修改可变 `asset_instruments` authority；另写入 pending projection 并以两个 cutoff 严格解析。 | strict resolver 不因可变 authority/裸 lookup key 改写历史；只按已发布 frozen revision、有效期和 cutoff 解析。pending projection 不可见，发布后才在合适 cutoff 出现。 | `test_identity.py`、`identity_projection.py`；identity T0/T1/T2 见 L-197-01 | `NOT_RUN` |
| AC-197-018 | 让行情页 v2 返回超过 500 条的多页响应（当前开发回归为 17 页、516 条），并注入 query ID、identity/observation knowledge cutoff、revision 不一致、重复 cursor、篡改签名或不同 HMAC key 签发的 token。 | helper 持续收集至 `next_cursor=null`，不以 500 条或固定页数截断；任何分页完整性不一致 fail closed。签名不符在本地读取、provider 调用或写入前以 `CURSOR_SIGNATURE_INVALID` 拒绝。 | `src/__tests__/views/DataPage.test.ts`、`test_query_service.py`；见 L-197-01、L-197-03 | `NOT_RUN` |
| AC-197-019 | 对 date-indexed OpenBB `OBBject` 和离线 yfinance fork 参数转换请求 UTC 日对齐的 `1d` 半开边界、最长 3650 天边界、超长窗口、`1w`/`1mo`、分钟和非日对齐窗口；真实 runner 只允许验证导入前拒绝。 | 离线代码以 `to_df(index=None)` 保留 event 时间。fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` / `openbb-yfinance 1.6.3.post1` 只允许 `1d`：由父 `[start,end)` 的最后一个 UTC 日得到 OpenBB 包含式 `end_date`，并以 `period=None` 向 yfinance 传递该日期加一天的排他 `end`；保存结果仍裁剪回父窗口。`1w`、`1mo`、分钟、非 UTC 日对齐和超过 3650 天的窗口必须在扩展导入前拒绝。离线 fork 测试不证明真实出站请求、返回数据或许可。未来还必须证明完整隔离导入闭包、不可变镜像、AGPL-3.0-only 许可证、出网审计、static permit/source-policy/provider DTO/runner mirror 的逐轴一致性；当前 permit 为空，正常请求不得导入扩展或测试网络。 | `test_openbb_provider.py`、fork 离线测试；第 8.2 节真实运行器演练 | `BLOCKED` |
| AC-197-020 | 用无 `data:read` 用户访问 `query-bundle`、`query-contract` 和事实查询；再分别使用失效/未授权主来源、仍获准 fallback、本地旧/compatibility 来源、撤权 calendar、授权变更后的 cursor、provider 请求期间撤销角色/registry、同一 provider 的重复 request ID、以及 provider DTO hash 错配执行查询/写入。 | 无读取权在家族、目录、主数据、calendar 或事实 I/O 前 403；只允许当前 registry 批准的 route source、`VERIFIED` `MdSourceSnapshot` 和位于同一 allow-list 的 `VERIFIED` calendar 参与读取。成功获取分别保存静态 policy 摘要、动态 access-grant 摘要和冻结 source authorization；无 grant 不能触发在线写入，显式 compatibility 回执不进入 v2 结果。网络返回后的 current/locking recheck、旧 cursor 或 follower 重读若发现角色/registry 改变均失败关闭；同一 provider 的重复 request ID 与错误 request evidence 均不落库。 | `test_access_authorization.py`、`test_query_service.py`、`test_store.py`、`test_storage_models.py`、`test_calendar_importer.py`、`test_query_api.py` | `NOT_RUN` |
| AC-197-021 | 对同一 snapshot 的多条 `option_chain`（不同 expiry/strike/right）和同一 report date 的多条 `position_report`（不同 reporting entity/rank）发起请求；分别尝试未绑定和绑定到目前未配置家族的路径。 | **NO-GO：当前不把这类请求视为可执行的数据产品。** 公共 HTTP 未绑定请求在 catalog/identity/provider 前以 schema HTTP 422 拒绝；抵达 resolver 的未绑定内部请求以 `DATA_FAMILY_BINDING_REQUIRED` 拒绝；已绑定的未配置家族以 `DATA_FAMILY_UNCONFIGURED` 拒绝。任何未来启用必须先证明稳定 record key、事实唯一性/读取/分页/provenance、slice/report completeness 及同一时间多行 `provider → store → PIT replay`；本地单行或空响应不能作为通过证据。 | `test_query_resolution.py`、`test_query_api.py`；未来多记录端到端回归 | `BLOCKED` |
| AC-197-022 | 自动输入预检、普通按钮预检、用户明确缓存补齐分别执行；后者尝试手工构造错误 mode/consistency/cutoff/cursor、关闭 v2/online/cache-fill 中任一服务端前置条件、display-only source、research-only source、成功 receipt 与不完整或 contract 不兼容响应，并覆盖 `query_v2=true, online=true, cache_fill=true, bridge=false`。 | 自动输入与普通预检只能 `local_only + research + strict` 且不触网。显式补齐只能 `local_first + research_cache_fill + display`，无 cutoff/cursor；`query_v2=false` 时 v2 HTTP 边界首先返回 `MARKET_DATA_QUERY_V2_DISABLED`。在 `query_v2=true` 下，只要 online fetch 或 effective cache-fill 关闭，返回 `MARKET_DATA_RESEARCH_CACHE_FILL_DISABLED` 且不调用 query service，display-only source 不可借用。cache-fill 响应必须逐项匹配 exact contract 的 identity、dataset、asset type、metadata version、kind/frequency、source policy 与 family/version，否则不得显示 receipt、标记补齐成功或触发 strict 复读。bridge=false/cache=true 的正例必须显示并允许显式补齐；成功后只做同一冻结预检快照的 `local_only + research + strict` 本地 v2 复读，不发送 bridge marker、不修改迭代 196 precheck 通过状态，也不形成研究/回测/审批工件或 PIT 证据。 | `test_query_contract.py`、`test_query_api.py`、`test_access_authorization.py`、`test_store.py`、`StrategyPage.test.ts`；真实 E-197-10 | `BLOCKED` |
| AC-197-023 | 对 11 个 B1 单记录 family 读取 bundle；分别执行 `stock.liquidity`、`fund.liquidity`、`fund.nav`、`fx.range` 的精确 contract/route 离线检查，执行已开通 family 的 provider→store→local reread calendar-grid 链路，并尝试用 DTO、静态卡片、dataset code 或 source policy 交叉升级其它 family。 | 六个逻辑 dataset 保留独立 schema/字段/资产范围并共用不可变 revision binding；DTO/registry/路由逐轴核对精确 family shape。四个候选 B1 的 `adjustment`、`price_basis`、`currency`、`unit` 都是必传的精确值：FX 的 `null` 轴必须保留在 JSON 中，NAV 固定为 `source_reported + nav + CNY + fund_share`，省略或变更任一轴在 provider I/O 前稳定拒绝。`fund.nav` 还要求 CN-SSE/CN-SZSE、`product_type=ETF` 和 `fund_identity_kind=LISTING`；policy、compatibility bridge 和 adapter 三层都在 I/O 前拒绝 LOF、REIT、share class 或缺失身份。只有上述四个 B1 family 可在候选代码中由用户显式选择：两个流动性 family 使用各自的 `reference_series` AkShare route，NAV 使用专用 ETF route，FX range 使用完整 OHLC route。其余七个 B1 family 仍为 `unconfigured`，不能产生 provider 调用或事实读取；B2 多记录 family 仍稳定拒绝。真实来源、日历、写回和每个 family 的 `provider → store → local_only` 证据完成前，四个候选开通项也不得标为正式可用。 | `test_bootstrap.py`、`test_dataset_contracts.py`、`test_legacy_contract.py`、`test_akshare_provider.py`、`test_query_service.py`、`marketData.test.ts`、`DataPage.test.ts`；未来逐项 B1 端到端验收 | `NOT_RUN` |
| AC-197-024 | 对已绑定 research unit 依次尝试复制 token 到另一 unit、修改 workspace 为 trading、撤销 `data:read`、拒绝/变更当前 source evidence、在 fresh replay 后禁用 sealed source registry、在长 replay 间提交撤销 receipt、篡改 unit binding 字段、客户端传入 `runtime_dir`、排队重试或子进程启动前撤销、同一 unit 的两个合法 OOS 请求并发运行、停止发生在 preflight/task promotion 边界、延迟 poller 回写，以及替换 CSV 路径或插入 symlink。 | 浏览器 create/batch 在写 unit 前以 `MARKET_DATA_BINDING_CONSUMER_CREATE_FORBIDDEN` 拒绝；仅私有 AI 编排可建立 exact `(binding,user,intent,workspace,unit)` consumer。每次任务创建、并发槽重试和子进程启动前都必须在 fresh session 重读 unit、重放当前 strict `local_only + backtest + PIT` 查询并逐条比较 sealed evidence；最终 current-read fence 锁定 sealed snapshots 与 registry 并重新授权。严格绑定 unit 必须先由数据库 CAS 取得唯一租约，竞争请求不读绑定、不写 runtime、不创建第二 task；task 仅在租约原子提升为 task ID 后调度，取消/轮询/终态写入只能 CAS 当前 owner，未知/超时观察不得释放运行权。任何 scope/consumer、权限、来源、撤销、身份、窗口、HMAC、artifact hash、租约或 fd-path-chain 失败均不创建或执行 runtime/backtest，并使被拒绝的 bound runtime 不可执行；若共享确定性目录仍可能属于新 lease，失败路径不得删除或覆写它，以避免 ABA。公共 API/通用 service 以 `BACKTEST_RUNTIME_DIR_CLIENT_FORBIDDEN` 拒绝客户端目录。读取 CSV 使用同一已验证 `O_NOFOLLOW` 文件描述符，路径替换不能改变 pandas 读取的 inode。 | `test_research_binding.py`、`test_strategy_runtime_support.py`、`test_workspace_service.py`、`test_backtest_service.py`、`test_backtest_enhanced.py`；最终候选本地记录 | `NOT_RUN`（正式候选） |
| AC-197-025 | 调用默认 AkShare CFFEX source、使用 authenticated source seam 返回 `symbol,date,settle,pre_settle,open_interest` rows、可选 `MARKET` 的非 CFFEX 行、重复/缺字段/缺 target、错误 `family_id`、五个语义/策略轴、错误 authorization purpose、当前 registry 禁用、第二个 target 普通失败，以及已 durable publish 后尚未返回时的 Store/lease-release cancellation（包括 release failure），以及最终 release 返回失败。 | 默认 CLI 为 `NOT_RUN` 且 `--live` 为 `BLOCKED`，两者均零网络/零数据库写入。默认 `AkShareCffexSettlementSource` 在 import/endpoint/network 前以 `CFFEX_SETTLEMENT_SOURCE_TRANSPORT_UNAPPROVED` 拒绝，当前没有可调用线上 CFFEX source。authenticated seam 的无 MARKET 行可由冻结 CFFEX request/route 映射，显式非 CFFEX 行和任何全批校验失败在写入前拒绝。错误 family、语义、purpose 或当前 registry 在 provider I/O 前拒绝。全 target 成功后才返回成功报告；普通后来失败返回 `CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED` 与已返回 prefix；最终 lease release 失败时不返回成功报告，而以 `CFFEX_SETTLEMENT_FETCH_LEASE_RELEASE_FAILED` 携带完整 durable prefix；cancel 先完成当前 shielded Store 或 lease-release task，只要已有 durable prefix 就以仍属 cancellation 的 `CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED_CANCELLED` 携带精确返回 prefix，Store task 失败则保持原取消，release task 失败则作为该取消错误的 cause。绝不宣称跨合约原子性、进程崩溃恢复或生产 scheduler。 | `test_cffex_settlement_collector.py`；第 8.3 节的真实 scheduler 演练 | `NOT_RUN` |
| AC-197-026 | 使用有/无 `data:read` 的用户读取 capability；在原始变量矛盾的配置下比较 capability 与 `POST /queries`；分别延迟 mandate 确认与 capability，期间修改标的、timeframe、日期窗和质量门槛后提交；验证每次并发提交只使用自身最新 capability；验证 mandate 不匹配时 binder/artifact/task/snapshot/workspace 写入全为零、`RB0` 与 `rb0` 不匹配、伪造 auto preview/objective 被忽略。对带旧 binding 的 run-record/task-snapshot 续跑尝试旧 CSV/provider/目录/mixed `data_config` override、任意 full override 的 context/lineage 注入，并在 bridge 关闭时向同步、异步和两种续跑入口提交 `market_data_asset_type`、`market_data_binding_*` 或精确 `market_data_binding` marker。再通过公开 workspace POST/PUT 的顶层、嵌套、列表和大小写/前缀键伪造 `ai_research*` record，篡改已签名字段、复制 A workspace record 至 B、移除/替换 signature/version、轮换密钥，并使用无签名 legacy task/run 触发续跑。 | 无 `data:read` 时 capability 在返回任一 rollout 字段前以 403 拒绝；有权限时 capability 不泄露原始配置、provider 或密钥，且只返回有效派生值。若 `online=false`，即使 raw cache-fill=true，查询端点也以 `MARKET_DATA_RESEARCH_CACHE_FILL_DISABLED` 拒绝且不调用 service。前端必须在任何 await 前固定完整 request 与 mandate match basis；最终 payload 的标的、timeframe、日期、质量门槛、mandate ID 和 marker 均来自同一快照。服务端验证并重建 binding，绝不信任最小客户端意图；所有 submit/continue 直接使用本次 capability 返回。续跑前先验签并比较 source owner/outer workspace/record ID/完整 payload；仅验签的 blank-auto source 可恢复自动语义，所有 legacy/default marker 均失败关闭。公开 workspace API 对保留命名空间返回 `WORKSPACE_SERVER_OWNED_SETTINGS_FORBIDDEN`，不会写入或影响 preparer/LLM。续跑剥离旧 binding，仅允许单字段资产意图，并对新 task intent 签发新 binding；full override 仍使用服务器来源重建 context/lineage。普通同步/异步入口收到 continuation context/lineage 在 mandate、binder、artifact、workspace、task 或 snapshot 写入前拒绝。bridge 关闭时所有入口返回结构化 `MARKET_DATA_BRIDGE_DISABLED` / 503；同步路径不创建 workspace，异步和续跑路径在 task state、snapshot 或 background runner 前拒绝，不能回退旧 CSV。 | `test_query_api.py`、`test_ai_research_direction_a.py`、`test_ai_strategy_research_service.py`、`test_strategy_api.py`、`StrategyPage.test.ts` | `NOT_RUN` |
| AC-197-027 | 以合法服务端签名的 run、paper workspace/unit、策略快照和 manager launch 构造纸面复核；再逐一篡改策略模板或 unit 配置、使用无签名/冲突同 run ID 记录、替换 instance/launch、移除/替换指标回执、让正常配置二次 freshen/restart、以及在刷新时令记录过期。 | 只有签名策略快照、paper runtime anchor、当前 launch 和 HMAC 指标回执全部匹配时才可成为实盘候选。策略或配置漂移、伪造/冲突历史、旧 launch 或缺失回执均失败关闭；未实际配置变更的二次 freshen 仍保持锚点有效。过期合法记录按其刷新前原始 signature 定位并重签写回，`runs` 与 canonical `last_run` 同步更新；未签名或冲突签名记录不被替换或升级。 | `test_ai_strategy_research_service.py`、`test_live_trading_manager.py` | `NOT_RUN`（正式候选） |
| AC-197-028 | 对受保护的 paper/live handoff unit 分别调用公开 workspace run/start/start-all/stop/delete、strategy create/update/delete、simulation 与 live-trading 路由；再经受控 activate/deactivate 流程执行启动、停止、停止失败、历史 A handoff 在后续 B run 后停止、以及当前/历史页面按钮交互。 | 所有通用/公开路径稳定拒绝，不能伪造启动 capability。受控 activate 在物化后、manager spawn 前重新校验当前纸面证据，并只使用一次性私有能力启动；deactivate 先持久化 pending，只有确认真实停止后撤销批准。停止失败保持 pending/failed；停止历史 A 不覆盖 B 的 canonical `last_run`，也不能恢复 A 的启动资格。页面只调用受控路由并展示启动/停止状态。 | `test_ai_strategy_research_service.py`、`test_strategy_api.py`、`test_live_trading_manager.py`、`src/__tests__/api/strategy.test.ts`、`src/__tests__/views/StrategyPage.test.ts` | `NOT_RUN`（正式候选） |
| AC-197-029 | 向默认关闭的私有 `market.stock_valuation_captured_snapshot / valuation_snapshot / snapshot` collector 提交 forged envelope、任何 HTTP/fetch 尝试、未冻结或错配 CN listing identity、重复/缺字段/非有限已知行、未知结构有效代码、伪造来源时间、超出 2 MiB/10 MiB/16-target 边界的批次，以及第 N+1 个 target 的 Store/publication 失败或外部嵌套 payload 篡改。 | 入口只接受预捕获批次，固定验证 provider、endpoint、空 request shape、collector version、source revision、captured_at、collector_observed 和自排除 SHA-256；构造时递归冻结 source payload。已知 target 仅在精确 capture instant 的一微秒选择窗口内持久化，`source_event_time/source_as_of` 均为 null；unknown 只进 quarantine。所有预算与授权检查先于写入，后续 target 失败报告 durable prefix；公开 `stock.valuation` 继续返回 `DATA_FAMILY_UNCONFIGURED`。共享 BLOB 存储、引用和重建证据另由 AC-197-030 验收。 | `PASS`（L-197-21，本地开发回归）；真实 scheduler/source/database/browser 验收 `NOT_RUN`。 |
| AC-197-030 | 将同一合法 `source_batch` 投影为 N 个 target receipt；验证恰一条 canonical UTF-8 shared payload、N 条 target source-snapshot ref、每个紧凑 manifest 不含完整 batch，并逐项比对 ref/descriptor 的 hash、format、bytes、role。再复算 BLOB hash/bytes，将 JSON 解码的 BLOB 放回 `receipt_payload.source_batch`，逐一复算完整 receipt hash。提交不同字节的 batch、非法 descriptor、缺失段或篡改已存 BLOB；在 SQLite `foreign_keys=ON` 且 parent snapshot 已有依赖时从 consumer revision 升级，尝试对非空 shared 表 downgrade，验证 MySQL BLOB/LONGBLOB drift 和 PostgreSQL downgrade 锁顺序，并离线渲染 MySQL/PostgreSQL DDL。 | Store 只接受固定 `source_batch / canonical-json-utf8-v1 / source_batch` descriptor，并自行计算内容地址、格式和字节数；相同 bytes 只复用同一 BLOB，不同 bytes 新建行。任一非法 descriptor、缺失段或内容完整性冲突在新事实写入前失败，长期 Session 复用前也强制从数据库重读。`MdPublication` 只引用 target source snapshot，shared BLOB 没有独立 publication 或公开读取路径；本轮没有 shared-payload reader，因此数据库外部篡改的 ref/manifest 一致性审计属于未来 reader 的 fail-closed 前置条件。迁移只创建 child evidence tables，不改写 `md_source_snapshots`；downgrade 在任一 immutable payload/ref 存在时稳定拒绝，MySQL 使用 MEDIUMBLOB 且需 writer-drain fence，PostgreSQL 使用 BYTEA 并在空表证明和 DROP 前对 child evidence 表取得排他锁。 | `PASS`（L-197-21，本地 SQLite/离线方言回归）；真实 MySQL/PostgreSQL 演练、真实 AkShare/OpenBB 和任何公开读取授权验收仍为 `NOT_RUN`。 |


## 6. 数据中台专项验收

`AC-197-025` 的 authenticated seam 补充约束：生产 registry 当前为空，collector 只由静态 descriptor ID 解析 construction-only factory，不能接受 caller source 或自建 descriptor。未来 descriptor 必须固定 provider/revision/endpoint、无 credentials/path/query 的 HTTPS origin、`pinned-peer-certificate-sha256-v1` 与小写 pin digest，并使 canonical descriptor digest 进入 lease/receipt。raw envelope 顶层只能含 collector request、source route、`cffex-settlement-transport-evidence-v1` 与 response rows；route/evidence 必须逐项匹配已解析 descriptor，evidence 只允许版本、`https` scheme、origin、`tls_verified=true`、certificate policy 与 peer-certificate SHA-256。未登记 descriptor、HTTP、未验证 TLS、错误 revision/policy/digest、origin 不一致或证据额外字段均在 Store 写入前拒绝。response rows 的任意嵌套 mapping/list 出现 authorization/token/secret/password/credential/cookie/access/API/private key/bearer/headers 等 credential-shaped key 时也必须以 `CFFEX_SETTLEMENT_SOURCE_SENSITIVE_PAYLOAD_REJECTED` 拒绝，Store 计数为零，且稳定错误不回显 key/value。以上离线 gate 只固定可审计形状与本地拒绝，不能替代 TLS、adapter、证书链或 egress 的真实验收。

### 6.1 本地优先与可追溯性

对每个将启用的 `(dataset_code, canonical_id, data_kind, frequency, adjustment, price_basis, currency, unit, source_policy_id)` 组合执行下列试验，并保存结果：

1. **本地命中**：准备覆盖完整的本地版本、合格字段和请求频率的冻结显式网格；调用 `local_first`。数据库和适配器审计必须显示零外部请求，响应含对应数据系列、来源快照/修订标识及 `complete` 覆盖。随后写入一条较新的窄字段修订并重试宽字段请求，确认旧的完整修订仍可被选择而不触网。
2. **精确缺口补齐**：删除或隔离一个明确事件，调用相同请求。只允许批准路由收到该缺口的半开窗口；成功后查询 `md_source_snapshots`、`md_observation_revisions`、原始载荷 hash 和来源回执，再重复相同 `local_only` 请求。第二次请求必须零外部调用，且返回保存后的本地事实而非内存中的适配器对象。
3. **拒绝路径**：提供错误标的、错误 provider receipt、越界 event、字段不足、原始载荷 hash 错配或缺少请求频率 grid 的日历。检查没有错误来源回执/观测进入事实表，并且 API 只返回稳定机器码、覆盖状态或 warning，不输出堆栈和凭据。
4. **同进程并发**：让两个等价 `local_first` 请求在同一事件循环同时命中同一缺口。记录 provider 调用数、来源回执数、leader/follower 记录和两个独立数据库 session 的结果。此试验只验收单进程行为，不能替代 E-197-08 的多 worker 验收。
5. **publication 恢复**：在事务 A 提交、事务 B 写入 `published_at` 前停止调用方。对 calendar/identity 等非 source-fenced receipt，可由受控通用恢复程序继续 pending publication；记录事实/receipt 的 ID、hash、A/B 时间、恢复前后的 `local_only` / strict 读取。对带 lease generation 的 source receipt，通用恢复必须保持其 hidden；只有仍未过期的 exact owner/fence 协调路径可完成 B。若 owner 已丢失或到期，记录旧 receipt 仍不可见，并由新 owner 重新获取生成新 receipt。任何恢复后可见的事实都只能在合适 cutoff 可读。

验收人应记录每次试验的 query fingerprint、source snapshot ID、revision ID、执行时间、数据库计数前后变化和网络调用计数。仅保存屏幕截图而不保留这些可关联标识不足以证明回填链路。

### 6.1.1 A 股估值预捕获批次候选

`AC-197-029` 与 `AC-197-030` 已通过本地开发回归，只证明私有 capture snapshot collector 的离线拒绝、导入和持久化边界；它们不是 `stock.valuation` 的真实取数或页面验收。L-197-20 的 `139 passed, 1 warning` 是 shared payload/ref 增量前的 collector 历史证据。当前候选的 SQLite focused Store/collector/migration/config 集为 `113 passed, 45 warnings`，完整中台/配置集为 `680 passed`（L-197-21）。这仍不替代真实 AkShare、日线 calendar、MySQL/PostgreSQL、浏览器、scheduler 或策略验收。

1. collector 只接受私有 `market.stock_valuation_captured_snapshot / valuation_snapshot / snapshot` 的预捕获批次，无 fetch/HTTP/public query/legacy route；公开 `stock.valuation` 持续 `NOT_CONFIGURED`。
2. 批次固定核验 AkShare provider、`stock_zh_a_spot_em`、空 request shape、collector version、source revision、精确 UTC `captured_at`、`collector_observed` 与自排除 SHA-256。构造时递归冻结 source payload；外部嵌套引用之后的变更不能改写待验证证据。
3. 每个已知 target 必须带冻结 CN-SSE/CN-SZSE listing identity、四字段语义、`local_only + display` 和 `[captured_at, captured_at + 1µs)` 窗口。`event_at` 仅为 capture instant，`source_event_time`、`source_as_of` 均为 null；它不是来源 event、日线 calendar event 或 public `as_of`。
4. 已知 target 的错配、重复、缺字段和非有限值使整批零写入；未知结构有效代码只进入 receipt-local quarantine。授权或 Store 写入前必须检查 2 MiB source envelope、最多 16 targets 和 10 MiB 完整 target receipt；任一超限整批零写入。完整 `source_batch` 以 canonical UTF-8 BLOB 仅保存一次，每个 target 仅持有紧凑 receipt 与受控子引用；先比对 ref/descriptor、复算 BLOB hash/bytes，再按引用重建完整 receipt 并匹配其 `payload_sha256`。该离线存储证据不等于真实 source、数据库或页面验收。
5. 全批预检后每个 target 独立经历事实事务 A 与 publication 事务 B；N+1 失败或取消时记录 durable prefix。只有 publication 后的 Store `local_only` 重读可作为本地保存证据。真实来源、daily coverage、严格 PIT、MySQL/PostgreSQL、scheduler、浏览器和策略/回测仍全部 `NOT_RUN`。
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

当前候选有十个 `ready` family：六个 `*.realtime` 的 `market.bars`，以及 `stock.liquidity`、`fund.liquidity`、`fund.nav` 三个日线 `reference_series` 和 `fx.range` 的完整 OHLC 日线。后面四个只在行情页明确选择、server bundle/contract 精确绑定、来源策略匹配时进入候选代码路径；它们没有扩展策略页的 strict bars/PIT 预检。其它七个 B1 family、快照和 B2 多记录产品仍为 `unconfigured`。本表的“本地命中/受控缺口补齐”仍是正式验收要求，**不是当前真实环境通过声明**；AC-197-021 保持 `BLOCKED` / NO-GO，直到多记录事实模型和完整性规划已实现并完成真实端到端证据。

### 6.3 严格研究与回测专项

对 `purpose=research` 和 `purpose=backtest` 至少各运行一个真实的已批准数据集：

1. 请求必须为 `consistency=strict` 且携带含时区的 `knowledge_cutoff`；回测截止点不得晚于请求结束时间。
2. 在截止点后新增修订或回填主数据版本，再以原截止点重放。重放不得看到新增事实，也不得因在线刷新改变历史结果。
3. 保存已解析 canonical identity、metadata version、冻结 identity projection、数据系列、来源策略、日历版本、查询 fingerprint、知识截止点、source/calendar/identity publication receipt、来源快照和修订 ID 至研究/回测工件。
4. 同一候选数据集进行两次本地重放，输出行、字段哈希和工件指纹应一致；不一致必须按 `FAIL` 处理，不能以“数据源更新”解释。

迭代 196/197 的工件格式、迁移链与本地 strict-binding 回归已完成集成；本专项不再因“迭代 196 最终工件格式”本身而阻塞。它仍等待已批准真实数据的 PIT 重放、浏览器/API/数据库三方证据和部署运行证据，详见第 9 节。

## 7. 数据库迁移与灾备验收

### 7.1 候选数据库演练

在生产拓扑等价的、可恢复的 MySQL/PostgreSQL 副本上执行：

1. 记录升级前 schema、Alembic revision、遗留 AkShare 表行数及抽样校验和。
2. 在已完成 196/197 合并链的候选版本上执行 `alembic heads`，结果必须只有一个 head；若多 head，状态为 `FAIL`，不可人工任选一条链继续上线。
3. 执行 `alembic upgrade head`，重新审计 `dg_*`、`md_*` 的列、外键、唯一约束、检查约束和索引。任何 MySQL 执行 `20260909_market_data_constraint_name_portability` 时，都必须先停止全部 market-data writer，并在本次命令明确设置 `MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_MAINTENANCE_FENCE=confirmed`；执行 `20260910_market_data_shared_source_payloads` 时同样必须停止 writer 并设置 `MARKET_DATA_SHARED_SOURCE_PAYLOAD_MAINTENANCE_FENCE=confirmed`。即使当前反射结果看似无需改动也不能跳过，以免检查与 DDL 间发生 TOCTOU。有限等待 `GET_LOCK` 只串行化迁移执行者，不能替代 writer drain。
4. 在每个新建和复用的应用连接记录时区：MySQL 记录 `@@session.time_zone`（应为 UTC 等价值），PostgreSQL 记录 `SHOW TIME ZONE`（应为 `UTC`）。当前候选没有可替代这项检查的自动 session-time-zone 证据；若任何连接不符合，停止验收并先补齐部署/连接初始化合同。
5. 使用带偏移的边界 timestamp（包括交易日和 `knowledge_cutoff` 临界前后）在事务 A 写入来源回执、观测与 pending publication，先从第二个连接重读 `local_only` 与 `strict` 请求，再以事务 B 写入 `published_at` 后重复读取。MySQL 与 PostgreSQL 都必须证明 UTC 归一化、A/B 间的不可见性、发布后的 PIT 可见性和字段选择未因连接时区偏移；SQLite 不可替代。
6. 验证遗留 AkShare 表定义、行数和抽样校验和未被迁移改写；验证新表初始为空或只含受控引导数据。
7. 在新表写入一条受控测试来源回执后，确认降级路径不会静默删除带证据的数据。需要回退时执行已批准的导出/治理过程，而不是强制 `downgrade`。
8. 做一次备份恢复演练，恢复后重复 `local_only` 读取、来源链追溯、时区检查和 schema 审计。

### 7.2 当前状态

| 项目 | 状态 | 阻塞原因/所需证据 |
| --- | --- | --- |
| SQLite 升级/降级与离线方言渲染的自动化契约 | `PASS`（当前本地开发回归） | L-197-21 覆盖 shared payload/ref 的 SQLite `foreign_keys=ON` 已填充 parent 升级、非空 downgrade 拒绝及 MySQL MEDIUMBLOB/PostgreSQL BYTEA 离线渲染；这不替代 MySQL/PostgreSQL 真实方言与 UTC/PIT 演练。 |
| MySQL 准生产升级、UTC session、PIT 与恢复演练 | `NOT_RUN` | 需要经授权的可恢复数据库副本、每连接 UTC 验证、维护窗口和跨连接证据；任何执行 portability revision 的 MySQL upgrade 均须先 drain writer 并显式设置 `MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_MAINTENANCE_FENCE=confirmed`，任何执行 shared payload revision 的 MySQL upgrade 还须设置 `MARKET_DATA_SHARED_SOURCE_PAYLOAD_MAINTENANCE_FENCE=confirmed`。MySQL `DATETIME` 时区语义不能靠 SQLite 推定。 |
| PostgreSQL 准生产升级、UTC session、PIT 与恢复演练 | `NOT_RUN` | L-197-10 已在 disposable PostgreSQL 证明 fresh 与 predecessor→head 升级、两个 UTC session、截断 CHECK 名修复和清理；仍需要经授权的可恢复副本、PIT A/B publication、exact-identity 真实列审计与恢复演练。 |
| 多进程 calendar import lock 与 observation/source writer 并发 | `NOT_RUN` | L-197-10 已以真实 PostgreSQL 的两个 OS 进程、确定性 provider 和 durable lease 验证一个精确缺口仅一次调用及 follower 本地重读；calendar lock 的跨连接行为、真实 provider、故障接管和连续分段导入仍需真实方言演练。 |
| 196/197 Alembic 单 head 合并 | `PASS`（本地隔离 SQLite） | `20260909_ai_research_market_data_merge` 后依次追加 binding、consumer 与 `20260910_market_data_shared_source_payloads`，当前唯一 head 为后者；shared payload revision 只新增 child evidence tables，SQLite `foreign_keys=ON` 的已填充 parent 升级和非空 downgrade 拒绝均已本地回归。MySQL/PostgreSQL 仍为 `NOT_RUN`。 |

## 8. 真实提供方验收

### 8.1 AkShare 受控实时验证

仅在数据许可、访问条款和网络访问已获确认的环境执行。每次调用使用小窗口、最小字段集和非敏感公开标的，遵守上游限频：

1. 为每个实际启用路由选择精确 canonical identity，验证请求符号、市场、函数路由、复权、价格口径、币种、单位与来源策略完全一致。
2. 验证 AkShare 若使用含结束日的接口，适配器仍只保存 `[start, end)` 内事件；请求窗口外的记录不能写入。
3. 验证返回标的与请求身份不一致时，适配器拒绝结果且本地不写入来源回执。
4. 验证超时、并发槽耗尽、超大响应和不支持的资产/数据类型产生稳定码，不绕过限制调用另一函数或返回样例。
5. 成功案例必须保留匿名化的请求语义、`provider_id`、source revision、source snapshot ID、行数、字段哈希和后续 `local_only` 复读证据；不得记录账户凭据或完整未授权原始载荷。

当前状态：`FAIL`（已执行的 `stock.liquidity` 子用例）。离线 AkShare 假函数测试只能证明代码契约，不能证明实时服务或许可。2026-09-09 的受限 `stock_zh_a_hist("600000")` 小窗口探测返回一个 `ProviderFetchResult`，但安全计数为 `response_row_count=0`、`normalized_observation_count=0`：临时库内有 1 条 persisted fetch/receipt，却没有 observation revision、完整覆盖或后续 `local_only` 复读；临时数据库随后已删除，未保留可复核的 snapshot/revision ID。此前 `forex_hist_em("USDCNH")` 的受限探测只是无成功链的历史线索，未附本候选命令、版本和输出，故不改变该 route 的正式 `NOT_RUN`。这些记录不能用来宣称四个 B1 family 的真实来源通过；除 `stock.liquidity` 的失败子用例外，`fund.liquidity`、`fund.nav`、`fx.range` 等其它实际启用 AkShare 路线仍为 `NOT_RUN`。

### 8.2 OpenBB 隔离运行器验证

仅在单独的、可销毁的 OpenBB 运行环境执行；FastAPI/主应用进程不得安装或导入未经审核的 OpenBB 扩展以满足测试。

当前静态 permit matrix 为**空**，`MARKET_DATA_OPENBB_ALLOWED_MARKETS` 不会生成 route、legacy contract 或 provider fallback。fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` 的 `openbb-yfinance 1.6.3.post1` 仅是待封装构件候选：它把 daily route 的 OpenBB 包含式 `end_date` 转为 yfinance 的排他 `end=end_date + 1 UTC calendar day`，并使用 `period=None`。候选只定义 `1d`、UTC 日对齐、最长 3650 天的父半开窗口；它不批准 `1w`、`1mo`、分钟、非日对齐或超长窗口。构件清单的版本/包内哈希检查只能证明期望构件一致性，不能证明可导入、可联网、可使用或获许可。

在完整隔离动态扩展导入闭包、不可变运行镜像、AGPL-3.0-only 许可证书面审查和最小出网审计完成前，任何正常 OpenBB 请求必须在**动态扩展导入前**拒绝。本轮不得执行真实 OpenBB/yfinance 网络调用或把 `--self-check` 称为来源验收；只可运行无网络自检，其输出不得含密钥、环境变量值、绝对包路径或文件哈希。当前构件清单的 `candidate` 状态、未封装环境或与清单不匹配环境都应返回 `OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED`；不得把清单数据改写为启用状态，未来必须由新的执行认证代码和独立验收解除该拒绝。backend wheel 只打包两个 manifest，不把源码 `scripts/openbb_market_data_runner.py` 作为可执行 runner 交付，且 provider 会拒绝 checkout 内脚本；因此没有 OCI image 或独立 runner package 的 digest、绝对 executable 与 checkout 外 HOME/workdir 证据时，配置 runner 也是 `NO-GO`。该机器码不能被解释为已安装或已通过运行审计。

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


### 8.3 CFFEX 日结内部采集器验证

未来 authenticated source 必须先从静态 reviewed registry 的 descriptor ID 构造；当前 registry 为空。descriptor 固定 provider/revision/endpoint、HTTPS origin、`pinned-peer-certificate-sha256-v1` 与 pin digest，batch evidence 只与 descriptor 比较，不能自报批准 origin。route 与 evidence 必须绑定同一无 credentials/path/query 的 HTTPS origin，evidence 只含版本、scheme、origin、TLS verified boolean、certificate policy 与 peer-certificate SHA-256；response rows 的任意嵌套 mapping/list 也不得含 credential-shaped key。此离线 shape 检查不能代替真实 adapter、证书链、访问条款或 egress 验收。

本轮新增的 `CffexSettlementCollector` 是内部、默认关闭的候选，不改变 `futures.settlement` 在页面/API 中的 `unconfigured` 状态。`scripts/collect_iteration197_cffex_settlement.py` 不带参数只返回 `NOT_RUN`，`--live` 也只返回 `BLOCKED`，两者均不导入 AkShare、不连接数据库、不发起网络请求；未来 scheduler 必须在独立变更中提供审核过的 target map、授权 descriptor、calendar、registry 与运行身份。

离线回归只证明下列契约：当前 AkShare CFFEX source 在 import/endpoint/network 前以 `CFFEX_SETTLEMENT_SOURCE_TRANSPORT_UNAPPROVED` 硬拒绝，故不会调用本机明文 HTTP route；冻结的 collector request/source route 可供未来 authenticated seam 证明 CFFEX，故该 seam 的无 `MARKET` 列 `symbol,date,settle,pre_settle,open_interest` 行可映射；显式非 CFFEX 市场、重复行、日期/字段/target 不一致均在事实写入前拒绝；错误 family、`unadjusted/settle/CNY/contract/source-policy` 轴、source-authorization purpose 或当前 registry 禁用不会触发 provider I/O。全批验证后，当前存储仍按 contract 逐一持久化和发布。普通后续 target 失败时，`CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED` 会带已返回 prefix；最终 lease release 失败时会以 `CFFEX_SETTLEMENT_FETCH_LEASE_RELEASE_FAILED` 携带完整 durable prefix；cancellation 会等同一 shielded Store 或 lease-release task 返回，只要已有 durable prefix 就以专用 cancellation 错误携带它，release 失败作为 cause，Store 失败时不伪造 prefix。它不是原子批发布、进程崩溃恢复或自动恢复的证据。

真实验收须在可销毁、已授权的验收库中完成：审核 AkShare 或替代来源的访问条款、HTTPS/证书验证和限流；导入精确 CFFEX contract identity 与日历；验证 source registry、purpose、lease、全量 receipt digest、transport evidence、quarantine 和每个 publication；强制制造第二 target 写入/发布失败和已 durable publish 但尚未返回的 cancellation，并记录 prefix 的幂等对账或重试；随后用 `local_only` 对每个已发布 target 复读。完成 MySQL/PostgreSQL、调度身份、持久 collection journal 与崩溃恢复演练前，当前状态为 `NOT_RUN` / `NO-GO`，不得启用公开 route 或将结果用作 strict research/PIT 证据。


## 9. 迭代 196 整合闸门

迭代 196 已冻结并作为本候选的基线。迁移图以 `20260909_ai_research_market_data_merge` 显式合并 196 研究审批 head 和 197 数据中台 head，随后依次追加 `20260909_market_data_research_bindings`、`20260909_market_data_research_binding_consumers` 与 `20260910_market_data_shared_source_payloads`。本地 `alembic heads` 已证明唯一 head；它不能替代可恢复 MySQL/PostgreSQL 副本或真实页面环境。

| 整合闸门 | 通过条件 | 当前状态 |
| --- | --- | --- |
| IG-196-01：接口冻结 | 196 的研究、策略、回测输入输出与数据工件 schema 已冻结，并有冻结收据。 | `PASS`（集成基线） |
| IG-196-02：迁移单头 | 196 与 197 的 Alembic 链已合并，`alembic heads` 恰一个 head，隔离升级演练通过。 | `PASS`（L-197-21：当前 head 为 `20260910_market_data_shared_source_payloads`；MySQL/PostgreSQL 仍 `NOT_RUN`） |
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
- [ ] 所有已定义的 AC-197 条目（当前至 AC-197-030）均有对应证据；开发回归、候选验收和真实验证的边界清楚可查。
- [ ] AC-197-029/030 的预捕获批次与共享原始载荷边界已经按记录执行；在公开 `stock.valuation` 开通前，真实来源、日线 calendar、数据库、页面和策略闸门均有独立证据。
- [ ] 七类资产和当前页面已支持数据类型都有经过验证的本地命中/受控补齐，或稳定的明确不支持/未配置状态。
- [ ] 真实 AkShare/OpenBB 验证、数据许可、来源策略登记、OpenBB 原始载荷 hash、完整动态扩展导入闭包、不可变镜像、AGPL-3.0-only 许可证与独立 service account/container/出网审计完成，或未启用对应在线路由。
- [ ] 每个已启用频率都有审核后的显式 calendar grid、连续 calendar segment 和导入锁证据；MySQL/PostgreSQL 候选迁移、每连接 UTC/PIT A/B publication 与恢复演练、`utf8mb4_bin`/`C` 精确身份列审计和单 head 检查完成。
- [ ] 实际部署已二选一：要么限制 v2 市场数据请求到一个经验证的 Web worker 并记录容量/回退边界，要么已完成多 worker/多进程的数据库 lease、接管和并发调用计数验收；不得把同进程 singleflight 表述为全局去重。
- [ ] IG-196-01 至 IG-196-05 均具备对应证据，并完成页面端到端灰度证据。
- [ ] AO-09 已使用经审查的 `iter196-market-data-baseline-v1` 冻结基线生成并验证范围清单；清单仍仅作为集成输入，不能单独开启策略页生产读取。
- [ ] 开关、告警、审计指标和回退程序经过演练；无凭据或敏感原始载荷进入测试输出、日志或文档。

在上述任一项未满足时，最终签收状态为 **`NOT_ACCEPTED`**；可继续保留为当前 `dev` 上的实现/验证候选，但不得表述为生产可用的数据中台。
