# 迭代 196：2026-09-08 六 worker 分层回归记录

> 结论：固定 6 worker 的后端功能通道、串行性能通道和固定 6 worker 的前端 Vitest 通道均在各自声明的本地范围通过；后端两通道互斥覆盖 6,278 cases，其中 6,149 passed、129 skipped、0 failure/error，前端 1,556/1,556 passed。该结果是 `LOCAL_T1` 组件与回归证据，不是候选封存或生产发布验收。依赖版本不符、未提交工作树、全仓格式检查未过以及真实基础设施/在线数据库/T2/T3 未验收，决定 `IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`。

## 1. 候选身份与证据边界

| 项目 | 冻结值 | 判定 |
| --- | --- | --- |
| 实现工作树 | `/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust` | 本地实现来源 |
| 分支 | `codex/iteration-196-ai-research-trust` | 本地实现来源 |
| 基础/当前提交 | `a18bcf52682686c30d919fe02d6fd734ee4271b9` | 工作树仍有大量未提交变更，不能作为 candidate seal |
| 后端 Python 来源摘要 | `03513ad1302d16e567ec180705181ac85be7d18fd25b88f5a13669de80988ec1` | 对 `app/`、`tests/`、`alembic/`、`scripts/` 下所有 `*.py` 排序、逐文件 SHA-256 后再汇总；功能跑前、功能跑后、性能跑后相同 |
| 前端扩展候选摘要 | `c9ac863c38d719c3e38e08ae16368dce0d8afc8ae061104b3c06cbf505540d0a` | 覆盖 `src/e2e/scripts` 的 `ts/vue/css/json/mjs`、`package.json` 和两个 Dockerfile |
| 前端窄摘要 | `37b83be5aa413062505ad230a6f1a25f81aff23a06c2ae6ea3600fd937009378` | 仅覆盖 `src/e2e/scripts` 的同类前端来源；不得替代扩展摘要 |
| Git/candidate gate | 未提交候选 | `G0 provenance/candidate seal=NO-GO` |

JUnit 与 Vitest JSON 位于 `/private/tmp/iter196-final-20260908.YoXAyt/`，只用于本次会话读回与核对。`/private/tmp` 不是持久发布工件库，不得把这些路径写进 release manifest 充当长期归档。

## 2. 依赖快照

后端回归统一从只读快照导入 Backtrader：

```text
/private/tmp/iter196-final-20260908.YoXAyt/pythonpath-snapshot
```

- 快照报告版本：`1.3.0`；
- 快照摘要：`34a1e78d996dc423d24d0ada5cd2609251734551ece05b523f51aa3fd8b8bee1`；
- 项目声明：`backtrader>=1.9.78.123`；
- 判定：导入来源虽然在跑次内固定，但版本不满足声明，依赖来源与干净重建门保持 `NO-GO`。

除 Backtrader 快照外，本机 Anaconda 环境的全部 transitive site-packages 未形成完整锁定/制品清单，因此本报告不能声明完整环境可复现。

## 3. 后端功能通道：固定 6 核

原生数学库线程均限制为 1，pytest-xdist 固定 6 worker，并排除 `performance` 标记；未使用自动重试：

```bash
OPENBLAS_NUM_THREADS=1 \
OMP_NUM_THREADS=1 \
MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 \
BLIS_NUM_THREADS=1 \
PYTHONPATH=/private/tmp/iter196-final-20260908.YoXAyt/pythonpath-snapshot \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
python -m pytest -p no:rerunfailures -q --tb=short --durations=20 \
-n 6 --dist load --maxschedchunk=8 -m 'not performance' \
--junitxml=/private/tmp/iter196-final-20260908.YoXAyt/backend-functional-6core-final.xml tests
```

最终结果：

- JUnit：6,254 cases；6,131 passed、123 skipped、0 failure、0 error；
- JUnit `time`：960.565 秒；pytest 终端：961.25 秒（约 16:01）；
- JUnit SHA-256：`cb48d988cba6a36151adef2513eee0d03c32ce4c8a8d69a382f2c231d2bf54fe`；
- `test_ai_research_*` classname 子集：1,303/1,303 passed；
- approval 子集：299/299 passed。

123 个 skip 仍按各自条件记为未执行，不得换算为 PASS。

## 4. 首轮失败记录与修复闭环

首轮正式 6 worker 功能报告被保留，没有被最终绿灯覆盖：

- 文件：`/private/tmp/iter196-final-20260908.YoXAyt/backend-functional-6core.xml`；
- JUnit：6,207 cases；6,082 passed、123 skipped、2 failed、0 error；
- JUnit `time`：1065.972 秒；终端：1066.43 秒；
- SHA-256：`8e6e6a35a67e0726986d37ec3309fed298265f1580009919a537dd770f663e26`。

两个失败均属于测试合同落后于已经审计确认的当前协议，而不是通过放宽生产实现规避：

1. migration 测试仍断言旧 head `20260908_ai_research_evidence_command`，实际唯一 head 已是 `20260908_ai_research_approval_authority`；先稳定复现 RED，再更新唯一 head 合同并以目标文件、完整 migration suite 和 Alembic heads 读回形成 GREEN。
2. ADMIN 权限测试仍以旧枚举长度断言“拥有全部权限”；新增的 `APPROVE_RESEARCH` 与 `MANAGE_APPROVAL_GRANTS` 是职责隔离权限，普通 ADMIN 不应自动拥有。测试改为验证精确权限闭包，并确认专用 `RESEARCH_APPROVAL_ADMIN` 只能管理 grant、不能直接批准。

## 5. 后端性能通道：必须串行

性能标记集没有使用 xdist，以避免 6 worker 争抢 CPU 令阈值失真；线程限制、只读 Backtrader 快照与功能通道一致：

```bash
OPENBLAS_NUM_THREADS=1 \
OMP_NUM_THREADS=1 \
MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 \
BLIS_NUM_THREADS=1 \
PYTHONPATH=/private/tmp/iter196-final-20260908.YoXAyt/pythonpath-snapshot \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
python -m pytest -p no:rerunfailures -q --tb=short --durations=20 \
-m performance \
--junitxml=/private/tmp/iter196-final-20260908.YoXAyt/backend-performance-serial-final.xml tests
```

结果：24 cases；18 passed、6 skipped、0 failure/error，6,254 deselected，14.96 秒；JUnit SHA-256 为 `266e54675445ada4b6d0e1c5c95db5f00b8dd63dea8b30c3687fa9233c71ab20`。6 个 skip 仍是未执行条件。

功能与性能通道通过互斥 marker 划分，总计 6,278 cases：6,149 passed、129 skipped、0 failure/error。该加总不把 deselected 重复计入，也不把性能用例并行化。

## 6. 前端固定 6 worker

Vitest 固定最小/最大 worker 均为 6：

```bash
npm test -- --run --minWorkers=6 --maxWorkers=6 \
  --reporter=basic --reporter=json \
  --outputFile.json=/private/tmp/iter196-final-20260908.YoXAyt/frontend-vitest-6core-final.json
```

| 检查 | 结果 |
| --- | --- |
| Vitest | 154 test files、1,556/1,556 passed、19.29 秒 |
| JSON SHA-256 | `86c6380a7c12650d89641a556afbab9198fb46602b7b7f4f38496e1b18b1467b` |
| TypeScript | `npm run typecheck` PASS |
| 审批错误目录 | strict verifier PASS：48 entries，版本 `ai-research-approval-errors/v1`，摘要 `6dd9f6ce55ec595c9441ae08e26f6cc0845549eb1c950a6a28481ad973870d53` |
| Build | 4,091 modules，22.67 秒，PASS |
| Scoped lint/node check | PASS |
| 独立前端终审 | P0/P1/P2=0；8 files、300/300 focused tests passed（4.17秒） |
| 运行时 | Node `v25.1.0`、npm `11.6.2`，超出 `engines >=20 <25` |

因此前端结果只能记为 `LOCAL_PASS_UNSUPPORTED_RUNTIME`。受支持的 Node 20 lane 为 `NOT_RUN`；authenticated current UI、真实 API/数据库链路与无替身浏览器旅程也为 `NOT_RUN`。

## 7. 审批、迁移与静态检查摘要

- 审批终审：P0/P1/P2 = 0；审批三文件聚焦回归 164/164 passed，API/hypothesis 相关回归 61/61 passed；真实 1+19 SQLite 入口 barrier 的同进程锁语义通过。
- scoped mypy：环境中的 mypy `1.16.1` 对 `research.py`、`approval.py`、`approval_authority.py` 报 0 error；项目锁定的 `1.20.2` 未执行，必须记 `NOT_RUN_PINNED_VERSION`。
- migration：唯一 head `20260908_ai_research_approval_authority`；独立 suite 135/135 passed；SQLite/PostgreSQL/MySQL/MariaDB 四个离线 SQL lane 与 heads 读回通过。
- `ruff check app tests alembic scripts`：PASS。
- `/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m compileall -q app tests alembic scripts`：PASS，exit 0。
- `ruff format --check app tests alembic scripts`：**FAIL**，报告 16 files would reformat；其中包含未由本迭代修改的干净文件 `tests/test_ctp_certification_workspaces.py`。本轮未擅自格式化无关文件；审批/迁移/前端 scoped format 均通过。全仓 format 仍是明确的 P2/gate limitation，不能写成“全静态绿”。
- `git diff --check`：PASS；冲突标记扫描：PASS。它们不能弥补未提交候选和缺少 candidate seal。

## 8. 未运行、阻断与最终判定

以下证据未被本地绿灯替代：

- 真实 PostgreSQL、MySQL、MariaDB 当前 head online upgrade/反射、触发器/函数执行、20 个独立 process/connection 竞争与 operational rollback：`NOT_RUN_CURRENT_HEAD`；
- 真实对象存储/IAM、queue、独立 Evaluator、真实 Provider、生产 Sandbox/runner：`NOT_RUN/BLOCKED_ENVIRONMENT`；
- authenticated current UI、受支持 Node 20、T2 新鲜真实数据/Provider、T3 前向观察与 staging 审批/回滚：`NOT_RUN/BLOCKED_ENVIRONMENT`；
- 干净 checkout 的完整依赖重建、提交身份与 candidate seal：`NO-GO`。

最终判定：本地后端、前端、审批与迁移合同回归在声明范围内通过，但 `IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`，candidate research/promotion 仍为 `BLOCKED/NO-GO`。
