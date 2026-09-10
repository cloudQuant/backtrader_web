# 迭代 197：本地优先市场数据中台

本迭代把行情页面和策略研究所需的市场数据收敛到一条可追溯的读取链路：先读取规范化本地数据；只有本地数据缺失、字段不全或覆盖证据不足时，才按受控策略调用 AkShare 或隔离的 OpenBB 运行器；所有成功获取的结果都以原始来源回执和不可变观测修订写回本地库。

## 文档索引

- [需求文档](REQUIREMENTS.md)：范围、用户故事、行为边界和验收口径。
- [设计文档](DESIGN.md)：数据模型、读取/写入流程、接口、迁移和运维设计。
- [验收文档](ACCEPTANCE.md)：自动化证据、待验证外部依赖和迭代 196 的整合闸门。
- [范围清单闸门](SCOPE_MANIFEST.md)：从 21 个家族合同和当前 UI/API 输入生成可复核清单；当前候选已按迭代 196 冻结收据重新生成并验证范围产物。它不覆盖私有估值 collector、shared payload/ref 迁移或完整回执重建，这些另有存储与迁移回归。
- [数据产品扩展计划](PRODUCT_EXPANSION_PLAN.md)：21 个页面家族的实际能力台账，以及 11 个单记录和 4 个多记录产品的后续模型、来源与验收要求。
- [并行设计基线整合记录](DOCUMENT_INTEGRATION_20260909.md)：保留独立设计工作区的同名文档基线及当前实现候选文档的对应关系。
- [A 股历史日线遗留表导入边界](LEGACY_STOCK_DAILY_IMPORT_GUARD.md)：`STOCK_ZH_A_HIST` 的 source-batch/import-scope/read-authorization、逐 target write-permit、逐 bar 唯一 revision/source binding、publication 不早于 Store local receipt、Store v2 来源时间封存、v1 `source_available_at=None` 拒绝、source/local availability 与 quarantine 证据链，以及候选本地证据和 `NO-GO` 启用条件。

当前实现已为 11 个 B1 单记录家族建立惰性的逻辑数据集目录、精确 family-shape 白名单和合同驱动的页面状态。其中 `stock.liquidity`、`fund.liquidity`、`fund.nav` 和 `fx.range` 已完成候选代码开通：它们具有各自的 `ready` family contract、精确来源策略和页面显式选择路径。`fund.nav` 只覆盖 CN-SSE/CN-SZSE ETF 的日线净值，字段为 `nav`、`cumulative_nav`、`daily_growth_rate`，语义固定为 `source_reported + nav + CNY + fund_share`。它还要求 frozen identity 同时声明 `product_type=ETF` 和 `fund_identity_kind=LISTING`；source policy、legacy compatibility bridge 和 AkShare adapter 均在 provider I/O 前复核该条件。其余七个 B1 家族仍为 `unconfigured`。这只表示代码合同与离线回归已具备，不能表示所有产品已经通过真实 provider、数据库或页面灰度验收。已执行的 `stock.liquidity` 真实子用例返回零 response/normalized rows，状态为 `FAIL`；其它实际启用 AkShare 路线仍为 `NOT_RUN`。

当 `local_first` 收到来源回执但 coverage 仍不完整时，行情页会显示“已记录回执；本地覆盖不足”的非成功状态，不能标为“已获取并入库”或完整本地缓存。该状态同样不触发 legacy price/K 线对 NAV 的替代展示。

`stock.valuation` 仍是公开 API 的 `unconfigured` family，公开合同固定为 `market.valuation / reference_series / 1d`，没有 route、source policy、freshness 或页面入口。已落地的内部候选是私有逻辑数据集 `market.stock_valuation_captured_snapshot / valuation_snapshot / snapshot`，只接受受控 scheduler 或测试夹具**已经捕获**的 AkShare `stock_zh_a_spot_em` 宽表；它不发起 fetch/HTTP，不注册 request-time adapter、public family 或 API。每个 target 必须冻结精确 CN-SSE/CN-SZSE listing identity，并使用精确 UTC `captured_at` 及仅用于选择该记录的 `[captured_at, captured_at + 1µs)` 窗口。宽表没有可信逐行来源时间时，`event_at` 明确是 `collector_observed` 的采集瞬时证据，`source_event_time` 和 `source_as_of` 均为 `null`；它绝不能变成交易所时间、日频事实或公开 `as_of`。批次封装固定校验 provider、endpoint、空 request shape、collector version、source revision、captured_at、time basis 与自排除 SHA-256。已知 target 的 identity、重复或字段问题整批失败关闭；未知但结构有效的代码只进入 quarantine，不能生成 canonical series。任何授权或写入之前均检查最多 16 个 target、完整来源批次最多 2 MiB、完整 target receipt 最多 Store 的 10 MiB；超限整批零写入。构造时递归冻结原始 payload，避免外部嵌套引用在验证前改写证据。对该固定宽表段，Store 将规范化 JSON 的 UTF-8 字节按 SHA-256 仅存入一条 `md_source_payloads`，并以 `md_source_snapshot_payload_refs` 把每个 target 的不可变 source snapshot 指向它；不同字节不能共用该行。审计时先从 child ref 取得 `content_sha256`，核验 BLOB 的格式、字节数和 SHA-256 与 ref/manifest descriptor 一致，再把 JSON 解码的 BLOB 放回 manifest `receipt_payload.source_batch`，规范化后的完整 DTO 必须匹配 target snapshot 的 `payload_sha256`。`MdPublication` 始终只绑定 target source snapshot，shared blob 没有公开读取路由或独立 publication。全批校验后仍按 target 独立 publication，后续失败必须报告 durable prefix；只有已发布 target 才可由 Store `local_only` 复读。本地回归只证明离线 SQLite fixture 边界，不能构成真实来源、日线 calendar coverage、`/data/market`、`/investment/strategies`、严格 PIT 或发布验收；`stock.valuation` 保持 `NOT_CONFIGURED`。

> 当前候选仍处于实现与离线验证阶段，不能视为发布验收通过。OpenBB runtime permit matrix 仍为空；fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` 的 `openbb-yfinance 1.6.3.post1` 只是一份待封装的运行构件候选，不安装到主应用，也不注册 route 或 permit。该候选仅定义 UTC 日对齐、最长 3650 天的 `1d` 窗口，并把 OpenBB 的包含式日终转换为 yfinance 的排他 `end`；在完成隔离动态扩展导入闭包、镜像、AGPL-3.0-only 许可证和出网审计前，任何正常请求仍在导入前拒绝。没有执行 OpenBB/yfinance 真实网络调用。跨 MySQL/PostgreSQL 的 PIT 验证、OpenBB 的操作系统级隔离、真实 provider 回执和浏览器灰度仍保留为 `NOT_RUN` 或 `BLOCKED`，具体证据边界见 [验收文档](ACCEPTANCE.md)。


`futures.settlement` 仍是公开 API 中的 `unconfigured` family。新增的 CFFEX 日结采集器只是默认不联网的内部候选：它冻结精确合约、UTC 日窗、`unadjusted/settle/CNY/contract` 语义、来源策略和当前 registry/source authorization，再验证整份回执。reviewed source registry 当前为空，collector 只能从静态 descriptor ID 构造 source；未来 descriptor 必须固定 provider/revision/endpoint、HTTPS origin、certificate policy 与 pin digest，并把其 digest 带入 lease/receipt。当前环境的 AkShare `futures_hist_daily_cffex` 实现使用明文 HTTP，因此 `AkShareCffexSettlementSource` 会在导入 AkShare 或解析 endpoint 前以 `CFFEX_SETTLEMENT_SOURCE_TRANSPORT_UNAPPROVED` 硬拒绝；未来只能由经 HTTPS/证书审计的独立 source 接入。回执的嵌套 rows 含 credential-shaped key 时会在 Store 前拒绝且不回显。现有存储原语按合约顺序发布，因此普通后续失败会明确返回 `CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED` 及已发布前缀；若所有 target 已 durable 但最终 feed lease 无法释放，采集器会以 `CFFEX_SETTLEMENT_FETCH_LEASE_RELEASE_FAILED` 和精确前缀拒绝成功报告；取消时正在持久化或释放 feed lease 的 task 会先完成同一临界区，再以 `CancelledError` 子类报告已返回的精确前缀，即使 release task 自身失败也不会隐去已 durable 的合约。真实传输、调度、日历、取消恢复账本和生产数据库验收仍为 `NOT_RUN`。

## 迭代边界

迭代 196 已以候选 `3ebe7717a0bfe7ebf1cde2dfc501d6842034c253` 固化为集成基线；该候选是合并提交 `fec74728ad4469ae6481b134323a6dd7d1401d32` 的第二父。原冻结收据中的完整 SHA 笔误及不可变更正链见 [2026-09-10 候选冻结收据更正](../迭代196-改进优化ai生成策略流程/CANDIDATE_FREEZE_CORRECTION_20260910.md)。197 的独立数据中台链已由显式 Alembic merge revision `20260909_ai_research_market_data_merge` 接入，后续依次追加 `20260909_market_data_research_bindings`、`20260909_market_data_research_binding_consumers`、`20260910_market_data_shared_source_payloads`、`20260910_market_data_capability_ledger` 和 `20260911_market_data_deferred_publications`；capability ledger 不会 seed 活动记录，release-hold 迁移也不会发布任何 receipt，因此升级不能启用任何 route。策略页桥接仍默认关闭；只有服务端重新解析合同、当前权限和严格本地 PIT 视图，生成并在任务创建与子进程启动前复核不可变 CSV 绑定后才可进入回测。真实 MySQL/PostgreSQL、提供方和页面灰度验收仍是单独闸门。

## 核心约束

- 覆盖现有页面支持的全部资产类型：股票、期货、债券、基金、期权、外汇、加密资产。
- 不使用旧 `MarketInstrumentService` 的样例、附近合约或模糊代码回退。
- 不以物理 AkShare 表名作为数据集身份；读取和写入只通过逻辑数据集、主数据版本和来源策略确定。
- 研究与回测使用严格一致性和知识截止点，读取 `available_at <= knowledge_cutoff` 的数据。
- 策略研究桥接只接收 `market_data_asset_type` 作为客户端意图；服务端重新解析精确 contract 与权限，以 `local_only + backtest + strict` 查询生成受控根目录中的不可变 CSV。策略/工作区只能携带绑定 ID、哈希、签名和 intent；服务器侧 scope/consumer receipt 精确绑定 research workspace/unit，运行前以新事务重放当前授权与来源证据并核对撤销、身份、窗口、路径和字节哈希。公共回测 API 不接受 `runtime_dir`，只有私有 workspace preflight 可取得确定性运行目录。任何复制、篡改或交易工作区复用均失败关闭。
- `research_cache_fill` 只表示用户明确请求的当前数据缓存补齐：它只能走 `local_first + display`、不得携带 PIT 截止点或分页游标、须保留研究用途的来源授权，并且只写中台 receipt/事实表。它不是迭代 196 的研究、回测或审批工件。
- 对需要按事件判断完整性的 `bars` 请求，覆盖事件必须来自经审核导入的 `(market, data_kind, frequency, event timestamp)` 显式网格；日线、周线、月线和任何分钟粒度各自有独立网格，不从交易日、周末规则或另一粒度推断。
- 同一事件读取“满足本次字段集、质量门槛和截止点的最新修订”；较新的窄字段修订不得遮蔽仍可满足宽字段请求的旧修订，也不得把不同修订的字段拼接成未经来源证明的行。
- 相同 `local_first` 缺口在同一 Web 进程内由 singleflight 合并，并由 `md_fetch_leases` 的 owner/fence/expiry 协议跨 worker 协调；事实和 publication 都受 fence guard 保护。该候选实现仍未替代真实多 worker、多方言、时钟和故障接管验收，不能据此宣称全局去重已上线。
- OpenBB 扩展只在受控子进程运行；FastAPI 进程不导入 OpenBB 扩展代码。运行器返回有上限的预规范化原始记录封套及 SHA-256，父进程复算哈希后才接受回执。当前没有活动 permit 或 route；`openbb-yfinance 1.6.3.post1` fork 候选只定义 `1d`、UTC 日对齐、最长 3650 天的窗口和包含式 OpenBB 日终到排他 yfinance `end` 的转换。未来 permit 的 route ID、family、provider、资产/市场、kind/频率、四个语义轴和 server-owned endpoint 全部进入回显 DTO，并由 runner 逐项核验后才可分发。
- 受控环境变量与工作目录只能缩小子进程继承面，不能代替操作系统隔离。`OPENBB_RUNNER_HOME` 和 `OPENBB_RUNNER_WORKDIR` 必须由运维显式提供为独立、绝对且已存在的目录；二者不能回退到临时目录、主应用 HOME 或工作树。生产 OpenBB 必须运行在独立 service account 或容器中，且不挂载主应用工作树、数据库凭据或其他应用密钥。
- 外部数据许可、来源策略和原始回执必须可审计；代码接入不等于数据商用授权。
- 每次 v2 读取都重新检查 `data:read` 与当前来源 registry；旧回执或旧 cursor 不授予永久读取权。当前注册流程不自动赋予该角色，灰度前须走独立 RBAC provisioning。
