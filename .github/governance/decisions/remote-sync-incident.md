# Incident: GitHub ↔ Gitee `master` 镜像漂移（iteration 195 D1）

> 登记日期：2026-08-23
> 类型：镜像一致性（低危，不影响 GitHub 权威流程）
> 状态：Open

## 事实（2026-08-23 只读快照）

| 远端 | ref | SHA |
|---|---|---|
| GitHub `cloudQuant/backtrader_web` | `master` | `605d4d0e1cf1ad6627483aab6c4cef2a742b3d0f` |
| Gitee `yunjinqi/backtrader_web` | `master` | `3d05130635f50c45adeaa4514af246380ff00451` |
| GitHub / Gitee | `dev` | `ebec2a0adf0f239784edbe4d2f3221ac581bd65e`（两端一致） |

发现方式：计划编制基线采集（`git ls-remote --heads`），见 `evidence/preflight.md` §2。

## 权威端

GitHub 为唯一权威（D1 决策）。Gitee 仅作只读镜像；差异**不得**由 CI、脚本或执行者自动 force-push、覆盖或修复。

## 处置方案（人工）

1. 管理员分别核对两端 `master` 各自领先/独有的提交（`git log --left-right --cherry-pick --oneline GitHub/master...Gitee/master`），确认需保留的历史。
2. 由有权限的人工执行一次明确方向的同步（fast-forward 或显式合并），操作前后各留存一份 `ls-remote` 记录到本目录。
3. 同步完成后在本文件回填结果并将状态改为 Resolved。

## 责任人与时间线

- 责任人：`@cloudQuant`（仓库管理员）
- 通知渠道：本 incident 文件 + 迭代看板条目（唯一治理工作流标识 `iteration-195-pr-governance`）
- 复核日期：**2026-09-30**（逾期未解决则升级为阻塞项重新评审 D1）
