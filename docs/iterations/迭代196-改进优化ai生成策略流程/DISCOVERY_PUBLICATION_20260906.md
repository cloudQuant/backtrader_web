# 首次发现验证：HTTP、搜索占位与试验发布

日期：2026-09-06。候选工作树仍为 `.worktrees/codex/iteration-196-ai-research-trust`，本记录是 [发现执行链](DISCOVERY_EXECUTION_20260905.md) 的后续实施证据。需求范围保持不变，整体验收仍为 **NO-GO**。

> 后续增量：持久化新旧图与 trial/stage 原子完成见 [版本化发现工作流](DISCOVERY_WORKFLOW_20260906.md)。本文的5,353完整回归及“尚未接线”结论仅对应本批历史源码，不作为新图的最新验收结论。

## 本批实现边界

- `HttpDiscoverySandboxExecutor`：只访问部署配置的 HTTPS `/v1/discovery-executions`。发送封存的 canonical command bytes，使用 operation ID 和 command hash；验证 TLS、不继承环境代理、不重试、不跟随重定向。响应只接受 200 JSON 和 identity encoding，同时限制响应头声明大小、实际读取大小和整体超时；拒绝重复 JSON key、非有限数字及错绑结果。测试使用 HTTPX 网络边界替身，不是实际 TLS、IAM 或远端沙箱证明。
- `DiscoveryExecutionJournal.prepare`：同一事务中锁定 owner epoch、核验当前任务和候选、占用搜索名额、保存唯一命令。名额写在 journal 的 `search_epoch_id/search_ordinal/search_budget_hash` 中，不再建立一套重复占位账。两个不同 run 只剩一个名额时只能成功一个；原命令精确重读不加次数。
- 预算计数覆盖该 epoch 的所有已提交执行，以及未被 journal 明确关联的历史 trial。PREPARED、UNKNOWN、失败执行仍占位；不能靠重试标签或 idempotency key 前缀豁免。已关联 trial 不重复收费。预算快照改变后拒绝继续使用旧 family；本切片不是所有入口的参数/资产/金额预算总闸。
- 迁移保留旧 journal 的 NULL 分配字段，不伪造历史占位。历史行仍可接收迟到结果，但不能走 prepare 幂等路径重新获得派发权；需要独立的恢复/核对政策。
- `DiscoveryTrialMaterializer.publish_in_session`：从持久 journal 重建并核验 command/result，检查 owner、run/task/attempt、有效 lease、取消状态、搜索占位、quota intent/fence/settled amount、候选和数据身份、真实代码字节。随后把结果 JSON 字节、工件、stage binding、append-only trial 及 journal→trial 关联放进调用者的同一事务。不自行 commit、不调用 runner、不改变 candidate freeze 或 stage status。
- 已观察行情的失败结果仍计入市场试验；尚未观察行情的失败留下 trial，但不计市场试验。保留完整有序收益，不凭空生成 Sharpe、成本、DSR 或统计有效性。结果与命令绑定不等于策略有效。
- `ExperimentLedger.record_trial_in_session` 与 `ArtifactBroker.register_stage_output_in_session` 保留既有独立提交 API 的兼容调用；新接口仅 flush，由外层决定整体提交或回滚。

## 复核与失败处置

| 项目 | 观察与处置 |
| --- | --- |
| 搜索预算初始业务 RED | 8 项失败：非法预算、耗尽、跨 run 最后名额竞争、预算漂移及历史 trial 均未被拦截；新增原子分配后通过 |
| epoch 绑定 TOCTOU | 独立审查指出先读旧 epoch、再锁到新 run/candidate 的风险；插桩测试确实未拒绝。传入锁定 epoch ID，并在 run 锁下再次核对，不允许计入错误家族 |
| 历史 NULL prepare replay | 单项业务 RED：旧 journal 可以由幂等返回继续派发；现在要求真实分配字段，历史证据不升级为新授权 |
| 发布接口初始 RED | 已有服务成功得到 durable result 后，新的 publish 接口尚未实现；8 项 NotImplementedError，随后实现真实事务写入 |
| 发布接线诊断失败 | 3 项失败源于误用 `DatasetRegistry` ambient API 参数，改为实际 `snapshot` 接口；这不是业务规则 RED，不隐藏该失败 |
| 原子性与计数 | 成功、失败且观察行情、未观察行情、过期/取消/配额/身份/内容漂移、幂等与 rollback 已分别覆盖 |
| 锁序复核 | 两项实际 SQLAlchemy row-lock 顺序 RED；新 discovery 路径改为 epoch→task→run→attempt，保持既有 broker 顺序。freeze 改为无锁读 epoch ID→epoch 锁→candidate 锁并重验绑定；成功市场 trial 的冻结前提不变。SQLite 执行时观察的是 SQLAlchemy FOR UPDATE 意图，不冒称 SQLite 实际支持行锁 |

此前统一定向结果为 **119 passed、34 warnings、27.55 秒、6 worker**，包含 HTTP、发现服务/journal、搜索预算、发布、ledger/broker 及迁移测试。此结果早于后续锁序修正，不作为最终候选全量证明。JUnit：`/private/tmp/iter196-current-head.WAaH1k/discovery-publication-targeted-20260906.xml`，SHA-256 `cebdeb280996541a70d7b2ed397063059ee9fefe4e6deac28d6b9c07f5338120`。最终冻结后的结果单列如下，不拼接历史跑次。

锁序修正后四个相关文件的定向结果为 **45 passed、7 warnings、17.31 秒、6 worker**。JUnit：`/private/tmp/iter196-current-head.WAaH1k/discovery-lock-order-targeted-20260906.xml`，SHA-256 `f2bed78a79cae132686467b707781de4c95690c4e0aff7ac8c303a4ea920e84e`。初次锁序观测测试误用默认 SQL 编译器，无法编译 `DatabaseUtcNow`；改为读取 ORM column descriptions 后，真实顺序 RED 才得到确认。此夹具诊断不计为生产功能失败。15 个涉及源码/迁移/测试文件的 Ruff check 和 format check 均通过。

## 当前冻结候选完整验证

**完整后端5,353 passed、129 skipped、174 warnings、539.40秒、6 worker、exit 0**；同份JUnit实际5,482项，0 failure/error，v2子集516项全过且无跳过。运行前/中/后Python源码摘要一致：`a95c7e1726c92bcd6afb3541db884e2422e24da17fdea4939298e233de5e7fb9`。XML SHA-256 `7eebd693add115988a6c803d180151e16d05cef9a9d918c2879d97e5f53f919e`，完整命令和路径见 [六进程回归记录](REGRESSION_6_WORKERS_20260905.md)。本批不重跑未修改的前端，不将先前前端证据冒称新验证。

在Unix-socket-only PostgreSQL17.7的全新 `iter196_lock_order_final` 临时库中，独立验证器用两个真实session调用 `ArtifactBroker.register_stage_output_in_session` 和发布路径的 `lock_search_epoch → _live_context`。broker持task锁时暂停，publication请求task但250ms内未请求run；释放后两方完成，stage binding为1。它证明已消除这对反向等待环，**不是完整publish事务的PG端到端测试，也不是全系统无死锁证明**。

脚本 `/private/tmp/iter196-search-allocation-verify.Ds27JZ/check_publication_broker_lock_order.py`，SHA-256 `76120e8c4e4d9e81db5a77e674d36c221a6c06669bdc6bae9bbd227d28b32860`。验证器先前两次诊断分别是误用Base.metadata触发legacy boolean建表差异、rollback后访问已过期ORM属性触发MissingGreenlet；改为正式Alembic建表及rollback前保存标识后，在新临时库完整通过，没有为此更改候选源码。PG最终fast stop，主代理再次单独执行 `pg_ctl status` 返回exit3/no server running。

当前head为 `20260906_ai_research_search_allocation`；SQLite/PG含历史journal的实际升级、分配写入、降级及重升通过，见 [迁移验收](CURRENT_HEAD_MIGRATION_20260905.md)。分配元数据降级会丢失，不能恢复派发后再假定预算仍有余额。

## 仍须完成的纵向链路

1. 在服务端为 run 绑定版本化工作流图，兼容已排队的 `CLARIFY → GENERATE → terminal`，新图才进入 `VALIDATE_DISCOVERY`；不得由模型或用户提交 next_stage 覆盖图。
2. GENERATE typed proposal 支持服务器选定的非终态；DiscoveryStageExecutor 调用发现服务，并由 stage completion 把发布与 checkpoint/event 同事务提交。不得将 HTTP adapter 直接当作阶段执行器。
3. 部署组合根提供真实三阶段 executor map、runner 配置、受控输入解析和沙箱镜像；重做真实候选 UI/API、恢复、取消、延迟结果和搜索耗尽验收。
4. 增加研究员显式 freeze 的公开命令，检查完整已发布执行及成功 checkpoint。当前底层 `CandidateRegistry.freeze` 的成功 trial 前提不得删除，也不能自动冻结。
5. 对 UNKNOWN / 已观察但迟到未发布的结果建立受控 reconciliation；在统计 gate 前完整结清试验账，不把缺失结果记作零或技术豁免。接入独立密封评估、审批和后续既定验收，不能用此切片缩减迭代范围。

本批没有修改常驻服务、业务库、真实凭据或主工作树业务代码，没有运行真实付费 provider/runner，也没有提交、推送或部署。

最终文档检查：本迭代27个Markdown、220个本地链接，0缺失；主工作树与隔离工作树 `git diff --check` 通过。候选的 tracked diff 仍为37个文件、1,074增/68删；大量v2源文件和本迭代文档尚未跟踪，该统计不代表完整交付清单。未改动他人的迭代197及总目录既有变更。
