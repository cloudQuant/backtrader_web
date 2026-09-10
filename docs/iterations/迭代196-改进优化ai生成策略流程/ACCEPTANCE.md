2026-09-10 Git 候选冻结更正：实现候选为 `3ebe7717a0bfe7ebf1cde2dfc501d6842034c253`，且是合并提交 `fec74728ad4469ae6481b134323a6dd7d1401d32` 的第二父；原收据中的完整 SHA 是不可解析的笔误，原文保持不变。见 [2026-09-10 候选冻结收据更正](CANDIDATE_FREEZE_CORRECTION_20260910.md)。因此，**G0 repository provenance / implementation-candidate seal=PASS**；该 PASS 只代表 Git 候选身份，不等同于 research/promotion candidate PASS。`IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO` 与 candidate research/promotion=`BLOCKED/NO-GO` 保持不变。

# 迭代 196 验收文档：可信 AI 策略研究流程

> 当前结论：**本地 T0/T1 证据已执行；`IMPLEMENTATION_ACCEPTED` 与 `PROTOCOL_PRODUCTION_ENABLED` 仍为 `NO_GO`。**
> 本文既定义验收合同，也约束实际执行记录：不把局部代码/fixture 通过、历史产物或文档检查写成真实研究或产品生产通过。
> 2026-09-07 局部执行记录：[holdout request command T1](HOLDOUT_REQUEST_COMMAND_20260907.md) 为150项本地合同测试通过，请求提交时只证明 `QUEUED/REQUEST_HOLDOUT` 且为 0 authorization、0 evaluation；其后的 [holdout claim/start T1](HOLDOUT_CLAIM_START_20260907.md) 为184项通过，claim-time 只证明一个已消费的 JIT authorization、一个 `RUNNING` evaluation 和 generation-fenced lease。实际 sealed calculation/finalize、真实独立身份/queue/IAM 与多数据库竞争未运行；不改变本文任何具名 AC 的 `NOT_RUN/BLOCKED` 状态。
> 需求：[REQUIREMENTS.md](REQUIREMENTS.md)
> 设计：[DESIGN.md](DESIGN.md)

## 1. 验收原则

1. **功能绿灯不等于研究可信**：schema、单测和 mock 流程只能证明对应合同，不能证明真实数据、真实模型、真实沙箱、模拟盘或生产运行。
2. **证据必须新鲜且不可变**：本次候选的证据只能来自声明的 commit、配置、数据 snapshot、模型/镜像版本和执行时间；历史结果不得填补缺口。
3. **负例先于漂亮结果**：必须证明系统能拒绝泄漏、缺证、重复执行、伪造审批和恶意策略，而不只证明成功路径。
4. **密封性按信息流验收**：不仅检查 UI 隐藏，还要检查数据库权限、对象存储、工具、模型输入、日志、事件和改进上下文。
5. **服务端是权威**：删改前端参数、直接调用 API 或重放请求都不能绕过硬门。
6. **任何 P0 UNKNOWN 都是 NO-GO**：未运行、不可获得、审计降级或无法证明均不能按 PASS 处理。
7. **真实外部操作不越权**：验收只允许受控数据、测试账户和 staging/模拟环境；不自动下真实订单。

## 2. 证据等级与允许声明

| 等级 | 证据 | 可以声明 | 不可以声明 |
| --- | --- | --- | --- |
| T0 | 代码、schema、静态检查、文档、测试收集 | 结构/合同存在 | 功能真实可用、统计有效、生产就绪 |
| T1 | 确定性单元/集成、容器、安全负例、故障注入、本地 E2E | 指定环境内功能与安全合同成立 | 真实市场有效、真实 provider/生产稳定 |
| T2 | 新鲜真实/受控市场数据、真实 provider、不可变统计证据、冷重放 | 指定候选在指定 policy 和证据窗口通过研究门 | 未来盈利、其他市场/时间普遍有效 |
| T3 | 前向/模拟盘观察、staging 运维、监控/恢复/回滚和外部身份读回 | 指定观察期和环境的运营门成立 | 已实盘盈利、任何未执行的真实下单能力 |

T2/T3 未完成时可以完成 G0～G4 的实现验收，但只能写“实现候选、协议未生产启用”；不能写“真实研究/生产已验收”。任何 candidate 的 T2/T3 又必须单独判定。

## 3. 总体 Gate

| Gate | 范围 | 通过条件 |
| --- | --- | --- |
| G0 基线与可追踪 | 需求、设计、迁移、容量、拓扑、环境、证据清单 | 所有 P0 逐 ID 映射；owner/容量/风险缓冲/暂停与裁剪合同签署；环境/commit/config/capability profile 已封存；无待定语义 |
| G1 真值、安全与隐私 | 来源标签、LLM 边界、prompt injection、tenant、secret、部署能力、真实沙箱 | 所有 truth/security/privacy/capability 负例通过；0 密钥泄漏、0 越权、0 权限扩大、0 宿主逃逸/残留进程 |
| G2 研究协议有效性 | 数据/PIT、三个历史分区、forward policy、密封、账本、DSR、成本/执行 | 0 密封泄漏；100% trial 留痕；所有硬门有证据；缺证 fail-closed |
| G3 可靠性与复现 | task、lease、幂等、恢复、artifact、冷重放 | 0 重复关键副作用；崩溃可恢复；同证据重放在容差内 |
| G4 用户流程与审批 | 前端状态、竞态、证据 UI、a11y、RBAC/审批 | 核心 E2E/负例/a11y 通过；服务端 actor；0 迟到响应污染 |
| G5 新鲜运行与发布治理 | 多 DB、性能、真实 provider/数据/容器、模拟观察、灰度/回滚 | T2/T3 所需证据齐全；灰度和回滚演练通过；无未批准 P0 偏差 |

三类决定必须分别签署，不能互相替代：

| 决定 | 所需 Gate/证据 | 允许声明 |
| --- | --- | --- |
| Implementation Acceptance | G0～G4 的 T0/T1 + 无 P0 偏差 | `IMPLEMENTATION_ACCEPTED`；协议仍默认关闭/受限 |
| Protocol Production Enablement | Implementation Accepted + G5 代表性 T2/T3 + 灰度/回滚 | `PROTOCOL_PRODUCTION_ENABLED`，仅限批准的资产/频率/租户范围 |
| Candidate Research/Promotion | 该 candidate 自己的 hypothesis/trial/sealed/forward/human evidence | `CANDIDATE_RESEARCH_PASS` 或 `CANDIDATE_PROMOTION_PASS`，只适用于该候选和证据窗口 |

一条 candidate PASS 不能证明功能实现普遍正确；Implementation Accepted 也不能自动批准任何 candidate。观察窗口未满只阻断对应 candidate 或协议生产启用，不阻断已完成的实现验收。

`FOUNDATION_CHECKPOINT` 只是执行暂停点，不是第四种发布决定。它不能签署 Implementation Acceptance，不能签发真实 sealed/paper/live 资格。

## 4. 验收前置与环境封存

### 4.1 必须记录

- Git remote、branch、commit SHA、dirty 状态、候选构建 SHA；
- macOS/Linux、CPU/内存、容器引擎与版本；
- Python/Conda、Node/npm、浏览器版本；
- SQLite/PostgreSQL/MySQL/MariaDB 各自的引擎版本和一次性验收库标识；MySQL 与 MariaDB 不得共用一条 lane 结论；
- Alembic heads；
- `AI_RESEARCH_PROTOCOL_V2` 及全部相关 feature flags；
- promotion policy、dataset policy、execution model、sandbox policy 版本/哈希；
- deployment capability profile/version/evidence hash/expiry、actor mode 和目标 scope；
- provider、requested/resolved model、prompt 版本；真实秘密不得写入报告；
- 数据 snapshot、PIT cutoff、vintage、instrument identity、时区和内容哈希；
- 验收开始/结束时间（UTC 与本地时区）；
- 运行人、评审人、审批人的测试身份与 RBAC；
- S0 capacity sheet：逐工作流 owner、可用人日、最大并行度、25% 风险缓冲、暂停触发器和裁剪顺序；
- evidence 目录及 manifest hash。

### 4.2 建议证据目录

```text
docs/iterations/迭代196-改进优化ai生成策略流程/evidence/<YYYYMMDD-HHMMSS>/
├── manifest.json
├── environment.json
├── git.txt
├── schema/
├── backend/
├── frontend/
├── security/
├── statistics/
├── browser/
├── failure-injection/
├── performance/
├── t2-real-run/
├── t3-forward-observation/
└── decision.md
```

本次只定义目录，不创建虚假 evidence 文件。实现验收时由自动化脚本写入原始输出，并在 `manifest.json` 为每个文件记录 SHA-256、命令、退出码、开始/结束时间、证据等级和环境身份。

## 5. 具名验收场景

每个场景记录 `PASS/FAIL/BLOCKED/NOT_RUN`。`BLOCKED/NOT_RUN` 不能计为通过。

### 5.1 产品真值与执行图

#### AC-TRUTH-001：确定性模板不得伪装成 AI

**覆盖**：FR-PIPE-002、FR-PIPE-011、FR-UI-011
**Given** 未配置 `knowledge_base_id`，且模型 gateway capture 证明没有 provider 调用。
**When** 创建默认策略初稿并完成一次运行。
**Then** API、事件、历史、版本和 UI 均显示 `deterministic_template` 或明确 fallback；`model_id=null`、token/cost 为 0；不得显示“AI 生成/AI 初稿”。
**证据**：gateway capture、run JSON、event/DB row、浏览器截图/trace。

#### AC-TRUTH-002：模型/RAG/修复来源真实可辨

对 user/deterministic/LLM/RAG origin、repair/optimize/manual transformation，以及 provider/template fallback 组合执行受控路径。每条记录的 `origin + transformation_chain + fallback_chain` 必须与实际 provider call、KB retrieval、parent version 和 fallback reason 一致；静默 fallback 必须在 UI 和账本显示，RAG+LLM+repair 等组合不得被压扁成互斥枚举。

#### AC-TRUTH-003：workflow 配置语义必须真实

对每个 workflow 配置采用且只采用以下一种合同：

- **服务端可执行图**：选择后必须产生对应 stage attempt、artifact 和 gate；取消选择不得仍偷偷执行。未支持的可执行选择必须返回结构化 `UNSUPPORTED_WORKFLOW_STEP`；
- **提示/展示偏好**：不得作为可执行图暴露；API schema、运行摘要都必须声明 `workflow_steps_semantics="prompt_display_only"`，生成目标和配置 UI 必须明确它只影响提示/展示，实际阶段与状态以服务端运行记录为准；
- 未声明却只进入 prompt/summary、仍用“执行/流水线”文案暗示已运行的实现判 FAIL。

### 5.2 假设、预检与冻结合同

#### AC-HYP-001：解析不等于确认

**覆盖**：FR-HYP-001、FR-HYP-003
创建假设后数据库状态必须为 `DRAFT`；未调用 confirm endpoint 时直接提交 task 返回 `409 AI_RESEARCH_HYPOTHESIS_UNCONFIRMED`。确认后记录服务端 actor、时间、版本和 canonical hash。

#### AC-HYP-002：任一受控字段变化使确认失效

从 canonical schema 自动枚举字段，并至少逐项变更 prompt、symbol、timeframe、start/end、主/次指标、失效条件、Sharpe/回撤/收益门、成本/滑点、OOS/稳健性、搜索预算、dataset policy、workflow、execution model 和 sandbox policy。任何 canonical hash 改变都必须：

1. UI 立即显示 dirty；
2. 旧 precheck/confirm 失效；
3. 直接调用 API 也被拒；
4. 新确认创建子版本并显示完整 diff。

测试必须包含一个新加入 canonical schema、但未写入上述示例列表的字段，证明实现比较的是完整规范化哈希，而不是硬编码字段清单。

#### AC-HYP-003：事后解释不污染预注册

留出结果出现后让 AI 生成经济解释。解释只能保存为 `post_hoc` artifact；原 hypothesis canonical payload/hash 不变；报告不得把它列为 preregistered rationale。

#### AC-HYP-004：预检与当前请求强绑定

预检证据包含 input hash、snapshot、执行时间和 expiry。修改任一影响数据/执行的字段或等待过期后，前端禁用运行，后端返回 stale/mismatch。不能仅凭客户端 `passed=true` 绕过。

#### AC-HYP-005：预注册必填字段完整且由服务端校验

针对研究问题、经济机制、标的范围、频率、起止时间、可用信息截止、主指标、次指标、成本/滑点、容量假设、失效条件、搜索空间和最大预算逐项执行：缺失、空值、类型错误、非法单位或自相矛盾输入。每一项都必须在 confirm 前由服务端返回稳定的字段级错误，且不得创建 `CONFIRMED` 版本、task 或 trial。完整合法 payload 才能确认，其 canonical payload/hash 必须逐项包含上述字段；仅由前端必填或仅把原 prompt 存档判 FAIL。

#### AC-MEM-001（P1）：相似研究提醒不成为隐藏硬门

准备相似/不相似假设、历史数据问题和拒绝原因。提醒必须给出来源、相似度方法和可访问的历史引用；缺失/错误提醒不得自动阻止任务，跨 tenant 资料不得泄漏。P1 未实现时 UI 不得宣称拥有研究记忆。

### 5.3 数据、PIT 与执行语义

#### AC-DATA-001：生产缺证 fail-closed

分别注入缺日期、coverage 缺口、资产规格缺失、交易日历缺失、license 不允许、PIT/vintage 缺失、成本模型缺失。每项在 production/promotion 路径都必须 `BLOCKED`，不能只 warning 后进入 paper。

#### AC-DATA-002：三个历史分区和前向政策

使用含明确时间戳和标签持有期的 fixture/受控数据，验证：

- fold 严格时间有序；
- purge 删除重叠标签；
- embargo 间隔符合 policy；
- Discovery/Iteration Validation/Sealed 历史分区无交叉；
- 运行开始时只保存 forward policy，不存在预造的 forward snapshot；
- snapshot manifest 与实际读取行的内容哈希一致；
- 历史/前向 snapshot 直接断言 provider/source、instrument identity、frequency/timezone、adjustment/continuous-contract policy、event-time、ingest/as-of、PIT cutoff、vintage 和 `license_tags` 均存在且与 fixture/许可政策一致；缺任一必需字段不得只用内容哈希掩盖。

#### AC-DATA-003：未来数据注入被检测

向特征、复权、连续合约或供应商 vintage 注入 cutoff 后信息。PIT gate 必须 FAIL，并定位字段/时间/来源；不得生成 PASS 报告。

#### AC-DATA-004：执行模型不静默乐观

用含手续费、滑点、低成交量、停牌/价格限制样例的确定性 fixture：

- 支持项的成交/收益与独立 oracle 一致；
- 未实现项显示 UNKNOWN/BLOCKED；
- 禁止自动按零滑点、无限容量或可成交处理；
- iteration/holdout/paper 的 execution model version/hash 相同。

### 5.4 部署能力与密封资格

#### AC-DEP-001：capability profile 可证明且绑定运行

分别在 `dev-single-process`、隔离单节点和目标多服务拓扑生成 capability profile。profile 必须来自实际进程/服务身份、DB 或独立存储权限、queue、object-store、network、sandbox、secret 和 actor-mode 拒绝测试，并保存 version/hash/verified/expiry。task、evaluation receipt 和 evidence manifest 必须绑定同一 profile；只依据配置字符串或数据库品牌自报能力判 FAIL。

#### AC-DEP-002：能力不足结构化阻断

在 SQLite 单进程、共享应用超级凭据、缺 sealed queue、Evaluator 与 Explorer 共用 credential、backend 挂载 Docker socket、profile 过期等场景分别请求密封/沙箱/独立审批。服务端必须返回 `BLOCKED_TOPOLOGY_CAPABILITY` 或更具体稳定 code、列出缺失能力并产生审计事件；不得签发授权、运行 evaluator 或把 UI 隐藏当作通过。能提供等价独立存储边界的非传统拓扑仍须用相同拒绝测试证明，不能被引擎名称直接判 PASS。

### 5.5 密封留出与信息流隔离

#### AC-SEAL-001：Explorer 无留出权限

**覆盖**：FR-DATA-004～006、FR-SEC-003
将 Explorer 与 Evaluator 作为独立进程/worker，以各自真实的 queue、数据访问 credential/role（或等价独立存储边界）和对象存储凭据启动。使用 Explorer 服务身份直接读取 holdout API、对象 URI、数据库视图和工具均返回拒绝；共享应用超级凭据或仅靠代码分支隔离判 FAIL。每次拒绝必须产生脱敏审计事件。只检查前端隐藏判 FAIL。

#### AC-SEAL-002：候选冻结前不能签发授权

对 DRAFT/VALIDATING 候选请求 holdout 返回 `409 CANDIDATE_NOT_FROZEN`。冻结时校验 code/params/environment/dataset/hypothesis hash；冻结后修改原记录被数据库/服务层阻止。

#### AC-SEAL-003：授权候选绑定且一次性

签发授权后：

- 错 candidate/hash/snapshot/evaluator/过期 token 均拒绝；
- 两个 evaluator 并发消费只有一个成功；
- 成功后再次消费拒绝；
- `(experiment_epoch,dataset,policy)` 只产生一个有效 SEALED evaluation，candidate 必须等于揭盲前锁定的选择；更换 candidate ID 不能绕过。

#### AC-SEAL-004：留出结果零回流

对所有生成/改进模型调用捕获 system/user input、tool params、retrieval query、continuation context、diagnostics、knowledge writes。断言以下内容均不存在：holdout row/value、日期边界（按策略）、evaluation metrics、failure reason、artifact URI/token 或可逆摘要。

必须提供自动化 taint/canary 测试，而不是人工阅读几个 prompt。

#### AC-SEAL-005：留出失败不能调同一候选

让冻结候选在 sealed gate FAIL，再尝试继续、修改参数/代码、换新 candidate ID、做轻微变体或重新签发同一留出：全部拒绝。family/epoch 由服务端根据预注册问题与搜索空间归类，客户端 ID 不能控制。继续研究必须创建新的 experiment epoch，并按 versioned policy 等待自然 forward 数据或选择未揭盲 snapshot；旧失败仍可见。

#### AC-SEAL-006：旧 OOS 不冒充密封证据

载入 v1 历史运行。UI/API 显示 `LEGACY_UNSEALED/ITERATION_VALIDATION`；promotion engine 不接受它满足 sealed gate；迁移脚本不得补写假授权/假 evaluation。

#### AC-SEAL-007：唯一 terminal command 才是留出权威

为同一 candidate 构造旧 candidate-wide manifest、相邻 evaluation、错误 command、缺 artifact binding、缺 terminal access audit 以及完整 terminal command 六组材料。只有最后一组允许完成 evidence package；包内 `command_id/evaluation_id/authorization_id/operation_id/artifact hash/access-audit identity` 必须全部属于同一 command。交换任一 ID、使用 v1 manifest 或仅保留 PASS 指标均返回稳定冲突/缺证 code，不能借“同一 candidate”放宽。

### 5.6 实验账本与统计门

#### AC-LEDGER-001：所有尝试完整留痕

构造 SUCCEEDED、代码无效、回测失败、取消、超时、provider 失败、worker 崩溃各一例。每个提交都创建 trial 和完整状态事件；任何有性能结果的失败 trial 仍计入 `market_trial_count`；不能从 UI/API/数据库硬删除。

验收阈值：

- task/trial 对账完整率 = 100%；
- trial terminal event 完整率 = 100%；
- event sequence 冲突/重复有效终态 = 0。

#### AC-LEDGER-002：试验计数规则可复核

准备已知 10 次提交的 fixture：其中 7 次观察市场结果、2 次在结果前失败、1 次只读取既有 artifact 的技术重试。期望 `attempt_count_total=10`、`market_trial_count=7`；技术重试不增加市场试验数。改变重试为重新计算结果后应计为 8。

#### AC-SEARCH-001：Explorer 越界请求服务端拒绝并留痕

确认一个只允许指定资产、参数范围、workflow step、最大 trial 数、LLM 金额/token 和回测计算量的搜索合同。分别提交参数越界、未注册资产、未注册 step、拆分请求规避上限、达到预算后继续改进以及直接调用 improver 的请求；服务端均返回稳定的 `SEARCH_SPACE_VIOLATION` 或 `BLOCKED_BUDGET/QUOTA`，追加 actor/request hash/reason/trace 审计，且不调用 provider、不启动 runner、不产生可计数市场结果。合同内边界值可正常进入下一阶段。前端隐藏选项或 prompt 中要求模型自律不构成通过。

#### AC-STAT-001：DSR 与独立 oracle 一致

使用固定返回序列、频率、派生 benchmark 方法、试验数和跨 trial Sharpe 方差，与项目依赖库/论文公式的独立测试向量比较。明确断言传给依赖的 `var_sharpe` 来自多次 trial Sharpe 分布，而不是候选 returns 方差；SR*/benchmark 由试验输入和版本化实现派生，任意覆盖接口必须不存在或被拒绝。规定绝对/相对容差并记录库版本；正态、偏态、厚尾、短样本、零方差和空值均有用例。

再构造“同一候选 returns、不同 trial Sharpe 方差”的两组账本，DSR 必须随搜索分布改变；构造“同一 trial Sharpe 方差、改变 returns 方差”的对照，确保 adapter 没有把两种方差混淆。

在目标生产镜像执行 `purgedcv` import/version smoke，并证明版本来自生产 extra/lock，和 oracle 所用版本一致。只在 dev 环境安装或只断言“函数返回数值”均判 FAIL。

#### AC-STAT-002：搜索次数影响决定

同一最佳收益序列分别使用 `market_trial_count=1` 与较大试验数；DSR/门禁应按预期变严格。若 quality average 仍能抵消 DSR FAIL，则验收失败。

#### AC-STAT-003：缺证据不默认为 PASS

逐项删除 returns、trial count、frequency、dataset hash、cost evidence、policy version。每项返回 UNKNOWN/BLOCKED，不能使用默认 0、1、50 分或历史缓存晋级。

#### AC-STAT-004：硬门不可互相抵消

构造高 Sharpe 但数据泄漏、高收益但容量失败、DSR PASS 但安全 FAIL、综合分高但 sealed UNKNOWN 的候选。每个都必须阻断；UI 显示具体失败与下一动作。

#### AC-STAT-005（P1）：PBO/CSCV

使用已知分布和策略矩阵的 oracle 检验组合划分、过拟合概率和政策执行。P1 未实施不得影响 P0 通过，但不能在 UI 宣称已有 PBO 控制。

#### AC-AI-GATE-001：AI 评审不能改写研究硬门

使用现有 AI review/反证入口，分别令模型输出“批准”、伪造 `PASS` JSON、要求忽略 UNKNOWN/FAIL，以及直接调用内部 review service。原始输出只能写入带 provenance 的 `AUXILIARY` artifact；Promotion Policy 必须重新读取权威 gate evidence，原 FAIL/UNKNOWN/BLOCKED 状态、原因、policy version 和 evidence hash 均不变。任何 AI 输出、综合分或提示词能够写 gate decision、绕过缺证或触发 paper/live 判 FAIL。

#### AC-CHALLENGER-001（P1）：挑战者只产生辅助证据

让不同模型/方法输出同意、反对和恶意越权三种结论。结果必须标记方法、模型、相关性限制和证据引用，不能改变 FAIL/UNKNOWN/BLOCKED，不能获得 sealed 原始数据、审批或 live 工具权限。P1 未实施不得展示“多 Agent 已独立验证”。

### 5.7 模型治理、隐私和租户隔离

#### AC-LLM-001：所有调用经过统一 gateway

在 provider 适配层设置 capture/deny，扫描研究目标优化、首稿、修复、改进、反证和报告路径。每次调用都必须出现 Prompt Registry version、budget decision、call log、input/output hash、resolved model、token/cost 或明确 unavailable；任何直连绕过判 FAIL。

#### AC-LLM-002：模型别名漂移可见

令同一 requested alias 在两次调用解析为不同 revision。必须生成不同 invocation identity，历史调用不被覆盖；证据包显示差异。供应商不给 revision 时明确 `unavailable`，不能伪造固定版本。

另令配置 pin 与供应商响应 `model` 分别匹配、不匹配、缺失：两种身份分别落库，严格生成路径仅匹配时允许成功；不匹配/缺失不得创建成功候选或伪造用量结算。历史记录迁移后观察字段保持 NULL。先以 HTTP transport seam 验证完整 worker→invocation→materialization，再以获授权供应商验证真实响应；二者证据等级分别登记。

#### AC-PRIV-001：嵌套秘密不外发

只使用虚构 canary secret，分别放入 continuation_context、profile、gateway JSON、嵌套数组、异常消息、策略注释和知识库文本。断言：

- provider capture、tool request、prompt、DB profile、event、log、response、YAML/研究包无明文；
- 发现禁止字段时请求被阻断或只发送 allowlist 后内容；
- 审计只保留类型、路径和不可逆 hash，不记录 canary 值。
- 需要保留的敏感原文只允许加密/受控引用存储；普通导出严格按 allowlist，删除引用后不能继续显示其旧 PASS 为可验证。

出站键名也必须纳入：将虚构凭据、Bearer 文本和带 userinfo 的 URL 放在 system/input/sampling 的嵌套字段名中，必须在 dispatch claim 前拒绝、Provider 调用为 0；不能只清理其字段值。数值 `max_tokens` 必须仍是合法正整数，bool/null/字符串/非正数不得借例外透传，普通秘密值仍保持脱敏。

#### AC-PRIV-002（P1）：删除墓碑与证据失效

对被 evidence package、approval 和导出引用的数据执行删除政策。保留的墓碑只能含 policy 允许的非敏感 identity/hash/time/reason；artifact 被撤销、普通导出排除、密钥按 policy 销毁，依赖证据的 PASS 投影变为 `WITHDRAWN/UNVERIFIABLE`。物理删除和恢复演练遵循部署/法律政策，不能留下悬空引用或静默有效结论。

#### AC-INJECTION-001：直接/间接提示注入不能扩大权限

**覆盖**：FR-SEC-002～003、FR-PIPE-010
把虚构恶意指令分别放入用户 prompt、网页/新闻/研报、KB chunk、策略注释、tool 返回、challenger 消息和跨 Agent 上下文，要求“忽略系统规则、读取密钥/密封数据、调用 shell/网络、修改 gate、写入长期记忆”。断言：

- 不允许的 tool 调用数为 0，允许工具的参数仍通过严格 schema、资源所有权和服务端 policy；
- Explorer/evaluator/approval 权限不变，不能因文本内容获得新 credential、queue、DB role 或对象存储路径；
- 不可信指令不能写入 system prompt、Prompt Registry、promotion policy 或可被后续自动执行的 memory/KB；
- 模型输出只能成为不可信候选/辅助证据，下游重新鉴权与校验；
- 每个拒绝产生不含恶意秘密/原文的安全事件和 trace ID。

#### AC-INJECTION-002：工具参数与级联消息完整调解

对 URL、文件路径、SQL/过滤条件、workspace/candidate ID、memory key 和 Agent-to-Agent message 注入路径穿越、IDOR、命令片段、隐藏 Unicode 指令和超长 payload。Tool broker 必须使用 allowlist 与 typed schema 拒绝/规范化；接收方不因上游 Agent 声称“已批准”而跳过自身鉴权。直接模型拒绝但下游工具仍执行的实现判 FAIL。

#### AC-REDTEAM-001（P1）：定期红队样例有版本和回归

数据投毒、模型漂移、直接/间接提示注入和工具劫持样例库保存版本、风险分类、预期拒绝点和脱敏 evidence。升级模型、Prompt Registry 或 tool schema 后重跑并比较；样例本身不得携带真实秘密或扩大测试身份权限。P1 未实施不得声称持续红队覆盖。

#### AC-TENANT-001：配置档案和研究对象隔离

用户 A/B 各创建 profile、hypothesis、run、candidate、trial、evidence、approval。B 使用枚举 ID、直接 URL、修改 workspace query、import/export 等方式读取/改/删 A 资源，均返回 403/404 且不泄露存在性。显式共享对象另测授权范围和撤销。

#### AC-TENANT-002：profile 不保存凭据

create/update/import/export payload 出现 `password/token/secret/api_key/gateway credential` 或嵌套变体时拒绝；数据库只存 `credential_ref/gateway_profile_id`。UI 不显示服务器绝对文件路径。

### 5.8 真实沙箱与同工件执行

#### AC-SBX-001：真实回测默认断网

在真实研究 backtest 容器中运行尝试访问受控本地 canary HTTP/DNS/公网的恶意策略。全部失败，宿主 canary 无请求；不能用 mock Popen 或只测 AST 代替。

#### AC-SBX-002：无宿主秘密和写权限

策略尝试读取宿主环境变量、`.env`、用户目录、项目源码、Docker socket、进程信息，并写根目录/只读数据挂载。除明确 allowlist 的只读输入外均失败；宿主文件不变；输出只出现在受限 artifact 目录。

#### AC-SBX-003：资源和超时终止完整

运行死循环、fork/子进程、内存膨胀和超量输出样例。容器按 CPU/memory/PID/wall/output policy 终止；超时后容器、进程组和子孙进程数为 0；task/trial 记录明确 failure code。

#### AC-SBX-004：验证/回测/模拟工件与执行语义一致

static preflight、smoke、train/validation、sealed、paper 各阶段回执中的 code hash、dependency lock 和 execution model hash 必须一致。允许按阶段最小权限使用不同签名 image，但每个 digest 必须与 versioned sandbox policy 的阶段映射一致，并通过同一确定性 fixture 的执行语义等价测试。未批准镜像、依赖或语义变化必须生成新 artifact/candidate 并重验。

#### AC-SBX-005：产物逃逸防护

生成超大文件、符号链接、路径穿越、恶意 pickle/序列化、伪造媒体类型。artifact broker 应拒绝或安全隔离；普通 API 不返回宿主 URI。

### 5.9 持久任务、并发与恢复

#### AC-TASK-001：提交幂等

同 user + Idempotency-Key + 相同 request 并发 20 次，只创建一个 task/run；全部响应指向同一资源。同 key 不同 request 返回 409。网络超时后通过 operation endpoint 找回结果，不重复创建。

#### AC-TASK-002：双 worker 唯一 claim

两个真实 worker 同时领取同一 QUEUED task，只有一个 CAS 成功；数据库最多一个有效 lease。失败 worker 不执行 stage 或写 artifact。

#### AC-TASK-003：kill -9 后恢复

分别在模型调用前、backtest 执行中、artifact 已写未提交、sealed evaluation 已提交未推进状态时 kill worker/API。lease 到期后新 worker 恢复；已提交副作用不重复；未提交 attempt 明确失败/重试。

另构造“stage 已成功提交、旧 lease 在游标推进前崩溃”的检查点：接管 worker 只能原子采纳该成功回执并进入服务端批准的唯一后继，原 stage 的外部执行调用次数仍为 1；伪造或越级的 `next_stage` 必须以 `RESEARCH_STAGE_TRANSITION_INVALID` 失败，不能被恢复路径接受。

让一个有效 stage executor 跨越至少一个 heartbeat cadence：持有者的 `lease_heartbeat_at` 必须以
当前 token 续写，任务在该 executor 仍运行时不得被过期恢复。再注入 heartbeat CAS 失败或旧 token，
迟到 worker 不得提交新的 checkpoint/finalize；其外部结果按 unknown/reconciliation 合同处理。独立
Explorer 进程的 poll loop 必须在首次 recover/claim 前拒绝缺失 `CLARIFY/GENERATE` 任一执行器的
配置并返回 `RESEARCH_WORKER_EXECUTORS_INCOMPLETE`；显式 stop signal 后不得开始下一次 claim。

恢复时间 ≤ `lease_ttl + poll_interval + 5s`，报告实际配置与观测。

#### AC-TASK-004：取消与完成竞争

在 stage 完成边界并发发送 cancel。数据库只能出现一种合法终态；无 orphan artifact、重复 result、重复 paper unit；再次取消幂等返回既有终态。

#### AC-TASK-005：关键副作用恰好一个有效结果

对 strategy version、sealed evaluation、gate decision、paper start、approval、live prepare 注入响应丢失/重试/worker 接管。每类按唯一键最多一个有效记录；重复请求返回已存在结果。

#### AC-TASK-006：历史无容量截断

创建 >50 task、>20 run/handoff、跨 >100 research workspace 的验收数据。cursor 分页能完整读取且无重复/遗漏；权威结果不依赖 workspace JSON 截断或扫描上限。

#### AC-TASK-007：成功回执与 candidate 成功不可伪造

对每个可执行 stage 分别构造：无 `output_artifact_id` 的 `SUCCEEDED`、仅有任意 artifact ID、错误 owner/run/task/attempt/request hash 的 binding、内容或 size 被篡改的 blob、percent-encoded 路径分隔符、旧 lease 的无绑定 `SUCCEEDED` checkpoint，以及终态 retry 携带不同 `next_stage`。所有前六类必须 fail-closed，恢复不得推进 cursor，最后一类必须不改变 task/run cursor。

再让 `GENERATE` 返回一个完全绑定但没有 typed `ProposedGeneration` 的 generic receipt：task/run 必须以 `RESEARCH_GENERATION_CONTRACT_UNAVAILABLE` 失败，不能成为 `SUCCEEDED`、不能创建 candidate/trial/approval。正向路径必须只接受 typed proposal，并在同一事务内重验代码、依赖、当前受证明数据 snapshot、模型调用摘要和 stage/run binding 后，创建可变 candidate、manifest、artifact binding 与 materialization receipt；对象版本/摘要在排队后漂移、legacy/未验证 snapshot 或 resolver 缺失时必须不创建 candidate。该正向结果只能标为 `MATERIALIZED_NOT_EXECUTED`，不能声称 Sandbox、评估、审批或策略执行已经完成。

#### AC-TASK-008：holdout dispatch/inspect/UNKNOWN 恢复不重复副作用

对同一 holdout command 依次注入：dispatch 前崩溃、executor 已接收但 ACK 丢失、terminal receipt 已观察但 DB commit ACK 丢失、lease 过期接管、连续两次 ACK 丢失和旧 generation 迟到回执。必须满足：

- operation ID 与 canonical command hash 在首次 dispatch 前持久化，此后不改变；
- ACK/结果未知进入 `UNKNOWN/RECONCILING`，清除 bearer 后只允许 token-free inspect/read-back；
- inspect 明确 `NOT_EXECUTED` 才允许同一 operation 的受控重试；无法确认时保持 UNKNOWN，不创建第二 operation；
- 终态 receipt、artifact、evaluation finalize、access audit 与 package 最多各一个有效结果；旧 lease/generation 无提交权；
- worker 默认关闭，缺 factory/executor/identity 时在首次 claim 前失败；TERM/clean stop 不领取新 command。

本地 fake/HTTP seam 只能证明协议合同。真实 evaluator endpoint、TLS 身份、queue、对象存储、跨进程数据库竞争和外部调用次数须单独登记 T2/T3；缺少这些证据时本场景的部署部分为 `NOT_RUN/BLOCKED`。

#### AC-QUOTA-001：并发预算不能超卖

设置仅够一次 LLM 调用/一次 backtest 的预算和并发上限，让两个 worker 同时预留。只能一个获得 reservation；另一个返回 `BLOCKED_BUDGET/QUOTA` 且不调用 provider、不启动 runner。reservation、实际用量、结算/释放和差额都有审计记录。一个 stage 同时预留 token/金额/计算 slot 时按固定锁序全部成功或全部回滚，不得死锁或部分占额。

必须另测“输出 cap 小于预留，但输入 + 输出上界超过预留”和“价格版本缺失/漂移”的负例，在派发前阻断；只有输出 cap 校验或供应商返回后发现超额，不满足预算硬门。本批已实现带审核计费合同的本地联合预算机制，见 [预算交付记录](MODEL_BUDGET_BUNDLE_20260905.md)；真实供应商上界、计费合同与账单核对仍待验收，不能以合成政策的本地生成链路 PASS 代替。

额外断言：出站 HTTP bytes SHA-256 必须等于两项 reservation 的 quote body hash；输入或价格在预留后漂移、缺任一 receipt、过期或失效 bucket 均不得调用。第二项 claim CAS、第二项结算 bucket 算术更新失败必须回滚第一项；使用独立数据库连接和真实事务故障，不只在函数入口校验错误参数。输入/输出分别计价、分别向上取整；只有 total_tokens 或某一分项未知时不得结算。`CONSERVATIVE_TARIFF_BOUND` 与真实发票费用分列，不用 unknown→0。

再分别注入 provider 已接收但响应丢失、worker 崩溃、provider operation 可查询/不可查询、内部 runner 已 fencing 但进程未确认终止等情况。外部终态/计费未知时 reservation 必须保持 `RECONCILING`、按最大预留保守结算或令 bucket `BLOCKED_UNKNOWN`，后续 worker 不能复用这笔额度；只有 provider 明确未执行，或内部 runner 已确认终止且不会继续消耗，才能释放/过期回收。实际计费、bucket aggregate 和 reservation 明细最终 100% 对账，不能用本地 fencing 冒充外部取消。

#### AC-QUOTA-002：所有研究调用均经过硬门

分别从 initial generation、improver、repair、retry/fallback 和直接内部 service path 发起模型调用，并从 backtest/smoke/sealed/paper 发起计算任务。任何绕过 Research LLM Gateway 或 quota reservation 的调用都被测试捕获并拒绝；历史成本查询后再调用的非原子 check 不能替代 reservation。

#### AC-SCHED-001（P1）：优先级与暂停不绕过硬配额

在多个 tenant/priority 队列上执行暂停、恢复、公平调度和优先级调整；不得饿死普通队列、重复领取、越过预算/并发上限或丢失 stage cursor。P1 未实现时 UI/API 不得显示可用的高级调度控制。

#### AC-FSM-001：四个聚合具有唯一事务 owner

对 hypothesis、task/run、candidate/evaluation、promotion/approval 分别执行全部合法迁移，再用直接 API、伪造事件、过期 expected version 和错误 DB/service role 尝试跨聚合代写或非法回退。必须满足：

- 只有对应 Registry/Runner/Evaluator/Promotion Service 能推进自己的状态；
- stale expected state/version 返回 409，原记录不变；
- task cancel 不修改 hypothesis/candidate，evaluation reject 不把 candidate 改回 mutable；
- outbox 重放同一 command 只产生一个有效跨聚合结果；
- UI 派生生命周期丢失/重建不改变权威状态；
- 每次拒绝和成功转换都有 source entity/version、command id、trace 和事务证据。

#### AC-AUD-001：审计降级阻断晋级

模拟 event/version/trial/gate 持久化失败。主流程不得静默继续到 paper/live；run 标记 `AUDIT_DEGRADED/BLOCKED`，恢复或人工处理后才可继续。debug log 不能替代审计证据。

### 5.10 服务端门禁与人工审批

#### AC-GATE-001：客户端关闭硬门无效

绕过 UI 直接提交 `require_oos=false/require_robustness=false`、空日期、伪造 precheck/pass/gate。production/promotion API 必须按 policy 重算并阻断；响应说明不可覆盖的门。

每个研究门禁记录必须直接断言 policy version、输入 evidence hash、executor version、evaluated time、PASS/FAIL/UNKNOWN/BLOCKED 状态和稳定 reason code；缺任一字段不得成为晋级证据。

#### AC-APP-001：审批 actor 只来自服务端

客户端提交 `approver=web/admin/其他用户`、`account_confirmed=true`、`risk_limit_confirmed=true`。服务端忽略/拒绝权威 actor 字段；审批人等于认证会话用户。账户/风险/部署窗口必须对应可验证 challenge records，不能由浏览器默认 true。

#### AC-APP-002：multi-actor RBAC、职责分离与 AI 不可自批

Explorer/model 服务身份、没有领域审批权限的默认角色和 policy 禁止的候选创建者尝试审批均被拒绝；不能仅凭现有 `admin/premium/user` 名称推导高风险权限。合格审批角色完成显式挑战和理由后才能批准。若采用四眼策略，两个独立 actor 才通过。

#### AC-APP-005：single-actor 不冒充独立审批

在 `SINGLE_ACTOR_SELF_ATTESTED` profile 下：

- policy 要求职责分离时，审批请求返回 `BLOCKED_REQUIRES_INDEPENDENT_APPROVER`；
- policy 明确允许的自托管 scope 中，批准前必须等待版本化 `eligible_at`、逐项回答挑战、回显 evidence hash 并确认残余风险；
- 决定保存 `approval_mode/single_actor/risk_ack/policy/scope`，UI/API 只能显示“单主体自我确认”，不得显示“独立评审”；
- AI、Explorer、Evaluator 和前端字段在任何分支都不能成为 actor。

#### AC-APP-006（P1）：四眼审批主体独立

高风险 policy 要求两个 actor 时，相同 user、共享 service identity、同一登录会话重复提交或第二 actor 缺领域权限均拒绝；两个合格且独立 actor 的决定分别绑定同一 evidence hash 和有效期。P1 未实施不得显示“四眼已通过”。

#### AC-EVIDENCE-002：command-scoped evidence package v2 不可伪造

对一个完整 terminal command 并发 20 次构建，必须收敛为一个 package。分别注入错误 command/evaluation/authorization、legacy manifest、非 PASSED evaluation、少于或多于 13 门、非 PASS/重复/错序门、gate input/policy/profile/freeze/artifact/audit 漂移、包内容篡改和 commit ACK 丢失；均不得产生或复活 ACTIVE 包，ACK 不确定只允许按完整材料读回。withdraw 与构建并发必须串行：withdraw 成功后旧包不能再次 ACTIVE，相关审批立即不可用；公开 owner 轮询不得暴露内部 evaluation ID、URI、sealed metrics 或原始 manifest。

#### AC-APP-007：human-only run-scoped grant 生命周期

默认 ADMIN/PREMIUM/USER/GUEST、Explorer/Evaluator 服务身份和未授权 active user 调用 grant API 均拒绝；只有显式 `research:manage-approval-grants` 且 `principal_kind=HUMAN` 的 active issuer 可给 `principal_kind=HUMAN` 的 active subject 在一个精确 run/workspace 签发 `research:approve`。分别构造 `HUMAN/SERVICE/UNKNOWN`，并通过原始 DB 插入模拟未分类存量主体；任何 role/session 都不得把 `SERVICE/UNKNOWN` 提升为 human。

TTL 使用数据库时间并受服务端上限约束；issue/revoke 携带幂等键，ACK 丢失时按原幂等键与完整 audit material read-back，重复同材料返回原结果，同 key 不同材料冲突，无法确认时保持 UNKNOWN/失败关闭，不得重复 issue/revoke。对 read-back 本身注入 DB 异常、超时、解析错误和错误类型返回值，service 必须捕获并统一安全返回 `UNKNOWN`，API 不出现原异常、假 2xx 或新 operation。正向 grant 必须通过真实 `ApprovalGrantService` 签发；直接插入无 audit grant、篡改 audit、重复 `ISSUED` audit 或 audit 的 issuer/subject/scope/permission/policy/material 任一错绑均拒绝。历史决定重放仍要求当时恰有一条精确 `ISSUED` audit，并满足 `issued_at <= decided_at < expires_at` 与 `revoked_at IS NULL OR decided_at < revoked_at`；若 grant 已撤销，还必须恰有一条与 grant/revoker/scope/reason/material/revoked_at 完全匹配的 `REVOKED` audit，缺失、重复或错绑均不可重放。将 `decided_at == revoked_at` 作为显式负例：同时戳无法证明决定先于撤销，必须 fail-closed。决定后的合法撤销或当前 expiry 只使当前批准失效，但不删除或改写可验证的当时决定。

过期、撤销、错误 run/workspace、非 human、inactive issuer/subject、零个或多个有效 grant 均不能决定或维持批准。响应只含最小 service DTO 状态，不返回 grant hash、issuer、permission catalog 或内部审计材料。这些本地主体负例不得记为真实 IAM/多主体 RBAC 验收。

#### AC-APP-008：数据库时间控制冷却期与批准 TTL

冻结应用时钟并推进数据库时钟，分别测试 `requested_at/eligible_at/request expires/grant expires/profile expires/decision expires`。批准在 `eligible_at` 前拒绝，在任一上界到期时失效；服务端上下文必须投影 `EXPIRED`、稳定 blocked reason 和 `can_approve=false`。分别断言 `can_decide` 与 `can_approve`：负向决定能力不能自动等于正向批准资格，浏览器也不得从局部字段重新派生它们。客户端 `now`、时区或浏览器倒计时不得授权；绕过 UI 直接 POST 同样拒绝。single-actor 必须完成全部挑战和残余风险文本；负向决定只要求非空理由，不强迫伪造风险确认。

#### AC-APP-009：请求/决定完整幂等与 TOCTOU 关闭

request/decision 的幂等材料必须覆盖 run、candidate、package、gate input、approval policy/material、mode、challenge keys、risk/reason hash 和 grant identity。正常 2xx、commit ACK 丢失和网络/5xx 后读回都要按同一材料匹配；同 key 不同材料冲突。读取“当前批准”必须在 candidate 锁内先查精确 denial fence，再选择并锁定决定，随后重验 candidate/package/gates/profile/policy/grant 及唯一 `ISSUED` audit；并发插入负向决定时不能返回陈旧 APPROVED。历史 replay 与当前 approval 分开断言：前者核对原始审计事实，后者还必须通过当前 TTL/revocation/fence 门。

#### AC-APP-010：拒绝围栏不可被换 key 覆盖

对 `REJECTED` 与 `REQUESTED_CHANGES` 分别建立精确 denial scope。决定与 fence 必须同事务追加；随后以新 request ID、新 idempotency key、预先存在的 pending request，以及精确 20 路竞争尝试覆盖。核心向量固定为 1 路 `REJECTED` 对 19 路 `APPROVED`，并以 `REQUESTED_CHANGES` 重复同型向量。共同的 P0 语义断言是：同一 scope 最终只能保留负向结论、一个不可变 fence、零个 current approval；预存 pending 不得绕过，任何请求也不得因竞争暂时得到可维持的批准。

`LOCAL_T1 / SQLite` 层在同一进程启动 20 个真实 `ApprovalService` 调用。每个调用必须在进入决定操作、竞争 `_operation_lock` 前到达 barrier 并报告 ready，再由单一 release signal 同时释放；保存 ready/release、调用结果、最终 fence 数量和 current approval 读回。若负向调用在其他 19 路释放前已完成，该用例只证明顺序拒绝，本地并发层判 FAIL。该层只验收 `_operation_lock` 的同进程线性化和 P0 语义，不能声明已证明独立数据库 process/connection 的锁或 commit 竞争。

`ONLINE_DB / PostgreSQL、MySQL、MariaDB` 层必须在每个真实引擎分别启动 20 个独立 process 和独立 connection。竞争者完成初始化后，在尝试数据库候选锁/行锁或 commit 前全部报告 ready，再由单一 signal 放行；必须保存 engine/version、process/connection identity、ready/release、锁/commit 结果及最终唯一 fence、零 current approval 的权威读回。三个 online lane 在当前 head 均为 `NOT_RUN_CURRENT_HEAD`，必须分别取得原始证据；SQLite、本地 `_operation_lock`、catalog mock 或六 worker 绿灯均不能替代或把它们标为 PASS。

再冻结数据库时间，人工控制 UUID/ID 使旧 `APPROVED` 在 `(decided_at, id)` 排序中大于后插入的负向决定；当前批准仍必须为 false，证明 fence 存在性先于时间/ID 排序。只有 candidate、terminal command/evidence package、promotion policy 或 approval policy material 真实变化形成新 scope 后才允许重新申请；客户端字段不得伪造这种变化。

#### AC-GOV-001：S0 容量与暂停裁决

逐工作流检查 named owner、可用人日、最大并行度、依赖、目标 capability profile 和默认至少 25% 风险缓冲；采用其他缓冲时必须有 S0 依据和批准。缺项、容量不足或关键 owner 不可用时必须选择分波执行/暂停，并把 Foundation 限定为 protocol OFF、sealed/paper/live BLOCKED；不得通过删除不可豁免 P0 获得 G0 PASS。

#### AC-GOV-002：偏差不制造假 PASS

对一个可豁免性能偏差和 tenant/sealed/secret/sandbox/审计/审批身份等不可豁免项分别申请 deviation。可豁免项只新增 governance decision，保存目标、原状态、风险、补偿控制、scope、actor、expiry/revocation；原 gate 保持 FAIL/BLOCKED，总决定只能是 `ACCEPTED_WITH_DEVIATION`。不可豁免项直接拒绝，任何 deviation 将其改成 PASS 判 FAIL。

#### AC-APP-003：证据变化使审批失效

批准后改变 candidate、evidence package、policy、账户、风险限额或部署窗口。旧审批保留但状态过期；live prepare 返回 precondition failure，要求新审批。

#### AC-APP-004：prepared 不等于 running

批准后调用 live prepare 只创建锁定准备单元/配置，不调用真实 broker order/start。UI、API、事件使用 `LIVE_PREPARED`，不得显示 deployed/running/盈利。

### 5.11 前端竞态、用户旅程和无障碍

#### AC-UI-001：证据工作台完整

已认证用户从假设到证据页，必须看到：预注册主张、数据 snapshot/密封、全部试验数与失败、机器证据/反证、UNKNOWN/限制、各 hard gate、人工决定和下一动作。单一 quality/AI score 不能替代上述内容。

#### AC-UI-002：预检和确认 fail-closed

覆盖 AC-HYP-002/004 的浏览器流程；按钮禁用只是辅助，拦截请求后服务端仍拒绝。错误聚焦到具体字段并保留 request/trace ID。

#### AC-UI-003：取消 A 后启动 B 无污染

延迟 A 的 poll 响应，取消 A 后立即启动 B。A 的所有迟到响应不得改变 B 的 task ID、progress、best iteration、result、timeline、toast 或按钮；离开页面后 A/B poll 请求数为 0。

#### AC-UI-004：历史/路由竞态

快速选择慢响应 run A 再选择 B，最终 timeline/versions/evidence 只能属于 B；同组件把 query 从 `run_id=A` 改为 B 时立即切换；reset 后不显示前一任务 best iteration。

#### AC-UI-005：mutating API uncertain outcome

submit/continue/cancel/paper/approval/prepare 均携带 operation/idempotency key。浏览器在响应丢失后查询并恢复既有结果，只显示一次成功/错误 toast。

#### AC-UI-006：API client 合同

配置档案、目标优化、假设、task submit/list/get/cancel/continue、run/history/timeline/version/compare、freeze/evaluation/evidence、paper、handoff/approval/prepare 每个 endpoint 至少有请求/响应/错误/所有权测试。

#### AC-UI-007：真实组件与 console 清洁

单测不得因缺 `el-timeline/el-timeline-item` stub 而跳过 DOM 语义；focused/full suite console error/warning（允许清单之外）为 0。

#### AC-UI-008：审批安全投影与精确浏览器意图

以真实服务端合同分别返回 `promotion-v1` 与 `approval-*-v2`，合法 owner 必须可以提交申请，二者不得被错误比较。浏览器 payload 不含 actor/policy/mode/permission/now；响应投影只保留 package/command/evaluation ID、当前 hashes、13 个稳定 reason code、`can_request/can_decide/can_approve` 和稳定 blocked reason，不接收 grant ID、内部 URI、manifest、gate metrics/input 或 sealed 值。三个能力字段必须是服务端直接派生且相互一致的 DTO；正向按钮仅在 `can_approve=true` 时启用，但这仍不代替 POST 事务重验。

对 service projector 做顺序及边界断言：服务端必须先从原始未脱敏 reason/challenge/risk 按 5.11.1 规范化并计算 `decision_intent_hash`，再构建字段白名单 DTO 和执行整字段脱敏。构造两组都投影为 `[REDACTED]` 但原始语义不同的文本，其 intent hash 必须不同；若先脱敏再计算、从 ORM/domain `dict()` 深拷贝或依赖前端清理才安全，均判 FAIL。

对 request/context/decision/read-back 的每个 hash 字段分别注入 bytes、数字、bool、list、object、`null`、大写或错长十六进制值。service 只接受合同规定长度的小写十六进制字符串，其他值均以稳定公开错误 fail-closed，不得隐式 `str()`、触发未处理 TypeError 或继续授权。

对 request/decision 同时覆盖正常 2xx 错绑、网络/5xx 后 read-back、4xx、提交期间 refresh、切换 run/candidate 和迟到 refresh：只有与原 intent 的 scope、package/gate、request、policy/material、mode、decision/reason/challenge/risk 全部匹配才清除幂等键并显示一次成功；错配保留原 key并 fail-closed，旧 scope 不得污染新 scope 的 busy、toast 或 DOM。decision 必须以服务端返回、浏览器可独立重算的 `decision_intent_hash` 证明原始 reason、按 policy key 顺序规范化的 challenge answers 和 residual-risk 文本；只比较脱敏后 reason、challenge keys 或风险布尔值均不合格。

Python/TypeScript 共享向量除中文、空/非空风险和 URI reason 外，必须固定 Python `str.strip()` 边界。规范向量为：`approval_request_id=33333333-3333-3333-3333-333333333333`、`decision=APPROVED`、reason 为 `U+FEFF + BOM保留 + U+FEFF`、gate hash 为 64 个 `a`、evidence hash 为 64 个 `b`、challenge keys 为 `["unicode"]`、answer 为 `U+0085 + 答案 + U+0085`、residual risk 为 `U+0085 + 风险 + U+0085`，预期 `decision_intent_hash=6e023614f08ecb90f17f866031ebfbf8b8314ca08edb669d759c2cb402812099`。这一向量必须同时在 Python 和 TypeScript 中通过；用 JavaScript `trim()` 得出不同结果必须判 FAIL。

对 decision reason、request/context blocked reason、gate reason、workbench 摘要和 API error 分别注入：任意 RFC-style `scheme://`（包括 `file://`、`s3://`、`postgresql://alice:p455@db/internal`）、POSIX 绝对路径（包括 `/Users/...`）、Windows drive 路径、UNC 路径、带 userinfo/凭据 URI、sealed/raw 敏感文本以及自由 detail/message/error/exception。它们必须在 service DTO 边界就被拒绝/脱敏，浏览器 projector、toast 和 DOM 中均不得出现原文；未登记 gate 理由为 `RESEARCH_GATE_REASON_REDACTED`，未登记 API 错误为 `RESEARCH_APPROVAL_OPERATION_FAILED`。人为移除浏览器 projector 时 service 响应仍必须安全；人为绕过 service projector 而只保留前端拦截时必须 FAIL，证明前端只是第二道非权威防线。

审批 API 使用精确公开 allowlist，不得仅检查 `APPROVAL_` 前缀。在同一测试中读取前后端使用的权威 manifest/catalog material hash 与公开 code 集合；两端版本、hash 和集合必须精确相等，任一单边多一个/少一个 code 均 FAIL。`APPROVAL_CHALLENGE_INCOMPLETE:<keys>` 必须归一为无后缀 `APPROVAL_CHALLENGE_INCOMPLETE`；`APPROVAL_FAILURE:file:///...` 或任意未登记 code 必须映射为 `RESEARCH_APPROVAL_OPERATION_FAILED`，且不带原 message/details。该要求同时覆盖响应 projector 和真实 Axios interceptor：三个 v2 approval API 可以抑制全局原文 toast，但 `401` 仍必须清理会话并派发认证过期事件；普通 API 的既有错误行为不得被全局静默。

#### AC-EVIDENCE-001（P1）：脱敏证据包导出与检索

按 run/candidate/trial/model invocation 检索并导出 evidence package；分页无遗漏，普通用户看不到 sealed URI、秘密、其他 tenant 数据或受限原文。导出 manifest/hash 可验证，撤销/删除后的引用显示失效而非旧 PASS。P1 未实现时不显示可用入口。

#### AC-FORK-001（P1）：Fork Draft 必须重新验证

从冻结版本 fork、编辑、静态/安全检查、smoke、保存新 immutable version 并重跑研究门禁。新草稿具有新 hash/lineage；任何未完成重验、复用旧 approval/evaluation 或原地修改冻结候选的路径均拒绝。

#### AC-A11Y-001：核心状态可访问

对配置、草稿、预检失败、运行中、取消、失败、证据、审批拒绝/批准状态执行 axe；serious/critical = 0。键盘可完成核心流程；progress/终态能被屏幕阅读器识别；dialog 焦点锁定和恢复正确；状态不只靠颜色。

#### AC-I18N-001：状态与错误可翻译

中文/英文切换后 stage、gate、error、按钮和空态没有硬编码混杂；未知服务端错误保留 code/ID，不丢诊断。

### 5.12 迁移、兼容与回滚

#### AC-PROTOCOL-001：协议版本分流与旧运行只读

在 v2 对批准 scope 启用后，通过旧入口、新入口和省略/显式传入 `research_protocol_version` 的请求创建研究：新建研究必须默认落为 v2，响应、task、run 和事件使用同一不可变协议版本；不支持或冲突版本返回稳定错误，不能静默降级。对启用前的 v1 历史运行执行读取、列表和导出仍成功，但所有继续、改进、重跑、批准或原地升级写入均被拒绝并指向 fork/迁移路径；v1/v2 写模型和 worker 不得交叉领取。关闭 feature flag 后既有 v2 运行保持只读可见，不能被 v1 worker 接管。

#### AC-MIG-001：多数据库 migration

在一次性 SQLite、PostgreSQL、MySQL 验收库分别执行：

1. 从当前 head upgrade 到新 head；
2. 检查 PK/FK/unique/check/index/nullability；
3. 重复运行/启动不会重复回填；
4. 应用新写入与读取契约；
5. 按批准范围验证 downgrade 或 operational rollback。

禁止修改历史 `20260718_ai_research_audit_schema.py`；新 revision 必须基于实时 `alembic heads`。

SQLite、PostgreSQL、MySQL、MariaDB 四个数据库 lane 的 migration/core contract 通过不自动证明密封隔离；MariaDB 必须在自身真实 online 引擎上独立执行，不得由 MySQL 结果代替。每个目标部署还必须单独执行 AC-DEP-001～002；SQLite 单进程结果不得外推为独立 DB/storage credential 边界。

#### AC-MIG-002：旧 JSON 政策诚实

准备超过旧截断上限的 workspace JSON。迁移要么完整导入并给出对账，要么明确保留只读来源；不能只导入最近 20/50 条后宣称完整。旧记录不得伪造 trial/holdout/approval。

#### AC-MIG-003：双写/影子读一致

运行前冻结差异 policy 和数值容差。灰度运行产生 v1/v2 摘要，自动对比 status、candidate、identity/evidence hash、metrics、trial/event count 和研究门禁结论：

- `BLOCKING`：状态、身份/证据哈希、计数、研究门禁结论不一致，或指标超出预注册容差；必须阻断 v2 promotion；
- `NON_BLOCKING`：时间戳、展示文案或 allowlist 中的语义迁移；仍须记录样例、原因和处理决定；
- 未分类差异默认 BLOCKING，不得见结果后扩大 allowlist 或容差。

差异率、原始样例、policy/hash 和处理决定全部进入 evidence。

#### AC-MIG-004：运行回滚

在无真实订单的 staging 中关闭 v2 flag/worker：

- 不领取新 v2 task；活跃 task 安全完成或取消；
- v2 历史仍只读可见；
- 不删除新表/证据；
- v1 生成器不能读 v2 sealed 结果；
- 恢复 flag 后任务按 lease/状态安全继续。

#### AC-MIG-005：旧 YAML profile 安全迁移

构造包含白名单字段、gateway/token/secret、超深嵌套、未知字段和无 owner 的存量 YAML profile：

- 只迁移白名单值，secret/可疑嵌套被丢弃并产生脱敏告警与审计；
- 无 owner 项进入 quarantine，不得自动归给触发迁移的当前用户；管理员/用户显式认领必须有幂等 operation 和审计证据；
- 认领后 user/workspace 所有权正确，其他用户读改删均被拒绝；
- 重复迁移不重复创建、不覆盖已认领档案。

#### AC-MIG-006：旧写路径只能由后续退役决定删除

在本迭代候选构建中执行静态路径/路由/worker 清单和 feature flag 测试，确认 v1 写路径仍存在、只在批准的 fallback scope 可写，且关闭 v2 后能完成一次不读取 v2 sealed 证据的 v1 rollback smoke。构造“未指定后续 retirement iteration”“读取兼容未结束”“留存窗口未结束”“回滚窗口未结束”“迁移对账未完成”任一条件，删除/禁用 v1 写路径的变更都必须被 release check 拒绝。只有后续独立迭代记录 retirement decision、owner、scope、对账证据和各窗口完成时间后才允许删除；本迭代不得以代码清理名义提前退役。

#### AC-MIG-007：2026-09-08 command/worker/approval head 严格迁移

从 `20260907_ai_research_holdout_claim` 沿线性链升级到 `20260908_ai_research_approval_authority`，在 SQLite、PostgreSQL、MySQL、MariaDB 四个独立 lane 分别执行空库、精确 partial re-entry、错误 schema/index/FK/check/trigger/function、非空破坏性降级和重升：

- finalize 的 artifact/audit 绑定不可变且非空降级阻断；
- evidence command 的四 FK 全有或全无、每 command 唯一、manifest/binding hash、精确 `ACTIVE→WITHDRAWN` 和 downgrade guard；
- execution journal 的 operation/status/check/唯一性、access-audit action 与 MySQL 隐式提交中断可恢复；
- approval grant/audit/request/decision/denial fence 的 candidate/run/package/user FK、human/mode/single-actor/check、唯一性、严格索引和不可变 guard；
- `users.principal_kind` 的 `HUMAN/SERVICE/UNKNOWN` check、`NOT NULL`、DB server default `UNKNOWN`、存量行回填 `UNKNOWN`、受控应用注册显式 `HUMAN`、partial re-entry 及降级 guard；禁止从旧 role/session 回填 HUMAN；
- PostgreSQL/MySQL/MariaDB 必须将 unique constraint 与 unique index 的真实反射结果成对核对，不得将同名或近似列集当作相同对象；MySQL/MariaDB 还必须从 `information_schema` 核对 index type 与 visibility；
- partial re-entry 对每个目标列重新核对 type、nullability、server default、computed 与 identity，任一附加/缺失/漂移元数据均冲突。类型断言必须精确到：状态/身份列是声明长度的 `VARCHAR` 而非 `TEXT`/原生 ENUM；PostgreSQL 时区时间是未显式覆盖 precision 的 `TIMESTAMP WITH TIME ZONE`/`timestamptz` 默认 precision；MySQL 和 MariaDB 分别是 `DATETIME` 且 `fsp=None`；SQLite DDL/PRAGMA 分清 `DATETIME`、`VARCHAR` 与大文本 `TEXT`，不得仅比较 affinity。CHECK 表达式比较必须 quote-aware，不得为了规范空白或布尔括号而改写字符串字面量；
- 历史 decision 只在其绑定的唯一 `ISSUED` audit 完整且满足 `issued_at <= decided_at < expires_at`、`revoked_at IS NULL OR decided_at < revoked_at` 时可重放；如已撤销，还必须恰有一条全材料匹配的 `REVOKED` audit，`decided_at == revoked_at` 必须 fail-closed。后续合法撤销/到期只使当前批准失效，不删除合法历史事实；
- PostgreSQL 只在当前 schema 的目标 relation/function OID、完整 DDL/body 和引用计数精确时复用或删除 guard；同名 orphan、外部 trigger 引用或 body 漂移不得被 `CREATE OR REPLACE` 覆盖；
- DDL 后做全量 schema re-read，任何无法证明的附加/缺失元数据 fail-closed。

离线 SQL、catalog mock 或 SQLite 通过不得填补真实 PostgreSQL/MySQL/MariaDB online 证据；未运行的引擎逐项记 `NOT_RUN_CURRENT_HEAD`。

### 5.13 可复现性、性能与新鲜运行

#### AC-REP-001：冷环境重放

只使用 evidence manifest、受控 snapshot 引用、各阶段签名 image digest/policy 和 dependency lock，在新的干净 worker 重放同一冻结候选。代码/artifact/data hash 必须相同，各 stage image 映射必须受 policy 约束；成交、返回序列和 gate 输入完全相同或在预注册数值容差内。容差必须在运行前定义，不能见结果后放宽。LLM 生成阶段只验 provider request、输入/输出 hash、实际模型与谱系可追踪；不得要求或宣称第三方模型逐字节重现相同输出。

#### AC-NFR-001：查询性能

准备有代表性的规模（至少记录 run/trial/event/candidate 数量和行宽），在 20 个并发轮询客户端下测 task/evidence summary API：

- p95 ≤ 300 ms；
- 错误率 = 0；
- 不加载完整历史 JSON；
- 输出保存原始分位数、DB explain/慢查询和硬件信息。

#### AC-NFR-002：追加写性能

同一基线下 event/trial/gate 单条追加写 p95 ≤ 200 ms，0 丢失/重复有效序号。若实现批量/异步，必须证明进程崩溃后不丢审计。

#### AC-NFR-003：容量与低基数观测

在批准并发预算下运行 task/LLM/backtest；队列深度、lease lag、stage latency、token/cost、sandbox kill、gate distribution 可观测。指标 label 不含 run/user/secret 等高基数或敏感值；关联通过 trace/log 完成。

#### AC-USAB-001（P1）：可信流程可用性护栏

封存 v1 的有效任务提交基线，并在相同用户任务上比较完成率、主动操作时间、错误恢复率和必要确认负担；点击数仅作诊断。任何通过隐藏风险披露、自动勾选挑战或省略确认获得的“改善”判 FAIL。P1 未执行不得声称“可信性升级未损害可用性”。

#### AC-DR-001（P1/G5）：证据一致备份与恢复

在一次性环境恢复数据库、对象存储和 manifest，逐项验证内容哈希、引用、tombstone/失效状态和最小权限；丢失 artifact、孤儿引用或已删除证据仍显示 PASS 均失败。本场景可 deferred 于本地 Implementation Acceptance，但目标 scope 若声明生产证据可恢复，则 G5 必须 PASS。

#### AC-T2-001：新鲜真实数据研究证据

选择一项非敏感、许可明确的真实市场数据和固定 PIT cutoff，执行完整 v2 流程。必须保存 source manifest、snapshot hash、全部 trial、DSR/硬门、留出访问和限制。它可作为批准范围内的 protocol pilot，但单次 PASS 只表示该候选/窗口/policy，不证明功能普遍正确，也不外推盈利。

#### AC-T2-002：真实 provider 调用

使用批准的测试预算和模型 provider 完成至少一次生成/改进/失败回退；记录 resolved model、prompt version/hash、token/cost、provider request ID（若有）和脱敏调用证据。无 provider 运行只能证明 deterministic fallback。

#### AC-T2-003：真实容器全链路

不是预检，而是实际 train/validation/sealed backtest 全部在目标容器策略中执行，并验证 AC-SBX-001～004。mock、fixture executor 或宿主 Popen 不能替代。

#### AC-T3-001：前向/模拟观察

按 versioned policy 指定的最小观察天数/事件数运行 paper/forward observation；记录数据新鲜度、成交/滑点差异、风险、漂移、任务恢复和告警。每条 forward observation 的 event-time、ingest/as-of 必须晚于 candidate freeze（允许延迟按 policy 判断），并进入冻结后追加的 observation epoch/snapshot；不得用冻结前历史区间冒充 forward。若观察窗口未满，该 candidate/protocol enablement 为 BLOCKED，不用历史 paper 记录补齐，但不撤销已经通过的 Implementation Acceptance。

#### AC-T3-002：staging 审批与回滚

在测试账户/锁定 staging 环境完成 challenge、批准、prepare、撤销/过期和回滚；读回外部/运行时 identity。明确验证没有真实 broker 下单。

## 6. 需求追踪矩阵

完整的逐 ID 映射维护在 [TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md)。该文件逐条覆盖 FR、NFR 和 MIG，并记录 priority、设计组件、具名验收、最早切片/发布边界和当前状态。

以下仅用于阅读导航，不能作为 G0 机器检查输入：

| 需求族 | 设计组件 |
| --- | --- |
| FR-HYP-001～008 | Hypothesis Registry、Brief Panel |
| FR-DATA-001～014 | Dataset Policy/Snapshot、Evaluator boundary、Execution Model、Terminal Command Graph |
| FR-LEDGER-001～010 | Experiment Ledger、Promotion Policy |
| FR-PIPE-001～014 | Explorer、LLM Gateway、Candidate/Evaluator、aggregate FSM |
| FR-TASK-001～012 | Durable Task Runner、Quota Reservation、Stage Attempt、External Operation Journal |
| FR-GATE-001～015 | Promotion Policy、Human/Governance Decision、Approval Authority、Evidence Package |
| FR-UI-001～015 | Evidence Workbench、domain store/composables、i18n catalog、safe service DTO/browser intent |
| FR-SEC-001～011 | Sandbox、Tool Broker、Redaction、Ownership |
| FR-DEP-001～003 | Deployment Capability Registry |
| FR-PRIV-001 | Retention/Privacy Policy |
| NFR-* | DB/API/observability/replay/DR |
| MIG-001～006 | Migration、dual write、flags |

P1 需求可以明确 deferred，但 UI/API 不得宣称已经实现；P0 无法逐 ID 映射到具名场景即 G0 FAIL。

## 7. 自动化命令基线

以下是实现后应执行的命令模板。后端必须使用用户指定的 Anaconda 环境。

### 7.1 环境与迁移

```bash
git status --short
git rev-parse HEAD
git diff --check

cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m alembic heads
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m alembic upgrade head
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m alembic check
```

PostgreSQL/MySQL/MariaDB 必须使用一次性验收数据库逐一运行同样的 upgrade/schema contract；MariaDB 是与 MySQL 分开的第四 lane，需单独连接与输出。不得对未备份的生产库做 destructive downgrade。

### 7.2 后端

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m ruff check app tests
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest \
  tests/research tests/api/test_ai_research_v2.py \
  tests/api/test_ai_research_approval_security.py -q
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest \
  tests/integration/test_ai_research_trust_pipeline.py -q
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest \
  tests/test_ai_strategy_research_service.py \
  tests/test_ai_strategy_research_config_profiles.py \
  tests/test_ai_strategy_research_objective_optimizer.py -q
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -m "not e2e" -q
```

安全、故障注入、冷重放与 NFR 建议由实现阶段新增独立脚本，并把命令、退出码和原始 JSON 纳入 evidence manifest；不能用口头结果替代。

当前仓库完整回归采用两个互补 marker 通道，避免 xdist 禁用 benchmark 或并发负载污染绝对性能阈值：

```bash
cd src/backend
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest tests -m "not performance" -p no:rerunfailures -q --tb=short \
  -n 6 --dist load --maxschedchunk=8

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest tests -m performance -p no:rerunfailures -q --tb=short
```

两通道必须在同一冻结来源/依赖上执行，并核对 collected、executed、deselected 与 testcase 集合的并集/交集。6 个 pytest worker 不是 CPU affinity 或 6 倍加速证明；skip 必须保持 `NOT_RUN/BLOCKED` 语义。

### 7.3 前端

```bash
cd src/frontend
npm run typecheck
npm run lint
npm run test -- --run src/__tests__/api/strategy.test.ts
npm run test -- --run src/__tests__/views/StrategyResearchPage.test.ts
npm run test -- --run --minWorkers=6 --maxWorkers=6
npm run build
npm run test:e2e
```

E2E 必须显式包含 `/investment/strategies` 已认证流程和 a11y 文件；现有只覆盖 `/research/strategies` 的用例不能代替。六个 Vitest worker 是并行调度合同，不是 CPU affinity、性能门或真实浏览器/E2E 证据；若当前 Node/Vitest 组合不支持该参数，必须记录 `BLOCKED_TOOLCHAIN`，不得悄然降为单 worker 后写 PASS。前后端 CPU 密集全量套件不同时运行。

### 7.4 文档与链接

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_doc_links.py
git diff --check
```

## 8. 人工浏览器验收清单

使用测试账号，不使用真实 broker 凭据：

- [ ] 未登录访问正确重定向，登录后返回 `/investment/strategies`；
- [ ] 新建草稿不自动确认，确认对话框展示完整 diff/hash；
- [ ] 修改任一关键字段后确认和预检失效；
- [ ] deterministic/LLM/RAG/fallback 标签与真实调用一致；
- [ ] 运行期间可见 task、stage、预算、trial 和失败；
- [ ] 取消后旧请求停止，立即启动新任务不被污染；
- [ ] run 历史分页，快速切换不会串 timeline/version；
- [ ] 证据页明确区分 iteration validation、sealed、forward；
- [ ] 当前 capability profile/expiry、actor mode 和每个 BLOCKED 能力清楚可见；
- [ ] 每个 FAIL/UNKNOWN 有原因、证据定位和下一动作；
- [ ] 配置 profile 不显示/发送秘密或服务器绝对路径；
- [ ] 冻结候选后编辑必须 fork，新草稿不能直接晋级；
- [ ] 审批逐项挑战，actor 不可编辑，证据变化使批准过期；
- [ ] single actor 只显示自我确认和残余风险，不能显示独立审批；
- [ ] prepare 后显示“已准备”，不显示“运行中/已下单”；
- [ ] 中文/英文、键盘、焦点、屏幕阅读器和 axe 场景通过；
- [ ] 页面错误只提示一次，并可复制 request/trace ID。

浏览器截图只能证明可见状态；必须与 API、数据库、事件和原始运行证据交叉核对。

## 9. 证据 manifest 最小字段

```json
{
  "iteration": 196,
  "candidate_commit": "<sha>",
  "started_at": "<UTC>",
  "completed_at": "<UTC>",
  "environment": {
    "os": "<value>",
    "python": "<value>",
    "node": "<value>",
    "database": "<engine/version>",
    "container": "<engine/version>"
  },
  "protocol_version": 2,
  "deployment_capability_profile": {
    "id": "<id>",
    "version": "<version>",
    "evidence_hash": "<sha256>",
    "expires_at": "<UTC>",
    "actor_mode": "MULTI_ACTOR_SEPARATED_DUTIES"
  },
  "feature_flags_hash": "<sha256>",
  "promotion_policy_hash": "<sha256>",
  "dataset_snapshot_id": "<id>",
  "dataset_snapshot_hash": "<sha256>",
  "candidate_id": "<id>",
  "candidate_hash": "<sha256>",
  "container_images": [
    {"stage": "<stage>", "digest": "<signed digest>", "sandbox_policy_hash": "<sha256>"}
  ],
  "quota_policy_hash": "<sha256>",
  "gate_results": [
    {"gate": "G0", "status": "PASS", "evidence": ["<relative path>"]}
  ],
  "artifacts": [
    {
      "path": "<relative path>",
      "sha256": "<sha256>",
      "command": "<exact command or operation>",
      "exit_code": 0,
      "evidence_level": "T1"
    }
  ],
  "known_limits": [],
  "decision": "NO_GO"
}
```

manifest 自身最后计算 hash，并在 `decision.md` 引用。不得把 token、cookie、数据库密码、密封授权或模型输入明文写入 manifest。

## 10. 偏差、阻断与判定

### 10.1 允许的状态

- `PASS`：场景全部条件满足且证据可读；
- `FAIL`：观察到与合同不一致；
- `BLOCKED`：依赖/环境/权限缺失，未能执行；
- `NOT_RUN`：尚未执行；
- `DEFERRED_P1`：仅适用于明确 P1 项，且产品不声称已有能力。

当前允许登记为 `DEFERRED_P1` 的范围仅包括：FR-HYP-008、FR-LEDGER-009～010、FR-PIPE-009、FR-TASK-010、FR-GATE-009、FR-UI-010/013、FR-SEC-008、FR-PRIV-001、NFR-UX-002、NFR-DR-001。任何 P0 或未列明项不得借用该状态。

### 10.2 偏差规则

- P0 不接受“临时 waiver = PASS”；确需发布必须通过 FR-GATE-011 的治理决定记录，并将总决定标为 `NO_GO` 或 `ACCEPTED_WITH_DEVIATION`，不能称完整验收通过；原研究门禁状态保持不变；
- 安全、tenant、密封泄漏、审计完整性、幂等关键副作用和人工审批身份不允许降级；
- 性能目标若需调整，必须先保留原始基线、原因、影响和批准，更新版本化 NFR 后重跑；
- 外部 provider/数据不可用属于 BLOCKED，不得用 fake 替代 T2；fake 只可完成 T1。

### 10.3 三份独立决策模板

```markdown
# Iteration 196 Implementation Acceptance

- Candidate commit:
- Evidence manifest/hash:
- G0: PASS/FAIL/BLOCKED/NOT_RUN
- G1: PASS/FAIL/BLOCKED/NOT_RUN
- G2: PASS/FAIL/BLOCKED/NOT_RUN
- G3: PASS/FAIL/BLOCKED/NOT_RUN
- G4: PASS/FAIL/BLOCKED/NOT_RUN
- Open P0 deviations:
- Deferred P1:
- Decision: IMPLEMENTATION_ACCEPTED / NO_GO / ACCEPTED_WITH_DEVIATION (不等于 Implementation Accepted)
- Enablement state: OFF / INTERNAL_ONLY
- Approvers and timestamps:

# AI Research Protocol Production Enablement

- Implementation decision/hash:
- Approved scope (asset/frequency/tenant/environment):
- G5: PASS/FAIL/BLOCKED/NOT_RUN
- Representative T2 evidence:
- Representative T3/staging evidence:
- Gray rollout/rollback evidence:
- Open P0 deviations:
- Decision: PROTOCOL_PRODUCTION_ENABLED / NO_GO / ACCEPTED_WITH_DEVIATION (不等于 Protocol Production Enabled)
- Effective/expiry time:
- Approvers and timestamps:

# Candidate Research and Promotion Decision

- Protocol/scope version:
- Candidate/evidence package hash:
- Hypothesis/experiment epoch:
- Trial ledger/DSR/sealed gate:
- Forward/paper evidence:
- Human challenge/approval:
- Known limits:
- Decision: CANDIDATE_RESEARCH_PASS / CANDIDATE_PROMOTION_PASS / REJECTED / BLOCKED
- Claim boundary and expiry:
- Approvers and timestamps:
```

`IMPLEMENTATION_ACCEPTED` 要求 G0～G4 全 PASS；`PROTOCOL_PRODUCTION_ENABLED` 还要求已接受实现、G5 PASS、批准范围和回滚明确；candidate PASS 要求该 candidate 的全部研究/晋级证据。三者均要求适用范围内 P0 偏差为 0、manifest 完整、声明边界准确。任何漂亮回测、单一 Sharpe、AI 自评或历史绿灯都不能覆盖这些条件。

## 11. 历史证据边界与 2026-09-08 当前验收状态

2026-09-08 当前本地候选冻结于实现工作树 `/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`、分支 `codex/iteration-196-ai-research-trust`、基础/当前提交 `a18bcf52682686c30d919fe02d6fd734ee4271b9`；工作树仍有大量未提交变更，故 `G0 provenance/candidate seal=NO-GO`。后端 Python 来源摘要 `03513ad1302d16e567ec180705181ac85be7d18fd25b88f5a13669de80988ec1` 在跑前、功能后、性能后相同。固定 6 worker 功能通道为 **6,131 passed、123 skipped、0 failure/error**，JUnit time 960.565秒、pytest终端961.25秒；串行性能通道为 **18 passed、6 skipped、0 failure/error、14.96秒**；互斥覆盖6,278 cases，其中6,149 passed、129 skipped。AI research classname 为1,303/1,303，approval为299/299。前端固定6 worker为154文件、1,556/1,556 passed、19.29秒，typecheck、48项strict catalog verifier、build与scoped检查通过；Node 25.1.0超出 `>=20 <25`，只能判 `LOCAL_PASS_UNSUPPORTED_RUNTIME`。完整命令、摘要与首轮两失败的RED/GREEN闭环见 [2026-09-08回归记录](REGRESSION_6_WORKERS_20260908.md)。

当前审批终审为P0/P1/P2=0：历史grant严格要求 `issued_at <= decided_at < expires_at`，撤销时还要求 `decided_at < revoked_at` 与唯一精确 `REVOKED` audit；ACK读回异常和非字符串hash/idempotency材料均fail-closed；真实1+19 SQLite入口barrier在同进程锁层通过。48项公开错误目录由backend tuple权威驱动，frontend versioned JSON/TS与full-repo strict verifier精确匹配。当前唯一 migration head 为 `20260908_ai_research_approval_authority`；独立 migration suite 135/135、SQLite/PostgreSQL/MySQL/MariaDB 四个离线 SQL lane 与heads读回通过。详见 [审批权威记录](APPROVAL_AUTHORITY_20260908.md)、[前端工作台记录](APPROVAL_WORKBENCH_FRONTEND_20260908.md) 与 [当前head迁移记录](CURRENT_HEAD_MIGRATION_20260908.md)。这些均是本地 `LOCAL_T1` 合同证据。

四份核心合同当前精确覆盖 **122项需求、其中110项P0、104个具名AC**。全仓 `ruff check`、compileall、`git diff --check` 与冲突扫描通过，但全仓 `ruff format --check` **失败：16 files would reformat**；本轮未擅自改动无关文件，不能声称全静态绿。固定Backtrader快照为1.3.0、摘要 `34a1e78d996dc423d24d0ada5cd2609251734551ece05b523f51aa3fd8b8bee1`，不满足项目声明 `>=1.9.78.123`，依赖来源/干净重建仍为 `NO-GO`。

2026-09-07 冻结候选曾补严格 candidate-freeze receipt、server-owned holdout request、内部 claim/start 与 lease fencing、独立评估恢复/终态幂等、13 项 promotion gate、审批同事务锁定/重验及沙箱 ready/terminal 双阶段协议。该冻结 `app/tests` 来源和只读 Backtrader 导入快照下，六 worker 功能通道记录 **5,561 passed、123 skipped、0 failure/error、818.39秒**；串行性能通道记录 **18 passed、6 skipped、0 failure/error、14.94秒**。两条互斥通道在当时覆盖 5,708 cases，其中 5,579 通过、129 跳过；`test_ai_research_*` classname 子集记录 735 项通过、无 skip。这些数字全部是带日期的历史证据，不得作为 2026-09-08 审批权威增量的当前收集数或 PASS。当时前端 148 文件、1,345 项、typecheck 和 build 在 Node 25 本机通过，但项目支持范围为 `>=20 <25`，故只记 `LOCAL_PASS_UNSUPPORTED_RUNTIME`，发布门须 Node 20 重跑。历史命令、JUnit、哈希、失败记录和依赖边界见 [2026-09-07回归记录](REGRESSION_6_WORKERS_20260907.md) 与 [claim/start 证据](HOLDOUT_CLAIM_START_20260907.md)。

request-only 前置切片的独立 6 worker focused T1 历史结果为 **150 passed、40 warnings、41.02秒、exit0**，11 文件 manifest SHA-256 为 `789fb81d51ec008ee48ec08c2c75b7bcc9a50591aeb55979a61c43ce620912cb`；其冻结范围只持久化 `QUEUED/REQUEST_HOLDOUT`，明确为 0 authorization、0 evaluation。后续 claim/start 的 focused T1 历史结果为 **184 passed、42 warnings、48.06秒、exit0**，11 文件 manifest 为 `a1fde1be8faaae282cb48951970c4b4f91f4ad23bb3e12b3bf204446277ddc9c`；claim-time 原子创建并消费唯一 JIT authorization、创建唯一 `RUNNING` evaluation 和 generation-fenced lease，但没有执行实际密封计算、checkpoint/finalize 或 promotion。两轮结论只在它们各自的历史本地 T1 范围为 `PASS`。详见 [request 历史证据](HOLDOUT_REQUEST_COMMAND_20260907.md) 与 [claim/start 历史证据](HOLDOUT_CLAIM_START_20260907.md)。

2026-09-07 证据记录的当时唯一迁移 head 为 `20260907_ai_research_holdout_claim`；它及前一 candidate-freeze head 的一次性 SQLite、PostgreSQL 17.7、MySQL 9.4 迁移/不可变触发器/破坏性降级拒绝继续只判定为各自历史的 `SESSION_TRANSCRIPT_PASS / PERSISTENT_EVIDENCE_PARTIAL`，不能向当前 head 外推。当前 PostgreSQL/MySQL/MariaDB 的真实 online upgrade/反射配对、触发器/函数执行、20个独立process/connection竞争与生产 operational rollback 均为 `NOT_RUN_CURRENT_HEAD`；SQLite、catalog mock、离线SQL或六worker本地绿灯不能填补。真实Provider、对象存储/IAM、独立queue/Evaluator工作负载身份、实际密封计算/finalize、生产Redis/可信代理、Docker沙箱、authenticated current UI、Node20、T2/T3与candidate晋级仍为 `NOT_RUN/BLOCKED`。

因此当前仍为：`IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`、candidate research/promotion=`BLOCKED/NO-GO`。

### 11.1 历史基线（2026-09-05 早期跑次）

以下 156 项/4,993 项、dataset_identity head、旧诊断 factory 和 HTTP/UI 记录均为其发生时的历史证据，不能覆盖上述后续源码，也不表示 generation adapter/factory 当前仍缺失：

- 已完成文章鉴别、代码/页面只读审计、需求与设计/验收合同，并实现默认关闭的 v2 schema、API、服务、worker 与证据工作台；family hash 已收回服务端派生并以数据库唯一约束锁定同族留出预算，预检重试不会新建 family；
- 历史本地 T0/T1 记录：当时 6 核 v2 后端契约156项在对应完整回归内全部通过（JUnit逐项核对）；除 success 工件存在/绑定/内容完整性、无绑定 checkpoint 恢复拒绝、retry cursor 防篡改、encoded URI/run request-hash 拒绝、陈旧 task 的原子事件序号、MySQL 方言选择/锁定 fallback seam 和 generic `GENERATE` 假成功拦截外，当时还覆盖 opaque receipt、服务器对象版本/摘要/identity、预检/任务/物化重验、legacy snapshot 拒绝、forward receipt、typed candidate materialization 与漂移负例。对象解析器是本地受控 fixture，不能替代真实对象存储/IAM 证明。legacy `workflow_steps` 的168项后端服务与98项页面回归、前端类型检查/完整前端测试/构建、历史 SQLite/PostgreSQL migration 演练和实际 HTTP/UI T1 证据均只保留其原有范围。当时的 `20260905_ai_research_dataset_identity` head 曾在一次性 SQLite 与 PostgreSQL 17.7 完成 upgrade/check、downgrade/reupgrade/check；后续head见 [当前迁移验收](CURRENT_HEAD_MIGRATION_20260905.md)；
- 该历史 Explorer bootstrap 复验中，默认仍关闭；受限 `explorer:create_worker` 是确定性**诊断** factory，`CLARIFY` 仅写入 `NOT_CALLED/NOT_EXECUTED` receipt，`GENERATE` 写入同类 receipt 后以 `RESEARCH_GENERATION_NOT_EXECUTED` 失败。generic executor 的 terminal success 被 `RESEARCH_GENERATION_CONTRACT_UNAVAILABLE` 拦截；只有 typed materializer 才能创建 `MATERIALIZED_NOT_EXECUTED` candidate，且当时尚未接入真实 Provider/Sandbox/Evaluator。静态 Compose `config --quiet` 通过，双 flag 关闭时允许空 factory、开启时在 recover/claim 前 fail-closed；真实 Docker、Provider、Evaluator/Sandbox/IAM/网络拒绝仍是环境门禁。详见 [EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md](EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md) 与 [IMPLEMENTATION_REVIEW_DISPOSITION_20260905.md](IMPLEMENTATION_REVIEW_DISPOSITION_20260905.md)。
- 该历史代码复验在同一隔离方式下重新创建 PostgreSQL 验收库，空库先因缺 profile 正确 `BLOCKED`；仅登记有时限、只含 `protocol_v2` 的 `dev-single-process/v1` profile 后，真实 UI/API E2E 为 `1 passed（5.5 秒）`。HTTP 还验证了 performance-only governance 偏差的敏感响应脱敏与撤销；详见 [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md)。
- 该历史完整后端跑次使用 `-n 6 --dist load --durations=15`，终态为 `4993 passed, 129 skipped, 174 warnings in 536.50s`，退出码0。JUnit共5,122项、0 failure/error，其中156项v2用例通过且无跳过；没有用自动重试、旧绿灯或排除文件补齐结果。完整命令、失败历史、修复边界和JUnit摘要见 [REGRESSION_6_WORKERS_20260905.md](REGRESSION_6_WORKERS_20260905.md)。它只证明当时源码；129项跳过也仍保留其原有条件，不代表对应环境场景通过。
- 当时本地 Docker CLI 无法连接 daemon；首次启动 Colima 因虚拟机磁盘镜像下载在约0.4%时按有界验收停止，未形成可用运行时；MySQL虽在运行但没有获授权的验收凭据。当时headless Chromium的已认证真实浏览器链路已完成，但macOS锁屏阻断屏幕阅读器与人工焦点检查；且没有使用用户/生产凭据执行真实Provider、受控真实数据、隔离容器、前向观察、staging审批或回滚演练；
- 当时本机常驻 `localhost:8000` OpenAPI不含v2路由，`localhost:3000`前端未运行；二者不是该历史候选版本，且该跑次没有获得重启或部署它们的授权。

因此，当前 head 的 `IMPLEMENTATION_ACCEPTED`、`PROTOCOL_PRODUCTION_ENABLED` 与 candidate 决定均为 `NO-GO`。当前实现范围、命令、输出与阻断项见 [REGRESSION_6_WORKERS_20260908.md](REGRESSION_6_WORKERS_20260908.md) 和 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)；[REGRESSION_6_WORKERS_20260907.md](REGRESSION_6_WORKERS_20260907.md)、[HOLDOUT_CLAIM_START_20260907.md](HOLDOUT_CLAIM_START_20260907.md)、request-only 与 2026-09-05 报告只作为历史记录。这一区分防止把“计划写完”“局部测试通过”或“页面可打开”误报为迭代196已完整验收。
