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

## 未执行的 10 个工作日 shadow 观察日志模板

状态：**模板未执行。** `PR Governance` 在 shadow 期只能报告，不得成为 required check。每个
工作日由治理负责人填一行，并为异常附 incident/PR 证据的受控引用；空白或 `N/A` 不得被解释为
“无问题”。观察期结束前，任何未解释的 P0/P1 误阻塞都必须重开相应任务，D4 继续保持 blocked。

| 工作日序号 | 收集范围/数据截止说明 | 错误分类 | 遗漏或重复 check | fork PR 反馈 | 误投 `master` | owner 请求结果（成功/失败/N/A）与证据引用 | 执行时间 | P0/P1、处置与证据引用 | 审阅结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 待真实观察 | 待填写 | 待填写 | 待填写 | 待填写 | 待真实观察：结果与证据引用待填写 | 待填写 | 待填写 | 待填写 |
| 2 | 待真实观察 | 待填写 | 待填写 | 待填写 | 待填写 | 待真实观察：结果与证据引用待填写 | 待填写 | 待填写 | 待填写 |
| 3 | 待真实观察 | 待填写 | 待填写 | 待填写 | 待填写 | 待真实观察：结果与证据引用待填写 | 待填写 | 待填写 | 待填写 |
| 4 | 待真实观察 | 待填写 | 待填写 | 待填写 | 待填写 | 待真实观察：结果与证据引用待填写 | 待填写 | 待填写 | 待填写 |
| 5 | 待真实观察 | 待填写 | 待填写 | 待填写 | 待填写 | 待真实观察：结果与证据引用待填写 | 待填写 | 待填写 | 待填写 |
| 6 | 待真实观察 | 待填写 | 待填写 | 待填写 | 待填写 | 待真实观察：结果与证据引用待填写 | 待填写 | 待填写 | 待填写 |
| 7 | 待真实观察 | 待填写 | 待填写 | 待填写 | 待填写 | 待真实观察：结果与证据引用待填写 | 待填写 | 待填写 | 待填写 |
| 8 | 待真实观察 | 待填写 | 待填写 | 待填写 | 待填写 | 待真实观察：结果与证据引用待填写 | 待填写 | 待填写 | 待填写 |
| 9 | 待真实观察 | 待填写 | 待填写 | 待填写 | 待填写 | 待真实观察：结果与证据引用待填写 | 待填写 | 待填写 | 待填写 |
| 10 | 待真实观察 | 待填写 | 待填写 | 待填写 | 待填写 | 待真实观察：结果与证据引用待填写 | 待填写 | 待填写 | 待填写 |

## 三类 PR 演练证据记录（均未执行）

以下是待真实草稿 PR 演练后填写的记录，不含真实 URL、SHA、check context、参与者或时间。
不得以本模板、截图占位符或本地 job 名称解除 D4。

### PR-E1：R1 常规 PR → `dev`

| 字段 | 待真实演练填写 |
| --- | --- |
| PR 证据引用 | 待填写 |
| base/head 提交证据 | 待填写 |
| 实际 Check Run display name/context | 待填写 |
| 受信任事件与维护者重跑观察 | 待填写 |
| 审批、结果与无不必要重型阻断证据 | 待填写 |

### PR-E2：R2 核心路径 PR → `dev`

| 字段 | 待真实演练填写 |
| --- | --- |
| PR 证据引用 | 待填写 |
| base/head 提交证据 | 待填写 |
| 自动升级、owner 请求与额外测试证据 | 待填写 |
| 实际 Check Run display name/context | 待填写 |
| 审批、结果与可读诊断 | 待填写 |

### PR-E3：`hotfix/master-*` 或 `release/vX.Y.Z` PR → `master`

| 字段 | 待真实演练填写 |
| --- | --- |
| PR 证据引用 | 待填写 |
| 来源命名与 base/head 提交证据 | 待填写 |
| 实际 Check Run display name/context | 待填写 |
| 两人审批、完整 checks、前移或 release metadata 证据 | 待填写 |
| 结果与未使用直接 push 的证据 | 待填写 |
