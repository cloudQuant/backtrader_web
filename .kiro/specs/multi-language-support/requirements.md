# Requirements Document

## Introduction

本特性在 Backtrader Web 前端现有的局部国际化（i18n）基础设施之上，扩展为一套完善的多语言支持方案。当前前端已集成 vue-i18n（Composition API 模式），但仅注册了简体中文（zh-CN）与英文（en-US）两套语言包，且语言切换组件 `LanguageSwitcher.vue` 尚未挂载到任何布局中。

本需求要在主布局顶部 header 中接入语言切换控件（位置介于"主题切换按钮"与"用户下拉菜单"之间），并将受支持语言扩展为：英文（en-US）、简体中文（zh-CN）、日语（ja-JP）、德语（de-DE）、法语（fr-FR）、意大利语（it-IT）、俄语（ru-RU）。同时需要将硬编码为 2 种语言的 i18n 基础设施（配置、`setLocale` 校验、语言标签映射、类型定义）泛化为可支持全部受支持语言，新增对应语言包并保证翻译键覆盖与缺失键回退，持久化用户选择并在刷新后保持，且更新文档语言属性（`<html lang>`）与切换控件的可访问性。

本特性聚焦前端展示文本的国际化，不改变后端 API、不引入服务端多语言存储。

## Glossary
- **Frontend_App**：基于 Vue 3 + TypeScript + Vite + Element Plus + Pinia 构建的前端应用，文件位于 `src/frontend/`。
- **I18n_Module**：i18n 基础设施模块，对应文件 `src/frontend/src/i18n/index.ts`，封装 vue-i18n 实例及 `getStoredLocale`、`setLocale`、`getLocale`、`getLocaleLabel` 等辅助函数。
- **Language_Switcher**：语言切换控件组件，对应文件 `src/frontend/src/components/LanguageSwitcher.vue`。
- **App_Layout**：主布局组件，对应文件 `src/frontend/src/components/common/AppLayout.vue`，其顶部 header 含右侧操作区。
- **Theme_Switcher**：界面风格（主题）切换按钮组件，对应文件 `src/frontend/src/components/common/ThemeSwitcher.vue`。
- **User_Menu**：顶部 header 右侧的用户（admin）下拉菜单（头像 + 用户名）。
- **Supported_Locale**：受支持语言之一，取值集合为 `{ en-US, zh-CN, ja-JP, de-DE, fr-FR, it-IT, ru-RU }`。
- **Locale_Code**：BCP 47 风格语言代码字符串，例如 `zh-CN`。
- **Locale_Bundle**：某一 Supported_Locale 对应的翻译键值消息文件，位于 `src/frontend/src/i18n/locales/`。
- **Translation_Key**：嵌套命名空间下的翻译键，例如 `nav.home`，由 `t()` 函数调用。
- **Fallback_Locale**：当当前语言缺失某 Translation_Key 时回退使用的语言，本特性中为 `en-US`。
- **Persisted_Locale**：持久化存储在浏览器 `localStorage`（键名 `locale`）中的用户语言选择。
- **Locale_Label**：在 Language_Switcher 中展示的语言名称，使用各语言的本族文字自称（如"日本語"）。
- **I18n_Type_Def**：i18n 消息模式的 TypeScript 类型定义文件 `src/frontend/src/i18n/i18n.d.ts`。

## Requirements

### Requirement 1: 语言切换控件的布局位置

**User Story:** 作为使用平台的用户，我希望在顶部 header 固定位置找到语言切换控件，以便随时切换界面语言。

#### Acceptance Criteria

1. WHEN App_Layout 完成顶部 header 渲染，THE App_Layout SHALL 在顶部 header 右侧操作区渲染并显示可见的 Language_Switcher。
2. THE App_Layout SHALL 将 Language_Switcher 放置在右侧操作区中，使其紧邻排列在 Theme_Switcher 之后、User_Menu 之前（即 Theme_Switcher 与 User_Menu 两者中间且彼此相邻，无其他控件插入）。
3. WHILE 视口宽度小于移动端断点（768px），THE App_Layout SHALL 在顶部 header 持续显示 Language_Switcher 而不将其隐藏或折叠。
4. WHEN 视口宽度在小于 768px 与大于等于 768px 之间发生切换，THE App_Layout SHALL 保持 Language_Switcher 位于 Theme_Switcher 之后、User_Menu 之前的相同相对位置。
5. THE Language_Switcher SHALL 复用现有右侧操作区控件之间的相同间距值与对齐方式，使其与相邻的 Theme_Switcher、User_Menu 采用一致的水平间距与垂直对齐基线。
6. IF Language_Switcher 渲染或初始化失败，THEN THE App_Layout SHALL 保持顶部 header 右侧操作区中 Theme_Switcher 与 User_Menu 的可见与可用，并在 Language_Switcher 原位置显示指示加载失败的占位提示。

### Requirement 2: 受支持语言集合

**User Story:** 作为多语言用户，我希望平台提供我所需的语言选项，以便使用熟悉的语言操作界面。

#### Acceptance Criteria

1. THE I18n_Module SHALL 注册且仅注册以下 7 种 Supported_Locale 的 Locale_Bundle：en-US、zh-CN、ja-JP、de-DE、fr-FR、it-IT、ru-RU。
2. WHEN Language_Switcher 的下拉菜单被打开，THE Language_Switcher SHALL 按上述注册顺序（en-US、zh-CN、ja-JP、de-DE、fr-FR、it-IT、ru-RU）为每个 Supported_Locale 各展示恰好一个可选项，且选项总数等于 7。
3. THE Language_Switcher SHALL 使用各语言的本族文字自称作为 Locale_Label 展示（en-US: English；zh-CN: 中文；ja-JP: 日本語；de-DE: Deutsch；fr-FR: Français；it-IT: Italiano；ru-RU: Русский）。
4. WHERE 某选项对应当前生效语言，THE Language_Switcher SHALL 为该选项添加选中态样式（`is-active`）以标识当前语言，且任一时刻处于选中态的选项数量恰好为 1。
5. IF 某 Supported_Locale 的 Locale_Bundle 加载失败或缺失，THEN THE I18n_Module SHALL 回退到默认语言 en-US 并保留其余已成功注册的 Supported_Locale 可用，同时向调用方返回一个标识该 Locale_Bundle 不可用的错误指示。
6. IF 某 Supported_Locale 的 Locale_Label 缺失，THEN THE Language_Switcher SHALL 使用该 Supported_Locale 的标识符（如 en-US）作为该选项的回退展示文本。

### Requirement 3: 切换语言并更新界面文本

**User Story:** 作为用户，我希望选择某语言后界面文本立即随之变化，以便确认切换生效。

#### Acceptance Criteria

1. WHEN 用户从 Language_Switcher 选择一个与当前生效语言不同的 Supported_Locale，THE I18n_Module SHALL 将 vue-i18n 当前生效语言更新为所选 Locale_Code。
2. WHEN vue-i18n 当前生效语言发生变更，THE Frontend_App SHALL 在 1 秒（1000 毫秒）内使用所选语言的 Locale_Bundle 重新渲染当前视图中所有通过 `t()` 解析的可见界面文本。
3. WHEN 用户选择的语言与当前生效语言相同，THE Language_Switcher SHALL 不触发语言变更操作，且保持当前生效语言、界面文本与 Persisted_Locale 不变。
4. IF 传入 `setLocale` 的 Locale_Code 不属于 Supported_Locale 集合，THEN THE I18n_Module SHALL 保持当前生效语言不变、不写入持久化存储，且保持当前界面文本不变。

### Requirement 4: 持久化与刷新后保持

**User Story:** 作为用户，我希望我选择的语言在刷新或重新打开应用后仍然保持，以免每次都要重新设置。

#### Acceptance Criteria

1. WHEN 用户成功切换到某 Supported_Locale，THE I18n_Module SHALL 将该 Locale_Code 写入 `localStorage` 的 `locale` 键作为 Persisted_Locale。
2. IF 写入 `localStorage` 失败（`localStorage` 不可用或写入被拒绝），THEN THE I18n_Module SHALL 保持当前生效语言不变，并向用户呈现指示持久化失败的错误提示。
3. WHEN Frontend_App 初始化，THE I18n_Module SHALL 读取 `localStorage` 的 `locale` 键作为 Persisted_Locale 候选值。
4. IF Persisted_Locale 存在且属于 Supported_Locale 集合，THEN THE I18n_Module SHALL 采用该 Persisted_Locale 作为初始生效语言。
5. IF Persisted_Locale 不存在、为空或不属于 Supported_Locale 集合，THEN THE I18n_Module SHALL 依据浏览器语言进行初始语言推断，且当推断出的 Locale_Code 属于 Supported_Locale 集合时采用该语言作为初始生效语言。
6. IF 浏览器语言推断结果不属于 Supported_Locale 集合，THEN THE I18n_Module SHALL 采用默认 Supported_Locale 作为初始生效语言。

### Requirement 5: 默认语言与浏览器语言推断

**User Story:** 作为首次访问的用户，我希望平台依据我的浏览器语言自动选择合适的初始语言，以获得更友好的初始体验。

#### Acceptance Criteria

1. WHEN 不存在有效 Persisted_Locale 且 `navigator.language` 为非空字符串，THE I18n_Module SHALL 提取 `navigator.language` 中首个连字符（`-`）之前的语言子标签（若不含连字符则取整个字符串），并以不区分大小写方式将其与每个 Supported_Locale 在首个连字符之前的语言子标签进行比对。
2. WHEN 不存在有效 Persisted_Locale 且 `navigator.language` 的语言子标签与某个 Supported_Locale 的语言子标签一致，THE I18n_Module SHALL 选择该唯一匹配的 Supported_Locale 作为初始生效语言。
3. IF 不存在有效 Persisted_Locale 且 `navigator.language` 为空字符串、为 undefined，或其语言子标签无法与任何 Supported_Locale 的语言子标签一致，THEN THE I18n_Module SHALL 采用 en-US 作为初始生效语言。
4. THE I18n_Module SHALL 将语言匹配限定在 Supported_Locale 集合（en-US、zh-CN、ja-JP、de-DE、fr-FR、it-IT、ru-RU）内，对其语言子标签不属于该集合的浏览器语言不作为生效语言采用。

### Requirement 6: 缺失翻译键的回退

**User Story:** 作为使用非英语语言的用户，我希望即使某些文本尚未翻译也能看到可读内容，而非空白或键名。

#### Acceptance Criteria

1. THE I18n_Module SHALL 将 Fallback_Locale 配置为 en-US。
2. IF 当前生效语言的 Locale_Bundle 缺失某被 `t()` 请求的 Translation_Key，THEN THE I18n_Module SHALL 使用 Fallback_Locale（en-US）中对应 Translation_Key 的非空值进行渲染。
3. WHILE 某 Supported_Locale 生效且被 `t()` 请求的 Translation_Key 存在于该 Supported_Locale 的 Locale_Bundle 或 Fallback_Locale 中的至少一个，THE Frontend_App SHALL 将该界面文本渲染为非空白且不等于其原始 Translation_Key 字符串的可读文本。
4. IF 被 `t()` 请求的 Translation_Key 在当前生效语言的 Locale_Bundle 与 Fallback_Locale 中均缺失，THEN THE Frontend_App SHALL 展示该 Translation_Key 原始字符串作为兜底文本，且不中断当前页面其余界面文本的渲染。

### Requirement 7: 泛化 i18n 基础设施

**User Story:** 作为开发者，我希望 i18n 基础设施不再硬编码为 2 种语言，以便集中维护受支持语言集合并降低新增语言的成本。

#### Acceptance Criteria

1. THE I18n_Module SHALL 在单一可维护的数据源中定义 Supported_Locale 集合（至少包含 'zh-CN' 与 'en-US' 两个 Locale_Code），并使 `getStoredLocale`、`setLocale`、`getLocaleLabel` 均引用该数据源而不各自维护副本。
2. WHEN `setLocale` 接收到属于 Supported_Locale 集合的 Locale_Code，THE I18n_Module SHALL 将当前 Locale_Code 切换为该值并持久化。
3. IF `setLocale` 接收到的 Locale_Code 不属于 Supported_Locale 集合，THEN THE I18n_Module SHALL 拒绝该次变更、保持当前 Locale_Code 不变，并返回指示校验失败的结果（且校验依据 Supported_Locale 集合判定，而非硬编码 `['zh-CN','en-US']`）。
4. THE I18n_Module SHALL 使 `getLocaleLabel` 为 Supported_Locale 集合中的每个 Locale_Code 返回其对应的 Locale_Label。
5. IF 传入 `getLocaleLabel` 的 Locale_Code 不属于 Supported_Locale 集合，THEN THE I18n_Module SHALL 返回该 Locale_Code 原值作为标签。
6. WHEN `getStoredLocale` 读取到的存储值不属于 Supported_Locale 集合或不存在，THE I18n_Module SHALL 返回 Supported_Locale 集合中定义的默认 Locale_Code（即 'zh-CN'）。
7. WHEN Language_Switcher 渲染语言选项，THE Language_Switcher SHALL 依据 I18n_Module 暴露的 Supported_Locale 集合动态生成下拉选项（选项数量等于集合元素数量），而非在组件内独立硬编码语言列表。

### Requirement 8: 新增语言包与翻译键覆盖

**User Story:** 作为多语言用户，我希望每种受支持语言都覆盖现有界面文本，以获得一致完整的本地化体验。

#### Acceptance Criteria

1. THE Frontend_App SHALL 在 `src/frontend/src/i18n/locales/` 下为 ja-JP、de-DE、fr-FR、it-IT、ru-RU 各创建一个 Locale_Bundle 文件，共计 5 个文件。
2. THE 每个新增 Locale_Bundle SHALL 采用与 zh-CN、en-US 完全一致的嵌套键结构，即键路径集合与 zh-CN 的键路径集合逐一对应，既无缺失键路径也无多余键路径。
3. THE 每个新增 Locale_Bundle SHALL 为 I18n_Type_Def 中声明的全部 Translation_Key 提供非空字符串值（去除首尾空白后长度不少于 1 个字符），不得存在空字符串、null 或未定义值。
4. WHERE I18n_Type_Def 定义了消息模式，THE 每个新增 Locale_Bundle SHALL 与该类型定义保持结构兼容，使 `npm run typecheck` 在 0 个类型错误的情况下通过。
5. IF 某个新增 Locale_Bundle 缺失任一 Translation_Key 或其值为空，THEN THE Frontend_App SHALL 使该 Translation_Key 回退到 en-US 的对应值，并在控制台输出指示缺失键及其语言的告警信息。

### Requirement 9: 更新文档语言属性

**User Story:** 作为依赖辅助技术或浏览器语言特性的用户，我希望页面的 `lang` 属性与当前语言一致，以便屏幕阅读器与浏览器正确处理内容。

#### Acceptance Criteria

1. WHEN 当前生效语言变更为某 Supported_Locale，THE I18n_Module SHALL 将 `document.documentElement.lang` 设置为该 Supported_Locale 对应的 Locale_Code（BCP 47 格式，取值为 en-US、zh-CN、ja-JP、de-DE、fr-FR、it-IT、ru-RU 之一）。
2. WHEN Frontend_App 初始化完成，THE I18n_Module SHALL 将 `document.documentElement.lang` 设置为初始生效语言对应的 Locale_Code，使其等于该 Supported_Locale 的 BCP 47 取值。
3. THE I18n_Module SHALL 为全部 7 种 Supported_Locale 各定义唯一对应的 `lang` 属性值，映射为 en-US→en-US、zh-CN→zh-CN、ja-JP→ja-JP、de-DE→de-DE、fr-FR→fr-FR、it-IT→it-IT、ru-RU→ru-RU，而非仅区分中英两种。
4. IF 尝试设置的生效语言不属于 Supported_Locale 集合，THEN THE I18n_Module SHALL 保持 `document.documentElement.lang` 的当前值不变。

### Requirement 10: 语言切换控件的可访问性

**User Story:** 作为使用键盘或屏幕阅读器的用户，我希望能够无障碍地操作语言切换控件，以便平等地切换语言。

#### Acceptance Criteria

1. THE Language_Switcher SHALL 为其触发元素提供描述其用途的无障碍标签（accessible name），且该标签为非空文本。
2. THE Language_Switcher SHALL 允许通过键盘 Tab 键将焦点移至其触发元素，使其成为可聚焦元素。
3. WHEN Language_Switcher 触发元素获得键盘焦点，THE Language_Switcher SHALL 显示与未聚焦状态在视觉上可区分的焦点指示样式（如焦点轮廓或边框）。
4. THE Language_Switcher SHALL 通过下拉选项的选中态样式（`is-active`）以视觉方式标识当前生效语言。
5. WHEN Language_Switcher 触发元素拥有键盘焦点且用户按下 Enter 键或空格键，THE Language_Switcher SHALL 打开下拉菜单。
6. WHEN 下拉菜单处于打开状态且用户通过键盘将焦点定位到某个 Supported_Locale 选项后按下 Enter 键，THE Language_Switcher SHALL 选定该选项对应语言并关闭下拉菜单。
7. WHEN 下拉菜单处于打开状态且用户按下 Esc 键，THE Language_Switcher SHALL 关闭下拉菜单并将键盘焦点返回触发元素。

### Requirement 11: 与现有项目约定保持一致

**User Story:** 作为维护者，我希望本特性遵循既有前端代码风格与约定，以便代码可维护且通过现有质量检查。

#### Acceptance Criteria

1. THE Language_Switcher SHALL 采用 `<script setup lang="ts">` 的 Composition API 组件结构并使用 scoped 样式。
2. WHEN 执行 `npm run lint` 与 `npm run typecheck` 时，THE Frontend_App SHALL 使所有新增与修改代码以 0 个错误且 0 个警告通过两项检查。
3. IF 任一新增或修改代码在 `npm run lint` 或 `npm run typecheck` 中产生错误或警告，THEN THE Frontend_App SHALL 将该次检查标记为失败并输出指明失败文件与对应规则的检查结果，且不修改源代码内容。
4. WHERE Locale_Label 为各语言本族自称（不需被翻译），THE Language_Switcher SHALL 在该文本处保留 `i18n-ignore` 注释以标记其不参与翻译的意图。
5. THE Frontend_App SHALL 使 Language_Switcher 的触发样式与 Theme_Switcher 复用相同的尺寸、内外边距、圆角、字体及颜色变量，使二者在同一视图中呈现一致的视觉风格。
6. WHEN 运行现有单元测试套件（含对 vue-i18n 的 mock）时，THE Frontend_App SHALL 使全部既有测试用例 100% 通过且不引入新增失败用例。
