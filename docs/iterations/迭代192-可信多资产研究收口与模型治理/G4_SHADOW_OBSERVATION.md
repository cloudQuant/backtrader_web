# G4 真实影子观察窗口

## 状态

- 观察起点：2026-08-07（AkShare 真实 T1 证据生成日）
- 当前前瞻影子交易日：0
- 期货/债券目标：至少 60 个交易日
- 数字货币目标：至少 90 个自然日（本项目 192 未做 crypto T1，另行启动）
- 目标最早完成日：约 2026-11 月上旬（以交易日历实际为准）

## 为什么不能提前验收

G4 的 T2 晋级要求“真实影子样本、至少 60 个交易日观察、校准、drift、审批和不可变
晋级事件”。60 个交易日必须由生产/预生产调度按交易日逐个写入不可变
`AssetSignalRun`、`AssetSignalPrediction` 和 `AssetSignalOutcome`。以下内容不能替代：

- 离线回测、walk-forward 测试夹具；
- 手工补录历史日期的 shadow 样本；
- 用 2026-08-07 单日真实快照重复计 60 次；
- 用模型卡或评估脚本存在性冒充前瞻统计；
- 用“计划已写好”或“脚本已能运行”作为 T2 证据。

## 启动步骤

```bash
cd src/backend
python -m alembic upgrade head
cd ../..
python scripts/ops/import_asset_research_manifest.py --apply
```

运行环境至少开启：

```bash
ASSET_RESEARCH_SCHEDULE_ENABLED=true
ASSET_RESEARCH_AKSHARE_PROVIDER_ENABLED=true
ASSET_RESEARCH_OUTCOME_EVALUATOR_ENABLED=true
```

然后启动后端 worker，使 `PUBLIC_SHADOW` 的期货和债券 schedule 在交易日 19:10
Asia/Shanghai 之后自动执行。每个 schedule 只对获批来源采集，不改变身份、cutoff
或 horizon。

## 每日核对

```sql
select
  asset_type,
  count(*) filter (where status = 'SUCCEEDED') as succeeded_runs,
  count(*) as total_runs
from asset_signal_runs
where owner_scope = 'PUBLIC_SHADOW'
group by asset_type;
```

```
select
  count(*) as pending_outcomes
from asset_signal_outcomes
where status = 'PENDING';
```

## 到期后 T2 证据包

- 60 个真实前瞻交易日的 `AssetSignalRun`/`AssetSignalPrediction` 时间序列；
- 与 entry prediction 同源、同 cutoff 的 `AssetSignalOutcome`；
- purge/embargo、CPCV/DSR/PBO、bootstrap 和费用/点差/滑点成本；
- model card、drift 报告、不可变 `SHADOW -> PROMOTED` 事件；
- 五方审批记录和证据 URI/hash；
- 单个 pooled 品种占比、分状态和尾部风险复核。

未达到上述证据前，方向模型保持 `SHADOW`，公开页面只显示 `HOLD/AVOID` 或
`RESEARCH_ONLY`。

## 风险 owner

- 数据工程 owner：负责调度、来源新鲜度、重试和日历；
- 量化 owner：负责评估、基线、drift 和晋级材料；
- 风控 owner：负责费用/风险/尾部指标复核；
- 合规 owner：负责来源许可、归属和再分发限制；
- 架构 owner：负责不可变证据、回滚和审计。

任一门禁未关闭不得晋级。
