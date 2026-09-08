# 迭代 196：可信 AI 策略研究流程

> 文档状态：独立评审后修订基线；实施与验收状态见 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
> 基线日期：2026-09-04
> 当前验收快照：2026-09-08，见 [六 worker 分层回归记录](REGRESSION_6_WORKERS_20260908.md)
> 最新证据：后端固定 6 worker 功能通道为 6,131 passed、123 skipped、0 failure/error，性能通道串行为 18 passed、6 skipped；前端固定 6 worker 为 1,556/1,556 passed，但 Node 25 超出 `>=20 <25`，只记 `LOCAL_PASS_UNSUPPORTED_RUNTIME`。审批终审 P0/P1/P2=0，当前唯一 migration head 为 `20260908_ai_research_approval_authority`。真实三数据库 online、跨进程竞争、对象存储/IAM、queue/Evaluator/Provider、authenticated current UI、T2/T3 均未闭合，整体仍为 `NO-GO`
> 适用页面：`/investment/strategies`
> 目标分支：常规功能变更应从功能分支提交并以 `dev` 为 PR 目标分支

## 1. 结论先行

当前 AI 投研已经具备从投资目标解析、策略生成、回测、迭代改进、样本外检查、稳健性检查、模拟盘评审到实盘准备的较完整用户旅程。迭代 196 不应继续把“生成更多策略”作为首要目标，而应把现有流程升级为**可隔离、可追溯、可复现、可否决的可信研究系统**。

本迭代采用“可信性优先的双通道研究架构”：

1. **探索通道（Explorer）**允许 AI 在发现集和迭代验证集上生成、回测和改进候选；
2. **独立评估通道（Independent Evaluator）**独占密封留出集，候选冻结后才能评估，结果不得回流给生成器继续优化同一候选；
3. **实验账本（Experiment Ledger）**追加记录所有成功、失败、取消和超时尝试，并将真实搜索次数用于多重检验修正；
4. **门禁与人工责任（Gate + Human Decision）**由服务端强制执行，AI 或单一综合评分都不能自动批准模拟盘或实盘晋级；
5. **证据工作台（Evidence Workbench）**把预注册主张、机器证据、反证、未知项、门禁决定和审批责任分开呈现。

这一方案保留当前生成与回测能力，同时解决现有流程中最关键的风险：所谓“样本外”结果目前会参与下一轮生成改进，因此它是迭代验证集，不是密封留出集；研究任务主要依赖进程内状态；确认、数据预检与实盘审批的部分约束停留在前端；模型、数据、代码和实验搜索谱系尚不足以重放一项研究结论。

## 2. 文档导航

| 文档 | 用途 |
| --- | --- |
| [ARTICLE_REVIEW.md](ARTICLE_REVIEW.md) | 鉴别两篇文章的观点、来源质量、可采纳边界及反需求 |
| [CURRENT_STATE_AUDIT.md](CURRENT_STATE_AUDIT.md) | 当前页面、后端、统计、沙箱、任务和审批的代码证据与风险分级 |
| [REQUIREMENTS.md](REQUIREMENTS.md) | 用户、业务、功能、数据、安全与非功能需求；含优先级和追踪 ID |
| [DESIGN.md](DESIGN.md) | 目标架构、状态机、数据模型、API、前端、迁移、回滚和实施切片 |
| [ACCEPTANCE.md](ACCEPTANCE.md) | 分层验收门、场景用例、证据契约、命令模板和发布判定 |
| [REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) | 需求集独立评审：A/B/C 分级改进建议、抽查验证记录与处置顺序 |
| [REVIEW_DISPOSITION.md](REVIEW_DISPOSITION.md) | 对独立评审逐项记录采纳/部分采纳、校正理由和计划落点 |
| [TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md) | 每个 FR/NFR/MIG 到设计组件、具名验收和发布切片的逐项映射 |
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | 已实现地基、验证证据、产品目录回归结果与明确的生产 NO-GO 条件 |
| [REGRESSION_6_WORKERS_20260908.md](REGRESSION_6_WORKERS_20260908.md) | 当前候选的固定 6 worker 功能回归、串行性能回归、前端 6 worker、源码/依赖摘要、首轮失败闭环和最终 NO-GO 边界 |
| [APPROVAL_AUTHORITY_20260908.md](APPROVAL_AUTHORITY_20260908.md) | human-only grant、历史决定重放、拒绝围栏、ACK-loss、48 项公开错误目录与审批终审证据 |
| [APPROVAL_WORKBENCH_FRONTEND_20260908.md](APPROVAL_WORKBENCH_FRONTEND_20260908.md) | 审批工作台权限表达、安全投影、浏览器意图哈希、错误目录、1,556 项前端回归及 Node 运行时边界 |
| [CURRENT_HEAD_MIGRATION_20260908.md](CURRENT_HEAD_MIGRATION_20260908.md) | 当前审批权威 head、135 项 migration suite、四方言离线 SQL 与真实三数据库 online 未运行边界 |
| [ACCEPTANCE_REPORT_20260905.md](ACCEPTANCE_REPORT_20260905.md) | 2026-09-05～06 历史 T0/T1 实施与验收快照、旧产品目录回归记录和 T2/T3 外部环境门禁 |
| [REGRESSION_6_WORKERS_20260907.md](REGRESSION_6_WORKERS_20260907.md) | 2026-09-07 历史候选的 6 worker 功能/串行性能分层回归、源码与依赖冻结、沙箱超时根因和当时验收边界 |
| [HOLDOUT_REQUEST_COMMAND_20260907.md](HOLDOUT_REQUEST_COMMAND_20260907.md) | claim 前的 server-owned holdout request command 历史切片：11 文件身份、150 项六 worker T1、请求时 0 authorization/0 evaluation 与负向声明 |
| [HOLDOUT_CLAIM_START_20260907.md](HOLDOUT_CLAIM_START_20260907.md) | 内部 Evaluator claim/start、lease fencing/heartbeat/recovery、184 项聚焦 T1、首次全量失败诊断与最终 6 worker 全绿证据 |
| [REGRESSION_6_WORKERS_20260905.md](REGRESSION_6_WORKERS_20260905.md) | 2026-09-05～06 历史回归时间线、并发夹具/CLI 导入修复与旧候选结果 |
| [DISPATCH_SAFETY_20260905.md](DISPATCH_SAFETY_20260905.md) | 单次外部派发、取消与租约重检、模型用量结算、并发记账的红绿证据及剩余边界 |
| [PROVIDER_RESPONSE_VALIDATION_20260905.md](PROVIDER_RESPONSE_VALIDATION_20260905.md) | ProviderResponse 完整验证、错误账本、计数脱敏例外与 59 项聚焦回归 |
| [GENERATION_EXECUTOR_20260905.md](GENERATION_EXECUTOR_20260905.md) | 服务端 GENERATE 执行器、固定政策/配额/数据门禁及首次组件交付记录 |
| [GENERATION_PROVIDER_DEPLOYMENT_20260905.md](GENERATION_PROVIDER_DEPLOYMENT_20260905.md) | HTTP adapter/部署组合根、模型观察字段、出站字段名保护、公开 worker 生成物化链与真实验收边界 |
| [MODEL_BUDGET_BUNDLE_20260905.md](MODEL_BUDGET_BUNDLE_20260905.md) | 不可变请求、审核计费契约、Token/金额原子预留派发结算与真实账单验收边界 |
| [DISCOVERY_EXECUTION_20260905.md](DISCOVERY_EXECUTION_20260905.md) | 冻结前发现验证的执行合同、远端调用、持久取证与纵向链路补齐进度 |
| [DISCOVERY_PUBLICATION_20260906.md](DISCOVERY_PUBLICATION_20260906.md) | 发现 HTTP adapter、原子搜索占位、journal→trial 发布、锁序修复与当前验收边界 |
| [DISCOVERY_WORKFLOW_20260906.md](DISCOVERY_WORKFLOW_20260906.md) | 持久化新旧执行图、公开 discovery worker、trial/stage 原子提交与版本降级护栏 |
| [FILESYSTEM_DATASET_RESOLVER_20260905.md](FILESYSTEM_DATASET_RESOLVER_20260905.md) | 默认关闭的文件字节证明、持久 receipt、API 静态接线及 POSIX/部署隔离边界 |
| [CURRENT_HEAD_MIGRATION_20260905.md](CURRENT_HEAD_MIGRATION_20260905.md) | 早期 candidate-freeze receipt head 的三数据库会话证据、破坏性降级拒绝及历史持久证据边界；当前 head 见 2026-09-08 记录 |
| [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md) | 一次性 PostgreSQL、实际 FastAPI、候选前端与 headless Chromium 的协议 v2 T1 证据及其边界 |
| [LOCAL_T1_TRACEABILITY_20260905.md](LOCAL_T1_TRACEABILITY_20260905.md) | 本地已执行契约到 AC/需求组的证据索引，以及不能误报为 PASS 的真实环境门禁 |
| [EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md](EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md) | 独立 Explorer worker 的默认关闭启动契约、Compose overlay、验证证据与未闭合的真实执行/隔离前置 |
| [IMPLEMENTATION_REVIEW_DISPOSITION_20260905.md](IMPLEMENTATION_REVIEW_DISPOSITION_20260905.md) | 实现完整性独立评审的逐项修复、当前诊断 factory 语义与保留的 candidate/Provider/Sandbox 门禁 |
| [文章1.md](文章1.md) | 用户提供的观点材料，保留原文，不作为已核验事实 |
| [文章2.md](文章2.md) | 用户提供的观点材料，保留原文，不作为已核验事实 |

目录名沿用用户创建的“改进优化 ai 生成策略流程”以保持链接稳定；本迭代的产品标题锁定为“可信 AI 策略研究流程”。

## 3. 当前能力基线

### 3.1 已存在且应复用

- 前端已提供 AI 研究工作台、参数与质量门配置、投资要求解析、运行/取消/继续/重试、进度与诊断、版本比较、模拟盘和实盘交接入口。
- 后端已有投资要求、流水线事件、策略研究版本与版本比较等持久化模型。
- 研究服务已有生成代码校验、回测、迭代验证、稳健性、模拟盘评审和实盘准备等阶段。
- 多资产研究模块已有 purge/embargo walk-forward、DSR 依赖封装、严格晋级门和任务 lease/heartbeat/CAS 恢复模式；迭代 196 应复用这些基础，但 DSR 适配器必须先修正 `var_sharpe` 语义并用独立 oracle 验证，不能原样照搬。
- 生产环境数据预检已有 fail-closed 基础，生成代码也已有沙箱相关基础。

### 3.2 已确认的主要缺口

| ID | 当前缺口 | 风险 | 迭代 196 方向 |
| --- | --- | --- | --- |
| GAP-01 | 每轮“样本外”结果会进入下一轮改进输入 | 留出集被反复观察，结果不再独立 | 重命名为迭代验证；增加服务端密封留出集和候选冻结 |
| GAP-02 | 只保留有限运行快照，任务主体依赖进程内字典和协程 | 重启后难以精确恢复，可能重复执行阶段 | 采用数据库任务、幂等键、lease、心跳和阶段游标 |
| GAP-03 | 投资要求在后端创建时已标记确认，前端确认只是本地布尔值 | 不能证明谁在何时确认了哪一版约束 | 持久化草稿/确认状态、版本哈希、确认人和时间 |
| GAP-04 | 前端数据预检的失败状态未完整绑定启动条件 | 用户可能在可见阻断下仍提交任务 | 前后端同时 fail-closed，服务端作为最终权威 |
| GAP-05 | 改动日期、成本和部分质量门后仍可能沿用旧确认 | 实际任务与已确认要求不一致 | 用完整规范化请求哈希绑定确认与任务 |
| GAP-06 | 取消后的旧轮询可能继续写入页面状态 | 新任务被旧任务结果污染 | 使用任务作用域/AbortController/卸载清理和响应身份校验 |
| GAP-07 | 实盘审批可由前端固定提交 `approver=web` 和确认布尔值 | 审批证据不可信、责任主体不可辨认 | 服务端从认证上下文取审批人；独立挑战、二次确认和不可变审计 |
| GAP-08 | 配置档案可持久化完整表单，包括 gateway JSON | 凭据或敏感配置可能落盘/回显 | 密钥引用化、字段白名单、服务端脱敏和禁止导出 |
| GAP-09 | 质量分是各门禁归一化后的简单平均 | 未反映搜索次数、选择偏差和证据缺失 | DSR + 完整试验计数；P1 增加 PBO/CSCV；缺证即未知/阻断 |
| GAP-10 | 模型调用元数据不含完整输入输出哈希、真实版本和环境谱系 | 模型别名漂移后无法复现或问责 | 保存实际模型版本、请求 ID、采样参数、哈希和工具/环境清单 |
| GAP-11 | 当前页面和组合式逻辑规模很大 | 高风险交互难以独立测试和演进 | 按“假设、数据、账本、证据、决定”拆分组件与 composable |
| GAP-12 | 默认首稿可能来自确定性模板，却统一呈现为 AI 初稿 | 产品真值、模型成本与能力声明失真 | 如实标注 LLM/RAG/template/repair/fallback 来源 |
| GAP-13 | Docker 主要覆盖预检，正式研究回测可走宿主普通子进程 | 网络、环境变量、文件、资源与超时终止边界不足 | 同一不可变工件在断网、只读、限资源容器完成全阶段 |
| GAP-14 | 配置档案是共享 YAML，任意 continuation 可进入模型输入 | 跨用户读改删、密钥落盘或外发 | user-scoped DB profile、credential ref、allowlist/污点/深层脱敏 |
| GAP-15 | 现有 DSR wrapper 把收益方差作为 `var_sharpe`，测试只验证非空 | 多重检验门的数值语义可能错误 | 从完整 trial 账本计算跨试验 Sharpe 方差，修正 adapter 并与独立 oracle 对照 |
| GAP-16 | 当前部署没有 Explorer/Evaluator/Sandbox 分离身份、专用 queue/storage 边界和研究领域审批角色 | 数据库或前端配置可能被误当作真实隔离/职责分离 | Deployment Capability Registry + 真实拒绝测试 + single/multi actor 明示 |
| GAP-17 | `purgedcv` 仅在 dev 依赖，部分 improver 可绕过统一预算，现有成本查询不是原子预留 | 生产 DSR 可能不可执行，并发任务可能超卖 LLM/计算预算 | 生产依赖锁/import smoke + 统一 gateway + 原子 quota reservation |

> 当前页面的实时检查只确认了前端和后端可访问、受保护路由会重定向到登录页。由于本次没有使用用户凭据，不能把未登录检查描述为“已完成真实用户流程验收”。功能基线来自当前代码、现有测试和只读运行检查。

## 4. 文章观点的产品化边界

两篇文章的共同价值在于指出：AI 降低实验成本后，最大风险从“写不出代码”转向“更快地产生大量假发现”；真正的产品壁垒是问题定义、数据治理、独立验证、失败留痕和人类责任。

迭代 196 采纳这些原则，但不采纳未给出原始证据的效率和行业数字：

- 采纳：AI 做边界明确、可机器校验的工作；所有尝试留痕；样本隔离由系统执行；生成器不能自批；考虑成本、容量、执行与风险；研究谱系可重放。
- 条件化采纳：“测试集只碰一次”落地为“候选冻结后揭盲、按实验纪元/候选家族关闭留出预算”；轻微变体不能换 ID 后反复窥探；“第二个 AI 反证”只能是辅助证据，不能构成独立批准。
- 不采纳：十倍效率、一人替代二三十人、行业采用率、收益提升或必然产生 Alpha 等没有可复核口径的主张。

详见 [ARTICLE_REVIEW.md](ARTICLE_REVIEW.md)。

## 5. 方案比较与决策

| 方案 | 内容 | 优点 | 主要问题 | 决策 |
| --- | --- | --- | --- | --- |
| A. 最小加固 | 调整默认门禁、重命名 OOS、增加 DSR 展示 | 改动小、交付快 | 不能解决数据隔离、任务恢复和审计责任 | 不作为终态；仅可做迁移第一步 |
| B. 可信双通道 | 探索/独立评估分离、密封留出、实验账本、持久任务、证据 UI | 直接解决核心可信性问题，可复用现有模块 | 涉及模型、API、前端和迁移 | **选定** |
| C. 全自治多 Agent 实验室 | 多模型并行发现、反证、知识图谱、自动组合与调度 | 潜在吞吐量高 | 成本、相关错误、治理和可解释性风险高 | P2 以后另立项，不属于本迭代 |

## 6. 迭代目标

### O1：研究结论可解释

- 每个候选都能回答：研究问题是什么、何时预注册、AI 看过哪些数据、试了多少次、哪一版代码和模型产生、哪些门通过/失败、谁批准了下一步。

### O2：密封证据不泄漏

- 生成器在权限、数据接口和提示上下文上均不能读取密封留出集；留出评估结果不进入同一候选的改进循环。

### O3：失败与搜索成本完整可见

- 失败、取消、超时及无效结果与成功结果同等进入追加式账本；统计修正使用可审计的试验计数，而不是“最佳结果数量”。

### O4：流程可恢复且不会重复副作用

- worker 重启、网络断开、前端取消/重试都不能制造第二个有效租约、重复留出评估或重复晋级。

### O5：晋级责任可问责，独立性声明真实

- 服务端强制数据、统计、稳健性、安全和审批门；AI 不能批准自身输出；审批人来自认证身份而非客户端自由字段。single-actor 部署必须披露未实现独立人类复核的残余风险，且在 policy 要求职责分离时 fail-closed。

## 7. 范围

### 7.1 P0（本迭代必须交付）

- 假设/投资要求预注册与不可变版本；
- 发现集、迭代验证集、密封留出集、前向观察集的权限与谱系；
- 候选冻结、留出访问授权和一次性评估规则；
- 追加式实验账本和完整搜索计数；
- DSR 计算及服务端 fail-closed 晋级策略；
- 模型、提示词、输入输出、代码、数据和环境的可重放元数据；
- 研究任务持久化、幂等、lease、心跳、恢复与取消；
- LLM/回测原子预算预留、并发硬上限与超限 fail-closed；
- 可信确认、数据预检和人工审批；
- 部署拓扑能力矩阵、single/multi actor 语义和偏差治理记录；
- 密钥脱敏、生成代码沙箱和不可信文本防护；
- 前端证据工作台、i18n/error catalog 和旧运行只读兼容；
- 灰度、双写/影子读、回滚和审计指标。

### 7.2 P1（P0 稳定后）

- PBO/CSCV、相关性调整的有效试验数；
- 更完整的容量、拥挤、市场状态和执行仿真；
- 辅助反证 Agent 与确定性检查器，但不授予审批权；
- 失败研究记忆、相似实验提醒和可复现研究包导出；
- 前向/模拟盘漂移、衰减和再认证；
- 隐私擦除协调、可用性回归护栏、证据备份与恢复演练；
- 队列优先级、人工暂停/恢复和高级公平调度。

### 7.3 非目标

- 不承诺发现 Alpha、盈利或任何固定收益表现；
- 不允许 LLM 直接下单、自动发布或自动批准实盘；
- 不重建完整交易执行平台；
- 不用“多 Agent/多模型一致”替代独立证据；
- 不把旧历史产物补填为本迭代的新鲜留出或生产证据；
- 不把文章中的生产力数字设为 KPI；
- 不在本迭代引入全自治多 Agent 研究实验室。

## 8. 交付切片与顺序

| 切片 | 交付 | 前置条件 | 退出条件 |
| --- | --- | --- | --- |
| S0 基线与治理锁定 | 现状快照、术语/命名迁移、功能旗标、容量/拓扑/actor 裁决、风险登记 | 无 | 旧 `out_of_sample` 仅等价于迭代验证；owner、容量、目标拓扑、暂停判据和裁剪顺序签署 |
| S1 可信身份 | 预注册、规范化哈希、数据快照、候选冻结 | S0 | 任何运行都绑定不可变身份 |
| S2 实验账本 | 全量 trial、模型调用、门禁决定、DSR | S1 | 失败与成功均可审计，缺证 fail-closed |
| S3 独立评估 | 密封授权、独立 evaluator、结果隔离 | S1、S2 | 生成器无法访问留出，且无结果回流 |
| S3b 受限执行 | 独立 Sandbox Runner、签名镜像、资源/进程约束、artifact broker | S1 artifact 合同；Cut A 前接入 S4 | AC-SBX-001～005 全过，回执绑定工件/镜像/政策/配额且无残留进程 |
| S4 持久执行 | DB task、lease、心跳、幂等、恢复 | S1 | 注入重启不重复关键副作用 |
| S5 证据 UI | 五类面板、可信审批、取消隔离、敏感字段治理 | S1-S4 与 S3b API/回执 | 用户能区分主张、证据、未知和决定 |
| S6 灰度收口 | 双写、影子核对、旧数据只读、回滚演练 | S1-S5（含 S3b） | G0～G4 实现验收后，以 G5 单独决定批准 scope 的协议生产启用；candidate 各自晋级 |

### 8.1 容量与暂停合同

S0 不得以“后续再确认”退出。团队必须逐工作流记录 owner、可用人日、最大并行度、关键前置、目标 capability profile 和默认至少 25% 风险缓冲；若采用其他缓冲，必须在 S0 记录依据和批准，并在以下两条路径中做出留痕决定：

1. **完整执行路径**：证据表明能够覆盖全部 Cut A P0，继续 S1～S6（含 S3b）；
2. **分波执行路径**：容量或隔离前置不足时，先完成 `FOUNDATION_CHECKPOINT`（S0 + S1 + S2 + S4 和最小只读证据视图），随后把 S3、S3b、可信审批与完整工作台转为明确后续波次。

`FOUNDATION_CHECKPOINT` 只允许声明“探索过程可审计、统计输入可复核、任务可恢复”，协议保持 OFF，paper/live promotion 一律 BLOCKED；它不等于 `IMPLEMENTATION_ACCEPTED`、密封独立性或可信 v2。若关键 owner 缺失、能力 profile 无法证明、计划超过已确认容量或风险缓冲被耗尽，必须暂停并重切分，不能在见到结果后放松 P0。

预签裁剪顺序为：P1 → S5 非核心展示/导出 → S6 自动化程度 → 批准资产/频率/租户 scope。最小证据五区块、密封隔离、tenant/secret、真实沙箱、审计、持久任务和服务端硬门不得从“可信 v2”声明中裁掉。

## 9. 成功指标

成功指标衡量流程可信性，不衡量生成数量：

- 研究任务与 trial 留痕完整率：100%；
- 密封留出访问未授权事件：0；
- 已执行模型调用的关键谱系完整率：100%；
- 终态重复转换和重复留出评估：0；
- 晋级门决定绑定证据哈希：100%；
- 服务端检测到缺少数据/搜索计数/返回序列/版本哈希时：100% fail-closed；
- 经批准研究包的冷环境可重放率：100%（对象是冻结候选、数据、代码、依赖、执行语义与 gate 输入；允许行情供应商数据按已封存快照读取，不允许重新拉取后冒充原快照；第三方 LLM 生成阶段只保证输入和谱系可追踪，不保证逐字节输出一致）；
- 安全样例中密钥进入模型输入、配置档案或导出：0。

这些是实现验收目标，不等于真实市场有效性。最终必须形成三个不同决定：G0～G4 的 `IMPLEMENTATION_ACCEPTED`、代表性 T2/T3 与灰度/回滚后的 `PROTOCOL_PRODUCTION_ENABLED`、以及每个候选自己的研究/晋级决定。三者不能互相替代，详见 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 10. 关键约束

- 前端不得成为可信门禁的唯一实现位置；后端必须重新验证全部约束。
- AI 生成器、独立评估器与人工审批者必须具有不同权限和审计身份。
- 密封、沙箱和审批能力按版本化部署 capability profile 验收；数据库品牌、前端隐藏或单元测试不能替代真实拒绝证据。
- single-actor 补偿控制不得被描述成职责分离；policy 要求独立审批时必须 BLOCKED。
- 旧字段和旧产物允许只读展示，但不能被回填为“已通过密封留出”。
- 统计实现优先复用 `asset_research/evaluation.py` 的 purge/embargo 结构和 `purgedcv` 依赖；DSR wrapper 必须改为接收跨 trial Sharpe 方差，并先补公式语义测试；布尔声明必须升级为有证据引用的验证结果。
- 任务可靠性优先复用 `AssetAnalysisTask` 和 `asset_research/task_runner.py` 的 lease/CAS 模式。
- 任何阈值都必须属于有版本的 promotion policy；阈值变化不得重写历史决定。
- 文档中的 G0～G5 统一称为“发布 Gate”；candidate 的 data/statistics/security/approval 结果统一称为“研究门禁”，两者不得混用。
- 用户拥有的未提交文章与无关工作树改动必须保留。

## 11. 参考方法边界

- Deflated Sharpe Ratio 用于纠正多重尝试和非正态收益造成的选择偏差，但它不是盈利保证。
- 简单单次留出不足以单独证明策略稳健；目标设计同时采用时间有序的 walk-forward、purge/embargo、密封留出和搜索账本。
- NIST AI RMF/GenAI Profile、NIST 对抗机器学习分类和 OWASP LLM 风险用于安全与治理参考。
- 美联储 SR 26-2 仅作为模型治理设计参考，不声称对本项目直接适用；其正式范围和对 GenAI/agentic AI 的排除必须在评审中保留说明。

权威链接和文章论点映射见 [ARTICLE_REVIEW.md](ARTICLE_REVIEW.md)。
