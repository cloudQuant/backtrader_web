# 迭代 197 需求文档

## 1. 目标与问题

当前行情页和部分策略链路直接依赖 AkShare 仓库或实时请求。不同资产类型走不同表和函数，未命中时存在样例或相近标的回退，在线取得的数据也不能稳定复用。这样的行为会让同一页面的结果不可重现，也无法证明回测或研究在某一时间点实际知道什么。

迭代 197 建立一个通用市场数据中台。它吸收 OpenBB 的扩展式数据源和标准化请求思想，同时保留本项目对中国市场、AkShare、可审计来源和多数据库的实际要求。

成功标准是：相同的已批准数据请求在本地覆盖完整时不访问网络；本地缺口才被受控补齐；补齐后的来源、字段、质量、可用时间和有界原始载荷（或其受控引用）及内容哈希都能追溯；严格研究/回测可按知识截止点重放。

## 2. 范围

### 2.1 资产与数据类型

首批逻辑契约覆盖当前两个页面支持的全部资产类型：

| 资产类型 | 首批重点数据 | 默认读取粒度 |
| --- | --- | --- |
| `stock` | OHLCV、估值/成交补充字段 | `1d`，可扩展至分钟 |
| `futures` | OHLCV、结算、持仓量 | `1d`，可扩展至分钟 |
| `bond` | 行情、收益率或参考序列 | `1d` / 快照 |
| `fund` | 净值、ETF 行情、参考序列 | `1d` / 快照 |
| `option` | 合约行情、期权链 | 快照 / 链 |
| `fx` | 汇率行情 | `1d` / 快照 |
| `crypto` | 交易对行情 | `1d` / 分钟 / 快照 |

公开 DTO 识别 `bars`、`quote_snapshot`、`option_chain`、`position_report` 和 `reference_series`，但“被识别”不等于已经可以读取。当前候选有九个 `ready` 家族：六个 `*.realtime` 的 `market.bars` 家族（股票、期货、债券、基金、期权精确合约、外汇），以及 `stock.liquidity`、`fund.liquidity` 两个 `reference_series + 1d` 产品和 `fx.range` 的完整 OHLC 日线产品。后面三个只有在页面明确选择同一 family、服务端签发精确 contract 且来源策略匹配时才可执行；它们不改变默认 realtime 家族，也不扩展策略页的严格 bars/PIT 预检。其余页面数据家族保持明确的 `unconfigured` 状态。尤其是期权链、风险曲面、持仓/库存报告和快照尚未具备同一 snapshot/report date 多行的安全事实身份、覆盖或分页模型，不能作为已支持能力启用。

在这些多记录产品具有稳定的维度/record key、修订唯一性与读取/分页/provenance 语义、slice/report 完整性规划器，以及同一时间点多行的端到端回归以前，它们只能返回明确机器码，不能通过变更标的、频率或来源来伪造结果。

### 2.2 页面与服务边界

- `/data/market` 仅在 `VITE_MARKET_DATA_QUERY_V2_ENABLED=true` 的独立浏览器灰度中使用新查询接口展示历史、快照和来源状态；关闭时不得请求 v2 contract、family bundle 或事实接口。
- `/investment/strategies` 最终把策略研究与回测请求绑定到已解析的 canonical identity、数据集、来源策略、数据版本和工件指纹。其 197 sidecar 还必须同时满足 `VITE_MARKET_DATA_QUERY_V2_ENABLED=true` 和 `VITE_MARKET_DATA_STRATEGY_BRIDGE_ENABLED=true`，否则不得访问任何 v2 控制面或事实接口。
- 在两个浏览器开关均开启的隔离候选中，用户明确触发“策略数据预检”时可额外请求 `purpose=research_cache_fill`；服务端还必须开启 `MARKET_DATA_RESEARCH_CACHE_FILL_ENABLED=true`，否则以稳定禁用码拒绝。输入去抖和非交互预检始终使用 `local_only + research + strict`，不得自动联网或写入。
- 旧 `/api/v1/data/market-instruments/*` 和 `/api/v1/data/kline` 保持兼容，直到新页面完成灰度和可观测性验收。
- 迭代 196 的 AI 研究/信任契约完成前，策略页只保留桥接设计和默认关闭的开关。`research_cache_fill` 的中台 receipt 不得写入、替代或批准不稳定的 `data_config`、CSV 回退、研究 run、holdout、回测或审批工件。

## 3. 用户故事与功能需求

### FR-01 精确请求

作为用户或内部调用方，我必须以 canonical ID，或完整的 `(asset_type, symbol, market)` 三元组请求数据。系统拒绝仅传代码、同时传两种选择器、大小写近似匹配、别名猜测和空字符串。

`canonical_id` 与三元组字段是协议标识符，不采用数据库默认的人类语言排序。权威 `asset_instruments.canonical_id` 与规范化投影/lookup 的身份字段在 SQLite 使用 `BINARY`、MySQL 使用 `utf8mb4_bin`、PostgreSQL 使用 `C` 排序规则；遗留 bridge 在查询 lookup key 后仍逐字符复核 lookup 行和已发布冻结 identity 的 asset type/symbol，因而未迁移或损坏的大小写不敏感库也必须失败关闭。MySQL/PostgreSQL 启用 v2 前必须完成 `20260909_market_data_exact_identity_collation` 迁移与真实方言回归，不能仅以 SQLite 通过作为排序规则证据。

请求指定：逻辑数据集、数据种类、半开时间区间 `[start, end)`、字段集、频率、复权/价格口径、币种、单位、来源策略、一致性级别、用途、知识截止点和模式。频率只能是明确的 `5min`、`30min`、`1h`、`1d`、`1w`、`1mo`。

所有公共 v2 请求都必须携带服务端签发、版本匹配且状态为 `ready` 的 `family_id` / `family_contract_version`，包括 `bars`。公共 HTTP DTO 将二者设为必填，缺失字段会在目录、主数据、日历、事实或 provider I/O 前以 FastAPI/Pydantic 的 HTTP 422 拒绝；仅内部编排 DTO 可暂存未绑定请求，若它被送入默认 resolver，仍返回稳定码 `DATA_FAMILY_BINDING_REQUIRED`。调用方显式给出 family 时，`query-contract` 只为该精确 family 签发 binding；遗留页面的无 family 输入形状则只能推导精确的 `<asset_type>.realtime`，绝不签发通用 `bars` 模板。若所请求 family 尚未配置，返回 `DATA_FAMILY_UNCONFIGURED`。遗留 lookup 兼容桥只有在响应同时给出精确请求 `symbol`、同一 contract canonical ID 和一致 family binding 时才可发起 v2 查询；三者任何一项缺失或逐字符不等（含大小写）都必须失败关闭。页面即使关闭 bundle 子开关也要请求并校验此 binding。

三个候选 B1 family 还将 `adjustment`、`price_basis`、`currency` 和 `unit` 纳入精确 binding。调用方必须显式传输四个轴；`null` 是经过签发的确定值而不是通配符，因此 `fx.range` 的 `currency=null`、`unit=null` 也不得在 JSON 序列化时丢失。省略或修改任一轴必须在 provider I/O 前返回 `DATA_FAMILY_QUERY_CONTRACT_MISMATCH`，不能由适配器默认值或相近产品合同代替。

### FR-02 本地优先读取

作为页面调用方，我选择下列模式之一：

| 模式 | 行为 |
| --- | --- |
| `local_only` | 只返回本地已提交观测与覆盖状态，从不发起网络请求。 |
| `local_first` | 本地覆盖完整时直接返回；缺口或日历证据未知时才请求受控来源。 |
| `refresh` | 即使本地完整也请求最新受控来源，并以新修订追加保存。 |

覆盖完整的含义不是“表中有几行”：系统根据冻结的交易日历、精确事件键、必需字段、质量状态和知识截止点计算。日历缺失时只能报告 `unknown_calendar`，不能声称完整。

对按事件判断完整性的 `bars` 或 `reference_series` 请求，交易日历中的覆盖证据必须显式声明为 `(market, data_kind, frequency, event timestamp)` 网格。首批 calendar-grid 清单在每条交易 session 事实上登记 `coverage: {data_kind, frequency}`，并以 `data_kind:frequency@UTC-event_start` 生成事件键；同一时点的不同数据种类/频率必须用不同 session 事实分别声明。`bars` 的 `1d`、`1w`、`1mo` 和 `5min`、`30min`、`1h` 各自独立；当前已审核的 `reference_series` 仅允许 `1d`，新增频率必须先扩展 importer、family contract 和回归证据。系统不得从某个交易日、另一个数据种类/频率的 session、周末规则、交易所营业时间或相邻记录推断缺失格点。缺少请求维度的明确网格时返回 `unknown_calendar` / `CALENDAR_GRID_UNAVAILABLE`，而不是把该窗口判为无交易或完整。

### FR-03 获取与持久化

作为平台，我在允许在线获取时依次尝试来源策略批准的适配器。每次成功响应必须：

1. 校验请求的精确标的、时间窗、事件唯一性和字段；
2. 保存来源回执、公共查询指纹、一次性 provider request ID、完整 provider DTO 的 SHA-256、有界原始载荷封套或受控引用及其 SHA-256、适配器/端点版本、获取时间和警告；公共查询语义与单次外部调用必须分开保存，不能把二者复用为同一个指纹。OpenBB 运行器须先返回预规范化 records 封套及 SHA-256，父进程复算一致后才接收；
3. 追加不可变观测修订，保存字段哈希、质量判定、可用时间和规范化版本；读取每一事件时选择满足本次字段集和质量门槛的最新可用修订，不能让较新的窄字段修订遮蔽较早但完整的修订，也不能混合不同修订的字段；
4. 重新从本地读取并计算覆盖结果，不直接把网络响应绕过存储层返回。

失败来源只产生稳定错误码和经截断的运维细节，不泄露凭据、原始异常堆栈或其他用户数据。

### FR-03A 跨 worker 缺口协调

对于需要在线补齐的每个 server-resolved coverage gap，平台必须在调用 provider 前取得 `md_fetch_leases` 中的 durable lease。lease key 由 canonical identity、数据集/主数据版本、产品 family ID/contract version、产品语义、精确 gap、来源策略和当前 access-grant descriptor 的 SHA-256 派生；它不接受客户端 provider 名或进程内对象作为身份。

- owner 在短事务中取得递增 fence token；同一 key 的 follower 不调用 primary 或 fallback provider，而是结束旧读事务并复读本地事实，返回 `FETCH_LEASE_HELD` 之类的可观察状态；
- provider I/O 不得处于数据库事务、lease 行锁、用户锁或 registry 锁内；
- owner 在事实事务 A 和 publication 事务 B 都必须以 `lease_key + owner_token + fence_token + 未过期` 条件续约/栅栏检查。任一检查失败时，该 owner 的事实或可见性回执不得提交；
- 事实事务 A 已提交但事务 B 未完成时，来源回执必须保留其 lease generation。通用 pending-publication recovery 一律跳过任何带 lease generation 的 source receipt；只有仍持有 exact owner/fence 的协调发布路径可以发布它。这样即使恢复任务在 owner 到期或被接管后运行，也只保留审计证据并失败关闭，不能让旧事实以更晚 visibility sequence 覆盖新 owner 的结果；
- owner 只能释放自己持有的精确 token。租约行保留其递增 fence，过期接管必须产生更高 token，避免 ABA；
- 当前 AkShare/OpenBB 的调用方等待超时为 30 秒，默认 lease TTL 为 5 分钟。AkShare 的 `asyncio.to_thread` 超时不能杀死其已开始的同步线程，因此 TTL 不是实际上游副作用的硬上界；超时后的跨 worker 零重复 AkShare I/O 必须保持 `NO-GO`，直到改用可终止 runner 或由独立会话持有/心跳租约；
- 数据库租约的代码契约不等于正式多 worker 验收。时钟一致性、真实 MySQL/PostgreSQL、多进程调用计数、故障注入、超时线程和部署拓扑仍须按 E-197-08 完成。

### FR-04 主数据与历史重放

作为严格研究/回测调用方，我需要使用某一已验证主数据版本。`research` 和 `backtest` 必须使用 `strict` 一致性且携带 `knowledge_cutoff`；回测截止点不能晚于请求结束时间。

主数据版本的有效期为半开区间。新版本写入时关闭旧版本的有效期并停用旧的当前索引；旧索引仍保留，支持历史时间点解析。同一市场代码在不同、不重叠的历史合约中复用必须可解析。

### FR-04A 策略页当前缓存补齐

`research_cache_fill` 是一个受限的、当前时点缓存用途，供用户明确触发的策略数据预检使用。它必须满足以下契约：

1. 仅允许 `mode=local_first`、`consistency=display`、无 `knowledge_cutoff`、无分页 cursor；任一组合在服务执行、目录、主数据或 provider I/O 前拒绝。
2. 它需要 `RESEARCH`、`RESEARCH_ONLY` 或 `DERIVED_RESEARCH` 的当前来源用途授权，不能借用 `DISPLAY` 许可；成功 receipt 的冻结 authorization provenance 必须明确记录 `purpose=research_cache_fill`。
3. 只有后端 `MARKET_DATA_RESEARCH_CACHE_FILL_ENABLED=true` 时才允许通过默认 source policy；浏览器开关仅控制体验，不能开启服务端写路径。`MARKET_DATA_ONLINE_FETCH_ENABLED`、`data:read`、当前 registry、精确 route、lease、fence 与事务 A/B 仍照常生效。
4. 成功补齐后响应只能报告本地重新读取的覆盖、warning、source snapshot 和 revision 证据。它不得修改 `aiResearchPrecheckResult.passed`、启动研究 run，或成为迭代 196 的 PIT、holdout、回测和审批输入；后续正式研究仍必须由 196 服务端工件链以自己的 strict/PIT 请求重新绑定证据。

### FR-05 数据源

作为运维人员，我可以为逻辑数据集配置批准的来源策略和数据提供方。首批适配器为：

- **AkShare**：独立、显式的函数路由表；调用在线函数使用线程隔离；不得调用遗留样例回退服务。
- **OpenBB**：独立 JSON 子进程协议；Web 进程不导入 OpenBB 扩展；请求 ID、协议版本、超时、输出大小、返回时间窗、去重、有界预规范化原始 records 封套与 SHA-256 全部校验。父进程只传递最小环境变量白名单，并把运行目录设为 `OPENBB_RUNNER_WORKDIR`（未配置时为系统临时目录）；这不是文件系统或身份隔离的证明。生产运行器必须由独立 service account 或容器托管，且不能读取应用工作树、主应用数据库凭据或其他应用密钥。

所有七种资产类型在 AkShare 路由表中显式声明。股票、期货、债券、基金和外汇具有已审核的有界历史路由；期权只允许 CFFEX 的 `IO`、`HO`、`MO` 精确合约日线，绝不做主力、期权链或附近合约回退；加密资产在 AkShare 中明确不可用。没有安全、精确、受限时间窗实现的组合必须返回不支持，不能伪装为已有数据。OpenBB 只可补充其明确批准的资产/市场组合，最终可用性仍由本地扩展、来源许可和运行器配置决定。

### FR-05A 当前读取授权与许可证快照

每个 v2 查询先从当前认证用户构造 principal、tenant scope 和 entitlement revision。没有 `data:read` 的用户必须在任何市场数据控制面或事实读取前失败关闭；系统不得把旧 cursor、旧回执或“已登录”本身当作读取授权。

`/market-instruments/query-bundle` 与 `/market-instruments/query-contract` 也属于 v2 市场数据控制面：前者返回可执行家族合同，后者读取目录和冻结主数据以生成精确请求模板。二者必须在返回家族、目录或 identity 元数据前执行同一 `data:read` 检查；遗留 `/kline` 和 `/lookup` 的兼容授权语义不因此被暗中改写。

在解析出精确资产、市场和服务器维护的 source policy 后、读取 observation/calendar、计算覆盖或调用 provider 前，系统必须逐一校验每个可用 route 对应的 `AssetDataSourceRegistry`：启用状态、资产类型、许可状态、允许用途、生效窗口、辖区、保留期和再分发策略。已采集的历史事实不自动保留当前读取权；来源停用、用途撤销、许可证过期或用户角色变化后，同一请求和旧分页 cursor 必须被拒绝或只允许仍获授权的来源。

calendar snapshot 也必须声明其 `source_registry_id`、被冻结的治理 provenance 和验证状态；v2 查询只能把来源 ID 位于当前 grant 的 `VERIFIED` calendar 当作 `KNOWN` 覆盖证据。缺失、未验证、已撤权或不在 allow-list 的 calendar 返回 `unknown_calendar`，不得以它驱动网络补齐或声称本地覆盖完整。

一次成功 provider 获取必须把 `MarketDataSourceAuthorization` 冻结在来源回执中，至少包括 registry ID/更新时间、许可和用途、辖区/有效窗口、保留与再分发决策、principal/tenant scope 的不可逆摘要、entitlement revision、允许决定及其 descriptor hash。该记录证明采集时的授权条件，不取代下一次读取时的实时授权检查。

`research_cache_fill` 使用与 `research` 相同的研究用途许可证集合，但它不是 strict/PIT 读取。该用途的默认 source-policy grant 由单独的后端开关控制，关闭时即使浏览器伪造请求也返回 `MARKET_DATA_RESEARCH_CACHE_FILL_DISABLED`；store 对回执 provenance 再次核验用途、授权集合和当前 registry，不能以 display receipt 伪装为研究缓存。

在线获取的授权线性化点分为两段：网络请求前的 route preflight 决定是否可以发送请求；提供方返回后、写入 receipt 前必须以当前用户角色和来源 registry 做短事务的 current/locking recheck。角色、许可或 registry descriptor 在两者之间变化时，获取结果不得持久化。singleflight follower 在 leader 提交后先结束旧读事务，再重建 principal/access 后本地复读。任何没有 `MarketDataQueryAccess` 的服务调用只能做 local read；它不得触发 provider 获取或把未授权结果写入 v2 事实表。

### FR-06 页面与可用性

行情页需要显示数据来自本地或刚写入的来源、数据集、canonical identity、覆盖状态、警告和更新时间。策略页在用户明确预检后可显示“本地优先”或“已补齐并持久化”的当前缓存状态；自动预检不触网。策略页仍需要在 196 合并后显示被冻结的数据版本/截止点，并拒绝把未验证或不完整的结果当作可回测输入。

在数据目录、主数据索引、日历或来源策略尚未准备好时，已启用的页面 v2 合同探测必须返回稳定状态。为保持既有功能，页面可明确标记为 `legacy_fallback` 后调用原兼容接口，但不得把该结果标成 v2 本地覆盖、来源回执或严格研究证据；也不得以样例、附近代码或模糊标的替代精确请求。普通行情页“查询”采用 `local_first`；`refresh` 必须由明确标记的受控操作触发，不能把常规查询静默变成全窗口在线刷新。

## 4. 非功能需求

- **正确性**：数据库排序规则不能将近似大小写或代码当成精确匹配；所有时间统一 UTC，并在 API 边界要求时区。
- **并发性**：身份版本切换和索引写入使用保存点；失败后外层事务继续提交也不能留下半成品。观测写入只追加，不覆盖旧事实。同进程请求按指纹 singleflight；跨 worker 的 provider 补齐按 durable fetch lease 协调，事实与 publication 分别做 fence 检查。follower 必须在复读前结束可能持有的认证只读事务，避免 MySQL `REPEATABLE READ` 使用提交前快照。候选代码与 SQLite 回归只能证明协议；在真实多 worker、MySQL/PostgreSQL 和故障接管证据完成前，不能把“同一缺口只访问一次网络”列为已验收需求。
- **可审计性**：每一返回行可回溯到数据系列、来源回执、字段哈希、质量策略和可用时间。
- **性能**：三元组查询使用物化索引，不扫描整个交易所；直接在线窗口有上限；分页和等待参数不改变数据语义。
- **时间与数据库**：应用边界使用带时区 UTC；MySQL `DATETIME` 不保存时区，因此候选部署必须对每个应用连接验证 UTC session time zone，并在真实 MySQL/PostgreSQL 上完成跨连接的 PIT 写入/读取演练。SQLite 或离线 DDL 不能替代该证据。
- **安全性**：不在源码中写入密钥；OpenBB 运行器命令由运维环境配置；无 shell 拼接执行；原始数据输出受大小限制。环境白名单和受控 `cwd` 不是容器/用户边界，必须由部署账户、容器镜像、挂载与密钥策略共同保证。
- **合规性**：OpenBB、AkShare 和上游提供方的代码许可、访问条款、再分发和商用数据许可必须由来源策略登记；技术接入不自动授予数据使用权。

## 5. 非目标

- 本迭代不替换所有旧 AkShare 数据治理/调度功能。
- 不自动从模糊用户输入创建 canonical identity。
- 不把 OpenBB 或其扩展安装进 FastAPI 运行环境。
- 不把同进程 singleflight 或候选数据库 lease 回归误写成生产级分布式去重；后者仍需要真实多 worker、多方言、时钟与故障接管验收。
- 不在迭代 196 未冻结前改写策略研究、回测的生产数据契约。
- 不将实时经纪商 tick 流与历史规范化观测表混为同一种数据源。
- 不把 `unconfigured` 的期权链、风险曲面、报告或快照家族描述成已具备本地命中、在线补齐或历史重放能力。
