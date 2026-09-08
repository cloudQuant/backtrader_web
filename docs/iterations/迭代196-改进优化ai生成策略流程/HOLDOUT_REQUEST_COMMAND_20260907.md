# Holdout Request Command 本地 T1 证据（2026-09-07）

> 判定：`LOCAL_T1_PASS`，仅覆盖 server-owned holdout request command 的本地 HTTP/数据库合同。
> 发布边界：`IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`、candidate research/promotion=`BLOCKED/NO-GO`。
> 实现工作树：`/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`
> 本页证据冻结时的迁移 head：`20260907_ai_research_holdout_request`
> 后续状态：内部 claim/start 已完成本地 T1，当前 head 为 `20260907_ai_research_holdout_claim`；见 [后续证据](HOLDOUT_CLAIM_START_20260907.md)。本页的 150 项结果仍保持其原始 request-only 范围。

## 1. 本切片交付了什么

本切片只把“请求独立留出评估”持久化为由服务器绑定的 command。客户端提交冻结候选的预期哈希和幂等键；服务器重读 owner、run、epoch、严格冻结回执、deployment capability profile 与数据政策，并从当前 owner/policy 下选择**唯一一个** `VERIFIED + SEALED_HOLDOUT` snapshot。候选为非冻结状态、绑定漂移、无合格 snapshot 或出现多个合格 snapshot 时均 fail-closed。

请求获 `202` 后的持久化真值固定为：

- command `status=QUEUED`；
- command stage 为 `REQUEST_HOLDOUT`；
- `authorization_id=NULL`；
- `evaluation_id=NULL`。

因此，本切片证明“请求意图已持久化”，不证明授权已签发、Evaluator 已领取任务或密封计算已完成。

本地合同还覆盖：

- 请求 body/OpenAPI 只允许 `expected_candidate_hash`，禁止客户端选择 snapshot、evaluator、policy 或 capability profile；
- 同 actor、同幂等键的重放返回同一 command；同一 event loop 内 20 个并发请求收敛为一个 command 和一条 `ACCEPTED` audit；
- command 与 `ACCEPTED` audit 同事务提交；确定性拒绝在权威事务回滚后以新事务写 `REJECTED` audit；提交结果无法确认或隔离写失败时写 `UNKNOWN`，不伪造拒绝或成功；
- audit 只保存 actor、候选/快照绑定、用途、稳定 reason code、request hash、trace 与结果，不保存 token、对象 URI 或 evaluation metrics；数据库触发器禁止 UPDATE/DELETE；
- capability 拒绝返回独立的 `code`、`message`、`missing_capabilities` 字段；
- 已认证请求按 actor 与远端 IP 组合执行 `30/minute` 本地限流；
- 数据对象重验失败后按精确 snapshot identity 隔离为失败状态；隔离写失败按可重试基础设施错误处理；
- COMMIT 回执丢失后只通过主库读回 command 与对应 `ACCEPTED` audit 判断结果，无法判定时返回 `HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN`。

## 2. 主验证命令与结果

工作目录：

```text
/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
```

命令：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 \
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m pytest -p no:rerunfailures -q --tb=short \
  -n 6 --dist load --maxschedchunk=8 \
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

结果：`150 passed, 40 warnings in 41.02s`，退出码 `0`。这是固定 6 worker 的 focused T1；在本页证据冻结时尚未重新执行全量后端回归。后续 claim/start 候选及全量重跑另见 [HOLDOUT_CLAIM_START_20260907.md](HOLDOUT_CLAIM_START_20260907.md)，不得倒填为本页的 request-only 证据。

## 3. 冻结的源码与测试身份

下表路径相对于实现工作树。11 个文件的组合 manifest SHA-256 为：

```text
789fb81d51ec008ee48ec08c2c75b7bcc9a50591aeb55979a61c43ce620912cb
```

| SHA-256 | 文件 |
| --- | --- |
| `ca129a55fb5712a42c2aad106535d1f60f2b8423288ce1d3e328b71ed379daa3` | `src/backend/app/services/research/holdout_request.py` |
| `a3d4947a9b73d1dc9826a1a2f205d91bfc474e324f9a254d00d161426ce75a6b` | `src/backend/app/services/research/dataset_registry.py` |
| `f2c2b4c1fbebffbf79a1d1a6892230e7f7ba8b3935e00d27a473851b66586bcb` | `src/backend/app/services/research/promotion.py` |
| `6b1d2ecac1becb0d85832feb302c33e9398cb204713dca43a4052b60e9eb77fd` | `src/backend/app/models/ai_research_v2.py` |
| `18ac3d25a5a78345d60e15dcb2789a67549987b10de7baaa5212a747ecd5251a` | `src/backend/app/models/__init__.py` |
| `752862d468275eed523e51e991888a01513a43de5d584d28a4fc36aec2f121f5` | `src/backend/app/schemas/ai_research_v2.py` |
| `3f128827ff7c4b8f7d4b214f48f8f5eaafd8a83231862d77f24496d737a155ed` | `src/backend/app/api/strategy/research.py` |
| `c6c1a00eede775e7483c69b4dc1d3a29f434ae4f8e3e7509aab7fa7d0fffb27c` | `src/backend/alembic/versions/20260907_ai_research_holdout_request.py` |
| `300c9cafbf5e1e88731fba44521485bd581320fd2154cecc3c3099a22c03c2a9` | `src/backend/tests/test_ai_research_holdout_request.py` |
| `060dc5f630e115f273d45829b5aa9ab9687943156cafa938b6ebe3042fe41581` | `src/backend/tests/test_ai_research_v2_migration.py` |
| `37b9fe93788510465d5b3b17cd2951316fb4e81019a40f0b8669240ab1625465` | `src/backend/tests/asset_research/test_migration.py` |

这些摘要只封存下一步 Evaluator claim 实现前的 11 文件范围；工作树尚无 Git commit/candidate seal，摘要也不覆盖依赖、部署配置、前端或完整仓库。

## 4. 独立评审处置

- 规格符合性第三轮复审：`PASS`，严格限定于本地 T1 command 切片。
- 代码质量终审：`PASS`，`P0=0`、`P1=0`，严格限定于本地 T1。
- 实现者的 focused 结果只作辅证；本页以独立执行的 150 项结果为主证据。
- 所有 `AC-SEAL-*`、`AC-DEP-*`、`AC-TASK-*`、`AC-AUD-*`、`AC-MIG-*` 行继续保持原 `NOT_RUN/BLOCKED`，不得依据本页改为 `PASS`。

## 5. 未运行与禁止声明

以下均为 `NOT_RUN`：

- 真实 PostgreSQL/MySQL 下的迁移与跨进程唯一竞争；
- 生产 Redis 多实例限流、可信代理链和客户端 IP 解析；
- 独立 sealed queue、Evaluator 服务身份、IAM/对象存储拒绝边界；
- 本页冻结点上的 Evaluator claim/lease、JIT authorization 签发与一次性消费；后续已有本地合同证据，但真实独立服务/IAM 仍未运行；
- 实际 holdout evaluation、密封指标生成和零回流；
- 当前源码的真实 UI/API E2E、浏览器 a11y；
- 本切片之后的全量后端回归。

所以本页不能支持“已签发留出授权”“已执行留出评估”“策略通过密封门”“具备生产隔离能力”或“迭代 196 已完成验收”等声明。

## 6. 已知 P2 与下一步

当前保留的 P2：

1. actor + IP 限流仍可能被同一 actor 更换 IP 扩大额度；
2. 请求 body 的 OpenAPI schema 由路由手工维护，存在 schema 漂移风险；
3. 数据库唯一冲突的 winner readback 目前为模拟竞争证据，不是真实多进程、多数据库竞争；
4. snapshot resolver 重验可能在持有数据库锁时进行远程 I/O；
5. snapshot quarantine 的 `integrity_checked_at` 尚需明确并验证单调更新时间合同。

下一实现切片原定为独立 Evaluator claim；其内部 claim/start、lease/fencing、JIT authorization 一次性消费和保守恢复现已完成本地实现与回归，见 [HOLDOUT_CLAIM_START_20260907.md](HOLDOUT_CLAIM_START_20260907.md)。尚未完成的是 lease-fenced checkpoint/finalize、真实独立 queue/服务身份和密封计算；真实 PostgreSQL/MySQL、Redis、对象存储/IAM 与部署拓扑中的拒绝、崩溃恢复和并发验收仍必须单独执行。
