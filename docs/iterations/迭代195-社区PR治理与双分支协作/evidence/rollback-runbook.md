# 治理回滚手册（模板；未执行）

状态：**未执行。** 本地文档变更不等同于 GitHub 平台变更。本手册为被授权人员在真实 incident
中使用的程序，不授权本任务执行外部设置、远端同步、发布、push、merge 或 bypass。

## 责任与授权

| 场景 | 负责人 | 所需授权 | 不可替代的证据 |
| --- | --- | --- | --- |
| workflow/doc 回滚 | 变更 PR owner + 维护者 | 常规 PR 审核与合并授权 | revert PR、失败证据和 review 记录 |
| Ruleset evaluate/停用 | 仓库管理员 | GitHub Ruleset 管理权限与 incident 授权 | 受影响规则读回、incident 和恢复检查 |
| CODEOWNERS 修复 | CODEOWNERS owner + 维护者 | 常规 PR 审核；重新启用前由仓库管理员确认 | 修复 PR、CODEOWNERS errors 读回、owner 可用性证据 |
| 镜像/镜像发布异常 | 发布负责人 + D1 指定负责人 | incident 响应与明确的人工同步/发布授权 | 停止记录、只读差异证据和后续决策 |

## Incident 记录模板

| 字段 | 内容 |
| --- | --- |
| incident 编号/受控链接 | 待真实 incident 填写 |
| 发现方式与影响开始范围 | 待填写 |
| 受影响 PR、ref、workflow 或发布对象 | 待填写 |
| 严重度、用户/贡献者影响和证据 | 待填写 |
| 事件指挥、执行者与授权依据 | 待填写 |
| 临时缓解、恢复条件与验证结果 | 待填写 |
| 后续修复 PR、复盘责任人和到期日 | 待填写 |

## 1. Workflow 或文档回滚

1. 保存失败的 workflow run、PR 诊断或文档问题证据，并创建 incident（如达到 incident 门槛）。
2. 通过新的 PR 对目标变更执行 `revert`；不要直接推送修改历史。
3. 在 revert PR 中说明影响、保留原失败证据引用，并按受影响风险级别完成 review 与 checks。
4. 合并后验证受影响文档/工作流恢复到预期行为；失败证据、revert PR 和验证结论一并保存。

## 2. Ruleset 误阻塞

1. 仓库管理员建立 incident，列出受影响 PR、阻断表现、规则范围、临时负责人和恢复条件。
2. 先读取并保存规则现状与受影响 PR 证据。若平台支持 evaluate，管理员可将**对应**规则改为
   evaluate；否则可暂时停用**对应** Ruleset。不得扩大到无关规则或用常规 bypass 代替处置。
3. 修正 desired manifest、workflow 或 required-check 合同的根因后，通过 PR 评审。
4. 重新启用前，确认真实 required-check context 已稳定、D2/D3/D4/D6 前置仍满足，并执行 API、
   CODEOWNERS errors 与 verifier 读回；不一致则保持停用/评估并升级。
5. 更新 incident：影响 PR、停用窗口、恢复证据和复盘到期日。此过程不使 D3/D4/D6 自动通过。

## 3. CODEOWNERS 错误

1. 保持 required code-owner review 未启用或在受影响 Ruleset 中暂停，避免把贡献者锁死。
2. 通过 PR 修正 CODEOWNERS 路径或 owner；不得用不存在的账户、全局管理员常规 bypass 或手工批准
   冒充 code-owner review。
3. 合并修复后读取 CODEOWNERS errors，并确认每个受影响保护域有真实、可访问且满足 D2 的 owner。
4. 只有 errors 为空、owner 证据完备且管理员完成 Ruleset 读回验证后，才重新启用该要求。

## 4. 镜像、远端或镜像发布异常

1. 立即停止后续发布/镜像动作并创建 incident；保存只读 ref、digest 或 workflow 诊断证据。
2. 不自动覆盖任一远端，不自动重推 tag/image，也不依据本地分支或文档推断权威状态。
3. 由 D1 指定负责人和具备明确授权的管理员决定人工恢复方案；先明确权威 ref、影响、审批与恢复
   检查，再单独执行获批动作。
4. 在 incident 中登记恢复后的只读核验、例外到期日和复盘；无法核验时保持发布停止并升级。

## 强制禁止项与边界

- 禁止 force-push、删除/重写远端历史、自动外部修复、自动远端覆盖，以及以 bot label 或本地模板
  代替人工授权。
- 禁止在回滚期间自动绕过 Ruleset、伪造 check、伪造 release/tag/digest 或把未执行的命令记为完成。
- 本地文档或 manifest 的 PR 只能改变仓库内容；Ruleset、CODEOWNERS API 状态、受保护环境、tag、
  镜像和远端 ref 仍属于独立的平台/发布变更，必须按本手册取得授权并保留读回证据。
