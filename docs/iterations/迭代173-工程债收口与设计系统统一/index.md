# 迭代 173 - 工程债收口与设计系统统一

> **文档状态**: 计划（草案 v1，待评审）
> **创建日期**: 2026-05-27
> **前置基线**:
> - 迭代 169 已完成切片棘轮、性能基线与 v0.2.0 RC，但 `REFACTORING_BACKLOG.md` 中多项 P0/P1 工程债延期至本轮收口
> - 迭代 170/171 已完成 FinceptTerminal MVP 与产品化深化；broker 边界已固化在 `bt_api_py / bt_api_xx`
> - 迭代 172 已完成首批 14 个 `bt_api_xx` 券商扩展包独立落地，`backtrader_web` 保持 consumer-only 边界
> - v0.2.0-rc1 已发版（2026-05-24），CHANGELOG `Known Boundaries` 仍挂账 AI 可观测性、多模型路由、VaR/CVaR/因子/归因/市场状态前端落地、回测链路 60% 降耗
> **核心目标**:
> 把 169/171 留下、并在 170-172 期间持续累积的工程债与产品化债，沿“安全配置 + 大文件切片 + 设计系统统一 + 性能与可观测性补完 + 迭代流程收口”五个维度做一次性收口，让 v0.2.0 从 RC 走到可发布 GA 的临界点。

---

## 0. 立项背景

### 0.1 当前可观察到的债

本轮立项不是基于主观感受，而是基于以下文档证据：

| 维度 | 证据 | 当前数字 |
|---|---|---|
| 安全配置 | `docs/REFACTORING_BACKLOG.md` P0-1 / P0-2 | `DEBUG=True`、`HOST=0.0.0.0` 默认；与 `.env.example` 文档化期望相反 |
| 后端大文件 | `wc -l src/backend/app/services/*.py` | `sync_service.py` 3091、`manual_gateway_service.py` 2037、`workspace_service.py` 1376、`quote_service.py` 1260 |
| 异步/阻塞混用 | `REFACTORING_BACKLOG.md` P1-4 | `manual_gateway_service.py` 内 `time.sleep / subprocess.run / urlopen` 出现在 async 路径 |
| 前端大视图 | `wc -l src/frontend/src/views/*.vue` | `KnowledgeBasePage.vue` 1777、`AIChatPage.vue` 1505、`GatewayStatusPage.vue` 1357、`QuotePage.vue` 1182 |
| 设计系统 | `docs/UI_CONSISTENCY_AUDIT.md` 2026-05-20 | 3 套独立颜色体系冲突；`AIChatPage` 主操作 `#0f766e` 与全站品牌色 `#3b82f6` 不一致；硬编码颜色 ≥75 处 |
| AI 可观测性 | `CHANGELOG.md [0.2.0-rc1] Known Boundaries` | 多模型路由、AI 调用结构化日志、Prompt 治理后半段未上 |
| 量化能力前端入口 | 同上 | 168 已完成的 VaR/CVaR、因子库、绩效归因、市场状态在前端无入口 |
| 性能目标 | `docs/perf-baseline-v0.2.0.md` | 5 策略状态轮询 Mean 102.1ms；目标“相同环境降 60%” 未启动 |
| 覆盖率 | `src/frontend/package.json` | 前端阈值 lines 34% / functions 40% / branches 45%；目标 60-70% |
| 静态分析 | `src/backend/pyproject.toml` | B904 仍被关；mypy 未 CI 闸 |
| 迭代流程 | `docs/iterations/README.md` | 迭代 146–150 仍标“进行中”，实际已被 162+ 系列接续，存在 zombie 状态 |
| 上轮残项 | `docs/iterations/迭代171-.../index.md` T2/T7/T10 | broker 边界二轮收口、`WS_GATEWAY_MIGRATION.md` 撰写、quant tools registry 真实 handler 三项未关 |

### 0.2 为什么是“一次性收口”

- 169 之后又过了 3 轮重产品的迭代（170/171/172），工程债不会因为继续叠产品功能而消失，反而每一轮都在被绕过。
- v0.2.0-rc1 已发版，距离 GA 只差“清理 Known Boundaries + 把 release-blocking 风险压到底”。
- 设计系统不统一会让 173 之后任何前端工作都付双倍价（每个新页面都得选一次颜色方案）。继续推后只会加重。
- 146–150 的“进行中”状态会让外部读者误判项目治理水平，影响 v0.2.0 GA 的对外可信度。

因此本轮的定位不是“做新功能”，而是“为 GA 收紧地基、为后续迭代清场”。

---

## 1. 范围定义

### 1.1 范围结构

本迭代采用「三主线 + 一流程线」结构：

```
迭代 173
├── 主线 A · 安全配置 + 大文件切片收口
├── 主线 B · 设计系统统一
├── 主线 C · 性能与 AI 可观测性补完
└── 流程线 D · 迭代状态整理
```

三主线相互独立，可并行推进；流程线 D 是轻量收口，第一周完成。

### 1.2 明确不在本迭代范围

为防止范围漂移，以下事项**明确排除**：

- ❌ 不接受新功能 PRD；任何新需求一律记到 174+
- ❌ 不在 `backtrader_web` 内新增 broker 适配（172 已固化边界，新 broker 走 `bt_api_xx`）
- ❌ 不做 FinceptTerminal 新批迁移；171 残项 T2/T7/T10 走独立线 173B，**不并入本计划**
- ❌ 不做数据库 schema 大改；如必须改，单独 RFC，不挂 173
- ❌ 不重做整站视觉重构；本迭代只做“颜色 token 单一来源化 + 关键大视图拆分 + 文档化设计契约”，不动信息架构
- ❌ 不引入新的语言/框架/构建工具
- ❌ 不做 Docker Hub 发版自动化升级（rc1 已具备最小通路）

---

## 2. 主线 A · 安全配置 + 大文件切片收口

### 2.1 任务卡

| ID | 任务 | 文件 | 验证方式 | 工作量 |
|---|---|---|---|---|
| A1 | 翻转 `DEBUG` 默认 `True → False` | `src/backend/app/config.py` | `tests/test_config_validation.py::test_debug_default_*` 更新；新增 explicit-true honor 用例 | S |
| A2 | 翻转 `HOST` 默认 `0.0.0.0 → 127.0.0.1` | `src/backend/app/config.py` | docker-compose dev/prod 显式设 `HOST=0.0.0.0`；启动脚本自动注入 | S |
| A3 | `manual_gateway` 切片 1：抽 `manual_gateway/utils.py` | 新建 `src/backend/app/services/manual_gateway/utils.py`；保留原模块为门面 | 纯函数迁移 + 单元测试（port discovery / env autodetect / error parsing） | M |
| A4 | `manual_gateway` 切片 2：阻塞 I/O 收边 | 在 async handler 用 `asyncio.to_thread` 包裹 `time.sleep / subprocess.run / urlopen` 调用点 | 异步性能基线（API p95 不退化） | M |
| A5 | `workspace_service` 切片 1：`workspace/_helpers.py` | 按 backlog Slice 1 抽 14 个静态方法 + 保留薄 `@staticmethod` shim | 现有 `test_workspace_service.py` 全绿不改 | M |
| A6 | `workspace_service` 切片 2：`workspace/lifecycle.py` | 抽 `create/get/list/update/delete_workspace` + `_normalize_workspace_*` + `_workspace_to_response` | API 集成测试不变 | M |
| A7 | `sync_service` 切片 1：抽 `sync/progress.py` | 进度/状态报告独立化 | 新增 progress 单测 ≥6 用例 | M |
| A8 | `quote_service` runtime 切片 | 抽 `quote/runtime.py`（gateway/receiver lifecycle）+ `quote/symbols.py`（normalization） | 现有 quote 测试不动 + 新增 runtime 单测 | M |
| A9 | 重启 B904 ruff 规则 | `src/backend/pyproject.toml` `[tool.ruff.lint] ignore` 去掉 B904 | `ruff check --select B904 .` 0 错误；按服务批改 | M（机械） |
| A10 | mypy ratchet 扩盘 | 按 backlog item 12，从 `app/utils app/schemas` 扩至 `app/api` | CI 新增 mypy job，失败阻塞 | S+M |

### 2.2 与 backlog 的映射 / 差距

- backlog P0-1/P0-2 = A1/A2（**全部消化**）
- backlog P1-4 manual_gateway 4 切片 = A3/A4（**消化前 2 切片**；切片 3 split-by-family、切片 4 psutil 替 lsof 留 174）
- backlog P1-5 sync_service 4 切片 = A7（**消化切片 1**；schema_diff / transport adapter 留 174）
- backlog P1-6 workspace_service 5 切片 = A5/A6（**消化切片 1/2**；slices 3/4/5 留 174）
- backlog P1-13 quote_service 4 切片 = A8（**消化切片 1/2**；façade & 测试增强 留 174）
- backlog P2-8 B904 = A9（**全部消化**）
- backlog P2-12 mypy = A10（**消化首阶段**）

### 2.3 验收 DoD

- 所有切片不破坏现有 API；测试套件全绿
- 4 个 P1 大文件至少各下降 25% 行数（sync 目标 ≤2300、manual_gateway ≤1500、workspace ≤1000、quote ≤950）
- B904 规则启用后无新增违例
- mypy 在 `app/api + app/utils + app/schemas` 域内 0 错误，CI 阻塞

---

## 3. 主线 B · 设计系统统一

### 3.1 任务卡

| ID | 任务 | 文件 | 验证 | 工作量 |
|---|---|---|---|---|
| B1 | 颜色 token 单一来源化 | `src/frontend/tailwind.config.js` 作为 SSOT；构建脚本生成 `style.css` CSS 变量；移除 `theme.ts` 中重复定义 | 视觉回归 1 个基线截图；color-tokens 单测 | M |
| B2 | 拆 `AIChatPage.vue` | 新建：`components/ai-chat/MessageStream.vue` / `InputBar.vue` / `DiagnosticsPanel.vue`；抽 `composables/useAIChatStream.ts` | 单文件 ≤500 行；硬编码颜色 → 0 | L |
| B3 | 拆 `KnowledgeBasePage.vue` | 新建：`components/kb/KBDocumentList.vue` / `KBRetrievalConfig.vue` / `KBChatPanel.vue` | 单文件 ≤500 行 | L |
| B4 | 暗色模式契约 | 在 `tailwind.config.js` `darkMode: 'class'` 下定义 `dark:` token 矩阵；至少首页+AIChat+Quote+KB 视觉回归基线 | 截图回归测试通过 | M |
| B5 | 写 `docs/DESIGN_SYSTEM.md` v0.1 | 颜色/间距/字号/按钮/卡片/暗色 6 大节；引用 token 而非硬编码值 | tech-writer 风格审核 | S |
| B6 | 全站硬编码颜色清理 | grep `#[0-9a-fA-F]{6}` 在 `*.vue` 中的命中数 → ≤10（仅允许图表色板/品牌资产） | CI lint gate 可选 | M |

### 3.2 与 UI 审计的映射

- 审计「3 套颜色体系冲突」 → B1 + B6 全部消化
- 审计「AIChatPage 主色 `#0f766e` 偏离」 → B1 + B2 全部消化
- 审计「暗色模式碎片化」 → B4 全部消化
- 审计「硬编码 60+」 → B2 + B6 全部消化
- 审计「按钮尺寸/字体不统一」 → B5 输出规范；具体页面收敛留 174

### 3.3 验收 DoD

- `grep -RE '#[0-9a-fA-F]{6}' src/frontend/src --include='*.vue' | wc -l` ≤ 10
- `AIChatPage.vue` ≤ 500 行；`KnowledgeBasePage.vue` ≤ 500 行
- 暗色模式在 4 个基线页面通过视觉回归（pixel diff < 1%）
- `docs/DESIGN_SYSTEM.md` v0.1 已发布并在 `docs/INDEX.md` 索引

---

## 4. 主线 C · 性能与 AI 可观测性补完

### 4.1 任务卡

| ID | 任务 | 文件 | 验证 | 工作量 |
|---|---|---|---|---|
| C1 | 回测任务状态轮询热点分析 + 优化 | `app/services/backtest_service.py` + `app/api/backtests.py`；按 perf-baseline 指明的 102.1ms 链路 profile | `tests/perf/test_backtest_throughput.py::test_5_strategy_status_poll` Mean p95 ≤ 40ms | M |
| C2 | AI 调用结构化日志 sink | 新建 `app/services/ai/observability.py`；JSON-lines 落 `runtime/ai-trace/`；可选 OTLP exporter | 单测覆盖 log shape；CHANGELOG `[Unreleased]` 记录 | M |
| C3 | 多模型路由门面 | `app/services/ai/router.py`：基于 task-type + cost 路由到 Sonnet/Haiku/Opus；fallback 链 | 单测覆盖路由决策矩阵；接入 1 个真实 endpoint | M |
| C4 | 量化能力前端入口落地 | 把 168 已完成的 VaR/CVaR、因子库、绩效归因、市场状态接到工作区视图 | 4 个能力各有 1 个 e2e smoke + 文档截图 | L |
| C5 | 前端覆盖率阈值棘轮 | `src/frontend/vitest.config.ts` lines 34→45 / functions 40→50 / branches 45→55 | CI 阻塞 | S |
| C6 | AI 成本看板最小入口 | 复用 C2 落盘数据；前端 `views/ai/CostDashboardPage.vue` 一页，按 model × day 聚合 | e2e smoke 通过 | M |

### 4.2 与 v0.2.x Known Boundaries 的映射

- AI observability → C2（**消化**）
- multi-model routing → C3（**消化 MVP**；advanced routing 留 174）
- Prompt 治理 → 不在本轮（167 已完成 80%，剩余推到 174）
- VaR/CVaR + 因子 + 归因 + 市场状态前端入口 → C4（**消化**）
- 回测链路 60% 降耗 → C1（**部分消化**，目标 ~60% reduction 102→40ms）
- Docker Hub 发版 → 不在本轮

### 4.3 验收 DoD

- 5 策略状态轮询 Mean p95 ≤ 40ms（相对 baseline 减少 ≥60%）
- AI 调用日志在 `runtime/ai-trace/` 可见；至少覆盖 KB Chat / Strategy Copilot 两条路径
- 多模型路由有 ≥2 个 model adapter；fallback 链至少 1 个端到端测试通过
- 前端覆盖率三档阈值均上抬，CI 红线
- `CostDashboardPage` 可访问且渲染当日数据（mock 也算）

---

## 5. 流程线 D · 迭代状态整理

### 5.1 任务卡

| ID | 任务 | 工作量 |
|---|---|---|
| D1 | 把 `iterations/README.md` 中 146–150「进行中」逐项审计：要么补一行收口结论（哪一次迭代接续了它），要么归档到 `iterations/archived/` | S |
| D2 | 把迭代 171 残项 T2/T7/T10 单独拆出现状摘要 → 决定走 173B（独立计划文档），**不并入本 173** | S |
| D3 | 更新 `iterations/README.md`：新增 173 行；统一 162 文件名（当前是裸目录 `迭代162/`，与其他命名不一致）；archived 段汇总 | S |
| D4 | 在 `docs/REFACTORING_BACKLOG.md` 中把本轮已落项打勾删除（不留绿勾，按约定直接删条目） | S |

### 5.2 验收 DoD

- `iterations/README.md` 中无 zombie「进行中」
- 173B 计划文档存在（即使只是 1 页摘要也算）
- backlog 中 A1/A2/A3/A4/A5/A6/A7/A8/A9/A10 对应条目已删

---

## 6. 全局验收门 / SLO

| 维度 | 量化指标 | 测量方法 |
|---|---|---|
| 安全 | 新克隆 + 默认 `.env` 启动 → 默认 `DEBUG=false / HOST=127.0.0.1` | 黑盒启动脚本 |
| 工程债 | 4 个 P1 大文件各下降 ≥25% 行数 | `wc -l` 对比基线 |
| 设计系统 | `.vue` 中硬编码十六进制颜色 ≤10 | `grep -RE '#[0-9a-fA-F]{6}' src/frontend/src --include='*.vue' \| wc -l` |
| 性能 | 5 策略状态轮询 Mean p95 ≤40ms | `pytest tests/perf/test_backtest_throughput.py -k status_poll --benchmark-only` |
| 覆盖率 | 前端 lines ≥45% / functions ≥50% / branches ≥55% | `npm run test -- --run --coverage` |
| 静态分析 | B904 ruff 启用且零违例；mypy 在 api/utils/schemas 域零错误 | `ruff check --select B904 .` & `mypy app/api app/utils app/schemas` |
| 流程 | iterations README 无「进行中」（除当前 173 自身） | grep |
| AI 可观测性 | KB Chat 与 Strategy Copilot 路径产生结构化日志 | tail `runtime/ai-trace/*.jsonl` |
| 量化能力入口 | VaR/CVaR/因子/归因/市场状态在工作区均可访问 | e2e smoke 4 用例 |

---

## 7. 推荐切片顺序（4 周）

> 切片原则：**先安全 → 先收口流程 → 再切大文件 → 最后做前端拆分与新增可观测性**。
> 每周末做一次 retro，调整切片顺序而不是范围。

### 第 1 周 · 安全 & 流程清场
- D1 + D3 + D2（流程清场）
- A1（DEBUG 默认）
- A2（HOST 默认）
- A5（workspace helpers）
- B1（color token SSOT，先不动具体页面）
- C1 分析阶段（profile + 报告，不动代码）

### 第 2 周 · 大文件切片 + 性能优化
- A6（workspace lifecycle）
- A3（manual_gateway utils）
- A7（sync progress）
- B2（AIChatPage 拆分前 50%）
- C1 实施阶段
- C2（AI observability sink）

### 第 3 周 · 后端收紧 + 前端深化
- A4（manual_gateway 异步收边）
- A8（quote runtime/symbols）
- A9（B904）
- B3（KnowledgeBasePage 拆分）
- C3（多模型路由 MVP）
- C5（前端覆盖率棘轮）

### 第 4 周 · 设计系统终稿 + 可观测性闭环 + 回归
- A10（mypy 扩盘）
- B4（暗色模式契约）
- B5（DESIGN_SYSTEM.md v0.1）
- B6（硬编码颜色清理）
- C4（量化能力前端入口 4 项）
- C6（AI 成本看板）
- D4（backlog 删条目）
- 全量回归 + 验收门检查

---

## 8. 风险与降级路径

| 风险 | 概率 | 影响 | 降级路径 |
|---|---|---|---|
| `manual_gateway` 切片影响实盘下单链路 | 中 | 高 | A3/A4 一律走 feature branch；要求至少 1 轮真人 paper-trading 验证后才合 main |
| 颜色 token SSOT 引入构建链路依赖（postcss/tailwind 互操作） | 中 | 中 | B1 在 PR 中提供 fallback：构建失败回退到双源临时共存，保 PR 不阻塞前端开发 |
| `AIChatPage` 拆分破坏现有对话流状态机 | 中 | 高 | B2 前先补 e2e smoke（消息发送/中断/错误/复制）作为安全网；拆分以 commit-by-commit + 等量替换推进 |
| 多模型路由 C3 触碰 API 计费 | 低 | 中 | 默认 dry-run（仅 mock provider）；真实 endpoint 接入做 daily cost cap |
| 性能优化 C1 触及 backtest_service 共享状态 | 中 | 高 | 优化前补一组并发轮询压测；优化后对比 p50/p95/p99，超基线 +20% 回滚 |
| 工作量评估偏乐观，4 周做不完 | 中 | 中 | 第 3 周末做 mid-iteration checkpoint；优先牺牲 B6（颜色清理）和 C6（成本看板）→ 推 174 |
| 团队同时改大文件冲突 | 中 | 低 | 按 A 系列 ID 顺序 serialize；同一文件每天最多 1 个开发者 |

---

## 9. 后续接续（174 候选）

本迭代收口后会留下的下一批债，明确登记为 174 候选，**不在 173 内做**：

- `manual_gateway` 切片 3（按 broker 家族分文件）+ 切片 4（psutil 替换 lsof）
- `sync_service` 切片 2/3/4（transport adapter / schema_diff / 进一步分层）
- `workspace_service` 切片 3/4/5（units / runtime / optimization）
- `quote_service` 切片 3/4（façade 收薄 + 测试增强）
- 173B：FinceptTerminal T2/T7/T10 收口（broker 二轮 / WS gateway migration doc / quant tools handler 真实化）
- AI Prompt 治理后半段（167 残项）
- Docker Hub 发版自动化升级
- 整站按钮 / 字号规范执行（B5 输出规范，174 落地具体页面）
- 前端覆盖率二级棘轮（45 → 60）

---

## 10. 输入文档索引

阅读本计划时建议交叉参考：

- `docs/REFACTORING_BACKLOG.md` — 工程债总账
- `docs/UI_CONSISTENCY_AUDIT.md` — UI 一致性审查（2026-05-20）
- `docs/perf-baseline-v0.2.0.md` — 性能基线
- `CHANGELOG.md` — v0.2.0-rc1 Known Boundaries
- `docs/iterations/迭代169-工程债务接续与基础设施收尾/`（如存在）— 上一轮工程债基线
- `docs/iterations/迭代170-FinceptTerminal能力迁移与数据治理实盘接口升级/`
- `docs/iterations/迭代171-FinceptTerminal迁移深化与产品化收口/`
- `docs/iterations/迭代172-bt_api_xx首批14个券商扩展包落地/`
- `docs/IMPROVEMENT_ROADMAP.md` — 产品/工程/社区三维度路线图
- `docs/STRATEGIC_ROADMAP.md` — 四阶段战略

---

## 11. 评审清单（提交合并前）

- [ ] 范围 1.2 中的“不做”项是否仍然成立，未被悄悄越界？
- [ ] 全局 SLO（第 6 节）每一行是否都有可执行的测量命令？
- [ ] 风险表第 8 节是否覆盖了每一条主线的最大风险？
- [ ] 第 7 节切片顺序是否与 `git log` 上的实际开发节奏匹配？
- [ ] backlog 中本轮承诺消化的条目，是否已映射到 A 系列任务卡？
- [ ] 174 候选清单是否清晰，避免下轮再次返工讨论“到底该不该做”？
