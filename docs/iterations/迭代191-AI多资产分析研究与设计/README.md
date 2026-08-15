# 迭代 191：AI 多资产分析研究与设计总计划

> 状态：改进建议已复核并纳入；P0a/P0b 代码基础与 P0c 只读股票兼容桥已完成隔离验证，固定夹具 NFR-C03/C04 已在隔离 MySQL 9.4.0 上完成 100 标的容量测量；资产身份、数据质量降级和 FX/数字货币服务端地区门禁已收紧；全量生产容量、授权数据源和 T2 晋级仍为关闭门禁
>
> 调研基准日：2026-08-01
>
> 目标版本：多资产研究 v1
>
> 实施方式：一个公共底座 + 六个可独立验收的资产子迭代
>
> 代码基线：`e7fd2d5151c86ba62173b8d19736983a0a379909`

## 1. 目标

在保留现有“AI 股票”能力的基础上，为债券、基金、期货、期权、外汇和数字货币增加单资产研究功能。用户输入一个可唯一识别的资产后，系统应：

1. 识别具体资产、交易场所、币种和合约属性，拒绝歧义代码；
2. 仅使用分析时点已经可获得的数据，生成可追溯的数据快照；
3. 执行资产专属的估值、收益、风险、流动性和事件分析；
4. 生成结构化方向观点、买入/卖出/持有或暂不参与建议，以及适用条件；
5. 生成可阅读、可导出、可保存至知识库的中文研报；
6. 保存用户触发和审批清单每日影子运行的预测及后续结果，展示历史建议、样本量、
   命中率、校准度和净收益；
7. 在数据不足、合规不允许或风险不可量化时主动放弃给出方向建议。

本迭代不承诺预测必然盈利。完成验收表示系统能诚实、可复现地生成并评价研究信号；只有通过独立的模型晋级门槛后，相应资产才可从“研究观察”升级为“方向建议”。

## 2. 产品决策

### 2.1 共用能力与资产专属能力

| 共用底座 | 必须按资产实现 |
| --- | --- |
| 资产解析、任务生命周期、来源快照、数据质量、研报生成与导出、历史预测、结果成熟、权限和审计 | 标识字段、交易日历、估值模型、特征、基准、持有期、成本、建议语义、结果评分、风险披露 |

现有 `MarketInstrumentService` 已声明 `stock/futures/bond/fund/option/fx/crypto` 七类资产，可复用资产发现和基础行情入口；现有股票财务、新闻、评分和 `1/5/20` 日结果模型不得直接复制到其他资产。

### 2.2 建议的统一表达

系统同时保存以下权威字段，避免把研究观点误解成订单：

| 字段 | 枚举 | 含义 |
| --- | --- | --- |
| `market_view` | `BULLISH/BEARISH/NEUTRAL/INDETERMINATE` | 对标的在指定期限内的方向观点 |
| `normalized_direction` | `LONG/SHORT/NEUTRAL/INDETERMINATE` | 对规范研究产品的目标方向；资产不支持做空时 `SHORT` 不可发布 |
| `recommendation` | `BUY/SELL/HOLD/AVOID` | 面向用户的研究建议；`AVOID` 为数据或风险否决 |
| `actionability` | `ACTIONABLE/RESEARCH_ONLY/INSUFFICIENT_DATA/REGION_RESTRICTED` | 是否具备展示方向建议的模型、数据和地区资格 |
| `position_context` | `FLAT/LONG/SHORT/UNKNOWN` | 用户可选的当前持仓状态，不从研究结果推断 |
| `trade_intent` | `OPEN/ADD/REDUCE/CLOSE/KEEP/NONE` | 建议如何解释；本迭代不执行该动作 |

对支持双向研究的线性产品，公共真值表为：

| 持仓 | 方向 | 建议 | 意图 |
| --- | --- | --- | --- |
| `FLAT` | `LONG` | `BUY` | `OPEN` |
| `FLAT` | `SHORT` | `SELL` | 产品批准开空研究时为 `OPEN`，否则 `NONE` |
| `LONG` | `SHORT` | `SELL` | `CLOSE` |
| `SHORT` | `LONG` | `BUY` | `CLOSE` |
| 与方向一致的已有持仓 | `LONG/SHORT` | `HOLD` | `KEEP` |
| 已有持仓 | `NEUTRAL` | `HOLD` | `KEEP` |
| `FLAT` | `NEUTRAL` | `HOLD` | `NONE` |
| `UNKNOWN` | `LONG/SHORT` | `BUY/SELL` | `NONE` |
| 任意 | `INDETERMINATE` | `AVOID` | `NONE` |

债券、基金、现货数字货币等 long-only 产品禁止把空仓 `SHORT` 映射为裸空；
期权 v1 只允许 `LONG + BUY + OPEN` 和已有精确多头的
`NEUTRAL + SELL + CLOSE`。`OPEN_LONG`、`SELL_TO_CLOSE` 等文字只能从公共字段派生，
不能形成第二套权威动作枚举。

每次运行同时保存内部 `candidate_decision` 和对用户公开的
`published_decision`。模型未晋级或地区受限时，候选方向仍可用于影子实证，
但普通用户 API、页面和导出只返回 `INDETERMINATE + HOLD/AVOID + NONE`。
地区禁止统一返回 `actionability=REGION_RESTRICTED + recommendation=AVOID +
trade_intent=NONE`，不得与仅表示模型阶段的 `RESEARCH_ONLY` 混用。
`short_open_research_allowed` 是服务端、地区和产品共同决定的版本化 capability，
必须纳入决策输入哈希；前端参数不能自行开启。

### 2.3 规范身份层级

公共身份使用 `identity_level=ASSET/PRODUCT/CONTRACT/SERIES`：

- `ASSET` 可表示不绑定场所的基础资产研究；
- `PRODUCT` 表示带交易机制、报价和结算约定的产品；
- `CONTRACT` 表示有到期、乘数或份额类别的精确合约；
- `SERIES` 只用于研究连续序列，必须冻结当时映射后才可形成合约结果。

`venue`、`currency`、链、份额类别、到期和结算字段按
`asset_type + identity_level` 条件校验，不把开放式基金或资产级 BTC 强行伪装成
场内产品。

### 2.4 研究和执行边界

- 本迭代只产出研究、报告、预测记录和影子评分，不连接账户、不读取资金、不创建订单。
- LLM 只能解释结构化事实和已经确定的建议，不能改写数值、数据质量结论或最终动作。
- 在中国大陆产品模式下，数字货币子迭代仅开放教育和研究展示，不提供交易开户链接、账户连接、交易指令或营销导流。
- 个性化适当性、组合仓位、真实/模拟执行均需独立立项和合规批准。

## 3. 文档导航

### 3.1 总体文档

- [调研报告](./RESEARCH.md)
- [总体架构设计](./ARCHITECTURE.md)
- [交付治理与风险登记册](./DELIVERY_GOVERNANCE.md)
- [数据库与股票兼容迁移计划](./MIGRATION_PLAN.md)
- [非功能需求与运行基线](./NON_FUNCTIONAL_REQUIREMENTS.md)
- [总体验收计划](./ACCEPTANCE.md)
- [改进建议处置结论](./IMPROVEMENT_REVIEW.md)
- [外部改进建议原始快照（历史输入，非权威计划）](./IMPROVEMENT_SUGGESTIONS.md)
- [实施状态与验收证据](./IMPLEMENTATION_STATUS.md)

### 3.2 六个子迭代

| 子迭代 | 需求 | 设计 | 实施计划 | 验收 |
| --- | --- | --- | --- | --- |
| 191A AI 债券 | [需求](./01-AI债券/REQUIREMENTS.md) | [设计](./01-AI债券/DESIGN.md) | [计划](./01-AI债券/PLAN.md) | [验收](./01-AI债券/ACCEPTANCE.md) |
| 191B AI 基金 | [需求](./02-AI基金/REQUIREMENTS.md) | [设计](./02-AI基金/DESIGN.md) | [计划](./02-AI基金/PLAN.md) | [验收](./02-AI基金/ACCEPTANCE.md) |
| 191C AI 期货 | [需求](./03-AI期货/REQUIREMENTS.md) | [设计](./03-AI期货/DESIGN.md) | [计划](./03-AI期货/PLAN.md) | [验收](./03-AI期货/ACCEPTANCE.md) |
| 191D AI 期权 | [需求](./04-AI期权/REQUIREMENTS.md) | [设计](./04-AI期权/DESIGN.md) | [计划](./04-AI期权/PLAN.md) | [验收](./04-AI期权/ACCEPTANCE.md) |
| 191E AI 外汇 | [需求](./05-AI外汇/REQUIREMENTS.md) | [设计](./05-AI外汇/DESIGN.md) | [计划](./05-AI外汇/PLAN.md) | [验收](./05-AI外汇/ACCEPTANCE.md) |
| 191F AI 数字货币 | [需求](./06-AI数字货币/REQUIREMENTS.md) | [设计](./06-AI数字货币/DESIGN.md) | [计划](./06-AI数字货币/PLAN.md) | [验收](./06-AI数字货币/ACCEPTANCE.md) |

## 4. 交付范围

### 4.1 在本迭代内

- 通用多资产研究领域模型、数据库表、API 和前端工作台；
- 六类资产的解析器、数据适配器、质量门控、特征、规则/模型、报告章节和结果评分器；
- 单资产即时分析、历史报告、预测记录、成熟结果和质量成绩单；
- Markdown/PDF 导出、知识库/工作区保存能力；
- point-in-time 数据快照、版本化策略、可复现运行和无前视偏差测试；
- 审批资产清单的日历感知每日影子调度、失败补跑和不可变晋级审计；
- 固定夹具、集成测试、前端测试和受控在线冒烟验证；
- 合规模式、数据许可证清单和功能开关。

### 4.2 明确不在本迭代内

- 真实或模拟下单、账户鉴权、持仓同步、资金和保证金管理；
- 组合优化、跨资产配置、自动调仓和批量扫描全部市场；每日调度只处理审批并版本化的
  小范围影子清单；
- 将研报或概率描述为保证收益；
- 裸卖期权、无限损失策略、未限定场所的数字货币合成报价；
- 未经许可复制或商业化使用受限行情、估值曲线或指数数据。

## 5. 总体阶段和顺序

| 阶段 | 周期 | 交付 | 退出条件 |
| --- | --- | --- | --- |
| P0a 契约与存储 | 第 1-2 周 | 领域契约、插件协议、expand 迁移、来源和合规注册表 | 公共 Schema 冻结，迁移演练通过 |
| P0b 编排与工作台 | 第 3-4 周 | orchestrator、API、前端壳、调度和运行指标 | 总体验收 A、B、C 的公共路径通过 |
| P0c 稳定与兼容 | 第 5 周 | 股票适配、双读/可选双写、故障和回滚演练 | 股票兼容契约冻结，旧股票回归必过 |
| P1 现货型资产 | 第 6-8 周 | AI 债券、AI 基金 | 191A、191B T1 独立通过 |
| P2 线性衍生与货币 | 第 8-10 周 | AI 期货、AI 外汇 | 191C、191E T1 独立通过 |
| P3 非线性衍生 | 第 11-12 周 | AI 期权 | 191D T1 通过且无裸卖路径 |
| P4 受限资产 | 第 12-13 周 | AI 数字货币研究模式 | 191F T1 合规与地区门控通过 |
| P5 集成与发布准备 | 第 14-16 周 | 多方言迁移、容量、韧性、安全和全链路验收 | 总体 T1 通过且迁移/回滚演练完成 |
| P6 前瞻影子验证 | 第 17 周起持续运行 | 每日预测、结果补齐、成绩单 | 达到资产专属 T2 门槛或保持研究观察 |

以上周期是容量规划基线，不是未经团队确认的交付承诺。基线团队为 1 名技术负责人、
2-3 名后端/数据工程师、1 名前端工程师、2 名资产领域研究人员、1 名 QA，以及共享的
DevOps/SRE 与合规/数据许可支持；资源不足时必须重新排序和估算，不能压缩验收门禁。
详细 RACI、风险和变更规则见
[交付治理](./DELIVERY_GOVERNANCE.md)。

191A/191B 在公共身份、来源快照和插件协议冻结后可以由不同插件团队并行；共享
`MarketInstrumentService` 严格身份适配边界只有一个 owner。191C/191E 可并行；
191D 依赖期货的合约日历和风险框架，191F 依赖地区合规门控。任何子迭代未通过，
不阻止其他子迭代独立上线为“研究观察”。

## 6. 公共实施任务

### 任务 1：建立通用领域契约

- [ ] 新增 `asset_research` 模型、Schema 和服务目录。
- [ ] 实现 `AssetResearchPlugin` 协议和六个插件注册。
- [ ] 建立六插件参数化协议一致性套件，对每个注册插件统一验证严格身份、raw snapshot
  先落库、质量拒绝、候选/发布隔离、报告输入、outcome 列表和禁止直接 DB/LLM/下单副作用；
  任一插件只能通过显式 capability 声明不支持，不能跳过公共合同。
- [ ] 建立带 `identity_level` 和资产专属 discriminated union 的
  `InstrumentIdentity`，任何衍生品都能还原到具体可交易合约。
- [ ] 建立唯一动作真值表、`PredictionHead`、`OutcomeKind`、
  `OutcomeStatus`、`MaturityReason` 和命名空间 `ReasonCode` 契约。
- [x] 将现有股票信号服务接入只读 `StockResearchCompatibilityAdapter`，保留后端
  `/api/v1/stock-analysis`、前端 `/investment/stock-analysis` 和历史表；兼容响应不
  伪造 canonical identity、来源 manifest、持仓上下文或 outcome head，也不启用双写。
- [ ] P0a 结束冻结公共 Schema、插件协议、reason code 和动作真值表；冻结后变更按
  [交付治理](./DELIVERY_GOVERNANCE.md)执行影响分析和版本升级。

### 任务 2：建立 point-in-time 数据层

- [x] 默认多资产 bridge 绑定本地 `akshare_data` 并关闭在线 refresh；来源 capability
  仅对已安装适配器声明的 source ID 生效，响应来源切换或 outcome 期许可失效均
  fail-closed，不把注册表当作事后归属标签。
- [ ] 在现有行情服务外建立严格身份适配器；精确代码未命中或返回身份不一致时拒绝，
  禁止用最近任意样本代替目标资产。
- [ ] 每个字段保存来源、观测时间、发布时间、获取时间和许可标签。
- [ ] 先不可变保存允许关键值为空的 `RawAssetSnapshot`，质量门控后才构造收紧的
  `EligibleAssetSnapshot`；数据缺失必须形成可审计拒绝决定，而不是请求或服务异常。
- [ ] 建立数据新鲜度、交叉源偏差、缺失和异常值门控。
- [ ] 同一运行冻结全部输入，报告和评分不回写原始快照。
- [ ] 对会修订的宏观、基金持仓和链上数据保存版本，不用今天的值回填历史预测。

### 任务 3：建立建议和研报流水线

- [ ] 确定性策略或受控模型先生成 `ResearchDecision`。
- [ ] 风险和质量否决可将任意方向降为 `AVOID`。
- [ ] LLM 仅基于结构化 JSON 生成资产专属报告章节，并执行引用一致性检查。
- [ ] 报告必须展示期限、适用持仓、建议语义、反方证据、失效条件和风险披露。

### 任务 4：建立预测和结果闭环

- [ ] 以规范化 `decision_input_hash` 保存完整请求、持仓、冻结身份、来源快照和
  全部 capability/compliance/cutoff/模型/策略/成本/校准版本，作为预测幂等依据。
- [ ] 将用户显式提供的持仓研究上下文保存为带访问主体、精确资产身份、有效期和
  内容哈希的不可变快照；跨用户、跨合约或过期快照不得授权期权平仓建议。
- [ ] 按目标定义保存一个或多个独立 `PredictionHead`，每个 head 分别保存标签、
  概率、目标/可评分规则版本、模型与校准 artifact 哈希、训练截止时点、基线版本，
  并且至多一个主晋级 head。
- [ ] 用 `head_spec_hash` 隔离结果 cohort；不同 target/scoreability/baseline 版本
  不得混算 Brier 或晋级指标。
- [ ] run 与不可变 prediction 使用 run 行上的直接外键和 `CREATED/REUSED` 审计角色；
  `PENDING/RUNNING/FAILED/CANCELLED` run 两列均为空，`SUCCEEDED` run 两列均完整，
  v1 不接受 `PARTIAL`；重试始终新增 run，相同输入可复用同一 prediction，禁止覆盖
  prediction 事实。
- [ ] 以 `outcome_kind` 保存同一预测的多种结果，并列化时点、价格、币种、
  成本、状态和成熟原因。
- [ ] 按资产使用不同基准、成本、交易日历和到期/滚动规则。
- [ ] 展示覆盖率、弃权率、分动作精确率、Brier/校准曲线、净收益和回撤。
- [ ] 旧股票记录双读，通用表稳定后再评审是否迁移；本迭代不删除旧表。
- [ ] 按 [迁移计划](./MIGRATION_PLAN.md)完成 expand-migrate-contract、现存库升级、
  失败恢复、可选双写语义对账和回滚演练。

### 任务 5：建立共用前端

- [ ] 新增 `/investment/ai-assets/:assetType`，保留 `/investment/stock-analysis` 兼容入口。
- [ ] 将现有股票页面拆成工作台壳和资产专属面板。
- [ ] 导航增加 AI 债券、AI 基金、AI 期货、AI 期权、AI 外汇、AI 数字货币。
- [ ] 每个页面均包含搜索、身份确认、分析参数、质量状态、结论、研报、历史和成绩单。
- [ ] 将现有 `useStockAnalysisTask` 泛化为单一任务状态机，处理取消、重试、终态停止、
  页面可见性和 stale response；不得再复制一套页面内轮询。

### 任务 6：验证和发布控制

- [ ] 使用固定 point-in-time 夹具完成单元和集成测试。
- [ ] 在同一参数化测试中运行六插件公共协议，避免每个资产只通过自己的局部测试却破坏
  orchestrator 契约。
- [ ] 用时间顺序 walk-forward 和间隔窗口完成离线评估。
- [ ] 上线后先运行影子模式，不向用户显示方向动作。
- [ ] 只有达到模型晋级门槛，才为相应资产/品种/期限打开方向建议开关。
- [ ] 按 [非功能需求](./NON_FUNCTIONAL_REQUIREMENTS.md)完成容量、延迟、韧性、
  生命周期、可观测性和 LLM 预算验收；未实测指标只能标为基线，不能对外称 SLA。

### 任务 7：建立每日影子调度和审计

- [x] 建立版本化 `schedule` 配置和 `cutoff policy`；管理员只能以 approval reference、
  evidence URI/hash 创建版本化静态 manifest，并在配置阶段展开为精确单资产 system
  schedule。创建前逐条重验 source capability 和有效身份，退役清单只禁用未来 fire、不改写
  历史 run/prediction；运行时不扫描市场。真实来源/主数据/日历未获批时仍保持关闭。
- [x] 调度器按资产专属 cutoff policy 和数据可用时间计算 fire，不统一套用北京时间 19:00；
  `test_schedule_policy.py` 覆盖中国市场、纽约收盘和 UTC 的固定时钟合同。真实授权市场日历
  的覆盖度仍是 T1 门禁。
- [x] 使用 `schedule_id + schedule_version + scheduled_fire_at + cutoff_at +
  cutoff_policy_version + policy_version` 生成 `run_key` 并以租约锁去重；
  补跑固定原 cutoff、资产标识和 schedule 配置，不能吸收事后数据；
  `test_schedule_runner.py`、`test_schedules.py` 覆盖重复认领、失败重试与 misfire。
- [x] 每轮 schedule worker 以配置化 `ASSET_RESEARCH_SCHEDULE_WORKER_CONCURRENCY=4`
  有界并发执行；所有同一 server-declared source 的采集共享
  `ASSET_RESEARCH_SOURCE_MAX_CONCURRENCY=2` 上限。`test_schedule_runner.py` 与
  `test_source_concurrency.py` 覆盖上限合同；这不替代容量压测或外部来源限流演练。
- [ ] 用户即时分析和调度分析共用预测幂等合同，但分别保留触发来源和权限。
- [ ] 晋级、暂停和回滚写入不可变审批历史，证据 URI、head spec 和各版本可追溯。

### 6.1 默认调度策略

| 资产 | 默认影子 cutoff | 说明 |
| --- | --- | --- |
| 债券 | 最近交易日官方估值、曲线和事件全部可用后 | 估值不是可执行报价 |
| 基金 | 对应 NAV/PCF 披露后 | ETF 与开放式基金分开 |
| 期货 | 中国市场北京时间 19:10 | 按品种日历决定下一夜盘或日盘 |
| 期权 | 交易所收盘且完整链可用后 | v1 只用已确认的明确合约，运行时不选约 |
| 外汇 | 纽约 17:10 后的完整日线 | 北京 19:00 只能另建 H1/H4 盘中策略 |
| 数字货币 | UTC 00:10 后 | 北京 19:00 只能另建完整 bar 快照策略 |

## 7. 模型晋级门槛

技术验收与模型有效性分开判断。每次晋级先冻结
`promotion_scope_key`，其至少包含资产类型、产品/样本池、期限、主预测 head、
资产专属范围参数，并声明 scope 类型。策略、模型和校准版本作为模型注册表唯一键的
独立列冻结，不重复塞入 scope key：

- `POOLED`：跨多个品种学习和评价，执行单一品种不超过 40% 的集中度门槛；
- `INSTRUMENT_SPECIFIC`：只针对一个品种/货币对/标的，不使用 40% 规则，
  但必须达到同等最小成熟样本并覆盖至少三个独立市场状态；衍生品还需覆盖多个合约或到期。

以下条件全部满足后，该 scope 才能从“研究观察”晋级：

1. 不存在前视、幸存者、修订值回填或连续合约不可交易偏差；
2. 离线 walk-forward 覆盖至少三个不同波动/利率/趋势状态；
3. 至少有 200 条可评分行动信号；只有 `POOLED` scope 要求任一单一品种不超过
   样本的 40%；
4. 计入点差、手续费、滑点、资金费、展期或申赎成本后，行动信号的平均净效用为正；
5. 注册的主 `PredictionHead` 相对朴素基线 Brier Skill Score 大于 0，
   可靠性图无系统性过度自信；
6. 95% bootstrap 置信区间下界不劣于对应基线；
7. 完成至少 60 个交易日的前瞻影子验证；数字货币为连续 90 个自然日；
8. 合规、数据许可、安全和产品负责人共同签字，审批记录固定 scope、head、
   target/scoreability/baseline、policy/model/calibration 版本、artifact 哈希和证据 URI。

运行时还必须逐项解析冻结的 T2 指标，并在预测 `as_of_at` 前找到与 registry 指标快照、
evidence URI/hash 完全一致的 `SHADOW -> PROMOTED` 不可变事件。单独把当前 registry
行写成 `PROMOTED` 不构成晋级；字段缺失、指标不一致、审批/事件晚于 cutoff 或 scope
专项条件不满足时，公开结论继续保持研究观察。

不满足门槛时，功能仍可展示事实、估值和风险，但主建议固定为“持有/暂不参与”，并明确显示“样本不足，未通过方向信号晋级”。
候选方向只保存在受限影子字段中用于实证评分，普通用户接口不得提前暴露。

## 8. 完成定义

- [ ] 本目录所有内部链接有效，六个子迭代均有需求、设计、计划和验收文档；
- [ ] 改进建议均在处置清单中有采纳结论和落点；历史建议文件不作为实施权威来源；
- [ ] 总体架构中的接口、表、枚举与子迭代一致；
- [ ] 资源、RACI、依赖、风险 owner、触发条件、应急方案和公共契约冻结点已确认；
- [ ] 空库与现存库升级、旧股票读写兼容、失败恢复和回滚演练均形成证据；
- [ ] 性能容量、运行指标/告警、数据生命周期和 LLM 预算基线形成可复现证据；
- [ ] 六类资产均定义可唯一解析的输入和无歧义的动作语义；
- [ ] 六类资产均定义关键数据缺失时的失败行为和可评分结果；
- [ ] 自动化测试、静态检查和构建通过；
- [ ] 每类资产至少完成一条成功、一条降级和一条拒绝的受控在线冒烟证据；
- [ ] 不存在下单、账户密钥、裸卖期权或中国大陆数字货币交易导流路径；
- [ ] 模型未达晋级门槛时，产品不会暗示方向建议已被验证有效。
