# 迭代 177 关闭报告 — 质量门禁修复与安全纵深

**关闭日期**: 2026-05-31
**起点**: 迭代 176 收口（commit `2c4db6cb`）
**终点**: 本迭代 §A–§D 全部收口
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
| §E mypy 仓库级棘轮 | stretch / 可选 | 未做（标注顺延） | ⏭️ |

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

## 6. 未完成 / 顺延项

- **§E mypy 仓库级棘轮**：PLAN 标注为 stretch，本迭代优先级让位于 §D 发现的安全事故，
  顺延至后续迭代。
- **F5 超大文件拆分**：standing 规则，按既有纪律滚动推进，本迭代不强拆。
- **P1#4 `manual_gateway_service` 阻塞 I/O 重构**：触及实盘下单，需独立分支 + 纸面验证。

---

## 7. 复现命令

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
```
