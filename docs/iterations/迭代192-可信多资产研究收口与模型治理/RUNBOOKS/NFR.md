# 迭代 192 NFR 验收 Runbook

## 目的

记录多资产研究的延迟、容量、韧性和前端性能基线执行方式。本文件不是 SLA；未实测的数值不得对外称为已通过。

## 执行入口

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  -p no:sugar tests/asset_research/test_metrics.py \
  tests/asset_research/test_lifecycle_executor.py
```

容量证据继续复用：

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  scripts/ci/run_asset_research_capacity.py \
  --database-url 'mysql+aiomysql://…/codex_iter192_capacity_<suffix>' \
  --confirm-disposable
```

## 证据要求

每份报告必须记录：

- Git SHA、数据库产品/版本、Alembic revision
- fixture/dataset 版本与校验和
- 并发、来源上限、worker 配置和 LLM stub 版本
- p50/p95/p99、错误率、CPU/RSS、队列深度、backlog
- 原始报告位置和 owner

## 当前状态

- 已实现：`asset_research_queue_depth`、LLM token/cost/fallback、migration reconciliation 指标。
- 已实现：tombstone-only lifecycle executor，dry-run 和审批提交测试通过。
- 未完成：NFR-L01 至 L08、C01/C02/C05、dashboard/告警、真实故障注入。

