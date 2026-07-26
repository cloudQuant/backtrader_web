# 迭代 177 — 质量门禁修复与安全纵深

> **创建日期**: 2026-05-30
> **前置**: 迭代 176「工程债接续与基础设施收尾」已收口（commit `2c4db6cb`）
> **性质**: 质量加固 / 安全纵深 / CI 门禁修复（非新产品特性）
> **沟通语言**: 中文；文档技术名词保留英文

---

## 0. 一句话目标

修复"**CI 门禁在主开发分支上从不运行**"这一根因，把已经悄悄堆积的 lint/format 债清零，
并补齐 secret 扫描、依赖审计现代化等安全纵深短板，让"绿色 CI"重新等价于"代码健康"。

---

## 1. 背景与根因（基于本轮巡检的实测证据）

迭代 176 把 175 记录的工程债代码侧全部清零。但本轮巡检发现一个**结构性盲点**：
质量门禁配置与实际分支策略错位，导致门禁形同虚设，债务在"看起来一切正常"的情况下回流。

### 1.1 关键发现速览

| # | 类别 | 严重度 | 证据 | 现状 |
|---|------|:---:|------|------|
| F1 | CI 触发分支错位 | **P0** | `.github/workflows/*.yml` 均 `branches: [master, develop]`；`git branch -a` 显示实际只有 `dev` 与 `master`，**无 `develop`** | 主开发分支 `dev`（领先 origin 108+ commits）上 push/PR **从不触发** CI |
| F2 | Lint 债回流 | **P0** | `ruff check src/backend` = **110 errors**；`ruff format --check` = **166 文件待格式化** | 若 CI 在 `dev` 上运行，`backend-lint` 立即 FAIL |
| F3 | `safety check` 已弃用 | P1 | CI `backend-security` 用 `safety check --json` | Safety CLI 已弃用 `check` 子命令、改 `safety scan` 且常需账号鉴权，门禁可能静默失效 |
| F4 | 无 secret 扫描门禁 | P1 | `.pre-commit-config.yaml` / `.github/` 无 gitleaks/detect-secrets/trufflehog | 防御纵深缺口（配合 P0#3 开发机真实密钥风险） |
| F5 | 超大文件回流 | P2 | 见 §5 实测清单 | 6 个 `.vue` >1000 行；`sync_service.py` 2483 行等 |
| F6 | mypy 仓库级未设棘轮 | P2 | `pyproject.toml [tool.mypy]` 仅 strict 子集 override | 已清包之外的新 type 错误不会 fail CI |

### 1.2 为什么 F1 是根因

176 的提交说明里反复出现"vitest 阈值已升至 75""ruff 0""mypy 0"等验证语句——这些都是
**本地手工验证**。但因为 CI 不在 `dev` 跑，这些验证没有被自动化门禁固化。一旦某次提交
本地漏跑，债务就回流且无人察觉。F2 的 110 个 lint 错误正是这样累积的：

```
$ ruff check src/backend --statistics
35  F401  unused-import          # 未使用 import
35  T201  print                  # 全部在 scripts/ 与 tests/（可加 per-file ignore）
29  I001  unsorted-imports        # import 排序
 8  F541  f-string-missing-placeholders
 1  B904  raise-without-from-inside-except
 1  E402  module-import-not-at-top-of-file
 1  UP035 deprecated-import
```

其中**生产代码 `app/` 仅 20 个**（14 F401 + 4 I001 + 1 E402 + 1 UP035），且 16 个集中在
`workspace_service.py`——是 176 §6 切片时把 `from app.services.workspace.config import (...)`
插到了模块级常量之后，触发 E402 + import 乱序的连带错误。其余 90 个在 `scripts/` 和 `tests/`，
多为 `print()`（脚本里合理）与未使用 import。

> **结论**：F2 不是"代码烂"，而是"门禁没拦住小疏漏"。修好 F1 后，F2 这类债将无法回流。

---

## 2. 范围与非范围

**本迭代做（代码/配置侧可闭环）**：
- §A CI 触发分支修复（F1）
- §B Lint/format 债清零 + per-file ignore 规整（F2）
- §C 依赖审计现代化：`safety` → `pip-audit`，前端 `npm audit` 策略复核（F3）
- §D secret 扫描门禁接入 pre-commit + CI（F4）
- §E mypy 仓库级棘轮（F6，可选 stretch）

**本迭代不做（标注清楚，避免假装完成）**：
- ⏭️ 超大文件拆分（F5）：作为**长尾 standing 规则**滚动推进，本迭代只更新清单与
  优先级，不强行一把梭（与 176 §G 的纪律一致）。
- ⏭️ P0#3 开发机真实密钥轮换：运维动作，非代码（176 已在 `CONTRIBUTING.md` 加清理清单）。
- ⏭️ §H 监控 blocker 切换、E2E 全套升 PR-blocking：需团队策略决议。
- ⏭️ `manual_gateway_service` 阻塞 I/O 重构（P1#4）：触及实盘下单，需独立分支 + 纸面交易验证。

---

## 3. §A — CI 触发分支修复（P0，最高优先）

### 问题
`ci.yml` / `e2e.yml` / `deploy-preview.yml` 触发条件为 `branches: [master, develop]`，
但仓库实际分支是 `dev` 和 `master`，`develop` 不存在。结果：

- push 到 `dev` → 无任何 CI
- PR `dev → master` → 触发（因为 `pull_request.branches` 指 base 分支 master）✅

也就是说，唯一会跑 CI 的时机是合并回 master 的 PR，日常 `dev` 提交完全裸奔。

### 决策点（需确认其一）
1. **方案 A（推荐，零迁移成本）**：把所有 workflow 的 `develop` 改为 `dev`，即
   `branches: [master, dev]`。语义最贴合现状。
2. **方案 B（规范化）**：把分支 `dev` 重命名为 `develop` 并改 `origin/HEAD`。迁移成本高、
   影响所有协作者本地 checkout，不推荐在本迭代做。

> 默认按**方案 A** 推进。若团队希望统一到 git-flow 的 `develop` 命名，另开运维任务。

### 改动清单
- `.github/workflows/ci.yml`：`push.branches` 与 `pull_request.branches` → `[master, dev]`
- `.github/workflows/e2e.yml`：同上
- `.github/workflows/deploy-preview.yml`：`pull_request.branches` → `[master, dev]`
- 复核 `docs.yml` / `docker-publish.yml` / `pr-check.yml` / `nightly.yml` 触发条件是否也需对齐

### 验收
- 在 `dev` 上推一个空 commit 或 `workflow_dispatch`，确认 `CI - Quality Checks` 被触发并跑完。
- 修复 §B 之前，预期 `backend-lint` 会红——这正是 §B 要解决的，证明门禁恢复了拦截力。

---

## 4. §B — Lint / Format 债清零（P0）

### 4.1 生产代码（`app/`，20 errors）必须手工修

重点是 `workspace_service.py` 的 E402 + import 乱序（176 切片遗留）：

- 将第 54-71 行的 `from app.services.workspace.config import (...)` 与
  `from app.services.workspace.run_ops import WorkspaceRunOpsMixin` 上提到文件顶部
  import 区，删除模块级常量插队造成的 `# noqa: E402`。
- `app/models/__init__.py:7`、`app/utils/tracing.py:45`、`manual_gateway_service.py:1`、
  `live_trading_manager.py:1` 的 F401/I001 逐一修（多为 re-export，必要时用 `__all__`
  显式声明而非保留裸 import）。
- `UP035`（deprecated-import，如 `typing.List` → `list`）按 ruff `--fix` 自动处理后人工复核。

### 4.2 scripts/ 与 tests/（90 errors）规整策略

- **`T201`（print，全部在 `scripts/migrate_*.py`、`seed_*.py`、`tests/test_performance_baseline.py`）**：
  脚本里 print 合理。在 `pyproject.toml [tool.ruff.lint.per-file-ignores]` 增加：
  ```toml
  [tool.ruff.lint.per-file-ignores]
  "scripts/**" = ["T201"]
  "tests/**/test_performance_baseline.py" = ["T201"]
  ```
- **F401 / I001 / F541**：tests 与脚本里的也一并 `ruff check --fix`，剩余人工确认。

### 4.3 Format（166 文件）

- 跑 `ruff format src/backend` 统一格式。**注意**：这会触及大量测试文件，diff 很大，
  建议**单独一个 commit**（`style(backend): ruff format sweep`），与逻辑改动分离，便于 review。

### 验收
- `ruff check src/backend` → `0 errors`
- `ruff format --check src/backend` → `All files already formatted`
- `pytest -q`（后端全绿，确认 format/import 调整无行为变化）
- 提交分两笔：①逻辑性 import 修复（`fix(lint)`）②纯格式化（`style`）

---

## 5. §C — 依赖审计现代化（P1）

### 问题
- CI `backend-security` 用 `safety check --json --output ...` 与 `safety check`。Safety 2.x+
  已弃用 `check`、推 `safety scan`，且新版常要求注册/登录 token，CI 里易静默降级或失败。
- 前端 `frontend-lint` 已有 `npm audit --audit-level=high`（良好），但无 lockfile 漏洞的
  定期复核记录。

### 改动
1. 后端：用 **`pip-audit`**（PyPA 出品、基于 OSV、无需账号）替换或并行于 `safety`：
   ```yaml
   - name: Audit Python dependencies (pip-audit)
     run: pip-audit --strict --desc || true   # 先 advisory 跑一轮拿基线
   ```
   先 advisory 一个迭代拿到基线，下迭代再 flip 成 blocking。
2. 把 `pip-audit` 加入 `pyproject.toml` 的 `dev` extra。
3. 前端：确认 `npm audit` 在 `dev` CI 恢复后真实运行；记录当前 high/critical 基线。

### 验收
- CI 输出 `pip-audit` 报告（advisory 不阻塞）。
- 在 `docs/explanation/` 或本迭代目录记录依赖漏洞基线快照。

---

## 6. §D — Secret 扫描门禁（P1，防御纵深）

### 问题
`.env` 已正确 gitignore 且从未被 track（`git ls-files` 无 `.env`），`config.py` 的
`validate_runtime_security_guards` 也会在生产拒绝默认 `SECRET_KEY`/`JWT_SECRET_KEY` 和弱
`ADMIN_PASSWORD`（良好）。但**没有任何自动化机制阻止未来误提交密钥**——考虑到 P0#3
记录开发机上存在 OKX/Binance/HTX/CTP 等真实 key，这是值得补的纵深。

### 改动
1. `.pre-commit-config.yaml` 增加 **gitleaks** 或 **detect-secrets** hook：
   ```yaml
   - repo: https://github.com/gitleaks/gitleaks
     rev: v8.x.x
     hooks:
       - id: gitleaks
   ```
2. CI 增加一个独立 `secret-scan` job（对全历史或 PR diff 扫描），先 advisory 一轮。
3. 若用 detect-secrets，生成 `.secrets.baseline` 并纳入版本控制。

### 验收
- pre-commit `gitleaks` 本地可拦截构造的假 key。
- CI `secret-scan` job 跑通并产出报告。

---

## 7. §E — mypy 仓库级棘轮（P2，stretch）

### 现状
`pyproject.toml` 已对 `app.utils` / `app.schemas` / `app.services.quote` 及 9 个 services
子包开 strict override，CI 有 4 个 mypy ratchet job。但**已清包之外**新增 type 错误不会
fail CI（P2#12）。

### 改动（若本迭代有余量）
- 增加一个 `mypy app`（非 strict、基线对比）的棘轮脚本：记录当前 error 数为 baseline，
  CI 在新增错误时 fail。可复用 i18n/bundle 已有的 baseline-json 模式。

### 验收
- `scripts/ci/mypy_ratchet.py` + baseline，advisory 跑一轮。

---

## 8. §F — 超大文件清单（standing，本迭代仅更新优先级，不强拆）

> 与 176 §G 纪律一致：任何 >500 行的新 `.vue`/service 应按既有 recipe 拆分，但不在本迭代
> 一把梭。下表为实测当前 top 清单，供后续迭代择机消化。

**前端 `.vue`（>1000 行，6 个）**：

| 文件 | 行数 | 备注 |
|------|---:|------|
| `views/KnowledgeBasePage.vue` | 1281 | 176 已做 a11y，未拆 |
| `components/workspace/WorkspaceUnitsTab.vue` | 1271 | 与 `TradingWorkspaceUnitsTab` 区分 |
| `views/GatewayStatusPage.vue` | 1256 | |
| `components/workspace/WorkspaceOptimizationTab.vue` | 1193 | |
| `views/QuotePage.vue` | 1185 | |
| `components/workspace/WorkspaceReportTab.vue` | 1160 | |

**后端 service（>700 行）**：

| 文件 | 行数 | 备注 |
|------|---:|------|
| `services/sync_service.py` | 2483 | 176 P1#5 已切 3 片，仍最大 |
| `services/gateway/manual.py` | 2046 | P1#4 阻塞 I/O，需独立分支 |
| `services/live_trading/manager.py` | 817 | |
| `services/paper_trading_service.py` | 793 | |
| `services/monitoring_service.py` | 789 | |
| `services/strategy/version.py` | 785 | |

---

## 9. 执行顺序与提交规划

建议顺序（每项独立可验证、独立 commit）：

1. **§A**（`ci(workflows): fix branch triggers dev≠develop`）— 最高优先，恢复门禁。
2. **§B-1 生产代码 import 修复**（`fix(lint): resolve E402/F401 in app/ services`）。
3. **§B-2 per-file ignore + tests/scripts 修复**（`chore(lint): per-file T201 ignores, clean unused imports`）。
4. **§B-3 format sweep**（`style(backend): ruff format`）— 单独一笔，diff 大但纯格式。
5. **§C**（`ci(security): adopt pip-audit, advisory baseline`）。
6. **§D**（`ci(security): add gitleaks secret scan`）。
7. **§E**（可选，`ci(types): mypy repo-wide ratchet baseline`）。

> 遵循 AGENTS.md：分支策略上，本迭代的提交仍走 `dev`；§A 合入后即可在 `dev` 看到 CI 反馈，
> 形成"改 → CI 验证 → 再改"的正反馈闭环。

---

## 10. 总体验收标准（Definition of Done）

- [ ] §A：`dev` 分支 push/PR 触发完整 `CI - Quality Checks`，可在 Actions 页观察到运行。
- [ ] §B：`ruff check src/backend` = 0；`ruff format --check` = 全通过；`pytest` 后端全绿。
- [ ] §C：CI 含 `pip-audit` job 并产出 advisory 报告；依赖漏洞基线已记录。
- [ ] §D：pre-commit + CI secret 扫描可拦截构造密钥；baseline（若用 detect-secrets）入库。
- [ ] §E（可选）：mypy 仓库级棘轮 advisory 跑通。
- [ ] 前端 `vue-tsc` 0、`vitest`（当前 ~987 用例）全绿无回归。
- [ ] 完成项从 `REFACTORING_BACKLOG.md` 对应条目删除（不留绿勾，沿用项目纪律）。
- [ ] 本迭代目录补 `CLOSURE.md` 记录终态与证据。

---

## 11. 风险与缓解

| 风险 | 缓解 |
|------|------|
| §B format sweep diff 巨大，淹没 review | 单独 commit；逻辑改动与格式化严格分离 |
| §A 改触发后 CI 立刻红（因 §B 未完成） | 接受短暂红；§A 与 §B 同一迭代连续推进，先红后绿证明门禁有效 |
| `pip-audit`/`gitleaks` 首轮可能爆大量历史告警 | 先 advisory（不阻塞，`\|\| true`）拿基线，下迭代再 flip blocking |
| 现有真实密钥若曾进过历史 commit | §D gitleaks 全历史扫描可发现；发现即触发 P0#3 轮换（运维） |

---

## 附：本巡检使用的核查命令（可复现）

```bash
# F1 分支触发
grep -rn "branches:" .github/workflows/*.yml
git branch -a

# F2 lint/format
ruff check src/backend --statistics
ruff check src/backend/app
ruff format --check src/backend

# F3 安全工具
grep -rn "safety\|bandit\|pip-audit\|npm audit" .github/workflows/

# F4 secret 扫描 / .env 状态
git ls-files | grep -E '(^|/)\.env$'      # 应为空
git check-ignore .env src/backend/.env     # 应被忽略

# F5 大文件
find src/frontend/src -name '*.vue' -exec wc -l {} + | sort -rn | head
find src/backend/app -name '*.py' -exec wc -l {} + | sort -rn | head
```
