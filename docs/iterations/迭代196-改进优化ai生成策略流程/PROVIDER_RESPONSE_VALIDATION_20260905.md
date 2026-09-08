# 迭代 196 模型响应运行时验证

日期：2026-09-05。对象为 `codex/iteration-196-ai-research-trust` 未提交工作树。此记录是本地组件验收，不是真实 Provider 调用证明。

## 评审结论与修复

独立评审合理：`ProviderResponse` dataclass 的类型注解不会验证适配器实际返回值。原实现遇到 `token_usage=None` 时在写调用账本前抛异常；`cost=None` 或不可 JSON 序列化的对象还可能在 token 已结算后才失败。原有全量回归没有覆盖该边界。

现在先对响应全部字段完成快照、类型、体积、深度及 JSON 有效性验证和脱敏，再允许结算：

| 字段 | 约束与失败语义 |
| --- | --- |
| `output` | 字符串，UTF-8 不超过 1 MiB；非法编码/脱敏解析失败均为 `LLM_PROVIDER_OUTPUT_INVALID` |
| `token_usage` | Mapping、有限 JSON；完整非负整数计数必须互相一致，否则 `LLM_PROVIDER_USAGE_UNVERIFIED` |
| `cost` | Mapping、有限 JSON；不得包含 NaN/Infinity、任意 Python 对象或非字符串 key |
| 元数据对象 | 每个映射 JSON 不超过 64 KiB、最多 4,096 个节点、深度不超过 16；遍历时累计字符串字节预算，避免先复制巨量字段再拒绝 |
| `provider_request_id` | `None` 或不超过 256 UTF-8 字节的字符串；入账前脱敏 |
| `fallback_chain` | tuple，最多 16 项，每项字符串不超过 256 UTF-8 字节；逐项脱敏 |

无效响应统一保留 `IN_FLIGHT` reservation，写入仅含稳定错误码和已知请求身份的账本；丢弃无效响应字段，不将未知使用量当作 0，不返回可供物化的成功结果。成本/身份/fallback 形状错误使用 `LLM_PROVIDER_RESPONSE_INVALID`。请求 ID 与 fallback 不再绕过脱敏。

输出、request ID、fallback 及元数据 key/value 均在结算前拒绝 NUL 字符，避免 SQLite 接受而其他数据库文本字段在结算后拒收。该边界由额外 5 项用例先复现，再修复；它是应用层一致拒绝测试，不是 PostgreSQL 全部 ledger 写入的端到端验证。

独立复核又发现“key 本身携密”路径：`api_key=...` 或 `authorization: Bearer ...` 作为 JSON 字段名时，仅脱敏 value 仍会泄漏原 key。两项用例先失败（11.58 秒），现对每个 metadata key 同样运行字符串脱敏检查；若 key 会被改变则拒绝整份响应，不持久化该 key，也不结算。该检查遵循项目现有敏感模式，不声称能识别没有任何特征的所有秘密文本。

通用敏感字段过滤器会匹配 `*_tokens`，因此仅对五个已知计数字段的非负整数保留数值，其余 token/凭据字符串仍脱敏。调用账本可以保留真实数值计数，而不是把合法 `total_tokens` 一并写为 `[REDACTED]`。

## 红绿证据

- 新增 16 项针对性用例先全部失败（13.80 秒），包括缺账本、先结算后序列化失败、超长响应未拒绝及计数误脱敏；不是因为 collection/夹具失败。
- 修复后完整 gateway 文件：45 passed、7 warnings，14.24 秒，退出码 0。
- 补充遍历累计预算与并发测试屏障后，gateway + generation materialization 两文件：52 passed、7 warnings，15.69 秒，退出码 0。
- NUL 增量先得到 5 failed、4 passed（`-k nul` 同时匹配已有 null 用例），14.16 秒；修复后的两文件最终结果为 **57 passed、7 warnings，15.49 秒，退出码 0**。
- key 携密补丁后的最新两文件为 **59 passed、7 warnings，24.05 秒，退出码 0**。前述 45/52/57 项是逐步增量历史，不混作同一跑次。
- 两个改动文件 Ruff check 通过，已按项目格式化。

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load \
  tests/test_ai_research_llm_gateway.py tests/test_ai_research_generation_materialization.py \
  --tb=short --junitxml=/private/tmp/iter196-current-head.WAaH1k/provider-response-key-final.xml
```

JUnit SHA-256：`43526a9f6fef3724e016216a8d34f2e904cc9b190204961ca516ec27ef4602f9`。首轮 45 项 JUnit 为 `provider-response-validation.xml`，SHA-256：`b22723c4353bd4f0695f5f0d6ac33990b8f3720829a1a3267d4e5a97439a38e5`；两者均在同一临时证据目录。

上段前一个摘要对应历史 52 项 `provider-response-materialization.xml`；最终 **57 项** JUnit 为 `provider-response-materialization-final.xml`，SHA-256：`68fdc773a0ec7e827a3d5bd5f568a0db878b8b1556de54cdaa44a2d96e6981db`，不混用两个跑次。

最新 **59 项** JUnit `provider-response-key-final.xml` 的 SHA-256 为 `ac1eb631cc9c9b6838013ac93a0ead314cdd0111518c6a78ce6eae80905b2ba5`。

并发记账测试也移除了已不经过的 `_locked_bucket` 屏障，改为两个独立 gateway 都到达真实 settlement 入口后同时放行，且断言确实到达两次。它验证独立连接的并发调用和最终 `(reserved, settled, active)=(0,34,0)`，不声称强制了某一数据库锁排序或旧 ORM 快照交错。

## 边界

- 本补丁防止可确定的坏响应绕过账本；没有把配额事务、外部提供商和调用账本三个提交点变成原子事务。数据库不可用/进程崩溃仍需要独立对账和未知状态恢复。
- Gateway 限制的是已返回对象的校验；HTTP 接收、反序列化前的体积/超时限制仍是 Provider adapter 的责任。
- 响应计数来自受控适配器，不等于供应商账单核对；成本 `{}` 可显式表示未知，不能推断免费。
- 真实 adapter 的供应商身份、实际模型版本和请求 ID 保真，以及 deployment factory 的 GENERATE 接线尚须独立闭合。
- 此增量发生在先前 5,034 项全量回归之后，不将旧全量结果冒称本补丁的回归证据。当前局部绿色也不改变迭代整体验收 `NO-GO`。
