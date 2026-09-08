# 迭代 197 需求文档：本地优先市场数据中台

> 状态：设计冻结候选；本次不开发。
> 依赖：迭代 196 的研究、回测和策略工件契约尚未冻结。

## 1. 背景与目标

当前行情页和部分策略链路主要直接依赖 AkShare 或实时请求。现有市场页初次 lookup 读取本地仓库，但手动 `refresh_online=true` 的在线主分支返回 AkShare payload，未形成可证明的 source snapshot、规范化事实和可见性 seal 持久化闭环；当前 `_store_history_cache()` 又没有已调用的主查询路径。数据身份、来源、口径、可用时间和本地缓存之间因此没有统一的证据链，难以回答“这一条数据来自哪里”“当时是否已知”“为什么这次与上次不同”。现有样例、附近标的或模糊回退也不能用于研究和回测。

迭代 197 设计一个市场数据中台，借鉴 OpenBB 的 provider/extension 边界和标准化请求模型，同时保留本项目对中国市场、AkShare、多数据库、可审计许可和严格回放的要求。

成功定义如下：

1. 对同一已批准请求，本地证据完整时不访问网络。
2. 本地缺口只由服务器批准的、与请求语义完全匹配的来源补齐。
3. 外部结果先形成不可变本地证据和可见性回执，再作为查询结果返回。
4. 研究和回测可以按一个冻结的知识/可见性边界重放，不受后来数据、身份、策略或 provider 配置变化影响。
5. 196 未冻结时，197 不接管策略页的生产读取路径。

## 2. 范围与交付边界

### 2.1 资产和数据类型

首批契约覆盖当前 `/data/market` 与 `/investment/strategies` 已支持的全部资产类型。覆盖表示“有统一的精确请求、存储、治理和明确失败语义”，不表示每个来源立即提供所有真实数据。

| 资产类型 | 当前页面数据族，197 必须逐项登记字段组 | 规范化数据类型与典型粒度 | 首批来源状态要求 |
| --- | --- | --- | --- |
| `stock` | 实时/历史 OHLCV、成交额/换手、估值（总/流通市值、PE、PB）、流动性和资金流。 | `quote_snapshot`、`bars`、`reference_series`；快照和日线，策略还声明分钟粒度。 | 已批准路线或明确未配置。 |
| `futures` | 实时价、买卖盘、成交/持仓、结算/昨结、库存和仓单。 | `quote_snapshot`、`bars`、`reference_series`；快照和日线，策略还声明分钟粒度。 | 已批准路线或明确未配置。 |
| `bond` | 可转债实时/历史、买卖盘和固定收益语义。 | `quote_snapshot`、`bars`、`reference_series`；快照/日线。 | 已批准路线或明确未配置。 |
| `fund` | ETF 实时/历史、流动性、NAV/净值。 | `quote_snapshot`、`bars`、`reference_series`；快照/日线。 | 已批准路线或明确未配置。 |
| `option` | 实时报价、合约字段（持仓、行权价、到期日）和风险面。 | `quote_snapshot`、`option_chain`、`reference_series`；快照/期权链。 | 无安全路线时必须显式不支持。 |
| `fx` | 实时/历史 OHLC、宏观汇率和区间序列。 | `quote_snapshot`、`bars`、`reference_series`；快照/日线。 | 已批准路线或明确未配置。 |
| `crypto` | 实时 24h 价量高低、历史 bars、CME 持仓/范围。 | `quote_snapshot`、`bars`、`reference_series`；快照/日线/策略分钟粒度。 | 无许可路线时必须显式不支持。 |

公共查询模型预留 `bars`、`quote_snapshot`、`option_chain`、`position_report` 和 `reference_series`。`frequency_semantics` 是必填枚举，不能以空值绕过校验：

| `data_kind` | 允许的 `frequency_semantics` |
| --- | --- |
| `bars` | `5min`、`30min`、`1h`、`1d`、`1w`、`1mo`。 |
| `quote_snapshot`、`option_chain`、`position_report` | `snapshot`。 |
| `reference_series` | 上述 bars 枚举之一，或 `snapshot`；由数据目录和 route capability 精确声明。 |
| 未来事件型数据（不在本期页面范围） | 仅在目录显式注册后使用 `event`。 |

不支持的 `(asset_type, data_kind, market, frequency_semantics, semantic axes)` 必须返回稳定机器码；不允许变换标的、频率、来源、币种或口径来伪造成功。

实施开始前必须冻结版本化 `MD-197-SCOPE-MANIFEST`：它从当时 `/data/market`、`/investment/strategies` 和后端 DTO 的受支持组合逐行导出 `asset_type`、`data_kind`、页面/消费方、字段组、`frequency_semantics`、语义轴、预期 route 或明确 `UNSUPPORTED`/`NOT_CONFIGURED` 结果。某来源缺失只能改变该行的预期结果，不能删掉页面已支持的组合或以代表性样本缩小范围。`commodity` 虽在底层 trust schema 中出现，但当前两个页面和市场服务没有该分支，故不属于本期首批页面验收范围，除非后续显式扩页并更新此清单。

当前页面频率基线也必须写入清单并在 v2 中去歧义：市场查询 UI 的 `daily`/`weekly`/`monthly` 分别映射为 `1d`/`1w`/`1mo`；市场 coverage UI 虽展示 `1d`/`1h`/`30m`/`5m`，但现有刷新链路已证实只有 `1d`，其余不能因 UI 选项而视为可用；策略 UI 公开 `1d`/`1h`/`30m`/`5m`，但其现有 `data_config` 和 asset inference 不构成完整七类资产契约。v2 禁止原始 `1m` 作为公开频率，遗留 `1m` 仅能由兼容层在原端点语境中映射为 `1mo`，避免与一分钟混淆。

当前 AkShare 路由能力也不是页面周期选择器的同义词，范围清单须显式保留下列已核实差异：

| 资产类型 | 当前市场 UI 允许 | 当前在线实现已核实行为 | 197 的清单要求 |
| --- | --- | --- | --- |
| `stock`、`fund` | `daily`/`weekly`/`monthly` | 将 period 传给各自历史接口。 | 逐条验证 provider capability 后才登记 route。 |
| `futures`、`bond`、`option`、`fx`、`crypto` | `daily`/`weekly`/`monthly` | 当前 handler 可接收 UI 值，但各自日线/现货/持仓路径不按 period 建立等价分支。 | 未验证的周/月/分钟组合标为 `NOT_CONFIGURED`，不能借 UI 选项宣称覆盖。 |
| coverage UI | `1d`/`1h`/`30m`/`5m` | 当前刷新矩阵只实际支持 `1d`。 | `1h`/`30m`/`5m` 必须有独立日历、route、存储与验收。 |
| strategy UI | `1d`/`1h`/`30m`/`5m` | 现有输入未形成完整 typed `data_config`/七类 asset contract。 | 在 IG-196 解除前仅作为范围需求，不可接入生产读取。 |

### 2.2 页面和服务范围

- `/data/market` 最终通过 v2 查询接口展示数据、覆盖状态、来源和更新时间。
- `/investment/strategies` 最终只能消费带有冻结市场数据谱系的研究/回测工件。
- 遗留 `/api/v1/data/market-instruments/*` 与 `/api/v1/data/kline` 在灰度完成前保持兼容。
- 197 不替换现有 AkShare 调度、所有历史仓库或实时经纪商 tick 流。

### 2.3 本次交付边界

本次只产出本目录中的需求、设计和验收文档。以下动作不在本次执行范围内：实现代码开发、依赖安装、数据库迁移、真实抓取、回填、OpenBB runner 启动、功能开关启用、页面改造、合并到 `dev`/`master` 或对 196 工作树的修改。文档可在独立 197 分支形成仅文档的本地提交，不能被视为实现交付。

## 3. 功能需求

### FR-197-01：精确、受限的公共查询

调用方必须以 canonical ID，或完整 `(asset_type, symbol, market)` 三元组请求数据。系统必须拒绝仅传代码、双重 selector、空字符串、大小写近似、别名猜测和附近合约替代。

请求必须包含或由服务器策略解析出以下语义：逻辑数据集、数据类型、UTC 半开区间 `[start, end)`、字段集、`frequency_semantics`、复权、价格口径、币种、单位、source policy、用途、一致性级别、知识截止点和读取模式。其组合必须满足本节的 data-kind/frequency 表；在线窗口和页大小必须有上限。

公共请求的 `query_fingerprint` 只描述业务语义，不能承担 provider 请求、用户授权或分页防篡改职责。

### FR-197-02：本地优先、覆盖证明和刷新语义

| 模式 | 要求 |
| --- | --- |
| `local_only` | 只读当前 principal/tenant 仍获准读取的 sealed 本地事实，绝不访问网络。完整本地数据即使使用的 policy 已退役，仍可按其历史用途授权重放；历史采集授权不能替代当前读取授权。 |
| `local_first` | 对未冻结的 `best_effort` 请求，本地完整时零网络；缺口或日历未知时，才按活动、授权、精确匹配的来源策略补齐。对已有 strict visibility anchor 的请求，它退化为 local-only：缺口返回 `HISTORICAL_COVERAGE_UNAVAILABLE` 或 `unknown_calendar`，零网络。 |
| `refresh` | 仅为未冻结的 `best_effort` 请求产生一条新的受控来源修订；响应必须区分 `fresh_complete`、`fresh_incomplete`、`fresh_unknown_calendar`，不得将旧缓存称为刷新结果。已有 strict visibility anchor 时返回 `STRICT_FETCH_FORBIDDEN`，零网络。 |

“完整”必须基于冻结交易日历、精确事件键、必需字段、质量状态和 PIT 边界计算。日历未知、日历覆盖范围不足或日历版本歧义时只能得到 `unknown_calendar`，不能因周末规则、空结果或表行数而声明完整。

### FR-197-03：数据集和来源策略隔离

每条在线 route 必须显式绑定以下集合或版本，且所有维度都精确匹配后才能发出网络请求：

- 逻辑 `dataset_code`，并在解析后复核服务器拥有的 `dataset_id`；
- 资产类型、数据类型、市场、频率、复权、价格口径、币种和单位；
- 允许用途和 policy 的不可变版本/哈希；
- adapter 请求 provider、预期 receipt provider ID、来源注册表 ID；
- 适用时间窗、许可、保留和再分发约束。

一个拥有相同标的和语义、但不同数据集的请求，不能借用另一数据集的 AkShare/OpenBB route 写入其存储。policy 退役后必须保留只读的历史 descriptor（用途授权和版本哈希不变），同时将在线 route 明确禁用；不得通过删除 descriptor 破坏严格本地重放。

每次本地读取、strict replay 与 196 工件消费也必须重新校验当前 principal/tenant 的 local-read entitlement、用途、有效期及再分发限制。来源快照中的历史授权决定只用于证明当时采集和工件创建的依据，不能授权一个当前无权或权限已撤销的主体读取 sealed 事实或工件；拒绝时零网络、零新证据写入。

### FR-197-04：外部获取、回执和本地回读

在线获取前，系统必须按 route 预检：provider 是否活动、来源注册是否启用、license 是否批准、asset type/用途是否允许、有效期是否覆盖、是否满足用户/租户 entitlement 及限流。任一预检失败时，零 adapter 调用、零新证据写入。

一次 provider request 必须带有服务器生成的不可变、不可猜测 request ID；完整 outbound DTO（包括该 ID、provider、route、精确身份、时间窗、字段和所有语义轴）必须另存 `provider_request_fingerprint_sha256`。provider 回执必须回显同一 request ID 和完整请求 DTO。公共 `query_fingerprint` 必须另存为查询关联字段；不能用它替代 provider request ID 或 provider request fingerprint。

成功外部响应必须依次完成：

1. 校验 exact identity、半开时间窗、事件唯一性、载荷大小、字段 JSON、质量与语义；
2. 写入来源快照、原始载荷哈希/清单、policy descriptor、来源登记授权决定和规范化观测修订；
3. 完成两阶段可见性 seal；
4. 仅从已 sealed 的本地表重新读取并计算覆盖；
5. 返回本地 revision/source snapshot 标识，不直接返回 adapter 内存对象。

### FR-197-05：PIT、主数据和可见性

`purpose=research` 或 `backtest` 必须使用 `consistency=strict` 并提供带时区的 `knowledge_cutoff_at`；回测 cutoff 不得晚于请求结束时间。首次解析时，服务端将它冻结成不可变 `visibility_anchor = (knowledge_cutoff_at, max_visibility_sequence_at_or_before_cutoff)`；后续分页、工件读取和重放只能使用保存/签名的 anchor，不能让调用方自造 sequence。主数据和交易日历也必须在同一 PIT 规则下解析。

provider 自报的时间只能作为来源 metadata。应用收到回执的时间只能作为 receipt evidence。两者都不能单独证明事实已经对本地严格读取可见。

系统必须使用两阶段可见性：先在事务 A 写入 prepared 来源快照和观测修订；事务 A 成功提交后，在事务 B 追加不可变 `visibility receipt`。receipt 的 `visibility_sequence` 在 canonical store 内全局单调，`visible_at` 对 sequence 非递减。严格读取只有在对应 receipt 已存在且 `(receipt.visible_at, receipt.visibility_sequence) <= visibility_anchor` 时才可选中该事实。事务 A/B 之间崩溃的 prepared batch 默认不可见，交由受控 reconciler seal 或 abort，并保留审计轨迹。

同一 `(data_series_id, event_at)` 的修订必须拥有单调 `revision_ordinal`，每个 visibility receipt 拥有单调 `visibility_sequence`。严格读取只从字段完整、质量合格且已 sealed 的候选中选择截止点前排序最大的 `(visibility_sequence, revision_ordinal, revision_id)`；相同排序键但内容哈希不同视为证据冲突并失败。不得使用未定义的 `available_at` 或任意 `created_at` 作为 PIT 条件。

### FR-197-06：分页快照防篡改

分页 cursor 必须是版本化、canonical payload 的 HMAC token，而不是可逆 Base64 JSON。签名至少绑定：

- public `query_fingerprint` 和 source-policy immutable version/hash；
- principal/tenant scope 与 entitlement revision；
- 首页冻结并签名的 `knowledge_cutoff_at` 与完整 `visibility_anchor`（时间和 sequence）；
- 排序锚点（事件时间和 revision ID）；
- cursor version，必要时签发时间和最大寿命。

服务端必须在任何 resolver、数据库读取或 provider 调用前验证签名、主体和查询一致性。篡改 cutoff、锚点、query、policy 或跨主体重放都必须失败，且不能产生网络或写入副作用。后续页必须只读首屏冻结的本地快照，不可重新在线补齐。

### FR-197-07：提供方适配器

**AkShare** 采用独立显式路由表。每一函数 route 必须证明任意精确标的、市场映射、有界时间窗、字段口径和返回身份验证；阻塞调用在受限线程池执行。七种资产类型都必须在注册表中有显式决定。暂不能安全实现的期权/加密组合必须返回 `UNSUPPORTED`，不能回退到样例、附近标的或遗留服务。

**OpenBB** 通过最小权限 JSON 子进程协议运行。主 Web 进程不导入 OpenBB extension；命令来自运维配置且不经 shell 拼接；runner 不拥有主应用数据库凭据。协议必须校验版本、request ID、输出上限、超时、非零退出、无效 JSON、重复/越界事件和声明的转换语义。OpenBB fallback 默认不注册，只有经过批准的 provider、市场白名单、许可证和运行器环境同时就绪时才可启用。

### FR-197-08：研究/回测工件绑定

196 和 197 整合后，每个研究或回测工件必须在创建时冻结并保存 `MarketDataQueryProvenance`，至少包括：

- canonical identity、主数据版本、逻辑数据集及 dataset ID；
- data series ID；
- 实际 calendar snapshot ID、calendar version；
- source-policy immutable version/hash、来源注册授权决定；
- `knowledge_cutoff_at`、完整 visibility anchor、visibility receipt/boundary；
- source snapshot IDs、observation revision IDs、查询和工件指纹；
- 采用 RFC 8785 canonical JSON（或等价、版本化的规范化编码）计算的 `provenance_manifest_sha256`；
- `artifact_schema_id`、`artifact_schema_version`、不含派生 hash 字段的持久化工件载荷 `artifact_payload_sha256`，以及 `SHA256(canonical({artifact_schema_id, artifact_schema_version, provenance_manifest_sha256, artifact_payload_sha256}))` 形式的 `artifact_fingerprint`。

工件读取或严格重放时必须重新计算并校验上述四个派生值；任一缺失或不匹配即拒绝。“可由数据库日后反查”不满足该要求。若 196 的工件 schema 尚未冻结，策略页读取链路必须保持关闭并标记 `BLOCKED`。

### FR-197-09：两页面迁移与遗留兼容门

`/data/market` 的 v2 接入必须在功能开关后将既有 `asset_type`、`symbol`、`market`、时间窗和 legacy period 解析为 typed query：默认 display 查询采用未冻结的 `best_effort + local_first`，旧的手动 `refresh_online=true` 映射为受批准的 `refresh`，但只有 route、许可和授权通过时才可访问网络。任何 strict anchor 查询仍按 FR-197-02 零网络处理。v2 返回 coverage、来源、sealed provenance 和稳定拒绝码；在灰度完成前，遗留端点保持兼容，且不得把在线内存 payload 冒充已持久化结果。

`/investment/strategies` 接入前必须以 typed `MarketDataQuery` 取代或严格包裹非类型化 `data_config`，将 `timeframe`/`timeframe_n` 映射为 `frequency_semantics`，并写入工件 provenance。现有策略预检只可明确推断部分资产且缺少 option 规则，因而不能在 196 冻结前作为七类资产的默认 identity/provider/series/adjustment 解析器。若任何输入无法解析为精确 typed query 或工件 schema 未通过 IG-196 闸门，则策略运行/读取路径返回 `BLOCKED` 或稳定机器码，不作猜测回退。

## 4. 非功能需求

| 类别 | 需求 |
| --- | --- |
| 正确性 | 不允许模糊身份、样例、附近记录或未来可见事实替代精确请求。所有边界时间统一为 UTC。 |
| 一致性 | source policy、主数据、日历、观测和 visibility receipt 必须有可复现版本；严格读以完整 `(visible_at, visibility_sequence)` anchor 为界，不依赖当前在线配置。 |
| 并发与恢复 | 每个外部请求有确定的幂等键、owner lease 与 fencing token；同一 provider request ID 的重试不能产生重复可见 snapshot/revision；prepared 未 sealed 的事实默认不可见；reconciler 有 lease、审计和人工处置路径。 |
| 性能 | 精确三元组使用物化索引；本地覆盖判断按请求窗口；网络窗口、并发、重试和载荷受限；任何响应/覆盖缓存 key 必须包含数据集、主体/entitlement、policy descriptor、完整 visibility anchor 和完整查询语义。 |
| 安全 | 不在代码或日志中暴露密钥；cursor 使用 HMAC；provider 命令无 shell 拼接且只接受受控 argv/JSON 协议；原始载荷限额和脱敏；所有在线行为经过认证、授权和限流。 |
| 合规 | provider 活动状态不足以构成授权；在线获取和本地读取都必须检查来源注册、license、allowed use、有效期、辖区、保留和再分发限制，并冻结采集决定。 |
| 可观测性 | 记录本地命中、未知日历、route 预检拒绝、在线/本地读取授权失败、receipt 错配、prepared/sealed/aborted batch、租约/fencing 拒绝、cursor 验证失败、provider 延迟和质量拒绝原因；指标/日志不得泄露密钥或未授权载荷。 |

## 5. 非目标

- 不自动把模糊文本识别为 canonical identity。
- 不把 OpenBB 或其第三方扩展直接装入 FastAPI 运行环境。
- 不承诺每类资产的每个市场立刻可由 AkShare 或 OpenBB 提供真实数据。
- 不在迭代 196 未冻结时改写策略研究、回测或页面生产数据契约。
- 不把历史规范化数据、实时经纪商 tick、用户私有账户数据和公开市场数据混入同一个无治理表。
