# Holdout Claim/Start 本地 T1 证据（2026-09-07）

> 判定：`LOCAL_T1_PASS`，仅覆盖内部 Evaluator claim/start、lease fencing、heartbeat 和保守恢复的本地服务/数据库合同。
> 发布边界：`IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`、candidate research/promotion=`BLOCKED/NO-GO`。
> 实现工作树：`/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`
> 当前迁移 head：`20260907_ai_research_holdout_claim`

## 1. 本切片交付了什么

本切片在 [holdout request command](HOLDOUT_REQUEST_COMMAND_20260907.md) 之后增加内部 `HoldoutClaimService`。它没有增加公开 HTTP claim、heartbeat 或 recover API；只有部署侧 Evaluator worker 能把自己的运行身份直接传给内部服务。

一次成功 claim 在同一权威事务中完成以下状态变化：

| 对象 | claim 前 | claim 成功后 |
| --- | --- | --- |
| command | `QUEUED / REQUEST_HOLDOUT`；0 authorization、0 evaluation、0 generation | `RUNNING / HOLDOUT_PENDING`；绑定一个 authorization、一个 evaluation 和 generation 1 |
| holdout authorization | 不存在 | 恰好一个，JIT 创建并已经 `CONSUMED` |
| evaluation | 不存在 | 恰好一个 `RUNNING` 记录；尚无结果工件或密封指标 |
| experiment epoch | `SELECTED` | `DISCLOSED` |
| access audit | 不存在 claim 事件 | 追加一条 `CLAIM_STARTED / ACCEPTED`，绑定 command、authorization、evaluation、epoch、candidate、snapshot 和 generation |

这里的 `RUNNING` 只表示 Evaluator 已取得带 fencing 的执行权，不表示已经读取完密封数据、完成回测、生成指标或通过晋级门。

服务端生成 bearer lease token，只把 SHA-256 哈希写入数据库；原始 token 仅通过内部返回对象交给领取者，并从该对象的 `repr` 隐藏。客户端、公开 API、审计行和数据库列都不接收原始 token。旧的兼容授权接口仍存在，因此生产部署必须继续隔离旧入口，不能把 `repr=False` 当作日志或序列化安全的完整证明。

## 2. Claim、heartbeat 与恢复合同

### 2.1 Claim fencing

正向 claim 会重新锁定并校验 command、epoch、candidate、严格冻结回执、run、capability profile、discovery snapshot 和队列时绑定的 sealed snapshot。运行身份包含 worker identity、evaluator identity 和 evaluator image digest；缺失、漂移、过期、对象完整性失败或已有 authority 残留均 fail-closed。

并发控制分两层：

- 进程内使用 64 个按 command 分片的异步锁，减少同一 event loop 中的重复工作；
- 数据库约束、锁序、唯一键和条件更新才是跨实例权威，进程内锁不能被解释为多进程证明。

本地 20 个并发 claim 收敛到一个 consumed authorization、一个 running evaluation、一个有效 lease generation 和一条 accepted claim audit；其余请求被拒绝，不能签发第二套 authority。

### 2.2 Heartbeat

heartbeat 必须同时匹配：

- command 与 `RUNNING / HOLDOUT_PENDING` 状态；
- worker/evaluator/image 运行身份；
- lease owner；
- bearer token 的服务端哈希；
- lease generation；
- 数据库时间下仍有效的租约。

任何旧 token、旧 generation、错误身份、过期租约或非运行状态都不能续租。租约时间取数据库时钟，避免把单机应用时钟当作并发权威。

### 2.3 过期与不确定提交恢复

过期 lease 不会重新排队或重新签发授权，而是转为 `RECONCILING / HOLDOUT_PENDING`，保留原 authorization、evaluation、generation 和 attempt，清除 active lease，并追加 `LEASE_EXPIRED_RECONCILING` 审计。恢复使用已持久化的静态 authority graph；即使 capability profile 后来过期或 live object resolver 暂时不可用，也不会借恢复路径重新读取密封对象或创造第二次访问。

若 accepted claim 的审计写入失败，整套 authority mutation 回滚，并返回稳定错误 `HOLDOUT_CLAIM_AUDIT_UNAVAILABLE`。若数据库 commit ACK 丢失，服务只允许对 command、authorization、evaluation、epoch、accepted audit 以及候选/冻结回执/run/profile/discovery/sealed 的冻结全列状态进行精确主库读回：

- 精确匹配已提交图，才返回原 bearer lease；
- pristine command 无法证实提交时，fence 为 `RECONCILING / REQUEST_HOLDOUT`，保持 0 authorization、0 evaluation、0 generation；
- 已开始的图无法证实时，fence 为 `RECONCILING / HOLDOUT_PENDING`，保留原 authority，清除 active lease；
- readback 漂移、`UNKNOWN` audit 和 fence 在同一 canonical-lock 数据库事务中完成，避免另一个进程在读回与 fence 之间领取 lease。

被 fence 为 `RECONCILING` 的 command 不能再次 claim。该合同选择“可能少执行一次并要求人工/自动对账”，而不是在提交结果未知时冒险重复揭盲。

## 3. 数据库迁移与不可变约束

迁移 `20260907_ai_research_holdout_claim` 线性承接 `20260907_ai_research_holdout_request`，增加：

- command 的 lease owner、token hash、generation、expiry、heartbeat、attempt count 与 started time；
- `QUEUED`、`RUNNING`、两类 `RECONCILING` 和终态的成组 CHECK 约束；
- evaluation 对 authorization 的唯一约束；
- 追加式 `ai_research_holdout_access_audits`；
- SQLite、PostgreSQL、MySQL/MariaDB 三种方言的 audit UPDATE/DELETE 拒绝触发器 DDL；
- 一旦已有 claim/audit 证据，downgrade 以 `HOLDOUT_CLAIM_DOWNGRADE_BLOCKED` 拒绝破坏性删证。

当前实际执行仅覆盖本地 SQLite migration/schema 合同和 PostgreSQL/MySQL DDL 生成/测试 seam；真实 PostgreSQL/MySQL upgrade、downgrade、触发器执行与跨进程竞争均为 `NOT_RUN`。

## 4. 聚焦验证与独立评审

主聚焦命令使用 6 个 xdist worker，并把每个 worker 的原生数学库线程限制为 1：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m pytest -p no:rerunfailures -q --tb=short \
  -n 6 --dist load --maxschedchunk=8 \
  tests/test_ai_research_holdout_claim.py \
  tests/test_ai_research_holdout_request.py \
  tests/test_ai_research_holdout_authorization.py \
  tests/test_ai_research_independent_evaluator.py \
  tests/test_ai_research_promotion.py \
  tests/test_ai_research_v2_api.py \
  tests/test_ai_research_v2_migration.py \
  tests/asset_research/test_migration.py::test_asset_research_revision_is_the_only_linear_head \
  tests/test_ai_research_dataset_registry.py \
  tests/test_ai_research_dataset_integrity.py \
  tests/test_ai_research_candidate_freeze_v2.py \
  tests/test_ai_research_candidate_registry.py
```

结果：**184 passed、42 warnings、48.06 秒、exit 0**。

独立规格复审与代码质量终审均为 `PASS`，限定在本地 claim/start T1 范围，未发现 P0/P1。审查后补齐的关键负例包括完整 authority graph 的 commit-ACK readback、恢复审计失败全回滚、profile/resolver 不可用时的静态恢复、跨进程 readback/fence 窗口和 attempt/generation FSM 一致性。

## 5. 六 worker 全量回归

### 5.1 首次全量失败保留为诊断证据

claim/start 实现后的第一次完整功能通道结果为：

```text
5,560 passed, 123 skipped, 1 failed, 192 warnings in 796.45s
```

JUnit：`/private/tmp/iter196-claim-full-6core.KoCJRj/backend-functional-6core.xml`；SHA-256：

```text
aade645bc9490e204e4ec2bdb7b06c02ffa385f6068ab9fef34bc15a5ba53e11
```

唯一失败为 `test_research_loop_persists_draft_when_cancelled_during_backtest_submission`。该测试在 fake 回测提交入口设置 `started`，但到达入口前会同步执行真实 multiprocessing 沙箱预检；沙箱协议允许最多 15 秒 bootstrap、3 秒执行和 5 秒 grace，而测试只等待 5 秒。6-worker 负载下，同步 `Pipe.poll` 阻塞事件循环，使 Event 与超时回调产生非确定性竞争。精确节点串行通过，同一 6-worker cancellation 组可一轮失败、一轮通过，因此判定为既有测试隔离缺陷，而不是 holdout 状态机死锁。

修复只修改该测试：保留生产 `_validate_strategy_code_draft` 的空值、安全、AST、`bt.Strategy` 继承、依赖和类完整性检查，仅 monkeypatch 本用例范围外的动态 `StrategySandbox.validate_strategy_code` spawn；同时注入已有的 fake/no-op mandate、event 和 version 服务。没有放宽生产超时或修改生产编排语义。独立审查 `PASS`、P0/P1 为 0；6-worker cancellation 定向组为 7/7 通过。

### 5.2 最终功能通道

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
PYTHONPATH=/private/tmp/iter196-final-6core.YhgaM8/pythonpath-snapshot.ITzNQN \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m pytest tests -m 'not performance' -p no:rerunfailures \
  -q --tb=short -n 6 --dist load --maxschedchunk=8 \
  --junitxml=/private/tmp/iter196-final-green-6core.hJclQn/backend-functional-after-cancel-isolation-6core.xml
```

结果：**5,561 passed、123 skipped、0 failure/error、192 warnings、818.39 秒、exit 0**。JUnit 实际为 5,684 cases，suite time 817.960 秒，SHA-256：

```text
a46356ebad9af83a5354e866251106d6dbe07337347cce7d72706708e4d8f221
```

其中 `test_ai_research_*` classname 子集为 **735/735 passed、0 skipped/failure/error**；holdout claim 文件因参数化在 JUnit 中为 33/33 passed；7 个 cancellation 场景也全部通过。

### 5.3 串行性能通道

性能测试没有用 xdist，避免 pytest-benchmark 和共享负载污染绝对时延：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
PYTHONPATH=/private/tmp/iter196-final-6core.YhgaM8/pythonpath-snapshot.ITzNQN \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m pytest tests -m performance -p no:rerunfailures -q --tb=short \
  --junitxml=/private/tmp/iter196-final-green-6core.hJclQn/backend-performance-serial-after-cancel-isolation.xml
```

结果：**18 passed、6 skipped、0 failure/error、5,684 deselected、6 warnings、14.94 秒、exit 0**。JUnit 为 24 cases，suite time 14.742 秒，SHA-256：

```text
fe1eafa9beb674730b5bb8efc3c1ea94a520c0fb425fbc3576bd091060052b62
```

功能与性能选择表达式互补，因此当前两通道并集为 **5,708 cases：5,579 passed、129 skipped、0 failure/error**。129 条 skip 继续保持原条件，不能计为 PASS。

回归前后 `app/` 与 `tests/` 下排序逐文件 SHA-256 清单摘要均为：

```text
369ed9e56080f0860ea56c887cf1ebb39b2bec97830a0873a9189f40fd432d22
```

只读 Backtrader 快照仍报告 `backtrader 1.3.0`，与项目声明 `>=1.9.78.123` 不一致；其余 Anaconda 依赖也未完整冻结，所以这是局部来源稳定的本地回归，不是干净可重建环境证明。

## 6. Claim 切片源码身份

下列 11 文件的组合 manifest SHA-256 为：

```text
a1fde1be8faaae282cb48951970c4b4f91f4ad23bb3e12b3bf204446277ddc9c
```

| SHA-256 | 文件 |
| --- | --- |
| `241e9fd37e8e91350ede9f8a987be0c6ffc2ca48a63c91fdd0c6b0bf3ad46932` | `src/backend/app/services/research/holdout_claim.py` |
| `eada2eab7f56b65a661235d5f0d222d8aa9ae9e3628b56656983779fa86e1fcd` | `src/backend/app/services/research/holdout_authorization.py` |
| `07189af22a509893bf039c7bd6959a2be7190cd85e4cf5fc24f5198b608de927` | `src/backend/app/services/research/holdout_request.py` |
| `a2f5db193a93607e60076983f0e7170e91b801f6e3f99dd288d05603e5b79f40` | `src/backend/app/models/ai_research_v2.py` |
| `2611820750044b40cbf888f4d97f84e50021f48e15b01a7fbac25ba425275736` | `src/backend/app/models/__init__.py` |
| `a82023728631164d2dc7bf09446b5653a2548cbbdd375e1dd925a7e6f249b899` | `src/backend/app/schemas/ai_research_v2.py` |
| `0cfcd5694353c6bf2a01ce33ed05a53c41e9f3b383b38bf02d83cae177ed8c89` | `src/backend/alembic/versions/20260907_ai_research_holdout_claim.py` |
| `c8a389c7d20ee79eb56115e8ad386266aeac5ab11797c439c389044fca2464d1` | `src/backend/tests/test_ai_research_holdout_claim.py` |
| `3c4203a0dce96d3c61a85ab7babe86d87a8f3897b9413706575665becc692554` | `src/backend/tests/test_ai_research_holdout_request.py` |
| `7260afddefe73a82264d60b1d265199de03c09fb8fb710abfe0e28be42daea76` | `src/backend/tests/test_ai_research_v2_migration.py` |
| `9ac9b6597ed0484712320e5295e5d5ddbb25f510e4b668481fd6fb7cacda82a3` | `src/backend/tests/asset_research/test_migration.py` |

测试隔离修复位于 `tests/test_ai_strategy_research_service.py`，不属于上述 claim 11 文件 manifest，但包含在最终 `app/tests` 清单与全量回归中。工作树尚无 Git commit/candidate seal；这些摘要也不覆盖依赖、部署配置、真实服务或前端制品。

## 7. 未运行与禁止声明

以下均为 `NOT_RUN` 或 `BLOCKED_ENVIRONMENT`：

- 真实 PostgreSQL/MySQL migration、触发器执行、锁语义和跨进程竞争；
- 独立 sealed queue、Evaluator 进程、服务身份、工作负载身份/IAM 和对象存储拒绝边界；
- 生产 Redis、多实例限流、可信代理链和实际客户端 IP；
- 真实密封数据读取、holdout 计算、结果工件、指标与终态 receipt；
- lease-fenced checkpoint/finalize、promotion 同事务收口和 evidence package 对新证据的选择；
- 真实 Provider、Docker sandbox、当前 authenticated UI/API E2E、Node 20 前端门；
- T2 真实数据、T3 前向观察/模拟审批、备份恢复、灰度与 operational rollback。

因此，本页不能支持“已完成密封评估”“候选通过留出门”“实现了真实职责分离”“依赖可重建”“可启用协议生产流量”或“迭代 196 已整体验收”等声明。

## 8. 保留 P2 与下一步

当前无 P0/P1 代码评审项，保留以下 P2：

1. `REJECTED/UNKNOWN` access audit 主要通过 `requested_command_id` 间接定位候选和 snapshot；
2. commit readback 的全列 tuple 对未来非语义/易变列较敏感，后续宜演进为版本化 authority fingerprint；
3. 初始 claim 在持锁期间执行对象 resolver 重验，真实远程 resolver 接入前需评估锁占用；
4. `repr=False` 不能阻止未来 `asdict` 或错误日志记录 bearer；应增加显式安全序列化合同；
5. legacy raw-token 兼容 API 必须继续隔离；历史 policy resolver 必须保持可用或迁移为不可变 policy snapshot；
6. 本地 runtime identity 字符串不是工作负载身份或 IAM 证明；
7. cancellation 测试的 monkeypatch 可在后续改为带调用计数的 spy；生产同步沙箱预检阻塞 event loop 是独立响应性技术债。

下一切片是 lease-fenced evidence checkpoint/finalize：由服务器构建并绑定结果工件，终态前第二次检查 lease，evaluation、13 项 gate、command、epoch、final audit 和 promotion 资格在同一权威事务中收口；崩溃恢复只能采纳已持久化 checkpoint，不能重做密封读取或重新签发授权。完成本地实现后，所有真实数据库、queue、IAM、容器和候选级验收仍须按 [ACCEPTANCE.md](ACCEPTANCE.md) 单独执行。
