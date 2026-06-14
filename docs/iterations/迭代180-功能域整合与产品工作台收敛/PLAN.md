# 迭代 180 - 功能域整合与产品工作台收敛计划

> **创建日期**: 2026-06-13
> **性质**: 产品架构 / 信息架构 / 工作流整合，不删除现有功能
> **前置基线**: 迭代 166-179 已陆续完成 AI 可信度、AI 工程化、量化研究能力、FinceptTerminal 能力迁移、券商扩展、设计系统、质量门禁与安全治理
> **核心目标**: 在保留当前所有功能和 API 兼容性的前提下，把平台从“功能入口集合”收敛为“数据、研究、交易、组合、AI、平台治理”六个清晰产品域，并用端到端工作流串联已有能力。

---

## 0. 一句话目标

把 Backtrader Web 现有的策略、数据、回测、优化、模拟/实盘、组合、AI、知识库、网关、数据治理、金融终端能力整合成稳定的信息架构和工作台体验：**不砍功能，不改业务边界，先建立权威能力地图、统一导航入口、兼容路由和跨域工作流**。

---

## 1. 当前问题判断

当前项目不是“功能不够”，而是“功能已经很多，但用户入口和产品心智混杂”。从本轮代码与文档核查看，主要表现如下：

| 观察点 | 现状证据 | 问题 |
| --- | --- | --- |
| 一级导航过多 | `src/frontend/src/components/common/AppLayout.vue` 中暴露 `AI助手 / 数据管理 / 行情报价 / 策略研究 / 策略交易 / 策略管理 / 组合管理 / Broker配置 / 组合账本 / 权益研究 / 新闻情报 / 期权链 / 条件扫描 / 量化工具 / 账户管理 / 知识库 / 设置` 等入口 | 入口像功能清单，不像工作台；新用户很难判断“下一步去哪” |
| 路由别名和历史入口叠加 | `src/frontend/src/router/index.ts` 同时保留 `/backtest`、`/workspace`、`/trading`、`/simulate`、`/live-trading`、`/gateways` 等 | 同一业务链路有多种入口，维护和文档成本上升 |
| 后端能力丰富但产品域分散 | `src/backend/app/api/router.py` 注册了 strategy、backtests、workspace、optimization、simulation、live-trading、portfolio、data、knowledge-base、rag、kb-chat、brokers、data-governance、data-topics、equity-research、news-intelligence、options-chain、scanners、quant-tools 等 | API 按技术模块完整，但缺少面向用户的能力归属 |
| 数据能力扩展后缺少统一心智 | `/data` 下已有市场数据、AkShare 脚本/任务/执行/表、同步、接口、治理、Airflow、DataTopicHub；另有 `/quote`、权益研究、新闻、期权、扫描 | “数据管理”和“市场情报”分裂，行情/研究数据/同步治理之间关系不清 |
| 研究与交易生命周期未统一 | 策略中心、研究工作区、回测结果、优化、策略评分、过拟合、解释器、交易工作区、实盘实例、组合账本各自存在 | 功能链条完整，但缺少“从想法到交易再到组合归因”的主流程 |
| AI 能力分布在多处 | AI Chat、知识库/RAG、KB Chat、策略 Copilot、Prompt 治理、AI 成本、多模型偏好、AI Trading 都已有入口或 API | AI 既是独立工作台，也是上下文能力；现在两种角色混在导航层 |

结论：迭代 180 不应该继续铺新模块，而应完成一次**产品功能整合迭代**，让现有功能在保留兼容的同时变得更像一个统一平台。

---

## 2. 整合原则

1. **保留全部功能**：所有现有页面、API、测试和深链入口必须继续可用；前端老路径可以 redirect，但不能 404。
2. **先产品域，后代码目录**：本迭代优先收敛导航、路由别名、能力地图和工作流，不做大规模后端包重命名。
3. **一条能力只有一个权威归属**：每个页面/API 都要归到一个主产品域，同时允许在其他工作流中作为快捷动作出现。
4. **管理入口下沉**：Prompt 治理、AI 成本、数据接口治理、Airflow、同步、审计、状态等 admin 能力默认收纳到对应域的“管理/治理”子入口，避免挤占普通用户主导航。
5. **工作流优先于模块名**：用户更关心“构思策略 - 回测 - 优化 - 上线 - 监控 - 归因”，而不是后端模块叫什么。
6. **兼容期可观测**：新旧路由并存至少两个迭代周期，记录旧入口访问，确认无人依赖后再讨论移除。

---

## 3. 目标产品域模型

| 产品域 | 用户心智 | 收纳现有功能 | 主入口建议 |
| --- | --- | --- | --- |
| 首页 / Command Center | 总览、最近任务、待处理风险、快速继续工作 | Dashboard、最近回测、最近工作区、告警、AI/数据配置健康摘要 | `/` |
| 市场数据 / Market Data Hub | 数据接入、行情、市场情报、数据治理 | 数据管理、AkShare 脚本/任务/执行/表/接口、同步、Data Governance、Data Topics、Airflow、Quote、权益研究、新闻情报、期权链、条件扫描 | `/data` |
| 策略研究 / Strategy Research Studio | 策略开发、研究工作区、回测、优化、报告、策略可信度 | 策略管理、研究工作区、回测结果、参数优化、Analytics、Comparison、Strategy Score、Overfitting、Strategy Explainer、Research Quant Tools | `/research` |
| 交易运营 / Trading Operations | 模拟/实盘运行、账户、网关、风控、自动交易 | 交易工作区、Simulation、Live Trading、Broker Profiles、Gateways、Auto Trading、AI Trading、Risk Control、Monitoring | `/trading` |
| 组合风控 / Portfolio & Risk Center | 组合、账本、风险、归因、绩效复盘 | Portfolio 聚合、Portfolio Ledger、Risk Analytics、Factor Library、Performance Attribution、组合报表 | `/portfolio` |
| AI 知识 / AI Knowledge Lab | 知识库、问答、策略 Copilot、模型治理 | AI Chat、Knowledge Base、RAG、KB Chat、Strategy Copilot、Prompt Templates、AI Observability、AI Preferences | `/ai` |
| 平台治理 / Platform Admin | 系统设置、状态、审计、文档、健康检查 | Settings、Auth/Profile、Audit、Metrics、Status Routers、Docs、可选路由状态 | `/admin` |

> `平台治理` 可以作为管理员可见的第七入口；非管理员只在右上角用户菜单和各域治理页看到必要设置。

---

## 4. 新信息架构

### 4.1 一级导航

建议把当前 20+ 个可见一级菜单收敛为：

1. `首页`
2. `市场数据`
3. `策略研究`
4. `交易运营`
5. `组合风控`
6. `AI知识`
7. `平台治理`（admin only）

### 4.2 二级入口

| 一级入口 | 二级入口 | 对应当前页面 |
| --- | --- | --- |
| 市场数据 | 行情报价 | `/quote` |
| 市场数据 | 数据表与脚本 | `/data/market`、`/data/scripts`、`/data/tasks`、`/data/executions`、`/data/tables` |
| 市场数据 | 数据接口治理 | `/data/interfaces`、`/data/governance`、`/data/topics`、`/data/sync`、`/data/airflow` |
| 市场数据 | 市场情报 | `/equity-research`、`/news-intelligence`、`/options-chain`、`/scanners` |
| 策略研究 | 策略库 | `/strategy` |
| 策略研究 | 研究工作区 | `/workspace`、`/backtest` |
| 策略研究 | 回测结果 | `/backtest/result/:id` |
| 策略研究 | 优化与报告 | workspace optimization/report tabs、`/optimization` API |
| 策略研究 | 可信度分析 | Strategy Score、Overfitting、Explainer、Comparison |
| 交易运营 | 交易工作区 | `/trading` |
| 交易运营 | 模拟/实盘实例 | `/simulation` API、`/live-trading` API |
| 交易运营 | 网关与账户 | `/gateways`、`/brokers` |
| 交易运营 | 自动/AI交易 | `/ai-trading`、`/auto-trading` API |
| 交易运营 | 风控与监控 | `/risk-control`、`/monitoring` API |
| 组合风控 | 组合总览 | `/portfolio` |
| 组合风控 | 组合账本 | `/portfolio-ledger` |
| 组合风控 | 风险分析 | `/risk-analytics` API |
| 组合风控 | 因子与归因 | `/factor-lib`、`/perf-attribution` API |
| AI知识 | AI 助手 | `/ai-chat` |
| AI知识 | 知识库 | `/knowledge-base` |
| AI知识 | 策略 Copilot | 当前 AIChat / Strategy API 草稿能力 |
| AI知识 | Prompt 与模型治理 | `/admin/prompt-templates`、AI model preferences |
| AI知识 | AI 成本与健康 | `/admin/ai-observability` |
| 平台治理 | 系统设置 | `/settings` |
| 平台治理 | 审计与状态 | `/audit`、`/metrics`、`/status/routers` API |
| 平台治理 | API 文档 | `/docs/postman`、OpenAPI |

---

## 5. 路由收敛方案

本迭代不移除旧路由，只新增 canonical path 与 redirect/alias。

| 当前路径 | 新 canonical path | 处理方式 |
| --- | --- | --- |
| `/strategy` | `/research/strategies` | 老路径保留并 redirect 或 alias |
| `/workspace` | `/research/workspaces` | 老路径保留；当前 `/backtest` 也导向这里 |
| `/backtest/workspace/:id` | `/research/workspaces/:id` | 老路径 redirect |
| `/backtest/result/:id` | `/research/backtests/:id` | 老路径 redirect |
| `/backtest/legacy` | `/research/backtests/legacy` | 标记 legacy，默认不放一级入口 |
| `/data/*` | `/data/*` | 保持，作为 Market Data Hub 主入口 |
| `/quote` | `/data/quote` | 老路径 redirect；Quote 成为数据域子页 |
| `/equity-research` | `/data/intelligence/equity` | 老路径 redirect |
| `/news-intelligence` | `/data/intelligence/news` | 老路径 redirect |
| `/options-chain` | `/data/intelligence/options` | 老路径 redirect |
| `/scanners` | `/data/intelligence/scanners` | 老路径 redirect |
| `/trading` | `/trading/workspaces` | 老路径可保留为 trading domain home |
| `/simulate` | `/trading/workspaces?mode=paper` | 老路径 redirect |
| `/live-trading` | `/trading/workspaces?mode=live` | 老路径 redirect |
| `/gateways` | `/trading/gateways` | 老路径 redirect |
| `/brokers` | `/trading/brokers` | 老路径 redirect |
| `/ai-trading` | `/trading/ai` | 老路径 redirect，保留高风险确认 |
| `/portfolio` | `/portfolio/overview` | `/portfolio` 作为组合域首页 |
| `/portfolio-ledger` | `/portfolio/ledger` | 老路径 redirect |
| `/quant-tools` | `/research/tools` | 老路径 redirect；AI 可在 AI 域中交叉引用 |
| `/ai-chat` | `/ai/chat` | 老路径 redirect |
| `/knowledge-base` | `/ai/knowledge-base` | 老路径 redirect |
| `/admin/prompt-templates` | `/ai/prompt-governance` 或 `/admin/ai/prompts` | 保留 admin 权限 |
| `/admin/ai-observability` | `/ai/observability` 或 `/admin/ai/observability` | 保留 admin 权限 |
| `/settings` | `/admin/settings` 或用户菜单 `/settings` | 非 admin 个人设置仍可直达 |

验收要求：旧路径直接访问、浏览器刷新、深链分享、E2E 登录后跳转都必须继续工作。

---

## 6. 权威工作流

### 6.1 策略生命周期

```text
AI/知识库构思
  -> 策略草稿 / 策略模板
  -> 策略库保存与版本管理
  -> 研究工作区创建策略单元
  -> 回测执行
  -> 结果分析 / 策略评分 / 过拟合 / 解释器 / 对比
  -> 参数优化与工作区报告
  -> 加入交易工作区
  -> 模拟运行
  -> 实盘启用前风控与网关检查
  -> 组合账本与绩效归因
```

整合点：

- Backtest Result 页增加“下一步”动作：`优化参数`、`加入研究报告`、`生成策略复盘`、`加入交易工作区`。
- Strategy Draft Card 的动作目标统一指向 `/research/...`，避免散落到旧路径。
- 交易启用必须经过 `/trading` 域内的账户、网关、风控检查，不从研究页直接写交易。

### 6.2 数据生命周期

```text
数据源/接口注册
  -> 脚本/任务/执行
  -> 数据表与质量检查
  -> DataTopicHub 发布
  -> 行情报价 / 股票研究 / 新闻 / 期权 / 扫描
  -> 研究工作区和交易工作区消费
```

整合点：

- `/data` 域首页展示 provider 健康、最近执行、数据表、新鲜度、topic 状态。
- Quote、Equity Research、News、Options、Scanners 统一归为“市场情报”子域。
- 数据同步、Airflow、接口治理默认 admin 可见，但普通用户能看到只读数据健康摘要。

### 6.3 交易运营生命周期

```text
Broker Profile / Gateway
  -> 账户健康与凭证轮换检查
  -> 交易工作区
  -> 模拟/实盘实例
  -> 自动交易配置 / AI Trading 二次确认
  -> 风控规则
  -> 监控告警
  -> 组合聚合与账本沉淀
```

整合点：

- `/trading` 域首页必须先展示“连接状态 / 风控状态 / 实例状态”，再展示工作区。
- Broker Profiles 和 Gateways 同属“账户与连接”，不再分别占一级入口。
- AI Trading 不作为普通 AI 功能，而作为交易域高风险入口，保留显式确认与审计。

### 6.4 组合风控生命周期

```text
交易/导入/手工记录
  -> 组合账本
  -> 持仓与现金
  -> NAV 快照
  -> 风险指标
  -> 因子分析 / 绩效归因
  -> 复盘报告
```

整合点：

- 明确 `/portfolio` 是“运行聚合视图”，`/portfolio/ledger` 是“独立账本真相源”。
- Risk Analytics、Factor Library、Performance Attribution 在 UI 上归到组合风控域，同时研究域可链接使用。
- 组合页提供反向追溯到策略/工作区/交易实例的链接。

### 6.5 AI 知识生命周期

```text
知识库上传与索引
  -> RAG / KB Chat
  -> 策略构思 / 策略草稿
  -> 上下文 AI 辅助
  -> Prompt 治理
  -> 模型偏好 / 成本 / 失败诊断
```

整合点：

- AI 域保留完整 AI 工作台。
- 策略研究、数据、组合页面可以嵌入轻量“上下文 AI”入口，但底层复用 AI 域配置。
- Prompt 治理和 AI 成本保留 admin 权限，但在 AI 域有清晰入口。

---

## 7. 任务拆分

### T0 - 能力地图与导航真相源

**目标**：建立一个权威 capability registry，覆盖所有现有页面、API 和导航项。

改动建议：

- 新增 `docs/product/CAPABILITY_MAP.md`，列出能力 ID、产品域、当前页面、API 前缀、权限、状态、canonical path、旧路径。
- 新增前端配置 `src/frontend/src/navigation/capabilities.ts`，由它驱动侧边栏、移动端菜单、面包屑和域首页入口。
- 能力状态统一为：`stable`、`beta`、`admin`、`legacy`、`hidden`。
- 每个路由必须映射到一个 capability；测试中校验没有孤儿路由。

验收：

- [ ] 当前所有可见菜单项都出现在 capability map。
- [ ] 当前所有前端 route 都有产品域归属。
- [ ] admin-only 能力有显式权限声明。
- [ ] legacy 入口不出现在一级导航，但深链可用。

### T1 - 前端导航收敛

**目标**：把 `AppLayout.vue` 中硬编码的长菜单收敛为六大域导航。

改动建议：

- `AppLayout.vue` 只渲染一级产品域，不再硬编码所有功能入口。
- 新增二级导航组件，例如 `DomainSubnav.vue`，在域首页和域内页面展示。
- 移动端抽屉复用同一 navigation config，避免桌面/移动两套菜单漂移。
- 页面标题由 route meta/capability 生成，不再维护独立标题表。

验收：

- [ ] 一级导航不超过 7 项。
- [ ] 当前所有页面可通过新导航 2 次点击内到达。
- [ ] 桌面和移动端导航项一致。
- [ ] 非 admin 用户看不到 admin-only 子入口。

### T2 - Canonical route 与兼容 redirect

**目标**：新增产品域路径，同时保证旧路径可用。

改动建议：

- 在 `src/frontend/src/router/index.ts` 增加 `/research`、`/data`、`/trading`、`/portfolio`、`/ai`、`/admin` 域路由。
- 老路径采用 redirect 或 alias，至少保留两个迭代。
- 给 redirect 增加轻量 telemetry/audit 事件，统计旧入口使用情况。
- 更新 Playwright/Vitest router 测试，覆盖旧路径和新路径。

验收：

- [ ] 表 5 中所有旧路径访问不 404。
- [ ] 旧路径刷新后仍能进入正确页面。
- [ ] route guard 对 admin-only 新旧路径行为一致。
- [ ] `router.test.ts` 覆盖 canonical path 与 redirect。

### T3 - 域首页与端到端动作入口

**目标**：每个产品域都有一个轻量工作台首页，展示状态、最近对象和下一步动作。

域首页建议：

| 域 | 首页内容 |
| --- | --- |
| `/data` | 数据源健康、最近任务、数据表、新鲜度、topic 状态、市场情报快捷入口 |
| `/research` | 最近研究工作区、策略库、最近回测、优化任务、待复盘结果 |
| `/trading` | 连接健康、交易实例、风控状态、监控告警、交易工作区 |
| `/portfolio` | 组合总览、账本、新近交易、风险摘要、归因入口 |
| `/ai` | 最近会话、知识库索引状态、策略草稿、模型偏好、AI 失败诊断 |
| `/admin` | 系统状态、可选路由、审计、指标、数据/AI 治理入口 |

验收：

- [ ] 每个域首页都只复用现有 API，不引入新业务能力依赖。
- [ ] 空状态明确，不能出现“功能不可用但没有解释”。
- [ ] 首页快捷动作指向 canonical route。

### T4 - 跨域工作流动作补齐

**目标**：让核心链路的“下一步”动作清晰可见。

改动建议：

- Strategy 页：`创建研究工作区`、`运行回测`、`打开 Copilot`。
- Research Workspace：`查看报告`、`优化参数`、`加入交易工作区`。
- Backtest Result：`策略评分`、`过拟合检测`、`策略解释`、`对比结果`、`生成复盘`。
- Trading Workspace：`绑定 Broker/Gateway`、`配置风控`、`查看组合影响`。
- Portfolio Ledger：`追溯交易来源`、`查看归因`、`生成复盘摘要`。
- Data 表/Topic：`用于行情报价`、`用于研究工作区`、`打开市场情报`。

验收：

- [ ] 策略生命周期至少有一条完整 E2E smoke：策略模板 -> 研究工作区 -> 回测 -> 结果 -> 组合/交易入口。
- [ ] 数据生命周期至少有一条完整 E2E smoke：数据接口/表 -> 行情/研究消费。
- [ ] 交易生命周期至少有一条只读 smoke：Broker/Gateway 状态 -> 交易工作区 -> 组合总览。

### T5 - 后端能力状态聚合

**目标**：给前端工作台提供统一能力状态，而不是每个页面各查各的。

改动建议：

- 新增或扩展 `/api/v1/status/capabilities`：
  - 复用 `optional_router_status`。
  - 返回各能力域的 API 可用性、权限、降级原因、最近错误。
  - 不替代现有业务 API，仅作聚合状态。
- 保留 `/api/v1/status/routers`，新增端点只服务产品工作台。

验收：

- [ ] 能力状态包含 core/optional router 可用性。
- [ ] 前端域首页能展示“可用 / 降级 / 需配置 / admin-only”。
- [ ] 后端测试覆盖 optional router unavailable 时的响应结构。

### T6 - 文档与用户指南同步

**目标**：文档从“模块清单”改为“工作流指南 + 能力地图”。

改动建议：

- 更新 `README.md` 的核心入口说明，弱化长 API 模块表。
- 更新 `docs/guides/USER_GUIDE.md`，按六大产品域组织。
- 更新 `docs/reference/API_OVERVIEW.md`，标明 API 仍按兼容前缀提供。
- 新增 `docs/product/CAPABILITY_MAP.md` 和 `docs/product/WORKFLOWS.md`。

验收：

- [ ] 用户指南能解释六大域和五条主工作流。
- [ ] 每个旧入口在文档中有迁移说明。
- [ ] API 文档明确“前端 canonical route 改变不等于 API breaking change”。

### T7 - 回归测试与可观测性

**目标**：确保整合只改变入口组织，不造成业务回归。

建议测试：

```bash
cd src/frontend
npm run typecheck
npm run test -- src/__tests__/router.test.ts src/__tests__/App.test.ts --run
npm run test -- src/__tests__/views/Dashboard.test.ts --run

cd src/backend
pytest tests/test_main_lifespan_and_websocket.py tests/test_api_e2e.py tests/test_backward_compat_iter170.py -q --tb=short
```

验收：

- [ ] 新旧路由兼容测试通过。
- [ ] 前端导航测试覆盖 admin/non-admin 两种用户。
- [ ] 后端 status/capabilities 测试通过。
- [ ] 关键 E2E smoke 覆盖六大域至少一次。

---

## 8. 非范围

本迭代明确不做：

- 不删除旧 API 前缀，不移除旧前端路径。
- 不重写 `live_trading`、`gateway`、`broker` 交易写路径。
- 不新增默认实盘下单能力。
- 不把后端包结构按产品域大搬家。
- 不引入新的外部数据源或券商。
- 不处理 P0 历史凭据轮换/force-push，该事项仍按既有安全 runbook 由 owner 执行。
- 不追求一次性重做所有页面视觉，只处理入口、域首页和工作流动作。

---

## 9. Definition of Done

- [ ] 一级导航收敛为 `首页 / 市场数据 / 策略研究 / 交易运营 / 组合风控 / AI知识 / 平台治理(admin)`。
- [ ] 现有所有功能都有产品域归属和 capability ID。
- [ ] 所有当前可见页面都能从新导航到达。
- [ ] 表 5 中旧路径全部保留兼容，不出现 404。
- [ ] 关键旧路径访问有 telemetry/audit 记录，便于后续决定是否移除。
- [ ] 至少 5 条权威工作流在 UI 上有“下一步”动作串联。
- [ ] 文档完成六大域和旧入口迁移说明。
- [ ] 前端 typecheck、router/AppLayout 相关测试通过。
- [ ] 后端 status/capabilities 和兼容 smoke 通过。

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 导航改动让老用户找不到原入口 | 用户体验回退 | 老路径保留；域首页提供“旧入口名称”搜索/快捷入口；文档列出迁移表 |
| route redirect 影响登录后跳转 | 登录流程回归 | router guard 专门加测试，覆盖 redirect query 和 admin 权限 |
| admin-only 能力误暴露 | 安全/权限问题 | capability map 明确 `requiresAdmin`；菜单和路由守卫都用同一配置 |
| AI Trading 被误认为普通 AI 能力 | 高风险操作误触 | 归入交易运营域，保留二次确认、风控、审计；AI 域只提供说明和跳转 |
| 新 canonical route 与 API 前缀不一致造成困惑 | 开发沟通成本 | 文档明确“前端信息架构”和“后端 API 兼容前缀”是两层 |
| 一次性改太多页面 | 回归范围大 | 先改导航/路由/域首页，不动业务组件内部逻辑 |

---

## 11. 建议提交顺序

1. `docs(product): add capability map and integration workflow plan`
2. `feat(nav): introduce product-domain capability registry`
3. `feat(router): add canonical product routes with legacy redirects`
4. `feat(layout): render grouped domain navigation from registry`
5. `feat(workbench): add lightweight domain home pages`
6. `feat(status): expose product capability status summary`
7. `test(nav): cover route compatibility and admin visibility`
8. `docs(guides): align user guide with six product domains`

---

## 12. 后续迭代建议

如果迭代 180 验收通过，后续可以拆出三条产品化路线：

| 后续路线 | 目标 |
| --- | --- |
| 迭代 181 - 研究到交易闭环体验 | 深化 Strategy -> Research -> Backtest -> Trading -> Portfolio 的跨页状态和报告 |
| 迭代 182 - 数据与市场情报产品化 | 把 Data Governance、Quote、Equity Research、News、Options、Scanners 进一步收敛为市场数据工作台 |
| 迭代 183 - AI 上下文助手 | 在研究、数据、组合页面嵌入上下文 AI，但统一走 AI Knowledge Lab 的配置、成本与审计 |

