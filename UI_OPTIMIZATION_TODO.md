# AI for Investor UI Optimization TODO

Last updated: 2026-07-12

This checklist tracks page-by-page UI modernization work. A page is only marked
`accepted` after implementation evidence is recorded with responsive layout,
theme compatibility, i18n coverage, and relevant build/test checks.

## Acceptance Gates

- Layout is professional for an operational trading product: dense enough for
  repeat use, clear hierarchy, no marketing-style filler.
- Component colors use design-system semantic variables or Element Plus tokens;
  no new component-level hex palettes.
- Text fits in Chinese and English, with no obvious overflow at desktop,
  tablet, and mobile widths.
- Light and dark theme backgrounds remain readable, including card, table,
  border, icon, success, warning, and danger states.
- Empty, loading, and error states are handled where the page loads remote data.
- Verification evidence is recorded in this file.

## Page Inventory

| Status | Area | Route | Component | Priority | Evidence |
| --- | --- | --- | --- | --- | --- |
| accepted | Home | `/` | `src/frontend/src/views/DashboardPage.vue` | P0 | 2026-06-30: redesigned overview, actions, status summary, recent table, empty state; validated with lint/typecheck/unit test. |
| accepted | Auth | `/login` | `src/frontend/src/views/LoginPage.vue` | P0 | 2026-07-01: moved to shared AuthFrame with tokenized layout, workspace preview, language/theme controls; validated with lint/typecheck/unit/smoke. |
| accepted | Auth | `/register` | `src/frontend/src/views/RegisterPage.vue` | P0 | 2026-07-01: moved to shared AuthFrame with tokenized layout, workspace preview, language/theme controls; validated with lint/typecheck/unit/smoke. |
| accepted | Shell | authenticated layout | `src/frontend/src/components/common/AppLayout.vue` | P0 | 2026-07-01: redesigned authenticated shell sidebar/header/subnav/mobile layout; validated with lint/typecheck/unit/smoke. |
| accepted | Investment Research | `/investment/strategies` | `src/frontend/src/views/StrategyPage.vue` | P0 | 2026-07-01: redesigned AI research workspace hero, controls, result/history panels, responsive dark controls; validated with lint/typecheck/unit/smoke. |
| accepted | Investment Research | `/investment/stock-analysis` | `src/frontend/src/views/investment/StockAnalysisPage.vue` | P0 | 2026-07-01: redesigned single-stock research command surface, configuration panels, empty/report states, and dark responsive module tiles; validated with lint/typecheck/unit/smoke. |
| accepted | Strategy Research | `/research/strategies` | `src/frontend/src/views/StrategyPage.vue` | P0 | 2026-07-01: redesigned strategy management hero, metrics, library filters, strategy cards, and owned-strategy table shell; validated with lint/typecheck/unit/smoke. |
| accepted | Strategy Research | `/research/workspaces` | `src/frontend/src/views/workspace/WorkspaceListPage.vue` | P0 | 2026-07-01: redesigned research workspace list hero, metrics, loading/empty/list states, and workspace cards; validated with lint/typecheck/unit/smoke. |
| accepted | Strategy Research | `/research/workspaces/:id` | `src/frontend/src/views/workspace/WorkspaceDetailPage.vue` | P0 | 2026-07-01: redesigned workspace detail hero, metrics, tab panel, localized nav/detail labels, and dark table shell; validated with lint/typecheck/unit/smoke. |
| accepted | Strategy Research | `/research/backtests/:id` | `src/frontend/src/views/BacktestResultPage.vue` | P0 | 2026-07-01: redesigned backtest result hero, KPI summary, performance/diagnostics/chart panels, localized backtest labels, and dark child-card/table shell; validated with lint/typecheck/unit/smoke. |
| accepted | Strategy Research | `/research/backtests/legacy` | `src/frontend/src/views/BacktestPage.vue` | P1 | 2026-07-01: redesigned legacy backtest launch workbench, summary/progress/latest-result panels, themed metrics/history components, and localized runtime messages; validated with lint/typecheck/unit/smoke. |
| accepted | Strategy Research | `/research/tools` | `src/frontend/src/views/QuantToolsPage.vue` | P1 | 2026-07-01: redesigned quant-tool registry/call console/result workbench with mobile card directory; validated with lint/typecheck/unit/smoke. |
| accepted | Market Data | `/data/market` | `src/frontend/src/views/data/DataMarketPage.vue` | P0 | 2026-07-01: redesigned market data workbench shell, hero metrics, themed chart/catalog/detail surfaces, and dark token coverage; validated with lint/typecheck/unit/smoke. |
| accepted | Market Data | `/data/quote` | `src/frontend/src/views/QuotePage.vue` | P0 | 2026-07-01: redesigned realtime quote console, source/status metrics, filter toolbar, themed table, dialogs, and dark K-line drawer; validated with lint/typecheck/unit/smoke. |
| accepted | Market Data | `/data/intelligence/news` | `src/frontend/src/views/NewsIntelligencePage.vue` | P1 | 2026-07-01: redesigned news intelligence desk, source governance panel, analysis/import/filter controls, themed table, and dark source dialog; validated with lint/typecheck/unit/smoke. |
| accepted | Market Data | `/data/intelligence/scanners` | `src/frontend/src/views/ScannerPage.vue` | P1 | 2026-07-01: redesigned scanner command desk with hero metrics, plan/live-run panels, scan overview, candidate table, and dark plan/pool dialog; validated with lint/typecheck/unit/smoke. |
| accepted | Market Data | `/data/tables` | `src/frontend/src/views/data/DataTablesPage.vue` | P1 | 2026-07-01: redesigned data table catalog with warehouse hero metrics, search workbench, themed status table, pagination, and mobile-safe layout; validated with lint/typecheck/unit/smoke. |
| accepted | Market Data | `/data/tables/:id` | `src/frontend/src/views/data/DataTableDetailPage.vue` | P1 | 2026-07-01: redesigned data table profile with hero metrics, metadata cards, themed schema/preview workbench, dark pagination, and mobile-safe table preview; validated with lint/typecheck/unit/smoke. |
| accepted | Market Data | `/data/topics` | `src/frontend/src/views/data/DataTopicsPage.vue` | P1 | 2026-07-01: redesigned data topic hub with stream controls, topic catalog, mobile topic cards, dark table/loading states, and payload inspector; validated with lint/typecheck/unit/smoke. |
| accepted | Trading | `/trading/workspaces` | `src/frontend/src/views/workspace/WorkspaceListPage.vue` | P0 | 2026-07-01: added trading-specific operations summary, readiness table state, dark-safe status pills, localized execution labels, and mobile-verified trading workspace list; validated with lint/typecheck/unit/smoke. |
| accepted | Trading | `/trading/:id` | `src/frontend/src/views/workspace/WorkspaceDetailPage.vue` | P0 | 2026-07-01: added trading runtime/readiness detail panel, trading-specific hero metrics and panel copy, dark-safe trading unit overview cards, localized readiness checks, and mobile-verified detail layout; validated with lint/typecheck/unit/smoke. |
| accepted | Trading | `/trading/ai` | `src/frontend/src/views/AITradingPage.vue` | P1 | 2026-07-01: redesigned AI trading into a command desk with execution mode controls, guardrail metrics, account context, parsed-response panel, and audit history; validated with lint/typecheck/unit/smoke. |
| accepted | Portfolio | `/portfolio/overview` | `src/frontend/src/views/PortfolioPage.vue` | P0 | 2026-07-01: redesigned portfolio overview into a risk workbench with hero, metrics, workspace scope, themed tabs, charts, and dark responsive surfaces; validated with lint/typecheck/unit/smoke. |
| accepted | Knowledge Base | `/ai/chat` | `src/frontend/src/views/AIChatPage.vue` | P0 | 2026-07-01: redesigned knowledge Q&A workbench hero, retrieval status, mode toolbar, three-panel chat workspace, themed message/context surfaces, and responsive composer; validated with lint/typecheck/unit/smoke. |
| accepted | Knowledge Base | `/ai/knowledge-base` | `src/frontend/src/views/KnowledgeBasePage.vue` | P0 | 2026-07-01: redesigned knowledge-base management workbench hero, metrics, themed library/document/detail panels, and retrieval dialog; validated with lint/typecheck/unit/smoke. |
| accepted | Knowledge Base | `/ai/knowledge-base/:id/documents/:docId` | `src/frontend/src/views/KnowledgeBaseDocumentPage.vue` | P1 | 2026-07-01: redesigned document reading workspace hero, metrics, reader/source/metadata panels, and themed AI side panel; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/data/scripts` | `src/frontend/src/views/data/DataScriptsPage.vue` | P1 | 2026-07-01: redesigned data-script governance hero, metrics, registry workbench, responsive script cards, and dark-safe config shell; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/data/scripts/:id` | `src/frontend/src/views/data/DataScriptDetailPage.vue` | P1 | 2026-07-01: redesigned data-script detail profile with hero, metrics, configuration/run/dependency panels, admin-safe config-route actions, and dark responsive states; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/data/tasks` | `src/frontend/src/views/data/DataTasksPage.vue` | P1 | 2026-07-01: redesigned scheduled-task governance hero, metrics, registry table, responsive task cards, and config execution-route actions; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/data/executions` | `src/frontend/src/views/data/DataExecutionsPage.vue` | P1 | 2026-07-01: redesigned execution observability hero, metrics, filter registry, desktop table, responsive execution cards, and detail/retry surfaces; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/data/sync` | `src/frontend/src/views/data/DataSyncPage.vue` | P1 | 2026-07-01: redesigned database sync console with connection/config metrics, direct-MySQL form, responsive upload/download/history surfaces, and active-task coverage; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/data/interfaces` | `src/frontend/src/views/data/DataInterfacesPage.vue` | P1 | 2026-07-01: redesigned AkShare interface registry with hero metrics, filter workbench, responsive interface cards, and detail drawer; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/data/governance` | `src/frontend/src/views/data/DataGovernancePage.vue` | P1 | 2026-07-01: redesigned data connection governance with provider registry, endpoint workbench, preview/job drawer, and responsive endpoint cards; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/data/airflow` | `src/frontend/src/views/data/AirflowDagsPage.vue` | P2 | 2026-07-01: redesigned Airflow DAG operations with orchestration hero, backend/DAG metrics, searchable control plane, responsive DAG cards, and recent-run drawer; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/ai/providers` | `src/frontend/src/views/config/AIProviderConfigPage.vue` | P1 | 2026-07-01: redesigned AI provider control plane with model-routing hero, provider/key/model metrics, searchable registry, responsive provider cards, and secure editor sections; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/ai/prompt-governance` | `src/frontend/src/views/PromptTemplatesPage.vue` | P1 | 2026-07-01: redesigned Prompt governance with control-plane hero, template/version metrics, authoring panel, searchable version registry, responsive template cards, and render-test drawer; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/ai/observability` | `src/frontend/src/views/AIObservabilityPage.vue` | P1 | 2026-07-01: redesigned AI cost observability with reliability hero, cost/token/failure metrics, scoped filters, usage/failure/slow-call workbench, responsive diagnostics cards, and daily trend strip; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/config/gateways` | `src/frontend/src/views/GatewayStatusPage.vue` | P1 | 2026-07-01: redesigned gateway operations control plane with health hero, connected/healthy/symbol/order metrics, filtered registry, responsive gateway cards/table, and existing connect/disconnect flow; validated with lint/typecheck/unit/smoke. |
| accepted | Config Center | `/admin/settings` | `src/frontend/src/views/SettingsPage.vue` | P2 | 2026-07-01: redesigned account/settings console with identity hero, account/AI usage metrics, profile and password panels, personal model preference, product info, and full supported-locale settings copy; validated with lint/typecheck/unit/smoke. |

## Acceptance Log

### 2026-06-30 - Dashboard

- Scope: `DashboardPage.vue`, dashboard locale keys, dashboard unit test.
- UI changes: added an operations overview band, tokenized metric cards, keyboard
  accessible quick actions, compact run-health summary, responsive recent
  backtest table, and a first-run empty state.
- Theme/i18n: removed page-level gray/brand utility colors in favor of semantic
  CSS variables; added matching dashboard strings across all locale files.
- Verification:
  - `npx eslint --max-warnings=0 src/views/DashboardPage.vue src/__tests__/views/Dashboard.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run typecheck`
  - `npm run test -- --run src/__tests__/views/Dashboard.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - Playwright/Chrome smoke with mocked Dashboard APIs:
    `zh-CN` light desktop, `en-US` dark tablet, `en-US` dark mobile; all rendered
    4 stat cards, 3 quick actions, 3 health items, recent table, and 0 detected
    overflow issues. Screenshots: `src/frontend/artifacts/ui-dashboard/*.png`.
- 2026-07-01 follow-up: App shell dark-mode smoke exposed Dashboard custom
  cards and Element Plus striped rows using light backgrounds under obsidian.
  Updated Dashboard custom surfaces to runtime theme variables and added a
  global dark striped-table override in `style.css`; revalidated through the
  shell smoke below.

### 2026-07-01 - Auth Login And Register

- Scope: `LoginPage.vue`, `RegisterPage.vue`, shared `AuthFrame.vue`, auth
  locale keys, Login/Register unit tests.
- UI changes: replaced the blue/purple centered card with a professional
  two-panel auth surface: secure form card, compact product preview, status
  metrics, language switcher, and theme switcher.
- Theme/i18n: auth pages initialize the theme store before login, use semantic
  CSS variables for backgrounds, borders, text, icons, chart bars, and status
  chips; added localized auth strings across all locale files.
- Verification:
  - `npx eslint --max-warnings=0 src/components/auth/AuthFrame.vue src/views/LoginPage.vue src/views/RegisterPage.vue src/__tests__/views/LoginPage.test.ts src/__tests__/views/RegisterPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run typecheck`
  - `npm run test -- --run src/__tests__/views/LoginPage.test.ts src/__tests__/views/RegisterPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - Playwright/Chrome smoke:
    `/login` `zh-CN` aurora desktop, `/login` `en-US` obsidian mobile,
    `/register` `en-US` obsidian tablet, `/register` `ja-JP` verdant mobile;
    all rendered the auth form, preview metrics, toolbar controls, correct
    theme mode, and 0 detected overflow issues. Screenshots:
    `src/frontend/artifacts/ui-auth/*.png`.

### 2026-07-01 - Authenticated Shell

- Scope: `AppLayout.vue`, shell smoke screenshots, and the dark table stripe
  token fix in `style.css`.
- UI changes: upgraded the authenticated frame with a stronger product brand
  block, tokenized sidebar navigation, active route treatment, compact header
  hierarchy, structured subnav, improved user menu trigger, mobile hamburger
  behavior, and a cleaner main content surface.
- Theme/i18n: shell surfaces use semantic variables for sidebar, header,
  subnav, focus, and main background; smoke covered Chinese, English, and
  Japanese labels under aurora, obsidian, and verdant.
- Verification:
  - `npx eslint --max-warnings=0 src/components/common/AppLayout.vue src/views/DashboardPage.vue src/__tests__/components/common/AppLayout.test.ts src/__tests__/views/Dashboard.test.ts`
  - `npm run typecheck`
  - `npm run test -- --run src/__tests__/components/common/AppLayout.test.ts src/__tests__/views/Dashboard.test.ts`
  - Playwright/Chrome smoke with mocked Dashboard APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP` verdant mobile;
    all rendered header, main surface, expected desktop sidebar or mobile
  hamburger, correct theme mode, dark Dashboard cards, dark striped table
    rows, and 0 detected overflow issues. Screenshots:
    `src/frontend/artifacts/ui-shell/*.png`.

### 2026-07-01 - Investment AI Research

- Scope: `/investment/strategies` in `StrategyPage.vue`, strategy locale keys,
  and the global dark Element Plus select/input-number token fix in `style.css`.
- UI changes: added an investment research hero with live workflow metrics,
  hid the single AI tab chrome on this route, split the page into professional
  research input and research output panels, tightened form/result/history
  spacing, improved empty and task states, and made long labels responsive.
- Theme/i18n: added localized hero/panel strings for Chinese, English,
  Japanese, German, French, Italian, and Russian; dark obsidian controls now use
  runtime theme variables instead of light Element defaults.
- Verification:
  - `npx eslint --max-warnings=0 src/views/StrategyPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run test -- --run src/__tests__/views/StrategyPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked Strategy/AI research APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP` verdant mobile,
    `de-DE` meridian narrow; all rendered the hero, 2 panels, 4 metrics,
    hidden single-tab header, correct theme mode, themed dark controls, and
    0 detected overflow issues. Screenshots:
    `src/frontend/artifacts/ui-investment-strategies/*.png`.

### 2026-07-01 - Investment Stock Analysis

- Scope: `/investment/stock-analysis` in `StockAnalysisPage.vue`, stock analysis
  locale keys, and responsive/dark control states inside the single-stock
  research workflow.
- UI changes: upgraded the page into a command surface plus workbench layout
  with hero metrics, compact analysis controls, module tiles, run profile,
  report output panel, empty preview state, and responsive mobile/tablet
  stacking. Fixed dark selected-module contrast and tablet preview label wraps.
- Theme/i18n: page styles use semantic CSS variables with no component-level
  hex colors; added `stockAnalysis` strings across Chinese, English, Japanese,
  German, French, Italian, and Russian so the route does not fall back to
  English in high-visibility UI.
- Verification:
  - `npx eslint --max-warnings=0 src/views/investment/StockAnalysisPage.vue src/__tests__/views/StockAnalysisPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run test -- --run src/__tests__/views/StockAnalysisPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth/model APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP` verdant mobile,
    `ru-RU` meridian narrow; all rendered 4 hero metrics, 5 module tiles,
    expected panels, correct theme/locale, no preview label overflow, no page or
    console errors, no detected horizontal overflow, and dark controls/module
    tiles were non-white. Screenshots:
    `src/frontend/artifacts/ui-stock-analysis/*.png`.

### 2026-07-01 - Strategy Management

- Scope: `/research/strategies` in `StrategyPage.vue`, strategy management
  locale keys, and tokenized strategy library card presentation.
- UI changes: added a dedicated strategy management hero with action and four
  operational metrics, replaced loose utility layout with structured library
  and table panels, improved category filters, and made template cards inherit
  semantic theme tokens with responsive button wrapping.
- Theme/i18n: management hero and metric labels are localized for Chinese,
  English, Japanese, German, French, Italian, and Russian; management surfaces,
  cards, tabs, filters, and dark inputs use design-system variables.
- Verification:
  - `npx eslint --max-warnings=0 src/views/StrategyPage.vue src/views/strategy-components/StrategyTemplateCard.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run test -- --run src/__tests__/views/StrategyPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked Strategy APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP` verdant mobile,
    `ru-RU` meridian narrow; all rendered 4 management metrics, 6 template
    cards, create action, localized hero text, no AI research tab on the
    strategy management route, no page or console errors, no detected
    horizontal overflow, and dark search/card backgrounds were non-white.
    Screenshots: `src/frontend/artifacts/ui-research-strategies/*.png`.

### 2026-07-01 - Research Workspaces

- Scope: `/research/workspaces` in `WorkspaceListPage.vue`,
  `WorkspaceCard.vue`, and workspace locale keys.
- UI changes: added a route-aware research/trading workspace hero, primary
  create action, card/table view controls, four operational metrics, structured
  list panel, custom loading/empty states, responsive card grid, and tokenized
  workspace card typography/actions.
- Theme/i18n: added workspace list hero, metric, view-mode, and panel strings
  across Chinese, English, Japanese, German, French, Italian, and Russian;
  replaced fixed utility colors in workspace cards with semantic theme
  variables so dark obsidian cards remain readable.
- Verification:
  - `npx eslint --max-warnings=0 src/components/workspace/WorkspaceCard.vue src/views/workspace/WorkspaceListPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run test -- --run src/__tests__/views/workspace/WorkspaceListPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked Workspace APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP` verdant mobile,
    `ru-RU` meridian narrow; all rendered the localized hero, 4 metrics,
    3 workspace cards, correct theme mode, no raw i18n keys, no page or console
    errors, no detected horizontal overflow, and dark workspace surfaces plus
    card body text passed non-white/readability checks. Screenshots:
    `src/frontend/artifacts/ui-research-workspaces/*.png`.

### 2026-07-01 - Research Workspace Detail

- Scope: `/research/workspaces/:id` in `WorkspaceDetailPage.vue`, workspace
  detail locale keys, high-visibility navigation domain labels, and the new
  `WorkspaceDetailPage` unit test.
- UI changes: added a professional workspace detail hero, status badge,
  data-source action, created/updated metadata, four operational metrics,
  structured strategy-units/results panel, themed border-card tabs, and
  tokenized loading/empty states. Kept the heavy unit toolbar inside the
  content panel instead of the global header for better tablet/mobile layout.
- Theme/i18n: localized workspace detail strings for Chinese, English,
  Japanese, German, French, Italian, and Russian; added missing navigation
  domain labels so the shell no longer falls back to English on non-English
  strategy-research pages. Dark obsidian tabs/table headers use semantic theme
  variables rather than light Element Plus defaults.
- Verification:
  - `npx eslint --max-warnings=0 src/views/workspace/WorkspaceDetailPage.vue src/__tests__/views/workspace/WorkspaceDetailPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run test -- --run src/__tests__/views/workspace/WorkspaceDetailPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked Workspace detail/unit/status
    APIs: `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP` verdant
    mobile, `ru-RU` meridian narrow; all rendered the localized shell/domain
    label, detail hero, 4 metrics, strategy-units table with 3 rows, correct
    theme mode, no raw detail i18n keys, no page or console errors, no detected
    horizontal page overflow, and dark hero/panel/tabs/table surfaces plus body
    text passed non-white/readability checks. Screenshots:
    `src/frontend/artifacts/ui-research-workspace-detail/*.png`.

### 2026-07-01 - Research Backtest Result

- Scope: `/research/backtests/:id` in `BacktestResultPage.vue` and backtest
  locale keys.
- UI changes: replaced the loose result layout with a structured result hero,
  status tag, export/back actions, task metadata, four KPI cards, dedicated
  performance panel, strategy diagnostics grid, themed chart tabs, annual
  summary grid, and tokenized loading/error states.
- Theme/i18n: moved BacktestResultPage strings into the canonical `backtest`
  namespace for Chinese and English, added localized backtest overrides for
  Japanese, German, French, Italian, and Russian, and added scoped theme fixes
  for nested score/overfitting/explanation cards and trade tables in dark mode.
- Verification:
  - `npx eslint --max-warnings=0 src/views/BacktestResultPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run test -- --run src/i18n/__tests__/locale-completeness.test.ts src/__tests__/navigation/capabilities.test.ts src/__tests__/components/common/AppLayout.test.ts src/__tests__/views/BacktestResultPage.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked analytics and strategy
    diagnostics APIs: `zh-CN` aurora desktop, `en-US` obsidian tablet,
    `ja-JP` verdant mobile, `ru-RU` meridian narrow; all rendered the localized
    hero, 4 KPI cards, performance panel, diagnostics cards, chart tabs,
    correct theme mode, no raw `backtest.*` keys, no page/API errors, no
    detected horizontal overflow, and dark panels/cards were non-white.
    Screenshots: `src/frontend/artifacts/ui-backtest-result/*.png`.

### 2026-07-01 - Research Legacy Backtest Launcher

- Scope: `/research/backtests/legacy` in `BacktestPage.vue`,
  `BacktestMetricsPanel.vue`, `BacktestHistoryTable.vue`, and backtest runtime
  locale keys.
- UI changes: replaced the single loose form card with a professional launch
  workbench: hero metrics, run actions, strategy/parameter setup sections,
  submission summary, live progress panel, latest-result shortcut, themed
  result metrics/equity panel, analysis callout, and tokenized history table.
- Theme/i18n: localized `backtestPg`, core `backtest` labels, and
  `backtestRt` runtime toast messages for Chinese, English, Japanese, German,
  French, Italian, and Russian. Removed fixed gray utility styling from the
  metrics/history child components so dark obsidian cards, tables, and chart
  shells use semantic variables.
- Verification:
  - `npx eslint --max-warnings=0 src/views/BacktestPage.vue src/components/backtest/BacktestMetricsPanel.vue src/components/backtest/BacktestHistoryTable.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run test -- --run src/__tests__/views/BacktestPage.test.ts src/__tests__/views/BacktestResultPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked strategy templates, template
    config, backtest history, and a completed WebSocket run: `zh-CN` aurora
    desktop, `en-US` obsidian tablet, `ja-JP` verdant mobile, `ru-RU` meridian
    narrow; all rendered localized launch hero, 4 stats, setup/summary/history
    panels, completed result metrics, localized runtime toast, correct theme
    mode, no raw i18n keys, no page/API errors, no detected horizontal
    overflow, and dark panels were non-white. Screenshots:
    `src/frontend/artifacts/ui-backtest-legacy/*.png`.

### 2026-07-01 - Research Quant Tools

- Scope: `/research/tools` in `QuantToolsPage.vue` and `quantTools` locale
  keys.
- UI changes: replaced the basic quant-tool page with a registry hero,
  operational metrics, structured call console, result panel, quick tool
  summary, and a full tool directory. Mobile routes now use stacked tool cards
  instead of a horizontally scrolling table.
- Theme/i18n: localized the route for Chinese, English, Japanese, German,
  French, Italian, and Russian; all page surfaces, inputs, JSON previews,
  result blocks, and directory cards use semantic CSS/theme variables.
- Verification:
  - `npx eslint --max-warnings=0 src/views/QuantToolsPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run test -- --run src/__tests__/views/QuantToolsPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth and quant-tool APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP` verdant mobile,
    `ru-RU` meridian narrow; all rendered localized hero/console/directory
    sections, 4 stats, successful tool call result, correct theme mode, mobile
    card directory, no page or console errors, and no detected horizontal
    overflow. Screenshots: `src/frontend/artifacts/ui-quant-tools/*.png`.

### 2026-07-01 - Market Data Workbench

- Scope: `/data/market` via `DataMarketPage.vue` and `DataPage.vue`, plus
  `dataMgmt` locale keys.
- UI changes: upgraded the historical-data route into a market data workbench
  with a stronger query hero, provider/status metrics, tokenized asset tabs,
  responsive query controls, themed overview/KPI/chart/catalog/detail/table
  sections, and clearer data-family coverage panels.
- Theme/i18n: added market workbench hero strings to Chinese and English; other
  locale bundles inherit the canonical key structure. Replaced fixed page
  colors with semantic variables, moved ECharts colors to runtime theme
  variables, and added scoped dark-mode overrides for tags and default buttons.
- Verification:
  - `npx eslint --max-warnings=0 src/views/DataPage.vue src/views/data/DataMarketPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/DataPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, market lookup, and table
    metadata APIs: `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP`
    verdant mobile, `ru-RU` meridian narrow; all rendered the workbench hero,
    7 asset tabs, 4 hero stats, 4 KPI cards, 3 data-family cards, nonblank
    chart canvas, correct dark-class state, no page or console errors, no
    detected horizontal overflow, and dark default buttons were non-white.
    Screenshots: `src/frontend/artifacts/ui-data-market/*.png`.

### 2026-07-01 - Realtime Quote Console

- Scope: `/data/quote` in `QuotePage.vue` and quote locale keys.
- UI changes: replaced the loose utility layout with a realtime quote console:
  source-health hero, four operational metrics, themed source switcher,
  structured filter/refresh toolbar, dedicated realtime quote table panel,
  tokenized add-symbol and column dialogs, and a dark-compatible K-line drawer.
- Theme/i18n: added Chinese and English quote-console strings; other locale
  bundles inherit the canonical key structure. Replaced page-level hardcoded
  colors with semantic variables, themed tags/buttons/inputs/table states, and
  moved chart drawer chrome onto dark-aware global overrides.
- Verification:
  - `npx eslint --max-warnings=0 src/views/QuotePage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/QuotePage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, quote sources, ticks,
    symbols, and chart APIs: `zh-CN` aurora desktop, `en-US` obsidian tablet,
    `ja-JP` verdant mobile, `ru-RU` meridian narrow; all rendered the quote
    hero, 3 source tabs, 4 stats, table rows, correct dark-class state, no page
    or console errors, no detected horizontal overflow, dark buttons were
    non-white, and the dark K-line drawer rendered a nonblank canvas.
    Screenshots: `src/frontend/artifacts/ui-data-quote/*.png`.

### 2026-07-01 - News Intelligence Desk

- Scope: `/data/intelligence/news` in `NewsIntelligencePage.vue` and
  `newsIntel` locale keys.
- UI changes: replaced the single-card utility page with a news intelligence
  desk: event-impact hero, four metrics, source governance summary, structured
  headline analysis toolbar, article import controls, filter panel, themed
  realtime article table, and a source configuration dialog for RSS presets.
- Theme/i18n: added Chinese and English strings for the new sections; other
  locale bundles inherit the canonical English structure. Replaced Tailwind
  surface colors with semantic variables and corrected dark-mode surfaces to
  use `--bg-color` instead of the light compatibility `--bg-color-card`.
- Verification:
  - `npx eslint --max-warnings=0 src/views/NewsIntelligencePage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/NewsIntelligencePage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth and news-intelligence APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet plus dark source dialog,
    `ja-JP` verdant mobile, `ru-RU` meridian narrow; all rendered the desk hero,
    4 stats, 3 article rows, correct theme mode, no page or console errors, no
    detected document-level horizontal overflow, and non-white dark dialog
    surfaces. Screenshots:
    `src/frontend/artifacts/ui-news-intelligence/*.png`.

### 2026-07-01 - Conditional Scanner Desk

- Scope: `/data/intelligence/scanners` in `ScannerPage.vue` and `scannerPage`
  locale keys.
- UI changes: upgraded the scanner page into a command desk with a metric hero,
  saved-plan center, instant-run panel, active DSL condition preview, scan
  overview cards, candidate result table, and a dark-compatible plan/pool
  editor dialog that keeps pool, indicator, custom universe, and result-table
  workflows together.
- Theme/i18n: added Chinese and English scanner-desk strings; other locale
  bundles inherit the canonical English structure. Replaced fixed surface
  styling with scoped semantic variables, corrected dark surfaces to use
  `--bg-color`, and themed metric/result pills, tables, dialogs, and mobile
  stacked controls.
- Verification:
  - `npx eslint --max-warnings=0 src/views/ScannerPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/ScannerPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, universe pools, scanner
    plans, plan runs, task, and run APIs: `zh-CN` aurora desktop, `en-US`
    obsidian tablet plus dark plan/pool dialog, `ja-JP` verdant mobile,
    `ru-RU` meridian narrow; all rendered the scanner hero, 4 hero stats, 5
    scan overview metrics, 3 candidate rows, correct theme mode, no page or
    console errors, no detected document-level horizontal overflow, and
    non-white dark dialog surfaces. Screenshots:
    `src/frontend/artifacts/ui-scanners/*.png`.

### 2026-07-01 - Data Table Catalog

- Scope: `/data/tables` in `DataTablesPage.vue` and `dataPages` locale keys.
- UI changes: upgraded the data-table list into a warehouse catalog with a
  metric hero, search workbench, total-count status pill, richer table-name
  metadata, row-count and update-status pills, empty state, themed pagination,
  and a mobile-safe table without fixed-column overlap.
- Theme/i18n: added Chinese and English catalog strings; other locale bundles
  inherit the canonical English structure. Replaced Element/Tailwind defaults
  with scoped semantic variables, including dark-safe table and pagination
  surfaces that use `--bg-color`.
- Verification:
  - `npx eslint --max-warnings=0 src/views/data/DataTablesPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/i18n/__tests__/locale-completeness.test.ts src/__tests__/api/akshare.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth and data-table APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP` verdant mobile,
    `ru-RU` meridian narrow; all rendered the catalog hero, 4 stats, 3 table
    rows, correct theme mode, no page or console errors, no detected
    document-level horizontal overflow, and non-white dark pager surfaces.
    Screenshots: `src/frontend/artifacts/ui-data-tables/*.png`.

### 2026-07-01 - Data Table Profile

- Scope: `/data/tables/:id` in `DataTableDetailPage.vue` and `dataPages`
  locale keys.
- UI changes: upgraded the detail page into a table profile with a compact hero,
  row/column/status/coverage metrics, metadata cards, schema and preview tabs,
  themed schema chips, sample-row table, empty/error alerts, and stable mobile
  stacking for long table names and date ranges.
- Theme/i18n: added Chinese and English detail strings; other locale bundles
  inherit the canonical English structure. Replaced light Element defaults with
  scoped semantic variables, including dark-safe table, card, pill, and
  pagination surfaces that use runtime theme tokens.
- Verification:
  - `npx eslint --max-warnings=0 src/views/data/DataTableDetailPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/i18n/__tests__/locale-completeness.test.ts src/__tests__/api/akshare.test.ts src/__tests__/router/index.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth and data-table detail APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet plus preview tab,
    `ja-JP` verdant mobile, `ru-RU` meridian narrow; all rendered the profile
    hero, 4 stats, metadata cards, schema rows, preview rows, correct theme
    mode, no page or console errors, no detected document-level horizontal
    overflow, and non-white dark pager surfaces. Screenshots:
    `src/frontend/artifacts/ui-data-table-detail/*.png`.

### 2026-07-01 - Data Topic Hub

- Scope: `/data/topics` in `DataTopicsPage.vue`, data-topic unit test, and
  `dataPages` locale keys.
- UI changes: upgraded the topic page into a real-time data-topic hub with a
  metric hero, refresh actions, subscription console, current stream URL,
  WebSocket gateway metrics, topic catalog, cache/error/status pills, mobile
  topic cards, and a payload inspector for refreshed values and live events.
- Theme/i18n: added Chinese and English topic-hub strings; other locale bundles
  inherit the canonical English structure. Replaced Tailwind utility surfaces
  with scoped semantic variables, including dark-safe table, loading-mask,
  code-preview, status-pill, and mobile-card states.
- Verification:
  - `npx eslint --max-warnings=0 src/views/data/DataTopicsPage.vue src/__tests__/views/DataTopicsPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/DataTopicsPage.test.ts src/i18n/__tests__/locale-completeness.test.ts src/__tests__/api/iteration170.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth and data-topic APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet plus refresh action,
    `ja-JP` verdant mobile, `ru-RU` meridian narrow; all rendered the hub hero,
    4 stats, 3 topic tags, 2 preview panels, mobile topic cards on narrow
    viewports, correct theme mode, no page or console errors, no detected
    document-level horizontal overflow, non-white dark surfaces, and screenshots:
    `src/frontend/artifacts/ui-data-topics/*.png`.

### 2026-07-01 - Trading Workspace List

- Scope: `/trading/workspaces` in `WorkspaceListPage.vue`, workspace list unit
  test, and `workspace` locale keys.
- UI changes: added a trading-only execution operations panel with runtime,
  executable-unit, attention, and completion cards; added trading readiness to
  the table view; replaced fragile table status tags with dark-safe status
  pills; preserved the previously accepted research workspace layout.
- Theme/i18n: added trading operations and readiness strings for Chinese,
  English, Japanese, Russian, German, French, and Italian. Trading operation
  cards, status pills, readiness pills, and table/loading surfaces now use
  semantic runtime theme variables and remain readable in dark mode.
- Verification:
  - `npx eslint --max-warnings=0 src/views/workspace/WorkspaceListPage.vue src/__tests__/views/workspace/WorkspaceListPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/ru-RU.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts`
  - `npm run test -- --run src/__tests__/views/workspace/WorkspaceListPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth and trading workspace APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet table view, `ja-JP`
    verdant mobile, `ru-RU` meridian narrow; all rendered the trading hero, 4
    workspace metrics, 4 operations cards, localized trading copy, mobile
    workspace cards, correct theme mode, readable dark table/status pills, no
    page or console errors, and no detected document-level horizontal overflow.
    Screenshots: `src/frontend/artifacts/ui-trading-workspaces/*.png`.

### 2026-07-01 - Trading Workspace Detail

- Scope: `/trading/:id` in `WorkspaceDetailPage.vue`, `TradingWorkspaceUnitsTab`
  theme styles, workspace detail unit test, and `workspaceDetail` locale keys.
- UI changes: added a trading-only runtime/readiness panel with active runtime,
  live/paper, gateway coverage, lock-state cards, execution-readiness checks,
  and trading-specific detail panel copy while preserving the accepted research
  workspace detail behavior.
- Theme/i18n: added trading detail strings for Chinese, English, Japanese,
  Russian, German, French, and Italian. Reworked trading-unit overview cards to
  use runtime theme variables instead of light semantic surfaces, keeping dark
  mode cards, schedule bars, and tables readable.
- Verification:
  - `npx eslint --max-warnings=0 src/views/workspace/WorkspaceDetailPage.vue src/components/workspace/TradingWorkspaceUnitsTab.vue src/__tests__/views/workspace/WorkspaceDetailPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/ru-RU.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts`
  - `npm run test -- --run src/__tests__/views/workspace/WorkspaceDetailPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, workspace detail, unit,
    status, auto-trading config, and schedule APIs: `zh-CN` aurora desktop,
    `en-US` obsidian tablet, `ja-JP` verdant mobile, `ru-RU` meridian narrow;
    all rendered 4 hero metrics, 4 trading operations cards, 4 readiness
    checks, the trading units tab, correct theme mode, non-white dark table and
    overview-card surfaces, no page or console errors, and no detected
    document-level horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-trading-workspace-detail/*.png`.

### 2026-07-01 - Trading AI Command Desk

- Scope: `/trading/ai` in `AITradingPage.vue`, extracted page styles, AI
  trading unit test, and `aiTrading` locale keys.
- UI changes: redesigned the natural-language trading page into an execution
  command desk with a professional hero, segmented paper/live mode control,
  guardrail/account/gateway/history overview cards, account context, quick
  command chips, command composer, parsed-response/risk panel, and execution
  audit history.
- Theme/i18n: added Chinese and English command-desk strings; other locale
  bundles inherit the canonical English structure. Replaced Element default
  surfaces with scoped semantic variables, including dark-safe panels, stat
  cards, guardrail boxes, response states, quick commands, and mobile stacking.
- Verification:
  - `npx eslint --max-warnings=0 src/views/AITradingPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/__tests__/views/AITradingPage.test.ts`
  - `npm run test -- --run src/__tests__/views/AITradingPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, AI-trading config,
    history, execute, and confirm APIs: `zh-CN` aurora desktop, `en-US`
    obsidian tablet, `ja-JP` verdant mobile, `ru-RU` meridian narrow; all
    rendered 4 overview cards, 3 quick commands, 3 history cards, guardrail
    panel, parsed response after submit, correct theme mode, non-white dark
    surfaces, no page or console errors, and no detected document-level
    horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-ai-trading/*.png`.

### 2026-07-01 - Portfolio Overview

- Scope: `/portfolio/overview` in `PortfolioPage.vue`, portfolio locale keys,
  and the portfolio page unit test.
- UI changes: redesigned the page as a portfolio risk workbench with a compact
  hero, asset/PnL/exposure/workspace metrics, running-workspace scope selector,
  themed workbench tabs, exposure summaries, empty states, and chart containers
  for equity and allocation.
- Theme/i18n: added Chinese and English portfolio workbench strings; other
  locales inherit the canonical English structure. Replaced light utility
  colors with scoped semantic theme variables, including dark-safe selected
  workspace cards, tab panels, tables, chart backgrounds, ECharts text, and
  responsive tablet/mobile layouts.
- Verification:
  - `npx eslint --max-warnings=0 src/views/PortfolioPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/__tests__/views/PortfolioPage.test.ts`
  - `npm run test -- --run src/__tests__/views/PortfolioPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, portfolio overview,
    workspace, positions, trades, equity, and allocation APIs: `zh-CN` aurora
    desktop, `en-US` obsidian tablet, `ja-JP` verdant mobile, `ru-RU` meridian
    narrow; all rendered 4 overview cards, 2 running workspace selectors,
    exposure cards, visible trade/equity/allocation tab surfaces, correct theme
    mode, non-white dark hero/selected-workspace surfaces, no page or console
    errors, and no detected document-level horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-portfolio-overview/*.png`.

### 2026-07-01 - Knowledge Q&A

- Scope: `/ai/chat` in `AIChatPage.vue`, extracted AI chat page styles, message
  bubble/citation/strategy-draft theme states, AIChat unit test, and `aiChat`
  locale keys.
- UI changes: redesigned the page as a knowledge Q&A workbench with a metric
  hero, retrieval-status command panel, compact mode toolbar, conversation rail,
  central chat surface, context/quick-tool panel, cited-answer state, and a
  responsive two-row composer that keeps textarea width stable in narrow chat
  columns.
- Theme/i18n: added hero/status/mode strings for Chinese, English, Japanese,
  German, French, Italian, and Russian. Replaced fragile `--bg-color-card`
  surfaces in AI chat components with runtime theme variables and added
  page-scoped Element Plus control tokens so obsidian buttons, selects,
  textareas, diagnostics, citations, and warning states remain readable.
- Verification:
  - `npx eslint --max-warnings=0 src/views/AIChatPage.vue src/components/aichat/ChatMessageBubble.vue src/components/aichat/StrategyDraftCard.vue src/components/aichat/CitationList.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/i18n/locales/ja-JP.ts src/i18n/locales/de-DE.ts src/i18n/locales/fr-FR.ts src/i18n/locales/it-IT.ts src/i18n/locales/ru-RU.ts`
  - `npm run test -- --run src/__tests__/views/AIChatPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, knowledge-base, document,
    conversation, send-message, and model APIs: `zh-CN` aurora desktop,
    `en-US` obsidian tablet, `ja-JP` verdant mobile, `ru-RU` meridian narrow;
    all rendered 4 hero metrics, the single knowledge-Q&A mode, conversation
    and context panels, cited assistant response after submit, correct
    theme/lang, non-white dark surfaces including buttons and inputs, no page or
    console errors, no detected document-level horizontal overflow, and a
    composer textarea width check. Screenshots:
    `src/frontend/artifacts/ui-ai-chat/*.png`.

### 2026-07-01 - Knowledge Base Management

- Scope: `/ai/knowledge-base` in `KnowledgeBasePage.vue`, knowledge-base
  locale keys, and the KnowledgeBasePage unit test.
- UI changes: redesigned the management route with a knowledge-asset hero,
  four operational metrics, current-KB command actions, a themed library rail,
  document tree/table workbench, selected-document detail panel, and responsive
  mobile stacking. Dialog cards now inherit theme tokens for retrieval
  configuration and document operations.
- Theme/i18n: added Chinese and English management hero/fallback labels; other
  locales inherit the canonical key structure. Replaced fixed utility colors in
  the page with semantic theme variables for cards, controls, status chips,
  metadata/code previews, tables, and dialogs.
- Verification:
  - `npx eslint --max-warnings=0 src/views/KnowledgeBasePage.vue src/__tests__/views/KnowledgeBasePage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/KnowledgeBasePage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, knowledge-base, document
    list, and document-detail APIs: `zh-CN` aurora desktop, `en-US` obsidian
    tablet, `ja-JP` verdant mobile, `ru-RU` meridian narrow; all rendered the
    hero, 4 metrics, library/document/detail panels, localized document rows,
    retrieval dialog, correct theme/lang, non-white dark surfaces including
    buttons and dialog, no raw `kb.*` keys, and no detected horizontal overflow.
    Screenshots: `src/frontend/artifacts/ui-knowledge-base/*.png`.

### 2026-07-01 - Knowledge Base Document Detail

- Scope: `/ai/knowledge-base/:id/documents/:docId` in
  `KnowledgeBaseDocumentPage.vue`, document detail child components, `kbDoc`
  locale keys, and the KnowledgeBaseDocumentPage unit test.
- UI changes: redesigned the document detail route as a reading workspace with
  document hero, status/source/content metrics, reader tabs, PDF/source
  controls, Markdown reader, metadata grid, and a themed AI follow-up side
  panel. Tablet and narrow layouts now switch earlier so long Russian and
  Japanese titles remain readable.
- Theme/i18n: added Chinese and English document-workspace strings; other
  locales inherit the canonical English structure. Replaced fixed light
  utility surfaces in the page and child components with semantic variables for
  cards, controls, status chips, JSON previews, empty states, and dark mode.
- Verification:
  - `npx eslint --max-warnings=0 src/views/KnowledgeBaseDocumentPage.vue src/views/knowledge-base-components/KnowledgeBaseDocSidePanel.vue src/views/knowledge-base-components/KnowledgeBaseDocSourceView.vue src/views/knowledge-base-components/KnowledgeBaseDocMetadata.vue src/__tests__/views/KnowledgeBaseDocumentPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/KnowledgeBaseDocumentPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, document-detail, and
    source-file APIs: `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP`
    verdant mobile, `ru-RU` meridian narrow; all rendered the hero, 4 metrics,
    reader and side panels, Markdown and metadata tabs, correct theme/lang,
    non-white dark hero/reader/side/metadata surfaces, no raw `kbDoc.*` keys,
    and no detected horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-knowledge-base-document/*.png`.

### 2026-07-01 - Config Data Scripts

- Scope: `/config/data/scripts` in `DataScriptsPage.vue`, the shared
  `ConfigDataLayout.vue` shell token fix, `dataPages` locale keys, and the
  DataScriptsPage unit test.
- UI changes: redesigned the route into a script-governance workbench with a
  compact hero, rescan/create actions, four operational metrics, registry
  filters, desktop script table, and responsive script cards for tablet and
  mobile layouts. Fixed the data-management tab label from data interfaces to
  data scripts.
- Theme/i18n: added Chinese and English script-workbench strings; other locales
  inherit the canonical English structure. Replaced fixed/light surfaces with
  semantic theme variables for the config shell, hero, metrics, toolbar,
  table, cards, pagination area, and script dialog controls.
- Verification:
  - `npx eslint --max-warnings=0 src/views/data/DataScriptsPage.vue src/views/config/ConfigDataLayout.vue src/__tests__/views/data/DataScriptsPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/data/DataScriptsPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, script stats, categories,
    and script-list APIs: `zh-CN` aurora desktop, `en-US` obsidian tablet,
    `ja-JP` verdant mobile, `ru-RU` meridian narrow; all rendered the config
    shell, hero, 4 metrics, registry filters, desktop table or responsive
    script cards, correct theme/lang, non-white dark shell/hero/workbench
    surfaces, no raw `dataPages.*` keys, no oversized mobile search field, and
    no detected horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-data-scripts/*.png`.

### 2026-07-01 - Config Data Script Detail

- Scope: `/config/data/scripts/:id` in `DataScriptDetailPage.vue`,
  `dataPages` script-detail locale keys, and a new DataScriptDetailPage unit
  test.
- UI changes: completed the detail route as a script profile with a compact
  hero, admin run action, four runtime metrics, configuration grid, manual-run
  panel, dependency schema panel, and responsive tablet/mobile stacking. Route
  actions now return to config data scripts and open config task/execution
  routes instead of legacy data routes.
- Theme/i18n: added Chinese and English script-detail strings; other locales
  inherit the canonical English structure. The page uses semantic variables for
  hero, metrics, status chips, run note, textarea, code block, panels, borders,
  and dark surfaces.
- Verification:
  - `npx eslint --max-warnings=0 src/views/data/DataScriptDetailPage.vue src/__tests__/views/data/DataScriptDetailPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/data/DataScriptDetailPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth and script-detail APIs:
    `zh-CN` aurora desktop, `en-US` obsidian tablet, `ja-JP` verdant mobile,
    `ru-RU` meridian narrow; all rendered the config shell, detail hero, 4
    metrics, configuration/run/dependency panels, correct theme/lang,
    non-white dark hero/panel surfaces, no raw `dataPages.*` keys, no page or
    console errors, and no detected horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-data-script-detail/*.png`.

### 2026-07-01 - Config Data Tasks

- Scope: `/config/data/tasks` in `DataTasksPage.vue`, `dataPages` task locale
  keys, and the DataTasksPage unit test.
- UI changes: redesigned scheduled tasks into a governance workbench with a
  compact hero, refresh/create actions, four operational metrics, task registry
  heading, filter toolbar, desktop task table, mobile task cards, custom empty
  state, and dark-safe schedule/dialog controls. Run/view-execution actions now
  open `ConfigDataExecutions` instead of the legacy data route.
- Theme/i18n: added Chinese and English task-workbench strings; other locales
  inherit the canonical English structure. The page uses semantic variables for
  hero, metrics, table headers, mobile cards, status chips, empty state,
  dialog, textarea, borders, and dark surfaces.
- Verification:
  - `npx eslint --max-warnings=0 src/views/data/DataTasksPage.vue src/__tests__/views/data/DataTasksPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/data/DataTasksPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, scripts, schedule
    templates, and task-list APIs: `zh-CN` aurora desktop, `en-US` obsidian
    tablet, `ja-JP` verdant mobile, `ru-RU` meridian narrow; all rendered the
    config shell, task hero, 4 metrics, registry workbench, desktop table or
    responsive task cards, correct theme/lang, non-white dark hero/workbench
    surfaces, no raw `dataPages.*` keys, no page or console errors, and no
    detected horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-data-tasks/*.png`.

### 2026-07-01 - Config Data Executions

- Scope: `/config/data/executions` in `DataExecutionsPage.vue`,
  `dataPages` execution locale keys, shared test stubs, and a new
  DataExecutionsPage unit test.
- UI changes: redesigned the route into an execution observability workbench
  with a hero, refresh action, four execution metrics, filter registry,
  desktop run-history table, responsive execution cards, explicit empty state,
  dark-safe detail drawer content, and clearer error/row-delta presentation.
- Theme/i18n: added Chinese and English execution-workbench strings; other
  locales inherit the canonical English structure. The page uses semantic
  variables for hero, metrics, table headers, mobile cards, status chips, empty
  state, drawer, code blocks, borders, and dark surfaces.
- Verification:
  - `npx eslint --max-warnings=0 src/views/data/DataExecutionsPage.vue src/__tests__/views/data/DataExecutionsPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/data/DataExecutionsPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, execution stats, list,
    detail, and retry APIs: `zh-CN` aurora desktop, `en-US` obsidian tablet,
    `ja-JP` verdant mobile, `ru-RU` meridian narrow; all rendered the config
    shell, execution hero, 4 metrics, filter workbench, desktop table or
    responsive execution cards, correct theme/lang, non-white dark
    hero/workbench surfaces, no raw `dataPages.*` keys, no page or console
    errors, and no detected horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-data-executions/*.png`.

### 2026-07-01 - Config Data Sync

- Scope: `/config/data/sync` in `DataSyncPage.vue`, sync child components,
  `dataPages` sync locale keys, and a new DataSyncPage unit test.
- UI changes: redesigned the route into a database sync console with a hero,
  save/test actions, four operational metrics, structured direct-MySQL config
  form, guidance cards, connection check results, active-task panel,
  upload/download workbenches, desktop tables, mobile sync cards, sync-history
  table/cards, and explicit empty/history message states.
- Theme/i18n: added Chinese and English sync-workbench strings; other locales
  inherit the canonical English structure. The page uses semantic variables
  for hero, metrics, config cards, table headers, mobile cards, status chips,
  empty state, borders, and dark surfaces.
- Verification:
  - `npx eslint --max-warnings=0 src/views/data/DataSyncPage.vue src/views/data/components/DataSyncConfigForm.vue src/views/data/components/DataSyncActiveTasks.vue src/views/data/components/DataSyncDatabaseTables.vue src/__tests__/views/data/DataSyncPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/data/DataSyncPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, sync config, database
    state, history, and connection-test APIs: `zh-CN` aurora desktop, `en-US`
    obsidian tablet, `ja-JP` verdant mobile, `ru-RU` meridian narrow; all
    rendered the config shell, sync hero, 4 metrics, config panel, database
    grid, history panel, mobile history cards where expected, correct
    theme/lang, non-white dark hero surface, no raw `dataPages.*` keys, no page
    or console errors, and no detected horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-data-sync/*.png`.

### 2026-07-01 - Config Data Interfaces

- Scope: `/config/data/interfaces` in `DataInterfacesPage.vue`,
  `dataPages` interface locale keys, and the DataInterfacesPage unit test.
- UI changes: redesigned the route into an AkShare interface registry with a
  hero, bootstrap/create actions, four operational metrics, metadata registry
  header, category/status/search filters, desktop table, responsive interface
  cards, explicit empty state, structured create/edit dialog, and a detail
  drawer with interface profile, metadata grid, parameter table, raw schema,
  and extra-config code blocks.
- Theme/i18n: added Chinese and English interface-registry strings; other
  locales inherit the canonical English structure. The page uses semantic
  variables for hero, metrics, workbench, table headers, mobile cards, status
  tags, empty state, dialog, drawer, code blocks, borders, and dark surfaces.
- Verification:
  - `npx eslint --max-warnings=0 src/views/data/DataInterfacesPage.vue src/__tests__/views/data/DataInterfacesPage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/data/DataInterfacesPage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, interface categories,
    interface list, detail, and bootstrap APIs: `zh-CN` aurora desktop, `en-US`
    obsidian tablet, `ja-JP` verdant mobile, `ru-RU` meridian narrow; all
    rendered the config shell, interface hero, 4 metrics, registry workbench,
    desktop table or responsive interface cards, correct theme/lang, non-white
    dark hero surface, no raw `dataPages.*` keys, no page or console errors,
    and no detected horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-data-interfaces/*.png`.

### 2026-07-01 - Config Data Governance

- Scope: `/config/data/governance` in `DataGovernancePage.vue`,
  `dataPages` governance locale keys, and a new DataGovernancePage unit test.
- UI changes: redesigned the route into a data connection governance workbench
  with a hero, bootstrap refresh action, four operational metrics, provider
  registry cards, endpoint registry filters, desktop endpoint table,
  responsive endpoint cards, empty states, and an endpoint detail drawer for
  metadata, preview parameters, schema, quality profile, preview result, and
  ingestion-job creation.
- Theme/i18n: added Chinese and English governance-workbench strings; other
  locales inherit the canonical English structure. The page uses semantic
  variables for hero, metrics, provider cards, endpoint table headers, mobile
  cards, status tags, empty states, drawer, textarea, code blocks, preview
  warning, borders, and dark surfaces.
- Verification:
  - `npx eslint --max-warnings=0 src/views/data/DataGovernancePage.vue src/__tests__/views/data/DataGovernancePage.test.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts`
  - `npm run test -- --run src/__tests__/views/data/DataGovernancePage.test.ts src/i18n/__tests__/locale-completeness.test.ts`
  - `npm run typecheck`
  - Playwright/Google Chrome smoke with mocked auth, governance bootstrap,
    providers, endpoints, preview, and job APIs: `zh-CN` aurora desktop,
    `en-US` obsidian tablet, `ja-JP` verdant mobile, `ru-RU` meridian narrow;
    all rendered the config shell, governance hero, 4 metrics, provider panel,
    endpoint panel, desktop table or responsive endpoint cards, correct
    theme/lang, non-white dark hero surface, no raw `dataPages.*` keys, no page
    or console errors, and no detected horizontal overflow. Screenshots:
    `src/frontend/artifacts/ui-data-governance/*.png`.

## 2026-07-12 现状复盘与下一阶段方案

### BMAD Help 路由结论

本次按 `bmad-help` 的目录、既有产物和产品目标进行了路由：项目已有 BMM 的
Product Brief、PRD、架构与实施产物，且当前任务属于已上线界面的持续体验优化，
不是新产品立项。Web Design Studio（WDS）下尚未发现可复用的用户旅程、页面规格或
设计交付工件。

因此，后续较大范围的界面改造应在新的上下文中按以下顺序补齐设计输入；它们不是
本次文档更新的阻塞条件：

1. `[PB]` `bmad-wds-project-brief`：以已有 Product Brief 为输入，明确本轮目标用户、
   北极星任务和成功指标。
2. `[TM]` `bmad-wds-trigger-mapping`：把“研究 → 验证 → 交易/复盘”中的动机、
   顾虑和功能价值建立映射。
3. `[OS]` `bmad-wds-outline-scenarios` 与 `[SP]` `bmad-wds-conceptual-specs`：先为
   本文 P0/P1 场景写清进入点、异常路径、窄屏行为和页面规格。
4. `[DD]` `bmad-wds-design-delivery`：在开发前把规格、验收条件和组件边界打包交付。

### 审计范围与证据边界

- 审阅了当前路由、导航、主题令牌、关键页面源码、E2E/a11y 覆盖和已提交的多端截图。
  截图是 2026-07-01 的模拟数据快照，只能用于发现布局风险；不能替代真实用户研究、
  线上漏斗数据或本轮真实浏览器回归。
- 产品目标以既有 Product Brief 为准：让量化交易者更快完成“策略研究 → 回测验证 →
  模拟/实盘监控”的闭环，而不是把每个页面都改造成指标看板。
- 结论中的“43 个表格组件 / 14 个移动卡片候选”来自源码检索，后者是基于
  `isMobile`、`mobile-card` 等命名的保守启发式，必须逐页实测后才可作为覆盖率指标。

### 主要发现

| 发现 | 证据 | 体验风险 | 处理方向 |
| --- | --- | --- | --- |
| 复杂数据表的移动策略不一致 | 43 个 Vue 组件渲染 `el-table`；已存在的行情移动截图仍以压缩表格呈现，列标题和内容可读性明显下降。 | 交易者在手机上无法快速比较价格、状态和风险字段，容易横向滚动或误触操作。 | 建立统一的 Responsive Data Grid：小屏只保留 2–4 个决策字段，其余放入行详情/抽屉；高频监控场景提供卡片模式。 |
| 工作台在中等宽度和手机上的信息优先级不足 | AI 问答当前包含会话、回答、上下文三块信息；回测结果和设置页的窄屏快照均形成很长的单列滚动。 | 阅读答案、查看引用、发起下一步或完成回测决策需要反复滚动，核心动作离视线过远。 | 按任务而不是模块切分主/次面板：保留阅读与输入主面板，次要会话/上下文改为可恢复抽屉或底部 sheet。 |
| 卡片、KPI 和并列按钮被过度复用 | 多数已验收页面均以 hero + 4 KPI + 多个卡片开场；策略模板卡每项同时暴露详情、复制、回测等操作。 | 首屏密度看似充足，但用户需要先判断“现在该做什么”，扫描和决策成本高。 | 引入“页面类型 + 动作层级”规范：只有任务相关页面才显示 KPI；每张实体卡仅保留一个主操作，次要操作进入更多菜单或详情页。 |
| 主题支持范围超过自动化验证范围 | 主题 store 支持 7 个主题；现有设计系统测试验证令牌存在和映射，但没有覆盖各关键页面、各状态和全部主题的视觉/对比度回归。 | 深色、非默认浅色主题或 Element Plus 覆盖在空态、禁用、表格、抽屉和图表中可能退化。 | 先定义所有 7 个主题必须满足的语义令牌和对比度基线；按“PR 抽样 + 夜间全矩阵”验证，不新增页面级色板。 |
| 可访问性和本地化的覆盖仍偏核心页面 | axe 仅扫描 7 个 Critical Page Set 路由，且主要为静态初始态；`en-US` 的无中文检查也只覆盖同一组核心路由。 | 管理台、交易/网关弹窗、动态加载、错误态以及长文本语言仍可能出现焦点、标签、溢出或文本截断问题。 | 扩展为关键任务 + 弹窗/抽屉/错误态矩阵，并加入 200% 缩放、键盘操作和伪本地化测试。 |
| 规范路由与部分 smoke 用例已漂移 | `e2e/smoke-175/journeys.spec.ts` 仍访问 `/backtests`、`/backtests/1`，而当前 router 的规范路径为 `/backtest`、`/backtest/result/:id`。 | 路由重构后，冒烟测试可能无法验证真实用户路径，或在错误页面上产生误判。 | 从一个共享的“规范路径 + 旧路径”注册表生成导航、重定向与 E2E 用例；每次 IA 调整先更新该注册表。 |

### 优先级待办

| ID | 优先级 | 目标与范围 | 可交付物 | 验收条件 |
| --- | --- | --- | --- | --- |
| UI-201 | accepted (P0) | **统一移动数据栅格**：首批覆盖 `/data/quote` 与研究/交易工作区的 unit 表；优化结果、持仓和组合表留在后续迁移清单。 | `ResponsiveDataGrid` 组件/API、Quote 卡片、`UnitTable` 卡片与字段优先级规范。 | 390px 实际浏览器检查无页面横向溢出，Quote 卡片显示标识、价格、涨跌、分类/更新时间及图表/移除操作；UnitTable 卡片显示状态、标的、周期、最新价、当日盈亏和详情入口。 |
| UI-202 | accepted (P0) | **重建核心闭环的任务引导**：首批覆盖首次无研究工作区与回测结果页；策略选择、创建工作区、配置、回测与结果复核按同一顺序展示。 | `ResearchWorkflowGuide`、研究空态步骤、回测完成/异常状态步骤与回到工作区的安全动作。 | 新建研究工作区不再只呈现空态；结果页按完成、进行中或异常/取消状态提示复核/返回；结果加载失败时也提供返回入口。真实用户的 5 分钟完成率仍由 UI-210 验证。 |
| UI-203 | accepted (P0) | **收敛导航和路由契约**：核心研究、回测、AI 问答和知识库路径从同一注册表读取；旧链接显式迁移。 | `navigation/routes.ts`、router 重定向、capabilities、keyboard/AI Chat 跳转与 smoke/a11y/i18n/E2E 用例更新。 | `/strategy`、`/workspace`、`/workspace/:id`、`/ai-chat`、`/knowledge-base` 和 `/backtest/:id` 都会重定向到规范目标；单元测试覆盖规范路径、旧链接、参数和 query 保留。 |
| UI-204 | accepted (P1) | **自适应研究工作台**：AI 问答、知识库阅读和回测结果在 768px 以下将会话、上下文或诊断收进可发现的抽屉，阅读/图表/输入和主操作保持在主工作区。 | 三种断点布局规格、统一抽屉交互契约、AI Chat / 文档阅读 / 回测诊断实现。 | 768px 以下始终保留回答/图表和输入/主操作；上下文与历史可一键打开并保留当前阅读位置；键盘焦点和关闭后的焦点返回正确。 |
| UI-205 | accepted (P1, 首批页面) | **信息与动作层级治理**：设置、策略模板、仪表盘和数据脚本页均落实一个可见主操作；详情、运行、启停、编辑与删除进入二级菜单。 | 设置页移动分区导航；策略模板和数据脚本溢出菜单；仪表盘主/次动作标记与测试。 | 首批页面每个实体卡只有一个可见主操作；危险操作仍明确标识；设置页窄屏按“账户、偏好、产品信息”渐进展开。其余配置卡片纳入后续迁移清单。 |
| UI-206 | accepted (P1, 令牌基线) | **主题与语义令牌收口**：7 个主题现在同时映射主色、主色前景、状态色、Element Plus 文本/背景/边框令牌；图表在主题切换时重新渲染。 | 主题令牌契约、主题变更事件、图表颜色解析器、7 主题浏览器对比度矩阵。 | aurora、obsidian、nebula、solaris、glacier、meridian、verdant 在 Dashboard 静态任务态均无 serious/critical Axe 对比度问题；新增组件继续禁止业务色板。 |
| UI-207 | accepted (P1, 关键路径) | **国际化与无障碍扩面**：Axe/i18n CI 独立于后端登录；覆盖交易工作区、网关、数据脚本与移动 AI 抽屉。 | 静态 API 桩、a11y/i18n Playwright 配置、11 项 Axe 和 10 项 en-US 检查、320px 抽屉键盘检查。 | 关键路由和抽屉均具备可访问名称、焦点返回与无严重 Axe 问题；en-US 关键路由无中文。伪本地化、200% 缩放及长德语/俄语视觉矩阵留作下一轮覆盖。 |
| UI-208 | accepted (P2, 回测图表) | **图表与交易信息的可读性**：权益、回撤、交易信号图提供摘要、空态、主题色和非颜色买/卖标记。 | `ChartEmptyState`、语义图表颜色工具、主题重绘、图表单测。 | 无数据、主题切换和窄屏下图表保留文字摘要；买/卖通过 `B`/`S` 形状与文字表达，不仅依赖红绿颜色。 |
| UI-209 | accepted (P2, 高频首批) | **高密度页面性能感知**：Quote 与数据脚本首屏加载改用稳定的表格骨架；数据脚本保留分页，Quote 保留可见、可暂停的自动刷新和重试。 | `DataTableSkeleton`、Quote/脚本页迁移、减少脚本表格动作噪声、刷新控件无障碍名称。 | 初始加载不再只显示居中 spinner；刷新状态可见，自动刷新开关和间隔可访问，错误态仍可重试。虚拟滚动阈值与其它大表迁移另列为后续性能工作。 |
| UI-210 | awaiting external participants (P2) | **用真实任务校准方案**：尚无可由仓库内自动化替代的独立参与者招募与访谈记录。 | 任务脚本、访谈记录、完成率/耗时/错误率、设计决策日志。 | 每个核心角色至少 3 人完成核心任务；发现的问题回写到旅程和规格，而不是只以主观视觉偏好决定改动。 |

### 建议执行顺序

1. **Sprint 0（1–2 天）**：执行 UI-203 的路由契约清理；为 UI-201 建立 360/390/768/1024/1440px 的
   截图与 `scrollWidth` 基线；用 WDS 的 PB/TM 补齐目标用户和关键任务。此阶段不做全局视觉重写。
2. **Sprint 1（约 1 周）**：交付 UI-201 的共享栅格，并在 Quote + 一个研究/交易工作区落地；完成 UI-202
   的任务状态和首轮 Backtest/Workspace 引导。
3. **Sprint 2（约 1 周）**：交付 UI-204、UI-205 的首批页面，先从 AI Chat、策略库、设置页开始；同步补充
   动态态 a11y 与国际化回归。
4. **Sprint 3（持续）**：按组件而非逐页复制样式推进 UI-206～209；全主题、全断点和真实用户测试在夜间/发布前运行。

### 新的验收门禁

以下门禁是在既有 Acceptance Gates 之上新增的；旧条目“accepted”仅表示 2026-07-01 的首轮验收，
不等同于通过本轮任务和状态覆盖。

- 每个 UI story 必须写明：目标用户任务、规范路由、桌面/平板/手机断点、支持语言、主题、加载/空/错/权限
  状态、危险操作的确认与撤销策略。
- 涉及表格的 story 必须定义 360px 的字段优先级和详情入口，不能仅依靠缩小字体或横向滚动作为移动方案。
- PR 至少覆盖 aurora + 一个深色主题；夜间任务覆盖全部 7 个主题。截图断言同时检查页面和主要可滚动容器的
  `scrollWidth <= clientWidth`。
- a11y 扫描除初始页外，要覆盖打开的菜单/抽屉/对话框及错误态；补充 Tab/Shift+Tab、Escape、200% 缩放和
  `prefers-reduced-motion` 的交互检查。
- i18n 除键完整性和 `en-US` 无中文外，增加伪本地化与至少一个长文本 locale 的视觉回归；所有数值、货币和
  日期必须使用 locale-aware formatter。
- 只在任务完成率、时间、误操作率或可访问性/性能指标有预期改善时改动布局。每次发布把截图、测试命令、
  未解决风险和真实用户反馈追加到本文件的 Acceptance Log。

### 2026-07-12 - P0 交付验收

- **UI-201 / 移动数据栅格**
  - 新增 `ResponsiveDataGrid.vue`，桌面保留完整表格，700px 以下切换为可访问的卡片区域。
  - `QuotePage.vue` 迁移为移动决策卡：代码/名称、最新价、涨跌幅、涨跌、分类、更新时间和图表/移除操作；
    不再把所有桌面列压进窄屏表格。
  - `UnitTable.vue` 迁移为工作区单元卡：运行状态、策略/标的、周期、最新价、当日盈亏和详情操作。
- **UI-202 / 核心闭环引导**
  - 新增 `ResearchWorkflowGuide.vue` 与共享状态模型。空研究工作区明确展示“创建 → 配置 → 回测 → 复核”并将
    唯一主操作指向新建工作区。
  - 回测结果页按完成、进行中、失败/取消生成步骤状态；失败的结果和加载错误均提供回到工作区/回测清单的安全出口。
- **UI-203 / 规范路径**
  - 新增 `navigation/routes.ts`，E2E smoke、a11y、i18n、导航能力、快捷键、AI Chat 和 router 均复用核心路径。
  - 旧的策略、工作区（含详情）、AI Chat、知识库和回测结果链接重定向到规范路径，保留知识库 query。
- **自动化验证**
  - `npm run typecheck`
  - `npm run test -- --run src/i18n/__tests__/locale-completeness.test.ts src/__tests__/components/common/ResponsiveDataGrid.test.ts src/__tests__/components/research/ResearchWorkflowGuide.test.ts src/__tests__/components/workspace/UnitTable.test.ts src/__tests__/navigation/routes.test.ts src/__tests__/navigation/capabilities.test.ts src/__tests__/router/index.test.ts src/__tests__/views/QuotePage.test.ts src/__tests__/views/workspace/WorkspaceListPage.test.ts src/__tests__/views/BacktestResultPage.test.ts` — **10 files / 93 tests passed**。
  - 对本轮文件运行 `npx eslint --max-warnings=0 ...` — **通过**。
  - `npm run build` — **通过**。
- **浏览器验收（本地 mock API，Chromium，390×844）**
  - `/data/quote`：`scrollWidth === clientWidth === 390`，渲染 2 张移动行情卡，桌面表格容器为 `display:none`、
    移动卡片容器为 `display:block`，无页面异常；截图 `/tmp/quote-responsive-390.png`。
  - `/research/workspaces` 空态：`scrollWidth === clientWidth === 390`，渲染 4 个流程步骤，无页面异常；截图
    `/tmp/research-workflow-390.png`。
- **当时的后续范围**：本条仅记录 P0 交付时的状态；UI-205～209 的首批范围已在本文后续“UI-205 至 UI-209
  交付验收”中关闭。优化/持仓/组合表迁移属于后续扩展 backlog，UI-210 的真实用户任务完成率仍需外部参与者验证。

### 2026-07-12 - UI-204 自适应研究工作台验收

- **窄屏信息优先级**：`AIChatPage` 在 768px 以下隐藏常驻的会话和上下文侧栏，主回答与输入区保持在工作台内；在
  对话顶部提供“会话”和“上下文”入口。`KnowledgeBaseDocumentPage` 将文档摘要、阅读建议和快捷追问侧栏收进“文档
  上下文”抽屉；`BacktestResultPage` 将冗长的诊断区收进“打开诊断”抽屉，绩效和图表主区仍在页面中。
- **抽屉与键盘行为**：三处入口都打开固定定位的窄屏抽屉，打开后焦点进入关闭按钮；`Escape`、关闭按钮和遮罩均可
  关闭，且关闭后焦点回到原入口。抽屉内的 `Tab` / `Shift+Tab` 循环在面板中，避免焦点落到被遮挡的阅读区。
- **路由回归**：AI Chat 的引用文档单测改为断言 `/ai/knowledge-base/:id/documents/:docId`，避免重新引入旧的
  `/knowledge-base/...` 链接。
- **验证**：
  - `npm run typecheck`
  - `npm run test -- --run src/__tests__/views/AIChatPage.test.ts src/__tests__/views/KnowledgeBaseDocumentPage.test.ts src/__tests__/views/BacktestResultPage.test.ts src/i18n/__tests__/locale-completeness.test.ts` — **4 files / 50 tests passed**。
  - 对三页、对应单测和中英文 locale 运行 `npx eslint --max-warnings=0 ...` — **通过**。
  - `npm run build` — **通过**（产物时间：2026-07-12 12:34 CST）。
  - 本地 mock API / Chromium / 390×844：三页均为 `scrollWidth === clientWidth === 390`；触发入口为 `display:flex`、
    常驻次级面板为 `display:none`；抽屉焦点分别落在 “Close panel” / “Close document context” / “Close diagnostics”，
    `Escape` 后焦点回到各自入口，浏览器异常均为 0。截图：`/tmp/ai-chat-mobile-workbench-390.png`、
    `/tmp/kb-doc-mobile-reader-390.png`、`/tmp/backtest-mobile-result-390.png`。

### 2026-07-12 - UI-205 设置页首轮实现

- **渐进展开**：设置页在桌面保持完整的双列工作台；680px 以下显示“账户 / 偏好 / 产品信息”分区导航，仅展示当前
  分区。账户保留身份与密码安全，偏好保留 AI 用量和默认模型，产品信息单独按需打开，避免移动端把全部设置平铺为长表单。
- **动作层级**：密码更新与保存模型偏好仍是各自分区的唯一主按钮；连通性测试保持普通次操作，未额外引入颜色或页面级
  主操作。
- **验证**：
  - `npm run test -- --run src/__tests__/views/SettingsPage.test.ts src/i18n/__tests__/locale-completeness.test.ts` — **2 files / 29 tests passed**。
  - 390×844 本地 mock API / Chromium：分区导航为 `display:grid`，切换“偏好”后账户分区为 `display:none`、偏好分区为
    `display:grid`，`scrollWidth === clientWidth === 390`，浏览器异常为 0。截图：`/tmp/settings-progressive-390.png`。
- **历史状态说明**：这是设置页首轮实现时的记录；后续已将策略模板、数据脚本和仪表盘纳入 UI-205 的首批范围，当前
  状态以优先级表和“UI-205 至 UI-209 交付验收”为准。其余配置卡片的统一迁移属于扩展 backlog。

### 2026-07-12 - 联合回归

- `npm run typecheck` — **通过**。
- 13 个本轮关联测试文件（路由、移动数据栅格、闭环引导、AI/文档/回测抽屉与设置页）共 **129 tests passed**。
- 本轮源码与测试的 ESLint、Git whitespace 检查均通过；生产构建产物已更新至 2026-07-12 12:34 CST。

### 2026-07-12 - UI-205 至 UI-209 交付验收

- **动作层级（UI-205）**：仪表盘的三项快捷动作明确为一项主任务、两项次任务；策略模板卡不再是嵌套的可点击
  容器，保留“使用模板”主操作，详情与回测放入“更多操作”；数据脚本桌面与移动视图均只保留“详情”，运行、启停、
  编辑和删除进入二级菜单。设置页的移动分区导航延续首轮实现。
- **主题（UI-206）**：主题 store 现在同步 `--primary-color`、`--primary-on-color`、四种状态色与
  Element Plus 的文本、背景、填充和边框变量；`themechange` 会驱动 ECharts 重绘。为深色主题的主按钮提供可读的
  前景色，另行校正 sidebar 激活态与 glacier 次级文本，避免以更改业务含义换取对比度。
- **无障碍与国际化（UI-207）**：新增不依赖后端 global setup 的 a11y/i18n Playwright 配置与静态 API 桩。
  Critical Page Set 扩展为登录、Dashboard、AI、回测、知识库、策略、交易工作区、网关和数据脚本；数据脚本筛选器、
  Quote 自动刷新控件、主题切换器和登录预览状态补齐可访问名称或对比度。移动 AI 会话抽屉验证了 dialog 语义、焦点
  进入、Escape 返回与 `scrollWidth <= 320`。
- **图表与高密度反馈（UI-208/209）**：新增共享 `ChartEmptyState` 与 `DataTableSkeleton`。权益曲线、回撤和交易
  信号图都提供 `role="img"` 的摘要和无数据说明；交易买/卖同时使用 `B`/`S` 文本与三角形状。Quote 与数据脚本的
  首次加载不再导致主操作区跳动。
- **浏览器验收（本地 Vite + 静态 API 桩 + Google Chrome）**：
  - 9 条已认证关键路由和登录页的 WCAG 2.1 A/AA Axe 扫描均为 `blocking: []`。
  - aurora、obsidian、nebula、solaris、glacier、meridian、verdant 7 套主题的 Dashboard 扫描均为
    `blocking: []`，且 `data-theme` 均正确应用。
  - 10 条登录/已认证路由在 `en-US` 下均未检测到中文字符。
  - 320×844 AI 会话抽屉得到 `role="dialog"`、打开后焦点在关闭按钮、Escape 后焦点返回触发器、无严重 Axe
    问题且页面宽度为 320px。
- **自动化验证**：
  - `npm run typecheck` — 通过。
  - `npm run test -- --run` — **135 files / 1214 tests passed**。同时修复了策略列表旧式未分页响应导致的异步
    未处理异常，并增加 store 回归测试。
  - `npx eslint --no-ignore --max-warnings=0 ...` 与 `git diff --check` — 通过。
  - `npm run build` — 通过（`dist/index.html` 产物时间：2026-07-12 13:24 CST）。
- **后续不可自动关闭的事项**：UI-210 需要产品方招募 3 类独立参与者（交易者、研究员、风控/管理），每类至少 3
  人；伪本地化、200% 缩放与长文本 locale 的视觉回归、其余高密度表的虚拟滚动阈值则进入下一批 UI 回归工作。

### UI-210 真实任务研究执行卡（待产品方安排）

可执行的主持脚本、匿名会话表和决策日志位于
[`docs/research/ui-optimization/`](docs/research/ui-optimization/README.md)；开始研究时先复制模板，再填写真实会话，
不要以示例行作为参与者证据。

| 角色 | 无引导任务 | 成功定义 | 记录字段 |
| --- | --- | --- | --- |
| 独立交易者（3 人） | 在手机宽度查看行情、暂停自动刷新、进入图表，再回到列表。 | 在 5 分钟内完成，未误删自选或误解刷新状态。 | 是否完成、耗时、误操作、卡点、设备/宽度。 |
| 量化研究员（3 人） | 从策略库选择模板，建立研究工作区，发起回测并在结果页判断下一步。 | 在 5 分钟内说出当前状态和下一步，不依赖协助找到关键入口。 | 是否完成、耗时、入口搜索次数、状态理解偏差、建议。 |
| 风控/管理角色（3 人） | 查看网关状态，筛选数据脚本，并说明一次运行/启停操作的风险边界。 | 能区分查看、普通操作和危险操作；不在未确认状态触发危险动作。 | 是否完成、耗时、误操作、风险理解、建议。 |

- 使用本地 mock 或无真实下单权限的测试环境；不收集账户、持仓、令牌或策略源码。
- 每次访谈后在设计决策日志写入：发现、证据（录屏时间点/原话）、严重度、对应 UI-ID、决定、负责人和复验日期。
- 只有同一问题在至少 2 名同角色参与者中出现，或造成关键任务失败/误操作时，才进入下一轮实现 backlog；单次视觉偏好只作观察记录。
