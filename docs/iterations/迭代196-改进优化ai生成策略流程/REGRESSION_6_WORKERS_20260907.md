# 迭代 196：2026-09-07 六 worker 分层回归记录

日期：2026-09-07。候选工作树：`/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`；分支：`codex/iteration-196-ai-research-trust`；基底提交：`a18bcf52682686c30d919fe02d6fd734ee4271b9`。

> 当前判定：后端 `LOCAL_REGRESSION_PASS_WITH_PARTIAL_ENV_FREEZE`；前端 `LOCAL_PASS_UNSUPPORTED_RUNTIME`。holdout claim/start 候选在同一冻结 `app/tests` 来源及只读 Backtrader 导入快照下，功能与性能两条互斥通道共收集并划分 5,708 cases，其中 5,579 passed、129 skipped、0 failure/error；其余 Anaconda 依赖没有完整冻结。前端 1,345 项单测、类型检查和生产构建命令在本机通过，但本机 Node 25.1.0 超出项目声明的 `>=20 <25`。最新后端证据见第 8 节；第 2～4 节较早结果保留为同日历史基线。
>
> 该结论只适用于本地候选的自动化回归。`IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`，candidate research/promotion 仍为 `BLOCKED/NO-GO`。真实数据、真实 Provider、生产对象存储/IAM、独立服务身份、真实容器隔离、前向观察、staging、灰度和回滚证据均不能由本记录替代。

## 1. 为什么采用分层回归

用户要求尝试使用 6 核缩短回归时间。本轮把“6 核”落实为 6 个 pytest-xdist worker，并把每个 worker 的原生数学库线程限制为 1：

```sh
OPENBLAS_NUM_THREADS=1
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
VECLIB_MAXIMUM_THREADS=1
BLIS_NUM_THREADS=1
```

这避免 6 个 pytest worker 各自再创建多条 BLAS 线程。本机诊断曾观察到每个沙箱子进程默认创建 8 条 OpenBLAS 线程，六 worker 下峰值可接近 48 条原生线程；限制后 24 次直接沙箱验证的总耗时由 21.72 秒降至 17.41 秒。该诊断的源码、运行负载和样本规模不足以构成产品性能基准。

pytest-benchmark 在 xdist 下会明确禁用 benchmark，而且共享负载会污染绝对时延阈值。因此：

- 功能通道使用 6 个 worker，选择 `not performance`；
- 性能通道选择 `performance`，保持串行；
- 两个 marker 表达式互补，使用各自实际 JUnit case 数及 deselected 数核对全集；
- 没有启用测试结果缓存、失败自动重试或文件排除来隐藏失败。

这里的 6 worker 不是操作系统 CPU affinity，也不构成“固定加速 6 倍”的承诺。

## 2. 冻结身份与依赖边界

| 对象 | 身份/结果 | 证明范围 |
| --- | --- | --- |
| claim/start 前的后端 Python 基线 | `8780ff54645321a3459ecb51fd3eab0ced14f8b258b1bdc0cf38ccfef84ae0e3` | 当时 `app/`、`tests/`、`alembic/`、`scripts/` 下全部 `*.py` 的排序逐文件 SHA-256 清单摘要；只保留为 claim/start 之前的同日基线 |
| 当前 claim/start 候选 `app/tests` 来源 | `369ed9e56080f0860ea56c887cf1ebb39b2bec97830a0873a9189f40fd432d22` | `app/`、`tests/` 下全部 `*.py` 的排序逐文件 SHA-256 清单摘要；最新六 worker 功能回归前后相同。未声称覆盖 `alembic/scripts` 或完整依赖环境 |
| 只读 Backtrader 导入快照 | `/private/tmp/iter196-final-6core.YhgaM8/pythonpath-snapshot.ITzNQN`；路径绑定校验清单摘要 `438ba5751c0d555c1b29cd919ff9d6481224d7afc6dd727a09291e26a3e28254` | 只含 `backtrader/` 与 `backtrader-1.3.0.dist-info/`，排除 `__pycache__`/`*.pyc`；两条正式后端通道前后相同。摘要的输入行含绝对文件名，只能核对原路径未漂移，不是复制后仍稳定的可移植内容哈希。其余 Anaconda site-packages 未冻结、未做完整 manifest |
| 前端当前来源 | `92541bf7fcf3ad98698e3b63a97f8f6bfd3043443c7255abb1c49734d6240ee2` | `src/`、`e2e/` 下 `*.ts/*.vue/*.css` 的当前清单摘要；前端 JSON 生成后未发现这些来源有更晚修改时间，不等于发布制品签章 |
| Git 身份 | base `a18bcf52682686c30d919fe02d6fd734ee4271b9` + 未提交候选工作树 | base commit 不包含本轮未跟踪/未提交实现，不能把 base SHA 冒充交付 commit |

摘要只证明上述本地来源在声明范围内未漂移，不证明 wheel 来源、锁文件、镜像、部署配置或远端提交已经签章。发布证据必须另建路径归一化 manifest，并逐文件保存相对路径、内容哈希与来源。

### 2.1 依赖环境异常与隔离

一次完整回归期间，另一任务对共享 Anaconda 环境执行了 `pip install --force-reinstall`。site-packages 在测试进程运行中经历非原子替换，导致一个 CTP 子进程短暂读取到不完整的 `backtrader` 包。该跑次标记为 `DEPENDENCY_ENV_MUTATED/INVALID`，既不计产品 FAIL，也不计 PASS；后续正式跑次使用只读快照固定 **Backtrader** 导入来源，其他依赖仍来自共享 Anaconda 环境。

快照读回的 `backtrader` 版本为 `1.3.0`，而 `pyproject.toml` 与 `requirements.txt` 声明 `backtrader>=1.9.78.123`。因此本记录能够证明“当前候选在这个明确快照上回归通过”，不能证明“从声明依赖可在干净环境重建同一运行时”。在自定义 wheel 的来源、版本语义、锁定、干净安装和制品读回闭合前，`DEPENDENCY_PROVENANCE=NO-GO`，并继续阻断发布验收。

### 2.2 未计入 PASS 的失败/无效跑次

最终双通道结果不覆盖或抹去此前失败。下列 JUnit 均保留在同一临时证据目录；它们不是当前 PASS 的组成部分：

| JUnit | 实际结果 | 处置 | SHA-256 |
| --- | --- | --- | --- |
| `backend-full-final.xml` | 5,635 cases；7 failures、129 skipped；其中2项明确为sandbox timeout，其余为AI研究续跑/状态断言失败 | `FAIL_DIAGNOSTIC`；当时未限原生线程且使用旧统一计时协议 | `d202e891c7438942be2480fc8dd14cdf77849c62b4d04870447c903c13d1b467` |
| `backend-full-final-source-6core.xml` | 5,635 cases；1 failure、129 skipped；CTP子进程缺少 `backtrader.analyzers.transactions` | `DEPENDENCY_ENV_MUTATED/INVALID`；共享site-packages在运行中被另一任务非原子替换，既不计产品FAIL也不计PASS | `2f534f09d7991c294c43b2d19bb6016c3e656461acdbc6def05359503d7bd3bb` |
| `backend-full-final-frozen-6core.xml` | 5,635 cases；1 performance failure、129 skipped；portfolio import样本最大值2,661.466ms，高于2,000ms阈值 | `FAIL_DIAGNOSTIC`；xdist共享负载污染绝对性能阈值，促成互斥双通道方法，但该跑次仍保持FAIL | `9e6d2d0b2352aca1a845fe585ae5560d82e76aaffd720cbd968fc93f6fedc1be` |
| `backend-functional-final-6core.xml` | 5,618 cases；3 AI策略研究服务 failures、129 skipped | `FAIL_DIAGNOSTIC`；2项断言载荷含sandbox timeout，另1项未独立归因；完成ready协议修复后重新全量执行，但不追溯改写该失败跑次 | `ca133135fcf22502ea6077dc604f6b91cec8f3977e5b087fe8b9edb55de87a3a` |
| `backend-functional-6core.xml` | 5,684 cases；1 failure、123 skipped；失败为取消期间等待 fake 回测提交入口固定 5 秒超时 | `FAIL_DIAGNOSTIC`；真实动态沙箱预检在入口之前同步阻塞 event loop，6-worker 负载下存在 Event/timeout 非确定性竞争。精确节点串行通过；隔离该测试的动态 spawn 后重新全量执行 | `aade645bc9490e204e4ec2bdb7b06c02ffa385f6068ab9fef34bc15a5ba53e11` |

这些失败跑次的case总量与该历史基线5,641不同，因为沙箱协议负例在后续TDD中增删/调整；不得把不同源码时点的testcase拼接成一次绿灯。

## 3. Claim/start 之前的后端正式基线

本节是同日较早候选的正式基线，不能作为后续 claim/start 源码的当前证明。claim/start 的 184 项聚焦结果、第一次全量失败诊断和最终全绿结果见第 8 节及 [独立证据](HOLDOUT_CLAIM_START_20260907.md)。

### 3.1 六 worker 功能通道

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
PYTHONPATH=/private/tmp/iter196-final-6core.YhgaM8/pythonpath-snapshot.ITzNQN \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest tests -m 'not performance' -p no:rerunfailures -q --tb=short \
  -n 6 --dist load --maxschedchunk=8 \
  --junitxml=/private/tmp/iter196-final-6core.YhgaM8/backend-functional-ready-protocol-6core.xml
```

结果：**5,494 passed、123 skipped、0 failure/error、188 warnings，626.07 秒，exit 0**。JUnit 实际含 5,617 cases，suite time 625.379 秒。

- JUnit SHA-256：`5f03dfc5fdf9644db0675a69ecd0bb84af012e18a2817e5344a6fd79114bc83b`。
- 123 项 skip 保留原条件，不解释为通过。主要包括 79 项 AkShare vendor/真实依赖场景、25 项需真实 Backtrader strategy context 的 analyzer 场景、3 项真实 MySQL task-runner/shared-schema 合同、3 项外部网络历史行情场景及其他既有条件跳过。
- `-p no:rerunfailures` 明确禁用失败自动重试；没有使用 `--ignore`。

### 3.2 串行性能通道

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
PYTHONPATH=/private/tmp/iter196-final-6core.YhgaM8/pythonpath-snapshot.ITzNQN \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest tests -m performance -p no:rerunfailures -q --tb=short \
  --junitxml=/private/tmp/iter196-final-6core.YhgaM8/backend-performance-serial-ready-protocol.xml
```

结果：**18 passed、6 skipped、0 failure/error、5,617 deselected、6 warnings，17.64 秒，exit 0**。JUnit 实际含 24 cases，suite time 17.633 秒。

- JUnit SHA-256：`21bd750f9bc960de1435d0157dadc1072157f4cd03bf2a9079561e4ddeb3dd0f`。
- 6 项 skip 均来自 `test_performance_baseline` 的既有显式条件“依赖系统负载、结果易波动”；这些场景为 `NOT_RUN_CONDITIONAL`，不能计为性能门 PASS。
- 14 项 pytest-benchmark 样本与其余已执行性能断言均通过；本结果只证明本机本轮串行阈值，不外推为容量、SLO 或生产负载验收。

### 3.3 两通道覆盖闭合

| 通道 | 实际 cases | Passed | Skipped | Failure/Error |
| --- | ---: | ---: | ---: | ---: |
| `not performance` | 5,617 | 5,494 | 123 | 0 |
| `performance` | 24 | 18 | 6 | 0 |
| 并集 | **5,641** | **5,512** | **129** | **0** |

性能通道报告 5,617 deselected，等于功能通道实际 cases；两个选择表达式互补，因此 testcase 交集为 0、并集为本轮 `tests` 收集全集 5,641。这里不把两次运行的墙钟时间相加后冒充一次单进程全量性能结果。

## 4. 沙箱并发超时的根因修复与归因边界

旧 XML 支持的结论必须拆开。`backend-full-final.xml` 的7项失败中，2项直接报sandbox timeout、1项断言载荷含sandbox timeout，另4项只是策略名称/续跑状态断言；`backend-functional-final-6core.xml` 的3项失败中，2项载荷含timeout，另1项只显示improver调用数/validation-failed断言。后两类断言可能受前置超时或并发状态影响，但现存JUnit不足以证明它们与沙箱共享同一根因，故继续保留为未独立归因的`FAIL_DIAGNOSTIC`，不因最终绿灯被追溯改写。

对明确、可复现的sandbox timeout，根因是 `StrategySandbox.validate_strategy_code` 的统一父进程计时：旧实现把spawn、模块导入、用户代码执行和可信Pandas/Backtrader预检全部压入 `execution_timeout + 5` 秒；高负载下有效策略可能在用户代码尚未超时前被父进程误杀。

本轮没有放宽不可信代码自身的执行时限，而是建立双阶段协议：

1. 子进程先应用 CPU/内存/文件描述符限制，再发送严格的 `("ready", "validator-v1")`；
2. 父进程用独立、有限的 15 秒等待 spawn/bootstrap；
3. 收到 ready 后才启动 `execution_timeout + 5` 的执行及可信预检预算；
4. terminal 只接受 `ok/execution/preflight` 且 payload 必须为字符串；
5. 清理使用 bounded join → terminate → bounded join → kill → bounded join；最终仍存活时成功路径 fail-closed，已有主异常则保留主异常并附加 cleanup failure；
6. Process 构造失败关闭 Pipe 两端，子端所有终态均在 finally 关闭。

新增6条协议/清理负例先RED后GREEN。最终完整沙箱及选取的三个曾失败业务节点为 **98 passed、1 skipped**；随后全部包含在5,617-case功能通道中。这证明修复后当前节点通过，但不反向证明旧XML的全部业务断言共享同一根因。multiprocessing路径仍只允许作为开发/测试隔离，`Connection.recv()` 的pickle/消息大小边界属于保留安全债务；生产路径必须使用Docker，并需另行提供真实网络、资源、进程清理和逃逸拒绝证据。

## 5. 前端结果

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/frontend
npm run test -- --run --minWorkers=6 --maxWorkers=6 \
  --reporter=basic --reporter=json \
  --outputFile.json=/private/tmp/iter196-final-6core.YhgaM8/frontend-vitest-6core.json
npm run typecheck
npm run build
npm run lint
```

| 检查 | 结果 |
| --- | --- |
| Vitest | **148 files、1,345/1,345 tests passed、0 failed/pending**；JSON 记录时长 20.141 秒 |
| Vitest JSON | SHA-256 `ecb9bbd79947d635608c5240a3a291937fb5f722d9db2e31572b5268ec8c56b9` |
| TypeScript | `vue-tsc --noEmit` PASS |
| Production build | PASS；初始记录26.11秒，文档收口时同源码复验25.49秒；保留既有大于500 kB chunk提示 |
| ESLint | exit 0、0 error、1,338 warnings；未用无关全仓自动修复改写该基线 |

本轮运行时为 Node 25.1.0，而 `package.json` 明确要求 `>=20 <25`，CI/Docker 使用 Node 20。因此这些结果只能记为当前源码的 `LOCAL_PASS_UNSUPPORTED_RUNTIME`，发布候选必须在 Node 20 重新执行；它们也不替代当前候选的已认证真实 UI/API、屏幕阅读器或人工焦点验收。

## 6. 静态与质量检查

- `/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base ruff check app tests alembic scripts`：PASS。
- 候选 `git diff --check`：PASS，但只检查tracked diff，不覆盖untracked文件。
- 最新读回时，代码候选worktree的 `git status --short` 为39个tracked修改、144个untracked，共183项；该统计不含主checkout里的迭代文档。
- 迭代196的31份Markdown位于主checkout；对该目录执行scoped `git status --short -- <iteration-196-dir>` 时显示为一个折叠的untracked目录项。代码候选与文档均尚无可由提交哈希读回的seal，`G0 provenance=NO-GO`。
- 本文引用的JUnit/JSON位于`/private/tmp`，未进入版本化制品库，可能被操作系统清理；哈希支持当前会话读回，不构成长期发布证据保全。
- 本轮没有 commit、push、PR、部署、服务重启、业务数据库写入、真实 Provider 调用或真实交易。

## 7. 验收裁决

| 决定 | 状态 | 依据/缺口 |
| --- | --- | --- |
| 六 worker 本地功能回归 | `LOCAL_PASS_WITH_SKIPS_PARTIAL_ENV_FREEZE` | 最新 claim/start 候选为5,684 cases，5,561 passed、123 skipped、0 failure/error；123条显式条件skip保留，且只冻结`app/tests`与Backtrader导入来源 |
| 串行性能回归 | `LOCAL_PASS_WITH_SKIPS_PARTIAL_ENV_FREEZE` | 最新 claim/start 候选为24 cases，18 passed、6 skipped、0 failure/error；6条负载敏感基线未运行，且不是容量/SLO验收 |
| 前端单测/类型/构建 | `LOCAL_PASS_UNSUPPORTED_RUNTIME` | 1,345 单测全过，typecheck/build 通过；Node 25.1.0 不在项目 `>=20 <25` 支持范围，须以 Node 20 重跑发布门 |
| 依赖可复现性 | `NO-GO` | 固定快照为自定义 `backtrader 1.3.0`，不满足项目声明版本范围；尚无来源/锁/干净安装/制品读回 |
| Git candidate seal / G0 provenance | `NO-GO` | 最新读回时代码worktree有39个tracked修改与144个untracked；主checkout的迭代196目录另为untracked。两边均未形成可由提交哈希重建的候选；`git diff --check`不覆盖untracked文件 |
| G0～G4 / `IMPLEMENTATION_ACCEPTED` | `NO-GO` | 横向回归通过不等于每个具名 AC 的身份、环境与负例均已满足；真实隔离拓扑、对象存储、当前 authenticated E2E 等仍缺 |
| T2 真实数据与 Provider | `BLOCKED_ENVIRONMENT` | 未使用授权真实数据、模型凭据或生产秘密 |
| T3 前向观察/模拟审批 | `BLOCKED_ENVIRONMENT` | 无冻结后真实观察窗口、staging 审批、监控、备份和回滚演练 |
| `PROTOCOL_PRODUCTION_ENABLED` | `NO-GO` | G5、依赖来源、生产容器/身份/网络和灰度证据未闭合 |
| Candidate research/promotion | `BLOCKED/NO-GO` | 本轮没有任何候选级新鲜真实数据、密封留出、前向和人工决定证据 |

因此，本轮证明的是“当前 claim/start 候选在明确本地 `app/tests` 源码和固定 Backtrader 导入快照下，可用六 worker 完成非性能功能回归，并用独立串行通道完成已启用性能测试”。由于其余依赖未形成完整环境 manifest，该结论不是完全冻结环境或干净重建证明；它也不证明策略有效、未来盈利、真实市场可用或生产可发布。

## 8. Holdout claim/start 增量证据与最终重跑

### 8.1 聚焦 T1

内部 claim/start、request、authorization、independent evaluator、promotion、API、migration、dataset 和 candidate 相邻合同使用 6 个 xdist worker 执行，结果为 **184 passed、42 warnings、48.06 秒、exit 0**。11 文件 manifest 为 `a1fde1be8faaae282cb48951970c4b4f91f4ad23bb3e12b3bf204446277ddc9c`；规格复审与代码质量终审均为本地范围 `PASS`、P0/P1 为 0。完整命令、逐文件身份和合同边界见 [HOLDOUT_CLAIM_START_20260907.md](HOLDOUT_CLAIM_START_20260907.md)。

### 8.2 首次全量失败与测试隔离

第一次 claim/start 后完整功能通道为 **5,560 passed、123 skipped、1 failed、192 warnings、796.45 秒**。失败测试在 fake 回测提交入口之前同步执行真实 multiprocessing 沙箱预检，却只等待入口 5 秒；沙箱自身允许 15 秒 bootstrap、3 秒执行和5秒 grace。精确节点串行通过，6-worker cancellation 组可失败后再通过，故判为既有测试隔离缺陷，不是 holdout 死锁。

修复保留生产 wrapper 的安全、AST、继承、依赖和类完整性检查，只在该 cancellation 用例中跳过范围外的动态 spawn，并注入已有 fake/no-op 附属服务。没有改变生产超时。独立审查为 `PASS`、P0/P1 为0；6-worker cancellation 组7/7通过。原失败 JUnit及 SHA 保留在第2.2节，不能被最终绿灯覆盖。

### 8.3 最终六 worker 功能通道

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
PYTHONPATH=/private/tmp/iter196-final-6core.YhgaM8/pythonpath-snapshot.ITzNQN \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest tests -m 'not performance' -p no:rerunfailures -q --tb=short \
  -n 6 --dist load --maxschedchunk=8 \
  --junitxml=/private/tmp/iter196-final-green-6core.hJclQn/backend-functional-after-cancel-isolation-6core.xml
```

结果：**5,561 passed、123 skipped、0 failure/error、192 warnings、818.39 秒、exit 0**。JUnit 实际为5,684 cases，suite time 817.960 秒，SHA-256 `a46356ebad9af83a5354e866251106d6dbe07337347cce7d72706708e4d8f221`。其中 `test_ai_research_*` classname 子集为735/735 passed、0 skipped/failure/error。

### 8.4 最终串行性能通道

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
PYTHONPATH=/private/tmp/iter196-final-6core.YhgaM8/pythonpath-snapshot.ITzNQN \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest tests -m performance -p no:rerunfailures -q --tb=short \
  --junitxml=/private/tmp/iter196-final-green-6core.hJclQn/backend-performance-serial-after-cancel-isolation.xml
```

结果：**18 passed、6 skipped、0 failure/error、5,684 deselected、6 warnings、14.94 秒、exit 0**。JUnit suite time 14.742 秒，SHA-256 `fe1eafa9beb674730b5bb8efc3c1ea94a520c0fb425fbc3576bd091060052b62`。功能与性能通道互斥并集为 **5,708 cases：5,579 passed、129 skipped、0 failure/error**；129条skip不计PASS。

当前 `app/tests` 源码清单摘要在功能回归前后均为 `369ed9e56080f0860ea56c887cf1ebb39b2bec97830a0873a9189f40fd432d22`。Ruff全范围与tracked diff whitespace检查通过。固定Backtrader快照仍为`1.3.0`，不满足声明`>=1.9.78.123`；真实PostgreSQL/MySQL、queue、IAM、Evaluator、sealed计算、checkpoint/finalize、当前authenticated UI/API、T2/T3、灰度和回滚均未运行。因此总体裁决继续保持第7节的全部 `NO-GO/BLOCKED`。
