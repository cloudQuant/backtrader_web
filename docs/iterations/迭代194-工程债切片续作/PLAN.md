# 迭代 194：工程债切片续作 Implementation Plan（骨架）

> **来源**：迭代 193 Task A/I/K/M 的 L 级递延条目。本文件为骨架，确保递延不遗漏；具体切片设计在 194 启动时补全。
> **红线**：不新增功能，仅切片重构、补测、补文档。

## 背景

迭代 193 完成门禁真伪校准与 P0/S 级 P1 清零，但以下 L 级改动单迭代消化不了，按棘轮逐批推进。193 已将 5 项 god file 登记进 `large_file_baseline.json`，2 项前端回归登记为 `_deferred_regressions`（本文件为其修复计划）。

## Task 列表（L 级切片）

### Task A：asset_research god file 切片（193 Task I 递延）

| 文件 | 当前行数 | 目标 | 切片策略 |
| --- | --- | --- | --- |
| `services/asset_research/orchestrator.py` | 3048 | ≤1000 | 按资产类型拆 sub-orchestrator（equity/fund/bond） |
| `services/asset_research/plugins/base.py` | 1948 | ≤1000 | 插件基类与具体实现分层 |
| `services/asset_research/providers/akshare.py` | 1310 | ≤1000 | 按数据域拆（行情/财务/事件） |
| `schemas/asset_research.py` | 1300 | ≤1000 | 按资产类型拆 schema 子模块 |

### Task B：`_run_pipeline` 1363 行拆分（193 Task I 递延）

`services/ai_strategy_research_service.py:486` 单方法 1363 行，按阶段拆 `pipeline/` 子包：data_prep -> feature -> model -> backtest -> evaluate -> package。193 已完成拆分设计 + 最独立 2-3 阶段先行，本迭代完成剩余阶段。

### Task C：`contract_spec_for` 492 行拆分（193 Task I 递延）

`services/position_valuation.py` 按资产类型拆解析函数（equity/fund/bond/futures/options）。

### Task D：portfolio helper 下沉（193 Task I 递延）

`api/portfolio/api.py` 87 个私有 helper 下沉 `services/portfolio_valuation/`。

### Task E：`lazy="raise"` 全量化（193 Task I 递延）

`models/*.py` 77 个 relationship 分批改 `lazy="raise"` + 显式 eager load，配合测试暴露隐式加载点。

### Task F：前端 god 文件续拆（193 Task A/K 递延 + `_deferred_regressions`）

| 文件 | 当前行数 | 基线 | 切片策略 |
| --- | --- | --- | --- |
| `views/strategy/useStrategyPage.ts` | 6795 | 6738（194 修复） | 抽 `useAIResearchRuntime`/`useLiveHandoff` composable |
| `views/StrategyPage.vue` | 3122 | 3122 | template 按功能区拆展示型子组件 |
| `views/investment/StockAnalysisPage.vue` | 1613 | 1433（194 修复） | 抽 signal lifecycle 展示型子组件 |
| `views/investment/AssetAnalysisPage.vue` | 1504 | 1504 | 按分析维度拆 |

### Task G：git 历史重写（193 Task F 递延）

`data/datas/*.csv`（246.7MB）历史重写 `git filter-repo`，单独排期，需 owner 协调。

### Task H：DR staging 恢复演练（193 Task M 递延，若未完成）

`docs/runbooks/backup-restore.md` 在 staging 实跑恢复演练。

### Task I：Lighthouse 多页审计恢复（193 Task D 递延）

193 已把死门禁修活：Chrome 安装、SPA 预览服务（`src/frontend/lhci-preview.config.mjs` stub）、
`/login` 实审。恢复 175 §3.1 的 Critical_Page_Set 7 页覆盖需要按端点提供真实数据形状的
API fixture（当前通用空 envelope 下,认证页挂起不渲染）。另需 `lhci/login.js` 的
sessionStorage 注入配合（已就绪）。

### Task J：dependabot 升级批次处理（2026-08 挂起 14 个 PR）

2026-08-16 关闭了 14 个 dependabot PR（#7-#20，python/node 运行时 major、mypy 2.3、
pinia 4、plugin-vue 6、actions major、若干 patch/minor）。后续批次按以下规则处理：

- **patch/minor**：重生成 dev 锁（uv pip compile，完整 extras、`--no-emit-package pip`）；
  npm 类需 `npm ci` 后跑 `ALLOW_BASELINE_UPDATE=1 python3 scripts/ci/npm_audit_ratchet.py --update`
  刷新棘轮基线（锁哈希绑定是预期门禁，不是故障）；全量测试后合并。
- **mypy major**：repo-wide 棘轮基线按版本锁定（当前 1.20.2），升级 = 锁重生成 + 基线重生成 +
  759 个历史错误的再审计，与 Task I（mypy 历史清理）合并做。
- **运行时 major（python/node Docker 镜像）**：发布链路无验证，需先专项验证依赖兼容性再升级。
- **actions major**：PR 自身 CI 即验证（改的就是 CI），绿即可合；docs.yml 相关（Pages 部署）
  在 master push 后确认部署正常。
- 治理已落地（2026-08-16）：`.github/dependabot.yml` 已为暂缓 major 加 `ignore` 条目（mypy >=2、pinia >=3、@vitejs/plugin-vue >=6、docker python >=3.13、docker node >=21），避免被关闭的 PR 每周重复提出；解除时机 = 本 Task 对应验证完成。

## 验收标准

- `large_file_baseline.json` 中 `_deferred_regressions` 清空（2 项前端回归修复至原基线）
- 所有 god file 降至 ≤1000 行或经评审基线
- `lazy="raise"` 全量化且测试全绿
- git 历史重写完成且 CI checkout 体积下降
