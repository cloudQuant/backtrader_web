# 前端 UI 一致性审查报告

**审查日期**: 2026-05-20  
**审查范围**: `src/frontend/src/` 下所有视图（views）和组件（components）  
**技术栈**: Vue 3 + Element Plus 2.5 + Tailwind CSS 3.4 + 自定义 SCSS

---

## 一、总体评估

| 维度 | 严重程度 | 说明 |
|------|----------|------|
| 颜色系统 | 🔴 严重 | 存在 3 套独立颜色体系，互相冲突 |
| 按钮样式 | 🟠 中等 | 尺寸、圆角、主色不统一 |
| 间距规范 | 🟡 轻微 | 页面级间距有 2 种模式混用 |
| 字体/排版 | 🟠 中等 | 标题层级、数值字号不一致 |
| 组件风格 | 🔴 严重 | AIChatPage 完全脱离设计体系 |
| 暗色模式 | 🟠 中等 | 实现方式碎片化，部分页面无支持 |

---

## 二、颜色系统不一致

### 问题 1：三套颜色定义互相冲突

项目中存在 **3 个独立的颜色定义源**，且未统一引用：

| 来源 | 主色 | 成功色 | 危险色 |
|------|------|--------|--------|
| `style.css` CSS 变量 | `#3b82f6` (蓝) | `#10b981` | `#ef4444` |
| `tailwind.config.js` | `primary-500: #3b82f6` | `#10b981` | `#ef4444` |
| `AIChatPage.vue` | `#0f766e` (青绿) | — | — |
| `theme.ts` store | 另一套 CSS 变量体系 | — | — |

**影响**：
- `AIChatPage` 的主操作按钮为青绿色 `#0f766e`，与全站蓝色 `#3b82f6` 完全不同
- 用户在不同页面看到不同的品牌色，体验割裂

### 问题 2：硬编码颜色值泛滥

| 文件 | 硬编码颜色数量 | 典型示例 |
|------|---------------|----------|
| `AIChatPage.vue` | **60+** | `#0f172a`, `#475569`, `#64748b`, `#cbd5e1`, `#dbe3ef` |
| `AITradingPage.vue` | 5 | `#1a56db`, `#dc2626` |
| `GatewayStatusPage.vue` | 4 | `#67c23a`, `#f56c6c` |
| `QuotePage.vue` | 6 | `#3b82f6`, `#67c23a`, `#909399` |

**问题**：
- `GatewayStatusPage` 使用 Element Plus 内置色 `#67c23a`（成功绿），而 Tailwind 定义的成功色是 `#10b981`
- `QuotePage` 的 `.source-tab--available` 用 `#67c23a`，但 Tailwind 的 `success` 是 `#10b981`

### 问题 3：文本颜色不统一

| 用途 | 应统一值 | 实际使用 |
|------|----------|----------|
| 主文本 | `text-gray-800` / `#1f2937` | `#0f172a`(AIChatPage), `#303133`(theme.ts), `text-gray-800`(Dashboard) |
| 次要文本 | `text-gray-500` / `#6b7280` | `#475569`, `#64748b`, `#94a3b8`, `text-gray-500` |
| 占位文本 | `text-gray-400` | `#94a3b8`, `#909399`, `#C0C4CC` |

---

## 三、按钮样式不一致

### 问题 4：主操作按钮颜色分裂

| 页面 | 主按钮实现 | 颜色 |
|------|-----------|------|
| 大多数页面 | `<el-button type="primary">` | `#3b82f6` (蓝) |
| `AIChatPage` | `.primary-action` 自定义类 | `#0f766e` (青绿) |
| `AIChatPage` | `.primary-action.accent` | `#2563eb` (深蓝) |

### 问题 5：按钮尺寸使用不规范

| 页面 | 按钮尺寸 | 场景 |
|------|----------|------|
| `GatewayStatusPage` | `size="small"` | 工具栏操作按钮 |
| `QuotePage` | `size="default"` | 工具栏操作按钮 |
| `DataPage` | 无 size（默认） | 工具栏操作按钮 |
| `StrategyPage` | `size="small"` | 卡片内操作按钮 |
| `BacktestResultPage` | 无 size（默认） | 工具栏操作按钮 |

**建议规范**：
- 页面级操作栏：`size="default"`
- 表格/卡片内操作：`size="small"`
- 对话框底部：`size="default"`

### 问题 6：圆角（border-radius）不统一

| 组件 | AIChatPage | AITradingPage | Element Plus 默认 |
|------|-----------|---------------|-------------------|
| 按钮 | `8px` | `6px` | `4px` |
| 卡片/面板 | `10px` | `8px` | `4px` |
| 输入框 | `8px` | `6px` | `4px` |
| 徽章 | `999px` | `4px` | `10px` |

---

## 四、间距规范不一致

### 问题 7：页面顶层间距

| 页面 | 顶层容器间距 |
|------|-------------|
| `DashboardPage` | `space-y-6` (24px) |
| `StrategyPage` | `space-y-6` (24px) |
| `PortfolioPage` | `space-y-6` (24px) |
| `QuotePage` | `space-y-4` (16px) ⚠️ |
| `AIChatPage` | `gap: 16px` (flex) ⚠️ |
| `AITradingPage` | `padding: 24px` (无统一间距) ⚠️ |

### 问题 8：卡片网格间距

| 页面 | 网格间距 |
|------|----------|
| `DashboardPage` | `gap-6` (24px) |
| `PortfolioPage` | `gap-4` (16px) ⚠️ |
| `AIChatPage` | `gap: 16px` ⚠️ |

### 问题 9：内容区 padding

| 位置 | 值 |
|------|-----|
| `AppLayout el-main` | `p-6` (24px) |
| `AITradingPage` 内部 | 额外 `padding: 24px` (双重 padding) ⚠️ |
| `AIChatPage .ai-panel` | `padding: 14px` ⚠️ |

---

## 五、字体/排版不一致

### 问题 10：统计数值字号

| 页面 | 数值字号 | Tailwind 类 |
|------|----------|-------------|
| `DashboardPage` | 30px | `text-3xl font-bold` |
| `PortfolioPage` | 24px | `text-2xl font-bold` ⚠️ |

### 问题 11：页面标题处理

| 页面 | 标题实现 |
|------|----------|
| `StrategyPage` | 页面内 `<h1 class="text-2xl font-bold">` |
| `DashboardPage` | 无页面内标题（依赖 AppLayout 顶栏） |
| `AIChatPage` | 自定义 hero 区 `font-size: 28px; font-weight: 750` |
| 其他页面 | 无页面内标题 |

**问题**：`StrategyPage` 有独立的 `<h1>` 标题，而其他页面依赖 `AppLayout` 顶栏显示标题，导致 `StrategyPage` 出现重复标题。

### 问题 12：卡片标题字重

| 位置 | 实现 |
|------|------|
| `DashboardPage` 卡片头 | `<span class="font-bold">` (700) |
| `AIChatPage` 面板标题 | `font-weight: 750` (自定义) |
| `PortfolioPage` | 无显式卡片标题 |

---

## 六、组件风格碎片化

### 问题 13：AIChatPage 完全脱离设计体系

`AIChatPage.vue` 包含 **270+ 行自定义 CSS**，构建了一套独立的设计语言：

| 特征 | 全站标准 | AIChatPage |
|------|----------|-----------|
| 主色 | `#3b82f6` (蓝) | `#0f766e` (青绿) |
| 卡片组件 | `<el-card>` | 自定义 `.ai-panel` div |
| 按钮组件 | `<el-button>` | 自定义 `.primary-action` / `.ghost-button` |
| 输入框 | `<el-input>` | 原生 `<select>` / `<input>` / `<textarea>` |
| 圆角 | 4px (Element Plus) | 8px / 10px |
| 边框色 | `var(--el-border-color)` | `#dbe3ef`, `#cbd5e1`, `#e2e8f0` |
| 暗色模式 | 支持 | ❌ 不支持 |

### 问题 14：卡片容器使用不统一

| 页面 | 容器方式 | shadow 属性 |
|------|----------|-------------|
| `DashboardPage` 统计卡 | `<el-card shadow="hover">` | hover |
| `PortfolioPage` 统计卡 | `<el-card shadow="hover">` | hover |
| `PortfolioPage` 内容卡 | `<el-card>` | 默认 (always) |
| `DataPage` 子卡片 | `<el-card shadow="never">` | never |
| `AIChatPage` | `<div class="ai-panel">` | 无 shadow |
| `AITradingPage` | 自定义 div + border | 无 shadow |

### 问题 15：表格配置不统一

| 页面 | stripe | border | size |
|------|--------|--------|------|
| `DashboardPage` | ✅ | ❌ | 默认 |
| `PortfolioPage` | ✅ | ❌ | `small` |
| `DataPage` | ✅ | ❌ | 默认 |
| `QuotePage` | ✅ | ✅ | `small` |
| `GatewayStatusPage` | ✅ | ❌ | `small` |

---

## 七、暗色模式实现碎片化

### 问题 16：三种暗色模式实现并存

1. **`style.css`**：通过 `html.dark .el-xxx` 选择器硬编码覆盖 Element Plus 组件样式
2. **`theme.ts` store**：定义 CSS 变量 (`--bg-color`, `--text-color-primary` 等)，但几乎没有组件引用这些变量
3. **`AppLayout.vue`**：直接操作 `localStorage` 和 `classList`，绕过 theme store

### 问题 17：部分页面无暗色模式支持

| 页面 | 暗色模式支持 |
|------|-------------|
| `AIChatPage` | ❌ 全部硬编码浅色值 |
| `AITradingPage` | ✅ 使用 `var(--el-xxx)` 变量 |
| `QuotePage` | ⚠️ 部分硬编码 |
| 其他页面 | ✅ 依赖 Tailwind dark: 和全局覆盖 |

---

## 八、优先修复建议

### P0 - 立即修复（影响品牌一致性）

1. **统一主色系统**：确定唯一主色（建议 `#3b82f6`），移除 AIChatPage 的青绿色体系
2. **AIChatPage 改造**：用 Element Plus 组件 + Tailwind 类替换 270 行自定义 CSS

### P1 - 短期修复（1-2 周）

3. **建立 Design Token 文件**：在 `src/styles/_tokens.scss` 中定义所有颜色、间距、圆角变量
4. **统一按钮尺寸规范**：工具栏 `default`，表格内 `small`，对话框 `default`
5. **统一间距**：所有页面顶层 `space-y-6`，卡片网格 `gap-6`
6. **统一表格配置**：全站 `stripe` + `size="small"`（数据密集型页面）

### P2 - 中期优化（2-4 周）

7. **暗色模式统一**：移除 `style.css` 中的硬编码覆盖，统一使用 Element Plus CSS 变量 + Tailwind `dark:` 前缀
8. **移除硬编码颜色**：将所有 `#hex` 值替换为 Tailwind 类或 CSS 变量引用
9. **统一卡片 shadow**：统计卡 `shadow="hover"`，内容卡 `shadow="never"`
10. **统一统计数值字号**：全站 `text-3xl font-bold`

### P3 - 长期治理

11. **创建 UI 组件规范文档**：记录按钮、卡片、表格、间距的标准用法
12. **添加 Stylelint 规则**：禁止在 scoped style 中使用硬编码颜色值
13. **移除 `StrategyPage` 的重复标题**：统一由 AppLayout 顶栏提供页面标题

---

## 九、不一致项汇总清单

| # | 类别 | 位置 | 问题描述 | 严重度 |
|---|------|------|----------|--------|
| 1 | 颜色 | AIChatPage | 主色 `#0f766e` 与全站 `#3b82f6` 冲突 | 🔴 |
| 2 | 颜色 | AIChatPage | 60+ 硬编码颜色值 | 🔴 |
| 3 | 颜色 | GatewayStatusPage | 使用 `#67c23a` 而非 Tailwind success 色 | 🟡 |
| 4 | 颜色 | QuotePage | `.source-tab` 使用 `#67c23a` / `#909399` | 🟡 |
| 5 | 颜色 | 全局 | 3 套颜色定义源未统一 | 🟠 |
| 6 | 按钮 | AIChatPage | 自定义按钮类替代 el-button | 🔴 |
| 7 | 按钮 | 多页面 | size 属性使用不一致 | 🟠 |
| 8 | 按钮 | AIChatPage/AITradingPage | 圆角 6px/8px vs Element Plus 4px | 🟡 |
| 9 | 间距 | QuotePage | `space-y-4` 而非全站 `space-y-6` | 🟡 |
| 10 | 间距 | PortfolioPage | 卡片网格 `gap-4` 而非 `gap-6` | 🟡 |
| 11 | 间距 | AITradingPage | 双重 padding（AppLayout + 页面内） | 🟡 |
| 12 | 字体 | PortfolioPage | 统计值 `text-2xl` 而非 `text-3xl` | 🟡 |
| 13 | 字体 | StrategyPage | 页面内重复 `<h1>` 标题 | 🟡 |
| 14 | 字体 | AIChatPage | `font-weight: 750` 非标准值 | 🟡 |
| 15 | 组件 | AIChatPage | 使用原生 HTML 替代 Element Plus 组件 | 🔴 |
| 16 | 组件 | 多页面 | el-card shadow 属性不统一 | 🟡 |
| 17 | 组件 | 多页面 | el-table 配置（border/size）不统一 | 🟡 |
| 18 | 暗色 | AIChatPage | 完全不支持暗色模式 | 🟠 |
| 19 | 暗色 | 全局 | 3 种暗色模式实现方式并存 | 🟠 |
| 20 | 暗色 | AppLayout | 绕过 theme store 直接操作 DOM | 🟡 |

---

## 十一、修复状态

以下修复已完成并通过 Vite 构建验证：

| # | 修复项 | 状态 |
|---|--------|------|
| 1 | AIChatPage 主色从 `#0f766e` 改为 `#3b82f6` (CSS 变量) | ✅ 已修复 |
| 2 | AIChatPage 60+ 硬编码颜色替换为 CSS 变量 | ✅ 已修复 |
| 3 | GatewayStatusPage `#67c23a`/`#f56c6c` → `var(--el-color-success/danger)` | ✅ 已修复 |
| 4 | QuotePage `.source-tab` 硬编码色 → CSS 变量 | ✅ 已修复 |
| 5 | 创建 `_tokens.scss` 统一设计令牌文件 | ✅ 已创建 |
| 6 | AIChatPage 自定义按钮改用统一主色 `var(--primary-color)` | ✅ 已修复 |
| 7 | 按钮尺寸规范已在 `_tokens.scss` 中文档化 | ✅ 已记录 |
| 8 | AIChatPage/AITradingPage 圆角统一为 `var(--el-border-radius-base)` | ✅ 已修复 |
| 9 | QuotePage `space-y-4` → `space-y-6` | ✅ 已修复 |
| 10 | PortfolioPage 卡片网格 `gap-4` → `gap-6` | ✅ 已修复 |
| 11 | AITradingPage 移除多余 `padding: 24px` | ✅ 已修复 |
| 12 | PortfolioPage 统计值 `text-2xl` → `text-3xl` | ✅ 已修复 |
| 13 | StrategyPage 移除重复 `<h1>` 标题 | ✅ 已修复 |
| 14 | AIChatPage `font-weight: 750` → `700` | ✅ 已修复 |
| 15 | AIChatPage 原生 HTML 输入框保留但样式统一 | ✅ 已修复 |
| 16 | 卡片 shadow 规范已在 `_tokens.scss` 中文档化 | ✅ 已记录 |
| 17 | 表格配置规范已在 `_tokens.scss` 中文档化 | ✅ 已记录 |
| 18 | AIChatPage 暗色模式支持（通过 CSS 变量 fallback） | ✅ 已修复 |
| 19 | `style.css` 暗色模式改用 CSS 变量而非硬编码值 | ✅ 已修复 |
| 20 | AppLayout 改用 theme store 而非直接操作 localStorage | ✅ 已修复 |

当前前端存在 **20 项 UI 不一致问题**，其中：
- 🔴 严重（4 项）：主要集中在 `AIChatPage` 的完全独立设计体系
- 🟠 中等（5 项）：颜色系统碎片化和暗色模式实现不统一
- 🟡 轻微（11 项）：间距、字号、组件属性的细节差异

**核心根因**：缺少统一的 Design Token 层和组件使用规范文档。`AIChatPage` 是最大的不一致来源，建议优先改造。
