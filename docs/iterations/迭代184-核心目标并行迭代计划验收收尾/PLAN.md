# 迭代 184 - 核心目标并行迭代计划验收收尾

> **创建日期**：2026-07-17<br>
> **最近校准**：2026-07-18<br>
> **来源计划**：`docs/plans/2026-07-05/ai-for-investor-core-goal-parallel-iteration-plan.md`<br>
> **来源验收**：`docs/plans/2026-07-05/ACCEPTANCE.md`<br>
> **状态**：待执行；Gate 0 未关闭<br>
> **性质**：原计划承诺的验收缺口闭合，不扩展原计划之外的业务领域<br>
> **沟通语言**：中文；代码、命令和配置名保留英文<br>
> **集成负责人**：Integrator（单一集成入口）；各泳道负责人见第 4 节

---

## 0. 复核结论与本版优化

原版对缺口识别基本准确，但更接近“问题清单 + 实现建议”，还不足以直接指导并行实施和最终验收。本版完成以下收敛：

1. 把 A/B/C 大包拆为可独立合并的工作包，补齐前置依赖、负责人、优先级、验收证据和状态。
2. 修复“标题是并行计划、执行顺序却是 A -> B -> C -> D 串行”的矛盾，新增并行波次、关键路径和集成门。
3. 将方向 C 的审核/风控持久化从“永久 JSON 或建表二选一”收敛为**结构化表方案**；同时增加模拟交易运行时数据真源决策，避免把 AI 投研的 `workspace/unit/instance` 错接到另一套 `paper_account` 引擎。
4. 将验收从“可用/有测试/明显提升”改为可自动判定的场景、行为和证据。
5. 增加空库、Alembic 存量库、`create_all` 历史库三类迁移验证，避免只证明空库可升级。
6. 区分 PR 必跑的确定性 10 步 E2E 与 nightly 外部集成冒烟，降低最终收尾阶段的不确定性。
7. 补齐生产门控、权限、幂等、告警去重、资金曲线容量、发布与回退约束。
8. 按 2026-07-18 当前仓库重新校准：
   - 迭代 183 已建立 `app/services/research/` 与 `useStrategyPage.ts` 的基础切片边界，184-A/C 不再整体依赖 183-B/C 才能启动。
   - AI 投研配置已包含 `parameter_sensitivity`，但 `OverfittingPanel` 的重跑选项仍缺该方法；184 只补齐该组件契约与测试，不重复实现后端算法。
   - 183-I 的外部 provider 凭据轮换仍是发布门，不计入 184 开发工作量。

---

## 1. 目标、成功标准与基线

### 1.1 一句话目标

闭合 2026-07-05 核心目标计划中尚未达标的迁移、测试、数据可信度、模拟交易审计和实时风控能力，并用可重复的证据把来源验收结论从“未完成”推进到“完成”。

### 1.2 成功标准

迭代只有在以下条件同时满足时才完成：

- 来源计划 A/B/C 共 15 条验收标准全部有可追踪证据，见第 6 节。
- 所有 Must 工作包完成；Should 工作包不得阻塞来源验收，未完成时必须迁出并记录后续迭代。
- A/C 迁移在三类数据库基线上通过，Alembic 最终只有一个 head。
- 稳健性验证在生产路径不可由普通请求绕过，失败或服务异常时禁止进入模拟交易（fail closed）。
- PR 确定性 10 步 E2E 全绿；nightly 外部集成冒烟至少取得一次成功证据。
- 无未关闭 P0/P1 缺陷；发布与数据回退方案已演练或有自动化测试证明。
- `ACCEPTANCE.md` 只在证据矩阵全部闭合后更新，不把文档勾选本身作为验收证据。

### 1.3 当前基线（2026-07-18）

| 项目 | 当前状态 | 184 处理 |
| --- | --- | --- |
| 来源验收 | A ~80%、B ~70%、C ~68%，总体未完成 | 以来源验收 15 条标准为唯一产品验收基线 |
| A 数据模型 | 4 个 ORM 模型存在，无方向 A Alembic revision | A1 补兼容迁移与迁移测试 |
| A 时间线/版本 UI | 有基础列表；缺指标详情下钻和结构化 delta | A3 补齐 |
| B 指标 | `AnalyticsService`、`MetricsService`/扩展指标 helper 仍存在不同输出契约 | B1 先固化 canonical schema，再以 adapter 保持兼容 |
| B 预检/稳健性 | 预检仍手动；`require_robustness_validation=False` | B3 自动预检并生产强制稳健性 |
| B 首屏 | `BacktestResultPage` 首个阻塞请求仍取完整 detail | B4 增 summary-first 契约 |
| B summary 契约 | 后端 `result_summary.metrics.*` 与前端读取 `result_summary.*` 存在层级错位 | G0-5/B4 固化显式 `BacktestSummaryResponse`，禁止前后端猜字段 |
| B 测试 | 6 个服务和 `/data/trust` 缺直接、系统化测试 | B2 补齐 |
| B 过拟合面板 | AI 投研配置已支持；`OverfittingPanel` 重跑选项仍只有三种方法 | B6 补选项、结果展示分支与测试 |
| C 存储 | 3 个审核/风控模型和资金快照表缺失 | C1 统一建表与回填 |
| C 模拟运行时 | AI 主闭环使用 paper workspace/unit/instance，独立 paper account 引擎使用 account/order/position/trade | G0-2 冻结数据真源与 ID 映射后才能设计 C1-C4 |
| C 产品闭环 | 无独立模拟详情/风控监控 UI；告警与实时风控未完整接线 | C2-C4 补齐 |
| C 告警存储 | 已有持久化 `Alert`/`AlertRule`，同时存在进程内 `RiskControlService._alerts` | C1/C3 统一为 DB `Alert` 真源，禁止再建第二套告警表 |
| 183 代码依赖 | 后端研究服务与前端状态层已有基础拆分 | 视为 entry condition 已满足，仍执行热点文件所有权规则 |
| 183 外部依赖 | provider 凭据轮换证据未完全闭合 | 作为 Release Gate，只读复核 |
| 10 步链路测试 | 已有 `test_ai_strategy_research_task_api_runs_generated_goal_full_pipeline` 覆盖大部分流程，但未强制 robustness、未断言 DB 事件/版本 | D1/D2 在既有测试上增强，不从零重复搭建 |

开始实施时必须在证据记录中补充基线 commit、Alembic head、后端/前端测试摘要；未记录基线不得宣称性能或覆盖率“提升”。

---

## 2. 范围、优先级与 Cut Line

### 2.1 Must：阻塞来源计划完成判定

- 184-A：A 方向迁移、失败事件/版本 API 测试、时间线详情、结构化版本对比。
- 184-B：服务/API 测试、canonical 指标契约、自动预检、summary-first、期货专项质量检查、生产稳健性强制、`OverfittingPanel` 方法契约补齐。
- 184-C：结构化审核/风控/资金快照模型与迁移、资金曲线 API、模拟详情页、审核三决策、实时风控、运行时告警、风控监控 UI。
- 184-D：确定性 10 步 E2E、nightly 冒烟、来源验收追踪和发布门复核。

### 2.2 Should：时间不足时迁出，不得拖延 Must 验收

- 将 `paper_trading_service.py` 进一步拆成 `paper_trading/broker.py`、`runner.py`、`review_service.py`。
- UI 视觉精修、资金曲线高级缩放/导出、告警高级筛选。
- 超出固定验收资产 RB0 的更多资产专项规则。

Should 项若与 Must 修改同一热点文件且能显著降低合并风险，可在对应泳道完成；否则迁入后续技术债迭代。

### 2.3 非范围

- 不新增原计划外的资产类型、交易通道或策略类型。
- 不重写已验收通过的稳健性算法、事件/版本写入和模拟交易基础账户/订单/持仓能力。
- 不由 agent 伪造 provider 凭据失效或轮换证据，不执行历史 rewrite/force-push。
- 不把迭代 183 的仓库卫生、通用 IDOR 修复、i18n 或大文件治理重新计入 184 工作量。
- 不在真实账户、实盘 broker 或开发数据库上执行迁移/回退演练。

---

## 3. Gate 0：实施前必须冻结的决策

Gate 0 未关闭前，只允许编写 characterization test、固定 fixture 和契约草案，不允许合并 schema、迁移或运行时行为变更。

| 决策 ID | 必须冻结的内容 | 本计划默认决策 | 证据 | Owner | 状态 |
| --- | --- | --- | --- | --- | --- |
| G0-1 | canonical 指标字段、单位和空值语义 | 内部统一使用 `annual_return`、`profit_loss_ratio`、`total_trades` 等 canonical 字段；旧 API 字段由 adapter 提供一个迭代 | ADR/契约测试 | Lane B | todo |
| G0-2 | C 模拟交易数据真源 | 当前 AI 主闭环以 `workspace_id/unit_id/instance_id` 为运行时真源；默认沿用该主域，`paper_account_id` 只在明确映射到 account engine 时作为可选关联。若改为 account engine，必须先交付双向 ID 映射、迁移和全链路证明 | ADR + ID mapping + sequence diagram | Lane C / Integrator | todo |
| G0-3 | 稳健性生产策略 | production 强制且 fail closed；`require=true` 自动蕴含 `robustness_validation=true`；opt-out 仅 test/dev 配置，不能由生产请求参数开启，绕过写审计 | 配置矩阵 + 门控测试设计 | Lane B / Integrator | todo |
| G0-4 | 迁移拓扑 | A/C 各自 revision，基于实施时 current head；并行产生多 head 时由 Integrator 创建 merge revision | `alembic heads` 基线 | Integrator | todo |
| G0-5 | API/事件契约 | summary、资金曲线、风控告警、`requested_changes` 状态与事件字段冻结 | OpenAPI diff + schema tests | Integrator | todo |
| G0-6 | 资金快照容量 | 时区 UTC；幂等键/采样粒度、分页、降采样、保留期和清理策略明确 | ADR + 容量估算 | Lane C | todo |
| G0-7 | C 结构化存储与告警统一 | 新建 `PaperReviewReport`、`LiveHandoffReview`、`RiskRule`、`PaperEquitySnapshot`，FK 跟随 G0-2；旧 JSON 双读一个迭代；告警统一写既有 `Alert`，按需扩展 workspace/unit/instance scope，废止进程内告警真源 | ADR + schema 草图 + 回填方案 | Lane C | todo |

Gate 0 Exit Criteria：七项均有决策记录，canonical schema 和 OpenAPI 变更通过相关泳道共同 review，无“实现时再决定”的二选一项。

---

## 4. 工作分解与并行泳道

状态只允许：`todo`、`doing`、`blocked`、`review`、`done`。`done` 必须有第 8 节规定的证据。

| ID | Pri | Owner | 工作包与主要产物 | Depends on | 验收项 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Must | Lane A | A 方向 4 表兼容迁移、索引/FK、三基线迁移测试 | G0-4 | A-AC1 | todo |
| A2 | Must | Lane A | 失败事件落库 E2E、versions/detail/compare API 与客户端测试 | A1、G0-5 | A-AC2 | todo |
| A3 | Must | Lane A UI | 时间线指标/输入输出/代码下钻；版本时间与结构化 delta | G0-5；183-C entry 已满足 | A-AC3 | todo |
| B1 | Must | Lane B | characterization tests、canonical 指标 schema、兼容 adapter | G0-1 | B-AC1 | todo |
| B2 | Must | Lane B Test | 6 服务 + `/data/trust` 正常/边界/失败测试 | Gate 0；可与 B1 并行 | B-AC2 | todo |
| B3 | Must | Lane B | 自动预检、具体缺口、生产稳健性强制与 fail-closed 门控 | G0-3、B1 | B-AC3 | todo |
| B4 | Must | Lane B UI/API | summary-first 端点/契约、首屏异步明细、性能回归测试 | G0-5 | B-AC4 | todo |
| B5 | Must | Lane B Data | 期货换月/夜盘专项检查、交易日历 fixture 与测试 | Gate 0 | B-AC5 | todo |
| B6 | Must | Lane B UI | `OverfittingPanel` 增 `parameter_sensitivity` 重跑选项、结果展示与回归测试 | B1 | B-AC6 | todo |
| C1 | Must | Lane C | 4 个结构化模型、Alert scope 扩展、迁移策略、旧 JSON/内存告警回填或停用 | G0-2、G0-4、G0-7 | C-AC1 | todo |
| C2 | Must | Lane C | 复用/收敛既有 simulation analytics，补资金快照写入、幂等/分页/降采样 API、canonical runtime 权限测试 | C1、G0-6 | C-AC2 | todo |
| C3 | Must | Lane C Runtime | `requested_changes` 状态机、下单前/成交后实时风控、告警接线与去重 | C1、G0-3、G0-5 | C-AC3 | todo |
| C4 | Must | Lane C UI | 按 G0-2 主域建设独立模拟详情页、风控规则/暂停/告警 UI、权限与空态测试 | C2、C3 API contract | C-AC4 | todo |
| C5 | Should | Lane C | `paper_trading/` 子包进一步拆分，行为零变化 | 183-B entry 已满足；C2/C3 稳定后 | C-AC5 | todo |
| D1 | Must | Lane D Test | 增强既有 full-pipeline 测试：RB0 fixture、mock LLM/provider、强制 robustness、事件/版本断言与清理 fixture | Gate 0；第一波即启动 | D-AC1 | todo |
| D2 | Must | Integrator | 最终 10 步 E2E、nightly 冒烟、证据矩阵与来源验收更新 | A/B/C Must gates、D1 | D-AC2 | todo |
| R1 | Release | Integrator | 只读复核 183-A/G/I 的安全、卫生和外部轮换证据 | 外部 owner | R-AC1 | blocked |

### 4.1 Lane A 验收契约

#### A-AC1：迁移

- fresh DB 从 base 升级到 head 后 4 表、必要索引和 FK 存在。
- current Alembic head 的非空数据库升级后既有数据可读。
- 曾由 `create_all` 建过同名表的 legacy DB 可升级，不因 table already exists 失败；结构差异被校验或补齐。
- A/C 并行 revision 合并后 `alembic heads` 仅一个 head。
- 迁移稳定后，生产初始化不再依赖 `_ensure_ai_research_schema_compatibility_sync`/`Base.metadata.create_all` 静默创建 A 表；兼容旁路应移除或仅在有截止日期的 legacy 模式启用。
- downgrade 只在隔离库演练；如数据回填不可逆，文档明确采用 forward-fix，不承诺生产无损 downgrade。

#### A-AC2：后端与 API

- 投研失败 fixture 断言 `ResearchPipelineEvent` 持久化，包含 stage/status/failure_reason/run/workspace 归属。
- versions list/detail/compare 覆盖成功、资源不存在和跨用户访问（404 或统一的非泄漏响应）。
- `api/strategy.ts` 六个相关方法均有请求路径、参数和响应测试。

#### A-AC3：前端

- 时间线 success/failed 事件展示 metrics；点击后可查看已授权的 input/output/code/metrics，敏感字段脱敏。
- 版本列表含 `created_at`；`metric_deltas`、`gate_deltas` 按结构化行展示 left/right/delta/operator/passed。
- 前端测试覆盖加载、错误、空态、切换 run 后数据隔离和键盘可达性。

### 4.2 Lane B 验收契约

#### B-AC1：指标唯一口径

- 固定 equity/trades fixture 经回测结果、Analytics adapter、AI 投研摘要三条路径后，canonical 字段数值和单位一致。
- canonical 字段只有一个计算入口；兼容 adapter 可以改名/换单位，不得重复计算。
- 旧字段兼容保留到迭代 185，并建立删除事项；新代码不得继续消费旧字段。

#### B-AC2：服务/API 测试

- `asset_spec_service`、`market_data_coverage_service`、`market_data_precheck_service`、`robustness_validation_service`、`execution_model`、`metrics_service` 各覆盖正常、边界、失败路径。
- `/data/trust` 每个端点覆盖认证、输入校验、成功和服务失败映射；新增代码覆盖率不降低仓库 blocking baseline。

#### B-AC3：自动预检与稳健性门控

- 资产/周期稳定后 debounce 自动预检；旧请求取消或结果不覆盖新选择；UI 列出具体 issue/severity/补齐建议。
- AI 投研和普通回测的生产提交均由服务端强制数据预检；前端自动调用只是体验增强，不能作为唯一门控。
- 生产提交若未运行稳健性、验证失败或验证服务异常，均不得创建或启动 paper unit。
- test/dev opt-out 只能通过环境配置启用且写审计；生产请求体无法绕过。

#### B-AC4：summary-first

- 新增显式 `BacktestSummaryResponse`，canonical metrics 的嵌套层级由 schema 固定；前端与后端契约测试必须发现顶层/`metrics` 层级漂移。
- 初始阻塞请求不包含 equity curve、drawdown 和 trades；在固定 10k 曲线点/1k trades fixture 下响应小于 64 KiB。
- 前端测试把 detail 人为延迟 2 秒时，summary 和页面骨架仍先展示；明细失败不清空 summary。
- payload、P50/P95 仅在记录基线环境后比较；不得只以主观“明显变快”验收。

#### B-AC5：期货专项检查

- 固定 RB0 fixture 覆盖正常换月、异常缺口、夜盘完整/缺失、节假日和交易日跨午夜归属。
- 异常大跳空默认是 warning，只有违反确定性覆盖规则才是 blocking error，避免把真实行情误判为坏数据。

#### B-AC6：过拟合面板方法一致性

- `OverfittingPanel` 的可选方法与后端/AI 投研契约一致，包含 `parameter_sensitivity`。
- 重跑事件携带选中的四类方法；参数敏感性结果有明确展示或通用结果卡，不落入 Monte Carlo 专用渲染分支。
- 组件测试覆盖选择、取消、重跑 payload 和参数敏感性结果。

### 4.3 Lane C 验收契约

#### C-AC1：结构化模型与兼容迁移

- 新增 `PaperReviewReport`、`LiveHandoffReview`、`RiskRule`、`PaperEquitySnapshot`，字段、索引、FK 和 user/workspace/unit/instance 归属跟随 G0-2；存在 account engine 映射时 `paper_account_id` 可选关联。
- 旧 run record/workspace JSON 可回填；一个迭代内双读，结构化表为写入真源；迁移重复执行/重试不产生重复数据。
- 运行告警复用既有 `Alert` 表并补齐主域 scope；`RiskControlService._alerts` 不再是查询真源，避免内存告警与 DB 告警双写分裂。
- 方案 B（永久 JSON）已从本迭代移除；如需恢复，必须新 ADR、来源 DoD 例外批准和重新验收。

#### C-AC2：资金曲线

- 创建模拟运行时写初始快照；成交和定时 mark-to-market/估值更新写后续快照，确保无成交期间也能形成连续资金曲线；相同幂等键重试不重复写入。
- 查询 API 支持时间范围、分页和降采样，统一 UTC 输出；无数据返回空集合而不是伪造 0 点。
- 查询标识和 FK 使用 G0-2 的 canonical runtime identity；跨用户访问返回非泄漏的 404/403；长期容量受 Gate G0-6 的保留/清理策略约束。

#### C-AC3：审核、实时风控和告警

- `requested_changes` 是独立合法决策：写审核记录和事件，保持 live 锁定，回到可继续优化状态。
- 下单前风控拒绝时 broker 的 submit 方法必须未被调用；风控服务异常按 fail closed 处理。
- 成交后检查账户/持仓/回撤；状态、快照和告警的事务边界明确，失败可重试且不重复告警。
- 订单失败、连接失败、风控拒单、回撤超限告警持久化到 `Alert`，包含类型、级别、canonical runtime scope 和去重键，可通过 API 查询；重启进程后仍可见。

#### C-AC4：详情与监控 UI

- 详情路由使用 G0-2 冻结的 canonical runtime ID（不得在无映射时硬编码为 `accountId`），展示权益、持仓、订单、成交、资金曲线和信号；各区有查询中、空态、失败和重试状态。
- 风控 UI 支持策略级/账户级规则、一键暂停和告警列表；危险动作有确认与审计结果反馈。
- 路由和 API 均做归属校验；前端不展示 secret、token、broker 原始凭据或未脱敏事件内容。

#### C-AC5：Should 拆包

- 仅移动 broker/runner/review 职责，不改变公开 API 和交易行为；既有 paper trading 测试全绿。
- 若拆包导致 Must 工作包延期，立即迁出，不影响 184 完成判定。

### 4.4 Lane D 验收契约

#### D-AC1：确定性 harness

- 复用并扩展现有 `test_ai_strategy_research_task_api_runs_generated_goal_full_pipeline`，引入固定 RB0 本地数据、mock LLM/provider、冻结时间和随机种子；测试零外网、可重复运行并自动清理账户/工作区。
- 从第一波开始构建，不能留到 A/B/C 全部结束后才准备。

#### D-AC2：10 步闭环

- PR blocking E2E 逐步断言：需求 -> 结构化确认 -> 生成 -> 回测 -> 优化 -> 稳健性 -> 模拟 -> 复核 -> 审核 -> 实盘准备。
- 断言每步事件、状态转换和关键 ID 关联；稳健性失败路径另测“不得进入模拟”。
- nightly 运行外部依赖冒烟；结果不阻塞普通 PR，但发布前至少有一次成功证据。

---

## 5. 并行波次、依赖和关键路径

### 5.1 执行波次

| 波次 | 可并行工作 | 集成门（Exit） |
| --- | --- | --- |
| Wave 0 | G0-1..G0-7；D1 fixture/harness 骨架 | 契约冻结、基线记录、热点文件 owner 明确 |
| Wave 1 | A1；B1/B2/B4/B5/B6；C1；D1 | 迁移草案、canonical tests、C schema、E2E skeleton 可 review |
| Wave 2 | A2/A3；B3；C2；C3 | A/B/C 后端 Must API 与行为测试全绿 |
| Wave 3 | C4；A/B/C 前端联调；必要兼容修正；C5 可选 | 各 Lane Release Gate 全绿，OpenAPI 无未审差异 |
| Wave 4 | D2 全链路、迁移矩阵、发布演练、证据收口 | 184 Exit Criteria 全部满足 |

### 5.2 关键路径

```text
Gate 0
  -> C1 结构化模型/兼容迁移
  -> C3 实时风控/告警/审核状态机
  -> C4 详情与监控 UI
  -> D2 10 步 E2E
  -> 总体验收
```

A1/A2/A3、B1-B6 和 D1 不在 C 主关键路径上，应并行推进。某任务 blocked 超过 1 个工作日，owner 必须在状态表记录阻塞原因、影响和可执行的解阻动作，并通知 Integrator。

### 5.3 共享热点文件所有权

| 热点 | 单一写 owner | 协作规则 |
| --- | --- | --- |
| `alembic/versions` / migration head | Integrator | Lane A/C 独立 revision；仅 Integrator 合并 head |
| `schemas/ai_strategy_research.py` | Lane B（门控契约） | Lane C 通过 schema PR/commit 串行合并，不并行直接改同一区块 |
| `StrategyPage.vue` / `useStrategyPage.ts` | Lane A UI | Lane B 预检优先抽组件；禁止继续把 C 详情页塞入该页面 |
| `BacktestResultPage.vue` | Lane B UI | A/C 只消费冻结的 canonical contract |
| `paper_trading_service.py` / `research/paper_handoff.py` | Lane C Runtime | C2/C3 先补 characterization tests，C5 最后移动代码 |
| OpenAPI/shared types | Integrator | 契约变更即时同步，不等每日状态会 |

---

## 6. 来源验收追踪矩阵

“来源 AC”指原始计划 A/B/C 各 5 条验收标准；“184 证据”指本计划工作包，不混用两种计数口径。

| 来源 AC | 来源标准摘要 | 184 工作包/证据 | 当前 |
| --- | --- | --- | --- |
| A-1 | 输入需求结构化并确认 | 既有能力回归 + D2 | baseline-pass |
| A-2 | 每次运行有完整时间线 | A2、A3、D2 | partial |
| A-3 | 每轮代码有版本记录 | A2、D2 | baseline-pass，补 API 证据 |
| A-4 | 能解释版本好/差 | A3 | partial |
| A-5 | 失败可定位阶段和原因 | A2、A3 | partial-test-gap |
| B-1 | 提交前明确数据是否足够 | B2、B3 | partial |
| B-2 | 多资产可筛选 | 既有能力回归 | baseline-pass |
| B-3 | 所有页面指标一致 | B1 | partial |
| B-4 | 稳健性通过后才进模拟 | B3、D2 | partial |
| B-5 | 回测结果首屏不依赖完整明细 | B4 | partial |
| C-1 | 达标后创建/启动模拟实例 | C3、D2 回归 | baseline-pass |
| C-2 | 持续记录订单/成交/持仓/权益 | C1、C2 | partial |
| C-3 | 观察期后生成复核报告 | C1、C3、D2 | baseline-pass，补结构化证据 |
| C-4 | 未审核不得进实盘准备 | C3、D2 | baseline-pass，补 requested_changes |
| C-5 | 实盘准备/运行前通过风控 | C3、D2 | partial-runtime |

所有 `baseline-pass` 仍需自动化回归证据，不能因来源验收曾判定通过而跳过回归。

---

## 7. 与迭代 183 的边界和发布门

| 183 项 | 2026-07-18 状态/影响 | 184 规则 |
| --- | --- | --- |
| 183-B 后端 god 文件拆分 | `app/services/research/` 基础切片已存在，entry condition 已满足 | 184-C 可启动；C5 仍是 Should，不重复统计 183 已完成工作 |
| 183-C 前端拆分 | `useStrategyPage.ts` 已抽出，但页面仍是共享热点 | 184-A 抽时间线/版本组件；C 详情页必须独立路由 |
| 183-A 安全授权 | 既有通用授权基线由 183 主导 | 184 新增 API 仍必须单独补归属和敏感字段测试，不能以“属于 183”豁免 |
| 183-G 仓库卫生 | 由 183 验收证据负责 | 184 只读复核，不提交日志、截图或运行 artifacts |
| 183-I 凭据轮换 | 外部 owner 行为，可能未完全闭合 | 作为 R1 Release Gate；不阻塞 184 代码合并，但阻塞来源计划最终改为“完成” |
| 183-E/F 质量门禁 | 已建立 ratchet/CI 基线 | 184 不得让大文件、mypy、覆盖率或依赖门禁回退 |

---

## 8. 状态同步与验收证据

### 8.1 更新节奏

- 每个工作日更新一次第 4 节状态；契约、迁移 head 或 blocking 风险变更即时更新。
- 每个工作包只有在 review 完成且证据齐全后才可设为 `done`。
- 每个 Wave Exit 由 Integrator 签收；不得绕过未关闭的 Gate 进入最终 D2。
- 计划变更必须注明原因、影响的来源 AC 和 Cut Line，不静默扩项。

### 8.2 证据格式

执行时在本迭代目录维护 `EVIDENCE.md`，每项至少记录：

| 字段 | 要求 |
| --- | --- |
| Work package / AC ID | 如 `B3 / B-AC3 / Source B-4` |
| Commit / PR / CI | 可定位的 revision 和 CI run |
| Automated test | 精确 test file 或 node id，含通过数量 |
| Migration/API evidence | schema assertion、single head、OpenAPI diff 等 |
| Manual check | 仅用于视觉/交互补充，不能替代行为测试 |
| Result / date / reviewer | pass/fail、日期、reviewer |

测试日志、截图和报告保留在 CI artifact，不提交仓库。`ACCEPTANCE.md` 的最终勾选应引用 `EVIDENCE.md`，不复制无法追踪的结论。

---

## 9. 发布、兼容与回退

| 变更 | 发布顺序 | 兼容窗口 | 回退/故障策略 | 触发条件 |
| --- | --- | --- | --- | --- |
| A/C schema migration | 先备份/演练，expand migration 先于应用 | 旧 JSON/旧字段保留至 185 | 优先 forward-fix；仅隔离库演练 downgrade | 升级失败、数据数/校验和不一致 |
| canonical 指标 | 先发布 canonical + 旧字段 adapter，再迁前端 | 到 185 删除旧字段 | 回退消费者；不得恢复双重计算 | 指标 fixture 数值漂移或页面不一致 |
| summary-first | 先 API 后前端 | 完整 detail 端点继续可用 | 前端可临时回退 detail，但记录性能退化 | summary 缺字段或错误率升高 |
| 稳健性强制 | test -> staging -> production | test/dev 可配置 bypass；prod 无请求级 bypass | 验证服务异常时保持 fail closed，暂停 promotion 而非跳过验证 | promotion 错误率/耗时越阈值 |
| C 主域与 JSON/告警迁移 | 先冻结 runtime ID 映射，再建表/回填，最后切结构化写入和 DB Alert 真源 | 一个迭代 | 读路径可临时回退 JSON；新表数据不删除；内存告警只作瞬时兼容 | ID 无法映射、回填计数不一致或告警查询缺失 |
| 实时风控/告警 | staging shadow 观测后切 enforce | shadow 只用于发布观察，不算验收完成 | 发现误拒单时暂停交易并回退规则版本，不关闭总门控 | 误拒单、漏拦截、告警风暴 |
| C5 拆包 | 所有 Must 行为稳定后 | 公共 API 不变 | revert 代码移动 | paper trading 回归失败 |

涉及交易安全的回退原则：宁可暂停 promotion/下单，也不能通过关闭稳健性或风控来恢复可用性。

---

## 10. 验证命令与环境约束

以下命令是实施后的目标命令。测试文件尚未创建时保持对应工作包为 `todo`，不得以 `rg` 命中替代行为验证。

### 10.1 后端定向验证

```bash
cd src/backend && pytest tests/test_iteration_184_migrations.py -q
cd src/backend && pytest tests/test_ai_research_direction_a.py tests/test_ai_research_versions_api.py -q
cd src/backend && pytest tests/test_asset_spec_service.py tests/test_market_data_coverage_service.py tests/test_market_data_precheck_service.py -q
cd src/backend && pytest tests/test_robustness_validation_service.py tests/test_execution_model.py tests/test_metrics_service.py tests/test_data_trust_api.py -q
cd src/backend && pytest tests/test_paper_equity_snapshot.py tests/test_paper_risk_runtime.py tests/test_paper_review_models.py -q
cd src/backend && pytest tests/test_iteration_184_full_loop.py -q
```

迁移测试必须由 `test_iteration_184_migrations.py` 创建隔离临时数据库，覆盖 fresh/current/legacy-create_all 三种基线。禁止直接对默认 `.env` 指向的数据库运行 `alembic upgrade/downgrade` 作为验收。

### 10.2 前端验证

```bash
cd src/frontend && npm run test -- --run src/__tests__/views/StrategyPage.test.ts src/__tests__/api/strategy.test.ts
cd src/frontend && npm run test -- --run src/__tests__/views/BacktestResultPage.test.ts src/__tests__/components/OverfittingPanel.test.ts
cd src/frontend && npm run test -- --run src/__tests__/views/PaperTradingDetailPage.test.ts src/__tests__/views/RiskControlPage.test.ts
cd src/frontend && npm run typecheck
cd src/frontend && npm run build
```

### 10.3 全量与 E2E

```bash
cd src/backend && pytest -m "not e2e" -q
cd src/frontend && npm run test -- --run
cd src/frontend && npm run test:e2e -- --grep "research loop"
```

PR E2E 必须零外网、使用固定 RB0 fixture；nightly 外部冒烟使用单独 CI job 和凭据，不复用开发者本地账户。

---

## 11. 风险登记册

| 风险 | 概率/影响 | Owner | 触发信号 | 预防与缓解 | Contingency |
| --- | --- | --- | --- | --- | --- |
| legacy `create_all` 表与 Alembic 冲突 | 中/高 | Integrator | table exists、列/索引差异 | 三基线迁移测试、expand-only、备份 | 停止发布，forward-fix revision |
| A/C 并行产生多个 migration head | 高/中 | Integrator | `alembic heads` > 1 | 独立 revision + 单一 merge owner | 合并 revision 后重跑三基线 |
| 两套 paper runtime ID 无法映射 | 高/高 | Lane C / Integrator | 详情、快照或告警只能覆盖其中一套运行时 | G0-2 sequence diagram、真实主闭环 fixture、禁止 account-only FK 先行 | 暂停 C1-C4，先交付映射 adapter 或收敛单一主域 |
| 指标数值或单位漂移 | 中/高 | Lane B | canonical fixture 差异 | characterization tests、单一计算入口 | 保留 adapter，阻止删除旧字段 |
| 稳健性强制导致 promotion 大量失败/变慢 | 中/中高 | Lane B | 失败率/P95 超基线 | staging 观测、明确超时、缓存可复用结果 | fail closed 并暂停 promotion 排障 |
| JSON 回填漏数/重复 | 中/高 | Lane C | 行数、唯一键、checksum 不符 | 幂等回填、双读对账 | 保持 JSON 读路径并 forward-fix |
| 实时风控误拒单或漏拦截 | 中/高 | Lane C Runtime | shadow/enforce 结果偏差 | 固定规则 fixture、broker-not-called 断言 | 暂停策略，回退规则版本 |
| 告警重试形成风暴 | 中/中 | Lane C Runtime | 同一事件重复告警 | dedupe key、幂等写、速率限制 | 暂停通知通道但保留审计写入 |
| 资金快照长期膨胀 | 高/中 | Lane C | 增长率超 G0-6 预算 | 降采样、分页、保留与清理策略 | 降低采样频率，异步归档 |
| 新详情/API 引入 IDOR 或敏感数据泄漏 | 中/高 | Lane C / Security reviewer | 跨用户访问成功、原始凭据返回 | 归属测试、response schema、脱敏 | 阻止发布并回滚 API |
| 共享热点文件冲突 | 高/中 | Integrator | 同时修改同一区块 | 单一写 owner、小 PR、契约优先 | 暂停后合并泳道，重新 rebase/review |
| E2E 对外部 LLM/行情不稳定 | 高/中 | Lane D | flaky/超时 | PR 固定 fixture + mock；nightly 分离 | 不以外部 job 阻塞 PR，但阻塞发布证据 |
| 183-I 外部轮换未完成 | 中/高 | External owner | 无旧凭据失效证据 | R1 明确 owner/证据链接 | 184 代码可完成，来源总验收不得改“完成” |

---

## 12. 最终 Exit Criteria

- [ ] Gate 0 七项决策全部关闭并有 review 证据。
- [ ] A/B/C 所有 Must 工作包为 `done`，Should 未完成项已明确迁出。
- [ ] 来源 A/B/C 15 条验收标准全部由第 6/8 节证据追踪，不能只写主观结论。
- [ ] fresh/current/legacy-create_all 三类迁移测试通过，最终 Alembic 单一 head。
- [ ] 新增 API 完成认证、跨用户隔离和敏感字段脱敏测试。
- [ ] canonical 指标、summary-first、自动预检、生产稳健性强制均有确定性自动化测试。
- [ ] 资金曲线、审核三决策、实时风控、告警、详情/监控 UI 的 Must 契约全部通过。
- [ ] PR 10 步 E2E 可重复全绿，nightly 外部冒烟至少有一次成功证据。
- [ ] 全量后端非 E2E、前端 Vitest、typecheck、build 和 blocking CI 全绿且基线不回退。
- [ ] 发布/回退矩阵已演练；无未关闭 P0/P1。
- [ ] R1 外部发布门有可核验证据；若未关闭，184 可标“代码完成”，但来源计划与 `ACCEPTANCE.md` 不得标“全部完成”。
- [ ] `EVIDENCE.md` 完整，`ACCEPTANCE.md` 的最终结论引用证据并由 Integrator 签收。
