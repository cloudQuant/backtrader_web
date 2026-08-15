# 迭代 192 故障切换 Runbook

## 原则

1. 先关闭新 cohort 和双写，不删除旧表。
2. 保留不可变 prediction/outcome/run 事实，不覆盖审计。
3. 恢复后必须重新核对身份、cutoff、来源许可和用户隔离。

## 切换顺序

1. 停止 `ASSET_RESEARCH_SCHEDULE_ENABLED`、`ASSET_RESEARCH_TASK_RUNNER_ENABLED`、`ASSET_RESEARCH_OUTCOME_EVALUATOR_ENABLED`。
2. 将股票双写切回 `OFF`，旧接口继续读写旧表。
3. 检查 `/metrics`、结构化日志和数据库租约，确认无卡死任务。
4. 定位故障来源并修复后，在一次性环境完成回放验证。
5. 经 owner/QA 签署后再打开新读或影子写。

## 禁止

- 禁止 `alembic stamp` 或删除旧表绕过恢复。
- 禁止把失败数据补成中性或回填历史预测。
- 禁止在未验证来源许可、主数据和 calendar 前打开真实资产 capability。

