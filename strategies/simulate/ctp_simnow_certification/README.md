# SimNow CTP 模拟认证工作区

这是面向初学者的 SimNow CTP 工作区。它保留了 33 个认证场景，包括登录、下单、平仓、撤单、连接监测、阈值告警、错误处理、应急处理和日志证据；源码来自项目中的 CTP 认证套件，并已适配为 `backtrader_web` 的策略模板。

## 安全约定

`--dry-run` 和 `--list` 不会连接 CTP。任何会执行认证场景的命令都必须带 `--execute`。其中下单、平仓、撤单、批量撤单等场景可能向 SimNow 提交测试委托；仅使用 SimNow 测试账户，并先确认合约、资金和当前交易时段。

在网页策略管理器中无参数启动该模板时，工作区只执行离线预检后退出；这样不会因为一次误点击就连接柜台。需要实际认证时请使用下文带 `--execute` 的命令。

## 第一次使用

```bash
cd /Users/yunjinqi/Downloads/backtrader_web
cp strategies/simulate/ctp_simnow_certification/.env.example \
  strategies/simulate/ctp_simnow_certification/.env
```

在 `.env` 中填写 `SIMNOW_USER_ID`、`SIMNOW_PASSWORD`，并把 `SIMNOW_ORDER_SYMBOL` 与 `SIMNOW_TICK_SYMBOL` 改为当前可交易合约。可选环境键为 `new_7x24`、`new_group1`、`new_group2`、`new_group3`。

先做离线预检：

```bash
conda run -n base python strategies/simulate/ctp_simnow_certification/run.py --dry-run
conda run -n base python strategies/simulate/ctp_simnow_certification/run.py --list
```

先从登录认证开始，再按需运行更多场景：

```bash
conda run -n base python strategies/simulate/ctp_simnow_certification/run.py \
  --case C01 --execute

conda run -n base python strategies/simulate/ctp_simnow_certification/run.py \
  --case T01 --case T03 --execute --timeout 180
```

只有在已获得测试授权并理解全部场景影响时才执行全量验证：

```bash
conda run -n base python strategies/simulate/ctp_simnow_certification/run.py \
  --all --execute
```

运行证据会写到 `reports/latest/`，该目录和 `.env` 均不会纳入 Git。优先使用这里的 `run.py`；内部 `run_case.py` 同样要求 `--execute`，避免绕过确认步骤。
