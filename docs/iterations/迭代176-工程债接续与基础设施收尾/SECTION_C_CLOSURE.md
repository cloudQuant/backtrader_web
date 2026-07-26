# 迭代 176 § C 关闭报告 — 前端 i18n 中文裸串清理

**关闭日期**: 2026-05-29
**起点**: 175 close（commit `51efc51e`，CJK 1188，strict 15553）
**终点**: pass-41（commit `88c920ea`，CJK 0，strict 13986）
**总计**: 25 commits（passes 17-41）跨 175 close 后续工作至 176 § C 收口

---

## 验收结果

| 指标 | 175 起点 | 176 § C 收口 | Δ |
|------|---------:|-------------:|--:|
| CJK 违规 | 1188 | **0** | -100% |
| Strict 总计 | 15553 | 13986 | -1567 |
| Locale parity keys（每侧） | 1100 | 2629 | +1529 |
| vue-tsc 错误 | 144 | 132 | -12 |
| CI 阻塞门状态 | advisory | **CJK blocking** | flipped |
| 测试通过 | n/a | 29/29（stores/theme + api/index） | clean |

## CI 阻塞门设计

CI workflow 现在有两个 i18n 步骤：

```yaml
- name: i18n CJK strict scan (blocking)
  run: python scripts/dev/check_i18n_coverage.py --strict --cjk-only

- name: Strict scan full (advisory; CJK + English over-reach)
  continue-on-error: true
  run: python scripts/dev/check_i18n_coverage.py --strict | tail -50
```

- **阻塞门**：CJK-only。未来引入 `<template>`、Element Plus `label`/`placeholder` 或 `ElMessage*` 调用首参数中的中文裸串将立即 fail PR。
- **Advisory 门**：完整 strict（CJK + EN）。残留 13986 主要是英文占位符/属性扫描器过度命中（`await ElMessageBox.confirm` 这类语句被当作"用户可见英文"），需要更细的扫描器启发式。**非 176 § C 范围**。

## 唯一豁免

`src/frontend/src/components/LanguageSwitcher.vue` line 33-34：

```typescript
const locales = [
  // i18n-ignore-next-line
  // i18n-reason: native-script self-label by convention; switching to t() would defeat the purpose of a language picker.
  { value: 'zh-CN', label: '中文' },
  { value: 'en-US', label: 'English' },
]
```

语言选择器的原生脚本自标签是行业约定（Google、Apple、Wikipedia 都这样做）。如果用 `t()` 包裹，对不懂当前 locale 的用户来说反而失去识别能力。

## 工作模式（passes 17-41）

每个 commit 专注一个或一组高密度文件，输出格式：

```
i18n(<scope>): <description> (176 § C)

<details>

Verification:
- ESLint clean / vue-tsc <count> (unchanged) / parity <n>/<n>
- CJK <before> -> <after> (-<delta>)
- Strict <before> -> <after>

Baseline updated: <baseline_commit> / <strict> / <cjk>
```

每批结束都更新 `scripts/dev/check_i18n_coverage_baseline.json` 的 `_history` 字段，使数字逐 commit 可追溯。

## 关键技术模式（确立）

1. **Vue SFC 用 `useI18n()`** — `<script setup>` 引入 `const { t } = useI18n()`，模板用 `t('ns.key')`。

2. **TS 模块用 `i18n.global.t`** — 非 setup 上下文不能用 `useI18n()`，统一用：
   ```typescript
   import i18n from '@/i18n'
   function tt(key: string, named?: Record<string, unknown>): string {
     return named ? i18n.global.t(key, named) : i18n.global.t(key)
   }
   ```
   已建立的参考实现：`logViewerHelpers.ts`、`useStrategyDraftWorkspaceExecution.ts`、`useBacktestRuntime.ts`、`useAIChatRendering.ts`、`gatewayStatusHelpers.ts`、`stores/quote.ts`、`stores/kbChat.ts`、`api/index.ts`、`composables/useInstanceActions.ts`、`composables/useKeyboardShortcuts.ts`、`composables/useUnitTableRendering.ts`、`composables/useOverfittingRuntime.ts`、`constants/strategy.ts`、`stores/theme.ts`、`components/workspace/optimizationChartHelpers.ts`、`views/data/utils.ts`。

3. **HTML 注释直接英文化** — 注释（`<!-- ... -->` 和 `// ...`）不需要 i18n，用英文等价物替换即可移除扫描器命中。这是 strict 总数下降的主要来源之一。

4. **测试 i18n mock passthrough** — 当现有测试断言依赖具体中文字符串时，加 `vi.mock('@/i18n', () => ({ default: { global: { t: (key) => zhMap[key] ?? key } } }))` 让测试仍然断言原中文，避免 churn 数十处用例。已用于 `__tests__/api/index.test.ts`（19 tests pass）和 `__tests__/stores/theme.test.ts`（10 tests pass）。

5. **响应式 locale 切换** — `THEME_OPTIONS` 之类的"模块顶层数组"如果直接用 `t()` 调用，会在模块加载时固化成首次解析时的 locale。解决方案：把数组构建包装成 `buildXxxOptions()` 函数，store 内部用 `computed(() => buildXxxOptions())` 让 locale 切换触发重新构建。已用于 `stores/theme.ts`、`stores/quote.ts`、`useAIChatRendering.ts`。

6. **死代码删除** — `src/composables/useBacktestRuntime.spec.ts` 不在 vitest config 的 include 模式中（`*.test.{ts,js}` 不匹配 `.spec.ts`），属于死代码。pass-38 直接删除节省 196 strict + 18 CJK。

## 命名空间清单（zh-CN.ts / en-US.ts，2629 keys 各侧）

新增 / 重构的 i18n 命名空间（按 pass 顺序）：

- `nav.*`（pass 之前）— AppLayout 导航菜单
- `workspaceDialogs.*` — 21 个 workspace dialog/card
- `dataPages.*` — views/data/* 13 个页面
- `aiChat.*`, `useAIChatRendering.*` — AI 聊天页 + 渲染助手
- `kb.*`, `kbDoc.*`, `useKnowledgeBasePage.*` — 知识库页
- `useBacktestRuntime.*` — 回测运行时（pre-existing，被复用）
- `gatewayStatus.*` — Gateway 状态页
- `charts.*` — components/charts/* 8 个图表
- `commonUi.*`, `LogViewer.*` — components/common/*
- `aiTrading.*`, `draftExec.*` — AI 交易页 + 草稿执行
- `backtestComp.*` — components/backtest/* 5 个组件
- `newsIntel.*`, `quote.*`, `backtestRt.*` — 新闻情报 + 行情 + 回测 RT
- `aiObs.*`, `portfolio.*`, `userSettings.*` — AI 成本看板 + 投资组合 + 设置
- `instanceActions.*`, `kbShortcuts.*`, `unitRendering.*` — 3 个 composables
- `apiClient.*`, `overfittingRt.*` — API 客户端 + 过拟合检测
- `strategyConst.*`, `themeStore.*` — 策略常量 + 主题
- `scannerPage.*`, `quantTools.*`, `dataMgmt.*` — 3 个工具页
- `backtestPg.*`, `equityResearch.*`, `optionsChain.*` — 3 个分析页
- `promptTpl.*`, `workspaceDetail.*` — 模板治理 + 工作区详情
- `brokerProfiles.*` — broker profile 管理
- `workspaceComp.*`, `optChart.*`, `kbChatStore.*`, `portfolioLedger.*`, `dataUtils.*` — 长尾收尾

## 后续工作

| 候选 | 来源 | 状态 |
|------|------|------|
| Strict scanner 启发式精化（消除 13986 EN 假阳性） | 176 § C 终态 | 推迟，非 176 范围 |
| Vue views > 1500 行拆分 | REFACTORING_BACKLOG § 7 | 顺延 |
| 500-999 行 .vue 收尾 | REFACTORING_BACKLOG § G | 顺延 |
| mypy services 剩余 6 子包 | REFACTORING_BACKLOG § A | 顺延 |

176 § C 自此关闭。
