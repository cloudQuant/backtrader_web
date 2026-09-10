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

公开 DTO 识别 `bars`、`quote_snapshot`、`option_chain`、`position_report` 和 `reference_series`，但“被识别”不等于已经可以读取。当前候选有十个 `ready` 家族：六个 `*.realtime` 的 `market.bars` 家族（股票、期货、债券、基金、期权精确合约、外汇），以及四个候选 B1 产品：`stock.liquidity`、`fund.liquidity`、`fund.nav`（`market.fund_nav + reference_series + 1d`）和 `fx.range` 的完整 OHLC 日线产品。这四个产品只有在页面明确选择同一 family、服务端签发精确 contract 且来源策略匹配时才可执行；它们不改变默认 realtime 家族，也不扩展策略页的严格 bars/PIT 预检。`fund.nav` 还只接受冻结主数据同时为 `product_type=ETF` 和 `fund_identity_kind=LISTING` 的沪深挂牌基金。其余页面数据家族保持明确的 `unconfigured` 状态。尤其是期权链、风险曲面、持仓/库存报告和快照尚未具备同一 snapshot/report date 多行的安全事实身份、覆盖或分页模型，不能作为已支持能力启用。

在这些多记录产品具有稳定的维度/record key、修订唯一性与读取/分页/provenance 语义、slice/report 完整性规划器，以及同一时间点多行的端到端回归以前，它们只能返回明确机器码，不能通过变更标的、频率或来源来伪造结果。

### 2.2 页面与服务边界

- 两页先读取经过 `data:read` 授权的 `GET /api/v1/data/market-data/capabilities`。它只返回服务端推导的有效能力，不返回 provider、密钥或原始部署变量。浏览器 build 环境变量不得启用、关闭或遮蔽 v2。
- `/data/market` 仅在 `query_v2_enabled=true` 时进入 contract/family bundle/事实查询；它会探测服务端 family bundle，旧服务不存在该控制面时才按受限兼容错误回到无 bundle 的 v2 contract。每次 lookup 必须在首个异步 capability/bundle/contract 调用前冻结 asset、symbol、market、period、时间窗、family 和请求序号；异步返回后若当前选择或序号已变化，必须直接丢弃，不得以新表单值触发 v2、legacy 或在线写回。能力接口不可用、格式无效或显式关闭时，只保留旧的本地兼容读取，不能发起 v2 或在线刷新。
- `/investment/strategies` 最终把策略研究与回测请求绑定到已解析的 canonical identity、数据集、来源策略、数据版本和工件指纹。其 197 strict sidecar 只有 `query_v2_enabled=true` 与 `research_backtest_bridge_enabled=true` 时才发送最小的 `market_data_asset_type` 客户端意图并进行 v2 严格本地预检；在任何 mandate 确认或 capability 请求开始前，前端必须捕获完整 request、mandate payload/match basis 和 `symbol`，后续异步步骤只能从该快照派生 `market_data_asset_type` 与最终 payload，不能读取期间可变的时间窗、质量门槛或表单状态。严格 bars family 由服务端映射：`stock`、`futures`、`bond`、`fund`、`option`、`fx` 使用各自的 `*.realtime` bars family，`crypto` 只能使用 `crypto.range`；`crypto.realtime` 的 quote snapshot 绝不能被改写为 bars。若映射 family 未配置或不支持请求周期，前端显示明确未配置状态，服务端必须在 contract、query/provider 和工件写入前以稳定 binding error 拒绝。该意图不是 canonical identity 或 binding 证据；服务端必须验证并重建其余绑定。否则保持迭代 196 的兼容预检，不能伪造 197 provenance。
- 用户单独触发“补齐本地缓存”才可请求 `purpose=research_cache_fill`，并且有效能力必须同时满足 `query_v2_enabled && online_fetch_enabled && research_cache_fill_enabled`；它**不**依赖 `research_backtest_bridge_enabled`。输入去抖、普通按钮预检和补齐成功后针对同一冻结预检快照的严格本地 v2 复读都使用 `local_only + research + strict`，不得自动联网或写入；即使 bridge 关闭，该复读也只报告本地覆盖，缓存填充本身不成为回测工件。
- 旧 `/api/v1/data/market-instruments/*` 保持兼容，直到新页面完成灰度和可观测性验收；但 `market-instruments/lookup?refresh_online=true` 不属于兼容承诺。该参数在读取遗留仓库、调用 AkShare 或写入任何数据前以 `MARKET_DATA_LEGACY_ONLINE_REFRESH_DISABLED` 拒绝，防止绕过 v2 的精确身份、授权、租约、来源回执、持久化与本地复读边界。遗留 lookup 只可读取本地数据；在线补齐只能进入 v2 `local_first` / `refresh`。
- 旧 `/api/v1/data/kline` 已保留既有响应形状，并改由受治理的 legacy K 线 bridge 执行：它先强制 `data:read`，再以服务端专有 contract 进入 v2 `local_first`，只在允许的缺口路径持久化补齐，最后以 `local_only` 重读投影。handler 和 bridge 不得直接 import/call AkShare、`MarketInstrumentService` 或遗留专表；AkShare 只可经已绑定的 v2 provider route 使用。该实现不等于真实来源、数据库、浏览器或生产验收，相关证据仍按 AC-197-031 保持 `NOT_RUN` / `NO-GO`。
- 迭代 196 已冻结，但策略页桥接仍默认关闭，直到独立的真实数据、浏览器和部署验收完成。`research_cache_fill` 的中台 receipt 不得写入、替代或批准不稳定的 `data_config`、CSV 回退、研究 run、holdout、回测或审批工件。

## 3. 用户故事与功能需求

### FR-01 精确请求

作为用户或内部调用方，我必须以 canonical ID，或完整的 `(asset_type, symbol, market)` 三元组请求数据。系统拒绝仅传代码、同时传两种选择器、大小写近似匹配、别名猜测和空字符串。

`canonical_id` 与三元组字段是协议标识符，不采用数据库默认的人类语言排序。权威 `asset_instruments.canonical_id` 与规范化投影/lookup 的身份字段在 SQLite 使用 `BINARY`、MySQL 使用 `utf8mb4_bin`、PostgreSQL 使用 `C` 排序规则；遗留 bridge 在查询 lookup key 后仍逐字符复核 lookup 行和已发布冻结 identity 的 asset type/symbol，因而未迁移或损坏的大小写不敏感库也必须失败关闭。MySQL/PostgreSQL 启用 v2 前必须完成 `20260909_market_data_exact_identity_collation` 及当前独立链 successor `20260909_market_data_constraint_name_portability`，并完成真实方言回归，不能仅以 SQLite 通过作为排序规则证据。

请求指定：逻辑数据集、数据种类、半开时间区间 `[start, end)`、字段集、频率、复权/价格口径、币种、单位、来源策略、一致性级别、用途、知识截止点和模式。公共 DTO 频率只能是明确的 `5min`、`30min`、`1h`、`1d`、`1w`、`1mo`。这只描述通用合同可表达的频率，不构成 OpenBB 授权：当前 OpenBB yfinance 构件候选只允许 `1d`，并要求整个 `[start,end)` 按 UTC 日边界对齐且不超过 3650 天；`1w`、`1mo`、分钟或任何非日对齐窗口都不得借该候选进入 runner。

所有**公共** v2 请求都必须携带服务端签发、版本匹配且对公共入口可见、状态为 `ready` 的 `family_id` / `family_contract_version`，包括 `bars`。公共 HTTP DTO 将二者设为必填，缺失字段会在目录、主数据、日历、事实或 provider I/O 前以 FastAPI/Pydantic 的 HTTP 422 拒绝；仅内部编排 DTO 可暂存未绑定请求，若它被送入默认 resolver，仍返回稳定码 `DATA_FAMILY_BINDING_REQUIRED`。调用方显式给出 family 时，`query-contract` 只为该精确、公共可选 family 签发 binding；遗留页面的无 family 输入形状则只能推导精确的 `<asset_type>.realtime`，绝不签发通用 `bars` 模板。若所请求 family 尚未配置，返回 `DATA_FAMILY_UNCONFIGURED`。专有 `stock.kline_legacy / market-data-kline-v1` 不属于 public bundle，`POST /api/v1/data/queries` 和 `query-contract` 均不得选择或签发它；只有 `/api/v1/data/kline` 的服务端 bridge 可解析并使用该 pair。遗留 lookup 兼容桥只有在响应同时给出精确请求 `symbol`、同一 contract canonical ID 和一致 family binding 时才可发起 v2 查询；三者任何一项缺失或逐字符不等（含大小写）都必须失败关闭。已获得服务端 v2 能力的页面必须探测并校验 bundle；只有服务器不存在该 endpoint 的已定义兼容错误才允许无 bundle contract 路径。

四个候选 B1 family 还将 `adjustment`、`price_basis`、`currency` 和 `unit` 纳入精确 binding。调用方必须显式传输四个轴；`null` 是经过签发的确定值而不是通配符，因此 `fx.range` 的 `currency=null`、`unit=null` 也不得在 JSON 序列化时丢失。省略或修改任一轴必须在 provider I/O 前返回 `DATA_FAMILY_QUERY_CONTRACT_MISMATCH`，不能由适配器默认值或相近产品合同代替。`fund.nav` 额外把冻结主数据的 `product_type=ETF` 与 `fund_identity_kind=LISTING` 纳入精确匹配；来源策略、遗留兼容桥和 AkShare 适配器都必须在 provider I/O 前拒绝缺失身份、LOF、REIT、其他产品类型或非 `LISTING` 身份，且 AkShare 适配器以 `AKSHARE_PRODUCT_IDENTITY_UNSUPPORTED` 失败关闭。它们不得由代码前缀、名称或相近 ETF 产品推断或补全身份。

### FR-01A 遗留 K 线的受治理兼容桥

`/api/v1/data/kline` 保留 `symbol`、`count`、`kline.{dates,ohlc,volumes}` 与 `records` 的既有 JSON 形状，但取得和投影数据已经改为受治理的 v2 闭环。为避免把 `stock.realtime` 的仅 `close` contract 静默升级为 OHLCV，候选实现新增 server-owned、非 public-bundle 的 `stock.kline_legacy` family，并仅为其登记 `family_contract_version=market-data-kline-v1`；不得原地扩大已有 `stock.realtime` 的字段承诺，也不得让客户端在 `/queries` 或 `query-contract` 中自行选择该 family。

`MarketDataFamilyContractVersion` 与 registry 已从单一全局版本比较收紧为 server-registry 约束的 `(family_id, family_contract_version)` pair：永久保留 `{stock.realtime: market-data-family-v1}`，且仅允许 `{stock.kline_legacy: market-data-kline-v1}` 使用 K 线版本。`query-bundle` 只列出 public-visible family，`query-contract` 只可为 public-visible registry family 签发正确 pair；不得接受自由字符串、客户端版本选择或把 `market-data-kline-v1` 用于其他 family。既有 v1 token、contract 和 binding 不转换、不重签为新 pair、也不放宽其比较；任一错配必须在控制面、事实、provider I/O 前以 HTTP 503 失败关闭。

本 bridge 仅适用于 CN stock legacy 参数形状。`start_date` 和 `end_date` 必须是 `Asia/Shanghai` 的 ISO `YYYY-MM-DD` 日期标签，并先验证 `start_date <= end_date`，再转换为 UTC 半开窗口：`daily` 映射 `1d`，为 `[start@00:00 Asia/Shanghai, (end+1 calendar day)@00:00 Asia/Shanghai)`；`weekly` 映射 `1w`，要求 start 为周一、end 为周日，且为 `[start@00:00 Asia/Shanghai, (end+1 calendar day)@00:00 Asia/Shanghai)` 的完整周窗口；`monthly` 映射 `1mo`，要求 start 为月初、end 为该月最后一日，且为 `[start@00:00 Asia/Shanghai, (end 所在月的下月 1 日)@00:00 Asia/Shanghai)` 的完整月窗口。daily 最多 366 个日历日、weekly 最多 260 个完整周、monthly 最多 120 个完整月；超过、错位、反向或无法解析的请求均为 HTTP 422。该 endpoint 不支持分页：首请求必须无 cursor，任何底层 cursor、部分页或无法在一页内覆盖上述 server-owned window 的结果均为 HTTP 503。

该 family 的每一份已签发 contract 至少精确绑定 canonical identity、`market.bars`、`bars`、由 `daily/weekly/monthly` 一一映射的频率、`adjustment=qfq`、价格口径、币种、单位、来源策略、family/version，及不可降级的 `open`、`high`、`low`、`close`、`volume` 字段。为保持 legacy `records[].change` 的语义，contract 还必须显式要求经过验证的 `change_pct`；不得因字段缺失而填入 `0`、从相邻 bar 推算，或把 `amount`、复权前后价格混入该投影。

legacy projection 是一个完整性断言，不是对 v2 行的格式转换：在持久化后的 v2 `local_only` reread 中，coverage 必须为 `complete`、`expected_event_keys == accepted_event_keys`、没有 missing key 或 gap，所有 accepted event 均在 sealed window 内；随后先拒绝响应 observation 自身的重复 event key，再按 contract 的规范顺序排序，并与 `coverage.accepted_event_keys` 做逐项精确相等比较。任一缺失、额外、重复、越界或排序后不相等均不得投影。`next_cursor=null` 只能说明当前响应没有续页，不能证明 legacy 窗口未被截断；桥接的首个 v2 请求必须显式无 cursor，且该单次响应覆盖完整 server-owned legacy window。`open`、`high`、`low`、`close`、`volume`、`change_pct` 必须通过同一 field-quality 规则：拒绝布尔值、`NaN`、正负无穷、空/纯空白文本和其他不可用数值，不能依赖 Python/JSON 的隐式转换或因质量问题保留部分行。

投影在存储之后执行，不得为显示精度改写 observation。每个 accepted event 恰好投影一行；其 event timestamp 转为 `Asia/Shanghai` 后生成严格递增、无重复 `YYYY-MM-DD` 的 `dates`，两个 accepted event 不得投影为同一日期。`count == len(records) == len(dates) == len(ohlc) == len(volumes)`，且同一索引上的 `records[i].date == dates[i]`，`records[i]` 的 open/close/low/high/volume 与 `ohlc[i]=[open, close, low, high]`、`volumes[i]` 相同。OHLC 与 `change` 必须按 `ROUND_HALF_UP` 规则投影为 server-owned 的既有两位小数 JSON number，并拒绝 signed zero；`change` 的单位为百分比点，`1.23` 表示 `+1.23%`，不得写成 `0.0123`。`volume` 必须为非负、语义上精确的整数，并处于 server-owned JSON safe-integer 范围 `0..9007199254740991`；不得通过 `int()` 或等效截断把小数、布尔值或超范围值伪造成成交量。任一序列化不变量或 field-quality 违反均为 HTTP 503。

已实现的 bridge 按以下顺序执行，且每一步都由服务端控制：

1. 先构建 current principal 并强制 `data:read`；无权限为 HTTP 403，且不得读取 capability、catalog、identity、calendar、事实或 provider。
2. 读取 effective v2 capability。缺失、关闭、过期或格式无效的 query capability 一律为 HTTP 503；不得回退至直接 AkShare 调用、遗留 warehouse 或 `MarketInstrumentService`。
3. 由服务端将 legacy token 解析为唯一、逐字符匹配的 current、published frozen stock identity，并签发上述 exact `qfq` contract。token 只能精确等于 frozen `display_symbol` 或 `details.exchange_symbol`；两种字段的候选组成同一集合，若命中不同 canonical identity、只命中 pending/历史 revision 或大小写不等，均为 HTTP 503。不能从后缀、市场、代码前缀或邻近标的猜测 identity；provider 请求继续使用被解析 identity 的 frozen display symbol，不能剥离或改写客户端 token。
4. 按本条 `Asia/Shanghai` 参数规范构造 contract 所定义的 UTC 半开窗口，并仅以 `local_first` 进入 v2 query service。daily/weekly/monthly 的标签、边界与 366 日/260 周/120 月 server-owned 上限任一不满足均为 HTTP 422；不能静默改为日线、裁短窗口或把包含式 legacy end 当作排他 end。
5. 本地 coverage 完整时只读已发布的本地 revision；coverage 有缺口时，只有 v2 source policy、online capability、lease 和 provider preflight 全部允许才可补齐。成功结果必须经过 receipt、事务 A/B publication、持久化后 `local_only` 重读和完整 coverage 复核。该 reread 必须同时满足 `coverage=complete`、`expected_event_keys == accepted_event_keys`、无 missing key、无 gap，且无重复 canonical observation event-key 序列与 `coverage.accepted_event_keys` 逐项精确相等，所有 accepted event 均在 sealed window 内；首请求无 cursor、`next_cursor=null` 并在一页覆盖完整 server-owned legacy window。不得把 `next_cursor=null` 单独当成完整性证明。任何 coverage 未完成、日历未知、event-key 缺失/额外/重复、required field 缺失或不通过统一 field-quality、序列化不变量违反、未发布 revision、首请求带 cursor、返回 cursor 或无法在一次 legacy 响应中完整投影的结果一律失败关闭为 HTTP 503，不得截断、拼接或直接返回内存 provider DTO。
6. 最后仅从已重读且通过 event-set、field-quality 和唯一序列化完整性断言的 v2 observations 投影 legacy JSON；`ohlc` 的既有顺序固定为 `[open, close, low, high]`，`change` 保持百分比点的两位小数 JSON number，volume 不可截断。实现不得直接 import/call AkShare、不得调用 `MarketInstrumentService` 作为 local 或 online fallback，也不得读取旧专表来绕过 v2 的授权、来源、quality 或 provenance 规则。

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
2. 保存来源回执、公共查询指纹、一次性 provider request ID、完整 provider DTO 的 SHA-256、有界原始载荷封套或受控引用及其 SHA-256、适配器/端点版本、获取时间和警告；公共查询语义与单次外部调用必须分开保存，不能把二者复用为同一个指纹。对于审核允许的宽表 `source_batch`，系统必须从完整 DTO 自行提取并规范化 JSON UTF-8 字节，按字节 SHA-256 在不可变 shared payload 表去重，再以 source snapshot 的子引用关联；不得信任调用方提交的独立 digest、字节数或第二份原始载荷。审计必须先验证 child ref、manifest descriptor、BLOB 格式/字节数与 BLOB SHA-256 一致，再把 JSON 解码的 BLOB 放回紧凑 receipt 的 `source_batch`，规范化后的完整 DTO 必须匹配 target source snapshot 的 `payload_sha256`。相同 canonical bytes 只能共用一条 payload，不同 bytes 必须新建 payload；publication 和读取授权始终附着 target source snapshot，shared payload 不提供单独的公开查询。OpenBB 运行器须先返回预规范化 records 封套及 SHA-256，父进程复算一致后才接收；
3. 追加不可变观测修订，保存字段哈希、质量判定、可用时间和规范化版本；读取每一事件时选择满足本次字段集和质量门槛的最新可用修订，不能让较新的窄字段修订遮蔽较早但完整的修订，也不能混合不同修订的字段；
4. 重新从本地读取并计算覆盖结果，不直接把网络响应绕过存储层返回。

共享 `source_batch` 的迁移必须仅新增 child evidence 表而不改写已有 source snapshot；它必须精确拒绝 MySQL `BLOB` 或 `LONGBLOB` 代替 `MEDIUMBLOB` 的 schema drift。含任一 immutable payload/ref 的 downgrade 必须失败关闭；PostgreSQL 的空表检查与 DROP 必须在两张 child 表的排他锁内完成，MySQL 必须先完成受控 writer-drain fence。上述真实数据库行为在本候选中仍为 `NOT_RUN`。

失败来源只产生稳定错误码和经截断的运维细节，不泄露凭据、原始异常堆栈或其他用户数据。

### FR-03A 跨 worker 缺口协调

对于需要在线补齐的每个 server-resolved coverage gap，平台必须在调用 provider 前取得 `md_fetch_leases` 中的 durable lease。lease key 由 canonical identity、数据集/主数据版本、产品 family ID/contract version、产品语义、精确 gap、来源策略和当前 access-grant descriptor 的 SHA-256 派生；它不接受客户端 provider 名或进程内对象作为身份。

- owner 在短事务中取得递增 fence token；同一 key 的 follower 不调用 primary 或 fallback provider，而是结束旧读事务并复读本地事实，返回 `FETCH_LEASE_HELD` 之类的可观察状态；
- 如果调用构成 online coverage gap 但没有 durable fetch-lease manager，服务只能返回既有本地状态和 `FETCH_LEASE_MANAGER_UNAVAILABLE`；它不得激活 route、调用 provider 或持久化来源回执。进程内互斥、测试 fake 或空 lease 不能替代生产数据库租约；
- provider I/O 不得处于数据库事务、lease 行锁、用户锁或 registry 锁内；
- owner 在事实事务 A 和 publication 事务 B 都必须以 `lease_key + owner_token + fence_token + 未过期` 条件续约/栅栏检查。任一检查失败时，该 owner 的事实或可见性回执不得提交；
- 事实事务 A 已提交但事务 B 未完成时，来源回执必须保留其 lease generation。通用 pending-publication recovery 一律跳过任何带 lease generation 的 source receipt；只有仍持有 exact owner/fence 的协调发布路径可以发布它。这样即使恢复任务在 owner 到期或被接管后运行，也只保留审计证据并失败关闭，不能让旧事实以更晚 visibility sequence 覆盖新 owner 的结果；
- owner 只能释放自己持有的精确 token。租约行保留其递增 fence，过期接管必须产生更高 token，避免 ABA；
- 当前 AkShare/OpenBB 的调用方等待超时为 30 秒，默认 lease TTL 为 5 分钟。AkShare 的 `asyncio.to_thread` 超时不能杀死其已开始的同步线程，因此 TTL 不是实际上游副作用的硬上界；超时后的跨 worker 零重复 AkShare I/O 必须保持 `NO-GO`，直到改用可终止 runner 或由独立会话持有/心跳租约；
- 数据库租约的代码契约不等于正式多 worker 验收。时钟一致性、真实 MySQL/PostgreSQL、多进程调用计数、故障注入、超时线程和部署拓扑仍须按 E-197-08 完成。

### FR-04 主数据与历史重放

作为严格研究/回测调用方，我需要使用某一已验证主数据版本。`research` 和 `backtest` 必须使用 `strict` 一致性且携带 `knowledge_cutoff`；回测截止点不能晚于请求结束时间。

主数据版本的有效期为半开区间。新版本写入时关闭旧版本的有效期并停用旧的当前索引；旧索引仍保留，支持历史时间点解析。同一市场代码在不同、不重叠的历史合约中复用必须可解析。

### FR-04B 严格研究数据绑定

AI 研究链路只能把客户端提交的最小 `market_data_asset_type` 当作意图；前端必须在任何异步 mandate/capability 步骤前，从完整提交快照中同时固定 request、mandate 匹配输入和 `symbol`，再由该快照推导 marker。它不能在等待期间读取后来变更的时间窗、质量门槛、标的或表单值。服务端必须按当前用户权限验证该意图、以 server-owned strict-bars family mapping 重建精确 `local_only + backtest + strict + knowledge_cutoff` 查询，并在 family 不是 `ready` bars 或不支持周期时于所有 contract/provider/artifact I/O 前拒绝；它只能使用完整、已发布的本地 OHLC 证据，不能因研究或回测未命中而触发 AkShare、OpenBB、样例 CSV、相近标的或其他网络回退。

每个实际 submit/continue 必须直接绑定本次请求获得的服务端 capability 返回值；页面缓存只可用于展示或早期提示，不能授权最终 payload。mandate 必须在 binder、binding artifact、workspace、task、snapshot 或 runner 的任何可观察写入之前校验。标的身份只允许去除首尾空白，不得将 `RB0` 与 `rb0` 这类协议标识做大小写折叠。自动模式的 mandate 只接受服务端规范化的 raw prompt、objective、auto-basis version/digest；客户端的预览文本或 objective 不能成为授权依据，显式 prompt/workflow 的续跑必须新建 explicit mandate。

每个可回测的研究请求必须产生不可变 binding receipt，并保存 canonical identity、主数据/数据集/family/source-policy 版本、PIT/visibility anchor、逐观测 revision 与 source-snapshot 证据、规范化 CSV 字节哈希和 manifest 哈希。binding 首次附着到 research workspace 时写入不可变 scope receipt；仅服务端 AI 编排在创建 unit 后可写入精确 `(binding,user,intent,workspace,unit)` consumer receipt。浏览器、通用 workspace create/batch/update API 和续跑请求都不得创建、复制、替换或降级这三类 receipt。

当有效 bridge 关闭时，任何 `market_data_asset_type`、精确 `market_data_binding` 或 `market_data_binding_*` 字段都必须在同步 workspace 创建之前、以及异步 task state、request snapshot 与 background runner 创建之前以 `MARKET_DATA_BRIDGE_DISABLED` 拒绝。该拒绝不得回落到旧 CSV 或遗留数据链路。

对源 run 或 task snapshot 的续跑，系统必须先递归剥离过期的 `market_data_binding` / `market_data_binding_*`，绝不复用旧 task 的 PIT 或 CSV 工件；若源快照曾带 binding，只能保留唯一 `{market_data_asset_type: string}` 意图并在新 task intent 上重新绑定。`data_config` override 仅可精确替换该单一意图，不能添加 CSV 路径、旧 binding、provider、目录或任意其他字段；历史快照即使缺少有效资产意图也要保留空 marker，以便 bridge 关闭时稳定 503、bridge 开启时由 binder 拒绝，而不能降级为 legacy。该 guard 必须在任何新 task、snapshot、workspace 或 runner 落库前运行。

run/task 续跑来源必须是服务端可验证的不可篡改记录。每条记录使用以服务端密钥域分离的 HMAC 覆盖 schema/kind、owner、实际容器 workspace、task/run ID 和完整可信 payload（包括 prompt/workflow/mandate、显式字段证据、lineage、context、diagnostics/next actions 与 binding 相关数据）；恢复时重新比较容器 workspace 与记录字段。签名缺失、未知版本、密钥轮换、任一字段篡改或从 workspace A 复制到 B 的记录均不得作为 continuation source。公开 workspace create/update 及其嵌套/深合并输入不得写入 `ai_research` 或 `ai_research_*` 保留命名空间；历史 client-writable 记录同样失败关闭。task/run 的每次服务端状态更新必须重新签名。

可信续跑只从该签名来源重建 prompt、mandate、seed strategy、run/workspace lineage 与 LLM continuation context；浏览器 full override 只能改变明确定义的操作参数，不能注入 `continuation_context`、`continue_from_run_id`、`research_workspace_id` 或 `seed_strategy_id`。普通 `/ai-research/run` 和 `/ai-research/tasks` 入口收到这些 continuation 字段时，必须在 mandate、binder、artifact、task、snapshot 或 workspace 写入前拒绝。`request_explicit_fields_persisted=true` 仅在已验签来源中与实际 persisted field 共同构成 blank-auto 证据；legacy 默认空列表不是证据。

每一次实际任务提交、每一次“并发任务已满”后的重试，以及任务进程启动前，系统都必须重读当前 unit，并重放 sealed strict 查询：校验当前 `data:read`、source policy、registry、许可证、purpose、scope、consumer 和撤销 receipt，再逐条比较封存的 revision/source-snapshot evidence。最终短授权事务还必须锁定每个 sealed source snapshot 及其当前 registry，并以当前 principal、资产、市场、用途和许可证重新裁决；任何权限、来源、许可、事实、身份、时间窗、HMAC 或工件变化均失败关闭，并使旧 runtime 失去可执行资格；清理由精确 lease/task owner 在确认自身已退出后进行，不能由并发失败路径删除或覆写新 owner 的目录。公共回测 API 不得接受客户端 `runtime_dir`；只有服务端 workspace-unit 调用可通过私有 trusted-runtime preflight 取得确定性的受控目录。

严格绑定 unit 在任何 preflight 或 runtime 写入前必须以数据库条件更新取得唯一、持久的运行租约。同一 unit 的第二个请求只能返回当前 `queued`/`running` 状态，不能读取绑定、生成目录、创建或调度第二个 task。租约只可在 task 已持久化而尚未调度的私有边界原子提升为该 task ID；取消、preflight 失败、后台轮询和终态写入必须以同一租约或 task ID compare-and-swap，观察超时、未知 task 状态或取消失败不得释放仍可能运行的单元。旧租约失效后不得删除、覆写或回写新租约的 runtime、状态或指标。

绑定 CSV 的运行时读取必须从受控根的预期相对路径按完整 `O_NOFOLLOW` 路径链打开单一文件描述符，在该 descriptor 上验证大小和 SHA-256，并把相同 descriptor 交给 CSV 读取器。验证后重新按路径打开文件、符号链接、路径替换、`directory_path`、环境变量或 provider 参数均不得改变实际读取的 inode。

### FR-04C 纸面运行与实盘交接的服务端证据链

市场数据 strict binding 进入 AI 研究、纸面交易和实盘交接后，研究记录、策略代码、纸面运行时和实盘单元必须形成一条服务端可验证的闭环。普通 workspace、strategy、gateway、simulation、live-trading 和 scheduler API 不能把一个带有 AI 研究保留标记的对象改造成可执行实盘单元，也不能代替研究服务直接启动、停止、删除或重建它。

1. 每个可晋升的策略在生成时冻结服务端签名的策略快照；后续纸面/实盘只读取该快照，而不读取可被修改的研究 workspace unit 或策略模板。快照策略 ID 是受保护的服务端资源：通用 strategy create/update/delete、workspace create/batch/update、优化、simulation 和 live-trading 路由都必须拒绝伪造或复用该 ID。
2. 可供纸面复核的 unit 必须带 HMAC 纸面运行时锚点，锚点精确绑定 owner、research workspace、paper workspace、unit、run、规范化后的运行时配置和物化快照摘要。服务器生成的日期窗口必须在锚点和物化配置两侧使用同一稳定规范化规则；未实际变更配置的二次 freshen/restart 不得使锚点漂移，显式日期仍必须被保留并参与摘要。
3. 纸面指标不是浏览器可写的 `metrics_snapshot`。每次服务端确认的 manager launch 都生成私有 launch ID；用于复核的指标回执以 HMAC 绑定 paper workspace/unit、instance、launch ID 和指标摘要。重启、实例替换、度量变更或回执缺失必须撤销 live-ready 状态，重新收集并重新审批。旧记录可以只读展示，但缺签名、过期、冲突或没有当前纸面回执的记录不得续跑、启动纸面或进入实盘。
4. 实盘交接 unit 另有 HMAC 锚点，绑定源 run 的签名、研究/实盘 workspace、unit 和规范化配置。只有 AI 研究服务的受控 `activate` 可以在最终再次核对当前纸面证据后，为 manager 签发一次性、进程内且不可由 HTTP 伪造的启动能力；通用 run/start/start-all 不能接受此能力。`deactivate` 先持久化停止待确认状态，再以私有能力停止；只有确认进程和订单清理均已结束，才撤销批准并标记为 deactivated。失败或仍在运行时必须保持 pending/failed，不能伪造已撤销。
5. refresh/review 对同一 `run_id` 的替换身份是 `(run_id, 原始已验签 signature)`，而不是刷新后生成的新 signature。这个规则允许合法过期记录被重新签名并持久化，同时拒绝同 run ID 的未签名或冲突签名高优先级伪造记录。历史 live handoff 的停止解析只用于安全停止，必须按其原锚点写回，不能覆盖稍后 run 的 canonical `last_run`，也绝不能恢复旧记录的启动资格。

### FR-04A 策略页当前缓存补齐

`research_cache_fill` 是一个受限的、当前时点缓存用途，供用户明确触发的策略数据预检使用。它必须满足以下契约：

1. 仅允许 `mode=local_first`、`consistency=display`、无 `knowledge_cutoff`、无分页 cursor；任一组合在服务执行、目录、主数据或 provider I/O 前拒绝。
2. 它需要 `RESEARCH`、`RESEARCH_ONLY` 或 `DERIVED_RESEARCH` 的当前来源用途授权，不能借用 `DISPLAY` 许可；成功 receipt 的冻结 authorization provenance 必须明确记录 `purpose=research_cache_fill`。
3. 只有有效服务端能力 `research_cache_fill_enabled=true` 时才允许通过默认 source policy；它要求对应的环境 kill switch 均为真，且当前 append-only capability ledger 中的 rollout 与精确 route 同时具有匹配 descriptor 的 `declared / installed / verified / authorized` 有效记录。环境变量只能收窄 ledger 的 durable 结论，不能单独授予能力；这与 `MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_ENABLED` 无关。浏览器不能开启写路径。`data:read`、当前 registry、精确 route、lease、fence 与事务 A/B 仍照常生效。
4. 回应中存在 provider fetch 或来源回执本身不构成补齐成功。只有持久化后重新本地读取且 `coverage.status=complete` 的响应，才能报告本地重新读取的覆盖、warning、source snapshot 和 revision 证据，并把结果记为“已补齐并持久化”。页面在显示该 receipt 或成功状态前，必须逐项校验响应的 canonical identity、dataset、asset type、主数据版本、data kind、frequency、source policy 与 family/version 均等于同一服务端签发 contract；任何不兼容响应都不得成为补齐成功或严格复读的输入。若 `coverage.status` 不完整，即使已有一个或多个持久化来源回执，也只能显示覆盖不足警告，不能修改 `aiResearchPrecheckResult.passed`、启动研究 run，或成为迭代 196 的 PIT、holdout、回测和审批输入。页面可在 bridge 关闭时继续执行 `local_only + research + strict` 的本地 v2 复读；后续正式研究仍必须由 196 服务端工件链以自己的 strict/PIT 请求重新绑定证据。

### FR-05 数据源

作为运维人员，我可以为逻辑数据集配置批准的来源策略和数据提供方。首批适配器为：

每个 rollout capability 与 source-policy route 都必须由 `md_capability_ledger_entries` 中按 `(capability_id, revision)` 追加的 durable 记录证明其 `declared`、`installed`、`verified`、`authorized` 与有限有效期。记录必须绑定当前 server-owned descriptor 和 evidence 的 SHA-256；缺失、重叠、过期、descriptor 不匹配、任一 lifecycle 位为假或 kill switch 关闭时均 fail closed。迁移不会写入活动记录，公开 API 也没有写入该账本的路径。完整审核 source policy 始终用于本地事实读取；只有由台账算出的 `online_route_ids` 可限制 provider I/O，因此撤销或过期 route 不会让已有、仍获当前来源授权的本地事实失去可重读性。

- **AkShare**：独立、显式的函数路由表；调用在线函数使用线程隔离；不得调用遗留样例回退服务。
- **OpenBB**：独立 JSON 子进程协议；Web 进程不导入 OpenBB 扩展；请求 ID、协议版本、超时、输出大小、返回时间窗、去重、有界预规范化原始 records 封套与 SHA-256 全部校验。`OPENBB_MARKET_DATA_RUNNER` 必须精确解析为“绝对 Python 可执行文件、`-I`、`-S`、绝对 runner 脚本路径”四段，不能有 wrapper、模块模式或额外参数；runner 的每种 CLI 入口均须在读取 permit/artifact manifest、distribution metadata、candidate identity 或动态 OpenBB import 前验证该隔离启动条件。父进程只传递最小环境变量白名单，并要求运维显式提供独立、绝对且已存在的 `OPENBB_RUNNER_HOME` 与 `OPENBB_RUNNER_WORKDIR`；任一变量缺失、非法、指向主进程工作目录、继承主进程 HOME 或落入系统临时根目录时稳定拒绝，不存在临时目录回退。这只能收窄继承环境，不能证明文件系统、身份或 OS 级出网隔离。生产运行器必须由独立 service account 或容器托管，且不能读取应用工作树、主应用数据库凭据或其他应用密钥。

所有七种资产类型在 AkShare 路由表中显式声明。股票、期货、债券、基金和外汇具有已审核的有界历史路由；期权只允许 CFFEX 的 `IO`、`HO`、`MO` 精确合约日线，绝不做主力、期权链或附近合约回退；加密资产在 AkShare 中明确不可用。没有安全、精确、受限时间窗实现的组合必须返回不支持，不能伪装为已有数据。OpenBB 只可补充其明确批准的资产/市场组合，最终可用性仍由本地扩展、来源许可和运行器配置决定。

当前 OpenBB 没有活动 source-policy route、permit 或在线开关。fork `24d06a7657ab9e19d07b5ba4f801394a440287a1` 产出的 `openbb-yfinance 1.6.3.post1` 仅作为构件候选：它在 daily route 同时具有开始日和 OpenBB 包含式结束日时，把该结束日加一天作为传给 yfinance 的排他 `end`，并固定 `period=None`。候选只允许 UTC 日对齐、最长 3650 天的 `1d` 半开窗口；静态构件清单只能固定预期发行版、版本和包内文件哈希，不能生成 route、permit、数据许可或真实网络证据。清单的 `candidate` 状态不是可编辑为启用状态的数据开关：即使全部包文件匹配，正常请求也必须在动态 OpenBB 扩展导入前保持拒绝，直到隔离导入闭包、不可变镜像、AGPL-3.0-only 许可证审查和最小出网策略都完成，并由新的执行认证代码与独立验收共同接受。


### FR-05B CFFEX 日结批采集候选

`futures.settlement` 继续是公开 v2 API 的 `unconfigured` family，不能因存在采集器而由页面、`local_first`、`refresh`、普通 shell 命令或任意 source policy 触发。`scripts/collect_iteration197_cffex_settlement.py` 不带参数时只能输出 `NOT_RUN`，`--live` 也只能输出 `BLOCKED`；未来经批准的调度器必须直接调用内部 `CffexSettlementCollector`，并在调用前提供同一交易日的精确 CFFEX 合约映射及冻结的 `MarketDataSourceAuthorization`。

候选只接受 `futures.settlement + market.settlement + reference_series + 1d`、字段集恰为 `settle`、`previous_settle`、`open_interest` 的 CFFEX 合约日窗，且语义必须精确为 `unadjusted + settle + CNY + contract + market-cffex-settlement-batch-v1`。每个 target 的 asset、venue、family、半开 UTC 日窗和 source authorization 的 asset、market、`ALLOW` 决定及 `purpose` 必须在任何 provider I/O 前一致；活动 provider 以及当前 registry/descriptor 也必须在调用前复核，并在网络返回后写入 receipt 前再次复核。原始回执的顶层字段只能为固定 CFFEX collector request、精确 source route、`cffex-settlement-transport-evidence-v1` 和全量 response rows。source route 必须含 `endpoint`、无 query/credentials/path 的 HTTPS `origin` 与日期参数；transport evidence 必须只含其版本、`https` scheme、相同 origin、`tls_verified=true`、certificate policy 和小写 SHA-256 peer certificate digest，任何缺失、额外或不一致字段都在事实写入前拒绝。该结构仅保留 adapter 的可审计声明，不能替代对 HTTPS/certificate adapter、证书链和出网策略的独立验收。无 `MARKET` 列的 `symbol,date,settle,pre_settle,open_interest` 行只能由该冻结 CFFEX request/route 证明，若行显式给出市场则必须精确为 CFFEX。

当前环境的 AkShare `futures_hist_daily_cffex` 实现使用明文 HTTP。`AkShareCffexSettlementSource` 因此必须在导入 AkShare、解析 endpoint 或发起网络调用前以 `CFFEX_SETTLEMENT_SOURCE_TRANSPORT_UNAPPROVED` 拒绝；不得以 config、普通 shell 或 source policy 绕过。未来启用必须新增经审计的 HTTPS/证书验证 adapter 或隔离 runner，并把 transport evidence 写入 receipt；在此之前没有可调用的 CFFEX 在线 source。

当前 reviewed CFFEX source registry 显式为空。collector 只按静态 registry 的 descriptor ID 构造 source，调用方不能注入 source 实例或自建 descriptor；未来独立变更必须在同一审核变更中登记 factory 和 descriptor，逐项固定 provider ID、source revision、endpoint、canonical HTTPS origin、`pinned-peer-certificate-sha256-v1` policy 与小写 pinned peer-certificate digest。descriptor 的 canonical SHA-256 必须进入 feed lease 与每条 receipt，任何未登记 ID、provider/revision/endpoint/origin/policy/digest 不一致都在 provider I/O 或 Store 写入前拒绝。`response_rows` 及其任意嵌套 mapping/list 不得包含 authorization、token、secret、password、credential、cookie、access/API/private key、bearer 或 headers 等 credential-shaped key；检测到即以稳定码拒绝，既不写 Store，也不得在异常、日志或 receipt 回显 key/value。

采集器在写入任何事实前验证整份批次：日期、合约格式、重复行、三个必要指标及所有已冻结 target 均不可缺失。未知但结构正确的 CFFEX 合约只能留在原始批次封套和 quarantine 列表，不能写入 canonical series。当前 `MarketDataStore.persist_provider_result` 一次只持久化和发布一个 series；因此全量输入验证并不提供跨合约原子发布。普通后续 target 持久化失败时，采集器必须抛出 `CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED` 并携带已返回的已发布 prefix。若所有 target 已 durable 但最终 feed lease 无法释放，collector 不得返回成功报告，必须以 `CFFEX_SETTLEMENT_FETCH_LEASE_RELEASE_FAILED` 和精确 durable prefix 拒绝，以便 scheduler 对账。若 cancellation 命中正在执行的 Store 持久化或 feed-lease release task，collector 必须先等待该同一 task 完成；任一 task 已持久化/释放但尚未将结果交给 collector 时，都必须以 `CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED_CANCELLED` 的 `CancelledError` 子类报告其精确返回 prefix；即使 release task 自身失败，也不得隐去已 durable 的 prefix。若 Store task 自身失败，保持原始 cancellation，不得伪造 prefix。未来 scheduler 仍须以独立可恢复账本处理进程崩溃、未知 Store 结果和跨进程恢复。真实来源、许可、日历、调度身份、生产数据库和恢复演练完成前，该候选保持 `NOT_RUN` / `NO-GO`。

### FR-05A 当前读取授权与许可证快照

每个 v2 查询先从当前认证用户构造 principal、tenant scope 和 entitlement revision。没有 `data:read` 的用户必须在任何市场数据控制面或事实读取前失败关闭；系统不得把旧 cursor、旧回执或“已登录”本身当作读取授权。

`/market-instruments/query-bundle` 与 `/market-instruments/query-contract` 也属于 v2 市场数据控制面：前者返回可执行家族合同，后者读取目录和冻结主数据以生成精确请求模板。二者必须在返回家族、目录或 identity 元数据前执行同一 `data:read` 检查；遗留 `/kline` 和 `/lookup` 的兼容授权语义不因此被暗中改写。

在解析出精确资产、市场和服务器维护的 source policy 后、读取 observation/calendar、计算覆盖或调用 provider 前，系统必须逐一校验每个可用 route 对应的 `AssetDataSourceRegistry`：启用状态、资产类型、许可状态、允许用途、生效窗口、辖区、保留期和再分发策略。已采集的历史事实不自动保留当前读取权；来源停用、用途撤销、许可证过期或用户角色变化后，同一请求和旧分页 cursor 必须被拒绝或只允许仍获授权的来源。

calendar snapshot 也必须声明其 `source_registry_id`、被冻结的治理 provenance 和验证状态；v2 查询只能把来源 ID 位于当前 grant 的 `VERIFIED` calendar 当作 `KNOWN` 覆盖证据。缺失、未验证、已撤权或不在 allow-list 的 calendar 返回 `unknown_calendar`，不得以它驱动网络补齐或声称本地覆盖完整。

一次成功 provider 获取必须把 `MarketDataSourceAuthorization` 冻结在来源回执中，至少包括 registry ID/更新时间、许可和用途、辖区/有效窗口、保留与再分发决策、principal/tenant scope 的不可逆摘要、entitlement revision、允许决定及其 descriptor hash。该记录证明采集时的授权条件，不取代下一次读取时的实时授权检查。

`research_cache_fill` 使用与 `research` 相同的研究用途许可证集合，但它不是 strict/PIT 读取。该用途的默认 source-policy grant 只在有效条件 `query_v2 && online_fetch && cache_fill` 同时成立时登记：若 `query_v2=false`，v2 HTTP 边界首先返回 `MARKET_DATA_QUERY_V2_DISABLED`；若 `query_v2=true` 但 online fetch 或 effective cache-fill 关闭，即使浏览器伪造请求也返回 `MARKET_DATA_RESEARCH_CACHE_FILL_DISABLED`。store 对回执 provenance 再次核验用途、授权集合和当前 registry，不能以 display receipt 伪装为研究缓存。

在线获取的授权线性化点分为两段：网络请求前的 route preflight 决定是否可以发送请求；提供方返回后、写入 receipt 前必须以当前用户角色和来源 registry 做短事务的 current/locking recheck。角色、许可或 registry descriptor 在两者之间变化时，获取结果不得持久化。singleflight follower 在 leader 提交后先结束旧读事务，再重建 principal/access 后本地复读。任何没有 `MarketDataQueryAccess` 的服务调用只能做 local read；它不得触发 provider 获取或把未授权结果写入 v2 事实表。

### FR-06 页面与可用性

行情页需要显示数据来自本地或刚写入的来源、数据集、canonical identity、覆盖状态、警告和更新时间。当前 `/data/market` 在有来源回执但 `coverage.status` 不完整时必须使用 `provider_persisted_incomplete` 警告状态，显示“已记录 N 个来源回执；本地覆盖不足”和“已保存 N 个来源回执，但未形成完整本地可追溯缓存”，不得显示“已获取并入库”或其他成功样式。策略页在用户明确预检后只有在完整本地覆盖下可显示“本地优先”或“已补齐并持久化”的当前缓存状态；自动预检不触网。策略页仍需要在 196 合并后显示被冻结的数据版本/截止点，并拒绝把未验证或不完整的结果当作可回测输入。

在数据目录、主数据索引、日历或来源策略尚未准备好时，已启用的页面 v2 合同探测必须返回稳定状态。为保持既有功能，页面可明确标记为 `legacy_fallback` 后调用原兼容接口，但不得把该结果标成 v2 本地覆盖、来源回执或严格研究证据；也不得以样例、附近代码或模糊标的替代精确请求。普通行情页“查询”采用 `local_first`；`refresh` 必须由明确标记的受控操作触发，不能把常规查询静默变成全窗口在线刷新。

## 4. 非功能需求

- **正确性**：数据库排序规则不能将近似大小写或代码当成精确匹配；所有时间统一 UTC，并在 API 边界要求时区。
- **并发性**：身份版本切换和索引写入使用保存点；失败后外层事务继续提交也不能留下半成品。观测写入只追加，不覆盖旧事实。同进程请求按指纹 singleflight；跨 worker 的 provider 补齐按 durable fetch lease 协调，事实与 publication 分别做 fence 检查。follower 必须在复读前结束可能持有的认证只读事务，避免 MySQL `REPEATABLE READ` 使用提交前快照。候选代码与 SQLite 回归只能证明协议；在真实多 worker、MySQL/PostgreSQL 和故障接管证据完成前，不能把“同一缺口只访问一次网络”列为已验收需求。
- **可审计性**：每一返回行可回溯到数据系列、来源回执、字段哈希、质量策略和可用时间。共享宽表载荷仅经已授权 source snapshot 可达；其内容 hash、格式、字节数和完整 receipt 重建校验必须可审计，且不能形成跨租户或未发布证据的存在性探针。
- **性能**：三元组查询使用物化索引，不扫描整个交易所；直接在线窗口有上限；分页和等待参数不改变数据语义。
- **时间与数据库**：应用边界使用带时区 UTC；MySQL `DATETIME` 不保存时区，因此候选部署必须对每个应用连接验证 UTC session time zone，并在真实 MySQL/PostgreSQL 上完成跨连接的 PIT 写入/读取演练。SQLite 或离线 DDL 不能替代该证据。
- **安全性**：不在源码中写入密钥；OpenBB 运行器命令由运维环境配置；无 shell 拼接执行；原始数据输出受大小限制。环境白名单和受控 `cwd` 不是容器/用户边界，必须由部署账户、不可变镜像、挂载、动态扩展导入闭包、最小出网策略与密钥策略共同保证。候选构件的静态哈希验证不是这些运行时边界的替代品。
- **合规性**：OpenBB、AkShare 和上游提供方的代码许可、访问条款、再分发和商用数据许可必须由来源策略登记；技术接入不自动授予数据使用权。该 OpenBB fork 与拟封装的 `openbb-yfinance 1.6.3.post1` 按 AGPL-3.0-only 处理；在完成对镜像分发、服务部署、源代码提供义务、动态扩展闭包及与本项目组合方式的书面许可证审查前，OpenBB 在线路由为 `NO-GO`。

## 5. 非目标

- 本迭代不替换所有旧 AkShare 数据治理/调度功能。
- 不自动从模糊用户输入创建 canonical identity。
- 不把 OpenBB 或其扩展安装进 FastAPI 运行环境。
- 不因存在 fork `24d06a7657ab9e19d07b5ba4f801394a440287a1`、静态构件清单或离线 mock 测试而安装 `openbb-yfinance 1.6.3.post1`、创建 permit/route 或开启任何 OpenBB/yfinance 网络访问。
- 不把同进程 singleflight 或候选数据库 lease 回归误写成生产级分布式去重；后者仍需要真实多 worker、多方言、时钟与故障接管验收。
- 不因迭代 196 已冻结而自动开启策略研究、回测的生产数据契约；研究绑定和页面灰度仍须通过独立的本地、迁移、提供方和浏览器验收。
- 不将实时经纪商 tick 流与历史规范化观测表混为同一种数据源。
- 不把 `unconfigured` 的期权链、风险曲面、报告或快照家族描述成已具备本地命中、在线补齐或历史重放能力。
