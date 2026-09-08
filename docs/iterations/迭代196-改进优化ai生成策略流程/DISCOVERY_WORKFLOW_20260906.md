# 版本化发现工作流与阶段原子提交

日期：2026-09-06。实施仅在 `codex/iteration-196-ai-research-trust` 隔离工作树；本文不授权部署或真实 Provider/runner 调用。

> 最终完整后端：**5,400通过、129跳过、184 warnings、502.81秒、6 worker、exit0**；562项v2全过、无跳过。跑前/中/后源码一致。完整命令与JUnit见 [六worker回归记录](REGRESSION_6_WORKERS_20260905.md)。本地切片通过不等于迭代整体或真实部署验收。

## 1. 交付范围与真值

本批把此前独立的 generation、discovery execution、trial publication 接到部署侧公开 worker 入口。目标需求与发布门不变，以 [需求](REQUIREMENTS.md)、[设计](DESIGN.md)、[验收](ACCEPTANCE.md) 为准；上批发现基础链及其5,353通过的完整回归是 [历史证据](DISCOVERY_PUBLICATION_20260906.md)，不能证明本批新增源码。

| 持久图版本 | 服务端执行顺序 | 兼容规则 |
| --- | --- | --- |
| `generation-v1` | CLARIFY → GENERATE → 任务结束 | 迁移前的任务、默认设置及旧 worker 继续使用此图 |
| `discovery-v1` | CLARIFY → GENERATE → VALIDATE_DISCOVERY → 任务结束 | 新研究由服务端显式选择；discovery worker 支持两种图 |

`SUCCEEDED` 只表示该版本工作流完成，不表示策略盈利、统计门通过、候选冻结、独立留出评估通过或获准模拟/实盘。新 discovery 图结束时候选仍为 `MUTABLE`。

## 2. 服务端图与部署契约

- `ResearchRun.workflow_version` 是非空持久字段，默认及数据库默认都是 `generation-v1`。旧行不被静默升级为新图。
- 新任务版本来自 `AI_RESEARCH_PROTOCOL_V2_WORKFLOW_VERSION`；API 请求不能选择执行图。已有幂等任务返回原 run/version，改变部署设置不会改写旧任务，也不改变原预检/request hash 的含义。
- 图定义集中在 `workflow_graph.py`。worker 的完整执行器校验、领取、恢复、阶段 successor 及 checkpoint 输入都使用持久版本；旧 worker 不领取/恢复新图任务。
- `generation:create_worker` 维持旧图；新静态 factory 为 `app.research_deployments.discovery:create_worker`。新 factory 复用 generation 组合组件，并注册三个实际执行器；共用同一个 DatasetRegistry，不制造 dummy 成功结果。
- 双 feature flag 默认关闭。discovery endpoint、token、runner identity、镜像摘要、no-network、只读输入、CPU/内存/PID/输出上限、wall deadline、quota policy/lease 和 HTTP timeout 均来自部署配置，构建期间不调用业务库或网络。错误不得包含 token、URL、对象根目录或政策内容。
- 部署时需先迁移，再部署支持两种图的 worker，确认配置/依赖就绪后才能把 API 新任务设置切到 discovery-v1。本次未执行这些生产步骤。

## 3. 副作用、事务和恢复

1. `DiscoverySandboxService.execute()` 使用既有配额、搜索占位和持久 execution journal 调用远端。已知结果先保留为 `OBSERVED`，配额已知用量结算后返回。
2. `DiscoveryStageExecutor` 只返回 execution ID 与该结果的 status/error，不生成 trial、artifact ID 或下一阶段。
3. `ResearchStageAttemptService.complete()` 在同一事务内重验 owner/run/stage/lease、真实 command/result、quota、candidate、dataset 和保留输入字节；调用 `DiscoveryTrialMaterializer.publish_in_session()`。
4. trial、returns evidence、artifact binding、journal.trial_id、stage terminal 状态及阶段完成事件同时提交。调用者提供的 status/error 必须等于执行结果，不能把 FAILED 改为 SUCCEEDED。最后再次以数据库时间验证 lease。
5. Task/Run 的最终收口仍由 worker 在后续事务执行；若它在已成功的 checkpoint 后崩溃，新 lease 只读验证 journal→trial→artifact 的绑定和规范化字节，再收口任务，不重复外部执行或插入新 trial。

当前阶段最新 checkpoint 已为 FAILED/TIMED_OUT/CANCELLED、而 Task 尚未最终提交时，租约恢复直接保留该 checkpoint 并以其 status/error 收口 task/run、清理 lease，不重排队。最新 SUCCEEDED 仍走成功恢复；仍有 RUNNING checkpoint 则保留未知结果语义。这一恢复用例模拟持久状态/过期租约，不冒充实际 kill -9 跨进程演练。

发现阶段不接受“任意绑定工件 + SUCCEEDED”。已观察市场结果的 FAILED/TIMED_OUT/CANCELLED 先发布其真实试验，再按失败类终态收口；是否计为市场试验只取决于已观察结果，不由任务成功与否决定。

用户取消与已知结果并发时，live 路径只记录 `CANCELLED/TASK_CANCEL_REQUESTED`，不发布新 trial；原 OBSERVED journal 和搜索占位保留。未知响应、晚结果、已取消/过期后的市场观察后续仍需要受控对账，不能自动归零或重试。本批未声称闭合该门。

生成物化和发现发布统一以 epoch → task → run → attempt 的顺序获取写锁，避免与搜索占位/账本的反向等待。锁前身份读取只用于定位，锁后重新验证；不能以等待之前的缓存 Task 授权取消或 lease。单测观察实际执行的 SQLAlchemy 锁意图；不把 SQLite 忽略 FOR UPDATE 当作 PostgreSQL 并发证明。

## 4. 失败驱动验证记录

- 首先真实复现任意绑定 artifact 可完成发现阶段：1 项失败（`DID NOT RAISE`），修复后与发布用例共15项通过。
- 原子提交、结果冲突、过期、取消、失败市场计数、终态幂等、新 lease 恢复及篡改 trial 拒绝纳入专用测试。首个扩展跑次21通过/1失败，是新增 run 存在性检查提前改变既有无 run 诊断夹具的错误合同；恢复通用失败路径原校验次序，后24项通过。
- 新图 GENERATE 必须由服务器传入 VALIDATE_DISCOVERY；省略或改写 successor 被拒绝。
- 复核又发现新图 GENERATE 变成非终态后，“普通绑定工件 + 正确 successor”可绕过 typed generation；专用用例真实 DID NOT RAISE 后，worker 与 stage service 双层补拒绝。新图专用10项已通过，7 warnings、15.01秒、6 worker。
- 锁序用例真实失败：epoch 首次锁位置11、task位置0，证明生成入口与新发布入口顺序相反；统一 typed generation 和独立 materialize 入口后，相关38项通过、7 warnings、23.79秒，6 worker。该组不是完整后端回归。
- 根代理初步5文件检查与随后完整涉及25文件的 Ruff check、format check均通过。最终完整目录另行冻结并核对来源，不借用上批5,353绿灯。
- 新图 GENERATE 恢复对任意绑定工件的绕过也真实复现为 DID NOT RAISE；恢复现在要求同 owner/run/task/attempt/artifact 的 generation materialization 关联，正向 typed 恢复及拒绝用例随专用10项通过（15.36秒）。
- 失败 checkpoint 的崩溃窗口：FAILED/TIMED_OUT/CANCELLED 三参数初跑均被错误重排队为 QUEUED；修复后3项通过，worker/task/graph/migration/process 联合65项通过（44 warnings、23.28秒）。
- 部署/API 组39项通过（15 warnings、15.23秒）；三阶段测试仅替换两端 HTTP transport，真实业务服务与数据库记录未被替身替换。它不等于真实 Provider/TLS/runner 验收。
- 两端 HTTP seam 初跑关于 run 状态的失败经代码复核定位为测试读到 worker 前 session 的旧 ORM 对象；末尾重新查询 run 并保留 SUCCEEDED 断言，不修改生产状态语义。该诊断失败与后续绿灯分开登记。

严格 JSON 修复前的联合回归：`tests/test_ai_research_*.py`、config、iteration184 与 asset migration，共 **578通过、0失败/错误/跳过、60 warnings、72.65秒、6 worker、exit0**；其中 v2 557项。JUnit `/private/tmp/iter196-workflow-verify.6ZmW8l/workflow-targeted-20260906.xml`，SHA-256 `b2ed1f86125cf665932bbdc7c4a06f09685f5da2de2fc64ca8f64811e094c380`。跑前/后源码摘要均为 `fd21023df9ef1a0f7505b6fbee3917cfc2d87d43657581da463d14580973c452`，24个涉及Python文件 Ruff check/format check通过。该跑次不证明随后JSON修复后的源码；不能把578加到完整回归数量中。

### 独立复核 P2 处置

只读复核限定阶段提交、物化、发现发布和恢复，不替代全需求审计。除已知的失败恢复与 GENERATE 恢复 guard 外，未报告其他新的严重问题；提出1个P2：模型 JSON 默认解析允许重复键和非有限数。主代理核对 `_parse_draft` 与 `_mapping_copy` 后采纳：

- 5项真实RED：顶层重复strategy_code及嵌套重复params被接受；NaN/Infinity/-Infinity直到后续canonical层才拒绝，未在模型输出边界形成统一错误合同。
- 模型输出解析现在全层拒绝重复key、拒绝非JSON数字常量；mapping复制同样 `allow_nan=False`，不静默按最后一个重复值生成候选。
- 参数化用例绑定原模型文本hash，并核对拒绝后candidate、materialization、artifact/content和binding数量不增加。后续修复跑次和完整回归独立记录。

修复后 generation materialization、stage completion、generation HTTP pipeline、discovery deployment 共 **47通过、7 warnings、18.38秒、6 worker、exit0**。JUnit `/private/tmp/iter196-workflow-verify.6ZmW8l/workflow-strict-json-20260906.xml`，SHA-256 `bc09472f4af46bcb56023e61941b12b0a4fd3fd291bd5da4d4ae89dfbe5a5db6`；0失败/错误/跳过。完整后端回归另以最终源码摘要核对。

最终完整JUnit为5,529 cases、0 failure/error、129skip，其中562项v2全部通过；文件 `/private/tmp/iter196-workflow-verify.6ZmW8l/backend-full-6-workflow-20260906.xml`，SHA-256 `148f9dd1c395489e92c51992d60ed4bf77c01ac3f6cc41ffc4052a14bc20c2c7`。源码 `app/tests/scripts/alembic` Python排序摘要跑前/中/后均为 `90c2abbac31dc609cc99cfc7006a67894c6a8a71cd68c3402dd27aa5ac5c89f3`。所有定向、历史与完整跑次相互独立，不加总。

## 5. 实际 PostgreSQL 迁移证据

当前 migration `20260906_ai_research_workflow_version`，父版本 `20260906_ai_research_search_allocation`。一次性 PostgreSQL 17.7 的真实 Alembic 验证已执行：

1. 升到父版本并插入完整外键历史 run/execution，升级当前 head，旧 run 读回 generation-v1、字段非空/有数据库默认，历史 execution 仍为1；`alembic check` 无待生成操作。
2. 纯旧图降到父版本、重升当前 head；旧图身份与历史保留，再次 check 无待生成操作。
3. 临时历史 run 设置 discovery-v1 后尝试降级，得到 `RESEARCH_WORKFLOW_VERSION_DOWNGRADE_BLOCKED`；事务回滚后 head 与 discovery-v1 字段值、历史 execution 全保留，第三次 check 无待生成操作。

新图或未知版本存在时禁止 drop 版本列，避免重新升级时把新图冒充旧图。需要退役此类数据必须另行设计显式前向归档/转换，不能用本迁移无损回滚的说法代替。

- 验证脚本：`/private/tmp/iter196-workflow-verify.6ZmW8l/verify_workflow_migration.py`，SHA-256 `6c8a1ffa411ebc55fa5fb1ed779545a0c968da912b273be3d2582f9fb736a8c6`。脚本复用上一批保留的纯历史 seed helper；全部 DDL/DML 指向此次新建的临时集群，不读取应用 DATABASE_URL。
- 首次验证时 migration SHA-256：`f7e6a0c4f3c1f4f7f880398a9c7ce11d07aaaa64858610a6db1bf1bce4457a3c`。最终 Ruff 格式化后摘要为 `c54beaa0b71f9435fc79a58f514f88ff52516d24488fa5fe5c1e3f1830b35cec`；为保持最终来源一致，又在新临时数据库 `workflow_frozen` 上完整重做上述三个步骤与三次 check，全部通过、exit0。
- 最终冻结版验证器 `/private/tmp/iter196-workflow-verify.6ZmW8l/verify_frozen_workflow_migration.py`，SHA-256 `7d73c420e337d2c447250c05733623a723b0f4a54fc72f6cbceda2817a3613e3`；停止后的 PostgreSQL 日志 SHA-256 `ae9b7eaa9fa8c47efb1756c10a6322db428e81f31f17d1056074d2c158ce2e35`。不是对旧数据库重复插入或篡改旧证据。
- 临时 cluster `pgdata` 仅监听此目录 Unix socket，端口标识56498；验证终态 exit0。已 fast stop，root 读回 `pg_ctl status` 为 no server running（exit3）。保留本地脚本、数据和日志供复查，未改业务库或常驻服务。
- SQLite 迁移契约、完整源码冻结及 MySQL/运行中灰度/真实回滚分别核对，不能由上面的 PostgreSQL schema 证明代替。

## 6. 剩余本地开发与外部验收

整体验收继续 `NO-GO`，并非只有环境问题：

1. 显式 owner-scoped freeze API/界面与成功发布 checkpoint 门；不能由仅有 trial 自动冻结。家族存在未对账 UNKNOWN/晚到市场观察时不能绕过完整试验计数给统计绿灯，需与下一项恢复政策协调。
2. 所有搜索/模型入口的预算一致性，以及 UNKNOWN/晚结果/取消后市场观察的受控对账和完整统计计数。
3. 冻结候选 → 独立密封评估 → evidence package/gate → 人工审批 → 沙箱/前向观察的版本化部署连接与恢复。
4. 新图当前 authenticated UI/API 的实际进程演练、冷重放、真实对象权限及隔离证据。
5. 获授权真实数据/模型/runner、容器资源/no-network、跨服务/IAM、T2/T3 与灰度回滚验收。

上述1–4仍有可推进的本地实现/验证，不应把外部环境缺失当作整体停止理由；同时不擅自开启真实 Provider、部署服务或交易。
