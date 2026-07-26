# 迭代 180 验收方案 - 功能域整合与产品工作台收敛

> **创建日期**: 2026-06-13
> **验收目标**: 证明本迭代只整合入口和工作流，不造成现有功能回归。

---

## 1. 验收范围

本轮验收覆盖：

- 设计文档完整性
- 前端能力地图
- 一级导航收敛
- 二级导航可达
- canonical route 与旧路径兼容
- 后端 `/status/capabilities`
- admin 权限一致性
- 基础测试与类型检查

---

## 2. 文档验收

- [ ] `PLAN.md` 存在并说明产品域、路由、任务、DoD。
- [ ] `DESIGN.md` 存在并说明前后端设计边界。
- [ ] `ACCEPTANCE.md` 存在并说明验收用例和命令。
- [ ] 文档明确“不删除现有功能，不移除旧路径”。

---

## 3. 前端验收

### 3.1 导航

- [ ] 侧边栏一级导航不超过 7 项。
- [ ] 一级导航包含：`首页`、`市场数据`、`策略研究`、`交易运营`、`组合风控`、`AI知识`。
- [ ] admin 用户能看到 `平台治理`。
- [ ] 非 admin 用户看不到 `平台治理`。
- [ ] 当前域二级导航显示该域下功能入口。

### 3.2 路由兼容

- [ ] `/strategy` 可访问。
- [ ] `/research/strategies` 可访问。
- [ ] `/workspace` 可访问。
- [ ] `/research/workspaces` 可访问。
- [ ] `/backtest/result/:id` 可访问。
- [ ] `/research/backtests/:id` 可访问。
- [ ] `/quote` 可访问。
- [ ] `/data/quote` 可访问。
- [ ] `/brokers` 可访问。
- [ ] `/trading/brokers` 可访问。
- [ ] `/ai-chat` 可访问。
- [ ] `/ai/chat` 可访问。
- [ ] `/knowledge-base` 可访问。
- [ ] `/ai/knowledge-base` 可访问。

### 3.3 权限

- [ ] 非 admin 访问 `/admin/ai-observability` 被重定向。
- [ ] 非 admin 访问 `/ai/observability` 被重定向。
- [ ] 非 admin 访问 `/data/governance` 被重定向。
- [ ] admin 能访问上述页面。

---

## 4. 后端验收

- [ ] `/api/v1/status/routers` 保持原响应结构。
- [ ] `/api/v1/status/capabilities` 返回 `domains` 数组。
- [ ] 返回中至少包含 `data/research/trading/portfolio/ai/admin` 域。
- [ ] optional router 不可用时，对应 capability 返回 `available=false` 或 domain `status=degraded`。
- [ ] core capability 默认 `available=true`。

---

## 5. 推荐验证命令

前端：

```bash
cd src/frontend
npm run typecheck
npm run test -- src/__tests__/router/index.test.ts src/__tests__/components/common/AppLayout.test.ts --run
```

后端：

```bash
cd src/backend
pytest tests/test_status_capabilities.py -q --tb=short
```

文档和工作区核对：

```bash
git status --short
```

---

## 6. 业务回归抽查

- [ ] 登录后访问首页正常。
- [ ] 从新导航进入策略研究，再打开策略库正常。
- [ ] 从新导航进入市场数据，再打开行情报价正常。
- [ ] 从新导航进入交易运营，再打开 Broker 配置正常。
- [ ] 从新导航进入 AI 知识，再打开知识库正常。
- [ ] 旧 URL 收藏夹仍能打开对应页面。

---

## 7. 退出条件

满足以下条件才能认为本迭代第一阶段可收口：

- [ ] 文档、前端、后端三类验收项均完成。
- [ ] 推荐验证命令通过，或失败项有明确原因和后续处理。
- [ ] `git status` 只包含本迭代相关变更和既有用户改动。
- [ ] 未触碰交易写路径。

