# 2026-08-07 MySQL 9.4.0 真实合同证据

## 环境

- MySQL Server：9.4.0（Homebrew，macOS arm64）
- 方式：一次性临时 datadir，端口 3307，root 无密码仅限本机临时实例
- 数据库：`codex_iter192_ci`、`codex_iter191_contract`
- 完成后已关闭实例并删除临时目录

## 命令与结果

```bash
DATABASE_URL='mysql+aiomysql://root@127.0.0.1:3307/codex_iter192_ci' \
  /Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m alembic upgrade head
DATABASE_URL='mysql+aiomysql://root@127.0.0.1:3307/codex_iter192_ci' \
  /Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m alembic downgrade 20260801_stock_signal_predictions
DATABASE_URL='mysql+aiomysql://root@127.0.0.1:3307/codex_iter192_ci' \
  /Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m alembic upgrade head
```

结果：

- `upgrade head` 成功；
- `downgrade 20260801_stock_signal_predictions` 成功；
- 再次 `upgrade head` 成功；
- `alembic current` 为 `20260811_asset_research_task_leases (head)`。

## MySQL 合同测试

```bash
ASSET_RESEARCH_MYSQL_SHARED_SCHEMA_URL='mysql+pymysql://root@127.0.0.1:3307/codex_iter191_contract' \
ASSET_RESEARCH_MYSQL_SHARED_SCHEMA_CONFIRM=yes \
ASSET_RESEARCH_MYSQL_TASK_RUNNER_DISPOSABLE_URL='mysql+aiomysql://root@127.0.0.1:3307/codex_iter191_contract' \
ASSET_RESEARCH_MYSQL_TASK_RUNNER_DISPOSABLE_CONFIRM=yes \
  /Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m pytest -q -p no:sugar tests/asset_research/test_mysql_contract.py
```

结果：`3 passed`。

## 边界

该证据只证明一次性 MySQL 9.4.0 隔离实例上的迁移、约束和 task-runner 合同。它不替代生产目标环境的备份恢复、维护窗口和 forward-repair 演练。

