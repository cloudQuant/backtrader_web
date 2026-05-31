# 迭代 178 — 安全纵深收口与质量债治理

> **创建日期**: 2026-05-31
> **前置**: 迭代 177「质量门禁修复与安全纵深」已收口（commit `e15d7bfc`，CLOSURE 完整）
> **性质**: 安全收口 / 异步正确性 / 质量债棘轮下行（非新产品特性）
> **沟通语言**: 中文；文档技术名词保留英文

---

## 0. 一句话目标

把 177 留下的**两条最硬的尾巴**收口——① git 历史里仍真实存在的交易所/数据库凭据（P0
安全事故，代码侧只清了 working tree）；② 实盘网关层阻塞 I/O 跑在 async 事件循环上的正确性
隐患（P1#4）——并继续把"advisory 门禁→blocking"与"mypy 1065 棘轮基线"按纪律往下拧，
让安全纵深和质量债**真正闭环**而非停在"已发现"。

---

## 1. 背景与根因（基于本轮巡检的实测证据）

177 修好了"CI 从不在 `dev` 跑"的根因，并在 §D 意外发现"真实凭据已进 git"。但 177 受限于
"代码侧可闭环"原则，把最关键的两件事明确登记为**顺延项**：历史凭据清除（运维）与实盘阻塞
I/O 重构（需独立分支）。本轮巡检确认这两项**仍然开放**，且 git 历史里的凭据每天都在累积
暴露面，属于必须优先处理的真实风险。

### 1.1 关键发现速览

| # | 类别 | 严重度 | 证据（本轮实测） | 现状 |
| --- | --- | :---: | --- | --- |
| F1 | git 历史仍含真实凭据 | **P0** | `git log --all -- src/backend/data/manual_gateways.json` → 命中 `f575cce6`、`b6d3097a`（**早于** 177 的 untrack 提交 `2e620ab5`）；`sync_config.json` 同样命中 | working tree 已清（177 §D），但**历史版本仍可 `git show` 取出真实 key**；secret-scan 全史步骤仍 advisory |
| F2 | 实盘网关阻塞 I/O 跑在事件循环 | **P1** | `api/live_trading/api.py` 的 `async def query_gateway_account/query_gateway_positions/get_gateway_health` 直接 `mgr.xxx()`；`manager.py` 对应方法是同步 `def`，下钻 `gateway/manual.py` 含 `subprocess.run`（L55/1042/1065/1107/1152）、`time.sleep`（L153/187/702/1464）、`urllib.request.urlopen`（L1264/1294/1308），**无 `to_thread`/`run_in_executor`** | 实盘查询/健康检查会**阻塞整个事件循环**，拖慢所有并发请求；REFACTORING_BACKLOG P1#4 |
| F3 | `pip-audit` 仍 advisory | P1 | `ci.yml:493-496` `pip-audit ... \|\| true`；本地复跑因 SSL（网络）未取到基线 | 漏洞门禁无牙齿，未拿到可信基线、未 flip blocking |
| F4 | mypy 仓库级 1065 错误长尾 | P2 | `scripts/ci/mypy_app_baseline.json` `baseline_errors: 1065`（mypy 1.20.2） | 棘轮只拦新增，存量 1065 未启动 scope 化下行 |
| F5 | 静默吞异常（observability 缺口） | P2 | `grep "except Exception" + pass` = **16 处**，集中在 `gateway/manual.py`（5）、`ctp_tunnel.py`（4）、`main.py`（2）等 | 实盘/隧道路径异常被吞且无日志，故障难定位 |
| F6 | 多个 CI 门禁仍 advisory | P2 | `monorepo-check`（`continue-on-error`）、i18n 全量 strict（`continue-on-error`）、e2e i18n（`\|\| true`）、secret-scan 全史 | 门禁"看着绿"但部分无拦截力，需逐项 flip 决策 |
| F7 | 超大文件回流（standing） | P2 | `sync_service.py` 2483、`gateway/manual.py` 2061、`live_trading/manager.py` 819… | 滚动消化，本迭代仅刷新清单 |

### 1.2 为什么 F1 是本迭代最高优先

177 CLOSURE §5.4 已把 F1 登记为 P0 运维项，但**它每多留一天，暴露面就多一天**：任何能
clone 仓库的人都能 `git show f575cce6:src/backend/data/manual_gateways.json` 拿到 Binance/
OKX/CTP/MT5/IB 的真实 key 与 MySQL root 口令。working-tree 清除（177 已做）只挡住了"未来新
clone 的人不会在最新代码里看到"，但**历史不会自己消失**。这是典型"已发现未闭环"，必须在 178
推动闭环（代码侧能做的：备好脚本、allowlist、blocking flip 的 PR；不能做的：轮换 + force-push
由 owner 执行）。

> **巡检方法论说明**：本轮所有发现均附 `file:line` 或可复现命令实测证据（见 §附），不依赖
> 177 文档的转述。

---

## 2. 范围与非范围

**本迭代做（代码/脚本/配置侧可闭环或可备好）**：

- §A F1 git 历史凭据清除**收口准备**：备好 `git filter-repo` 清除清单脚本、轮换检查单、
  历史清除后把 secret-scan 全史步骤 flip blocking 的 PR（代码侧 + 文档），轮换/force-push
  动作交 owner 按 runbook 执行。
- §B F2 实盘网关阻塞 I/O 治理（P1#4 的**可闭环切片**）：按 backlog recipe 在 async 调用点
  用 `asyncio.to_thread(...)` 包裹阻塞调用，service 内部保持同步、零行为变化；先做
  account/positions/health 三个查询路径（最高频、最易复现）。
- §C F3 `pip-audit` 拿可信基线并 flip blocking（或在已知 CVE 上加 ignore + 记录）。
- §D F5 静默吞异常审计：16 处逐一加 `logger.debug/warning`（保留吞行为但留痕），实盘路径
  优先。
- §E F4 mypy 1065 棘轮下行：选 1–2 个高价值包做 strict 清零并 `--update` 收紧 baseline
  （证明棘轮能下行，不是只挂着）。

**本迭代不做（标注清楚，避免假装完成）**：

- ⏭️ §A 的**密钥轮换 + force-push 历史重写**：破坏性、影响所有协作者、触及真实账户，
  必须 owner 执行；本迭代只交付 runbook + 脚本 + blocking-flip PR。
- ⏭️ F2 的**全量网关家族拆分**（P1#4 slice 3：按 ib/ctp/ccxt/mt5 拆文件）：触及实盘下单
  全路径，需独立分支 + 纸面交易验证；本迭代只做 async 调用点的 to_thread 包裹（slice 2）。
- ⏭️ F7 超大文件拆分：standing 规则，滚动推进。
- ⏭️ F6 中需团队策略决议的 flip（e2e 全套 PR-blocking、monorepo-check blocker）。

---

## 3. §A — git 历史凭据清除收口（P0，最高优先）

### 问题（实测）

```bash
$ git log --oneline --all -- src/backend/data/manual_gateways.json
2e620ab5 ci(security): ... untrack leaked runtime credentials (177 §D)   # 删除提交
f575cce6 update                                                           # 仍含真实 key
b6d3097a chore(dev): snapshot current workspace changes                   # 仍含真实 key
```

177 的 `git rm --cached` 只是新增一个"删除"提交，**历史快照里的明文凭据原样保留**。
`sync_config.json` 同样命中。涉及凭据见 177 CLOSURE §5.2（Binance/OKX/CTP/MT5/IB +
MySQL root，本地 + 远程 `43.167.221.188`）。

### 本迭代交付（代码侧可闭环）

1. **清除清单脚本** `scripts/ops/purge_secret_history.sh`（不自动执行，需 owner 手动运行）：
   - 用 `git filter-repo --invert-paths` 列出全部需抹除路径（9 类运行时文件，见 177 §5.3）。
   - 内置 dry-run 开关与"执行前必须确认已轮换"的交互守卫。
2. **轮换检查单** `docs/iterations/迭代178-安全纵深收口与质量债治理/ROTATION_RUNBOOK.md`：
   逐 provider 列出"重置入口 + 验证方式 + 完成打勾"，供 owner 执行并留痕。
3. **blocking-flip PR（代码侧）**：把 `ci.yml` 的 `secret-scan` 全史步骤从 advisory
   （`|| echo ::warning`）改成 blocking，**但用 feature flag / 注释门控**，标注"历史清除确认
   干净后再合入"，避免在脏历史上立刻把 CI 焊红。

### 决策点（需 owner 确认）

- 历史重写时机：是否能协调所有协作者在某窗口重新 clone？（force-push 后旧 clone 会冲突）
- 是否用 `git filter-repo`（推荐）还是 BFG。

### 验收

- [ ] `scripts/ops/purge_secret_history.sh --dry-run` 正确列出待抹除路径且不误伤。
- [ ] `ROTATION_RUNBOOK.md` 覆盖 177 §5.4 列出的全部凭据，每项可勾选。
- [ ] blocking-flip PR 就绪（门控注释清晰），等历史清除后由 owner 合入。
- [ ] REFACTORING_BACKLOG P0#3 状态更新（仍 OPEN，但补上"178 已备好 runbook+脚本"证据链）。

---

## 4. §B — 实盘网关阻塞 I/O 治理（P1，P1#4 slice 2）

### 问题（实测）

`api/live_trading/api.py`：

```python
async def query_gateway_account(...):
    result = mgr.query_gateway_account(gateway_key)   # 同步阻塞，无 to_thread
async def query_gateway_positions(...):
    positions = mgr.query_gateway_positions(gateway_key)
async def get_gateway_health(...):
    gateways = mgr.get_gateway_health()
```

`manager.py` 的这三个方法是同步 `def`，再下钻 `gateway/manual.py` 含 `subprocess.run`
（`lsof`/`ifconfig`/`scutil` 等）、`time.sleep`、`urllib.request.urlopen`。结果：**在
`async def` 里直接调用会阻塞整个事件循环**，单个慢查询拖垮所有并发请求。

> 注：`connect_gateway` 已正确用同步 `def`（FastAPI 自动丢线程池），是正面参照；问题只在
> 用了 `async def` 又调阻塞同步方法的那几个端点。

### 改动（最小、零行为变化）

- 把 `query_gateway_account` / `query_gateway_positions` / `get_gateway_health` 三个端点里
  的同步调用改为 `await asyncio.to_thread(mgr.xxx, ...)`。service 内部**不动**，符合 backlog
  P1#4 slice 2 的"在 caller 包裹、内部保持同步"原则。
- 复核 `disconnect_gateway` / `list_connected_gateways` 是否也含阻塞（按需同样处理）。
- 不触及 `connect_gateway`（已是同步 def，正确）。

### 验收

- [ ] 三个端点改用 `asyncio.to_thread`，`ruff`/`mypy` 通过。
- [ ] 现有 `test_live_trading*` / 网关相关测试全绿（行为不变）。
- [ ] 加一条针对性测试：mock 一个慢 `mgr.query_gateway_account`（`time.sleep`），断言事件
      循环在调用期间仍能处理另一并发请求（证明已 offload）。

---

## 5. §C — `pip-audit` 拿基线并 flip blocking（P1）

### 问题

`ci.yml:493-496` 仍 `pip-audit ... || true`（177 §C advisory）。本地复跑因 `pypi.org` SSL
握手失败未取到基线（环境网络问题，非代码）——说明**基线从未在干净网络里固化**。

### 改动

1. 在 CI（有干净网络）跑一轮 `pip-audit --format json` 拿到真实漏洞清单，落
   `docs/iterations/迭代178.../pip-audit-baseline.json`。
2. 对每个命中：能升级则在 `pyproject.toml` / lock 升级；暂不能升级的用
   `pip-audit --ignore-vuln <ID>` 显式 ignore 并在本迭代文档记录原因 + 复查日期。
3. 清单清干净（或全部显式 ignore 有据）后，去掉 `|| true`，flip 成 blocking。

### 验收

- [ ] `pip-audit-baseline.json` 入库，每条 CVE 有处置（升级 / ignore+理由）。
- [ ] CI `pip-audit` 步骤去掉 `|| true`，新漏洞能让 `backend-security` 红。

---

## 6. §D — 静默吞异常审计（P2，observability）

### 问题（实测 16 处）

`except Exception: pass` 集中在实盘/隧道热路径：`gateway/manual.py`（L51/73/185/495/1099）、
`ctp_tunnel.py`（L51/112/210/216）、`main.py`（L78/88）、`sync_service.py`（L537）、
`quote_service.py`（L614）、`workspace/units.py`、`workspace/run_ops.py`、
`reqdocs_migration_service.py`。实盘路径吞异常且无日志 → 线上故障无法定位。

### 改动

- 逐处评估：**保留吞行为**（多为"best-effort 清理/探测"合理吞）但补
  `logger.debug(..., exc_info=True)` 或 `logger.warning`，让异常**留痕可观测**。
- 确有 bug 风险的（如吞掉了状态写入失败）升级为 `warning` 并复核是否应重抛。
- 不为了清零而强行去掉吞——以"可观测"为目标，不是"消灭 except"。

### 验收

- [ ] 16 处全部有日志或明确"无需日志"的 inline 注释说明。
- [ ] 实盘/隧道路径（manual.py、ctp_tunnel.py）的吞异常 100% 留痕。
- [ ] 相关单测不回归。

---

## 7. §E — mypy 1065 棘轮下行（P2，证明棘轮能往下拧）

### 现状

`mypy_app_baseline.json` baseline=1065（mypy 1.20.2）。177 建立了棘轮但**只拦新增**，存量
未动。错误构成（177 §6.1）：`no-untyped-def` 614 为主。

### 改动（择 1–2 个高价值包，证明下行可行）

- 选 `app.api.live_trading` 或 `app.services.live_trading`（与 §B 同片区，改完顺手补类型）
  做 strict 清零：补 `-> ReturnType` 与参数标注。
- 清完跑 `make mypy-ratchet-update` 把 baseline 从 1065 下调，commit 说明记录"下调 N，来自
  包 X 的 no-untyped-def 清零"。
- 既有 4 个 per-package strict job 不动。

### 验收

- [ ] baseline 从 1065 **下降**（哪怕只降几十），证明棘轮是双向工作的纪律工具。
- [ ] `make mypy-ratchet` exit 0；人为调低再 +1 错误能 fail（牙齿仍在）。

---

## 8. §F — CI advisory 门禁 flip 决策清单（P2，部分可代码闭环）

| 门禁 | 当前 | 178 处置 |
| --- | --- | --- |
| `secret-scan` 全史 | advisory | §A：历史清除后 flip blocking（PR 就绪、门控） |
| `pip-audit` | advisory | §C：拿基线后 flip blocking |
| i18n 全量 strict（CJK+English） | `continue-on-error` | 复核 over-reach 是否已收敛；能则 flip，否则记录顺延理由 |
| e2e i18n（`\|\| true`） | advisory | 需 baseline 清中文泄露，本迭代评估不强 flip |
| `monorepo-check` | `continue-on-error` | 团队策略项，**不在本迭代** flip |

### 验收

- [ ] 至少把 §A、§C 两项推进到"基线/历史就绪即可 flip"的可执行状态。
- [ ] 其余项在本文件留明确"为何暂不 flip"的决策记录。

---

## 9. §G — 超大文件清单刷新（standing，仅更新优先级，不强拆）

**后端 service / api（>700 行，实测）**：

| 文件 | 行数 | 备注 |
| --- | ---: | --- |
| `services/sync_service.py` | 2483 | 176 已切 3 片，仍最大；P2 候选 |
| `services/gateway/manual.py` | 2061 | P1#4 阻塞 I/O；§B 后再议拆分（slice 3） |
| `services/live_trading/manager.py` | 819 | |
| `services/paper_trading_service.py` | 793 | |
| `services/monitoring_service.py` | 789 | |
| `services/strategy/version.py` | 785 | |
| `services/rag_service.py` | 785 | |
| `services/workspace_service.py` | 766 | backlog #6 已大幅瘦身，剩静态 helper |
| `services/ai_trading_service.py` | 754 | |
| `services/backtest/service.py` | 732 | |
| `api/live_trading/api.py` | 702 | §B 改动同片区 |

**前端 `.vue`（>1000 行，实测）**：

| 文件 | 行数 | 备注 |
| --- | ---: | --- |
| `views/KnowledgeBasePage.vue` | 1281 | |
| `components/workspace/WorkspaceUnitsTab.vue` | 1271 | |
| `views/GatewayStatusPage.vue` | 1256 | |
| `components/workspace/WorkspaceOptimizationTab.vue` | 1193 | |
| `views/QuotePage.vue` | 1185 | |
| `components/workspace/WorkspaceReportTab.vue` | 1160 | |

---

## 10. 执行顺序与提交规划

建议顺序（每项独立可验证、独立 commit）：

1. **§B**（`fix(live-trading): offload blocking gateway I/O via asyncio.to_thread`）— P1
   正确性，改面小、收益高、好验证，先做。
2. **§D**（`refactor(observability): log swallowed exceptions on live/tunnel paths`）。
3. **§E**（`ci(types): strict-clean live_trading pkg, ratchet baseline 1065→N`）。
4. **§C**（`ci(security): pin pip-audit baseline, flip to blocking`）— 依赖 CI 干净网络。
5. **§A**（`ops(security): add history-purge runbook + gated secret-scan blocking flip`）—
   代码侧交付 runbook/脚本/门控 PR；轮换 + force-push 由 owner 按 runbook 执行。

> 遵循 AGENTS.md：提交走 `dev`；177 已让 CI 在 `dev` 跑，形成"改→CI 验证→再改"闭环。
> §A 的破坏性运维动作不在 agent 执行范围，仅交付可执行物料。

---

## 11. 总体验收标准（Definition of Done）

- [x] §A：history-purge 脚本（dry-run 可用）+ ROTATION_RUNBOOK + 门控 blocking-flip PR 就绪；
      P0#3 backlog 证据链更新（仍 OPEN，待 owner 执行轮换/重写）。
- [x] §B：三个 async 网关端点改 `to_thread`（实际扩展到 7 个阻塞端点）；并发不阻塞测试通过；
      实盘相关测试全绿。
- [x] §C：`pip-audit` 基线入库、命中漏洞已处置（starlette CVE-2026-48710 → 1.0.1）、
      CI flip blocking。基线通过 OSV 批量 + `pip-audit --no-deps` 交叉验证（绕开本地 PyPI 慢链路）。
- [x] §D：16 处吞异常全部留痕；实盘/隧道路径 100% 覆盖。
- [x] §E：mypy baseline 实测下降 1065→1017 并 `--update` 收紧；棘轮牙齿验证通过。
- [x] `ruff check src/backend` = 0；`ruff format --check` 全通过；后端相关测试全绿。
- [ ] 前端 `vue-tsc` 0、`vitest` 全绿无回归。**本迭代未触前端**，沿用 177 终态。
- [x] 完成项从 `REFACTORING_BACKLOG.md` 对应条目更新（P0#3 补 178 证据链；P1#4 见 CLOSURE）。
- [x] 本迭代目录补 `CLOSURE.md` 记录终态与证据。

---

## 12. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| §A force-push 历史重写影响所有协作者 | 仅交付 runbook + 脚本，明确标注 owner 执行 + 协调窗口；不自动跑 |
| §B `to_thread` 改动触及实盘查询路径 | 改面极小（仅 caller 包裹，service 不动）；加并发不阻塞测试 + 跑全量实盘测试 |
| §C `pip-audit` flip 后 CI 因历史 CVE 焊红 | 先拿基线、逐条处置（升级/ignore+理由），确认清单为空再去 `\|\| true` |
| §D 给吞异常加日志可能刷屏 | 默认 `debug` 级；仅真正异常态用 `warning`；不改吞行为 |
| §E 强清 mypy 反而引入回归 | 只补类型标注、不改逻辑；改完跑该包全部测试 |

---

## 附：本巡检使用的核查命令（可复现）

```bash
# F1 历史仍含凭据
git log --oneline --all -- src/backend/data/manual_gateways.json
git log --oneline --all -- src/backend/data/sync_config.json
git ls-files src/backend/data/                 # 应仅 .gitkeep

# F2 阻塞 I/O 跑在 async
grep -n "async def query_gateway\|async def get_gateway_health\|to_thread" src/backend/app/api/live_trading/api.py
grep -n "subprocess.run\|time.sleep\|urlopen" src/backend/app/services/gateway/manual.py

# F3 pip-audit 门禁
grep -n "pip-audit" .github/workflows/ci.yml

# F4 mypy 基线
cat scripts/ci/mypy_app_baseline.json

# F5 静默吞异常
grep -rn -A1 "except Exception" src/backend/app --include="*.py" | grep -B1 "pass$" | grep except

# F6 advisory 门禁
grep -rn "continue-on-error\|advisory\||| true" .github/workflows/ci.yml

# F7 大文件
find src/backend/app -name '*.py' -exec wc -l {} + | sort -rn | head
find src/frontend/src -name '*.vue' -exec wc -l {} + | sort -rn | head
```
