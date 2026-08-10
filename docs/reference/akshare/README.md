# AKShare 文档镜像

## 来源

- 在线文档：<https://akshare.akfamily.xyz/>
- 源码仓库：<https://github.com/akfamily/akshare>
- 镜像来源：2026-08-07 从 `akfamily/akshare` 仓库 `docs/` 目录抓取
- 来源提交：`5cb11b4270ee5c4c97fdb6c4db040b51c82a46fd`
- 抓取时间：2026-08-07T13:46:38Z

本目录是 AKShare 在线文档的只读本地参考副本，主要用于迭代 191/192 多资产
研究的数据字段、接口、许可证边界和来源归属查询。它不声明这些上游数据源已获得
本项目的商业分发或交易用途授权。

## 目录

- `data/futures/futures.md`：期货交易所、交易时间、合约规则、合约详情、实时/历史行情、日历
- `data/bond/bond.md`：债券基础信息、行情、报价、收益率曲线、现金流/条款、可转债数据
- `data/tool/tool.md`：交易日历等通用工具接口
- `data/stock/stock.md`：股票、ETF、指数、宏观等股票侧接口
- `data/fund/fund_public.md`、`data/fund/fund_private.md`：公募/私募基金
- `data/option/option.md`、`data/fx/fx.md`、`data/currency/currency.md`：
  期权、外汇、数字货币相关接口
- `data/index.rst`、`data/qhkc/index.rst`：文档索引原始文件

## 已核对接口（迭代 192）

以下接口已在 2026-08-07 通过真实在线调用验证，并用于本项目 provider 映射：

| 用途 | AKShare 接口 | 关键字段 |
| --- | --- | --- |
| 期货历史行情 | `futures_zh_daily_sina` | `date/open/high/low/close/volume/hold/settle` |
| 期货实时盘口 | `futures_zh_realtime` | `symbol/bidprice1/askprice1/bidvol1/askvol1/trade/ticktime/tradedate` |
| 期货实时汇总 | `futures_zh_spot` | `symbol/open/high/low/current_price/hold/volume/amount` |
| 期货合约规格 | `futures_contract_detail` | `交易品种/交易单位/最后交易日/最低交易保证金/交割方式` |
| 期货交易所日历 | `futures_contract_info_cffex` | `合约代码/最后交易日/上市日/查询交易日` |
| 期货保证金/涨跌停 | `futures_rule` | `交易所/代码/交易保证金比例/涨跌停板幅度/合约乘数/最小变动价位` |
| 交易日历 | `tool_trade_date_hist_sina` | `trade_date` |
| 债券/可转债实时盘口 | `bond_zh_hs_cov_spot` | `symbol/name/trade/buy/sell/volume/amount/ticktime` |
| 债券条款与现金流 | `bond_cb_profile_sina` | `到期日/起息日期/付息日期/年付息次数/票面利率/利率说明/债券面值` |
| 债券历史行情 | `bond_zh_hs_daily` | `date/open/high/low/close/volume` |
| 收益率曲线 | `bond_china_yield` | `曲线名称/日期/3月/6月/1年/3年/5年/7年/10年/30年` |
| 收益率曲线历史 | `bond_china_close_return` | `日期/期限/到期收益率/即期收益率/远期收益率` |

## 使用边界

- 本镜像用于字段结构、来源归属和接口参数核对，不替代原始交易所/数据供应商的
  授权条款审查。
- 上游数据包括新浪财经、中国债券信息网、中国货币网、国泰君安期货等公开接口；
  项目只能按 `asset_data_source_registry` 中冻结的 `RESEARCH_ONLY` 用途使用。
- 禁止把本镜像中的接口文档描述成“已获授权可交易数据”或“可再分发数据”。
- 在线接口会随时间变化；新增资产/字段前必须重新抓取并记录新的提交号、抓取时间和字段样例。

## 重新抓取命令

```bash
git clone --depth 1 https://github.com/akfamily/akshare.git /tmp/akshare-docs-source
git -C /tmp/akshare-docs-source rev-parse HEAD
cp -R /tmp/akshare-docs-source/docs/data docs/reference/akshare/data
```

更新后应同时更新本 README 的提交号、抓取时间、字段核对表和相关证据哈希。
