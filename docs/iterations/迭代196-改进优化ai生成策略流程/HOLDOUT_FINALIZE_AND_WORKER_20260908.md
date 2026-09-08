# Holdout Finalize、外部执行 Journal 与 Worker 本地证据（2026-09-08）

> 判定：`LOCAL_T1_PASS`，只覆盖当前源码下的本地服务、SQLite/SQLAlchemy 合同和受控 fake/HTTP adapter。
> 发布边界：`IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`、candidate research/promotion=`BLOCKED/NO-GO`。
> 实现工作树：`/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`
> 需求/验收：`FR-DATA-014`、`FR-TASK-011～012`、`AC-SEAL-007`、`AC-TASK-008`。

## 1. 本切片闭合的协议

本切片承接 [claim/start 合同](HOLDOUT_CLAIM_START_20260907.md)，把 `RUNNING / HOLDOUT_PENDING` 之后的本地协议补到可审计终态。外部 Evaluator 调用不再被一个不可验证的函数返回值代表，而被拆成四类持久对象：

| 对象 | 权威内容 | 禁止内容 |
| --- | --- | --- |
| execution command | 精确 command hash、候选/冻结回执、authorization/evaluation、snapshot/profile/policy/image 的不透明绑定 | 原始留出数据、路径、URI、密钥、bearer token |
| execution operation/journal | operation ID、idempotency key、`PREPARED/DISPATCHING/UNKNOWN/OBSERVED/SETTLED`、inspect 结果与 fencing generation | 浏览器提供的执行身份或“已执行”布尔声明 |
| result artifact/checkpoint | 服务端规范化的聚合指标、安全回执、artifact hash、command/evaluation binding | raw returns、逐笔数据、留出路径、任意客户端 manifest |
| terminal graph | evaluation、13 项 gate、command、epoch、terminal audit、promotion receipt 与 evidence package 的同一 command-wide 绑定 | 从其他 evaluation 拼门、legacy evidence、缺失或额外 gate |

`checkpoint` 与 `finalize/reconcile` 都在写入前、外部动作后和提交前重验 lease generation、owner、bearer hash、evaluator/image identity 与冻结 authority graph。终态只接受服务器持久化 checkpoint；恢复不能再次读取密封数据、重签 authorization 或重新派发同一外部副作用。

## 2. 外部副作用与 ACK 不确定性

worker 使用同一个 operation ID 执行以下状态机：

```text
PREPARED -> DISPATCHING -> OBSERVED -> SETTLED
                         \
                          -> UNKNOWN -> inspect
                                      -> OBSERVED -> SETTLED
                                      -> NOT_EXECUTED -> 同 operation 重新派发
                                      -> STILL_UNKNOWN -> 保持 UNKNOWN/阻断
```

关键规则：

- `execute` 只能在原子 `begin_dispatch` 成功后调用；两个 worker 竞争只有一个 dispatch winner；
- HTTP adapter 只允许固定的 HTTPS collection route，operation key 在 header/route 中绑定，密钥不进入 body、日志或数据库；
- timeout、连接断开或 commit ACK 丢失不能推断“未执行”，必须进入 `UNKNOWN`；
- 只有对同一 operation 的 `NOT_EXECUTED` 证明才允许重派发，而且仍复用原 operation；
- `OBSERVED` 后即使 worker 崩溃，新 worker 也只能从 journal/checkpoint 收口，不能再次调用 Evaluator；
- 连续 inspect 仍未知时维持 `UNKNOWN`，不会通过换 worker、换幂等键或租约过期制造第二个副作用；
- heartbeat 在远端仍运行时续租；旧 token、旧 generation、错误 identity/image 或过期 lease 均不能续租。

## 3. Worker 与部署边界

`scripts/run_ai_research_v2_holdout_worker.py` 只允许从受限 deployment namespace 解析经过审查的 factory。默认配置为关闭；关闭时不会解析 factory、claim 或连接 Evaluator。启动失败只返回稳定错误码，不向控制台泄漏 bootstrap detail。

这些合同证明了“本地代码在受控 executor 下不会盲目重复派发”，没有证明生产独立性。当前没有新鲜证据证明：

- 独立 queue、进程/容器、workload identity、数据库角色和对象存储 IAM；
- 真实 HTTPS Evaluator 的证书固定、网络策略、超时与 operation read-back；
- 跨主机/跨进程数据库竞争、真实 PostgreSQL/MySQL/MariaDB 锁语义；
- 真实 sealed snapshot 读取、计算资源限制、raw output 防外传和生产审计采集。

因此 deployment capability 仍须 fail-closed；本地 factory、fake executor 或 HTTP mock 不能被显示为“独立评估已完成”。

## 4. 已执行的六 worker 聚焦证据

功能测试按用户要求使用 6 个 xdist worker，并把每个 worker 的 BLAS/OpenMP 线程限制为 1。holdout finalize、execution contract/journal、worker/process、HTTP executor、相邻 claim/promotion/evidence/migration 合同的组合回归结果为：

```text
377 passed, 0 failed/error, 88.91 seconds
```

对 dispatch ACK loss、inspect、同 operation 重派发和跨 worker 恢复的核心切片另行复验：

```text
48 passed, 0 failed/error, 18.87 seconds
```

holdout finalize/execution migration 的本地聚焦合同为：

```text
22 passed, 0 failed/error
```

命令统一采用：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m pytest -p no:rerunfailures -q --tb=short \
  -n 6 --dist load --maxschedchunk=8 <上述聚焦文件>
```

这些数字是完成各切片时的当前源码证据；最终横向源码冻结与完整回归另见 [2026-09-08 六 worker 回归记录](REGRESSION_6_WORKERS_20260908.md)。若最终记录尚未形成或源码摘要不一致，本页不能代替最终回归。

## 5. 验收判定

| 项目 | 状态 | 边界 |
| --- | --- | --- |
| terminal command/checkpoint/finalize 本地合同 | `LOCAL_T1_PASS` | 受控数据库与 fake executor |
| UNKNOWN/inspect/同 operation 恢复 | `LOCAL_T1_PASS` | 没有真实网络/远端服务故障注入 |
| 六 worker 同进程竞争 | `LOCAL_T1_PASS` | 不等于跨进程/多数据库竞争 |
| 真实 Evaluator、queue、IAM、object storage | `NOT_RUN` | 阻断 capability 与生产启用 |
| 真实密封研究与候选晋级 | `NOT_RUN/BLOCKED` | 没有真实数据、指标或人工决定 |

