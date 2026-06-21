# 迭代 181 - 本轮改进与验收记录

> 验收日期：2026-06-16
> 范围：本轮优先落地 181-A / 181-B / 181-C / 181-D / 181-E 中可安全闭环的代码项；不执行历史重写、force-push、provider 凭据轮换等 owner 运维动作。

---

## 1. 已完成改进

### 181-A 敏感文件治理

- 已将 `src/bt_api_py/configs/ibkr_cookies.json` 中的 IBKR cookie-like 值替换为 `replace-with-*` 占位符。
- 新增 `scripts/ci/check_sensitive_tracked_files.py`，对 git 跟踪文件中的 `.env`、cookie、key、keystore、DB、zip 等敏感候选做 allowlist 分类检查。
- 已把敏感候选检查接入 `scripts/ci/check-generated-artifacts.sh`，避免后续未分类敏感文件静默入库。
- 当前分类候选为 3 个：IBKR cookie 示例、`src/clientportal.gw/root/demo.zip`、`src/clientportal.gw/root/vertx.jks`。

### 181-B sync 命令执行与密码暴露收口

- `src/backend/app/services/sync/transport.py` 新增 `redact_text()` / `redact_command()`。
- `run_exec()` 的失败和超时路径不再把原始 `-p<password>` / `MYSQL_PWD=...` 暴露到异常消息。
- 新增 `SensitiveArgs`，MySQL CLI 构造函数不再返回含 `-p<password>` 的 argv。
- 直接执行路径通过 0600 临时 `--defaults-extra-file` 注入密码，执行完成后清理。
- 本地 `bash` 与远端 `ssh` 改为 `bash -s` + stdin 脚本，避免把含敏感内容的脚本放入进程参数。
- 远端 Docker dump/query 改为 `docker exec -i ... sh -s` + heredoc；远端 Docker import 先通过 stdin 写容器内临时 defaults 文件，再执行不含密码 argv 的 `mysql --defaults-extra-file=...`。
- database / table / object / column / index / view 名称增加 MySQL-safe identifier 白名单。
- `mysqldump --where` 改为只接受内部 builder 产生的 `InternalWhereSql`。
- 新增 `docs/operations/SYNC_SECURITY.md`，说明新的凭据注入方式、限制和排障方法。
- 新增 `src/backend/tests/test_sync_transport_security.py` 覆盖：
  - `mysql -p...` 参数脱敏。
  - `MYSQL_PWD=...` shell 片段脱敏。
  - 子进程失败路径脱敏。
  - MySQL builder 不再把密码放入 argv。
  - `run_exec()` 会物化临时 defaults 文件并在执行后清理。
  - `run_bash()` / `run_ssh()` 通过 stdin 传脚本，不把敏感脚本放入 argv。
  - Docker shell helper 不再使用 `sh -lc` argv 承载内部脚本。
  - 恶意标识符被拒绝。
  - 裸字符串 `where_sql` 被拒绝。

### 181-C Gateway 阻塞 I/O 与大文件切片

- 新增 `src/backend/app/services/gateway/manual_ports.py`：
  - 承接端口占用进程清理。
  - 承接 base URL endpoint 解析。
  - 承接 TCP endpoint 可达性探测和等待逻辑。
  - 保留 psutil-first，只有 psutil 不可用时才 fallback 到 `lsof`。
- 新增 `src/backend/app/services/gateway/manual_ctp_proxy.py`：
  - 承接 macOS `utun` 计数和 TUN 代理识别。
  - 承接 CTP 直连路由、Clash DIRECT 规则、代理 bypass 文件写入。
  - 承接 CTP HTTP CONNECT 隧道决策和 TUN proxy 用户提示。
- `manual.py` 保留原 `_xxx` 私有入口作为薄包装层，兼容现有调用和测试 monkeypatch 点。
- `manual.py` 从 2044 行降到 1697 行，达到 181-C / 181-G 对 gateway 切片的行数目标。
- 新增 `src/backend/tests/test_gateway_manual_helpers.py`，直接覆盖新增 helper 模块关键路径。

### 181-E CI advisory baseline-gated

- `scripts/dev/check_i18n_coverage.py` 增加 `--baseline-file` 和 `--max-output`。
- `.github/workflows/ci.yml` 中 full strict i18n 从 `continue-on-error` advisory 改为 baseline-gated blocking step。
- `scripts/dev/check_i18n_coverage_baseline.json` 更新到当前工作树 `15076` full strict violations，CJK baseline 保持 0。
- 清理 stock analysis 前端新增 CJK 裸字符串，`--strict --cjk-only` 恢复 0。

### 181-D 前端 HTML 与 Token 存储收口

- `StrategyDetailDialog.vue` 改为接收 raw markdown，并在组件内部调用 `renderMarkdown()` 后再进入 `v-html`。
- `StrategyPage.vue` 移除 `renderedReadme` HTML prop 传递，减少调用方忘记 sanitizer 的风险。
- `markdown-sanitizer.ts` 加固：
  - 预清理 `script` / `iframe` / `object` / `embed` 远程执行或加载标签。
  - 移除 `on*` 事件属性。
  - 移除 `href/src` 上的 `javascript:` / `data:` 危险 URI 属性。
  - DOMPurify 后再做一次保底清理。
- 新增 `StrategyDetailDialog` XSS 回归测试。
- `session.ts` 中 `setAccessToken()` 改为兼容性 no-op，不再主动写 legacy `localStorage`；保留读取和清理逻辑用于迁移窗口。
- 更新 `session.test.ts`，明确验证不再写入 legacy `localStorage`。

### 181-F 类型逃逸小棘轮

- 后端业务代码 `type: ignore` 从 11 处降到 1 处：
  - 去掉 `optimization/task_gateway.py` 中 Optional dict 访问的 3 个 ignore。
  - 去掉 `live_trading/manager.py` 中 loguru/stdlib logger fallback 的 assignment ignore。
  - 去掉 `utils/logger.py` 中 frame walk 的 assignment ignore。
  - 去掉 `middleware/metrics.py` 中 Prometheus 可选导入 fallback 的 4 个 ignore。
  - 去掉 `data_fetch/utils/common_utils.py` retry decorator 的 return-value ignore。
  - 剩余 1 处为 `pandas` 第三方 stub 缺失：`data_fetch/core/database.py` 的 `import-untyped`。
- 前端生产代码显式 `any` 清零：
  - `OptionsChainPage.vue` 增加 `OptionChainRow` / `OptionLeg` 类型。
  - `WorkspaceOptimizationTab.vue` 增加 optimization display settings 类型，并用 `CSSProperties` 替代 dialog style `as any`。
  - `GatewayStatusPage.vue` 增加 gateway credentials 类型，避免 connect form 使用 `Record<string, any>`。
  - `api/index.ts` 注释去掉 `(e: any)` 示例，便于静态扫描清零。
- repo-wide mypy baseline 未下调：当前工作树 `python ../../scripts/ci/mypy_ratchet.py` 报 `1030` errors，高于 baseline `958`；主要新增集中在未收口的 `app/services/stock_analysis/tasks.py` SQLAlchemy 模型属性类型，以及既有 `app/db` / `app/middleware` 错误。
- 前端测试 `as any` 存量未在本轮下降，当前扫描为 670 处，作为后续 typed mount helper 棘轮基线。

---

## 2. 验收结果

| 验收项 | 命令 | 结果 |
| --- | --- | --- |
| 敏感候选文件分类检查 | `python3 scripts/ci/check_sensitive_tracked_files.py` | 通过：`Sensitive tracked file check passed (3 classified candidate files).` |
| 生成物 + 敏感候选 CI 检查 | `./scripts/ci/check-generated-artifacts.sh` | 通过 |
| sync transport / service Ruff | `ruff check app/services/sync/schema_diff.py app/services/sync/transport.py app/services/sync_service.py tests/test_sync_schema_diff.py tests/test_sync_transport_security.py` | 通过 |
| sync transport 安全专项测试 | `pytest tests/test_sync_transport_security.py -q` | 通过：12 passed，1 个 backtrader quandl deprecation warning |
| sync 周边测试 | `pytest tests/test_sync_transport_security.py tests/test_sync_schema_diff.py tests/test_sync_progress.py -q` | 通过：76 passed，1 个 backtrader quandl deprecation warning |
| sync 高风险源码扫描 | `rg -n 'f"-p\{password\}"\|MYSQL_PWD=.*password\|sh -lc\|bash -lc\|join_command\(args\)' src/backend/app/services/sync src/backend/app/services/sync_service.py` | 通过：无命中 |
| gateway helper Ruff | `ruff check app/services/gateway/manual.py app/services/gateway/manual_ports.py app/services/gateway/manual_ctp_proxy.py tests/test_gateway_manual_helpers.py tests/test_gateway_net_probe.py tests/test_extracted_modules.py` | 通过 |
| gateway helper / extracted / net probe 测试 | `pytest tests/test_gateway_manual_helpers.py tests/test_gateway_net_probe.py tests/test_extracted_modules.py -q` | 通过：127 passed，2 skipped，1 个 backtrader quandl deprecation warning |
| gateway / live trading 通配测试 | `pytest tests/test_*gateway* tests/test_live_trading* -q` | 通过：234 passed，1 个 backtrader quandl deprecation warning |
| gateway 行数验收 | `wc -l src/backend/app/services/gateway/manual.py` | 通过：1697 行 |
| 前端 Markdown / Dialog / Session / StrategyPage / AIChat / stock analysis 专项测试 | `npm run test -- --run src/__tests__/utils/markdown-sanitizer.test.ts src/__tests__/components/strategy/StrategyDetailDialog.test.ts src/__tests__/utils/session.test.ts src/__tests__/views/StrategyPage.test.ts src/__tests__/views/AIChatPage.test.ts src/__tests__/stores/kbChat.test.ts src/__tests__/components/aichat/StockAnalysisTaskCard.test.ts src/__tests__/components/aichat/StockAnalysisReportCard.test.ts` | 通过：8 files，89 tests |
| 前端类型检查 | `npm run typecheck` | 通过 |
| 本轮前端改动文件 lint | `npx eslint src/composables/useAIChatPage.ts src/views/AIChatPage.vue src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/views/StrategyPage.vue src/views/strategy-components/StrategyDetailDialog.vue src/utils/session.ts src/utils/markdown-sanitizer.ts src/views/OptionsChainPage.vue src/components/workspace/WorkspaceOptimizationTab.vue src/views/GatewayStatusPage.vue src/api/index.ts src/__tests__/components/strategy/StrategyDetailDialog.test.ts src/__tests__/utils/session.test.ts src/__tests__/views/StrategyPage.test.ts src/__tests__/views/AIChatPage.test.ts` | 通过 |
| 前端类型逃逸扫描 | `rg -n "as any|: any|Record<string, any>|Array<Record<string, any>>|<any>" src/frontend/src --glob '!**/__tests__/**' --glob '!**/*.test.ts' --glob '!**/*.spec.ts'` | 通过：无命中 |
| 前端类型小项测试 | `npm run test -- --run src/__tests__/views/OptionsChainPage.test.ts src/__tests__/views/GatewayStatusPage.test.ts src/__tests__/components/workspace/WorkspaceOptimizationTab.test.ts` | 通过：3 files，14 tests |
| 后端 `type: ignore` 扫描 | `rg -n "type:\\s*ignore|#\\s*type:\\s*ignore" src/backend/app` | 通过：1 处，仅 `pandas` `import-untyped` |
| 后端类型小项 Ruff | `ruff check app/services/optimization/task_gateway.py app/services/live_trading/manager.py app/utils/logger.py app/middleware/metrics.py app/data_fetch/utils/common_utils.py app/data_fetch/core/database.py` | 通过 |
| 后端类型小项 mypy | `mypy app/services/optimization/task_gateway.py app/services/live_trading/manager.py app/utils/logger.py app/middleware/metrics.py app/data_fetch/utils/common_utils.py --show-error-codes` | 通过 |
| 后端类型小项测试 | `pytest tests/test_optimization_helpers.py tests/test_enhanced_logger.py tests/test_live_trading_manager.py -q` | 通过：100 passed，3 skipped，1 个 backtrader quandl deprecation warning |
| metrics API 回归 | `pytest tests/test_api_routes.py::TestMonitoringAPI::test_get_metrics -q` | 通过：1 passed，1 个 backtrader quandl deprecation warning |
| mypy repo-wide 棘轮 | `python ../../scripts/ci/mypy_ratchet.py` | 未通过：1030 errors > baseline 958，未下调 baseline |
| i18n CJK blocking gate | `python3 scripts/dev/check_i18n_coverage.py --strict --cjk-only --max-output 20` | 通过：0 CJK violations |
| i18n full strict baseline gate | `python3 scripts/dev/check_i18n_coverage.py --strict --baseline-file scripts/dev/check_i18n_coverage_baseline.json --max-output 5` | 通过：15076 <= baseline 15076 |
| i18n parity | `python3 scripts/dev/check_i18n_coverage.py --check-parity` | 通过：2711 keys each side |

---

## 3. 未完成阻断项

### 181-A 仍需 owner 执行

- provider 凭据轮换、git 历史 purge、force-push、协作者 re-clone 未由 agent 执行。
- `SECRET_SCAN_HISTORY_BLOCKING=true` 仍应在历史清理完成并确认 CI 通过后再启用。
- `demo.zip` / `vertx.jks` 已有 allowlist 门禁，但仍建议补来源、校验和和 owner 说明。

### 181-F / 181-G 剩余项

- mypy baseline 958 -> 900 未完成；当前工作树 repo-wide mypy 为 1030，需要先收口 stock_analysis / db / middleware 类型错误。
- 前端测试 `as any` 棘轮未完成；当前存量 670 处。
- `sync_service.py` 进一步下降到 2100 行以下、前端 >1200 行页面拆分仍未在本轮执行。

---

## 4. 本轮结论

本轮已闭环 181-A 的新增门禁、181-B 的 sync 密码 argv / shell 参数泄露和 identifier/filter 约束、181-C 的 gateway helper 切片、181-D 的前端 XSS/Token 尾巴、181-E 的 i18n full strict baseline gate，以及 181-F 的 `type: ignore` / 前端生产 `any` 小棘轮。
剩余高价值工作转向 repo-wide mypy baseline、前端测试 typed helper 和更大范围的大文件棘轮。
