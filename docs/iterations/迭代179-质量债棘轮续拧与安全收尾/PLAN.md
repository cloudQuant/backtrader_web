# 迭代 179 — 质量债棘轮续拧与安全收尾

> **创建日期**: 2026-05-31
> **前置**: 迭代 178「安全纵深收口与质量债治理」已收口（commit `6c386388`，CLOSURE 完整）
> **性质**: 质量债棘轮下行 / 异步正确性深化 / 安全收尾（非新产品特性）
> **沟通语言**: 中文；文档技术名词保留英文

---

## 0. 一句话目标

在 178「安全纵深 + 阻塞 I/O slice 2 + mypy 1065→1017」收口的基础上，继续把质量债棘轮
**实测往下拧**，并清掉本轮巡检新发现的两个真实小尾巴——① git 里仍跟踪着一个本不该入库的
运行时产物 `src/backend/.slowapi.env`；② `gateway/manual.py` 仍是阻塞 I/O 与超大文件的双重
重灾区（178 §B 只在 caller 包了 `to_thread`，文件本身的 `subprocess.run(["ifconfig"/"scutil"
/"lsof"])` 与 2061 行体量没动）——让"已发现"继续向"已闭环"收敛，而非停在巡检报告里。

---

## 1. 背景与根因（基于本轮巡检的实测证据）

178 收口质量很高：§A–§F 全部代码侧闭环，mypy baseline 实测 1065→1017，`pip-audit` 已 flip
blocking，16 处吞异常全部留痕（本轮复扫 = 0，无回归）。本轮巡检**不重复 178 已闭环项**，只
登记仍然开放或新冒头的问题，且每条附 `file:line` 或可复现命令实测证据。

### 1.1 关键发现速览

| # | 类别 | 严重度 | 证据（本轮实测，2026-05-31） | 现状 |
| --- | --- | :---: | --- | --- |
| G1 | git 历史仍含真实凭据 | **P0** | `git log --all -- src/backend/data/manual_gateways.json` 仍命中 `f575cce6`/`b6d3097a`；working tree 已清（`git ls-files src/backend/data/` 仅 `.gitkeep`） | 178 §A 已备好 runbook+脚本+门控 flip；**轮换 + force-push 仍待 owner 执行** |
| G2 | 运行时产物 `.slowapi.env` 被 git 跟踪 | **P1** | `git ls-files \| grep .env` → 命中 `src/backend/.slowapi.env`（`wc -l` = 0，空文件，slowapi 限流落盘产物） | 不是密钥泄露，但是**不该入库的运行时状态**；`.gitignore` 未覆盖 |
| G3 | `gateway/manual.py` 阻塞 I/O + 超大文件 | **P1** | `subprocess.run(["ifconfig"])` L1042、`subprocess.run(["scutil","--proxy"])` L1051、`lsof` 兜底 L56；文件 2061 行（全仓第 2 大） | 178 §B 只在 async caller 包 `to_thread`（slice 2）；**slice 1（抽纯 helper）/ slice 4（psutil-only 端口发现）未做**；REFACTORING_BACKLOG P1#4 仍 OPEN |
| G4 | mypy 仓库级 1017 错误长尾 | P2 | `mypy_app_baseline.json` baseline_errors 为 1017（mypy 1.20.2） | 178 证明棘轮能下行（降幅 48）；存量 1017 仍以 no-untyped-def 为主，需继续选包清零 |
| G5 | 4 个 CI 门禁仍 advisory | P2 | `.github/workflows/ci.yml` `continue-on-error` L658（PR-template i18n）/L950（i18n strict）/L1098+L1116（monorepo-check）；`|| true` L978（e2e i18n） | 门禁"看着绿"但无拦截力；逐项 flip 或留明确顺延理由 |
| G6 | 超大文件回流（standing） | P2 | `sync_service.py` 2490（178 时 2483，**反增 7 行**）、`gateway/manual.py` 2061、`live_trading/manager.py` 819… | 滚动消化，本迭代结合 G3 仅切 `manual.py` slice 1 |
| G7 | 前端 `: any` 18 处 / 后端 `type: ignore` 11 处 | P3 | `grep -rn ": any" src/frontend/src` = 18；`grep -rn "type: ignore" src/backend/app` = 11 | 类型逃逸口子，本迭代仅刷新清单，不强清 |

> **已确认无新增风险（本轮实测，免得误以为遗漏）**：`verify=False` = 0；`shell=True` = 0；
> `eval(`/`exec(` 仅 `utils/sandbox.py`（策略沙箱，受限 builtins，设计内）与 `scanner_service.py`
> （`{"__builtins__": {}}` 受限 eval）；`pickle.load` 仅 `data_fetch/.../fund_detail_info.py`
> 读本地自产 `lost_codes.pkl`（可信）；`except Exception: pass` = 0（178 §D 无回归）。

### 1.2 为什么 G2/G3 是本迭代的代码侧重点

- **G2** 是 178 收口后新浮出的小尾巴：178 把 `data/` 下的运行时文件 untrack 了，但
  `src/backend/.slowapi.env` 这个限流落盘产物漏在网外，仍被跟踪。它现在是空文件、无泄露，
  但 slowapi 在生产可能写入限流计数/状态，**属于"运行时状态混进版本库"的同类问题**，应在它
  写入敏感内容前 untrack + gitignore，零风险、几分钟可闭环。
- **G3** 是 P1#4 里**代码侧仍能安全推进的最大块**：178 §B 已证明 caller 包 `to_thread`
  零行为变化、可验证。slice 1（把端口发现/错误解析/env 自动探测抽成 `gateway/manual_utils.py`
  纯函数）与 slice 4（用 `psutil` 取代 `subprocess.run(["lsof"/"ifconfig"/"scutil"])`，去掉对
  非 Python 外部命令的依赖）都是**纯函数 / 等价替换**，不触及实盘下单路径，可在 `dev` 上
  "改→CI→再改"闭环；唯独 slice 3（按 ib/ctp/ccxt/mt5 拆文件）触及下单全路径，仍顺延。

---

## 2. 范围与非范围

**本迭代做（代码/配置侧可闭环）**：

- §A G2 `.slowapi.env` 收口：`git rm --cached` untrack + `.gitignore` 补规则 + 验证加载器
  在文件缺失时能自建（不破坏限流功能）。
- §B G3 `gateway/manual.py` slice 1 + slice 4（P1#4 的可闭环切片）：
  - slice 1：抽纯 helper（端口发现、错误解析、env 自动探测）到 `gateway/manual_utils.py`，
    纯函数、零行为变化、补类型与单测。
  - slice 4：端口/网络探测优先走 `psutil`，`subprocess.run(["lsof"/"ifconfig"/"scutil"])`
    降为有据兜底链，去掉硬依赖外部命令。
- §C G4 mypy 1017 棘轮续拧：选 1–2 个高价值包 strict 清零并 `--update` 收紧 baseline
  （延续 178 §E 纪律，证明棘轮持续双向工作）。
- §D G5 advisory 门禁 flip 决策：逐项给"能 flip / 暂不 flip + 理由"的可执行结论，至少推进
  PR-template i18n（最易 flip）到 blocking。
- §E G6 超大文件清单刷新（standing），结合 §B 记录 `manual.py` 下行证据。

**本迭代不做（标注清楚，避免假装完成）**：

- ⏭️ §A(G1) 的**密钥轮换 + force-push 历史重写**：178 已交付全部工具，破坏性运维动作必须
  owner 执行；本迭代仅在 backlog 补"179 复核工具仍就绪"证据链，不重复造轮子。
- ⏭️ G3 slice 3（按网关家族拆文件）：触及实盘下单全路径，需独立分支 + 纸面交易验证。
- ⏭️ G5 中需团队策略决议的 flip（monorepo-check blocker、e2e 全套 PR-blocking、i18n 全量
  strict——14k over-reach 需 scanner 启发式，见 178 §F）。
- ⏭️ G6 `sync_service.py`（2490）拆分、G7 `any`/`type: ignore` 强清：滚动推进，仅刷新清单。
- ⏭️ 前端：本迭代不触前端（沿用 178 终态：vue-tsc 0 / vitest 全绿）。

---

## 3. §A — `.slowapi.env` 运行时产物收口（P1，几分钟可闭环）

### 问题（实测）

```bash
$ git ls-files | grep -E "\.env$"
src/backend/.slowapi.env          # 被跟踪
$ wc -l src/backend/.slowapi.env
0 src/backend/.slowapi.env         # 当前空，但属 slowapi 限流落盘产物
$ grep -n "slowapi" .gitignore      # 无命中 → .gitignore 未覆盖
```

178 把 `data/` 下运行时文件 untrack 了，这个限流产物漏网。空文件无泄露，但运行时 slowapi
可能写入限流状态，应在它变"脏"前收口。

### 改动（最小）

1. `git rm --cached src/backend/.slowapi.env`（保留磁盘文件，仅停止跟踪）。
2. `.gitignore` 增加 `*.slowapi.env` / `**/.slowapi.env` 规则。
3. 复核 slowapi 初始化代码：确认文件缺失时能自建（不影响限流功能）。

### 验收

- [ ] `git ls-files | grep slowapi` 为空（已 untrack）。
- [ ] `.gitignore` 命中该路径；新 clone 不会重新跟踪。
- [ ] 后端启动 / 限流相关测试全绿（限流功能不回归）。

---

## 4. §B — `gateway/manual.py` slice 1 + slice 4（P1，P1#4 续作）

### 问题（实测）

```bash
$ grep -n "subprocess.run\|lsof\|ifconfig\|scutil" src/backend/app/services/gateway/manual.py
56:   ["lsof", "-nP", f"-iTCP:{port}", ...]        # 端口占用发现兜底
1042: subprocess.run(["ifconfig"], ...)            # 网络接口探测
1051: subprocess.run(["scutil", "--proxy"], ...)   # 代理探测
# 文件 2061 行，全仓第 2 大
```

178 §B 已在 async caller 包了 `to_thread`（slice 2，正确性已收口），但**文件内部仍直接 shell
out 到 `lsof`/`ifconfig`/`scutil`**——这既是阻塞调用，也对运行环境强加"必须装这些命令"的隐式
依赖（容器/精简镜像里可能没有），且 2061 行的体量让任何改动都难审查。

### 改动（纯函数抽取 + 等价替换，零行为变化）

- **slice 1**：把可独立的纯 helper 抽到新文件 `gateway/manual_utils.py`：
  - 端口占用发现、网关错误信息解析、env 自动探测等无 `self` 依赖的逻辑。
  - 纯函数、补完整类型标注、迁出后原处改为 import 调用（保持对外 API 不变）。
  - 为抽出的 helper 补针对性单测。
- **slice 4**：端口/网络探测优先 `psutil`：
  - 端口占用：`psutil.net_connections()` 为主，`lsof` 降为"psutil 不可用时"的兜底。
  - 接口/代理探测：能用 `psutil`/标准库的走库，`subprocess.run` 仅作有注释的兜底链。
  - 去掉"必须装 lsof/ifconfig/scutil"的硬依赖，跨平台更稳。

> 严格不动：实盘下单路径、`connect_gateway` 生命周期、gateway 家族拆分（slice 3 顺延）。

### 验收

- [ ] `manual_utils.py` 抽出后 `manual.py` 行数下降（记录下行数值），`ruff`/`mypy` 通过。
- [ ] 端口/网络探测在 psutil 可用时不再 shell out；psutil 缺失时兜底链仍工作。
- [ ] 现有 `test_*gateway*` / `test_live_trading*` 全绿（行为不变）。
- [ ] 抽出的纯 helper 有针对性单测覆盖。
- [ ] REFACTORING_BACKLOG P1#4 更新：slice 1/4 标记完成，slice 3 仍 OPEN（补 179 证据链）。

---

## 5. §C — mypy 1017 棘轮续拧（P2，延续 178 §E）

### 现状

`mypy_app_baseline.json` baseline=1017（178 从 1065 下拧而来）。错误仍以 `no-untyped-def`
为主。178 证明了棘轮能往下走，本迭代继续选包清零，保持下行纪律。

### 改动（择 1–2 个高价值包）

- 优先选与 §B 同片区的 `app/services/gateway` 或 `app/services/live_trading`（改完顺手补类型），
  做 strict 清零：补 `-> ReturnType` 与参数标注，**只补类型不改逻辑**。
- 清完跑 `make mypy-ratchet-update` 把 baseline 从 1017 下调，commit 记录"下调 N，来自包 X"。
- 既有 per-package strict job 不动。

### 验收

- [ ] baseline 从 1017 **再次下降**（记录降幅与来源包）。
- [ ] `make mypy-ratchet` exit 0；人为 +1 错误能 fail（牙齿仍在）。
- [ ] 清零的包跑全部相关测试无回归。

---

## 6. §D — CI advisory 门禁 flip 决策（P2，部分可代码闭环）

| 门禁 | 当前 | 行号 | 179 处置 |
| --- | --- | --- | --- |
| PR-template i18n manifest | advisory | `ci.yml:658` | **本迭代尝试 flip blocking**：脚本稳定、误报低，最易收口 |
| i18n 全量 strict（CJK+English） | advisory | `ci.yml:950` | 暂不 flip：~14k over-reach 需 scanner 启发式（沿用 178 §F 理由），记录顺延 |
| e2e i18n（`\|\| true`） | advisory | `ci.yml:978` | 暂不 flip：需先清中文泄露 baseline，记录顺延 |
| monorepo-check | advisory | `ci.yml:1098/1116` | 团队策略项，**不在本迭代** flip，记录决策 |

### 验收

- [ ] 至少把 PR-template i18n 推进到可 flip（或给出明确不能 flip 的实测理由）。
- [ ] 其余 3 项在本文件留明确"为何暂不 flip + 解锁条件"的决策记录。

---

## 7. §E — 超大文件清单刷新（standing，不强拆）

**后端 service / api（>700 行，实测 2026-05-31）**：

| 文件 | 行数 | 备注 |
| --- | ---: | --- |
| `services/sync_service.py` | 2490 | 178 时 2483，**反增 7 行**；P2 候选，本迭代不拆 |
| `services/gateway/manual.py` | 2061 | §B slice 1/4 后记录下行；slice 3 顺延 |
| `services/live_trading/manager.py` | 819 | |
| `services/paper_trading_service.py` | 793 | |
| `services/monitoring_service.py` | 789 | urlopen 已 `to_thread`（178 同期/既有），无阻塞问题 |
| `services/strategy/version.py` | 785 | |
| `services/rag_service.py` | 785 | |
| `services/workspace_service.py` | 766 | backlog #6 已大幅瘦身，剩静态 helper |
| `services/ai_trading_service.py` | 754 | |
| `services/backtest/service.py` | 732 | |
| `api/live_trading/api.py` | 713 | 178 §B 改动同片区 |

**前端 `.vue`（>1000 行，实测，本迭代不触前端）**：

| 文件 | 行数 |
| --- | ---: |
| `views/KnowledgeBasePage.vue` | 1281 |
| `components/workspace/WorkspaceUnitsTab.vue` | 1271 |
| `views/GatewayStatusPage.vue` | 1256 |
| `components/workspace/WorkspaceOptimizationTab.vue` | 1193 |
| `views/QuotePage.vue` | 1185 |
| `components/workspace/WorkspaceReportTab.vue` | 1160 |

---

## 8. 执行顺序与提交规划

建议顺序（每项独立可验证、独立 commit，走 `dev`）：

1. **§A**（`chore(security): untrack .slowapi.env runtime artifact + gitignore`）— 最小、零风险，先做。
2. **§B**（`refactor(gateway): extract manual_utils + psutil-first port discovery (P1#4 slice 1/4)`）— 本迭代主块。
3. **§C**（`ci(types): strict-clean gateway pkg, ratchet baseline 1017->N`）— 与 §B 同片区，顺手。
4. **§D**（`ci(i18n): flip PR-template i18n gate to blocking; record advisory decisions`）。
5. 文档收口（`docs(iteration-179): CLOSURE + backlog evidence chain`）。

> 遵循 AGENTS.md：提交走 `dev`；CI 已在 `dev` 跑（177 修复），形成"改→CI 验证→再改"闭环。
> §A(G1) 的破坏性运维动作不在 agent 执行范围。

---

## 9. 总体验收标准（Definition of Done）

- [x] §A：`.slowapi.env` 已 untrack + gitignore；限流功能不回归（23 rate-limit 测试全绿）。
- [x] §B：`net_probe.py` 抽出（6 个纯 helper + 15 单测），`manual.py` 2061→2044；
      psutil-first utun 探测落地；gateway/实盘测试全绿（206）；P1#4 backlog slice 1/4 更新。
- [x] §C：mypy baseline 1017→**958**（-59，`app/api/workspace_api` strict 清零）并 `--update`；
      棘轮牙齿验证通过（+1 untyped def → fail）。
- [x] §D：PR-template i18n 门禁改 diff-aware 并 flip blocking；其余 3 项 advisory 决策记录见 §6/CLOSURE。
- [x] §E：超大文件清单刷新；`manual.py` 下行证据入档。
- [x] `ruff check src/backend` = 0；`ruff format --check` 全通过；后端相关测试全绿。
- [ ] 前端 `vue-tsc` 0、`vitest` 全绿。**本迭代未触前端**，沿用 178 终态。
- [x] G1（P0 历史凭据）backlog 补"179 复核工具仍就绪、仍待 owner 执行"证据链。
- [x] 本迭代目录补 `CLOSURE.md` 记录终态与证据。

---

## 10. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| §A untrack 后限流功能依赖该文件 | 改前确认加载器有缺失自建兜底；跑限流相关测试 |
| §B 改动触及实盘网关探测逻辑 | 只抽纯 helper + 等价替换探测实现，不动下单/连接生命周期；psutil 缺失保留 shell 兜底；跑全量 gateway/实盘测试 |
| §B psutil 在某些平台行为差异 | 保留 lsof/ifconfig/scutil 兜底链；探测失败走既有降级路径，不抛 |
| §C 强清 mypy 引入回归 | 只补类型标注、不改逻辑；改完跑该包全部测试 |
| §D flip i18n 门禁误伤 PR | 仅 flip 误报最低的 PR-template 项；其余保持 advisory 并记录解锁条件 |

---

## 附：本巡检使用的核查命令（可复现）

```bash
# G1 历史仍含凭据（178 已备工具，仍待 owner）
git log --oneline --all -- src/backend/data/manual_gateways.json
git ls-files src/backend/data/                      # 应仅 .gitkeep

# G2 .slowapi.env 被跟踪
git ls-files | grep -E "\.env$"
grep -n "slowapi" .gitignore                         # 应无命中（待补）

# G3 manual.py 阻塞 I/O + 体量
grep -n "subprocess.run\|lsof\|ifconfig\|scutil" src/backend/app/services/gateway/manual.py
wc -l src/backend/app/services/gateway/manual.py

# G4 mypy 基线
cat scripts/ci/mypy_app_baseline.json                # baseline_errors: 1017

# G5 advisory 门禁
grep -n "continue-on-error" .github/workflows/ci.yml # 658 / 950 / 1098 / 1116
grep -n "|| true" .github/workflows/ci.yml | grep -i i18n  # 978

# G6 大文件
find src/backend/app -name '*.py' -exec wc -l {} + | sort -rn | head

# G7 类型逃逸
grep -rn ": any" src/frontend/src --include="*.ts" --include="*.vue" | wc -l   # 18
grep -rn "type: ignore" src/backend/app --include="*.py" | wc -l               # 11

# 确认无新增高危（应全为 0 / 设计内）
grep -rn "verify=False\|shell=True" src/backend/app --include="*.py"           # 空
grep -rn -A1 "except Exception" src/backend/app --include="*.py" | grep -B1 "pass$" | grep -c except  # 0
```
