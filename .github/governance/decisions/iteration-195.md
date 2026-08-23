# Iteration 195 — Decision Gates (D0–D7)

> 记录日期：2026-08-23
> 决策依据：仓库所有者授权按《迭代195：社区 PR 治理与双分支协作正式迭代计划》实施；各门推荐值即计划 §2 的推荐值。
> 规则：没有决策记录不得将任何规则切为阻塞状态；"稍后再说"不是已通过。本文件只登记仓库内可追溯决策，外部 GitHub/Gitee 设置仍须由管理员在对应门通过后单独执行。

## D0 — 默认分支与双分支语义

- **状态：通过**
- 决策：暂保留 `master` 为默认分支，保持稳定克隆/发布入口；由 `PR Governance` 门禁阻断普通 PR 目标为 `master`。安全治理 workflow、其调用的标准库脚本与治理 manifest 须经 `release/governance-bootstrap` PR 提升到 `master` 后才对 fork 的 `pull_request_target` 生效。
- 决策人：仓库所有者 `@cloudQuant`（2026-08-23 授权实施本计划）
- 证据：`docs/iterations/迭代195-社区PR治理与双分支协作/evidence/preflight.md` §1/§3（GitHub API 返回默认分支 `master`）
- 下一步：bootstrap PR 合并后在 fork 草稿 PR 上做 shadow 演练（Task 2 Step 3.5）。

## D1 — 远端权威与当前漂移处置

- **状态：通过**
- 决策：GitHub 为唯一 PR / 发布权威；Gitee 仅作受监控只读镜像。当前 GitHub/Gitee `master` SHA 差异登记为镜像事件，由人工确定同步方案；监控脚本只报告、不自动同步、不 force-push。
- 决策人：仓库所有者 `@cloudQuant`（2026-08-23）
- 证据：preflight §2（GitHub master=`605d4d0e` vs Gitee master=`3d051306`；dev 两端一致）；事件记录 `.github/governance/decisions/remote-sync-incident.md`
- 下一步：管理员人工核对两段历史后择期同步；复核日期 2026-09-30。

## D2 — 真实 owner 与审批池

- **状态：通过（含到期日例外）**
- 决策：受保护域主 owner 使用已验证的真实 GitHub 用户 `@cloudQuant`（类型 `User`，CODEOWNERS errors API 返回空）。R2/R3 与 `master` 的第二独立维护者审批池尚未建立——在该审批池确认前，不启用 code-owner required review，Ruleset 审批数先按"至少 1 位批准"落地，`master` 双人审批作为 Ruleset 静态要求保留但依赖后续审批池扩充。
- 决策人：核心维护者 `@cloudQuant`（2026-08-23）
- 证据：preflight §1 #5（errors 空）、§3 #3（owner 类型验证）
- 到期日例外：备用 owner 名单须于 **2026-10-01** 前补充并经成员可访问性复核；逾期未补则维持"仅 code-owner 提示、不强制 required review"。
- 下一步：邀请第二维护者加入审批池；补充后更新 CODEOWNERS 与 manifest。

## D3 — Ruleset 能力与 bypass

- **状态：有到期日的例外**
- 决策：manifest 先行（`.github/governance/rulesets/*.json` 为归一化 desired state）；沙盒/观察期验证（required workflow/check、code-owner review 字段可用性、evaluate 支持）未完成前，不在远端应用任何 blocking Ruleset。常规 bypass 保持为零；紧急 bypass 须 incident + 理由 + 24 小时复盘。
- 决策人：仓库管理员 `@cloudQuant`（2026-08-23）
- 证据：preflight §1 #2/#3/#4（Ruleset 列表为空、无既有保护）
- 到期日：**2026-10-15** 前完成沙盒验证与 `verify_github_governance.py --live` 读回对比；逾期则继续以 shadow gate 运行并在本文件追加延期理由。
- 下一步：Task 6 shadow 期结束后按 manifest 应用 `dev`，读回验证后再处理 `master`。

## D4 — required-check 合同

- **状态：阻塞**
- 阻塞原因：确切的 check context 名称必须来自真实草稿 PR 的 Checks API/界面记录（Task 4 三类演练），禁止以 YAML job id 猜测。截至 2026-08-23 尚无演练记录。
- 责任人：CI owner `@cloudQuant`
- 解除条件：三类草稿 PR（R1→dev、R2→dev、hotfix/release→master）演练完成，且 `Governance Gate` 等聚合 check 在 opened/synchronize/labeled/unlabeled/review 等事件下均稳定报告；记录写入 `evidence/dry-run-matrix.md`。
- 未解除前的约束：Ruleset 不配置 required checks；manifest 中 required-check 字段保留占位来源说明。

## D5 — preview 产品边界

- **状态：通过**
- 决策：本迭代只保留无 secrets 的 "Preview Build Artifact"；删除虚构部署 URL 与部署宣称。真实托管预览（平台、凭据、cleanup、环境保护）另立方案，不在本迭代承诺。
- 决策人：发布/平台 owner `@cloudQuant`（2026-08-23）
- 证据：`deploy-preview.yml` 改造（Task 5），artifact 名称与 job summary 不再出现 "Deployed" 字样。
- 下一步：如需真实 preview，另立迭代签署平台与凭据设计。

## D6 — release tag 与镜像权限

- **状态：有到期日的例外**
- 决策：仅允许指向 `master` 当前 HEAD 的受保护版本 tag（`vMAJOR.MINOR.PATCH[-rcN]`）触发镜像发布；工作流内先实现 tag↔`origin/master` HEAD 相等校验（不等则在 Docker login 前失败）。手动 `image_tag` 发布入口移除。Docker Hub 凭据绑定受保护 release environment —— environment 尚未配置，属本例外范围。
- 决策人：发布负责人 + 仓库管理员 `@cloudQuant`（2026-08-23）
- 到期日：**2026-10-15** 前由管理员创建 `release` environment 并加审批规则；在此之前发布工作流对生产凭据保持不可用状态（secrets 未注入 environment 即无法登录）。
- 下一步：非生产 release 演练（Task 5 Step 4）通过后配置 environment，再恢复生产发布。

## D7 — 安全披露通道与响应承诺

- **状态：阻塞**
- 阻塞原因：尚未书面确认受监控披露通道（候选：GitHub 私密漏洞报告 Private Vulnerability Reporting；备选受监控邮箱或工单系统）。未确认前不新增根 `SECURITY.md`，不承诺任何邮箱、私信或 SLA。
- 责任人：安全负责人 `@cloudQuant`
- 解除条件：通道开通验证（能收到测试报告）、支持版本清单、响应时限书面确认后，方可在独立 PR 中新增 `SECURITY.md` 并更新 Issue Template 指向。
- 过渡措施：`config.yml` 仅指向 GitHub Discussions 与文档，安全问题描述引导至私密漏洞报告（启用后自动生效），不写虚构联系方式。
