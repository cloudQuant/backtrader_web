# 迭代 196：当前 AI 投研功能审计

> 审计日期：2026-09-04
> 审计方式：当前 checkout 源码、测试与只读本地可达性检查
> 代码基线：`dev@a18bcf52`；审计开始时 tracked worktree 无差异，仅迭代196目录（两篇原文）未跟踪
> 审计结论：已有完整功能骨架，但尚不能把当前链路描述为密封、可复现、可恢复的可信研究流程

## 1. 证据边界

本审计只陈述当前 checkout 可见的代码事实和只读运行事实：

- 前端 `http://localhost:3000/investment/strategies` 可达；未登录时重定向到 `/login?redirect=/investment/strategies`；
- 后端 `http://localhost:8000/api/v1/health` 可达并返回健康状态；
- 本次没有使用用户凭据，没有执行已认证 AI 投研、真实模型、真实回测、模拟盘或实盘准备；
- 现有测试较丰富，但其中大量使用 fake service/dependency override/mock Popen；它们不能替代真实 provider、真实容器、进程重启、多 worker、密封留出和真实数据证据；
- 两篇文章是观点材料，不是本项目现状证据；观点鉴别见 [ARTICLE_REVIEW.md](ARTICLE_REVIEW.md)。

源码行号均以 `a18bcf52` 为准；后续 commit 若改变文件，应先对照该 SHA 或重新执行审计，不能把漂移后的行号当作同一证据。本次新增的六份文档仍位于同一未跟踪迭代目录，未改变 tracked code 基线。

因此，“页面可打开”“健康检查通过”“现有单测通过”都不能被写成迭代 196 已验收。

## 2. 当前用户旅程

当前代码已经支持以下主链路：

```text
配置档案 / 自然语言目标
→ 投资要求解析与前端确认
→ 数据预检
→ 异步 task（同步 run fallback）
→ 生成 / 修复 / 回测 / 评审 / 改进
→ 当前所谓 OOS / 稳健性
→ 最佳版本、时间线、版本比较与晋级审计
→ 模拟盘启动 / 评审
→ 实盘交接包 / 人工批准
→ 锁定实盘单元准备
```

主要入口：

- 路由：`src/frontend/src/router/index.ts:32-39,58-65`；
- 页面：`src/frontend/src/views/StrategyPage.vue`（当前约 3,122 行）；
- 页面逻辑：`src/frontend/src/views/strategy/useStrategyPage.ts`（当前约 6,795 行）；
- 前端 API：`src/frontend/src/api/strategy.ts:158-387`；
- 后端 API：`src/backend/app/api/strategy/base.py:291-918`；
- 请求/响应：`src/backend/app/schemas/ai_strategy_research.py:497-1081`；
- 编排服务：`src/backend/app/services/ai_strategy_research_service.py:470-1849`。

## 3. 已实现能力与复用建议

| 当前能力 | 代码证据 | 迭代 196 处理 |
| --- | --- | --- |
| 投资要求、事件、版本、比较关系表 | `app/models/ai_research.py:15-110`；`alembic/versions/20260718_ai_research_audit_schema.py:33-128` | 保留并关联 v2 run/task/trial/evidence |
| 目标优化、mandate、task/run/history/timeline/version API | `app/api/strategy/base.py:291-799` | 兼容读取；增加 protocol v2 与幂等合同 |
| 模拟盘、交接、批准、prepare | `app/api/strategy/base.py:802-918` | 保留后半段；强化服务端门、actor 和证据绑定 |
| AST、策略完整性、trade-call、preflight | `app/services/research/robustness.py:9-85` | 保留第一层代码安全检查 |
| Docker sandbox 基础 | `app/utils/sandbox.py:307-362,519-633,651-837` | 扩展到真实研究回测全链路 |
| 时间 train/validation 窗口分离 | `app/services/research/robustness.py:272-308` | 明确其为迭代验证，再新增密封留出 |
| Monte Carlo/walk-forward/参数敏感性基础 | `app/services/overfitting/` 与 robustness 服务 | 复用/校准，不把已有基础误写成密封或 DSR/PBO |
| purge/embargo 与 DSR 依赖基础 | `app/services/asset_research/evaluation.py:18,87-208` | 复用 split/依赖；先修正 DSR `var_sharpe` 适配并增加 AI 策略证据合同 |
| fail-closed 晋级范式 | `app/services/asset_research/promotion.py:90-120` | 复用模式，不照搬预测任务阈值 |
| DB lease/heartbeat/CAS | `app/models/asset_research.py:220-292`；`services/asset_research/task_runner.py:100-489` | 为 AI research 建独立表并复用并发模式 |
| AI 调用预算/Prompt Registry/call log | `app/services/ai_chat_service.py:158-166,351-443` | 统一研究 LLM gateway，不再直连绕过 |
| 页面进度、诊断、版本、paper/live 视图 | `StrategyPage.vue:1036-2088` 等 | 拆成证据工作台组件，保留用户能力 |

## 4. P0 事实与风险

### AUD-P0-01：当前 OOS 是可反馈的迭代验证，不是密封留出

**事实**：

- 训练回测使用 train window，验证使用 validation window，初始切分本身没有把验证区间放进训练调用；
- 但是验证失败指标会被 `_improvement_metrics` 合并，并传入下一轮 `_improve_draft`：
  - `src/backend/app/services/ai_strategy_research_service.py:1116-1264,1561-1574`；
  - `src/backend/app/services/research/robustness.py:514-552`；
- 现有测试还明确覆盖“样本外失败后继续研究”的行为。

**判定**：当前字段 `out_of_sample` 只能解释为 `iteration_validation/legacy_oos`。它有价值，但多轮观察后已成为调参信息，不能满足独立最终测试。

**需求**：FR-DATA-001～010、FR-PIPE-004～006；验收 AC-SEAL-001～006。

### AUD-P0-02：默认首稿可能没有调用模型，却被标成 AI

**事实**：

- `StrategyService.generate_copilot_draft` 只有在 `knowledge_base_id` 存在时才调用 RAG；否则直接调用确定性 `build_ai_strategy_draft`，返回 `model_id=None/tokens=0`：`app/services/strategy/core.py:207-249`；
- 研究服务仍可能统一记录 `source=ai_initial_draft`，展示层将其表达成“AI 初稿”。

**风险**：用户无法判断结果来自 LLM、RAG、规则模板、修复还是 provider fallback，模型成本/能力声明也会失真。

**需求**：FR-PIPE-011、FR-UI-011；验收 AC-TRUTH-001～002。

### AUD-P0-03：预检 Docker 与真实回测执行环境存在断层

**事实**：

- 代码预检/沙箱工具具备 Docker 能力；
- 真实研究回测最终进入 `BacktestService._run_strategy_subprocess`，使用当前 `sys.executable`、复制完整 `os.environ`，通过普通 `subprocess.Popen` 执行：`app/services/backtest/service.py:506-568`；
- `communicate(timeout=...)` 的 finally 只注销 PID，当前代码不能证明超时后 kill 完整进程组；
- 生成代码会写入 workspace 策略目录并被动态 import。

**风险**：预检通过不等于正式回测在断网、只读、无秘密、受限 CPU/内存/PID 的环境运行；恶意或错误策略可能读取宿主数据、保留子进程或消耗资源。

**需求**：FR-PIPE-013、FR-SEC-001、FR-SEC-009；验收 AC-SBX-001～005。

### AUD-P0-04：任意 continuation 上下文可以进入外部模型 prompt

**事实**：

- `AIStrategyResearchRunRequest.continuation_context` 接受自由 dict：`app/schemas/ai_strategy_research.py:651-654`；
- 改稿时 `dict(request.continuation_context)` 被直接序列化进模型输入：`app/services/research/generation.py:175-194`；
- 任务 snapshot 的脱敏不等于 provider outbound 发送前脱敏。

**风险**：凭据、内部路径、账户信息或其他敏感值可经嵌套字段外发；日志/账本还可能再次持久化。

**需求**：FR-PIPE-010、FR-SEC-004、FR-SEC-010；验收 AC-LLM-001、AC-PRIV-001。

### AUD-P0-05：配置档案是共享 YAML，API 丢弃用户身份

**事实**：

- profile 服务写同一 `config/ai_research_profiles.yaml`；config 可包含自由结构；
- list/create/import/get/update/delete API 均取得 `current_user` 后显式 `del current_user`：`app/api/strategy/base.py:373-511`；
- 前端 profile snapshot 深拷贝大部分研究表单，包含 gateway JSON 的风险。

**风险**：认证用户可能互相读、改、删档案；秘密值可能进入 repo-local YAML、API、日志、导入/导出和 UI。

**需求**：FR-UI-007、FR-SEC-005、FR-SEC-011；验收 AC-TENANT-001～002、AC-PRIV-001。

### AUD-P0-06：生产 hard gate 不完整

**事实**：

- 生产 guard 主要强制 robustness 与数据 precheck；并未无条件强制 required OOS/sealed；
- RunRequest 的日期可空，`require_out_of_sample_validation` 后端默认可为 false；没有可切分日期时验证可能 skipped；
- 数据 coverage 缺口和交易成本缺失可被记为 warning，入口主要检查 `passed`；
- 基本质量门主要为 Sharpe、交易数和可选回撤/收益/胜率，默认最小交易数可很低。

**风险**：缺日期、缺覆盖、缺成本或无独立验证的候选仍可能进入 paper；“生产模式”标签强于实际证据。

**需求**：FR-DATA-011～012、FR-LEDGER-005～008、FR-GATE-001～003；验收 AC-DATA-001～004、AC-STAT-001～004、AC-GATE-001。

### AUD-P0-07：研究 task/run 不是 durable 一等记录

**事实**：

- AI 研究关系表没有 first-class research run/task；event/version 的 `run_id` 是字符串而非 run FK；
- task manager 使用 `asyncio.create_task` + 进程内字典；重启将未完成 snapshot 标为 interrupted/failed，再由用户 continue；
- task/run/handoff 快照存 workspace settings，存在 20/50 条截断和最多扫描有限 workspace 的路径；
- pipeline event/version 持久化失败的部分路径会降级继续。

**风险**：多 worker、kill -9、取消/完成竞争、响应丢失和重试无法证明唯一执行；审计失败也可能不阻断晋级。

**需求**：FR-TASK-001～008、FR-GATE-002～003；验收 AC-TASK-001～006、AC-AUD-001。

### AUD-P0-08：mandate 确认不是不可变服务端合同

**事实**：

- `InvestmentMandate.status` 默认 `confirmed`；create endpoint 的语义接近“解析并确认”；
- 前端解析后将本地 `confirmed=false`，点击确认主要翻转本地布尔值；
- mandate 复用主要校验 owner，页面一致性只比较 prompt/symbol/timeframe；日期、成本、质量门、OOS/稳健性变化后仍可能沿用旧 mandate ID。

**风险**：不能证明用户确认了实际执行的完整约束，运行与 mandate 语义可能分离。

**需求**：FR-HYP-001～007；验收 AC-HYP-001～004。

### AUD-P0-09：实盘审批事实可由浏览器自动填写

**事实**：

- 当前前端批准路径可固定发送 `approver='web'`、泛化 comment，并自动提交 `account_confirmed/risk_limit_confirmed=true`：`useStrategyPage.ts:5019-5068`；
- 一个通用 confirm 点击不能证明账户、限额、部署窗口和 evidence hash 已独立挑战。

**风险**：actor 和批准事实不可问责；证据变化后旧批准也可能被错误复用。

**需求**：FR-GATE-004～010；验收 AC-APP-001～005。

### AUD-P0-10：前端预检、轮询和 artifact 请求存在一致性缺口

**事实**：

- 数据预检 UI 可显示“阻断”，但运行校验没有完整要求 `precheck.passed`；预检失效 watcher 只覆盖部分字段：`useStrategyPage.ts:1136-1215,5783-5805,6303-6315`；
- task poll 没有完整 AbortSignal/generation token；取消只更新共享状态，unmount 未停止 task poll：`useStrategyPage.ts:5879-6052,6317-6322`；
- 快速选择历史 A/B 的 timeline/version 请求缺 selected-run 响应校验；reset 没有清空 best iteration；query 主要在 mounted 恢复。

**风险**：用户看到阻断仍可提交；A 的迟到响应可污染 B；页面展示与服务端当前对象不一致。

**需求**：FR-HYP-007、FR-TASK-007、FR-UI-004～006、FR-UI-012；验收 AC-UI-002～005。

### AUD-P0-11：现有 DSR wrapper 的方差输入语义不足

**事实**：

- `app/services/asset_research/evaluation.py:197-214` 调用 `purgedcv.deflated_sharpe_ratio`，但把 `np.var(values)`（候选收益序列方差）传给 `var_sharpe`；
- 当前安装的 `purgedcv` 合同说明 `var_sharpe` 应为多次候选/超参数试验 Sharpe 的方差，并与 Sharpe 单位一致；
- `tests/asset_research/test_evaluation.py:75-78` 只断言 DSR 结果非空，没有用独立向量检查输入语义或数值。

**风险**：虽然项目已有 DSR 名称和依赖，当前 wrapper 仍不能直接证明多重搜索修正正确；若原样接入 promotion gate，会把错误适配固化成可信性门禁。

**需求**：FR-LEDGER-004～006；验收 AC-LEDGER-002、AC-STAT-001～003。

### AUD-P0-12：目标部署能力与计划中的安全边界尚不等价

独立评审后的代码复核补充：

- 当前生产 Compose 使用单一应用 DB credential，未提供 Explorer/Evaluator 分离身份、sealed queue、对象存储/KMS 或对应网络拒绝策略；
- backend Dockerfile/Compose 未提供可作为正式研究执行面的独立 Sandbox Runner；直接给 backend 挂载宿主 Docker socket 会把 API 权限扩大为宿主级控制，不是可接受修复；
- SQLite 单进程没有 DB role，但数据库引擎本身也不能决定是否安全：PostgreSQL/MySQL 共享超级凭据同样不合格，必须以进程、存储、队列、网络和 credential 的真实 capability evidence 判定；
- 当前 auth/RBAC 只有通用 guest/user/premium/admin 等角色，没有 reviewer/risk-approver/auditor 的领域权限合同，不能直接满足职责分离验收；
- 项目支持多用户，评审中“主部署通常单用户”没有仓库证据；真正缺口是 single/multi actor 拓扑及其声明语义未定义。

**风险**：不能用“采用某数据库”“隐藏按钮”或同进程代码分支声称密封/独立审批成立。

**需求**：FR-DEP-001～003、FR-DATA-013、FR-GATE-004、FR-GATE-010；验收 AC-DEP-001～002、AC-SEAL-001、AC-APP-002/005。

### AUD-P0-13：预算与统计生产依赖尚未形成硬运行合同

- `purgedcv` 当前只在 dev extra/lock 中，生产 lock/镜像没有等价依赖；即使修正 wrapper，目标镜像仍可能无法执行 DSR 门；
- `AIChatService` 有预算基础，但部分 AI 策略改进路径可直接调用 router；调用前累计成本查询也不是跨 worker 的原子预算预留；
- 现有预算机制不统一覆盖回测计算资源和并发超卖。

**风险**：不能把“已有预算 service”或“开发环境能 import”当作 P0 Research Gateway、配额或生产统计门证据。

**需求**：FR-LEDGER-006、FR-PIPE-010、FR-TASK-009；验收 AC-STAT-001、AC-LLM-001、AC-QUOTA-001～002。

## 5. P1 改进项

| ID | 当前事实 | 后续方向 |
| --- | --- | --- |
| AUD-P1-01 | 简单质量分未考虑完整搜索次数；现有 AI 链路无 DSR/PBO | P0 DSR + raw market trial；P1 PBO/CSCV/effective trial |
| AUD-P1-02 | robustness method 是宽松字符串，非法值可能回退到默认方法 | 枚举、版本化算法和 unsupported 错误 |
| AUD-P1-03 | 执行模型有手续费/保证金基础，但滑点/成交量/停牌/价格限制等不完整 | 统一 execution model evidence 与无法支持项 fail-closed |
| AUD-P1-04 | `workflow_steps` 主要影响 prompt/summary，不控制 orchestrator | 变成真实 server graph，或从“可执行配置”删除 |
| AUD-P1-05 | 页面、composable、CSS 和主测试规模过大 | 拆成 route/page、domain store、五类面板与用户行为测试 |
| AUD-P1-06 | AI 路由仍加载普通策略列表/模板，历史重卡片缺分页/虚拟化 | 路由按需加载；历史 cursor 分页 |
| AUD-P1-07 | timeline 类型含 input/output/metrics，但 UI 主要显示 summary/error | 在权限/脱敏下展示证据引用和执行版本 |
| AUD-P1-08 | `/investment/strategies` 缺专属 E2E/axe，现有关键 E2E 偏策略管理 | 增加 AI 投研成功、负例、竞态、审批与 a11y 场景 |

## 6. 测试现状与证据缺口

### 6.1 已有测试价值

- `src/backend/tests/test_ai_strategy_research_service.py` 覆盖生成、修复、OOS、稳健性、paper/live、恢复和 API 的大量行为；
- `test_ai_strategy_research_config_profiles.py`、`test_ai_strategy_research_objective_optimizer.py` 提供专项回归；
- 前端 `src/frontend/src/__tests__/views/StrategyPage.test.ts` 对 AI 页面分支覆盖较多；
- `src/frontend/src/__tests__/api/strategy.test.ts` 有部分 API client 合同；
- 资产研究已有 DSR 与 task lease 测试可作为实现参照。

### 6.2 不能由现有测试证明

- 同一不可变 code/dependency/execution semantics 在受策略约束的真实 stage Docker 中完成预检、训练、留出和 paper；
- 真实网络/文件/环境/进程隔离与 timeout 后 0 子孙进程；
- 真实 provider 的 resolved model、prompt/call log、budget 和 secret 阻断；
- Explorer 在 DB/API/object/tool 各层均无法读取密封留出；
- 多 worker claim、kill -9、CAS、取消/完成竞争和关键副作用幂等；
- 完整 trial 搜索账本、DSR oracle、PBO 和 final holdout；
- 真实 PIT 数据 snapshot、许可、执行成本/容量；
- `/investment/strategies` 已认证完整 E2E 与 a11y；
- 模拟盘观察窗口和生产/staging 运行门。

当前前端 focused tests 即便绿色，若仍有未解析 Element Plus timeline 组件警告，也不能证明时间线 DOM 语义已被测试。

## 7. 设计裁决

对现状有三种可选策略：

1. 只调整默认门禁/文案：改动小，但无法解决密封、审计和恢复；
2. 在现有流程中增加可信双通道、实验账本、持久任务和证据 UI：能复用现有能力并修正核心风险；
3. 直接建设全自治多 Agent 研究实验室：吞吐量高，但会先放大当前统计、安全和治理缺口。

迭代 196 选择方案 2。详细目标架构见 [DESIGN.md](DESIGN.md)，逐项需求见 [REQUIREMENTS.md](REQUIREMENTS.md)，验收门见 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 8. 当前状态判定

| 维度 | 当前判定 | 说明 |
| --- | --- | --- |
| 功能骨架 | 已存在 | 从目标到 paper/live prepare 的主要入口齐全 |
| 产品真值 | 需改进 | deterministic/RAG/LLM/fallback 标签不充分 |
| 数据可信 | 需改进 | OOS 可反馈、缺 final sealed/PIT 完整证据 |
| 统计可信 | 需改进 | 缺全量试验账本与 AI 链路 DSR/PBO |
| 执行安全 | P0 阻断 | 正式回测普通 Popen，不等于真实容器隔离 |
| 秘密/tenant | P0 阻断 | 任意 continuation 外发、共享 YAML profile |
| 任务可靠性 | 需改进 | 内存 task 与 workspace JSON 不是 durable orchestration |
| 审批问责 | P0 阻断 | 客户端可自动声明多个审批事实 |
| 用户一致性 | 需改进 | 预检、确认、poll/history 竞态 |
| 真实市场/生产 | 未验收 | 本次无已认证、真实 provider/data/container/shadow 证据 |

因此当前结论不是“功能不可用”，而是“功能骨架具备，可信研究与生产晋级证据尚未闭环”。这正是迭代 196 的范围。
