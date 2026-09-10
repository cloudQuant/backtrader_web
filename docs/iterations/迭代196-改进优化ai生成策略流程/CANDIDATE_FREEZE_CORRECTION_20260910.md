# 迭代 196 Git 候选冻结收据更正（2026-09-10）

## 更正范围

本收据以追加方式更正 [2026-09-09 Git 候选冻结收据](CANDIDATE_FREEZE_20260909.md) 中的实现候选完整提交号。原收据不作修改，其当前内容 SHA-256 为 `f47d8ff435a36f53a43049a209c0b614f4bde59f8c50e2dd76d56385e42646d1`。

| 字段 | 原记录 | 经 Git 对象复核后的值 |
| --- | --- | --- |
| 实现候选提交 | `3ebe7717f6f901932591f59e6f1bb8244827b493` | `3ebe7717a0bfe7ebf1cde2dfc501d6842034c253` |
| 合并提交 | `fec74728ad4469ae6481b134323a6dd7d1401d32` | `fec74728ad4469ae6481b134323a6dd7d1401d32` |
| 合并提交第二父 | 未单列 | `3ebe7717a0bfe7ebf1cde2dfc501d6842034c253` |

## 复核依据

在本仓库 Git 对象库中，以下事实必须同时成立：

1. `git cat-file -e 3ebe7717a0bfe7ebf1cde2dfc501d6842034c253^{commit}` 成功；
2. `git rev-parse fec74728ad4469ae6481b134323a6dd7d1401d32^2` 精确返回该候选提交；
3. 原收据中的完整字符串 `3ebe7717f6f901932591f59e6f1bb8244827b493` 不可解析为 Git 对象。

因此，本更正只修复候选身份的完整 SHA 记录；它不修改原冻结收据的内容，也不扩大迭代 196 的验收结论。迭代 196 的 `IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO` 和 research/promotion 的 `BLOCKED/NO-GO` 仍然有效。
