# 2026-08-03 六资产交互任务隔离验收

## 范围与隔离

本证据运行 Iteration 191 的真实交互任务持久化路径：

`QUEUED → durable lease → 授权快照 → 质量门 → prediction/run/outcome → 公开研报 → terminal lease release`。

运行环境是本机 Homebrew MySQL **9.4.0** 的独立、临时、无密码实例及名称受限的空 schema
`codex_iter191_six_asset_20260803_final`。先对该 schema 执行 `alembic upgrade head`，最终 revision 为
`20260811_asset_research_task_leases`。没有读取或写入共享 `backtrader_web` 数据库、账户、外部来源或真实市场数据。
验收结束后，三个仅用于本次尝试的 `codex_iter191_six_asset_*` schema 已删除、临时实例已停止，数据目录已移至系统废纸篓；共享数据库未受影响。

夹具来源 `iter191-six-asset-fixture-source` 仅在临时 schema 中注册为 `RESEARCH_APPROVED`；数据适配器是进程内确定性夹具，明确记录 `external_network_used=false`、`market_data_used=false`、`execution_enabled=false`。该来源不会使共享环境的 capability 打开。

## 执行命令

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  ../../scripts/ci/run_asset_research_six_asset_fixture.py \
  --database-url 'mysql+aiomysql://root@127.0.0.1:33362/codex_iter191_six_asset_20260803_final' \
  --confirm-disposable
```

运行器拒绝非 MySQL、共享库以及不符合 `codex_iter191_six_asset_*` 命名空间的目标；同时要求目标库已经迁移且相关运行事实表为空。

## 结果

运行器返回 `passed=true`、`violations=[]`：

| 资产 | task/run | 公开动作性 | 公开建议 | 研报 | asset-specific outcome |
| --- | --- | --- | --- | --- | --- |
| 债券 | `SUCCEEDED/SUCCEEDED` | `RESEARCH_ONLY` | `HOLD` | 是 | 3 |
| 基金 | `SUCCEEDED/SUCCEEDED` | `RESEARCH_ONLY` | `HOLD` | 是 | 2 |
| 期货 | `SUCCEEDED/SUCCEEDED` | `RESEARCH_ONLY` | `HOLD` | 是 | 3 |
| 期权 | `SUCCEEDED/SUCCEEDED` | `RESEARCH_ONLY` | `HOLD` | 是 | 4 |
| 外汇 | `SUCCEEDED/SUCCEEDED` | `REGION_RESTRICTED` | `AVOID` | 是 | 3 |
| 数字货币 | `SUCCEEDED/SUCCEEDED` | `REGION_RESTRICTED` | `AVOID` | 是 | 3 |

持久化行数的独立只读 SQL 复核为：`tasks=6`、`snapshots=6`、`predictions=6`、`outcomes=18`、`reports=6`。六条公开 prediction 的 `execution_disabled` 均为 `true`；每一条终态 task 均释放了 lease。

期权夹具还显式要求 `ELIGIBLE` 质量状态，避免链/合同字段嵌套错误被“任务成功”掩盖。外汇与数字货币的 `REGION_RESTRICTED + AVOID` 是当前服务端地区策略的预期安全输出，不是交易信号。

## 回归

```text
tests/test_asset_research_six_asset_fixture_script.py
tests/asset_research/test_task_runner.py
tests/asset_research/test_plugin_outcome_contracts.py
49 passed, 1 warning
```

## 结论与边界

通过的是六类资产的任务生命周期、资产专属 outcome 分类、研报产物、MySQL 9.4 方言持久化及发布禁执行边界。它**不**证明真实数据源许可、主数据、实时性、成熟 outcome、方向预测质量、T1 观察或 T2 模型晋级；因此不能据此启用买卖、自动执行或对外投资建议。
