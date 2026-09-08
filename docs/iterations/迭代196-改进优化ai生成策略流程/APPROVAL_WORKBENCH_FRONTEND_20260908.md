# 迭代 196：审批与证据工作台前端验收记录（2026-09-08）

> 结论：审批工作台的权限表达、安全投影、浏览器意图哈希、错误目录和竞态处理已通过固定 6 worker 的完整前端回归；154 个测试文件、1,556/1,556 用例通过。由于执行环境是 Node 25.1.0，超出项目声明的 `>=20 <25`，结论仅为 `LOCAL_PASS_UNSUPPORTED_RUNTIME`。Node 20 与 authenticated current UI 均未运行。

## 1. 实现范围

- 实现工作树：`/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`；
- 分支：`codex/iteration-196-ai-research-trust`；
- 基础/当前提交：`a18bcf52682686c30d919fe02d6fd734ee4271b9`；
- 核心落点：审批 composable、研究工作台审批面板、研究 workflow 类型、versioned error catalog 及严格校验脚本；
- 候选仍未提交，不能形成前端 candidate seal。

## 2. 用户可见合同

1. `can_decide` 与 `can_approve` 明确分离。`can_decide=true/can_approve=false` 时，用户可以做 `REJECTED` 或 `REQUESTED_CHANGES`，但批准动作不可用；页面不会只凭角色名称猜测批准能力。
2. 时间线、请求、决定、grant 和 evidence package 通过安全 DTO/allowlist 投影后才进入 store 与 DOM。服务端排序优先级保持为权威，前端不自行重排出另一套事实。
3. 浏览器确认意图使用与 Python `str.strip()` 对齐的精确字符集合后做规范哈希；跨端固定向量结果为 `6e023614f08ecb90f17f866031ebfbf8b8314ca08edb669d759c2cb402812099`。U+0085 会剥离，U+FEFF 保留，避免浏览器与服务端签署不同文本。
4. 安全投影会拒绝 URI scheme、用户信息、绝对/相对敏感路径、Windows drive/UNC、sealed/raw 标识及其标点或中文相邻形式；相关 canary 同时覆盖 projector、API 数据与 DOM，不把完整 manifest、存储位置或 secret-bearing 字段带入浏览器。
5. 仅三个审批 mutation API 抑制全局 Axios toast，由工作台按结构化 code 给出上下文反馈；401 仍执行原有 session 清理，普通 API 的全局错误行为不变。
6. timeline stub 与未完成状态使用显式定义，不产生 unresolved component warning 或假成功占位。

## 3. 公开错误目录

公开错误目录只有一个版本化合同：

- 版本：`ai-research-approval-errors/v1`；
- 条目：48 个排序的 `code/status/retryable` tuple；
- SHA-256：`6dd9f6ce55ec595c9441ae08e26f6cc0845549eb1c950a6a28481ad973870d53`；
- 后端 tuple 是权威；前端 JSON manifest 与 TypeScript adapter 消费同一精确集合；
- strict verifier 扫描并比较 backend/frontend 版本、内容和摘要，不能靠手写两个不同 allowlist 通过；
- 隔离的 frontend Docker 只能显式运行 `pinned-only`，输出必须包含 `backend comparison NOT_RUN`，不能把未挂载后端源码伪装成跨仓一致性验证。

真实响应优先使用 `details.code`，legacy `detail` 只作兼容。内部、冲突或未知 code 统一显示通用 `RESEARCH_APPROVAL_OPERATION_FAILED`；只有 `APPROVAL_CHALLENGE_INCOMPLETE:<fields>` 按协议归一为目录中的基础 code。

## 4. 固定 6 worker 证据

```bash
npm test -- --run --minWorkers=6 --maxWorkers=6 \
  --reporter=basic --reporter=json \
  --outputFile.json=/private/tmp/iter196-final-20260908.YoXAyt/frontend-vitest-6core-final.json
```

| 检查 | 结果 |
| --- | --- |
| Vitest | 154 test files、1,556/1,556 passed、19.29 秒 |
| JSON SHA-256 | `86c6380a7c12650d89641a556afbab9198fb46602b7b7f4f38496e1b18b1467b` |
| Typecheck | PASS |
| Strict catalog verifier | 48 entries、version/hash 精确匹配，PASS |
| Build | 4,091 modules、22.67 秒，PASS |
| Scoped ESLint/node check | PASS |
| 独立前端终审 | P0/P1/P2 = 0；8 files、300/300 focused tests passed（4.17秒），typecheck与scoped ESLint通过；strict精确比较通过，pinned-only明确声明backend comparison NOT_RUN，strict缺权威时按预期失败 |

JSON 报告位于 `/private/tmp`，只用于本轮校验，不是持久发布工件。

## 5. 来源摘要与运行时边界

- 扩展候选摘要：`c9ac863c38d719c3e38e08ae16368dce0d8afc8ae061104b3c06cbf505540d0a`，覆盖 `src/e2e/scripts` 中 `ts/vue/css/json/mjs`、`package.json` 和两个 Dockerfile；
- 窄摘要：`37b83be5aa413062505ad230a6f1a25f81aff23a06c2ae6ea3600fd937009378`，仅覆盖 `src/e2e/scripts` 的同类前端文件；
- 运行时：Node `v25.1.0`、npm `11.6.2`；项目 engines 为 `>=20 <25`；
- 判定：`LOCAL_PASS_UNSUPPORTED_RUNTIME`；受支持 Node 20 lane 为 `NOT_RUN`。

## 6. 未运行与最终判定

- authenticated current UI、真实 FastAPI/当前 head/真实数据库的审批旅程：`NOT_RUN`；
- 屏幕阅读器、人工焦点与生产身份权限验证：`NOT_RUN`；
- 真实对象存储/IAM、queue/Evaluator/Provider、T2/T3：`NOT_RUN/BLOCKED_ENVIRONMENT`；
- Node 20、干净 install/build、已提交 candidate seal：`NOT_RUN/NO-GO`。

本地前端组件与合同可以判定为通过，但不能外推为当前部署或发布验收。总体仍为 `IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`。
