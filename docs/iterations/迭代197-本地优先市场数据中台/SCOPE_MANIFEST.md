# MD-197-SCOPE-MANIFEST：冻结基线后的范围证据工具

> 状态：已为当前 `dev` 候选生成并验证范围清单（2026-09-10；manifest SHA-256：`2950d1ac6f05d3a468060d07d4b2289363f21413d026e20ef844f9c8018961df`）。
>
> 冻结输入：[iter196-market-data-baseline-20260909.json](iter196-market-data-baseline-20260909.json)；生成结果：[iteration197-market-data-scope-manifest-20260909.json](iteration197-market-data-scope-manifest-20260909.json)。基线引用迭代 196 的冻结候选与不可变 [更正收据](../迭代196-改进优化ai生成策略流程/CANDIDATE_FREEZE_CORRECTION_20260910.md) SHA-256，而不是当前工作树或测试夹具。该 artifact 只覆盖 21 个公开 family 与 UI/API 输入；不覆盖私有估值 collector、`md_source_payloads` / `md_source_snapshot_payload_refs` 迁移、shared BLOB 完整性或完整 receipt 重建。

## 目的

`src/backend/scripts/generate_iteration197_scope_manifest.py` 从三个当前代码面生成一个确定性的**临时范围清单**：

1. 服务端 `DatasetContractRegistry` 的 21 个家族合同；
2. `/data/market` 的资产页签、`daily/weekly/monthly` 输入和 21 个显示家族；
3. 后端 `MarketDataAssetType`、`MarketDataFrequency` 与现有 legacy period 映射。

它把每一行的产品合同、UI/API 可接受输入、生成器及来源文件 SHA-256 和独立 `row_sha256` 固化为 JSON。清单还有整体 `manifest_sha256`，因此审核者可以区分单行被改动、整份文件被改动和当前源代码漂移。

清单只描述当前合同面。它不会启用 `MARKET_DATA_QUERY_V2_ENABLED`、`MARKET_DATA_ONLINE_FETCH_ENABLED` 或前端开关，也不会授权 `/investment/strategies` 使用生产数据路径；也不能证明私有 collector、shared payload/ref schema、BLOB hash 或 target receipt 重建。生成结果始终包含：

```json
{
  "scope_status": "provisional",
  "strategy_page_production_status": "not_enabled_by_scope_manifest"
}
```

## 必需的迭代 196 冻结输入

生成前必须由迭代 196 的负责人提供并审查一个 JSON 文件。字段必须完整、无额外字段，且 `baseline_ref` 为不可变完整 Git commit ID：

```json
{
  "schema_version": "iter196-market-data-baseline-v1",
  "iteration": 196,
  "status": "frozen",
  "baseline_ref": "<40-or-64-lowercase-hex-commit-id>",
  "baseline_sha256": "<64-lowercase-hex-frozen-artifact-hash>",
  "artifact_ref": "<reviewed-immutable-contract-artifact-reference>",
  "frozen_at": "<UTC-ISO-8601-time>"
}
```

`status` 不是 `frozen`、ref/hash 格式不合法、文件缺失、内容无法解析，都会在读取任何范围输入前以稳定错误码失败。没有“当前 HEAD”默认值，也没有自动写出的半成品清单。

## 操作方法

在 `src/backend` 下执行。当前候选使用下列受控输入和输出；重新生成前必须审查冻结基线和源代码变化：

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  scripts/generate_iteration197_scope_manifest.py \
  --iter196-baseline ../../docs/iterations/迭代197-本地优先市场数据中台/iter196-market-data-baseline-20260909.json \
  --output ../../docs/iterations/迭代197-本地优先市场数据中台/iteration197-market-data-scope-manifest-20260909.json

/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  scripts/generate_iteration197_scope_manifest.py \
  --validate ../../docs/iterations/迭代197-本地优先市场数据中台/iteration197-market-data-scope-manifest-20260909.json
```

生成会先在内存中重新验证行哈希、整体哈希和当前源文件，再原子写入目标文件。目标目录必须预先存在。验证会重新从当前检出推导期望内容；所以任何注册表、Pydantic API 类型、legacy 映射、前端页签、period 或家族声明变化，都会要求重新审查并生成新清单。

## 行语义与边界

- `declared_compatibility_periods` 是家族的已声明频率与现有页面 `daily/weekly/monthly` 的交集；它不表示该家族已配置来源。
- `v2_query_available` 表示当前市场页可以按服务端签发的精确 family、状态和 source policy 进入 v2 合同链；`v2_query_frequencies` 保留该 family 的完整 v2 频率集合。当前公共 ready allowlist 仅包含 `bars`、`reference_series` 与单记录 `quote_snapshot` 的精确合同形状；`valuation_snapshot`、期权 slice、曲面、报告和库存家族即使出现在声明清单也必须为 `unconfigured/not_applicable`，前端不得把它们变为可选或可查询。
- `v2_query_periods` 仅表示现有 `daily/weekly/monthly` 兼容 period 输入的交集。合格的 ready 快照或分钟频率可以由 v2 UI 直接表达，但不会被这个兼容字段遗漏后误记为不可选；未配置报告类不得因此得到 query 路径。页面默认仍是 `asset.realtime`；其他非实时行必须由用户显式选择，不能由前端或 provider 猜测为可执行。
- `declared_api_frequency_inputs` 是该合同所声明且被 public query schema 接受的频率；不是上游提供方能力承诺。
- `contract_status=unconfigured` 仍会进入 21 行范围清单，以防需求、页面和服务端合同之间产生静默遗漏；它绝不是可取数状态。

## 失败码与验收作用

| 错误码 | 含义 | 处理 |
| --- | --- | --- |
| `ITER196_BASELINE_REQUIRED` | 没有指定或找不到基线文件 | 保持策略页关闭，等待 196 提供审查后的冻结基线。 |
| `ITER196_BASELINE_NOT_FROZEN` | 基线明确不是 `frozen` | 不生成清单；不能以草稿替代冻结输入。 |
| `SCOPE_MANIFEST_FRONTEND_*_DRIFT` | 当前页面资产、period、家族或 v2 选择规则无法被受限解析器证明 | 审查页面变化和对应合同，再更新工具及测试。 |
| `SCOPE_MANIFEST_API_*_DRIFT` | API 类型或 legacy 映射与注册表不一致 | 先恢复精确合同，不能扩大范围。 |
| `SCOPE_MANIFEST_ROW_HASH_MISMATCH` | 某一产品行被改变而未重算证据 | 拒绝整份清单。 |
| `SCOPE_MANIFEST_CONTENT_DRIFT` | 哈希自洽但不再能从当前源代码重建 | 重新审查并生成，不复用旧产物。 |

本工具是迭代 196/197 集成候选的一项输入完整性闸门。它不能代替私有 collector、shared payload/ref migration 或完整 receipt 重建的测试，也不能代替单 head Alembic 演练、真实 AkShare/OpenBB 数据回执、跨数据库 PIT 验证、浏览器灰度或策略工件的端到端验收。
