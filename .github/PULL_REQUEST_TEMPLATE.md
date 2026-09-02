<!--
Iteration 175 §4.7 — the "i18n 变更清单" section is mandatory and is verified
by `scripts/ci/check_pr_template.py`. Please leave it in place even if your
PR does not touch any string literals (state "无变更" / "no change" in the
relevant subfields).

Iteration 195 — the static "Governance declaration" contract is verified by
`scripts/ci/check_pr_template.py`. Regular changes must target `dev`;
`master` only accepts `release/vX.Y.Z` promotions and `hotfix/master-*`
emergency fixes (see CONTRIBUTING.md, "Branch Model").
-->

## What & Why

<!-- What does this PR change? Why is it needed? -->

## How

<!-- High-level approach. Link to design doc / issue if relevant. -->

## Governance declaration

<!-- Required by iteration 195 PR Governance. Fill every field; placeholders fail CI. -->

- **目标分支**: <!-- dev，或 master + release/hotfix 理由 -->
- **风险等级**: <!-- R0 docs / R1 常规 / R2 核心路径（auth、DB、router/stores、bt_api_py）/ R3 workflow、docker、依赖。以变更路径自动分类为准，label 不能下调 -->
- **测试证据**: <!-- 本地/CI 测试命令与结果，或链接 -->

<!--
GitHub uses one PR template and cannot conditionally hide these sections. Normal PRs should
delete or ignore both master-only sections; only a master hotfix or release PR must keep and
complete its corresponding section.
-->
## Hotfix 前移计划 (master hotfix PRs only)

- **前移计划**: <!-- incident reference；等价修复在 dev 的 issue/PR 链接，或“不受影响”的理由 -->

## Release 清单 (master release promotion PRs only)

- **Release 清单**: <!-- 版本号、changelog 链接、完整验证证据、回滚点说明 -->

## Test Plan

<!-- How did you verify the change? Unit tests, e2e, manual repro, etc. -->

## i18n 变更清单 (i18n change manifest, 175 §4.7)

- **zh-CN key 数量 (count)**: `<fill in>`
- **en-US key 数量 (count)**: `<fill in>`
- **本 PR 新增 key (added)**:
  - <fill in or "无 / none">
- **本 PR 删除 key (removed)**:
  - <fill in or "无 / none">

## Bundle size note (175 §7.6)

<!--
If this PR ships > 10 % growth on the entry chunk gzip size, either:
  - apply the `BUNDLE_SIZE_GROWTH_OVERRIDE` label, or
  - include the marker `<!-- bundle-size-override: <reason> -->` in this body.

Otherwise leave this section as-is.
-->

## Checklist

- [ ] Tests added/updated
- [ ] Documentation updated (if applicable)
- [ ] No secrets / credentials committed
- [ ] CI is green (or any failures explained above)
