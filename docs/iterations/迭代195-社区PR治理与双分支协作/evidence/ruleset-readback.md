# Ruleset 读回记录（未执行模板）

状态：**未执行。** 本文件不是 GitHub Ruleset、CODEOWNERS 或 verifier 的运行输出，也不能证明
任何远端设置已激活、读回成功或与 desired manifest 一致。

## 当前前置阻塞清单

| Gate | 状态 | 读回前必须如实处理的阻塞 | 责任/到期日 | 受控来源 |
| --- | --- | --- | --- | --- |
| D2 | 有到期日的例外 | R2/R3 与 `master` 的第二独立维护者审批池尚未确认；不得据此启用 required code-owner review。 | 核心维护者 `@cloudQuant`；2026-10-01 前补充备用 owner 并复核可访问性。 | `.github/governance/decisions/iteration-195.md`（D2）；[preflight](preflight.md) §4。 |
| D3 | 有到期日的例外 | Ruleset 字段能力、evaluate 支持和 emergency bypass 的外部能力验证尚未完成；本地 manifest 仅是 desired state。 | 仓库管理员 `@cloudQuant`；2026-10-15 前完成沙盒验证及只读 verifier 对比。 | `.github/governance/decisions/iteration-195.md`（D3）；[preflight](preflight.md) §4。 |
| D4 | blocked | 三类真实草稿 PR 尚未产生经读取确认的稳定 required-check context；不得猜测或回填 context。 | CI owner `@cloudQuant`；无已批准的到期日。 | `.github/governance/decisions/iteration-195.md`（D4）；[preflight](preflight.md) §4。 |
| D6 | 有到期日的例外 | 受保护 release environment、tag 权限与真实授权主体尚未由管理员配置和验证；不得激活 `release-tags`。 | 发布负责人 + 仓库管理员 `@cloudQuant`；2026-10-15 前配置受保护 `release` environment 及审批规则。 | `.github/governance/decisions/iteration-195.md`（D6）；[preflight](preflight.md) §4。 |

## 后续的只读读回命令（不得在本任务执行）

当授权管理员完成相应外部设置后，按每次设置立即执行以下只读命令，并把**实际输出的受控摘要**
附到对应记录，而不是填写猜测值：

```bash
gh api repos/cloudQuant/backtrader_web/rulesets --paginate
gh api repos/cloudQuant/backtrader_web/codeowners/errors
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python \
  scripts/ci/verify_github_governance.py --live \
  --repo cloudQuant/backtrader_web --manifest-dir .github/governance/rulesets
```

这些命令用于读回和比对；它们不授权创建、修改、删除 Ruleset，也不授权 bypass、push 或 merge。

## 待填读回记录

每条记录均须有一次 API Ruleset 清单、一次 CODEOWNERS errors 结果和一次 verifier 输出的关联证据。
“无记录”“本地 JSON 存在”或人工口头确认均不是读回。

### `dev`

| 预期证据字段 | 待真实读回填写 |
| --- | --- |
| 读回范围与收集时点 | 待填写 |
| API 返回中匹配的 ref/规则摘要（不填造 ID） | 待填写 |
| enforcement、PR/审批、force/delete、code-owner、bypass 字段 | 待填写 |
| 实际 required checks 及其 D4 证据来源 | 待填写 |
| CODEOWNERS errors 结果 | 待填写 |
| verifier 退出状态与差异摘要 | 待填写 |
| 与 `.github/governance/rulesets/dev.json` 的逐字段比较 | 待填写 |

### `master`

| 预期证据字段 | 待真实读回填写 |
| --- | --- |
| 读回范围与收集时点 | 待填写 |
| API 返回中匹配的 ref/规则摘要（不填造 ID） | 待填写 |
| enforcement、PR/审批、force/delete、code-owner、bypass 字段 | 待填写 |
| 实际 required checks 及其 D4 证据来源 | 待填写 |
| CODEOWNERS errors 结果 | 待填写 |
| verifier 退出状态与差异摘要 | 待填写 |
| 与 `.github/governance/rulesets/master.json` 的逐字段比较 | 待填写 |

### `release-tags`

| 预期证据字段 | 待真实读回填写 |
| --- | --- |
| 读回范围与收集时点 | 待填写 |
| API 返回中匹配的 tag ref/规则摘要（不填造 ID） | 待填写 |
| enforcement、tag 创建/更新/删除、bypass 字段 | 待填写 |
| D6 tag 权限、受保护 environment 与 provenance 证据来源 | 待填写 |
| verifier 退出状态与差异摘要 | 待填写 |
| 与 `.github/governance/rulesets/release-tags.json` 的逐字段比较 | 待填写 |

## 比对、差异与升级规则

1. 逐字段将读回的归一化结果与同名 desired manifest 比较；required check 还必须回链到
   `dry-run-matrix.md` 中真实的 D4 证据。
2. 任何缺失、额外、值不一致、CODEOWNERS error、verifier 非零或无法读取均为未通过；保留原始受控
   证据、记录影响范围，并升级给仓库管理员和对应 gate owner。
3. 禁止填造 Ruleset ID、URL、SHA、actor、check context 或时间来让比对看似通过。外部能力或权限
   不足时，保留为阻塞/例外，不能以本地 manifest 替代平台证据。
