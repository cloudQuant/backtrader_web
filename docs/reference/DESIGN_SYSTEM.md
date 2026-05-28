# Design System

## 颜色

当前前端颜色体系采用两层契约：

- `src/frontend/src/styles/design-system.scss`
  - 保存原始 palette token 与多主题原始变量，是颜色唯一源头
- `src/frontend/src/style.css`
  - 把原始 token 映射为运行时语义变量，例如 `--primary-color`、`--warning-surface`、`--code-bg-color`

组件应优先使用语义变量，而不是直接写十六进制颜色。常用变量包括：

- `--primary-color`
- `--accent-color`
- `--success-color`
- `--warning-color`
- `--danger-color`
- `--text-color-*`
- `--bg-color-*`
- `--border-color*`

图表色板允许保留在 `src/constants/chartColors.ts`，但不应继续散落在 `*.vue` 中。

## 间距

间距暂不另起一套自定义 token，当前遵循两条规则：

- Tailwind 工具类优先，用于页面布局、栅格、响应式间距
- 在 scoped 样式中，继续沿用 Element Plus 半径、阴影与页面现有节奏，避免再引入新的像素体系

当某个页面需要复用的容器间距模式时，应优先抽为组件样式或布局类，而不是新增硬编码常量。

## 字号

字号继续以现有技术栈为准：

- Tailwind 文本工具类负责大部分页面结构字号
- Element Plus 负责表单、表格、弹层基础字号
- 自定义 scoped 样式只在页面标题、卡片数值、辅助说明文本等局部场景补充

新增页面时应优先复用：

- 标题：`text-2xl` / `text-xl`
- 二级标题：`font-semibold` + `text-base` 或 `text-lg`
- 辅助文本：`12px-14px` 对应 `--text-color-secondary`

## 按钮

按钮颜色以语义 token 为准：

- 主操作：`--primary-color`
- 警示/提醒：`--warning-color` 或 `--warning-surface`
- 危险操作：`--danger-color`
- 次级操作：`--bg-color-card` + `--border-color`

页面内如果需要 inline style 或自绘 SVG，请使用 `var(--primary-color)` 等语义变量，不要直接写品牌色 hex。

## 卡片

卡片类容器遵循以下结构：

- 默认背景：`--bg-color-card`
- 默认边框：`--border-color` 或 `--border-color-light`
- 信息态：`--info-surface` + `--info-border-color`
- 成功态：`--success-surface` + `--success-border-color`
- 警告态：`--warning-surface` + `--warning-border-color`
- 危险态：`--danger-surface` + `--danger-border-color`

线性渐变卡片允许使用语义变量组合，例如从 `--bg-color-card` 渐变到 `--info-surface`，但不要重新发明一套孤立 palette。

## 暗色

暗色契约由 `src/frontend/src/stores/theme.ts` 负责切换主题模式与 `data-theme`，但主题原始颜色值统一放在 `design-system.scss`。这意味着：

- `theme.ts` 不再持有原始 hex palette
- 多主题只负责选择变量组，不负责重新定义颜色真值
- 组件层继续只消费语义变量，不关心当前是 `aurora`、`obsidian` 还是其他主题

当前暗色基线主题包括：

- `obsidian`
- `nebula`
- `solaris`

亮色基线主题包括：

- `aurora`
- `glacier`
- `meridian`
- `verdant`

## 规则

- 不要在 Vue 组件里新增品牌/语义 hex 值
- 新图表色板放入 `src/constants/chartColors.ts`
- 新语义颜色先加到 `design-system.scss` / `style.css`，再在组件中消费
- 多主题差异只放在设计系统层，不向页面组件泄漏主题实现细节
