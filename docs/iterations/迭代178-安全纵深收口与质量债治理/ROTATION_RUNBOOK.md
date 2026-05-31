# 凭据轮换与 git 历史清除 Runbook（迭代 178 §A，P0 安全）

> **状态**: ⛔ 待仓库 owner 执行（破坏性 / 触及真实账户 / 影响所有协作者）
> **代码侧已就绪（178 §A 交付）**: 清除脚本 `scripts/ops/purge_secret_history.sh`、
> 本 Runbook、CI 门控 flip（`SECRET_SCAN_HISTORY_BLOCKING`）。
> **本 Runbook 不可由 agent 自动执行**——轮换需登录各 provider，历史重写需 force-push。

---

## 0. 为什么必须做

迭代 177 §D 用 `git rm --cached` 把含真实凭据的运行时文件移出了最新提交，并加了
`.gitignore` + gitleaks 门禁防止新泄露。但**历史快照仍含明文**：

```bash
git show <旧commit>:src/backend/data/manual_gateways.json   # 仍打印真实 key
```

177 全史 gitleaks 扫描报 ~114 个发现，主体就是下列真实凭据。任何拿到过 clone 的人
都已掌握这些 key。因此：**轮换（让旧 key 失效）是第一要务，历史清除是第二步。**

---

## 1. 暴露凭据清单与轮换步骤

> 逐项轮换并打勾。轮换 = 在 provider 侧**作废旧密钥并生成新密钥**，再把新值写入
> **未入库的** `.env` / 运行时配置（绝不能再提交进 git）。

### 1.1 交易所 API 密钥

- [ ] **Binance** — API key + secret
  - 入口：Binance → API Management → 删除泄露的 key → 新建（建议绑定 IP 白名单、最小权限）
  - 落地：写入开发机 `.env` 的 `BINANCE_API_KEY` / `BINANCE_SECRET_KEY`
  - 验证：用新 key 调一次只读接口（账户余额）确认生效、旧 key 调用返回 401
- [ ] **OKX** — api_key + secret + passphrase
  - 入口：OKX → API → 删除旧 key → 新建（passphrase 一并更换）
  - 落地：`OKX_API_KEY` / `OKX_SECRET_KEY` / `OKX_PASSPHRASE`
  - 验证：新 key 只读调用成功；旧 key 失效
- [ ] **HTX（火币）** — 若曾配置则一并轮换 api_key + secret

### 1.2 期货 / 外汇 / 券商账户口令

- [ ] **CTP（simnow 账号 089763）** — 交易口令
  - 入口：SimNow 用户中心修改密码（或生产 CTP 经纪商渠道）
  - 落地：对应网关配置 / `.env`
- [ ] **MT5（账号 5047785364）** — 登录口令
  - 入口：MT5 终端 / 经纪商后台修改密码
- [ ] **IB（账号 quantyunjinqi999999 / dup* 派生）** — 登录口令
  - 入口：IBKR 账户管理 → 修改密码；若用 access token 一并重置

### 1.3 数据库口令

- [ ] **本地 MySQL root（`127.0.0.1`）** — 重置 root 口令
  - `ALTER USER 'root'@'localhost' IDENTIFIED BY '<新强口令>';`
  - 更新本地同步配置（运行时生成，不入库）
- [ ] **远程 MySQL root（`43.167.221.188`）** — 重置 root 口令
  - 登录该主机 `ALTER USER ...`；同时检查是否应**禁用 root 远程登录**、改用最小权限账户
  - 更新同步任务配置

> 轮换全部完成后，旧凭据即便仍在某人 clone 的历史里也已失效——这是把风险从"P0 活跃"
> 降到"P3 历史痕迹"的关键一步。

---

## 2. git 历史清除（轮换完成后）

### 2.1 前置确认

- [ ] §1 全部凭据已轮换并验证旧值失效
- [ ] 已与所有协作者约定 re-clone 窗口（force-push 会让旧 clone 冲突）
- [ ] 已安装 `git-filter-repo`（`pipx install git-filter-repo` 或 `brew install git-filter-repo`）
- [ ] 已对仓库做一次完整备份（裸 clone：`git clone --mirror <url> backup.git`）

### 2.2 先 dry-run 核对范围

```bash
scripts/ops/purge_secret_history.sh --dry-run
```

应列出 7 类路径（`manual_gateways.json` / `manual_gateways/` / `sync_config.json` /
`sync_history.json` / `auto_trading_config.json` / `live_trading_instances.json` /
`quote_custom_symbols.json`）。

### 2.3 执行清除

```bash
scripts/ops/purge_secret_history.sh --execute
```

脚本会要求依次输入 `rotated` → `coordinated` → `PURGE` 三道确认，任一不符即中止。

### 2.4 清除后验证

```bash
git log --all --oneline -- src/backend/data/manual_gateways.json   # 期望：空
gitleaks detect --config .gitleaks.toml --no-banner --redact        # 期望：0 findings
```

### 2.5 force-push 与协作者通知

```bash
git remote add origin <remote-url>      # filter-repo 会移除 origin，需重加
git push origin --force --all
git push origin --force --tags
```

- [ ] 通知所有协作者：删除本地 clone 重新 `git clone`，或
  `git fetch origin && git reset --hard origin/dev`
- [ ] 提醒：任何人若用旧 clone push，会把历史秘密带回来——务必全员 re-clone

---

## 3. CI 门禁：full-history 扫描 flip 为 blocking

历史确认干净后，把 `secret-scan` 的全史步骤从 advisory 翻成 blocking：

- 设置仓库/组织变量 **`SECRET_SCAN_HISTORY_BLOCKING=true`**（GitHub → Settings →
  Secrets and variables → Actions → Variables）。
- 该变量为 `true` 时，CI 的"Scan full history for secrets"步骤不再吞错误（去掉
  `|| echo ::warning`），任何历史泄露直接 fail。
- 实现见 `.github/workflows/ci.yml` 的 `secret-scan` job（178 §A 已加门控逻辑）。
- [ ] flip 后在一次 PR 上确认 `secret-scan` 全史步骤为绿（blocking 通过）

---

## 4. 完成判定（Definition of Done，owner 维护）

- [ ] §1 全部凭据轮换完成且旧值验证失效
- [ ] §2 历史清除完成、`git log`/`gitleaks` 验证干净、force-push 完成
- [ ] §2.5 全体协作者已 re-clone
- [ ] §3 `SECRET_SCAN_HISTORY_BLOCKING=true` 已设、CI 全史 blocking 通过
- [ ] 在 `REFACTORING_BACKLOG.md` 删除 P0#3 条目（按项目纪律，完成即删不留绿勾）
