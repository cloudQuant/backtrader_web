# 凭据轮换、fingerprint 基线与可选历史清除 Runbook（迭代 178 §A，P0 安全）

> **状态**: 🟡 owner 已确认所有历史凭据均已作废且全史复扫为 0；等待发布后的 blocking CI 证据。
> **代码侧已就绪**: 103 条已审计 finding 的 `.gitleaksignore` 精确基线、可选清除脚本
> `scripts/ops/purge_secret_history.sh`、本 Runbook 和 CI 门控 flip。
> **Owner 决策（2026-07-18）**: IBKR 仅用于模拟交易并接受历史暴露；不要求改写 git 历史。

---

## 0. 为什么必须做

迭代 177 §D 用 `git rm --cached` 把含真实凭据的运行时文件移出了最新提交，并加了
`.gitignore` + gitleaks 门禁防止新泄露。但**历史快照仍含明文**：

```bash
git show <旧commit>:src/backend/data/manual_gateways.json   # 仍打印真实 key
```

使用 CI 固定的 gitleaks 8.30.1 复扫得到 114 个发现：103 条为测试/公开值/误报，已按
commit+path+rule+line 的精确 fingerprint 建立基线；剩余 11 条来自旧 Binance、OKX、
手工网关和 MySQL 同步配置。IBKR cookie 未触发 finding。

因此：**有效凭据失效或轮换是安全边界；历史改写不是必需条件。** 精确 fingerprint
只忽略已审计旧 finding，未来在相同路径新增的 secret 仍会被 CI 阻断。

---

## 1. 暴露凭据清单与轮换步骤

> 逐项轮换并打勾。轮换 = 在 provider 侧**作废旧密钥并生成新密钥**，再把新值写入
> **未入库的** `.env` / 运行时配置（绝不能再提交进 git）。

### 1.1 交易所 API 密钥

- [x] **Binance** — API key + secret（owner 确认旧值已作废）
  - 入口：Binance → API Management → 删除泄露的 key → 新建（建议绑定 IP 白名单、最小权限）
  - 落地：写入开发机 `.env` 的 `BINANCE_API_KEY` / `BINANCE_SECRET_KEY`
  - 验证：用新 key 调一次只读接口（账户余额）确认生效、旧 key 调用返回 401
- [x] **OKX** — api_key + secret + passphrase（owner 确认旧值已作废）
  - 入口：OKX → API → 删除旧 key → 新建（passphrase 一并更换）
  - 落地：`OKX_API_KEY` / `OKX_SECRET_KEY` / `OKX_PASSPHRASE`
  - 验证：新 key 只读调用成功；旧 key 失效
- [x] **HTX（火币）** — owner 确认全部历史凭据已作废

### 1.2 期货 / 外汇 / 券商账户口令

- [x] **CTP（如已配置）** — 交易口令（owner 确认旧值已作废）
  - 入口：SimNow 用户中心修改密码（或生产 CTP 经纪商渠道）
  - 落地：对应网关配置 / `.env`
- [x] **MT5（如已配置）** — 登录口令（owner 确认旧值已作废）
  - 入口：MT5 终端 / 经纪商后台修改密码
- [x] **IBKR（模拟交易）** — owner 接受历史暴露风险；无需轮换或历史改写
  - 当前树仍须保持 cookie 文件 untracked，仅提交占位符 example

### 1.3 数据库口令

- [x] **本地 MySQL root** — owner 确认历史口令已作废
  - `ALTER USER 'root'@'localhost' IDENTIFIED BY '<新强口令>';`
  - 更新本地同步配置（运行时生成，不入库）
- [x] **远程 MySQL root** — owner 确认历史口令已作废
  - 登录该主机 `ALTER USER ...`；同时检查是否应**禁用 root 远程登录**、改用最小权限账户
  - 更新同步任务配置

> 轮换全部完成后，旧凭据即便仍在某人 clone 的历史里也已失效——这是把风险从"P0 活跃"
> 降到"P3 历史痕迹"的关键一步。

---

## 2. 推荐方案：保留历史，以精确 fingerprint 收口

1. 复核 `docs/security/gitleaks-history-baseline.md` 中的 103 条已分类 finding。
2. 按 `docs/security/credential-rotation-inventory.md` 轮换全部可能实盘凭据，并记录旧值失效证据。
3. 仅把完成风险判定的 finding 的 `Fingerprint` 加入 `.gitleaksignore`。
4. 运行脱敏全史扫描，必须得到 0 个未解决 finding。
5. 设置 `SECRET_SCAN_HISTORY_BLOCKING=true`，保留一次 blocking CI 通过记录。

此方案不改变 commit SHA、不需要 force-push，也不要求协作者重新 clone。

---

## 3. 可选方案：git 历史清除

只有 owner 明确要求彻底删除旧 blob 时才使用本节。它不是迭代 183 的验收前提。

### 3.1 前置确认

- [ ] §1 全部凭据已轮换并验证旧值失效
- [ ] 已与所有协作者约定 re-clone 窗口（force-push 会让旧 clone 冲突）
- [ ] 已安装 `git-filter-repo`（`pipx install git-filter-repo` 或 `brew install git-filter-repo`）
- [ ] 已对仓库做一次完整备份（裸 clone：`git clone --mirror <url> backup.git`）

### 3.2 先 dry-run 核对范围

```bash
scripts/ops/purge_secret_history.sh --dry-run
```

应列出 8 类路径（`ibkr_cookies.json` / `manual_gateways.json` / `manual_gateways/` /
`sync_config.json` / `sync_history.json` / `auto_trading_config.json` /
`live_trading_instances.json` / `quote_custom_symbols.json`）。

### 3.3 执行清除

```bash
scripts/ops/purge_secret_history.sh --execute
```

脚本会要求依次输入 `rotated` → `coordinated` → `PURGE` 三道确认，任一不符即中止。

### 3.4 清除后验证

```bash
git log --all --oneline -- src/bt_api_py/configs/ibkr_cookies.json # 期望：空
git log --all --oneline -- src/backend/data/manual_gateways.json   # 期望：空
gitleaks detect --config .gitleaks.toml --no-banner --redact        # 期望：0 findings
```

### 3.5 force-push 与协作者通知

```bash
git remote add origin <remote-url>      # filter-repo 会移除 origin，需重加
git push origin --force --all
git push origin --force --tags
```

- [ ] 通知所有协作者：删除本地 clone 重新 `git clone`，或
  `git fetch origin && git reset --hard origin/dev`
- [ ] 提醒：任何人若用旧 clone push，会把历史秘密带回来——务必全员 re-clone

---

## 4. CI 门禁：full-history 扫描 flip 为 blocking

114 条 finding 完成判定且脱敏全史扫描为 0 后，把 `secret-scan` 置为 blocking：

- 已提交的 `gitleaks_history_baseline.json` 为 `blocking_ready=true`，CI 会自动硬阻断
  任何未基线 finding。
- 仓库/组织变量 **`SECRET_SCAN_HISTORY_BLOCKING=true`** 仅作为可选 emergency override，
  可在 baseline 尚未 ready 时提前强制阻断。
- [ ] 在一次发布后的 PR/branch CI 上确认 `secret-scan` 全史步骤为绿（blocking 通过）

---

## 5. 完成判定（Definition of Done，owner 维护）

- [x] IBKR 模拟交易历史暴露已由 owner 接受，不要求历史改写
- [x] owner 确认 `credential-rotation-inventory.md` 中所有历史凭据均已作废
- [x] 所有已接受 finding 仅按精确 fingerprint 入基线，全史扫描为 0
- [ ] §4 变更发布后 CI 全史 blocking 通过（metadata 自动启用；仓库变量为可选 override）
- [ ] 在 `REFACTORING_BACKLOG.md` 删除 P0#3 条目（按项目纪律，完成即删不留绿勾）
