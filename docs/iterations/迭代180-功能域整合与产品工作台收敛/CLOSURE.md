# 迭代 180 本次切片验收记录

> **验收日期**: 2026-06-13
> **切片范围**: 文档设计 + 前端产品域导航/canonical route + 后端 capability status 聚合

---

## 1. 已完成

- 新增 `DESIGN.md`：明确前端能力地图、产品域导航、canonical route 和后端状态聚合设计。
- 新增 `ACCEPTANCE.md`：明确文档、前端、后端、权限和测试验收项。
- 新增前端能力地图 `src/frontend/src/navigation/capabilities.ts`：
  - 六大产品域 + admin 平台治理。
  - 每个 capability 记录 canonical path、legacy path、权限和状态。
  - AppLayout 页面标题、当前域、二级入口均从能力地图推导。
- 改造 `AppLayout.vue`：
  - 侧边栏一级导航收敛为产品域。
  - Header 显示当前域二级入口。
  - 桌面/移动端菜单使用同一份产品域配置。
- 新增 canonical route：
  - `/research/*`
  - `/data/quote`
  - `/data/intelligence/*`
  - `/trading/*`
  - `/portfolio/*`
  - `/ai/*`
  - `/admin/settings`
- 保留旧路径：
  - `/strategy`
  - `/workspace`
  - `/backtest/*`
  - `/quote`
  - `/brokers`
  - `/gateways`
  - `/portfolio-ledger`
  - `/ai-chat`
  - `/knowledge-base`
  - `/admin/ai-observability`
  - `/admin/prompt-templates`
- 新增后端 `/api/v1/status/capabilities`：
  - 按 `data/research/trading/portfolio/ai/admin` 聚合能力状态。
  - 复用 `optional_router_status` 标记 optional 能力降级。
  - 保持 `/api/v1/status/routers` 原响应结构。
- 补充前后端测试。

---

## 2. 验收结果

| 验收项 | 结果 |
| --- | --- |
| 前端 router + AppLayout 测试 | 通过，54 tests |
| 前端 i18n completeness | 通过，18 tests |
| 前端 typecheck | 通过 |
| 后端 status capabilities 测试 | 通过，3 tests |
| 后端 ruff check | 通过 |
| 后端 ruff format --check | 通过 |
| git diff --check | 通过 |

---

## 3. 已运行命令

```bash
cd src/frontend
npm run test -- src/__tests__/router/index.test.ts src/__tests__/components/common/AppLayout.test.ts --run
npm run test -- src/i18n/__tests__/locale-completeness.test.ts --run
npm run typecheck

cd src/backend
pytest tests/test_status_capabilities.py -q --tb=short
ruff check app/api/status.py tests/test_status_capabilities.py
ruff format --check app/api/status.py tests/test_status_capabilities.py

git diff --check
```

---

## 4. 未纳入本切片

- 域首页深度建设：当前只完成导航和 canonical route，后续可继续做 `/research`、`/trading`、`/portfolio`、`/ai` 的工作台首页。
- 跨域“下一步”动作：本切片未改 Strategy / Backtest / Portfolio 页面内部操作。
- 旧入口 telemetry：本切片保留旧路径，但尚未接入访问统计。
- 后端业务包重组：按计划未做。
- 交易写路径：按计划未触碰。

---

## 5. 后续建议

下一切片建议优先做：

1. `/research`、`/trading`、`/portfolio`、`/ai` 域首页。
2. Backtest Result 页增加 `优化参数 / 加入交易工作区 / 生成复盘` 等下一步动作。
3. 旧路径访问 telemetry，统计两个迭代后再决定是否隐藏/移除 legacy 入口。

