# 迭代 196 实施与验收状态

> 2026-09-08 当前本地候选：审批权威、human-only run-scoped grant、历史决定严格重放、不可变拒绝围栏、48 项公开错误目录、审批工作台安全投影与当前唯一 migration head `20260908_ai_research_approval_authority` 已完成本地合同终审。冻结后端 Python 来源和只读 Backtrader 快照下，固定 6 worker 功能通道为 6,131 passed、123 skipped、0 failure/error，串行性能通道为 18 passed、6 skipped；两通道互斥覆盖 6,278 cases，其中 6,149 passed、129 skipped。前端固定 6 worker 为 154 files、1,556/1,556 passed，typecheck、strict catalog verifier、build 与 scoped lint/node check 通过，但 Node 25.1.0 超出 `>=20 <25`，只记 `LOCAL_PASS_UNSUPPORTED_RUNTIME`。全仓 `ruff format --check` 仍有 16 文件待格式化，不能称为全静态绿。完整命令、哈希、失败历史和限制见 [2026-09-08 回归记录](REGRESSION_6_WORKERS_20260908.md)。工作树仍有大量未提交变更，Backtrader `1.3.0` 不满足声明的 `>=1.9.78.123`，真实三数据库 online、跨进程竞争、对象存储/IAM、queue/Evaluator/Provider、authenticated current UI、T2/T3 未闭合，因此整体及生产启用仍为 `NO-GO`。

> 2026-09-07 历史候选：严格 candidate-freeze receipt、server-owned holdout request、内部 Evaluator claim/start 与 lease fencing、独立评估恢复、13 项 promotion gate、审批同事务锁定/重验及本地沙箱双阶段超时协议已补齐。当时冻结 `app/tests` 来源和只读 Backtrader 导入快照下，六 worker 功能通道 5,561 passed、123 skipped，串行性能通道 18 passed、6 skipped；两通道共收集并互斥划分 5,708 cases，其中5,579 passed、129 skipped、0 failure/error。前端 1,345 项、typecheck、build 在 Node 25.1.0 本机通过，只记 `LOCAL_PASS_UNSUPPORTED_RUNTIME`。完整历史见 [2026-09-07 回归记录](REGRESSION_6_WORKERS_20260907.md) 与 [claim/start 证据](HOLDOUT_CLAIM_START_20260907.md)，不得替代当前候选证据。

> 2026-09-07 历史局部切片：request 时仍只写 `QUEUED/REQUEST_HOLDOUT`，产生 0 authorization、0 evaluation；其后内部 claim 原子建立一个已消费的 JIT authorization、一个 `RUNNING` evaluation 和 generation-fenced lease，迁移 head 当时推进为 `20260907_ai_research_holdout_claim`。独立 6 worker focused T1 为 184 passed、42 warnings、48.06秒、exit0。`RUNNING` evaluation 不是实际密封计算或终态结果。完整范围、11 文件 SHA、失败诊断与剩余边界见 [claim/start 历史证据](HOLDOUT_CLAIM_START_20260907.md)。

> - 更新日期：2026-09-08
> - 文档基线/当前提交：`a18bcf52682686c30d919fe02d6fd734ee4271b9`
> - 实施分支：`codex/iteration-196-ai-research-trust`
> - 实施工作树：`/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`

> 历史预算切片：完整后端5,216通过、129跳过、601.36秒，6 worker；379项 v2 全过。不可变 HTTP 请求、Token/金额联合预算、快照持久化及严格派发拒绝的证据见 [预算交付记录](MODEL_BUDGET_BUNDLE_20260905.md)。历史跑次保留在 [回归记录](REGRESSION_6_WORKERS_20260905.md)，不作为后续源码证明。独立评估/审批/沙箱图、全入口预算与组对账仍有本地开发工作，真实供应商计费上界另需审核；整体验收保持 `NO-GO`。

## 1. 评审处置结论

[REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) 的核心判断合理，但不应逐字照搬其数字和前提。正式处置见 [REVIEW_DISPOSITION.md](REVIEW_DISPOSITION.md)：16 项 finding 中直接采纳 11 项、部分采纳 5 项、无整体拒绝项；评审中关于 P0 数量、XL 数量和多数据库 NFR 编号的三处事实误差已校正。

需求、设计、验收和逐项追踪仍分别以 [REQUIREMENTS.md](REQUIREMENTS.md)、[DESIGN.md](DESIGN.md)、[ACCEPTANCE.md](ACCEPTANCE.md)、[TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md) 为权威。该状态记录不改写独立评审原文，也不把“有单元测试”表述为真实研究有效或生产启用。

## 2. 已落地的协议实现

- 协议 v2 写入默认由服务端 feature flag 关闭；既有 legacy 读取路径不被 v2 路由重写。
- 假设确认、数据快照、实验 epoch、候选冻结、试验账本、模型谱系、统计硬门和人工决定均有独立的持久化模型与 owner-scoped 服务边界。server-owned 路径已延伸到 holdout request→内部 claim/start，但实际密封计算、artifact checkpoint、evaluation finalize、promotion、approval 和 sandbox 仍未由真实部署 worker/API 串成一次生成→候选→独立评估→审批→沙箱执行端到端事务流。
- 预注册在服务端做完整性与语义校验；浏览器只能先创建草稿、明确确认并通过服务端数据预检后，才能提交绑定的研究运行。确认回执与启动请求以规范化内容哈希精确绑定。
- experiment epoch 的 family hash 仅由服务端从已确认的预注册身份字段派生；API 禁止客户端传入 `family_hash`，同一 owner/family 在数据库中唯一。旧库若已存在重复 family，迁移会 fail-closed 要求人工对账，而不会静默挑选或合并记录。
- 数据快照现在只能由服务器对象 receipt 创建：浏览器/API 只传不透明 `object_receipt_id`，受控 resolver 签发并保存逻辑对象、不可变版本、摘要、大小、校验时间、receipt hash 与 snapshot identity hash；客户端传 URI/version/digest/size 一律拒绝。旧 `storage_uri` 兼容快照明确标为 `LEGACY_UNVERIFIED`，严格路径拒绝它。预检、任务创建和 typed `GENERATE` 物化均会重新核验对象；任务提交遇到漂移会持久记录 `FAILED` 数据完整性状态后拒绝创建任务。候选冻结、holdout/independent evaluation、evidence package、approval 及 forward readiness 都要求受证明快照；forward 追加同样只接收对象 receipt。当前证据使用进程内受控 resolver，尚未接入真实对象存储/IAM，因此不能把本地 fixture 的替换检测外推为生产存储完整性证明。
- 预检为 `FAIL`、`BLOCKED` 或过期时，浏览器只会对同一份已确认 hypothesis、dataset 和 epoch 重做服务端预检，不能借“重试”创建新的 family 或留出预算；创建草稿同时要求 profile ID/version，默认信息截止点也不会因客户端时区早于研究窗口而伪阻断。
- 候选冻结必须由调用方提交预期内容哈希；冻结、签发及消费 holdout 授权时都会重验代码/依赖/参数/数据/环境等绑定，授权还绑定候选哈希，防止冻结后内容或数据漂移被误用。
- discovery candidate 的严格冻结现在会原子写入追加式 `candidate-freeze-v1` receipt，绑定候选/代码/参数/依赖、完整 trial ledger、搜索预算与计数、数据、环境、成本和 workflow version；数据库禁止 receipt 更新/删除。holdout、independent evaluator、evidence package、promotion 和 forward policy 均重新验证同一 receipt 指纹，缺失、漂移或旧冻结一律 fail-closed。holdout request/claim/finalize、evidence command 与审批权威的线性迁移已继续推进，当前唯一 Alembic head 为 `20260908_ai_research_approval_authority`。
- holdout request HTTP 路径只持久化 server-owned command：服务端从唯一合格的 `VERIFIED + SEALED_HOLDOUT` snapshot 解析绑定，写入 `QUEUED/REQUEST_HOLDOUT`，并以幂等键、提交结果读回和追加式 `ACCEPTED/REJECTED/UNKNOWN` 审计保持 fail-closed。OpenAPI 契约、actor+IP 的本地 `30/minute` 限流、20 并发同 key 收敛与 snapshot quarantine 已有 focused T1；真实 queue/Evaluator/IAM 及实际密封评估尚未执行。
- 内部 `HoldoutClaimService` 不暴露公开 claim/heartbeat/recover API。成功 claim 在同一事务中把 command 改为 `RUNNING/HOLDOUT_PENDING`，JIT 创建并消费唯一 authorization，创建唯一 `RUNNING` evaluation，把 epoch 改为 `DISCLOSED`，追加 access audit，并只持久化 bearer token 哈希。heartbeat 以 runtime identity、owner、token hash、generation、状态与数据库时间共同 fencing；过期或 commit-ACK 不确定会进入保守 `RECONCILING`，不能重新 claim 或重复签发。这里仍未执行真实 sealed 数据读取、指标计算、checkpoint/finalize 或终态晋级。
- independent evaluator 的 operation/terminal receipt 支持精确幂等与恢复：同一终态可重放，参数或绑定改变会拒绝；晋级以 13 项具名 gate、完整保留 trial ledger 和 DSR 置信阈值作服务端裁决，不允许综合分数掩盖单门失败。该实现仍是本地组件/数据库合同，不等于独立 Evaluator 身份和密封数据面已经部署。
- 审批写入与证据/candidate/gate 的最终重验使用同一数据库 session 和锁序，关闭读取后再提交造成的 TOCTOU；策略内容或证据在锁内变化会拒绝。此处仍不把 single-actor 补偿控制冒充职责分离。
- capability profile 以版本、证据哈希和过期时间决定能力；无法证明拓扑隔离时密封/沙箱相关路径 fail-closed。
- Durable task 支持 request-hash 幂等、CAS 租约、取消优先、过期恢复和终态同步；配额采用 reservation/fencing/reconciliation，而非超时自动释放。
- 最新新增部署侧 filesystem resolver、显式摄取 CLI 与 API 静态 factory 接线：实际读取字节签发持久 receipt，每次重新哈希、跨实例重验，默认关闭且不支持 sealed。FIFO、symlink、权限、inode 替换、临时 hard-link 崩溃恢复和异步活性已补回归；这扩展了此前仅 in-memory 的本地实现证据，但不替代 IAM/真实行情数据。详见 [文件 resolver 记录](FILESYSTEM_DATASET_RESOLVER_20260905.md)。
- 最新 LLM/Sandbox 派发已改为单次 reservation CAS，重检取消、task/attempt lease、resource/unit 与数据库时间。LLM 只在完整已知 token 用量结算后返回成功，未知/超额保留预算；结算用同一事务的凭证 CAS 和汇总算术 UPDATE，避免不同调用并发丢记账。详见 [60 项聚焦证据与剩余边界](DISPATCH_SAFETY_20260905.md)。
- generation 严格路径现强制 Token／microUSD 完整组原子预留、claim 与结算，绑定不可变请求 bytes、受审计费政策和持久 quote context；正确 hash 但缺快照、请求/价格漂移或部分 receipt 均零 HTTP。未知用量不零记账，旧单笔恢复接口不能拆组。部署合同与用量计算出的保守金额不是真实发票；全入口统一、provider readback/group reconciliation 及账本崩溃窗口尚未闭合，见 [预算交付记录](MODEL_BUDGET_BUNDLE_20260905.md)。
- 租约恢复对“阶段可能已经产生外部副作用”的任务保守地标为结果未知，而不会重新排队并重复调用外部 Provider/runner。
- `ResearchProtocolWorker` 是部署侧 worker 的组合根：每一阶段先写入持久 checkpoint，再调用显式注册的执行器；没有注册执行器时以 `RESEARCH_STAGE_EXECUTOR_UNAVAILABLE` fail-closed，不能把占位符结果标为成功。
- stage 的 `SUCCEEDED` 现在一律要求内容受控、内容哈希/长度可复核、并精确绑定到 owner/run/task/attempt/request hash 的输出；无工件成功、旧无绑定成功 checkpoint 的恢复、篡改 blob、编码路径穿越和错误 request hash 均 fail-closed。已终态 attempt 的 idempotent retry 只读取/验证，不能用新的 `next_stage` 改写 task/run cursor。
- `GENERATE` 已新增 server-owned typed materialization：只有 `ProposedGeneration` 能进入正向路径；服务器在同一事务内重验 stage/output/run binding 和当前受证明数据对象，生成可变 candidate、代码/参数/依赖/模型调用 manifest、artifact binding、materialization receipt 与结果。逻辑对象在排队后发生版本或摘要漂移时，物化失败且不创建 candidate；未配置对象 resolver 同样失败关闭。generic terminal success 仍被改写为 `RESEARCH_GENERATION_CONTRACT_UNAVAILABLE`，诊断 executor 仍只会 `NOT_CALLED/NOT_EXECUTED` 后以 `RESEARCH_GENERATION_NOT_EXECUTED` 失败。
- 此 materialization 的语义严格为 `MATERIALIZED_NOT_EXECUTED`：它没有调用真实 Provider、Sandbox、backtest、Evaluator、审批或市场试验。Candidate、evaluation/gate、evidence/approval 与 sandbox runner 仍未由经过部署的 worker/API 组合为生成→独立评估→审批→沙箱执行的端到端运行链，因此不能被表述为有效策略、批准或隔离运行的证据。
- 后续新增 `ResearchGenerationExecutor`：固定部署 prompt/model alias/sampling/quota 政策，服务端重读已确认研究输入与数据证明，仅允许发现/迭代验证分区，调用配额和注入的 gateway 并返回 typed proposal。原 9 项组件测试之外，现有 HTTP adapter 和独立 `generation:create_worker` 同时安装执行器、共享 resolver 与物化服务；旧 explorer 诊断 factory 未切换。配置 pin/供应商观察型号分列保存，公开 worker 的生成物化链已有本地 HTTP seam 正反测试，详见 [生成部署记录](GENERATION_PROVIDER_DEPLOYMENT_20260905.md)。
- 长轮询由独立 Explorer 进程显式调用，而非 FastAPI startup hook；该入口只接受完整的 `CLARIFY/GENERATE` executor map，缺任一执行器即在首次 recover/claim 前以 `RESEARCH_WORKER_EXECUTORS_INCOMPLETE` 拒绝启动。worker 在已领取任务的 stage 外部执行期间持续 CAS heartbeat；续租失败不会让旧 worker 获得迟到 checkpoint 的提交权。
- Explorer 现有 deployment-only bootstrap、CLI 与可选 Compose overlay：只有同时打开 v2/worker 两个 flag 后，才从镜像内受限 `app.research_deployments.*` namespace 解析工厂；factory 必须返回完整的 `ResearchProtocolWorker`，空/非法/导入失败/错误返回值均在首次 recover/claim 前以稳定 code 退出。已提供的 `explorer:create_worker` 仅实现确定性诊断 receipt：`CLARIFY` 成功进入下一阶段，`GENERATE` 以 `RESEARCH_GENERATION_NOT_EXECUTED` 失败；默认配置仍不引用它。overlay 默认不启动、无 host port/volume、只读非 root、drop capabilities 且 `restart: "no"`；它明确不是 sealed Evaluator 或真实 Sandbox 的能力证明。
- 已成功 stage 的回执与 task/run 游标推进同一事务提交；新 lease 只采纳符合持久图的同 task/stage 成功证据，绝不重放已完成阶段。默认 generation-v1 保留 CLARIFY→GENERATE，显式 discovery-v1 增加 VALIDATE_DISCOVERY；模型不能选择图或 successor。当前阶段最新失败/超时/取消 checkpoint 的恢复直接收口，不再重新排队；未知运行中回执仍不盲重试。
- 取消在阶段执行返回后的竞态已闭合：阶段回执会记录 `CANCELLED/TASK_CANCEL_REQUESTED`，任务与运行同样以取消终态收口，不遗留 `RUNNING` attempt。
- LLM 与沙箱外部副作用现在同时要求有效配额、当前 task 租约和运行中的 stage attempt；错绑、取消、过期或旧租约均拒绝在 provider/runner 前执行。
- evidence package 仅由服务端从已冻结且完整性重验通过的候选及当前门禁材料构建；其 manifest/hash/binding 可重新验证，审批不能接受客户端伪造 hash，材料变更会令旧 package stale。
- governance deviation 现由独立的追加式服务处理：服务器 policy 默认不允许任何偏差，且即使 allowlist 被配置也只接受 `NFR-PERF-###` 目标；记录强制绑定当前 actor 自己的 run/candidate、原 `FAIL/BLOCKED/NOT_RUN` 状态、风险、补偿控制、生效/到期时间和幂等键。撤销只追加时间，不会删除或改写原状态；工作台查询也再次按 actor 隔离，并以“限制而非 PASS”摘要显示。
- 前向观察必须晚于候选冻结和策略起点，按数据源、延迟、事件时间、采集时间和质量策略落账；未满足窗口保持未就绪，不用旧数据冒充未来观察。
- 存量 YAML profile 可脱敏隔离；无 owner 的历史档案必须显式认领，不能自动归属给当前登录用户。
- AI 投研页新增证据工作台，展示预注册、数据、账本、门禁、人工决定、模型谱系和 evidence package 身份；工作流明确分为“草稿 → 确认与数据预检 → 启动”，前端用 request generation 与 `AbortController` 隔离晚到响应，所有新增文案走中英文 i18n，且完整 manifest/受控 URI 不进入浏览器。
- legacy `workflow_steps` 保持后向兼容，但不再被描述为可执行编排：API schema 与运行摘要固定返回 `prompt_display_only` 语义，生成目标和配置页明确它只影响提示/展示，实际阶段以服务端运行记录为准；v2 固定执行图不接受它作为输入。
- 默认主题的关键状态对比度已收紧：主色回退、侧栏激活态与策略分类选中态使用可满足前景色对比度的色值；此前静态 axe 发现的 3 个 serious `color-contrast` 项已由回归测试覆盖。
- 与投研页共用的 legacy market-data trust 模型现在也遵守既有 PostgreSQL 无时区 timestamp 合同：`asset_specs`、coverage、quality report 和 robustness result 的默认时间统一使用 `utc_now_naive()`。这只修复 ORM 默认值与既有列的绑定，不改 migration 或历史时间语义；空 PostgreSQL 库上的实际 `/api/v1/data/trust/precheck` 因而返回正常业务 `failed/200`，不再因 asyncpg 时区绑定错误返回 `503`。
- PostgreSQL migration/schema-check 暴露的历史 paper-runtime metadata drift 已闭合：既有数据库同时有 `source_record_id` 的唯一约束和唯一索引，ORM 现在显式表达二者并由回归测试锁定；这是元数据对齐，不是业务约束或历史 migration 的改写。
- 本地 multiprocessing 策略验证现在先在子进程应用资源限制并发出版本化 ready，再分别执行有限 bootstrap 和 runtime/preflight 预算；terminal 协议与进程清理均 fail-closed。不可信代码自身的执行时限没有放宽。该路径只用于开发/测试；生产仍要求真实 Docker 隔离证据。

## 3. 已执行验证

当前候选采用互斥分层回归：非性能功能集固定 6 个 xdist worker，性能标记集串行执行。两者在后端 Python 来源摘要 `03513ad1302d16e567ec180705181ac85be7d18fd25b88f5a13669de80988ec1` 和只读 Backtrader 快照上覆盖 6,278 cases，其中 6,149 passed、129 skipped、0 failure/error。前端固定 6 worker 为 154 文件、1,556/1,556 passed，类型检查、strict catalog verifier、build 与 scoped lint/node check 通过；Node 25.1.0 超出声明范围，只记 `LOCAL_PASS_UNSUPPORTED_RUNTIME`。完整事实以 [2026-09-08 六 worker 记录](REGRESSION_6_WORKERS_20260908.md)、[审批权威记录](APPROVAL_AUTHORITY_20260908.md)、[前端工作台记录](APPROVAL_WORKBENCH_FRONTEND_20260908.md) 和 [当前 head 迁移记录](CURRENT_HEAD_MIGRATION_20260908.md) 为准。2026-09-05～07 跑次继续保留为历史基线；横向回归 PASS 不等于具名 AC、真实研究或生产整体验收。

| 层级 | 命令/范围 | 结果 |
| --- | --- | --- |
| 当前后端功能通道（冻结 Python 来源/Backtrader） | 原生数学库各限 1 线程；`pytest -p no:rerunfailures -q --tb=short --durations=20 -n 6 --dist load --maxschedchunk=8 -m 'not performance' ... tests` | 6,254 cases：6,131 passed、123 skipped、0 failure/error；JUnit time 960.565秒，pytest终端961.25秒（约16:01）；JUnit SHA-256 `cb48d988...54fe`；AI research classname 1,303/1,303、approval 299/299。完整命令见 [当前回归](REGRESSION_6_WORKERS_20260908.md) |
| 当前后端性能通道（同一冻结来源） | `pytest -p no:rerunfailures -q --tb=short --durations=20 -m performance ... tests`，串行 | 24 cases：18 passed、6 skipped、0 failure/error，14.96秒，6,254 deselected；JUnit SHA-256 `266e5467...ab20`。功能/性能互斥并集为6,278；6条skip不是PASS |
| 首轮 6 worker 失败报告 | 与最终功能通道同形命令，原 JUnit 保留且未覆盖 | 6,207 cases：6,082 passed、123 skipped、2 failed、0 error；旧 migration head 断言与旧 ADMIN 权限长度断言经 RED/GREEN 修正，见 [失败闭环](REGRESSION_6_WORKERS_20260908.md#4-首轮失败记录与修复闭环) |
| 2026-09-07 历史后端功能通道 | 当时 `pytest tests -m 'not performance' -p no:rerunfailures -q -n 6 --dist load --maxschedchunk=8` | 5,684 cases：5,561 passed、123 skipped、0 failure/error，818.39秒；只证明当时源码，见 [历史记录](REGRESSION_6_WORKERS_20260907.md) |
| 2026-09-07 历史后端性能通道 | 当时 `pytest tests -m performance -p no:rerunfailures -q`，串行 | 24 cases：18 passed、6 skipped、0 failure/error，14.94秒；只证明当时源码 |
| holdout claim/start 局部 T1 | claim/request/authorization/evaluator/promotion/API/migration/dataset/freeze 相邻合同，限制原生数学库各 1 线程，`pytest -p no:rerunfailures -q --tb=short -n 6 --dist load --maxschedchunk=8 ...`；见 [独立证据](HOLDOUT_CLAIM_START_20260907.md) | 184 passed、42 warnings、48.06秒、exit0；11文件 manifest SHA-256 `a1fde1...d9c`。只证明内部 claim/start、lease/heartbeat/recovery、本地并发、迁移及相邻合同；实际 sealed evaluation/checkpoint/finalize 为 `NOT_RUN` |
| 当前依赖来源 | 只读 `PYTHONPATH` 快照 | 快照 SHA-256 `34a1e78d...bee1`，但 `backtrader 1.3.0` 不满足项目声明 `>=1.9.78.123`；依赖可复现性保持 `NO-GO` |
| 当前静态检查 | 全仓 Ruff、compileall、format、diff/冲突扫描及 scoped 检查 | `ruff check app tests alembic scripts`、conda base `python -m compileall -q app tests alembic scripts`、`git diff --check`、冲突扫描 PASS；**全仓 `ruff format --check` FAIL：16 files would reformat**。本轮审批/迁移/frontend scoped format PASS；不得称为全静态绿 |
| 当前 Git 候选身份 | worktree/branch/commit 读回 | `/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`、`codex/iteration-196-ai-research-trust`、`a18bcf52682686c30d919fe02d6fd734ee4271b9`；仍有大量未提交变更，`G0 provenance/candidate seal=NO-GO` |
| 当前迁移 head | 审批权威 schema 与本地 migration 合同 | 唯一 head `20260908_ai_research_approval_authority`；独立 suite 135/135，SQLite/PostgreSQL/MySQL/MariaDB 离线 SQL 4/4 与 heads PASS。真实 PostgreSQL/MySQL/MariaDB online、触发器/函数、跨进程竞争和 operational rollback 均为 `NOT_RUN_CURRENT_HEAD`，见 [当前迁移验收](CURRENT_HEAD_MIGRATION_20260908.md) |
| 历史迁移基线 | SQLite/PostgreSQL 空库与聚焦 migration 契约 | `HISTORICAL_BASELINE`：当时的 upgrade/check、降级/重升及 19/31 项聚焦结果只证明对应历史源码，不替代当前 head 或运行中任务 operational rollback |
| 历史 legacy data-trust PostgreSQL 兼容 | 一次性 PostgreSQL 17.7 上的服务与实际 FastAPI precheck | `HISTORICAL_BASELINE`：当时 39 项及 `200/failed` 结果只证明对应历史源码，不作为当前候选 HTTP 证据 |
| 前端 | `npm run typecheck`；48项 strict catalog verifier | `LOCAL_PASS_UNSUPPORTED_RUNTIME`：typecheck PASS；目录版本 `ai-research-approval-errors/v1`、摘要 `6dd9f6ce...0d53`，backend/frontend 精确比较 PASS；Node 25.1.0 超出 `>=20 <25` |
| 前端 | `npm test -- --run --minWorkers=6 --maxWorkers=6 ...` | `LOCAL_PASS_UNSUPPORTED_RUNTIME`：154 文件、1,556/1,556 用例通过，19.29秒；JSON SHA-256 `86c6380a...467b`；Node 20 lane `NOT_RUN` |
| 前端 | `npm run build`；scoped ESLint/node check | `LOCAL_PASS_UNSUPPORTED_RUNTIME`：4,091 modules、22.67秒，build与scoped检查PASS；发布门须Node20重跑 |
| 前端静态浏览器 | 临时 preview + `npx playwright test -c playwright.a11y.config.ts --project=chromium` | `HISTORICAL_BASELINE`：当时14通过、1跳过且API由fixture拦截；当前候选未重跑，不能作为当前UI/a11y证据。 |
| 前端真实 UI/API | `e2e/a11y/trusted_ai_research.real.spec.ts`；一次性 PostgreSQL 17.7、候选 FastAPI、候选 Vite 与 headless Chromium；详见 [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md) | `HISTORICAL_T1`：此前版本的真实认证会话完成草稿、确认、dataset、epoch、`PASS` precheck、run 与 workbench，且无 v2 fixture、axe serious/critical 为 0、未发现受控 URI 泄漏。本轮新增 object receipt 与 typed materialization 后尚未重做该 authenticated real UI/API 演练，不能把旧跑次称为当前界面证据。 |
| 2026-09-07 历史前端静态 | 当时 `npm run lint` | `HISTORICAL_BASELINE`：exit0、0 error、1,338 条 warning；当前只声明本轮 scoped ESLint PASS，不沿用此数字冒充当前全仓 lint |
| legacy workflow 真值 | `pytest -q tests/test_ai_strategy_research_service.py`、前端 StrategyPage 测试、typecheck/build | `HISTORICAL_BASELINE`：当时后端168项、前端页面98项及构建结果保留，不替代当前候选的对应聚焦证据。 |
| 当前完整回归的 AI research/approval 子集 | 最终功能 JUnit classname 统计 | AI research 1,303/1,303 passed；approval 299/299 passed；属于当前本地组件合同证据，不证明真实对象存储、Provider、Evaluator、Sandbox 或端到端研究闭环 |
| 当前审批终审 | 历史 grant、ACK-loss、类型校验、48项公开错误目录、真实1+19 SQLite barrier | P0/P1/P2=0；审批三文件164/164，API/hypothesis相关61/61。scoped mypy 1.16.1为0 error；项目锁定1.20.2 `NOT_RUN_PINNED_VERSION`，见 [审批权威记录](APPROVAL_AUTHORITY_20260908.md) |
| Explorer worker bootstrap | 历史6核 v2 聚焦组 + `docker compose ... config --quiet` | `HISTORICAL_BASELINE`：当时 diagnostics factory、静态 Compose 等契约随156项回归通过；当前真实外部 factory、Docker daemon、Evaluator/Sandbox/IAM/网络仍未验证。详见 [EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md](EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md)。 |
| 后端 HTTP 协议 | 一次性 PostgreSQL 17.7 + 实际 FastAPI 进程；详见 [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md) | `HISTORICAL_T1`：此前版本在真实 HTTP 上验证了认证、草稿/确认、family、预检、幂等、脱敏、owner 隔离、治理偏差及默认关闭 `409`；runner/provider 未启动。本轮新增 object receipt/dataset identity/typed materialization 后尚未重做该隔离 HTTP 演练，当前新路径只可称为本地契约覆盖。 |
| 2026-09-07 历史本机常驻实例 | 当时读取 `localhost:8000/openapi.json` 与 `localhost:3000` | `HISTORICAL_BASELINE/NOT_CANDIDATE`：当时8000的OpenAPI不含v2路由、3000未运行；本轮未部署候选，authenticated current UI仍为`NOT_RUN`。 |
| 后端目录回归（2026-09-05～06） | 6 worker 全目录历史跑次 | `HISTORICAL_BASELINE`：4,993 passed、129 skipped、0 failure/error、536.50秒；只证明当时源码，见 [历史六进程回归记录](REGRESSION_6_WORKERS_20260905.md)。 |

历史跑次曾使用 `-n 6 --dist load --durations=15`，终态为 `4993 passed, 129 skipped, 174 warnings in 536.50s`，退出码 0。该 JUnit 共5,122项、0 failure/error，其中156项 v2 用例全部通过且无跳过；它只证明2026-09-05～06当时源码。完整命令、失败历史、修复边界和 JUnit 摘要见 [REGRESSION_6_WORKERS_20260905.md](REGRESSION_6_WORKERS_20260905.md)。2026-09-07 的 5,708-case 分层跑次同样保留为历史证据；所有跑次的 skip 均保留原条件，不代表对应环境场景通过。

当前唯一线性 head 已推进为 `20260908_ai_research_approval_authority`。独立 migration suite 135/135、SQLite/PostgreSQL/MySQL/MariaDB 四个离线 SQL lane 与 heads 读回通过；真实 PostgreSQL/MySQL/MariaDB online upgrade/反射、触发器/函数执行、跨进程唯一竞争及 operational rollback 均为 `NOT_RUN_CURRENT_HEAD`。前一 heads 的一次性数据库记录继续限定为各自历史的 `SESSION_TRANSCRIPT_PASS / PERSISTENT_EVIDENCE_PARTIAL`，不能向当前 head 外推。详见 [当前迁移验收](CURRENT_HEAD_MIGRATION_20260908.md) 与 [此前迁移历史](CURRENT_HEAD_MIGRATION_20260905.md)。较早真实 HTTP/UI 仍为 `HISTORICAL_T1`。

## 4. 验收判定

| 判定 | 当前状态 | 原因 |
| --- | --- | --- |
| T1 自动化/契约地基 | `LOCAL_PASS_WITH_SKIPS_PARTIAL_ENV_FREEZE（后端）/ LOCAL_PASS_UNSUPPORTED_RUNTIME（前端）` | 后端功能/性能互斥通道共6,278 cases、6,149通过、129跳过、0 failure/error；AI research 1,303/1,303、approval 299/299。Backtrader 1.3.0不符合声明范围。前端1,556/1,556在Node25通过但须Node20复验。skip、离线DB和本地组件证明不代表真实Provider/runner、完整研究闭环或生产验收。 |
| `IMPLEMENTATION_ACCEPTED` | `NO-GO` | 审批终审P0/P1/P2=0、迁移与工作台合同已增强，但工作树未提交、全仓format仍有16文件未过、生产对象存储/IAM、可重建的Backtrader依赖、三数据库online/跨进程竞争、真实Provider/Sandbox/runner、当前authenticated E2E与完整冷重放证据仍缺。 |
| T2 真实数据与 Provider | `BLOCKED_ENVIRONMENT` | 本次未使用授权的真实数据、真实模型 Provider 或生产凭据。 |
| T3 前向观察/模拟盘审批 | `BLOCKED_ENVIRONMENT` | 尚无冻结后的真实观察窗口和获授权的 staging 审批环境。 |
| `PROTOCOL_PRODUCTION_ENABLED` | `NO-GO` | 没有多服务隔离拒绝证据、真实 container no-network/resource 证据、T2/T3 证据或灰度/回滚演练。 |

因此，这一轮交付的是可审计、默认关闭、fail-closed 的协议实现候选，而不是“AI 已自主生成有效策略”或“可上线实盘”的声明。当前命令、结果、首轮失败和边界见 [2026-09-08 六 worker 回归记录](REGRESSION_6_WORKERS_20260908.md)，审批与迁移证据分别见 [审批权威记录](APPROVAL_AUTHORITY_20260908.md)、[前端工作台记录](APPROVAL_WORKBENCH_FRONTEND_20260908.md) 和 [当前 head 迁移记录](CURRENT_HEAD_MIGRATION_20260908.md)；2026-09-05～07 的文档继续作为历史记录。进入真实环境前仍必须按 [ACCEPTANCE.md](ACCEPTANCE.md) 的 G0–G5、T2/T3 和 rollback drill 补齐独立证据。
