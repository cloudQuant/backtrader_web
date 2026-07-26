# Technical Design Document

> 迭代 175「质量加固与可观测性纵深」

## Overview

本文档为迭代 175 的 11 个需求提供技术设计方案。175 不引入新框架/语言/构建工具，所有改动落在「现有 stack 的横切关注点」上：mypy 严格作用域扩盘、vitest 覆盖率门禁、Playwright a11y/i18n/e2e 测试、OpenTelemetry span 网络、Vite manualChunks、Alembic 守护脚本、uv workspace 单一入口。设计遵循「最小侵入 + 可阻塞回归 + 可观测」三条主线，保证每条需求的验收门都有一条 CI job 兜底。

## Architecture

### 175 改动的横切层（不动业务逻辑）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       Frontend (Vue 3 + Vite)                            │
│  ┌────────────────┐  ┌─────────────────┐  ┌──────────────────────────┐  │
│  │ a11y e2e Suite │  │ i18n e2e Suite  │  │ smoke e2e Suite (5 旅程)  │  │
│  │ (axe + Playwr.)│  │ (en-us-no-zh)   │  │ (Playwright + retries:1) │  │
│  └────────────────┘  └─────────────────┘  └──────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ vitest perFile thresholds（High_Coverage_Core ≥90%；全局 ≥75%） │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ vite manualChunks: element-plus / vue-router / pinia / echarts /  │  │
│  │  monaco-editor → 对应 vendor chunk                                │  │
│  │ check_bundle_size.sh: entry chunk gzip ≤ 300KB；登录路由非 vendor │  │
│  │  JS ≤ 4 个                                                        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI + SQLAlchemy 2.0)                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ OTel Tracer 网络：                                                 │  │
│  │  backtrader.backtest.{create,submit,execute,collect,finalize}     │  │
│  │  backtrader.strategy.{submit,version_create}                      │  │
│  │  backtrader.ai.{intent_parse,llm_call,response_format}            │  │
│  │  backtrader.live.{place_order,cancel_order,on_fill}               │  │
│  │  + business attributes (bt.user_id / bt.strategy_id / ...)        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ mypy strict scope 扩盘：app.services.{strategy,backtest,gateway,   │  │
│  │  akshare,optimization,live_trading,workspace,log_parser,           │  │
│  │  ai_trading}.*                                                     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Alembic 守护：check_orm_schema_drift.py + check_migration_safety   │  │
│  │  .py + alembic-meta 注释规范                                       │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  Observability (Local profile=observability)             │
│  Jaeger all-in-one (4317/4318/16686) → 本地查看 trace 树                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                 Repo Workspace (uv workspace)                            │
│  pyproject.toml(root)                                                    │
│   └─ members: src/backend, src/bt_api_py                                 │
│  scripts/dev/check_all.sh / Makefile: ruff + mypy + pytest 一键全跑      │
└─────────────────────────────────────────────────────────────────────────┘
```

### CI 工作流变更概览

```
.github/workflows/ci.yml （新增/修改）
├─ backend-mypy-services            # 新 job，blocker
├─ frontend-test                    # 修改：覆盖率阈值 + summary 表
├─ frontend-a11y                    # 新 job，blocker
├─ frontend-i18n                    # 新 job，blocker（独立 job）
├─ frontend-e2e-smoke               # 新 job，blocker（≤5min）
├─ frontend-build                   # 修改：bundle-size 强制阻塞
├─ check-migrations                 # 修改：追加 drift + safety check
├─ monorepo-check                   # 新 job，advisory
└─ ci-summary                       # 修改：needs += 新 jobs

.github/workflows/nightly.yml （修改）
└─ 扩展跑完整 e2e/；失败时调 GitHub API 创建/复用 issue

.github/workflows/e2e.yml          # 拆分或保留：smoke 走 PR；全量走 nightly
```

## Components and Interfaces

### 1. mypy 严格作用域扩盘（Requirement 1）

**配置位置**：`src/backend/pyproject.toml` `[[tool.mypy.overrides]]`

**新增条目**（保留现有 4 个 override 不动）：

```toml
[[tool.mypy.overrides]]
module = [
    "app.services.strategy.*",
    "app.services.backtest.*",
    "app.services.gateway.*",
    "app.services.akshare.*",
    "app.services.optimization.*",
    "app.services.live_trading.*",
    "app.services.workspace.*",
    "app.services.log_parser.*",
    "app.services.ai_trading.*",
]
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
```

**残留 Any 登记机制**：每个子包根 `__init__.py` 顶部以 `# any-source: <类别> - <简述>` 行注释登记，实施期间总数 ≤ 5 类/子包。同一份清单原文复制到 `docs/iterations/迭代175-质量加固与可观测性纵深/PROGRESS.md` 的「已知尾巴」小节。

**ignore 行数审计**：CI 中通过 `git diff <175 起点 commit>..HEAD -- 'src/backend/**.py' | grep -c '^+.*# type: ignore\['` 计数；阈值 80。

**新增 CI job**：

```yaml
backend-mypy-services:
  needs: [backend-lint]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: '3.11', cache: 'pip' }
    - run: pip install -e ".[dev]"
      working-directory: src/backend
    - run: |
        mypy app/services/strategy app/services/backtest \
             app/services/gateway app/services/akshare \
             app/services/optimization app/services/live_trading \
             app/services/workspace app/services/log_parser \
             app/services/ai_trading
      working-directory: src/backend
```

### 2. 前端覆盖率三级棘轮 + High_Coverage_Core（Requirement 2）

**配置位置**：`src/frontend/vitest.config.ts`

**全局阈值**：

```ts
test: {
  coverage: {
    provider: 'v8',
    reporter: ['text', 'lcov', 'json-summary'],
    thresholds: {
      lines: 75, functions: 75, branches: 75, statements: 75,
      perFile: false, // 全局阈值不按文件拆
      // High_Coverage_Core 通过 `<modulePath>` 键设置独立阈值
      'src/stores/auth.ts':              { lines: 90, functions: 90, branches: 90, statements: 90 },
      'src/stores/user_preferences.ts':  { lines: 90, functions: 90, branches: 90, statements: 90 },
      'src/stores/backtest.ts':          { lines: 90, functions: 90, branches: 90, statements: 90 },
      'src/stores/strategy.ts':          { lines: 90, functions: 90, branches: 90, statements: 90 },
      'src/stores/knowledge_base.ts':    { lines: 90, functions: 90, branches: 90, statements: 90 },
      'src/composables/useAuth.ts':      { lines: 90, functions: 90, branches: 90, statements: 90 },
      'src/composables/useApiClient.ts': { lines: 90, functions: 90, branches: 90, statements: 90 },
      'src/composables/useI18n.ts':      { lines: 90, functions: 90, branches: 90, statements: 90 },
    },
  },
},
```

**降级路径**：若运行环境的 vitest 不支持 `<modulePath>` 键，改用自定义 reporter `scripts/dev/coverage_core_reporter.ts`，读取 `coverage/coverage-summary.json` 后逐路径校验，未达标 exit 1。

**登记文件**：`src/frontend/__tests__/coverage_core.md` 列出 8 个模块路径与每个的「已豁免行号区间」（如有）。

**CI summary 表**：`frontend-test` job 的 `npm run test` 步骤后追加：

```yaml
- name: 覆盖率核心阈值汇总
  if: always()
  run: |
    node scripts/dev/coverage_core_summary.mjs >> $GITHUB_STEP_SUMMARY
```

`coverage_core_summary.mjs` 读取 `coverage/coverage-summary.json`，输出两张 markdown 表（全局指标 + High_Coverage_Core 指标）。

### 3. A11y 基线达成 WCAG 2.1 AA（Requirement 3）

**目录结构**：

```
src/frontend/e2e/
├─ a11y/
│  ├─ login.spec.ts
│  ├─ dashboard.spec.ts
│  ├─ ai-chat.spec.ts
│  ├─ backtests-list.spec.ts
│  ├─ backtest-detail.spec.ts
│  ├─ knowledge-base.spec.ts
│  └─ strategies.spec.ts
└─ fixtures/
   └─ auth.ts        # 复用：返回 storageState 路径供其他 spec test.use(...)
```

**单条 spec 模板**：

```ts
import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('dashboard a11y - 0 critical/serious', async ({ page }) => {
  test.setTimeout(30_000)
  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()

  const blocking = results.violations.filter(
    v => v.impact === 'critical' || v.impact === 'serious'
  )

  if (blocking.length > 0) {
    console.log('::group::a11y violations')
    blocking.forEach(v => console.log(JSON.stringify({
      url: page.url(), id: v.id, impact: v.impact,
      nodes: v.nodes.map(n => n.target.join(' ')),
      help: v.helpUrl,
    })))
    console.log('::endgroup::')
  }
  expect(blocking).toHaveLength(0)
})
```

**Lighthouse 阈值升级**：`config/lighthouserc.js` `assertions` 中

```js
'categories:accessibility': ['error', { minScore: 0.9 }]
```

`collect.url` 扩展为 7 个核心页面。登录后页面通过 `puppeteerScript` 注入 token：

```js
puppeteerScript: './lhci/login.js'  // 该脚本登录并把 token 写入 localStorage 后跳转到目标 url
```

**新增 CI job**：

```yaml
frontend-a11y:
  needs: [frontend-build]
  steps:
    - 构建前端 dist + 启动 vite preview
    - 启动后端 + 数据库 service container
    - 等待 7 个页面 HTTP 200（最长 120s）
    - npx playwright test e2e/a11y/
    - 上传 trace artifact
```

### 4. i18n 100% 覆盖率（Requirement 4）

**核心脚本**：`scripts/dev/check_i18n_coverage.py`

**架构**：

```
check_i18n_coverage.py
├─ Vue 文件 SFC 解析（用 lxml 或 vue-template-compiler 等价 python lib）
│   ├─ <template> 节点遍历 → 文本节点检查
│   ├─ <el-...> 组件 prop 解析 → label / placeholder 字符串检查
│   └─ <script setup> AST → ElMessage/ElMessageBox/ElNotification 调用检查
├─ TS 文件 AST（用 @babel/parser 或子进程 tsc + parser）
│   └─ ElMessage/ElMessageBox/ElNotification 首参数检查
├─ 豁免注释解析
│   ├─ // i18n-ignore-next-line + i18n-reason: <5-120 字符>
│   └─ <!-- i18n-ignore-next-line --> + i18n-reason
├─ 违规识别
│   ├─ 中文裸串：[\u4e00-\u9fff]+
│   └─ 英文长度 ≥4 裸串：[A-Za-z]{4,}
└─ 输出
    ├─ stdout JSON-line 或 markdown 表格
    └─ 末行 `summary: <N> violations`
```

**Locale_Key_Parity 检查模式**：

```
locale_dir/zh-CN/*.json → 全部加载 → 递归点路径展开 (a.b.c) → 字典序
locale_dir/en-US/*.json → 全部加载 → 递归点路径展开 (a.b.c) → 字典序
diff(zh, en) → 输出 only-in-zh / only-in-en 两段
```

**Playwright en-us-no-zh 测试**：

```ts
// e2e/i18n/en-us-no-chinese.spec.ts
const PAGES = ['/login', '/dashboard', '/ai-chat', '/backtests', '/backtests/1', '/knowledge-base', '/strategies']
for (const url of PAGES) {
  test(`en-US no Chinese on ${url}`, async ({ page }) => {
    test.setTimeout(30_000)
    await page.addInitScript(() => localStorage.setItem('locale', 'en-US'))
    await page.goto(url)
    await page.waitForLoadState('networkidle')
    const text = await page.locator('body').innerText()
    expect(text).not.toMatch(/[\u4e00-\u9fff]/)
  })
}
```

**新增 CI job**：

```yaml
frontend-i18n:
  needs: [frontend-build]
  steps:
    - python scripts/dev/check_i18n_coverage.py --strict
    - python scripts/dev/check_i18n_coverage.py --check-parity
    - 启动前后端 → 等待 7 页面 200 → npx playwright test e2e/i18n/
```

**PR 模板**：`.github/PULL_REQUEST_TEMPLATE.md` 增加段落：

```markdown
## i18n 变更清单

- zh-CN key 数量：____
- en-US key 数量：____
- 本 PR 新增 key：
  - ...
- 本 PR 删除 key：
  - ...
```

`scripts/ci/check_pr_template.py` 在 PR 中提取 description，校验上述子字段非占位符；缺失则失败。

### 5. OpenTelemetry 全链路追踪（Requirement 5）

**Span 命名空间矩阵**：

| 命名空间 | phase 集合 | 必备业务属性 |
|---|---|---|
| `backtrader.backtest.*` | create / submit / execute / collect / finalize | bt.user_id, bt.backtest_id |
| `backtrader.strategy.*` | submit / version_create | bt.user_id, bt.strategy_id |
| `backtrader.ai.*` | intent_parse / llm_call / response_format | bt.user_id |
| `backtrader.live.*` | place_order / cancel_order / on_fill | bt.user_id, bt.symbol, bt.order_id |

**装饰器辅助类**（避免在每个方法手写 `with` 块）：

```python
# src/backend/app/utils/tracing.py
from contextlib import contextmanager
from opentelemetry import trace

_tracer = trace.get_tracer("backtrader-web")

@contextmanager
def business_span(name: str, **attrs):
    """业务 span，自动注入 bt.* attribute，异常路径标记 ERROR + record_exception。"""
    with _tracer.start_as_current_span(name) as span:
        for k, v in attrs.items():
            if v is not None:
                span.set_attribute(f"bt.{k}", v if isinstance(v, (int, str, float, bool)) else str(v))
        try:
            yield span
        except Exception as exc:
            span.set_status(trace.StatusCode.ERROR, str(exc)[:200])
            span.record_exception(exc)
            raise
```

**调用示例**：

```python
async def create_backtest(self, user_id: int, payload: BacktestCreate) -> Backtest:
    with business_span("backtrader.backtest.create", user_id=user_id):
        # ... 核心实现
        with business_span("backtrader.backtest.submit", user_id=user_id, backtest_id=bt.id):
            # ... 提交执行
        return bt
```

**no-op 模式**：`OTEL_ENABLED ∈ {true,1,yes,on}` 大小写不敏感才启用；其他值（含未设置）走 NoOpTracerProvider，零开销。

**Jaeger profile**：`docker/compose/dev.yml` 追加

```yaml
services:
  jaeger:
    profiles: [observability]
    image: jaegertracing/all-in-one:1.55
    ports:
      - "4317:4317"
      - "4318:4318"
      - "16686:16686"
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
```

**测试**：`src/backend/tests/test_telemetry_e2e.py` 使用 `opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter` 替代 OTLP exporter，断言 span 名称集合、parent-child 关系、business attributes。

### 6. E2E_Smoke 上 CI（Requirement 6）

**目录与可观察断言**：

| 旅程 | 文件 | 关键断言 |
|---|---|---|
| 登录与登出 | `e2e/smoke/auth.spec.ts` | 登录后 navbar 含用户名；登出后 url 包含 `/login` |
| 创建回测 | `e2e/smoke/backtest.spec.ts` | 详情页 `[data-test=equity-curve]` 元素存在；状态文本 `completed` |
| AI 对话 | `e2e/smoke/ai-chat.spec.ts` | 首条 assistant message 文本长度 ≥ 1 |
| KB 问答 | `e2e/smoke/knowledge-base.spec.ts` | `[data-test=citation-chip]` 至少 1 个，`href` 非空 |
| 策略管理 | `e2e/smoke/strategy.spec.ts` | 列表中存在 name 完全匹配的行 |

**playwright.config.ts 调整**：smoke 项目设置 `retries: 1`、`timeout: 60000`、单 worker 串行（保证 wall-clock 可预测）。

**CI job**：

```yaml
frontend-e2e-smoke:
  services:
    postgres:
      image: postgres:15
      env: { POSTGRES_PASSWORD: test }
      options: >-
        --health-cmd pg_isready --health-interval 10s --health-timeout 5s
  steps:
    - 安装依赖 + 构建前端 dist
    - 后台启动后端 (uvicorn) + 前端 (vite preview)
    - 跑 scripts/dev/seed_e2e_smoke.py（≤30s 注入最小种子集）
    - wait-on http://localhost:8000/api/v1/health（超时 60s；失败时打印末 50 行 stderr）
    - npx playwright test e2e/smoke/
    - upload-artifact: trace + video + screenshot（7 天）
```

**Nightly issue 自动化**：`scripts/ci/report_nightly_failure.sh` 调用 `gh api`，先查找近 7 天同标题 issue：

```bash
EXISTING=$(gh issue list --label nightly-e2e-failure --search "[nightly-e2e] failure" --state open --json number,createdAt --jq '.[] | select((.createdAt | fromdateiso8601) > (now - 604800)) | .number' | head -1)
if [[ -n "$EXISTING" ]]; then
  gh issue comment "$EXISTING" --body "$(cat failure_summary.md)"
else
  gh issue create --title "[nightly-e2e] failure on $(date -I)" --label nightly-e2e-failure --body-file failure_summary.md
fi
```

GitHub API 失败时 `set +e` 兜底 + summary 段落输出。

### 7. Bundle Size Ratchet（Requirement 7）

**vite manualChunks**：

```ts
// vite.config.ts
build: {
  rollupOptions: {
    output: {
      manualChunks(id) {
        if (id.includes('node_modules/element-plus/') || id.includes('node_modules/@element-plus/')) return 'element-plus'
        if (id.includes('node_modules/vue-router/')) return 'vue-router'
        if (id.includes('node_modules/pinia/')) return 'pinia'
        if (id.includes('node_modules/echarts/') || id.includes('node_modules/zrender/')) return 'echarts'
        if (id.includes('node_modules/monaco-editor/') || id.includes('node_modules/@monaco-editor/')) return 'monaco-editor'
        return undefined
      },
    },
  },
}
```

**check_bundle_size.sh 检查项**：

```bash
ENTRY=$(ls dist/assets/index-*.js | head -1)
ENTRY_GZIP=$(gzip -c "$ENTRY" | wc -c)
if [[ $ENTRY_GZIP -gt 307200 ]]; then
  echo "::error::entry chunk gzip $ENTRY_GZIP > 307200 (300KB)"
  STATUS=FAIL
fi

# 登录路由非 vendor JS
LOGIN_JS=$(node scripts/ci/list_route_assets.mjs /login dist | grep -v -E '/(element-plus|vue-router|pinia|echarts|monaco-editor)-' | wc -l)
if [[ $LOGIN_JS -gt 4 ]]; then
  echo "::error::/login non-vendor JS files = $LOGIN_JS > 4"
  STATUS=FAIL
fi

[[ "$STATUS" == "FAIL" ]] && exit 1
echo "OK: bundle size within budget"
```

**PR 体积对比阻塞**：`scripts/ci/compare_bundle_size.sh` 计算 `(current - base) / base`：> 0.10 输出 `::error` 并 exit 1；base 缺失则 echo 跳过 + summary 注释。`BUNDLE_SIZE_GROWTH_OVERRIDE` 标签或 `<!-- bundle-size-override: <reason> -->` 注释绕过；CODEOWNERS 校验通过 `gh api` 检查 PR 是否有 owner 的 approved review。

**baseline 文档**：`docs/reference/frontend-bundle-budget.md` 表格列：vendor chunk 名 / 体积（gzip 字节）/ 采集 ISO 日期 / commit SHA。

### 8. Alembic 迁移守护（Requirement 8）

**check_orm_schema_drift.py 流程**：

```python
# pseudo-code
import tempfile, sqlalchemy as sa
from app.db.base import Base

with tempfile.TemporaryDirectory() as tmp:
    db_path = f"{tmp}/drift.db"
    # alembic upgrade head 到该 SQLite
    subprocess.run(["alembic", "-x", f"db_url=sqlite:///{db_path}", "upgrade", "head"],
                   check=True, timeout=120)

    expected = Base.metadata
    engine = sa.create_engine(f"sqlite:///{db_path}")
    actual = sa.MetaData()
    actual.reflect(bind=engine)

    diffs = compare_schemas(expected, actual)  # 详见对比规则
    if not diffs:
        print("OK: schema aligned")
        sys.exit(0)
    print_markdown_table(diffs)
    sys.exit(1)
```

**对比规则（compare_schemas）**：

- table 集合差集
- column 集合差集（表内）
- column type 类别比较：`type(col.type).__name__` 相等性 + 对 `String/Text/VARCHAR` 做归一化（忽略长度）
- index 比较：按 `(name, tuple(sorted(c.name for c in cols)))` 元组集合
- foreign_key 比较：按 `(src_table.src_col → tgt_table.tgt_col)` 字符串集合
- 任何步骤的内部异常：exit 2 + stderr

**check_migration_safety.py 流程**：

```python
import ast, subprocess

# 仅扫描 PR 内变更的 migration 文件
files = subprocess.check_output(
    ["git", "diff", "--name-only", "--diff-filter=AM", f"origin/{base}...HEAD",
     "--", "src/backend/alembic/versions/*.py"],
    text=True,
).splitlines()

for path in files:
    tree = ast.parse(open(path).read())
    for call in walk_calls(tree):
        if matches_op_add_column_no_default_nonnull(call):
            emit_warning(path, call.lineno, "add_column NOT NULL without server_default", suggest="...")
        elif call.func == "op.drop_column" or call.func == "op.drop_table":
            emit_warning(path, call.lineno, f"{call.func} 不可逆", ...)
        elif matches_alter_column_type_change(call):
            emit_warning(...)
        elif matches_create_index_no_concurrently(call):
            emit_warning(...)

    if not has_alembic_meta_comment(path):
        emit_warning(path, 1, "missing alembic-meta header", ...)

emit_summary_to_step_summary()
sys.exit(0)  # 永不阻塞，仅 warning
```

**alembic-meta 注释规范**：

```python
"""add user_preferences table

Revision ID: ...
"""
# alembic-meta: estimated_rows=0; lock_kind=short
```

**playbook 文档**：`docs/how-to/database-migration-playbook.md` 新增 4 节，含：

- 危险操作识别速查（4 类）
- PG 推荐写法：`SET lock_timeout='5s'`、`CREATE INDEX CONCURRENTLY`、分批回填
- safety check 输出解读
- PR review 必看清单（≥5 条）

### 9. uv Workspace（Requirement 9）

**根 pyproject.toml**：

```toml
[tool.uv.workspace]
members = ["src/backend", "src/bt_api_py"]

[tool.uv.sources]
# 不在 backend 里 pin bt_api_py 到 path，避免破坏 SSOT lock
```

**入口脚本** `scripts/dev/check_all.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
TIMEOUT_SECS=1800

cd "$(git rev-parse --show-toplevel)"

run_member() {
    local member="$1"
    pushd "$member" > /dev/null
    echo "::group::$member ruff check"
    ruff check . || { echo "::error::ruff check failed in $member"; exit 1; }
    echo "::group::$member ruff format --check"
    ruff format --check . || exit 1
    echo "::group::$member mypy"
    if [[ -f pyproject.toml ]]; then
        # 解析当前包的 mypy 严格作用域，否则覆盖 app/ 或顶层包
        mypy "$(python ../../scripts/dev/extract_mypy_scope.py)" || exit 1
    fi
    echo "::group::$member pytest"
    pytest -m "not e2e" -q || exit 1
    popd > /dev/null
}

run_member src/backend
run_member src/bt_api_py
echo "OK: all members green"
```

加 `timeout 1800 bash scripts/dev/check_all.sh` 包装。

**冲突检测**：`scripts/dev/check_workspace_lock_conflict.py` 解析 `uv.lock` 与 `config/requirements-dev.lock`，按包名匹配，version 字面比较；不一致 stderr 输出 `<package> workspace=<v1> lock=<v2>` 并 exit 1。

**CI advisory job**：

```yaml
monorepo-check:
  continue-on-error: true
  steps:
    - bash scripts/dev/check_all.sh
ci-summary:
  steps:
    - if: needs.monorepo-check.result == 'failure'
      run: echo "⚠️ monorepo-check failed (advisory only)" >> $GITHUB_STEP_SUMMARY
```

**文档**：`docs/explanation/python-monorepo.md` 三节：

1. 工具选型（uv workspace vs hatch workspace vs pdm workspace 对比表）
2. 对 vendored 包的处理（`src/clientportal.gw` 不进入 workspace 成员，仍由 vendor 路径管理）
3. 与 174 §A6 边界一致性（`src/bt_api_py` 与 `src/backend` 的 consumer-only 边界保持不变）

### 10. 173B 处置（Requirement 10）

**disposition 文档结构**：

```markdown
# 173B disposition for iteration 175

> 评估日期：2026-XX-XX
> 评估人：<gh-user>

## 总览

| Item | 实现完成度 | 剩余工作清单 | 决议 | 判定依据 | 责任人 | 目标日期 |
|---|---|---|---|---|---|---|
| T2  | 60% | 接口 X 未迁；测试 Y 缺 | 顺延 176 | 工作量 4d 超 175 容量 | @owner | 2026-08-01 |
| T7  | 0%  | 整体未启动 | 终止/归档 | 业务优先级降低 | @owner | n/a |
| T10 | 90% | 仅缺文档 | 纳入 175 | 残余工作量 0.5d | @owner | 175-W3 |
```

**disposition → 175 子需求转写**：若 T10 决议为「纳入 175」，则在 requirements.md 的 Requirements 列表追加 §11.x（编号取 11.1 开始递增），并复制 EARS 验收准则。

**一致性校验**：`scripts/ci/check_173b_disposition_consistency.py` 解析两个文件的同标识符列（决议类型 / 责任人 / 目标日期），不一致 exit 1。

### 11. 500-999 行 .vue 收尾（Requirement 11，可选）

**进度文件 §11 表头**：

```markdown
## §11 500-999 行 .vue 收尾

| ID | 文件 | 当前行数 | 目标拆分子组件 | 工作量 | 状态 |
|----|------|---------|--------------|--------|------|
| C-501 | views/X.vue | 990 | A.vue + B.vue + useX.ts | M | ⚪ |
```

工作量映射：S ≤ 4h；M 4-8h；L 8-16h。「已完成」严格定义见 requirements 11.4。

## Data Models

175 不引入新数据库表；唯一新增的「类数据模型」是 OTel span 的属性 schema：

| 属性键 | 类型 | 必填命名空间 | 取值约束 |
|---|---|---|---|
| `bt.user_id` | int / str | backtest, strategy, ai, live | 非空 |
| `bt.strategy_id` | int / str | strategy, （回测中适用时）backtest | 非空（命名空间要求时） |
| `bt.backtest_id` | int / str | backtest | 非空 |
| `bt.symbol` | str | live | 非空 |
| `bt.order_id` | str | live | 非空 |
| `bt.attr_missing` | bool | 任一 | 仅当业务对象缺失时为 true，不静默 |

OTLP 导出协议遵循 OTel 1.x，不做协议层修改。

## Error Handling

### Mypy 扩盘异常路径

- 子包内 ignore 行数 > 80 → `backend-mypy-services` job 级 fail；附 owner approval 路径作为豁免出口（PR description 列清单）。
- 某子包暂时无法扩盘 → 从 mypy override 列表中移除该子包 + 在 PROGRESS.md 标注「176 候选」+ 子包数 ≥ 7 兜底。

### 覆盖率阈值未达

- 全局未达 → vitest exit 1 → `frontend-test` job fail。
- High_Coverage_Core 未达 → `coverage_core_summary.mjs` exit 1，输出未达标模块表。

### A11y 异常路径

- 7 个页面任一页面 axe 扫描超时 30s → 该 spec fail。
- 等待 7 页面 200 超过 120s → frontend-a11y job fail，打印末 50 行后端 stderr。
- 必要豁免超过 5 条 → docs/explanation/accessibility-baseline.md 触发 PR review 强制要求。

### i18n 异常路径

- 中文裸串发现 → `--strict` exit 1，stdout 列表 + summary。
- key 不对等 → `--check-parity` exit 1，only-in-zh / only-in-en 两段输出。
- en-us 残留中文（playwright）→ frontend-i18n job fail，trace artifact 上传。
- PR description 缺 i18n 段 → check_pr_template.py exit 1。

### OTel 异常路径

- collector unreachable → log warning，业务路径继续；test_telemetry_e2e.py 中专门测试此 case。
- span 内业务函数抛异常 → span 标记 ERROR + record_exception + 异常向上抛（不吞）。
- OTEL_ENABLED 非真值 → no-op TracerProvider，零开销。

### E2E_Smoke 异常路径

- /api/v1/health 超时未 200 → smoke job fail + stderr 末 50 行。
- 单测试失败（CI retries: 1 后仍失败）→ trace zip artifact 上传 + summary 链接。
- nightly 全量失败 → gh api 创建/复用 issue；gh api 自身失败 → summary 输出 skip 信息。

### Bundle Size 异常路径

- 阈值越界 → `check_bundle_size.sh` exit 1。
- > 10% 增长 → `compare_bundle_size.sh` exit 1（非阻塞绕过：override label/注释 + CODEOWNERS approve）。
- base 缺失 → 跳过对比并 summary 注释。

### DB Migration 异常路径

- ORM ↔ schema drift → drift check exit 1，markdown 表 stdout。
- 危险操作 → safety check exit 0 但 ::warning + summary。
- alembic-meta 缺失 → safety check warning。
- alembic upgrade head 在 SQLite 上失败 → drift check exit 2，stderr 错误。

### Monorepo 异常路径

- check_all.sh 任一步骤 fail → exit 1，stderr 含失败步骤名 + 成员包名。
- workspace 与 lock 版本冲突 → exit 1，列冲突包名与版本对。
- monorepo-check job advisory，仅 ci-summary 显示 ⚠️。

## Testing Strategy

### Unit Tests（已有体系扩展）

- 后端：pytest + Hypothesis；175 不强制新增 Hypothesis property test，但 `test_telemetry_e2e.py` 必须 ≥ 6 用例（详见 Requirement 5.9）。
- 前端：vitest；High_Coverage_Core 8 个模块走 ≥ 90% 阈值。

### Integration Tests

- backend 层面：仍由 `tests/integration/` 承载；175 不动。
- frontend 层面：vitest + jsdom；不动。

### A11y / i18n / E2E（Playwright，新建/扩展）

| 套件 | 阻塞 | 频率 | 时长 |
|---|---|---|---|
| `e2e/a11y/` | PR-blocking | 每 PR | ≤ 5 min |
| `e2e/i18n/` | PR-blocking | 每 PR | ≤ 3 min |
| `e2e/smoke/` | PR-blocking | 每 PR | ≤ 5 min |
| `e2e/`（全量）| Nightly only | cron | ≤ 30 min |

### CI Job 矩阵（修改/新增汇总）

| Job | 类别 | 阻塞 | 引用需求 |
|---|---|---|---|
| `backend-mypy-services` | 新增 | ✅ | 1 |
| `frontend-test`（增强）| 修改 | ✅ | 2 |
| `frontend-a11y` | 新增 | ✅ | 3 |
| `frontend-i18n` | 新增 | ✅ | 4 |
| `frontend-e2e-smoke` | 新增 | ✅ | 6 |
| `frontend-build`（强制阻塞）| 修改 | ✅ | 7 |
| `check-migrations`（增强）| 修改 | ✅ | 8 |
| `monorepo-check` | 新增 | ⚠️（advisory）| 9 |
| `nightly.yml`（扩展全量）| 修改 | ❌ | 6 |

### Performance Validation

OTel 性能开销基准（Requirement 5.8）：

```
pytest -m benchmark tests/perf/test_backtest_throughput.py [OTEL_ENABLED=false] × 30 次
pytest -m benchmark tests/perf/test_backtest_throughput.py [OTEL_ENABLED=true]  × 30 次
P95 增长比例 ≤ 5%；否则降级（PR description 附手动对比表）
```

## Dependencies and Sequencing

### 横向依赖

- Requirement 3（A11y）与 Requirement 4（i18n）共用 Playwright 启动栈；两个 job 可串行或并行，但 fixtures 复用。
- Requirement 5（OTel）与 Requirement 6（E2E_Smoke）相互独立，但 e2e smoke 阶段可顺带验证 OTel no-op 模式不影响业务。
- Requirement 7（Bundle Size）与 Requirement 2（覆盖率）相互独立。
- Requirement 8（DB 守护）与 Requirement 1（mypy）相互独立。
- Requirement 9（uv workspace）依赖 174 §A6 已澄清的 `src/` 边界。

### 174 兜底依赖

175 启动前置条件：

- 174 主线 B 已完成 → mypy 扩盘的目标子包都已存在
- 174 主线 C 主体已完成 → 前端 ≥1000 行 .vue 已拆，500-999 区间才有意义
- 174 docs/ Diátaxis 已落地 → `docs/explanation/`、`docs/how-to/`、`docs/reference/` 目录已存在，175 文档可直接放入

不绿则 175 启动延后。

## Migration Strategy

175 不动 DB schema，无 schema migration。所有改动均为代码/配置/CI 层面，回滚通过 git revert 即可。

uv workspace 引入：

- 旧 `pip install -e .` 流程在 174 仍可用 → 175 引入 `uv sync --workspace` 作为新增入口，不替换旧入口
- CI 在 175 内仍以 `pip install -e ".[dev]"` 为主路径；`monorepo-check` 单独跑 uv 路径作 advisory
- 176 决议是否把 uv workspace 提升为 SSOT（届时同步替换 lock 生成）

## Compatibility Constraints

- API path 0 破坏（继承 174）。
- mypy 严格扩盘只增不减；未通过的子包暂时移出 override 列表，176 补回。
- 覆盖率阈值只增不减（Coverage_Ratchet 棘轮约束）。
- A11y / i18n 阈值首次设定后只增不减。
- bundle size 阈值首次设定后只减不增（除 PR 显式 override + owner approve）。

## Validation Gates Cross-Reference

```
Requirement → Job → SLO 指标
 1 → backend-mypy-services → mypy app exit 0；ignore ≤ 80
 2 → frontend-test          → 全局 ≥ 75；HCC ≥ 90
 3 → frontend-a11y          → axe 0 critical/serious；LH a11y ≥ 0.9
 4 → frontend-i18n          → strict pass；parity pass；en-US 无中文
 5 → pytest test_telemetry_e2e → 4 命名空间全 phase span 命中
 6 → frontend-e2e-smoke     → 5 旅程绿；P95 ≤ 60s/case；总 ≤ 5min
 7 → frontend-build         → entry gzip ≤ 300KB；登录 JS ≤ 4
 8 → check-migrations       → drift 0；safety warnings 完整
 9 → monorepo-check         → check_all.sh exit 0（advisory）
10 → 文件存在性检查           → 173B_disposition.md 与三项决议
11 → PROGRESS.md §11        → 已完成 ≥ 5（可选）
```


## Correctness Properties

> 175 不强制要求 Hypothesis / fast-check 性质测试；以下"可观测正确性属性"作为推荐校验，落入对应 CI job 的断言或测试用例中。

### Property 1: mypy 扩盘单调性

**Validates: Requirements 1.2, 1.3, 1.6**

**陈述**: 任意 commit `c1, c2`（`c2` 在 `c1` 之后），若 `c1` 已通过 `backend-mypy-services` job，则 `c2` 必须也通过；否则 `c2` 必须显式从 mypy override 列表移除该子包并在 PROGRESS.md 登记降级。

**校验**: CI job 阻塞 + Coverage_Ratchet 思路扩展（不可静默回退）。

### Property 2: 覆盖率棘轮单调性

**Validates: Requirements 2.1, 2.3**

**陈述**: 全局阈值与 High_Coverage_Core 阈值任一被降低 → CI 必须 fail（通过对比 git history 中 vitest.config.ts 的阈值字段）。

**校验**: 推荐增加 `scripts/ci/check_coverage_ratchet.py`，从 `git show <base>:src/frontend/vitest.config.ts` 提取阈值与 HEAD 对比，下调即 exit 1（advisory，本轮不强制）。

### Property 3: OTel span 完整性

**Validates: Requirements 5.1, 5.10**

**陈述**: 在 `OTEL_ENABLED=true` 下，对任意核心业务方法调用，其装饰范围内创建的 span 必须 `__exit__`；不存在「孤立 active span」即任意时刻 `trace.get_current_span()` 不可在不该有 span 的地方返回非 noop span。

**校验**: `test_telemetry_e2e.py` 中至少 1 个用例通过 `InMemorySpanExporter` 验证 span 数与 `assert all(span.end_time is not None for span in exported)`。

### Property 4: i18n 双向 parity

**Validates: Requirements 4.4, 4.5**

**陈述**: zh-CN 与 en-US 的 key 集合在任意 commit 上完全相等；新增 key 必须双侧同时新增。

**校验**: `--check-parity` CI job + 推荐 pre-commit hook（advisory）。

### Property 5: bundle size 不可静默回退

**Validates: Requirements 7.2, 7.6**

**陈述**: entry chunk gzip 体积 ≤ 当前阈值 + 单次增长 ≤ 10%（除非 owner 显式 override）。

**校验**: `check_bundle_size.sh` + `compare_bundle_size.sh` 双道关卡。

### Property 6: ORM ↔ migration 等价

**Validates: Requirements 8.1, 8.2**

**陈述**: 任意 commit 上 `Base.metadata` 与 `alembic upgrade head` 后的 SQLite schema 在 175 定义的对比维度（表 / 列 / 列类型类别 / 索引 / 外键）上完全等价。

**校验**: `check_orm_schema_drift.py` 在 check-migrations job 内阻塞执行。

### Property 7: 173B 决议唯一性

**Validates: Requirements 10.2, 10.4**

**陈述**: T2 / T7 / T10 各自的决议在 `173B_disposition.md` 与 `iterations/README.md` 中三个字段（决议类型 / 责任人 / 目标日期）始终一致。

**校验**: `check_173b_disposition_consistency.py`（建议加入 ci-summary 前置）。
