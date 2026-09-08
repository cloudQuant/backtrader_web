# 迭代 196 六进程回归与并发问题处置

日期：2026-09-05。工作树：`/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`。

> 历史快照提示（2026-09-07）：本文保留 2026-09-05～06 的实际失败、修复和冻结跑次，正文中的“最新”仅相对于该历史时间线。当前候选的互斥功能/性能通道、固定依赖、沙箱 ready 协议及最终来源摘要见 [2026-09-07 六 worker 分层回归](REGRESSION_6_WORKERS_20260907.md)；不得用本文旧数字覆盖后续源码。

> 2026-09-06 冻结候选：**完整后端5,400 passed、129 skipped、184 warnings，502.81秒（约8分23秒），6 worker，exit 0**；562项 v2 全过且无跳过，源码跑前/中/后摘要一致。版本化发现工作流、原子阶段提交、恢复与严格JSON的交付边界见 [本批记录](DISCOVERY_WORKFLOW_20260906.md)。整体及生产启用仍为 NO-GO。

> 历史预算切片完整后端：**5,216 passed、129 skipped、174 warnings，601.36 秒（10 分 1 秒），6 worker，exit 0**；379项 v2全部通过且无跳过。预算首轮失败/中断及两个测试隔离修复分别保留，不拼接历史结果。

## 最新：版本化发现工作流与原子阶段完成（2026-09-06）

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q --tb=short -n 6 --dist load --maxschedchunk=8 \
  --durations=15 \
  --junitxml=/private/tmp/iter196-workflow-verify.6ZmW8l/backend-full-6-workflow-20260906.xml \
  tests
```

终态 **5,400 passed、129 skipped、184 warnings，502.81秒，exit0**。同份JUnit实际 **5,529 cases、0 failure/error、129 skipped**；v2子集 **562项、0 failure/error/skip**。没有ignore或失败自动重试，不与任何定向/历史跑次加总。

- XML SHA-256：`148f9dd1c395489e92c51992d60ed4bf77c01ac3f6cc41ffc4052a14bc20c2c7`。
- `app/tests/scripts/alembic` 全部Python（包括未跟踪文件）排序摘要，跑前、运行中及结束后均为 `90c2abbac31dc609cc99cfc7006a67894c6a8a71cd68c3402dd27aa5ac5c89f3`；回归期间未改源码。
- 严格JSON修复前578项联合通过属于 `fd21023d...` 历史快照；修复后47项和本次完整目录均另存。任意工件、生成恢复、反向锁序、失败checkpoint重排队及重复JSON键的真实RED和处置见 [工作流记录](DISCOVERY_WORKFLOW_20260906.md)，未用旧绿灯覆盖新源码。
- 最终25个涉及Python文件 Ruff check/format check通过；当前SQLite契约与最终格式化migration的真实PG升级/安全降级拒绝分开登记。临时PG已停止。
- 最慢单项为legacy research loop 13.54秒。六worker是测试进程并行调度，不是CPU affinity，也不构成固定6倍加速的受控基准。129项skip仍保留原条件，不能当成对应场景通过。
- 本批未改前端、未重新跑前端；147文件/1,315项及typecheck/build只保留历史证据。两端HTTP替身的三阶段链不等于真实Provider/runner、容器/IAM或当前真实浏览器验收。
- `git diff --stat` 的候选跟踪文件为37个、1,231新增/69删除，包含前序迭代工作；大部分v2源码/测试/迁移及主工作树迭代文档仍未跟踪，因此该stat不是全部交付清单。未commit/push/部署，主工作树无关README及迭代197保留。

已接通本地生成→发现验证，但显式freeze、完整搜索/未知结果对账、独立密封评估/审批部署链及T2/T3仍有工作；完整目录PASS不提升整体验收或生产启用。

## 历史：发现 HTTP、搜索占位与 trial 发布（2026-09-06）

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q --tb=short -n 6 --dist load --maxschedchunk=8 \
  --durations=15 \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/backend-full-6-discovery-publication-20260906.xml \
  tests
```

终态 **5,353 passed、129 skipped、174 warnings，539.40秒，exit 0**。同份 JUnit 实际 **5,482 cases、0 failure/error、129 skipped**；其中 `test_ai_research_` 子集 **516项、0 failure/error、0 skip**，不与定向或历史结果加总。没有 ignore、失败自动重试或生产数据/远端调用。

- XML SHA-256：`7eebd693add115988a6c803d180151e16d05cef9a9d918c2879d97e5f53f919e`。
- 后端 `app/tests/scripts/alembic` 所有 Python 文件（包括未跟踪文件）排序 SHA 摘要，在完整跑前、运行中和结束后均为 `a95c7e1726c92bcd6afb3541db884e2422e24da17fdea4939298e233de5e7fb9`。
- 本批 HTTP adapter27项、搜索预算11项、trial发布14项、ledger新增3项，共新增55项，均包含在上述完整目录中；不能把它们再加到5,353上。
- 锁序修正前119项定向、修正后45项定向、实际 SQLite/PG 迁移与双会话锁序证明单列在 [发现发布记录](DISCOVERY_PUBLICATION_20260906.md)；15个涉及文件 Ruff check/format check通过。
- 最慢单项为 legacy research loop 的14.22秒。相邻完整跑次耗时不同，不能据此宣称固定6倍加速；六worker是并行调度，不是CPU affinity或性能基准。129项跳过仍未获对应环境验收。
- 前端本批无修改、未重跑；先前147文件/1,315项、typecheck/build均为历史证据，不标为本轮重新验证。

本批只完成本地发现执行基础链与试验发布。**版本化公开工作流、journal→trial→stage同事务、显式freeze、真实runner和完整研究闭环仍有开发/验收工作**，整体验收保持NO-GO。

## 历史：发现执行记录与派发增量（2026-09-06）

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load --maxschedchunk=8 \
  --durations=20 --tb=short \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/backend-full-6-discovery-dispatch-20260906.xml \
  tests
```

终态 **5,298 passed、129 skipped、174 warnings，501.53秒，exit 0**。实际解析 JUnit 为 **5,427 cases、0 failure/error、129 skipped**；从同份 XML 筛出的 `test_ai_research_` 子集为 **461项全过、0 skip**，不与任何聚焦或历史跑次加总。

- XML SHA-256：`2553f51297c385e96fa7ba4b13b367291c5103699972bf0409064297d60c3c75`。
- `app/tests/scripts/alembic` Python 源文件按本文方法计算，运行前、中、后均为 `8144c0f93620f4ad73985b71ad277ac598051e5955939709f3c22c08104a71c6`。包括未跟踪 Python，不包括依赖/镜像/部署配置；base HEAD 仍不是包含未提交工作的交付提交。
- 本批16文件 Ruff check 与 format check 通过；SQLite/PostgreSQL discovery migration 实际 upgrade/check、parent downgrade、reupgrade/check 另见 [迁移记录](CURRENT_HEAD_MIGRATION_20260905.md)。本批未改前端，前端既有1,315项仅保留为历史证据，未重复运行。
- 最慢两项为 monitoring 用例60.01/30.01秒；legacy research-loop 最慢14.17秒。相较上一批601.36秒有所缩短，但源码、用例数及机器负载不同，不构成受控速度 A/B，更不承诺6倍加速。xdist 会禁用 benchmark 测量，本跑次仅作功能回归。

此前统一 v2/配置/迁移跑次 **1 failed、476 passed、42 warnings，62.80秒**：`test_clarify_executor_writes_a_bound_no_model_receipt` 的正向夹具固定租约在 `2026-09-05 16:05 UTC` 到期，跨午夜后被正确拒绝。修复只把夹具租约改为数据库当前时间加5分钟，未弱化生产 lease 校验。先完成44项定向，再运行上述完整目录；该用例在同份完整 XML 中耗时0.846秒、无失败。

失败 XML `/private/tmp/iter196-current-head.WAaH1k/v2-discovery-dispatch-final-20260906.xml` 虽含 final 文件名，仍登记 FAIL：477 cases、1 failure、0 error/skip，其中461项 v2；SHA-256 `69509bd000f4dc5d91e0564ac62482f8afde713ccaaacfdaa9d193889c904ffd`。失败跑前/后源码摘要均为 `6a75e6c0569e02476141df52df59dbe0f1bea26ac8738d96306829e89fec6963`，不覆盖修复后的源码。

本批新增 wire contract、journal/迁移、候选/数据/隔离校验、严格派发 context 与租约余量、超时/晚结果证据。**HTTP adapter、epoch 原子搜索占位、journal→trial→stage 原子提交、版本化 worker 图及显式 freeze 仍未接通**；不能将本地注入 runner 的结果视为实际回测或独立部署。完整目录 PASS 不提升 `IMPLEMENTATION_ACCEPTED`、T2/T3 或生产启用结论。

## 执行策略

后端使用用户 Anaconda base 环境，pytest-xdist 固定 `-n 6`。最初按文件分配（`--dist loadfile`）以减轻进程发现测试之间的干扰；JUnit 随后显示 `test_ai_strategy_research_service.py` 独占一个 worker、累计 469.81 秒，形成长尾。脚本测试完成局部隔离后，最终改用 `--dist load` 按用例动态分配，使慢文件也能分摊到六个 worker。这里的“6 核”表示六个 pytest worker，并非操作系统 CPU affinity 限制。

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load --durations=15 \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/backend-full-6-load.xml tests
```

`--no-capture-output` 让 conda 实时转发 pytest 进度；`-p no:rerunfailures` 保留此前命令的插件配置；本轮不靠自动重试隐藏失败。xdist 会自动禁用 benchmark 测量，因此这些结果是功能回归，不是性能基准。

## 已确认结果

**跑次时序说明**：下表 4,993 项完整后端跑次早于随后新增的外部单次派发、模型配额结算与 filesystem resolver 接线；它保留为独立历史全量证据。最新冻结源码已另跑完整目录：5,034 passed、129 skipped、174 warnings，494.05 秒；详情见本文末尾，不以历史与聚焦跑次拼接代替。

| 检查 | 结果 |
| --- | --- |
| 数据集严格重验证与审批接线聚焦组 | 30 passed、7 warnings，19.01 秒 |
| 严格重验证后 v2 全组（心跳夹具修复前） | 155 passed、23 warnings，36.05 秒；后续完整回归暴露心跳夹具问题，不能仅靠该绿灯签署完整回归 |
| 心跳夹具修复后 workflow + task runner | 19 passed、7 warnings，15.21 秒 |
| 端口/进程脚本两个完整文件，`-n 6 --dist loadfile` | 9 passed、7 warnings，30.18 秒 |
| 当前 v2 源码/相关测试静态检查 | Ruff check 通过；83 files already formatted |
| 最新 head 数据库演练 | SQLite、PostgreSQL 17.7 的 upgrade/check、downgrade/reupgrade/check 均通过，见 [当前迁移验收](CURRENT_HEAD_MIGRATION_20260905.md) |
| 隔离修复前完整后端目录，`--dist loadfile` | FAIL：1 failed、4,991 passed、129 skipped、174 warnings，544.64 秒（9 分 4 秒）；`backend-full.xml` 共 5,121 项，无 collection error |
| 上述完整回归内的 v2 子集 | 155 项，0 failure/error、0 skip；从同轮 `backend-full.xml` 按 `test_ai_research_` classname 逐项解析，不是历史跑次拼接 |
| 脚本测试隔离后两个文件，`--dist loadfile` | 9 passed、7 warnings，19.43 秒；生产脚本、5 秒截止时间和业务断言均未改 |
| 脚本隔离与本地 CLI 导入修复后四文件，`--dist load` | 117 passed、7 warnings，30.29 秒；含脚本/端口测试、worker CLI 和 AkShare 脚本导入契约 |
| 本轮改动静态检查 | `scripts/__init__.py`、`test_ai_research_worker_process.py`、`test_ensure_dual_stress_running_script.py`：Ruff check 通过，3 files already formatted |
| 修复后完整后端目录，`--dist load`（无 ignore） | PASS：4,993 passed、129 skipped、174 warnings，536.50 秒（8 分 56 秒），退出码 0；JUnit 共 5,122 项、0 failure/error |
| 最新完整回归内 v2 子集 | 156 项、0 failure/error、0 skip；新增 1 项 CLI 来源断言使该子集由 155 增至 156 |

## 失败与根因

1. 严格重验证补丁后的首轮可执行主集为 `1 failed, 4982 passed, 129 skipped, 174 warnings in 599.47s`。唯一失败为 `test_worker_heartbeats_a_live_lease_until_stage_execution_finishes`。预期为受控的 `RESEARCH_GENERATION_CONTRACT_UNAVAILABLE`，实际收到 `RESEARCH_STAGE_EXECUTOR_FAILED`。
2. 独立审计保留 `-n 6` 重跑该测试，另一次复现了 `UNIQUE(task_id, sequence_no)` 冲突。测试全局夹具采用内存 SQLite + StaticPool，多个 AsyncSession 借用同一物理连接；心跳事务的 commit/rollback 能干扰阶段输出/事件分配事务，因此它不能作为独立事务并发正确性的依据。
3. 对照诊断脚本 `/private/tmp/iter196_workflow_staticpool_compare.py` 使用同构工作流。StaticPool 路径出现表不可见等连接生命周期失真；临时文件 SQLite + NullPool 路径连续 250 次得到预期终态，6 条事件序号始终为 1～6，无 ArtifactBroker 原始异常。额外观测的 heartbeat false 发生在任务已终态且 lease 已清空之后，不足以证明执行期间租约失效。
4. 最小修复仅改变心跳测试：采用局部 file-backed SQLite + NullPool，让会话拥有独立事务；等待实际成功 heartbeat 的事件再释放阻塞执行器；最终检查 6 条事件的类型和连续序号。生产原子事件分配器未因测试夹具问题改写。局部 session factory 在 fixture 结束时恢复，worker 已完成后再 dispose 引擎。
5. 主任务取得新的本地执行权限后，端口绑定已实际通过。两个此前排除的脚本文件在默认按用例调度下出现一次 5 秒超时，同时输出了其他用例的假 supervisor；改为按文件分配后 9 项全部通过。未修改产品脚本或放宽其断言。旧子代理仍受限的结果只属于该子代理环境，不再代表主任务当前权限。

## 验收范围

首轮完整目录命令退出码为 1，唯一失败为 `tests/test_ensure_dual_stress_running_script.py::test_status_discovers_running_monitor_without_pid_file`：`status` 在打印 supervisor 状态后超过测试固定的 5 秒截止时间。macOS 路径会多轮逐 PID 启动 `ps`，成本受全机进程规模影响，测试也未隔离默认 split/monitor PID 路径。现以 `_script_env` 为全部八个脚本用例隔离 PID/log 路径；Darwin 临时 PATH shim 只替换精确的 `ps -axo pid=` 枚举输入，包含本用例 fake 进程和无关的真实 pytest PID；其余 `ps -p` 存活/命令行检查均委托真实 ps。Linux 继续走 `/proc`，未将该 Darwin 局部隔离宣称为跨平台全机发现性能证明。

中途按文件分配的重跑由任务主动发送 SIGINT 停止，以切换到更均衡的调度；其结果为 621 passed、76 skipped、2 collection errors，72.73 秒，证据为 `backend-full-isolated.xml`，不能计入正式全量验收。其中还暴露了本地 `scripts/` 无 `__init__.py` 而被 Anaconda 已安装的同名 regular package 遮蔽的问题，独立解释器实际返回了 site-packages 下的 `scripts.__file__`。已新增本地 package marker，并增加 worker CLI 绝对来源断言；两个原失败的 CLI 导入和 117 项聚焦回归现已通过。未卸载或修改环境中的第三方包。

修复后新的完整跑次已通过，其证据独立于历史 4,977 项绿灯、两文件受限记录和局部 9/117 项检查。独立只读复核确认脚本夹具仍验证真实存活、命令行和 PID 回写，CLI marker 只修复 source-tree/test 导入优先级（当前 wheel 只打包 app*，未宣称扩展 wheel 公共 API）。

最新 JUnit：`/private/tmp/iter196-current-head.WAaH1k/backend-full-6-load.xml`，SHA-256：`8c09f5442aaac726905c0d598783e7ea6c58d7a198a4db54cdd8ac6cac270657`。基底 HEAD 为 `a18bcf52682686c30d919fe02d6fd734ee4271b9`，验收对象是其上未提交的候选工作树，不是该基底提交本身。

6 worker 只规定并行度，不构成 6 倍加速承诺。本机两轮完整跑次分别为 544.64 与 536.50 秒，代码/夹具与调度均有变化，因此不能当成受控性能 A/B。最新最慢单项为 legacy 研究完整流水线 11.51 秒；后续若继续优化调度，可单独评估 `--maxschedchunk`，本次未将未跑过的参数写成已验证命令。真实对象存储/Provider、生成到独立评估及审批的部署闭环、真实前向观察和生产启用仍按 [ACCEPTANCE.md](ACCEPTANCE.md) 分别验收，129 项跳过也不意味着对应场景已通过。

## 前端六 worker 最新回归

最新历史分页、run/task/candidate 直链恢复、双流轮询和请求所有权修复已由主代理重新验证：

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/frontend
npm run test -- --run --minWorkers=6 --maxWorkers=6 \
  --reporter=basic --reporter=json \
  --outputFile.json=/private/tmp/iter196-current-head.WAaH1k/frontend-full-6.json
```

结果：**147 files、1,315 tests passed，33.57 秒，退出码 0**。JSON SHA-256：`78e3d24a23d56a54d977c497607641533d7d8c2eb1fa94f34d4437e509deee88`。`npm run typecheck` 和 `npm run build` 也已重跑通过，构建耗时 40.23 秒；保留既有 Browserslist/大 chunk 提示。

Vitest 1.6.0 在本机应同时指定 min/max 为 6，单设 max 会与机器默认最小线程数冲突。首个完整跑次还暴露了测试生命周期问题：旧 `StrategyPage.test.ts` 在 tab stub 中挂载真实 `TrustedResearchWorkbench`，大量 wrapper 未销毁，造成历史列表定时轮询累积、测试不退出。该跑次由主代理 SIGINT 停止（exit 130），不能算通过。最小修复只在父页单测中 stub 独立工作台，并保留 AI 投研路由挂载该组件的断言；没有删除测试文件、延长 timeout 或关闭生产轮询。父页 98 项先通过，再执行上述全部 147 文件；子组件/composable 的 42 项真实独立测试仍覆盖分页、请求 A/B 隔离、candidate 绑定与退出清理。

这些结果是单测/类型/构建证据。真实 authenticated UI/API 演练与屏幕阅读器人工检查仍不能由它们替代。

## 本批冻结源码的完整后端结果

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load --maxschedchunk=8 \
  --durations=20 \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/backend-full-6-chunk8.xml tests
```

**终态：5,034 passed、129 skipped、174 warnings，494.05 秒（8 分 14 秒），退出码 0。** JUnit 共 5,163 项，0 failure/error；197 项 `test_ai_research_` 用例全部通过、无跳过，覆盖本批派发/结算及文件 resolver 增量。

原始 JUnit SHA-256：`1f3c3ed3d5b35cd8f20d43ac4b57f989385423326d6f9d4c1a9e337bc070f9f3`。启动前、运行中及结束后的后端 Python 来源清单摘要完全一致：`19009eb105e09890c79d0c59b2ba4cdff57fae04d70840cf161583d2908bcdd8`；计算范围为 `app/tests/scripts/alembic` 中 `rg --files -g '*.py'`，排序后逐文件 SHA-256，再对清单 SHA-256。该摘要只证明这些源文件未在跑次中变动，不是依赖镜像、Git 提交或部署产物的完整来源签章。

本次实际验证了 `--maxschedchunk=8`，最慢单项为 legacy research-loop 14.00 秒。总时长比先前 536.50 秒少 42.45 秒，但两轮代码/用例数和机器负载不同，不能声称这是该参数的受控加速比，更不是 6 倍加速。后续功能回归可沿用本命令；性能结论另做同源码、同环境 A/B。

仍保留 129 项的原有跳过条件。该跑次之后已修复独立复核发现的 ProviderResponse 非 Mapping 账本缺口，并完成 52 项 gateway/materialization 联合聚焦，见 [响应验证记录](PROVIDER_RESPONSE_VALIDATION_20260905.md)；时钟与生成接线另行验证，详见 [派发安全记录](DISPATCH_SAFETY_20260905.md)。本轮全量 PASS 是其冻结源码的回归结果，不是后续源码、实现完整性、真实 Provider/存储、隔离执行或生产启用 PASS。

## 响应、时钟与生成执行器增量的统一回归

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load --maxschedchunk=8 \
  tests/test_ai_research_*.py --tb=short \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/v2-response-clock-generation.xml
```

终态：**241 passed、23 warnings，38.76 秒，退出码 0**。实际解析 JUnit：241 cases、0 errors、0 failures、0 skipped。XML SHA-256：`d328850209d6a8e4b2e2f01affe594107fb7f15eb5fc909dee47944bf930557d`。8 个本批源码/测试文件 Ruff check 与 format --check 通过。

跑前/跑后 `app/tests/scripts/alembic` Python 清单摘要均为 `4ba9b538c0482f5b24a14f58022c209207e93c9bffde1f153b86748c48963d21`，使用上文同样排序/逐文件 hash 方法；不把基底 HEAD 当作包含未提交文件的候选提交。本次测试源在统一跑次中没有变动。

这是 v2 完整匹配子集，**不是全后端目录回归**。本批未改 legacy/front-end 代码，因此先验证新增 v2 及其所有匹配回归文件，避免每个微小补丁都重复全仓慢跑；后续部署组合根、真实 adapter 或共享 legacy 依赖改动完成后，仍需按前述完整 `tests` 命令重新验收。不能把本次 241 项与历史 5,034 项加总为“当前 5,275 项通过”。

证据落点：[响应形状/脱敏与错误账本](PROVIDER_RESPONSE_VALIDATION_20260905.md)、[quota/task 数据库时钟与心跳边界](DISPATCH_SAFETY_20260905.md)、[生成执行器及接线缺口](GENERATION_EXECUTOR_20260905.md)。前向分区拒绝不等于实际前向观察验收；Provider seam 不等于供应商调用；PostgreSQL clock round-trip 不等于完整跨数据库租约闭环。迭代总体维持 `NO-GO`。

## HTTP 生成部署、出站敏感字段与阶段时钟的统一回归

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load --maxschedchunk=8 \
  tests/test_ai_research_*.py tests/test_config.py --tb=short \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/v2-http-generation-stage-clock.xml
```

终态 **303 passed、23 warnings，44.60 秒，exit 0**。JUnit 实际解析为 299 项 v2 + 4 项 config，0 failure/error/skip；XML SHA-256 `964bd4d628ebf3a4e028425a1d3e10820a0313913848038fd1266ef9f6287a9f`。本批 21 个源码/测试文件 Ruff check 与 format --check 通过。

集成测试发现数值 `max_tokens` 被误脱敏的接线失败；独立只读审查发现出站映射键可携密。分别新增 6、9 项 RED 后修复，本跑次包含其完整 gateway 回归以及真实服务组成的公开 worker 正反链路。实现与限制见 [生成部署验收](GENERATION_PROVIDER_DEPLOYMENT_20260905.md)。

在收到映射键 P1 时，首个完整目录跑次被主动 Ctrl-C 停止，exit 1；当时进度还出现 1 个 F，未产生完整 JUnit/失败详单，**该跑次是中断且非通过**。随后单独复现到 `asset_research/test_migration.py` 的旧 head 断言，更新目标 head 后该文件 12 passed（7.51 秒）。不能证明中断时的 F 只可能来自此项，必须以随后新的完整跑次确认全部结果；没有使用排除文件或自动重试掩盖它。

## 历史冻结源码：provider/stage-clock 完整后端目录结果

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load --maxschedchunk=8 \
  --durations=20 --tb=short \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/backend-full-6-provider-stage-clock-final.xml \
  tests
```

终态：**5,136 passed、129 skipped、174 warnings，502.37 秒（8 分 22 秒），exit 0**。JUnit 实际解析 **5,265 cases、0 errors、0 failures、129 skipped**，其中 `test_ai_research_` 的 **299 项均通过且无跳过**。没有 ignore、失败自动重试或与其他跑次拼接。

XML SHA-256：`db7602b6f7af22f4d6147c8a7d495b7ed7963750a568f44c5574b25adec44293`。启动前、运行中和结束后 `app/tests/scripts/alembic` Python 源文件摘要均为 `329eeeb2cc935923f010614a95d302bf003d6d59b253c3b9db44508d32cc5773`。这包括未跟踪 v2 文件，不以 `git diff` 或基底 HEAD 代替实际候选来源；不包含依赖镜像或生产配置签章。

```sh
rg --files -0 app tests scripts alembic -g '*.py' \
  | LC_ALL=C sort -z | xargs -0 shasum -a 256 | shasum -a 256
```

最慢单项仍是 legacy research-loop，14.02 秒。相较此前 5,034 项/494.05 秒，本轮多 102 项测试、耗时多 8.32 秒；源码、用例和负载不同，不当作受控性能 A/B 或 6 倍加速结论。六 worker 是并发进程配置，不是 CPU affinity。

本批 21 个源码/测试文件 Ruff check/format --check 通过，主 checkout 与候选 `git diff --check` 均通过；文档仍以本迭代目录为权威。未改前端源码，因此此前前端 1,315 项只保留原有跑次，未冒称本轮重跑。跳过项不代表环境场景通过，完整目录通过也不消除 [生成部署记录](GENERATION_PROVIDER_DEPLOYMENT_20260905.md) 中的费用硬上界、后续执行/评估图、当前 UI/API 与 T2/T3/生产门禁缺口。

## 最新预算批次：联合资源、不可变请求与恢复拒绝保护

本批实现与验证边界见 [MODEL_BUDGET_BUNDLE_20260905.md](MODEL_BUDGET_BUNDLE_20260905.md)。新增准备/计费合同、总 Token／microUSD 预留、完整组 claim/settle、快照持久化、实际 HTTP seam 接线，以及独立评审发现的旧单笔恢复保护和 quota lease 下限。

### 聚焦结果

```sh
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load --maxschedchunk=8 \
  tests/test_ai_research_*.py tests/test_config.py --tb=short \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/v2-budget-bundle-final.xml
```

终态：**374 passed、23 warnings，53.46 秒，exit 0**。解析 JUnit 为370项 v2 + 4项 config，0 failure/error/skip；SHA-256 `754825ea805d9cd309ed414b4f55cb18bc65fdc650d24aee630d5907a6d69a82`。跑前/跑中/跑后 Python 清单摘要同为 `732385138301878be725497b7d7abcf24bf6b5c883d299f2d3602d43260c7b97`。

更早的 `v2-budget-bundle.xml` 为363 passed、23 warnings、55.42秒，未包含后续3项租约配置和8项旧单笔预算保护；不作为这两项修复后的证明。独立评审先复现单笔恢复可拆分预算，修复策略是禁止旧API拆组，未临时伪造供应商 group readback。租约1/60/89秒的配置先出现3个RED，增加 `ceil(timeout)+30s` 下限后工厂15项全过。

上述聚焦后，统一格式检查发现5个文件需要 Ruff 重排，已格式化；最终19个本批源码/测试/迁移文件 Ruff check 与 format --check 通过。下面完整目录在格式化后的新摘要上执行，不能以之前的hash代替它。

### 完整后端目录

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load --maxschedchunk=8 \
  --durations=20 --tb=short \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/backend-full-6-budget-bundle.xml tests
```

预算批次首轮完整目录：**FAIL / INTERRUPTED，exit 2，不能计为 PASS**。终端记录为 **1 failed、5,202 passed、129 skipped、174 warnings，764.31 秒**，随后报告 KeyboardInterrupt。主代理因末项长时间等待而向 pytest 主进程发送 SIGINT，未把中断误记为已完成。唯一已报告失败是 `test_health_check_exception_branch`；`test_full_optimization_workflow` 等未完成项不计为通过。

原始 XML SHA-256：`410f8c6f772441994e064529e69679ef81239fe0f9323484012e33cae5b37397`。中断 XML 自身也不完整：suite 属性记 5,332 tests，而实际含 5,333 个 testcase 节点（1 failure、0 error、129 skipped）；不据此推算完整收集数量或验收剩余项。跑前/跑中/跑后 Python 清单摘要均为 `a27b3fbeb9abe7bdd5a3c706c5593d4104cf8019522b2718b209999c480a83d9`，未使用 ignore 或自动失败重试。

### 中断后最小修复与独立 RED/GREEN

1. 健康检查测试先用真实健康探针预热缓存，再模拟 DB 失败，可稳定复现 `healthy != degraded`。生产健康路由具有 10 秒缓存，旧测试没有清理缓存，受 worker 内用例顺序影响。修复只让该测试注册独立 FastAPI 健康路由闭包，并在故障探针前通过 monkeypatch 清空兼容缓存；故障状态及 disconnected 断言保留，不修改生产缓存策略。整个文件独立结果为 **7 passed、1 skipped，2.75 秒**。
2. 优化工作流测试全局 patch `threading.Thread`，首次触发异步 DB 运行器时真实线程不会启动，`ready.wait()` 永远等不到事件；先前串行或同 worker 的 warm-up 会掩盖它。新解释器下单项在外部 15 秒截止时稳定被中断。修复仅 patch 本模块的 `_run_optimization_thread`，并让纯运行态用例显式使用 `use_db=False`，保留进度/结果/取消断言。修复后该单项 **1 passed，0.53 秒**，整个优化文件六 worker **47 passed，17.01 秒**。未延长产品 timeout、删测试或修改异步运行器。
3. 严格预算调用还补独立安全负例：即使 request hash 正确，缺少持久 quote 快照也必须零 HTTP。先实测旧路径仍派发一次 HTTP（RED），随后严格 gateway 为完整组显式设置 `require_reservation_context=True`；quota 在锁定组上要求非空 `model-budget-quote-v1`、canonical 一致且 hash 相符。flag 只接受同组一致的真实 bool，generic 旧 None-context 默认路径保持兼容。

以上修改后源码重新冻结；新的完整跑次将使用独立 XML 文件，不覆盖失败证据。

### 修复后的当前候选验证

```sh
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load --maxschedchunk=8 \
  tests/test_ai_research_*.py tests/test_config.py \
  tests/test_misc_branch_fixes.py tests/test_optimization_service.py --tb=short \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/v2-budget-isolation-final.xml
```

聚焦终态 **437 passed、1 skipped、23 warnings，64.27 秒，exit 0**。JUnit 实际438项，其中379项 v2 全部通过、0 skip；唯一 skip 来自原有 misc 文件。XML SHA-256：`75af784b1affb681488b09968a853d316453e2c70879bdf5b82ead1b0c470174`。新增9项 v2包括8项严格 quota context/flag 和1项真实 pipeline 缺快照拒绝。六个最终修复文件 Ruff check/format 通过；独立只读复核未发现新增问题。

```sh
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load --maxschedchunk=8 \
  --durations=20 --tb=short \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/backend-full-6-budget-isolation-final.xml tests
```

新完整目录终态 **5,216 passed、129 skipped、174 warnings，601.36 秒（10 分 1 秒），exit 0**。JUnit 实际 **5,345 cases、0 failure、0 error、129 skipped**；其中379项 v2全部通过且无跳过。此前失败的健康测试在本轮为0.530秒/通过，此前卡住的优化工作流为0.401秒/通过，不再依赖另一个 worker 先初始化异步线程。

XML SHA-256：`42cf88d1f73734c471bcfaa580b3caa9af24a8885aa1f055bf8ec8ff0241c935`。运行目录仍为候选 `src/backend`，跑前/跑中/跑后 Python 清单摘要均为 `7b5db86e3a33605cf7f0e0ae0f4b6bacdf8f20b806dd7a838e8f78f33da5e977`，与修复后聚焦一致；未排除文件、未自动失败重试、未删测试。该源清单包括未跟踪文件，但不是依赖镜像/配置/已提交制品的完整签章。

61个本批源码/相关测试文件 Ruff check 与 format --check 通过；主 checkout 和候选 `git diff --check` 通过。根代理逐项解析了 JUnit 而非只看进度100%；两处 legacy 修改只有测试隔离，不改变生产异步运行器或健康缓存策略。前端本批未编辑/重跑，既有1,315项仍只保留原跑次。

本轮最慢单项为 legacy research-loop18.12秒；完整耗时比历史 provider/stage-clock 的502.37秒长98.99秒，但用例多80项、源码和机器负载也不同，不能得出六 worker 变慢或加速倍数的受控结论。可复用的结论是固定六进程功能回归已完整完成；CPU affinity、benchmark、真实供应商及跳过环境场景没有因此被验收。

新迁移 head `20260905_ai_research_budget_context` 的 SQLite/PostgreSQL 17.7 历史NULL/JSON/降级重升独立证明见 [迁移验收](CURRENT_HEAD_MIGRATION_20260905.md)。T1本地合同不证明供应商价格与全计费Token上界、不证明全入口统一预算、自动对账、完整隔离执行图或T2/T3；整体保持NO-GO。
