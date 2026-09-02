# Iteration 195 — Preflight Baseline Evidence

> 采集日期：2026-08-23（Asia/Shanghai）
> 执行者角色：治理实施代理（以仓库所有者 `cloudQuant` 的本地凭据执行只读命令）
> 命令来源：`docs/iterations/迭代195-社区PR治理与双分支协作/正式迭代计划.md` §1.1
> 纪律：本文件只记录时间、命令、摘要、HTTP 状态与 SHA；原始 API 响应、token 与私密内容不入库。

## 1. 只读快照结果

采集时间：2026-08-23（本地会话，UTC+8）

| # | 命令 | HTTP/退出状态 | 摘要 |
|---|---|---|---|
| 1 | `gh repo view cloudQuant/backtrader_web --json defaultBranchRef,visibility` | 0 (200) | 默认分支 `master`；可见性 `PUBLIC` |
| 2 | `gh api repos/cloudQuant/backtrader_web/rulesets --paginate` | 0 (200) | 返回空数组 `[]`：当前无任何 Ruleset |
| 3 | `gh api repos/cloudQuant/backtrader_web/branches/master/protection` | 404 | `"Branch not protected"` — 传统 Branch Protection 未启用（有效基线证据） |
| 4 | `gh api repos/cloudQuant/backtrader_web/branches/dev/protection` | 404 | 同上，`dev` 亦未保护 |
| 5 | `gh api repos/cloudQuant/backtrader_web/codeowners/errors` | 0 (200) | `{"errors":[]}` — CODEOWNERS 无解析错误 |
| 6 | `gh label list --repo cloudQuant/backtrader_web --limit 100` | 0 (200) | `bug, documentation, duplicate, enhancement, good first issue, help wanted, invalid, merge-ready, question, wontfix`。注意：历史遗留 label `merge-ready` 已存在 |
| 7 | `git ls-remote --heads https://github.com/cloudQuant/backtrader_web.git master dev` | 0 | GitHub: `master=605d4d0e…`, `dev=ebec2a0a…` |
| 8 | `git ls-remote --heads https://gitee.com/yunjinqi/backtrader_web.git master dev` | 0 | Gitee: `master=3d051306…`, `dev=ebec2a0a…` |

## 2. 四个远端 ref SHA 登记

| 远端 | 分支 | SHA（短） | 说明 |
|---|---|---|---|
| GitHub (`cloudQuant/backtrader_web`) | master | `605d4d0e` | 权威端（D1 推荐） |
| GitHub (`cloudQuant/backtrader_web`) | dev | `ebec2a0a` | 日常集成 |
| Gitee (`yunjinqi/backtrader_web`) | master | `3d051306` | **与 GitHub master 不同 SHA → 镜像漂移**，登记于 `.github/governance/decisions/remote-sync-incident.md` |
| Gitee (`yunjinqi/backtrader_web`) | dev | `ebec2a0a` | 与 GitHub dev 一致 |

结论：`dev` 双远端一致；`master` 双远端已漂移。监控只报告差异，不自动同步或覆盖任一远端。

## 3. 关键事实对计划的影响复核

1. 默认分支为 `master`：新 fork / 新 PR 的默认 base 偏向 `master`。按 D0 推荐保留 `master` 为默认分支，由 PR Governance 门禁阻断普通 PR 目标为 `master`；安全治理 workflow 须先经 `release/governance-bootstrap` PR 提升到 `master` 后才会在 fork 的 `pull_request_target` 中生效。
2. `master`/`dev` 均无 Branch Protection 且 Ruleset 列表为空：文档承诺在 Ruleset 应用前不具备服务器端强制力。
3. CODEOWNERS 存在且无 errors，仅保护 iteration 193 ratchet 基线文件；新增领域 owner 时必须保留既有条目。owner 使用真实用户 `@cloudQuant`（GitHub 用户类型为 `User`，已验证存在）。
4. `pr-check.yml` 同时监听 `pull_request` + `pull_request_target`，顶层权限含 `pull-requests: write`，并执行 checkout/install 与自动贴 `merge-ready` 标签——P0 特权执行风险，Task 2 处理。
5. `deploy-preview.yml` 构建前端 artifact 却评论虚构 URL `https://pr-N.backtrader-web.preview.dev`——Task 5 改为如实命名。
6. `docker-publish.yml` 接受任意 `v*` tag 和手动输入 tag，未验证 tag 指向 `master` HEAD——Task 5 收紧。
7. 仓库布局：交易适配目录为 `src/bt_api_py/`；根 `dags/` 与 `tests/unit/scripts/` 不存在，本迭代不创建虚假路径规则。

## 4. 决策门状态摘要

详细决策记录见 `.github/governance/decisions/iteration-195.md`：

| 门 | 状态（2026-08-23） |
|---|---|
| D0 默认分支与双分支语义 | 通过（保留 `master` 为默认） |
| D1 远端权威与漂移处置 | 通过（GitHub 权威 / Gitee 只读镜像）+ incident 登记 |
| D2 真实 owner 与审批池 | 通过（主 owner `@cloudQuant` 已验证；备用 owner 待补，有到期日） |
| D3 Ruleset 能力与 bypass | 有到期日的例外（沙盒验证待做；manifest 先行，外部应用延后） |
| D4 required-check 合同 | 阻塞（依赖 Task 4 三类草稿 PR 演练取得确切 context 名） |
| D5 preview 产品边界 | 通过（仅 Preview Build Artifact，不宣称部署） |
| D6 release tag 与镜像权限 | 有到期日的例外（受保护 environment 待管理员配置；工作流先落 provenance 校验） |
| D7 安全披露通道 | 阻塞（未确认受监控通道前不发布 SECURITY.md） |

## 5. 后续证据索引

- 演练矩阵：`evidence/dry-run-matrix.md`
- Ruleset 读回：`evidence/ruleset-readback.md`
- 度量口径：`evidence/weekly-metrics-schema.md`
- 回滚手册：`evidence/rollback-runbook.md`
