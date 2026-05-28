# Accessibility (A11y) Baseline — WCAG 2.1 AA

> Iteration 175 §3 — single source of truth for the project's a11y baseline,
> the `Critical_Page_Set` scan results, and any "necessary exemptions" that
> are tolerated under the AA gate.

## Why this exists

A11y compliance is not a one-time fix; the baseline is enforced on every PR by
the `frontend-a11y` CI job. This document explains:

- which pages are scanned;
- the WCAG conformance level (2.1 AA);
- what `critical` and `serious` axe violations get blocked;
- the limited list of exemptions, each with the WCAG clause being deferred
  and the reason.

## Critical Page Set

The 7 pages enumerated in `requirements.md` Requirement 3.1:

| # | Route | View module | Auth required |
|---|---|---|---|
| 1 | `/login`              | `views/auth/Login*` | no |
| 2 | `/dashboard`          | `views/Dashboard*`  | yes |
| 3 | `/ai-chat`            | `views/AIChatPage`  | yes |
| 4 | `/backtests`          | `views/BacktestList*` (or equivalent) | yes |
| 5 | `/backtests/:id`      | `views/BacktestDetail*` | yes |
| 6 | `/knowledge-base`     | `views/KnowledgeBasePage` | yes |
| 7 | `/strategies`         | `views/Strategy*` | yes |

## Conformance level

- WCAG **2.1 Level AA**, scanned with axe-core via `@axe-core/playwright`
  using `.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])`.
- Lighthouse Accessibility category threshold: `>= 0.9` (90/100). See
  `config/lighthouserc.js`.

## Blocking impact levels

`critical` and `serious` axe violations fail the `frontend-a11y` CI job and
block PR merge. `minor` and `moderate` are surfaced as warnings.

## Hard interaction constraints (Requirement 3.4)

These are baseline expectations every page in the Critical_Page_Set must
already satisfy. Any of the following on a covered page is treated as a
serious violation by axe and will block PR merge:

| # | Constraint | Example fix |
|---|---|---|
| a | Non-decorative `<img>` / icon must have `alt` or `aria-label` | Add `aria-label="刷新数据"` to icon-only refresh button |
| b | All form inputs have explicit `<label>` or `aria-labelledby` | Wrap `<el-input>` with an Element Plus form-item that has a label |
| c | Color contrast ≥ 4.5:1 normal / 3:1 large text & graphics | Use design system colour tokens, see DESIGN_SYSTEM.md |
| d | All interactive elements reachable via Tab / Shift+Tab; focus ring visible | Avoid `outline: none` without a replacement focus indicator |
| e | Modal opens trap focus; close returns focus to invoker | Use Element Plus `<el-dialog>` (handles trap automatically) |

"Non-decorative" is identified as: an image element that does **not** carry
any of `role="presentation"`, `aria-hidden="true"`, or empty `alt=""`.

## Exemptions (necessary)

> Hard cap: ≤ 5 entries (Requirement 3.8). Each entry must reference a WCAG
> clause and be reviewed annually.

| # | Page / Component | WCAG clause | Reason | Owner | Annual review |
|---|---|---|---|---|---|
| _none_ | — | — | At 175 entry, no exemption registered. New entries require an
> RFC and CODEOWNERS approval. | — | — |

## 175 已落地的 a11y 修复（基线工作）

175 推进过程中已在以下组件应用了 a11y 修复，作为 `frontend-a11y` job 首次跑前的预清理：

### `src/components/common/AppLayout.vue` (覆盖 6 个登录后页面的公共 layout)

- 侧边栏 `<el-aside>` 添加 `role="navigation"` 与 `aria-label="主导航"`
- 移动端汉堡按钮：`<div @click>` → `<button type="button">`，附 `aria-label`、`aria-controls`、`aria-expanded`
- 移动端抽屉关闭图标：`<el-icon @click>` → `<button type="button">` 附 `aria-label`
- 移动端抽屉本体：补 `role="dialog"`、`aria-modal="true"`、`aria-label`、`id`（与 `aria-controls` 对应）
- 用户下拉触发器：`<span>` → `<button type="button">` 附 `aria-label`
- 主内容 `<el-main>` 添加 `role="main"`
- 装饰性图标（侧边栏品牌图标、菜单图标、下拉箭头、avatar 占位、`<TrendCharts />` 等）补 `aria-hidden="true"`
- 新增 `:focus-visible` 样式，确保键盘焦点可见（`outline: 2px solid var(--el-color-primary)`）
- `<el-avatar>` 补 `:alt="user?.username || ''"`

### `src/views/LoginPage.vue` (登录页)

- 表单 `<el-form>` 补 `:aria-label="t('auth.login')"` 与 `@submit.prevent="handleLogin"`（支持回车提交）
- 用户名 / 密码 `<el-input>` 补 `:aria-label`（屏幕阅读器需要 — placeholder 不替代 label）
- 输入框补 `autocomplete="username"` / `autocomplete="current-password"`（密码管理器 + a11y 双赢）
- 登录按钮补 `native-type="submit"` + `:aria-label`
- 注册链接补 `:aria-label`

### `src/views/AIChatPage.vue` (AI 对话页)

- 新建会话圆形按钮（icon-only）补 `aria-label="新建会话"`，icon 标 `aria-hidden="true"`
- 会话搜索框补 `aria-label="搜索会话标题"`
- 主对话输入区 `<el-input type="textarea">` 补 `:aria-label="inputPlaceholder"`
- 模型选择 `<el-select>` 补 `aria-label="选择 AI 模型"`

### `src/views/DashboardPage.vue` (页 #2 of 7)

- 4 张统计卡的装饰性 `<el-icon>` 补 `aria-hidden="true"`
- 3 张 Quick Start 卡片：`<div @click>` → `<div role="button" tabindex="0">` + 键盘事件（Enter / Space），并补 `:aria-label` 与 `:focus-visible` 样式

### `src/views/workspace/WorkspaceListPage.vue` (页 #4 of 7 — `/backtest`)

- toolbar 按钮补 `:aria-label` 与 icon `aria-hidden="true"`
- 视图切换 radio-group 补 `:aria-label`，每个 radio-button 补 `:aria-label`（区分 card / table）
- 全量国际化（30+ zh-CN literals → `workspace.*` 命名空间）

### `src/views/BacktestResultPage.vue` (页 #5 of 7 — `/backtest/result/:id`)

- 加载状态补 `role="status"` + `aria-label`
- 错误状态补 `role="alert"`
- 操作按钮补 `:aria-label`，icon 补 `aria-hidden="true"`
- 关键 selector：补 `data-test="backtest-detail"` 与 `data-test="backtest-status"`（smoke test 依赖）+ `data-test="equity-curve"`（同）
- 状态文本通过 `<span class="sr-only">` 注入，对屏幕阅读器可见但视觉不显示

### `src/views/StrategyPage.vue` (页 #7 of 7 — `/strategy`)

- 创建策略按钮补 `:aria-label`，icon `aria-hidden="true"`
- 搜索框补 `aria-label="搜索策略"`
- 类别 radio-group 补 `aria-label="按策略类别过滤"`
- 策略卡 `<el-card>`：补 `role="button" tabindex="0"` + `@keydown.enter` / `@keydown.space.prevent` + `:aria-label="\`策略 ${t.name}\`"`
- 新增 `.strategy-card:focus-visible` 样式

### `src/components/aichat/CitationList.vue` (覆盖 KB Chat / AI Chat)

- 文档列表 `<section>` 补 `:aria-label="'参考文档'"`
- 每个 citation `<button>` 补 `data-test="citation-chip"`（smoke test 依赖）+ `:aria-label`（含序号与标题）
- icon 补 `aria-hidden="true"`

### `src/views/KnowledgeBasePage.vue` (页 #6 of 7 — `/knowledge-base`)

- 知识库搜索 `<input>` 补 `aria-label`
- 其余 `<button>` 已是真实按钮元素，文本可见，a11y 基线达标

### `src/styles/design-system.scss`

- 新增 `.sr-only` 全局工具类：标准实现（position absolute / clip rect / 1px / -1px margin），用于「屏幕阅读器可见、视觉不显示」的内容

> 上述修复后，仍需在首次 `frontend-a11y` CI red line 后由团队继续清理 `BacktestPage` / 剩余 KnowledgeBasePage 子组件的具体违规。175 验收基线为「框架就绪 + 7 页核心结构清理」。

## Re-running the baseline locally

```bash
cd src/frontend
npm ci
npm run build
# In one terminal: serve the built dist (or use vite preview)
npx vite preview --port 4173 &
# In another terminal: run a11y suite
BASE_URL=http://localhost:4173 npx playwright test e2e/a11y/
```

## CI integration

- `.github/workflows/ci.yml` `frontend-a11y` job — required, blocks PR.
- `config/lighthouserc.js` `lighthouse-ci` job — required, blocks PR.
- Failed scans upload Playwright trace + axe violation list as artifact
  (7-day retention).
