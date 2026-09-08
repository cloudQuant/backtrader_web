# 迭代 196：隔离 HTTP 与真实 UI 协议 v2 验收证据（2026-09-05）

> 结论：**实际 FastAPI、一次性 PostgreSQL 17.7、候选 Vite 前端与 headless Chromium 上的协议 v2 契约通过，证据等级为 T1。**
>
> 其中包含无 API fixture 的 headless 浏览器 E2E，但不是人工辅助技术验证、真实数据/Provider、阶段执行器或隔离容器验收，不能改变 T2/T3、`IMPLEMENTATION_ACCEPTED` 与生产启用的 `NO-GO` 判定。
>
> **后续状态注记（同日）**：本文件记录的真实 HTTP/UI 运行早于 opaque object receipt、dataset identity 与 typed `GENERATE` materialization 的最后一轮变更。它仍是当时版本的有效历史 T1 证据，但不能替代当前新 API/UI 合同的 fresh HTTP 验收；当前版本仅有对应的本地 156 项 v2 契约，重新创建隔离数据库与浏览器环境后才可更新本页为当前证据。

## 1. 受控执行范围

- 使用一次性 PostgreSQL 17.7 验收库和工作树中的实际 FastAPI 应用进程；HTTP 服务只绑定本机回环地址与临时端口。
- 正向协议合同仅在该临时进程中开启 `AI_RESEARCH_PROTOCOL_V2_ENABLED`；另在独立的一次性 PostgreSQL/实际 FastAPI 进程中保持该 flag 默认 `false`，验证已认证写入口失败关闭。两次进程中的研究 task runner、调度器和 RAG 均保持关闭。
- 服务端预置的 `dev-single-process` capability profile 不包含 sandbox 或 sealed-evaluation 能力。测试因此只验证协议受理、持久化、权限与 fail-closed 边界，不启动执行器。
- 真实 UI 链路使用同一工作树的 Vite 候选前端，经本地反向代理连接候选 FastAPI；headless Chromium 以实际注册/登录测试用户的会话访问 `/investment/strategies`。所有 v2 请求均到达后端，未使用 Playwright route fixture 或响应伪造。
- 未读取生产数据、Provider 凭据、用户密钥或受控真实数据；测试身份和数据库仅用于本次验收。

## 2. 实际 HTTP 契约结果

| 检查 | 结果 |
| --- | --- |
| OpenAPI 路由发现 | `GET /openapi.json` 返回 `AI for Investor API`，并包含 `/api/v1/strategy/ai-research/v2/hypotheses`。 |
| 认证和身份边界 | 两个独立测试用户经实际注册/登录接口取得会话；第二个用户读取第一个用户的 run 返回 `404`。 |
| 默认关闭 | 在独立的默认配置进程中，已认证用户 `POST /api/v1/strategy/ai-research/v2/hypotheses` 返回 `409` 和稳定消息 `AI_RESEARCH_PROTOCOL_V2_DISABLED`。 |
| 真实候选 UI/API | `e2e/a11y/trusted_ai_research.real.spec.ts` 在真实 `/investment/strategies` 页面完成实际认证会话、草稿、确认、dataset、epoch、`PASS` precheck、run 提交与 workbench 读取；对应 v2 响应依次为 `201/200/201/201/201/201/200`。 |
| 真实候选 UI 可访问性 | 对提交后的 `trusted-research-workbench` 运行 axe，`critical`/`serious` 为 0；没有在浏览器页面或真实 v2 响应中发现 `controlled://`。 |
| 预注册流程 | 依次完成 hypothesis 草稿创建、显式确认和 experiment epoch 创建。 |
| family 身份 | 含客户端 `family_hash` 的 epoch 请求返回 `422`；合法请求由服务端返回 64 位十六进制 family hash。 |
| 数据与预检 | 创建 snapshot 后，数据预检返回 `PASS`；客户端响应和 workbench 摘要均未包含受控 `storage_uri`。 |
| 幂等启动 | 使用相同 `Idempotency-Key` 连续提交两次 run，返回同一个 run 和同一个 task。 |
| 工作台摘要 | workbench 返回 `PROTOCOL_V2_PENDING`，并保持受控 URI 脱敏。 |
| 未越权执行 | 可重复的真实 UI 验收库在清理前回读为 1 个 `QUEUED` run、1 个 `QUEUED` task、1 个 data precheck、0 个 model invocation、0 个 stage attempt；没有启动 Provider 或执行器。 |

## 3. 边界与未覆盖项

该结果补强了“fixture 静态浏览器测试”之外的真实后端 HTTP/数据库与 headless UI 证据，但不覆盖：

1. 解锁设备上的人工焦点检查、屏幕阅读器和其他辅助技术验证；
2. 真实 Provider、批准数据 snapshot、模型输出或可投资研究结果；
3. 独立 worker、queue、对象存储凭据、真实阶段执行器和多服务隔离；
4. 容器断网、资源限额、进程清理、冷重放、前向观察、staging 审批或 rollback drill。

因此，本页只能支持 [ACCEPTANCE.md](ACCEPTANCE.md) 所定义的本地 T1 协议结论。完整的环境门禁仍见 [LOCAL_T1_TRACEABILITY_20260905.md](LOCAL_T1_TRACEABILITY_20260905.md) 与 [ACCEPTANCE_REPORT_20260905.md](ACCEPTANCE_REPORT_20260905.md)。

## 4. 可重复的真实 UI/API 验收

验收用例位于候选前端工作树的 `e2e/a11y/trusted_ai_research.real.spec.ts`，默认跳过，只有明确设置 `RUN_REAL_AI_RESEARCH_E2E=1` 才会执行。它不依赖静态 preview 的 API fixture。

运行前必须由验收环境所有者完成：一次性数据库迁移、有效但不具 sandbox/sealed 权限的 `dev-single-process/v1` capability profile、v2 feature flag 开启且 worker/provider/scheduler 关闭的候选 FastAPI，以及经本地代理指向该 API 的候选 Vite 前端。实际复跑命令为：

```bash
RUN_REAL_AI_RESEARCH_E2E=1 \
REAL_AI_RESEARCH_API_BASE=http://127.0.0.1:18096/api/v1 \
BASE_URL=http://127.0.0.1:18098 \
npx playwright test -c playwright.a11y.config.ts \
  e2e/a11y/trusted_ai_research.real.spec.ts --project=chromium
```

先前基线复跑为 `1 passed (7.7s)`；本次最终代码复验为 `1 passed (5.5s)`，详见第 6 节。这是受控本地 T1，不能在没有显式环境所有权、临时数据库和清理计划时指向共享或生产服务。

## 5. 清理证明

验收结束后已停止全部临时 FastAPI 与候选 Vite 前端，并在确认没有活动连接后删除对应的一次性 PostgreSQL 验收库。没有修改正在运行的 `localhost:3000`/`localhost:8000` 应用，也没有保留测试运行、任务或数据库作为长期状态。

## 6. 最终代码隔离复验（2026-09-05）

为覆盖本轮最后加入的 governance 响应脱敏，重新创建了独立的 PostgreSQL 17.7 验收库 `btw_i196_e2e_20260905_2`，执行 `alembic upgrade head` 后启动候选 FastAPI 和候选 Vite，均只绑定 `127.0.0.1` 的临时端口。研究 task runner、schedule、outcome evaluator、Provider、RAG 均显式关闭。

首次真实浏览器运行按设计返回 `BLOCKED_TOPOLOGY_CAPABILITY:profile_not_found,protocol_v2`：空验收库尚未注册服务端 capability profile。这是 fail-closed 前置条件，不是把浏览器默认值当作 profile 的回退。随后仅在该一次性库注册了有时限的 `dev-single-process/v1` 测试画像：Explorer/Evaluator 均为共享身份，且 queue、storage、network、sandbox 均为 `false`，所以它只能声明 `protocol_v2`，不能声明 sandbox、sealed evaluation 或职责分离。

在该画像下，以下最终代码结果成立：

| 检查 | 新鲜结果 |
| --- | --- |
| 候选 UI/API Chromium | `RUN_REAL_AI_RESEARCH_E2E=1` 的无 fixture 用例 `1 passed (5.5s)`；完成 draft → confirm → dataset → epoch → `PASS` precheck → run → workbench，axe `critical`/`serious` 为 0。 |
| 已启用 v2 的实际 HTTP governance | 临时打开仅 `NFR-PERF-001` 的 server allowlist 后，创建偏差返回 `201`；`authorization=Bearer ...` 的理由和 `token=...` 的补偿控制均返回 `[REDACTED]`，撤销返回 `200` 且原始状态仍为 `BLOCKED`。 |
| 默认关闭的实际 HTTP | 另一个候选 FastAPI 进程保持 `AI_RESEARCH_PROTOCOL_V2_ENABLED=false`，已认证 hypothesis 写入返回 `409 AI_RESEARCH_PROTOCOL_V2_DISABLED`。 |
| 未越权执行回读 | 清理前为 1 个 run、1 个 task、2 个 precheck（一次缺 profile 的 `BLOCKED` 加一次 `PASS`）、1 个 governance decision、0 个 model invocation、0 个 stage attempt。 |

浏览器加载期间曾观察到既有 `/api/v1/data/trust/precheck` 背景请求在空 PostgreSQL 库中返回 `503`：`asset_specs` 的 `TIMESTAMP WITHOUT TIME ZONE` 列接收了 timezone-aware 默认值。该问题不属于 v2 请求链，却会影响同页的 legacy trust 提示；随后已以项目既有 `utc_now_naive()` 统一四个相关模型的默认值，并在新的独立 PostgreSQL 库和实际认证 HTTP 请求上复验为 `200/failed`（缺覆盖数据的正确业务结论）。这仍不把本页扩展宣称为整个 legacy data-trust 子系统或 T2/T3 的完整验收。

复验后已停止两次候选 FastAPI 和候选 Vite，确认临时端口无监听、验收库无连接后删除该库；`btw_i196_e2e_20260905_2` 不存在于本机 PostgreSQL catalog。
