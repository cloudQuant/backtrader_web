# 迭代 177 关闭报告 — 质量门禁修复与安全纵深

**关闭日期**: 2026-05-31
**起点**: 迭代 176 收口（commit `2c4db6cb`）
**终点**: 本迭代 §A–§E 收口 + 门禁开启后暴露的真实 bug 修复（§F）+ 既有测试欠债清零（§G）
**性质**: 质量加固 / 安全纵深 / CI 门禁修复（非新产品特性）

---

## 0. 一句话结论

修好了"CI 门禁在主开发分支 `dev` 上从不运行"的根因（§A），清零了由此回流的
lint/format 债（§B），把弃用的 `safety` 换成 `pip-audit`（§C），并接入 secret 扫描门禁
（§D）。**§D 在执行中发现了一个比 PLAN 预估更严重的真实安全事故：多个被 git 跟踪的运行时
文件中含真实交易所/数据库凭据**，本迭代已将其从版本控制中移除并加 `.gitignore`，
同时把"密钥轮换 + git 历史清除"明确登记为 P0 运维跟进项。

---

## 1. 验收结果总表

| 项 | PLAN 目标 | 终态 | 状态 |
|----|-----------|------|:---:|
| §A CI 触发分支 | `dev` push/PR 触发完整 CI | 全 workflow `develop`→`dev` | ✅ |
| §B Lint | `ruff check src/backend` = 0 | `All checks passed!` | ✅ |
| §B Format | `ruff format --check` 全通过 | `1663 files already formatted` | ✅ |
| §C 依赖审计 | `safety`→`pip-audit` advisory | CI 已切换 + dev extra | ✅ |
| §D Secret 扫描 | pre-commit + CI gitleaks | hook + 2 个 CI job（advisory 全史 + blocking PR diff） | ✅ |
| §D 泄露凭据处置 | （PLAN 未预见） | 9 类运行时文件 untrack + ignore | ✅ |
| §E mypy 仓库级棘轮 | stretch / 可选 | 实现棘轮脚本 + baseline，修复 backend-lint 的隐性红 | ✅ |
| §F 门禁开启后暴露的真实 bug | （PLAN 未预见） | 修复 akshare 导入链断裂 + 6 个 rot 测试 | ✅ |
| §G 既有测试欠债清零 | （PLAN 未预见） | 87 个确定性失败 → 0；2 个并行 flake 加 rerun | ✅ |

---

## 2. §A — CI 触发分支修复（commit `975bff11`）

按 PLAN 方案 A 推进：所有 workflow 的 `branches: [master, develop]` →
`[master, dev]`，使日常 `dev` 提交不再裸奔。验收：`dev` 上的 push/PR 现在触发完整
`CI - Quality Checks`。

## 3. §B — Lint / Format 债清零（commits `975bff11`, `9fe8f4e6`, `7af61ed9`）

- 生产代码 `app/` 20 个 lint 错误手工修复（含 `workspace_service.py` 的 E402 +
  import 乱序——176 切片遗留的 re-export 顺序问题）。
- `scripts/**` 与 `tests/**/test_performance_baseline.py` 加 `T201` per-file ignore；
  tests/scripts 的 F401/I001/F541 用 `ruff --fix` + 人工复核清掉。
- `ruff format` sweep 单独成一笔（`style`），与逻辑改动分离便于 review。
- 终态：`ruff check src/backend` = 0；`ruff format --check` = 1663 文件全已格式化。

## 4. §C — 依赖审计现代化（commit `47bded04`）

CI `backend-security` 用 PyPA 的 `pip-audit`（基于 OSV、无需账号）替换弃用的
`safety check`，先 advisory 跑一轮拿基线，下迭代再 flip blocking。`pip-audit` 已加入
`pyproject.toml` 的 dev extra。

## 5. §D — Secret 扫描门禁 + 泄露凭据处置（本次提交）

### 5.1 门禁接入

- `.pre-commit-config.yaml`：加 `gitleaks` hook（v8.30.1），本地提交即拦截硬编码密钥。
- `.gitleaks.toml`：`extend.useDefault` + 项目占位符 allowlist（`.env.example`、docs、
  `replace-with-*`、CI 测试 sentinel、`config.py` 弱口令校验常量），保证门禁高信噪比。
- `.github/workflows/ci.yml` 新增 `secret-scan` job，含两个步骤：
  - **全历史扫描（advisory）**：`fetch-depth: 0` 全史扫描，非阻塞。当前会报 ~114 个
    历史发现，多为下述真实凭据——在历史清除前会持续命中，故保持 advisory。
  - **PR diff 扫描（blocking）**：仅扫 PR 引入的 commit（`base..head`），任何**新增**密钥
    立即 fail。这让门禁**现在就有牙齿**，无需等历史清除。

### 5.2 ⚠️ 发现：真实凭据已进入 git（PLAN 未预见）

PLAN §D 假设"`.env` 已安全 ignore，仅缺自动化防御纵深"。实测 gitleaks 全史扫描发现
**被 git 跟踪的运行时文件含真实可用凭据**：

| 文件 | 泄露内容（已脱敏描述） |
|------|----------------------|
| `src/backend/data/manual_gateways.json` | Binance 实盘 API key+secret、CTP/MT5/IB 账户口令 |
| `src/backend/data/manual_gateways/*/config.json`（6 个） | 各网关 Binance/OKX api_key+secret、OKX passphrase、CTP/MT5/IB 口令 |
| `src/backend/data/sync_config.json` | 生产 MySQL root 口令（本地 + 远程 `43.167.221.188`） |
| `src/backend/data/sync_history.json` | 同步失败错误信息里内嵌的远程 MySQL 口令 |

这些文件均由后端运行时生成（`live_trading/manager.py`、`sync_service.py`、
`auto_trading_scheduler.py` 等通过 `get_backend_data_path()` 写入），加载器对缺失文件均有
`is_file()` 兜底+默认值，测试用 `tmp_path`——**不应进入版本控制**。

### 5.3 本迭代已做的处置（working-tree 级，可在本仓库闭环）

- `git rm --cached` 移除以下运行时文件（**保留磁盘副本**，应用照常运行）：
  - `manual_gateways.json` + `manual_gateways/`（config.json + .pid）
  - `sync_config.json`、`sync_history.json`
  - `auto_trading_config.json`、`live_trading_instances.json`、`quote_custom_symbols.json`
- `.gitignore` 加上述路径（修正了原 `data/manual_gateways.json` 的错误路径前缀——实际在
  `src/backend/data/` 下，旧规则从未生效）。保留 `src/backend/data/.gitkeep`。

### 5.4 ⛔ 仍需的 P0 运维跟进（非代码、本迭代不做，需人工 + 团队协调）

> 这些动作**破坏性 / 影响所有协作者 / 触及真实账户**，超出代码侧可闭环范围，
> 必须由仓库 owner 显式执行：

1. **立即轮换所有已暴露凭据**（在各 provider 侧重置）：
   - Binance API key/secret、OKX api_key/secret/passphrase
   - CTP（simnow 089763）、MT5（5047785364）、IB（quantyunjinqi999999）账户口令
   - MySQL root 口令（本地 `127.0.0.1` + 远程 `43.167.221.188`）
2. **清除 git 历史**：`git filter-repo` 或 BFG 抹除上述文件全部历史版本，
   force-push，并通知所有协作者重新 clone/rebase。
3. 历史清除确认干净后，把 `secret-scan` 全历史步骤从 advisory 翻成 blocking。

---

## 6. §E — mypy 仓库级棘轮（commit 本次）

### 6.1 ⚠️ 又一处隐性红（PLAN 低估）

PLAN 把 §E 标为 stretch/可选，依据是"已清包之外新增 type 错误不会 fail CI"。但实测
发现：`backend-lint` job 里有一个**阻塞**的 `Run Mypy type check` 步骤（`mypy app`，
无 `continue-on-error`），它和 F2 的 ruff 债是同一种"CI 从不在 dev 跑 → 静默腐烂"：
当前 `mypy app` 报 **1055 个错误**（355 文件，mypy 1.20.2）。§A 把 CI 在 `dev` 打开后，
这一步会让 `backend-lint` 立刻红——而 §B 只清了 ruff。

错误构成（前几类）：`no-untyped-def` 614、`attr-defined` 170、`arg-type` 103、
`assignment` 89、`union-attr` 20、`var-annotated` 19……多为历史欠的类型标注。

### 6.2 处置：棘轮而非假装清零

新增 `scripts/ci/mypy_ratchet.py` + `scripts/ci/mypy_app_baseline.json`（baseline=1055，
pin mypy 1.20.2）：

- 把 `backend-lint` 的 `mypy app` 步骤换成 `python ../../scripts/ci/mypy_ratchet.py`。
- 棘轮只在**错误数增加**时 fail（拦住新债），下降时提示 `--update` 收紧 baseline。
- 为可复现，`backend-lint` 安装步骤把 mypy pin 到 `1.20.2`（与 baseline 一致；
  dev lock 是 2.1.0，不同版本计数不可比，脚本会在版本不符时打 `::warning::`）。
- 既有的 per-package strict 门（`backend-mypy-*` 4 个 job）仍对已登记 scope 强制 0，
  不受影响。
- `Makefile` 加 `make mypy-ratchet` / `make mypy-ratchet-update`。

验收：本地 `python scripts/ci/mypy_ratchet.py` → `errors=1055 baseline=1055 delta=+0`
（exit 0）；人为把 baseline 调低 5 → exit 1 并打印 `::error::`，证明棘轮有牙齿。

---

## 6.5 §F — 门禁开启后暴露的真实 bug 与既有测试欠债（commit `22fef8d9`）

§A 把 CI 在 `dev` 打开后，跑后端测试立即暴露了一批"门禁从不运行 → 静默腐烂"的问题。
逐一核实它们**均先于 177 存在**（在起点 commit `2c4db6cb` 上同样失败），即非本迭代引入。

### 6.5.1 真实生产 bug：akshare 导入链断裂

176 之前的 `e96834fb`「remove 31 sys.modules shim files」把 akshare 模块重构进包，但
遗漏了 **14 处内部 import** 仍指向已删除的扁平 `app.services.akshare_*` shim。后果：
`import app.api.akshare` 直接失败 → akshare 可选路由（interfaces/tables/scripts/tasks/
executions）与 `/data/interfaces` 旧端点静默降级为 404。因 CI 从不在 dev 跑，无人发现。

修复：把所有引用改到新包路径（`akshare.execution` / `akshare.scheduler` /
`akshare.scheduler_service` / `akshare.script` / `akshare.data` / `akshare.interface` /
`akshare.interface_loader`）。验证：所有相关模块 import OK，`test_data_governance_compat`
转绿。

### 6.5.2 测试 rot（6 个，均为引用了被移动的符号/路径）

| 测试 | 问题 | 修复 |
|------|------|------|
| `test_smoke_ctp_gateway_script` | 脚本 reorg 后路径失效 | `scripts/` → `scripts/diagnostics/` |
| `test_api_router_optional_imports` | blocked 集用了旧 `strategy_version` 路径 | → `app.api.strategy.version` |
| `test_api_edge_cases_113`（realtime） | `app.api.realtime_data` 已移动 | → `app.api.data.realtime` |
| `test_api_edge_cases_113`（strategy_version） | 同上 | → `app.api.strategy.version` |
| `test_api_edge_cases_113`（templates） | patch `api.get_template_by_id` 不在包命名空间 | import `app.api.strategy.base` |
| `test_akshare_management_api` fixture | 旧扁平模块 | → `app.services.akshare.data` |

mypy 棘轮 baseline 1055 → **1065**：修好导入后，原先因 import 失败而无法分析的 akshare
`data_fetch` 代码变得可被 mypy 看见，暴露了既有的 Optional-cursor 等隐性告警（非新 bug）。
按棘轮纪律 `--update` 收录为新基线并在 commit 说明记录原因。

### 6.5.3 既有测试欠债盘点（先于 177）→ 已在 §G 清零

门禁开启后，全量 `pytest -n auto`（非 e2e/perf）首跑暴露 **87 个确定性失败**（先于 177，
在起点 commit 上同样失败，"CI 从不在 dev 跑"长期积累所致）。这批欠债已在 **§G 全部清零**
（见下）。本节保留作为问题发现的记录。

> 这一盘点本身就是 177 的价值：门禁修好后，长期被掩盖的欠债第一次变得可见、可度量、并清零。

---

## 6.6 §G — 既有测试欠债清零（commits `0eaa56dc`, `dd7cf29f`）

全量首跑：**87 failed / 3010 passed**。逐一定位根因后，终态 **0 个确定性失败**
（3097 passed），过程零行为回归。绝大多数是历史重构搬走模块/符号但未更新调用点或测试。

### 6.6.1 生产 bug（门禁开启才暴露，真实影响线上）

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `app/api/router.py` | 可选路由 `realtime_data` 指向已删除的扁平 `app.api.realtime_data`，导致整个 `/api/v1/realtime/*` API 静默 404 | 改指 `app.api.data.realtime` |
| 2 | `app/services/workspace_unit_runtime.py` | 策略模板目录缺失时 `sync_trading_unit_runtime` 抛 `FileNotFoundError`，使建单接口 500（`src/strategies/` 是开发机本地、未入库） | `_sync_trading_runtime_sources` 缺失即跳过+告警；`_strategy_module_name` 返回 `""` 不再抛；补模块级 logger |

### 6.6.2 测试 rot（引用了被重构搬走的模块/符号路径）

| 测试文件 | 旧路径 → 新路径 |
|----------|----------------|
| `test_strategy_version_service/api`、`test_service_edge_cases_113`、`test_param_optimization_service_branches`、`test_monitoring_strategy_version_edge_cases`、`test_misc_edge_cases` | `app.services.strategy_version_service` → `app.services.strategy.version`；`app.api.strategy_version` → `app.api.strategy.version` |
| `test_live_trading_service`、`test_service_edge_cases_113` | `app.services.live_trading_service` → `app.services.live_trading.service` |
| `test_strategy_score_api` / `test_strategy_explainer_api` | patch 目标 → `app.api.strategy.score` / `app.api.strategy.explainer` |
| `test_orchestration/test_backend_contract` | patch 目标 → `app.services.akshare.scheduler` |
| `test_api_router_optional_imports` | blocked 集 → `app.api.strategy.version` / `app.api.data.realtime` |
| `test_misc_branch_fixes` | 已删除的 `app.api.deps_permissions` shim → 改测 `deps` → `_dependencies` 现存委托 |
| `test_news_classifier` | 还原被误删的 `data/news_labelled_200.csv` 黄金集 |

### 6.6.3 测试对未入库模板目录的依赖（自包含化）

`test_trading_workspace_service`（2）与 `test_workspace_trading_api`（4）依赖
`src/strategies/simulate/gateway_*` 模板（gitignore、未入库）。改为测试内自建最小模板
（`run.py` + `strategy_*.py`）并用完清理，不再依赖 checkout 特定目录。

### 6.6.4 并行 flake（非确定性，非回归）

`test_login_rate_limit` 与 `test_data_topics_websocket_streams_single_topic_update` 在
**单独/小并行**下稳定通过，仅在 ~3100 全量 `-n auto` 高负载下偶发（共享内存限流器时间窗 /
websocket 异步投递时序）。断言本身正确、非回归，故用 `@pytest.mark.flaky(reruns=3)`
（pytest-rerunfailures）隔离，而非弱化断言。CI 用 `-n auto`，此举保门禁绿且不掩盖真实 bug。

### 6.6.5 mypy 棘轮

§G 的导入修复让原先因 import 失败而无法分析的 akshare `data_fetch` 代码可被 mypy 看见，
baseline 1055 → **1065**（见 §F；非新 bug，是类型覆盖扩大）。后续 §G 改动 baseline 稳定 1065。

---

## 7. 未完成 / 顺延项

- **§E mypy 仓库级棘轮**：已完成（见上）。注：1055 个 baseline 错误本身是长尾欠债，
  后续迭代按 scope 逐步清并 `--update` 收紧。
- **F5 超大文件拆分**：standing 规则，按既有纪律滚动推进，本迭代不强拆。
- **P1#4 `manual_gateway_service` 阻塞 I/O 重构**：触及实盘下单，需独立分支 + 纸面验证。

---

## 8. 复现命令

```bash
# §A 分支触发
grep -rn "branches:" .github/workflows/*.yml      # 应为 [master, dev]

# §B lint/format
ruff check src/backend                            # 0 errors
ruff format --check src/backend                   # all formatted

# §D secret 扫描（全史，advisory）
gitleaks detect --config .gitleaks.toml --no-banner --redact

# §D 确认泄露文件已 untrack 且 ignore
git ls-files src/backend/data/ | grep -v .gitkeep # 应为空
git check-ignore src/backend/data/sync_config.json

# §E mypy 棘轮
make mypy-ratchet                                 # errors=1055 baseline=1055 delta=+0
```
