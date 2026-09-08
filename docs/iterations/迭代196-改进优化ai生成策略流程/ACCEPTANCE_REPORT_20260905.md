# 迭代 196：本地实现与验收报告（2026-09-05）

> 历史快照提示（2026-09-07）：本文保留 2026-09-05～06 的实际执行记录，正文中的“最新”仅相对于该历史时间线。当前候选回归以 [2026-09-07 六 worker 分层回归](REGRESSION_6_WORKERS_20260907.md) 为准，当前决定以 [实施状态](IMPLEMENTATION_STATUS.md) 为准；不得用本文旧数字覆盖后续源码。

> 2026-09-06 最新增量：版本化公开 discovery 工作流、trial/stage 原子提交与 checkpoint 恢复已接通，并补严格模型 JSON、旧图兼容与破坏性降级拒绝。最新完整目录终态及来源统一见 [回归记录](REGRESSION_6_WORKERS_20260905.md)，本批具名正反例、失败处置和部署边界见 [版本化发现工作流](DISCOVERY_WORKFLOW_20260906.md)。显式冻结、对账、独立评估/审批部署链和真实runner仍未验收；整体NO-GO。

> 历史预算切片结论：完整后端5,216通过、129跳过、601.36秒，6 worker；379项 v2 全过。首轮失败/中断与修复后聚焦单独保留，不计入最新通过数量。不可变请求、Token/金额联合预算、持久快照及严格 claim 已实现，见 [预算交付记录](MODEL_BUDGET_BUNDLE_20260905.md)。后续评估/审批/沙箱执行图、全入口预算、组对账与真实供应商计费审核尚未完成，整体及生产启用保持 NO-GO。
>
> 本报告是 [ACCEPTANCE.md](ACCEPTANCE.md) 中验收合同的一次实际执行记录，不能替代 T2/T3 的真实环境证据。

## 1. 历史实现范围与后续增量

以下早期固定两阶段图和对应跑次保留历史语境。当前 generation-v1 仍是两阶段，discovery-v1 是服务端选择的三阶段图，详见本页顶部最新记录；不能把早期“固定图”描述理解为新任务永远只有两个阶段。

- 新增协议 v2 的持久化聚合、线性 Alembic migration 和 owner-scoped API；`AI_RESEARCH_PROTOCOL_V2_ENABLED` 默认仍为关闭。
- Durable task worker 以租约、阶段 checkpoint 和幂等键驱动。成功回执与 task/run 游标推进同一事务提交；旧 lease 失效后的接管只会原子采纳既有成功回执，绝不重放已提交 stage 的外部副作用。当前 v2 核心图固定为 `CLARIFY → GENERATE → terminal`，越级执行器跳转以 `RESEARCH_STAGE_TRANSITION_INVALID` 失败关闭。独立 Explorer poll loop 只接受完整的核心 executor map，缺失映射时在首次领取前以 `RESEARCH_WORKER_EXECUTORS_INCOMPLETE` 拒绝启动；已领取任务的外部 stage 执行期间持续 CAS heartbeat，续租失败的旧 worker 无法提交迟到 checkpoint。直接调用 worker 且没有注册某阶段执行器时，仍以 `RESEARCH_STAGE_EXECUTOR_UNAVAILABLE` 明确失败关闭，绝不伪造“已生成策略”。
- 每个 `SUCCEEDED` stage 还必须持有 broker 生成、内容哈希/长度可复核且精确绑定到 owner/run/task/attempt/request hash 的工件。无工件 success、旧无绑定 checkpoint recovery、篡改内容、编码 URI 穿越和错误 request hash 均拒绝；终态 retry 只能读取/验证，不能重新写 cursor。typed `ProposedGeneration` 会经 server-owned materializer 在同一事务内重验 binding 与对象身份，并创建可变 candidate、代码/参数/依赖/模型谱系 manifest、artifact binding 和 materialization receipt；generic terminal `GENERATE` success 仍改写为 `RESEARCH_GENERATION_CONTRACT_UNAVAILABLE`。物化语义只是 `MATERIALIZED_NOT_EXECUTED`：生成 executor 可调用配置的模型，但物化本身不再调用模型，也不执行 Sandbox、Backtest、Evaluator 或 market trial。
- 新增真实 HTTP adapter 的独立 `generation:create_worker`，将固定 prompt/model/quota policy、同一个文件 DatasetRegistry 与 materializer 组合；构建不读业务库、不建配额、不发模型请求。模型配置 pin 与供应商观察型号分列；数值输出 cap 不再误脱敏，出站携密键在 claim 前拒绝。双 flag 默认关闭，当前仅以本地 HTTP transport seam 验证公开 worker 正反路径，详见 [生成部署验收](GENERATION_PROVIDER_DEPLOYMENT_20260905.md)。
- 新增 deployment-only Explorer bootstrap、module CLI 和 opt-in Compose overlay。两个 v2 flag 关闭时 CLI 不加载 factory、不访问任务；开启时只允许解析镜像内 `app.research_deployments.*` 的显式 factory，factory 必须返回完整 `ResearchProtocolWorker`。缺 factory/不完整 map 在 recover/claim 前退出；overlay 无 host port/volume、只读非 root、drop capabilities、`no-new-privileges` 且 `restart: "no"`。该 overlay 不是 sealed Evaluator/Sandbox 生产拓扑，不能被注册为其 capability 证据。
- 候选分支包含 opt-in `explorer:create_worker`，但它只产生明确标识 `NOT_CALLED/NOT_EXECUTED` 的确定性诊断 receipt：`CLARIFY` 可成功，`GENERATE` 以 `RESEARCH_GENERATION_NOT_EXECUTED` 失败。默认配置不引用它；它不创建 candidate、不会调用 Provider/Sandbox/Backtest/Evaluator 或 market trial。实现评审处置见 [IMPLEMENTATION_REVIEW_DISPOSITION_20260905.md](IMPLEMENTATION_REVIEW_DISPOSITION_20260905.md)。
- Candidate Registry、holdout/independent evaluation、evidence package 与 approval 的严格路径均会拒绝 `LEGACY_UNVERIFIED`、完整性失败或 candidate/dataset 绑定不一致的快照；但它们仍未被部署 worker/API 串接为生成→独立评估→审批→沙箱执行闭环，不能因局部 contract 通过而被表述为已端到端运行。
- 修复取消竞态：取消若发生在阶段执行返回后，阶段回执也必须以 `CANCELLED/TASK_CANCEL_REQUESTED` 终态闭合，不能遗留 `RUNNING` 审计记录。
- 新增服务端构建的、脱敏且不可变的 evidence package；审批会验证 package 存在、未篡改、仍与当前候选/数据/epoch/门禁材料绑定。客户端不能自造 `evidence_package_hash` 取得批准。
- 预注册改为“草稿 → 显式确认 → 服务端数据预检 → 启动”的受控序列。数据创建只接受服务器注册的 opaque object receipt；受控 resolver 生成逻辑对象、版本、摘要、大小、receipt hash 与 snapshot identity hash，浏览器传 URI/version/digest/size 均拒绝。预检、任务启动和 typed materialization 都会重新核验对象，前向观察追加也只接受 receipt；`LEGACY_UNVERIFIED` 快照不能进入严格路径。本轮只用进程内受控 resolver 做 T1 证明，尚未接入真实对象存储/IAM 或使用真实不变对象，不能将该负例外推为生产存储证据。
- experiment epoch 的 family hash 由服务端从确认后的预注册身份字段推导，API 拒绝客户端指定该 hash；同一 owner/family 在数据库层只能存在一个 epoch。迁移遇到历史重复 family 必须先人工对账，不能静默合并。预检失败或过期时，工作台只会重做原绑定的服务端 precheck，绝不新建 family 规避留出预算。
- 候选冻结由调用方提交预期内容哈希，服务端在冻结、holdout 授权签发和授权消费时重验候选、代码/依赖、数据快照与环境绑定；holdout 授权保存候选哈希，防止候选或数据被篡改后继续评估。
- AI 投研工作台新增模型调用谱系和证据包的安全摘要；浏览器只收到 provider/model/prompt 版本、受限 token/cost 摘要及 manifest/binding hash，不会收到原始 manifest、受控 URI、prompt/output 或凭据。
- Governance deviation 使用服务器 policy 的性能类 allowlist、actor-owned run/candidate scope、确定性幂等 ID 和追加式撤销时间；它保留原 `FAIL/BLOCKED/NOT_RUN`，拒绝安全目标并在工作台显示为限制，而不是证据通过。工作台读取再次按 actor 隔离，普通页面不渲染理由、风险或补偿控制的自由文本。
- legacy `workflow_steps` 保持兼容但不再被视为执行图：后端请求 schema 和运行摘要均声明 `prompt_display_only`，生成目标与配置页明确它只影响提示/展示，实际阶段必须由服务端运行记录证明。

## 2. 已执行验证

前端历史列表、直链恢复和独立事件轮询已补齐分页尾页保留、A/B 请求所有权及 candidate query 绑定负例，并完成最新全量、类型与构建验证。后端新增单次派发、模型结算和 filesystem resolver 后也已在冻结源码上独立完成全量：5,034 passed、129 skipped、174 warnings，197 项 v2 全部通过；命令、源码摘要、JUnit/hash 和时序见 [六 worker 记录](REGRESSION_6_WORKERS_20260905.md)。下表原 4,993/156 项数字仍是 `HISTORICAL_BASELINE`。最新独立复核发现的两个实现缺口见 [派发安全记录](DISPATCH_SAFETY_20260905.md)，不被完整回归绿色结果抵销。

| 层级 | 命令或范围 | 结果 |
| --- | --- | --- |
| 后端静态检查 | `ruff check`（v2 API、模型、schema、research service、对应测试） | PASS |
| migration head | 迁移图 + 一次性数据库实际版本读回 | PASS：当前唯一 head 为 `20260906_ai_research_search_allocation`；SQLite/PostgreSQL 含完整外键历史 journal 的升级/check、分配写入、降级/重升/check通过。主体保留但分配/trial关联元数据会丢失，不代表无损回退，见 [迁移验收](CURRENT_HEAD_MIGRATION_20260905.md)。 |
| migration（当前候选 head） | 临时 SQLite、PostgreSQL 17.7：`upgrade head → check` | PASS：两种数据库均完成最新链升级，schema check 无新操作。 |
| migration rollback（历史 dataset_identity head） | 两种临时数据库：`downgrade 20260811_asset_research_task_leases → upgrade head → check` | HISTORICAL_PASS：降级时 v2 runs 表不存在，重升后恢复；budget_context 当前 head 与 provider_model 历史 head 的各自父版本降级/重升及历史行保留另见迁移记录。不替代运行中回滚。 |
| migration 契约 | `pytest -q tests/test_iteration_184_migrations.py tests/asset_research/test_migration.py tests/test_ai_research_v2_migration.py` | PASS：19 passed，36 warnings，10.74s |
| migration/paper-runtime 聚焦回归 | migration 契约 + `test_paper_runtime_service.py` | PASS：31 passed，36 warnings，15.36s；覆盖 paper-runtime ORM metadata 对齐后的服务回归。 |
| legacy data-trust PostgreSQL 兼容 | `pytest -q tests/test_datetime_utils.py tests/test_data_trust_api.py tests/test_market_data_coverage_service.py`；一次性 PostgreSQL 17.7 + 实际 FastAPI `POST /api/v1/data/trust/precheck` | PASS：39 passed，3 warnings，9.95s；`asset_specs` 等无时区 timestamp 默认值改用 `utc_now_naive()`，不产生 migration drift。实际认证请求返回 `200/failed` 和 `RB0` asset spec；缺行情覆盖是业务 `failed`，不再映射为时区绑定的 `503`。 |
| 本轮完整回归的 v2 子集 | `backend-full-6-load.xml` 按 `test_ai_research_` classname 核对 | 156 项在最新完整回归内全部通过（JUnit 逐项核对）；在既有 governance/API/lease/worker/迁移契约之上，覆盖 opaque receipt/URI 拒绝、服务器签发的对象版本/摘要/大小/identity hash、预检/任务/物化前重验、legacy snapshot 拒绝、forward receipt 追加、candidate/evidence/approval 完整性链、typed `GENERATE` 原子 materialization 及对象漂移负例，以及原有 output binding/recovery/retry/事件序号/MySQL fallback/诊断 factory。它仅证明本地受控 resolver 与组件合同；不证明真实对象存储、Provider、Evaluator、Sandbox 或端到端执行。`-p no:rerunfailures` 保留既有插件配置，不启用自动重试。 |
| Explorer 启动/部署契约 | 6 核 v2 契约 + `docker compose ... config --quiet` | PASS（T1 代码/静态范围）：156 项包含受限 factory、disabled no-op、完整 executor map、diagnostic factory 与 typed materialization/generic success fail-closed 语义。Compose 静态展开通过，双 flag 关闭时允许空 factory，双 flag 开启后空 factory 仍在 recover/claim 前退出 2。没有 Docker daemon、真实外部 factory、Evaluator/Sandbox/IAM/网络拒绝的运行证据。详见 [EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md](EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md)。 |
| v2 后端 HTTP 契约 | 一次性 PostgreSQL 17.7 + 实际 FastAPI；详见 [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md) | `HISTORICAL_T1`：认证、草稿/确认、family、预检、幂等、owner 隔离、治理脱敏/撤销与默认关闭 `409` 曾经由实际 HTTP 验证，且当时正向链路为 0 model invocation、0 stage attempt。该证据早于本轮 opaque receipt/dataset identity/typed materialization 变更，不能当作这些新 endpoint 与响应脱敏的当前 HTTP 证明；新路径当前由 156 项 v2 本地契约覆盖。 |
| legacy workflow 真值 | `pytest -q tests/test_ai_strategy_research_service.py` + `npm run test -- --run src/__tests__/views/StrategyPage.test.ts` + `npm run typecheck` + `npm run build` | HISTORICAL_BASELINE：168 后端测试（1 warning，299.99 秒）、98 前端页面测试（4.01 秒）、类型检查和构建通过；覆盖 schema、运行摘要、生成目标和配置 UI 对 `prompt_display_only` 的一致披露。 |
| 前端类型 | `npm run typecheck` | 最新重跑 PASS |
| 前端单测 | `npm run test -- --run --minWorkers=6 --maxWorkers=6` | 最新 PASS：147 文件、1,315 用例、33.57 秒；详见 [六 worker 记录](REGRESSION_6_WORKERS_20260905.md) |
| 前端构建 | `npm run build` | 最新重跑 PASS（40.23 秒）；仅既有 Browserslist/大 chunk 提示 |
| 前端静态浏览器 | 临时 preview + `npx playwright test -c playwright.a11y.config.ts --project=chromium` | HISTORICAL_BASELINE：14 passed、1 skipped（显式真实环境用例默认跳过）；包含 `/investment/strategies` 草稿、确认、`BLOCKED → retry → PASS`、键盘 Enter 与 axe。所有 v2 API 均由 fixture 拦截，不能外推为真实服务 E2E。 |
| 前端真实 UI/API | `e2e/a11y/trusted_ai_research.real.spec.ts`；一次性 PostgreSQL 17.7 + 候选 FastAPI + 候选 Vite + headless Chromium；详见 [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md) | `HISTORICAL_T1`：此前候选版本完成 draft → confirm → dataset → epoch → `PASS` precheck → submit → workbench，且 axe serious/critical 为 0、受控 URI 未泄漏。该跑次早于本轮 object receipt 与 typed materialization UI/API 变更，不能声称已覆盖当前界面；当前版本需要完成新的 authenticated real UI/API 演练。 |
| 前端静态 | `npm run lint` | HISTORICAL_BASELINE：0 error、1,318 条 warning；本迭代不以无关全仓格式化掩盖该基线 |
| 后端目录回归 | 6 worker `pytest -p no:rerunfailures -q -n 6 --dist load --durations=15 tests`（无 ignore） | `PASS`：4,993 passed、129 skipped、174 warnings、536.50 秒；JUnit 0 failure/error，其中 156 项 v2 用例全部通过。见 [六进程回归记录](REGRESSION_6_WORKERS_20260905.md)。 |

本轮不排除文件的完整后端回归使用 `-n 6 --dist load --durations=15`，终态为 `4993 passed, 129 skipped, 174 warnings in 536.50s`，退出码 0。JUnit 共 5,122 项、0 failure/error，其中 156 项 v2 用例全部通过且无跳过。原心跳 StaticPool 夹具、Darwin 全机 PID 扫描依赖和本地 CLI 导入遮蔽问题已修复；没有用自动重试、旧绿灯或排除文件补齐本轮结果。完整命令、失败历史、修复边界和 JUnit 摘要见 [REGRESSION_6_WORKERS_20260905.md](REGRESSION_6_WORKERS_20260905.md)。129 项跳过仍保留其原有条件，不代表对应环境场景通过。

根目录的裸 `pytest -q` 另有测试收集卫生问题，不可作为产品回归结果：`scripts/diagnostics/test_ctp_connect_trace.py` 在导入时尝试连接本机 CTP proxy，`src/backend/scripts/legacy/test_acceptance_124.py` 在导入时会 `sys.exit`。本次以项目测试目录 `src/backend/tests` 作为后端回归边界，并保留该问题待独立修复。

## 3. 验收判定

| 决定或证据等级 | 判定 | 原因 |
| --- | --- | --- |
| T0：schema、迁移、静态与 UI 合同 | PARTIAL（数据库迁移、最新前后端回归/类型/构建 PASS） | 当前 schema 已在一次性 SQLite/PostgreSQL 17.7 完成 upgrade/check 及 downgrade/reupgrade/check；真实 UI/API、MySQL、运行中迁移回滚仍需独立验收。 |
| T1：v2 确定性安全/协议契约 | PASS（范围内） | 156 项 v2 契约除原有预注册、family、evidence、lease、取消、配额、隔离拒绝、审批、governance、前端竞态与 migration 外，新增服务器对象 receipt/identity、legacy snapshot 拒绝、任务及 materialization 前重验、forward receipt、candidate/evidence/approval 数据完整性链，以及 typed `GENERATE` 原子候选物化和漂移负例。它只使用本地受控 resolver；不把它描述成真实对象存储、真实 Provider 或端到端研究闭环。实际 HTTP/UI T1 证据发生在没有启动 stage executor 的候选进程上，也不外推为诊断 factory 或真实策略执行验收。 |
| T1：项目完整后端目录 | PASS（保留 skip 与覆盖缺口） | 最新冻结源码、6 worker、无文件排除：5,216通过、129跳过、174 warnings，601.36秒，exit 0；379项 v2全过。首轮预算 FAIL/INTERRUPTED 另存，修复隔离和严格快照校验后以新完整跑次证明，不以聚焦或历史跑次替代。 |
| `IMPLEMENTATION_ACCEPTED` | NO-GO | Explorer 的 fail-closed 部署启动契约、typed candidate materialization 与本地对象身份合同已存在；但尚未证明真实对象存储/IAM 版本与摘要重验、candidate→evaluation→approval→sandbox 的部署端到端连接、真实 Provider、隔离 runner、完整多数据库/多服务隔离和冷重放。 |
| T2：真实数据与 Provider | BLOCKED_ENVIRONMENT | 未使用真实数据、Provider 凭据或生产秘密；没有任何真实研究结果可声明。 |
| T3：前向观察/模拟审批 | BLOCKED_ENVIRONMENT | 未在授权 staging/模拟环境完成冻结后观察期、审批和回滚演练。 |
| `PROTOCOL_PRODUCTION_ENABLED` | NO-GO | 不应打开 v2 feature flag；G5/T2/T3 和生产拓扑证据均未齐备。 |

## 4. 仍需完成的本地集成与环境门禁

第 1 项、全入口联合预算迁移、provider operation/group reconciliation、quota→ledger 崩溃恢复以及费用 UI 口径仍含本地可实现工作，不应全部归类为外部阻塞。已交付的 filesystem resolver 和 HTTP factory 不再记为缺失；真实 Provider 计费上界、账单、存储/IAM、隔离和 T2/T3 证据仍不能由本地 mock、fixture 或历史产物替代。

1. 将已完成的 typed `GENERATE` materialization 与独立 evaluator、approval、sandbox runner 接入同一可审计的任务/命令链；随后在独立 worker 身份、queue、存储凭据和 capability profile 下注册真实阶段执行器，验证无执行器时的 fail-closed 与有执行器时的实际回执一致。
2. 运行真实 container/sandbox 的网络隔离、资源限额、进程清理和无宿主逃逸负例。
3. 以真实受控对象存储 resolver/IAM 取代本地 in-memory resolver，证明不可变版本/字节摘要、权限拒绝和同 key 对象替换的运行时检测；随后使用真实模型 Provider 和不可变证据清单执行 T2 冷重放。
4. 在 staging/模拟环境完成候选冻结后的前向观察、人工审批、灰度与回滚演练。
5. 在解锁的已认证浏览器中，以测试身份完成屏幕阅读器和人工焦点验证；候选 headless Chromium 已连接真实 API 并覆盖基本链路，但不能替代此项。
6. 取得一次性 MySQL 验收库的安全凭据后，执行同样的 `upgrade head → schema check`；随后完成双写/影子读和 rollback drill。
7. （独立工程卫生）若要把仓库根目录的裸 `pytest -q` 也作为回归入口，修复诊断脚本的误收集问题；这独立于本次已通过的 `src/backend/tests` 产品回归入口。

本机 `docker` CLI 可用但仍无法连接 Docker daemon；首次启动 Colima 因虚拟机磁盘镜像下载在约 0.4% 时按有界验收停止，因此第 2 项继续明确记为 `BLOCKED_ENVIRONMENT`。headless Chromium 的真实候选 UI/API 已完成，但当前 macOS 锁屏仍使第 5 项的屏幕阅读器与人工焦点验证无法执行。没有用 mock、静态 preview、命令行存在性或宿主进程替代真实隔离证据；实际候选 UI/API 证据的边界见 [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md)。

此外，读取到的本机常驻 `localhost:8000` OpenAPI 当前没有 v2 路由，`localhost:3000` 前端未运行，因此它们不是本候选版本的验收对象；本轮未越权重启、替换或部署这些服务。

因此，本轮交付的是默认关闭、可审计、遇缺失能力即失败关闭的实现候选；它不表示 AI 已产出有效策略，也不表示可用于实盘或生产启用。实际 HTTP 的隔离 T1 证据和未覆盖边界见 [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md)，本地 AC/需求组对应的证据边界另见 [LOCAL_T1_TRACEABILITY_20260905.md](LOCAL_T1_TRACEABILITY_20260905.md)。
