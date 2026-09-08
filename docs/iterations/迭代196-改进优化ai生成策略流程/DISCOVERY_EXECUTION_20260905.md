# 冻结前发现验证：执行链补齐记录

日期：2026-09-05 起草，2026-09-06 更新。对应 J2/J3、S3b/S4、FR-PIPE、FR-TASK 和 AC-SBX。

> 本文保留首批合同/journal/派发服务及其 5,298 项完整回归历史。后续已实现有界 HTTP adapter、epoch 原子搜索占位、journal→trial ambient 发布，最新结果及剩余纵向工作以 [发现试验发布记录](DISCOVERY_PUBLICATION_20260906.md) 为准；不再把本文的历史“尚未实现”当作当前文件清单。

## 当前事实与实现顺序

上一批冻结候选完整后端为5,216通过、129跳过、601.36秒，原始证据见 [六 worker 回归](REGRESSION_6_WORKERS_20260905.md)。本批正在新增源码，不借用该历史完整回归作为新源码证明。

只读复核确认：`workflow_worker.py` 当前只推进 `CLARIFY → GENERATE → terminal`；生成物化只产生 `MATERIALIZED_NOT_EXECUTED` 候选。`CandidateRegistry.freeze` 要求已有成功市场试验，现有 `SandboxRunner` 又只接受 `FROZEN`，因此不能把现有 runner 直接接到首次探索验证。原需求 J2/J3 明确探索在前、显式冻结在后、一次性密封评估再后，不能删除冻结/密封保护来解除这项循环依赖。

实现按以下依赖推进，只有完整纵向链路才算首次发现验证交付：

1. 冻结前 `VALIDATE_DISCOVERY` 的不可变执行合同与有界远端 RPC；只允许发现集/迭代验证集，保留现有 frozen/sealed runner 合同。
2. 从当前 task/stage 和已持久化 generation materialization 派生候选，重验 owner、lease、候选/代码字节/数据对象与 capability；服务端选择执行政策和 sandbox-seconds 额度，先持久请求再一次性派发。
3. 独立 journal 先保存经过验证的远端结果；迟到结果仅取证，不因此获得 trial/阶段成功写入权。未知结果保留配额，不零记账、不重发。
4. 以当前 lease 下的同一事务导入受控结果工件、追加真实 `ResearchTrial` 并绑定 stage；成功、失败、取消、超时和已观察性能均不能丢失。缺任一关键回执不允许 freeze。
5. 为已绑定工作流增加发现验证阶段和部署组合根；公开 worker 链路通过后，再增加研究员显式 freeze 命令。不得自动冻结、自动审批，或用生成 JSON/代码编译成功冒充市场试验。

本批初始所有权：根代理负责服务端候选/数据/lease/配额派发、后续集成与文档；独立代理负责 wire 合同/持久 journal/迁移；另一代理负责 HTTP adapter。共享 ORM 由 journal 代理单独修改。候选工作树仍为 `codex/iteration-196-ai-research-trust`；不修改本机常驻服务或业务库。

## 合同与故障边界

- Command 使用 canonical JSON bytes 和 SHA-256，包含 task/run/stage/candidate、候选及环境/成本哈希、opaque code/dependency/dataset 身份、profile/evidence、严格执行政策和配额 fencing。无 URI、宿主路径、原始 lease token 或密钥；runner 必须在自身授权的受控输入存储中解析这些身份，普通 API 不负责取文件或执行代码。
- 此切片只预留 `sandbox_seconds/seconds` 一项资源，不能冒称已经覆盖 CPU/金额/所有入口的联合预算。配额 intent 不包含预留后才产生的 reservation ID/fence，避免 hash 循环；最终完整 command 另由 journal 封存。
- API/backend 不获得 Docker socket。首批只有注入的 `DiscoveryRemoteExecutor` 接口；后续 HTTP adapter 已落地并按合同拒绝环境代理、重试和重定向，见 [后续记录](DISCOVERY_PUBLICATION_20260906.md)。真实 TLS 和部署身份/输入存储隔离仍需环境验证。
- Result 必须精确绑定 command/operation/runner/image，区分已观察市场表现与未观察。只有代码预检、描述性 metadata 或生成文本不能形成成功市场 trial。
- 请求与响应 journal 是执行证据，不是策略有效、阶段成功、候选冻结或审批。quota、journal、trial、stage 的恢复顺序必须逐项验证，不能将本地 HTTP seam 说成独立 runner 已部署。

## 本批实际落地

1. `discovery_execution_contract.py` 封存请求/结果 canonical bytes，直接构造也执行验证。请求与嵌套 JSON 有界；结果只允许有限数值，不额外把收益限制为不低于 -100%（杠杆损失可能超出此范围）。失败后已经观察到一个收益点仍保留为真实观察；成功要求至少两个点，但这不是统计质量 PASS。
2. `discovery_sandbox.py` 从服务端唯一 generation materialization 派生可变候选，拒绝歧义关联、owner/run 漂移、候选哈希漂移、真实代码字节漂移及封闭分区。独立 runner 身份与 queue/storage/network isolation 必须同时成立，不能只看 `sandbox_runner=true`。
3. 数据对象重验证的成功/失败状态单独持久化；数据/profile I/O 之后重新读取 task/run/attempt 和数据库时间，取消或过期即拒绝。最终派发前重验证上限 10 秒，外部执行协程总上限 `wall_timeout_seconds + 60`；超时记录 UNKNOWN，不自动再次调用。
4. quota dispatch requirement 可显式指定严格的 `discovery-execution-intent-v1`，而现有模型调用的默认严格 schema 仍为 `model-budget-quote-v1`。清空快照不能退回 legacy NULL 兼容；claim 的数据库语句同时检查剩余 reservation lease 大于 `wall + 90`。新 `DatabaseUtcAfter` 使用数据库语句时间与绑定秒数，SQLite 已实际读回，PostgreSQL/MySQL SQL 编译不等于真实三库并发验收。
5. `ResearchDiscoveryExecution`、线性迁移和 journal 保存一个 attempt/receipt 的唯一完整 command。PREPARED/UNKNOWN 可以追加已验证的 OBSERVED 结果；已知结果在后续任务权限检查前落库，迟到/取消不抹掉证据。并发测试使用独立 SQLite/WAL 连接，验证 UNKNOWN 先落库后合法结果仍能更新为 OBSERVED。

以上首批服务未接到公开 worker 或 API。后续 ambient 发布服务已经能原子创建持久 `ResearchTrial` 与证据关联，但公开阶段完成、工作流和显式冻结链路仍未接通。正向测试注入的远端响应是本地基础设施测试输入，不是真实回测绩效或独立 runner 部署证据。

## 失败、复核与验证记录

| 验证 | 实际观察与处置 |
| --- | --- |
| 合同修正 | 两项业务 RED：有限杠杆损失/大收益被拒绝、失败后的单个已观察收益被丢弃；修正结果域，保留成功形状限制 |
| runner 隔离 | shared identity / storage / network / queue 四项 RED，补充独立身份及隔离证据检查 |
| generation 关联 | 多 materialization 歧义、关联 user/run 漂移三项 RED，改为唯一且精确绑定，不挑第一条 |
| quota / 数据 / 超时 | 四项 RED：NULL context 仍派发、剩余 1 秒仍派发、FAILED 数据状态回滚、协程无总截止；已分别修复 |
| 数据复核后的任务权限 | lease 过期与取消两项 RED：返回前只检查先前的 ORM 状态，仍发生一次调用；改为 I/O 后重新读取和验证，断言零调用 |
| journal 并发疑点 | 实际双连接 UNKNOWN→OBSERVED 测试直接 PASS，推测的 SQLite 写丢失未成立；保留行为验证，没有为此改写 journal |
| 修复中的接线错误 | 提取上下文检查后遗漏 `attempt` 局部变量，组合诊断出现 8 failed/33 passed；改用已核验 context 的 attempt ID，不能计为业务 RED 或正式通过 |
| 首次统一 v2/配置/迁移 | `1 failed, 476 passed, 42 warnings, 62.80s`；固定在 `2026-09-05 16:05 UTC` 到期的正向测试租约在跨日后失效，改为用数据库当前时间创建夹具，不改生产租约规则 |
| 夹具修复后定向 | deterministic executor + discovery service + database lease clock 共 `44 passed, 7 warnings, 15.66s`，6 worker |
| 本批静态检查 | 16 个涉及源码/测试/迁移文件 Ruff check 与 format check 通过 |

初始模块缺失的 collection error 只是接口尚不存在，不充当业务行为 RED。统一失败跑次保留 `/private/tmp/iter196-current-head.WAaH1k/v2-discovery-dispatch-final-20260906.xml`；虽然文件名含 final，该跑次明确为 FAIL。失败跑前/跑后后端 Python 源摘要同为 `6a75e6c0569e02476141df52df59dbe0f1bea26ac8738d96306829e89fec6963`。

夹具修复后的完整 `tests` 六 worker 回归已完成：**5,298 passed、129 skipped、174 warnings，501.53秒，exit 0**。JUnit 实际5,427项、0 failure/error，其中461项 v2全过且无跳过。运行前/中/后源码摘要均为 `8144c0f93620f4ad73985b71ad277ac598051e5955939709f3c22c08104a71c6`；完整 XML SHA-256 为 `2553f51297c385e96fa7ba4b13b367291c5103699972bf0409064297d60c3c75`。命令、失败历史和不加总原则见 [六 worker 记录](REGRESSION_6_WORKERS_20260905.md)。新迁移在一次性 SQLite/PostgreSQL17.7 的真实空表 schema 升降级已验证，临时 PG 已停止；不等于在途 journal 无损回退，见 [迁移记录](CURRENT_HEAD_MIGRATION_20260905.md)。

## 剩余实施门与环境

以下仍是本地开发任务，不是只等外部环境即可完成：

- 有界 HTTPS adapter 已补齐；独立 runner 的真实输入取用、结果回执和部署隔离仍须验收。
- 派发前 epoch 搜索预算原子占位已实现；其他入口的全搜索空间预算与未知试验对账仍需闭合。
- journal→受控结果工件→trial 的当前租约 ambient 提交已实现；仍需接入 stage 同事务及崩溃恢复，保留未知、失败、取消和迟到证据及相应搜索计数。
- 服务端持久的版本化执行图、新旧排队任务兼容与部署组合根；不静默改变旧 `CLARIFY→GENERATE→terminal` 语义。
- 显式 freeze API/owner/hash 验证，再接独立 sealed evaluation、门禁和人工审批，不能自动冻结或批准。

本轮只读 `docker info` 在10秒上限内返回无法连接本机 daemon，未启动 VM/容器或拉取镜像。真实 AC-SBX 隔离验证仍缺环境；不会退回宿主执行 AI 代码。其余可实现工作继续推进，整体目标与 G0～G5/T2/T3 验收范围不变。
