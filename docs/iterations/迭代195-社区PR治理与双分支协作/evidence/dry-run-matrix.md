# D4 PR Governance 演练矩阵（模板）

状态：**尚未执行；D4 仍为 blocked。** 本文件只定义真实草稿 PR 演练所需的记录字段，不能
作为 PR URL、commit SHA、Check Run context 或远端 Ruleset 已启用的证据。

`PR Governance` 只运行受信任的 `pull_request_target` 事件：`opened`、`synchronize`、
`reopened`、`edited`、`ready_for_review`、`labeled`、`unlabeled`。它不会订阅
`pull_request_review`；该事件的 workflow 文件可来自 PR merge ref，不能作为受信任 Gate。
review submitted、edited 或 dismissed 后，由维护者重新运行已有的受信任 `Governance Gate`。
若将来需要自动重跑，必须先单独评审 GitHub App/webhook relay 的 actor、权限与实际 Check
Run 证据；该 relay 未获批前不得作为 D4 通过依据。

| 场景 | 来源 → 目标 | 预期路径风险/结果 | 草稿 PR URL | base/head SHA | 实际 display name / context | 事件与重跑观察 | review 与可读诊断 | 记录人/时间 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 常规 R1 | `feature/*` → `dev` | R1；完整声明、1 个非作者批准后通过 | 待真实演练 | 待真实演练 | 待实际 Check Run 读取 | 逐项记录受信任事件；review 后由维护者重跑 | 待真实演练 | 待填写 |
| R2 | `feature/*` → `dev`（auth/router/store） | R2；不可被 label 下调，需测试证据及可读保护性 review/request | 待真实演练 | 待真实演练 | 待实际 Check Run 读取 | 逐项记录受信任事件；review 后由维护者重跑 | 待真实演练 | 待填写 |
| master hotfix | `hotfix/master-*` → `master` | 缺 incident/前移计划时给出修复诊断；完整资料、2 个非作者批准后才通过 | 待真实演练 | 待真实演练 | 待实际 Check Run 读取 | 逐项记录受信任事件；review 后由维护者重跑 | 待真实演练 | 待填写 |

完成三项真实演练前：

- 不得把 `Governance Gate` 填入 `dev.json` 或 `master.json` 的 required-check context；
- 不得将本地 workflow job id 视为 GitHub 实际 Check Run context；
- 不得把 shadow 观察期、D3 Ruleset 应用或 D6 tag/release-environment 状态标为完成。
