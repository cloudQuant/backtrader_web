# 宏源期货 CTP 穿透式认证工作区

这是 `backtrader_web` 内的宏源期货 CTP 穿透式认证策略工作区。它包含 33 个认证场景和独立证据目录，适用于宏源期货提供的仿真/认证账户；不要用生产账户执行这些场景。

## 安全约定

`--dry-run` 与 `--list` 完全离线。执行任何认证场景都要显式带 `--execute`；下单、平仓、撤单、批量撤单和应急类场景可能会影响测试账户状态。全量运行前应取得宏源期货的认证安排和测试许可。

网页策略管理器以无参数方式启动模板时，只会运行离线预检后退出；这避免一次误点击就连接宏源柜台。实际认证请使用下文带 `--execute` 的命令。

## 配置与预检

```bash
cd /Users/yunjinqi/Downloads/backtrader_web
cp strategies/live/ctp_hongyuan_penetration/.env.example \
  strategies/live/ctp_hongyuan_penetration/.env
```

填写 `HONGYUAN_USER_ID` 与 `HONGYUAN_PASSWORD`。可选择 `HONGYUAN_ENV=telecom` 或 `unicom`，并务必将 `HONGYUAN_ORDER_SYMBOL`、`HONGYUAN_TICK_SYMBOL` 设置为宏源当前可交易的认证合约。

```bash
conda run -n base python strategies/live/ctp_hongyuan_penetration/run.py --dry-run
conda run -n base python strategies/live/ctp_hongyuan_penetration/run.py --list
```

## 执行认证

先从登录场景开始：

```bash
conda run -n base python strategies/live/ctp_hongyuan_penetration/run.py \
  --case C01 --execute
```

按测试计划执行多个场景或全量场景：

```bash
conda run -n base python strategies/live/ctp_hongyuan_penetration/run.py \
  --case T01 --case T02 --case T03 --execute

conda run -n base python strategies/live/ctp_hongyuan_penetration/run.py \
  --all --execute
```

报告保存在 `reports/latest/`，并被 Git 忽略。若需要正式 DOCX，先把宏源认可的模板放到本目录并命名为 `期货程序化交易系统功能测试过程记录报告模板.docx`，在 33 项结果齐全后执行：

```bash
conda run -n base python strategies/live/ctp_hongyuan_penetration/fill_docx_report.py
```

生成的 DOCX 与本地凭据都不会提交到版本库。
