<!--
Iteration 175 §4.7 — the "i18n 变更清单" section is mandatory and is verified
by `scripts/ci/check_pr_template.py`. Please leave it in place even if your
PR does not touch any string literals (state "无变更" / "no change" in the
relevant subfields).
-->

## What & Why

<!-- What does this PR change? Why is it needed? -->

## How

<!-- High-level approach. Link to design doc / issue if relevant. -->

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
