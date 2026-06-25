# AkShare Gap Priority Current 2026-06-23 Rerun

- Source audit: `reports/akshare_data_completeness_audit_current_20260623_rerun.json`
- Remaining gaps: 40
- Has data: 1007 / 1047

## Top Remaining Gaps

| Priority | Task | Script | Category | Status | Target | Latest | Reason |
| ---: | ---: | --- | --- | --- | --- | --- | --- |
| 65 | 488 | `option_hist_dce` | funds/weekly | missing_table | `OPTION_HIST_DCE` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1018 | `stock_zh_a_tick_163` | stocks/daily | missing_table | `STOCK_ZH_A_TICK_163` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 60 | 425 | `fund_lcx_rank_em` | funds/weekly | empty_table | `FUND_LCX_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 55 | 368 | `spot_hist_sge` | common/hourly | missing_table | `SPOT_HIST_SGE` | COMPLETED | 行情历史/分钟/tick, 实时/池类数据 |
| 55 | 527 | `futures_dce_position_rank` | futures/weekly | missing_table | `FUTURES_DCE_POSITION_RANK` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 45 | 554 | `futures_to_spot_dce` | futures/hourly | missing_table | `FUTURES_TO_SPOT_DCE` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 40 | 82 | `currency_history` | common/weekly | missing_table | `CURRENCY_HISTORY` | COMPLETED | 行情历史/分钟/tick |
| 35 | 516 | `dce_delivery_data` | futures/monthly | empty_table | `FUTURES_DELIVERY_DCE` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 517 | `dce_delivery_match` | futures/weekly | empty_table | `FUTURES_DELIVERY_MATCH_DCE` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 574 | `warehouse_receipt_dce` | futures/weekly | empty_table | `FUTURES_DCE_WAREHOUSE_RECEIPT` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 589 | `a_share_news_sentiment_index` | indexs/weekly | empty_table | `A_SHARE_NEWS_SENTIMENT_INDEX` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 643 | `kq_foreign_trade_index` | indexs/weekly | empty_table | `KQ_FOREIGN_TRADE_INDEX` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 30 | 104 | `get_dce_rank_table` | common/weekly | missing_table | `GET_DCE_RANK_TABLE` | COMPLETED | 资金流/持仓/榜单 |
| 30 | 386 | `xincaifu_rank` | common/weekly | missing_table | `XINCAIFU_RANK` | COMPLETED | 资金流/持仓/榜单 |
| 30 | 557 | `futures_warehouse_receipt_dce` | futures/weekly | missing_table | `FUTURES_WAREHOUSE_RECEIPT_DCE` | COMPLETED | 核心资产类别 |
| 30 | 620 | `index_bloomberg_billionaires` | indexs/daily | missing_table | `INDEX_BLOOMBERG_BILLIONAIRES` | COMPLETED | 核心资产类别 |
| 30 | 864 | `stock_ipo_benefit_ths` | stocks/daily | missing_table | `STOCK_IPO_BENEFIT_THS` | COMPLETED | 核心资产类别 |
| 30 | 908 | `stock_new_gh_cninfo` | stocks/weekly | missing_table | `STOCK_NEW_GH_CNINFO` | COMPLETED | 核心资产类别 |
| 30 | 911 | `stock_news_main_cx` | stocks/daily | missing_table | `STOCK_NEWS_MAIN_CX` | COMPLETED | 核心资产类别 |
| 20 | 367 | `spot_golden_benchmark_sge` | common/hourly | missing_table | `SPOT_GOLDEN_BENCHMARK_SGE` | COMPLETED | 实时/池类数据 |
| 20 | 377 | `spot_quotations_sge` | common/hourly | missing_table | `SPOT_QUOTATIONS_SGE` | COMPLETED | 实时/池类数据 |
| 20 | 378 | `spot_silver_benchmark_sge` | common/hourly | missing_table | `SPOT_SILVER_BENCHMARK_SGE` | COMPLETED | 实时/池类数据 |
| 5 | 41 | `air_quality_hebei` | common/daily | missing_table | `AIR_QUALITY_HEBEI` | COMPLETED |  |
| 5 | 63 | `article_oman_rv` | common/daily | missing_table | `ARTICLE_OMAN_RV` | COMPLETED |  |
| 5 | 66 | `business_value_artist` | common/daily | missing_table | `BUSINESS_VALUE_ARTIST` | COMPLETED |  |
| 5 | 80 | `currency_convert` | common/daily | missing_table | `CURRENCY_CONVERT` | COMPLETED |  |
| 5 | 81 | `currency_currencies` | common/daily | missing_table | `CURRENCY_CURRENCIES` | COMPLETED |  |
| 5 | 83 | `currency_latest` | common/daily | missing_table | `CURRENCY_LATEST` | COMPLETED |  |
| 5 | 84 | `currency_pair_map` | common/daily | missing_table | `CURRENCY_PAIR_MAP` | COMPLETED |  |
| 5 | 85 | `currency_time_series` | common/daily | missing_table | `CURRENCY_TIME_SERIES` | COMPLETED |  |
| 5 | 86 | `energy_carbon_bj` | common/daily | missing_table | `ENERGY_CARBON_BJ` | COMPLETED |  |
| 5 | 87 | `energy_carbon_domestic` | common/daily | missing_table | `ENERGY_CARBON_DOMESTIC` | COMPLETED |  |
| 5 | 88 | `energy_carbon_eu` | common/daily | missing_table | `ENERGY_CARBON_EU` | COMPLETED |  |
| 5 | 89 | `energy_carbon_gz` | common/daily | missing_table | `ENERGY_CARBON_GZ` | COMPLETED |  |
| 5 | 90 | `energy_carbon_hb` | common/daily | missing_table | `ENERGY_CARBON_HB` | COMPLETED |  |
| 5 | 91 | `energy_carbon_sz` | common/daily | missing_table | `ENERGY_CARBON_SZ` | COMPLETED |  |
| 5 | 357 | `online_value_artist` | common/daily | missing_table | `ONLINE_VALUE_ARTIST` | COMPLETED |  |
| 5 | 384 | `video_tv` | common/daily | missing_table | `VIDEO_TV` | COMPLETED |  |
| 5 | 385 | `video_variety_show` | common/daily | missing_table | `VIDEO_VARIETY_SHOW` | COMPLETED |  |
| -5 | 219 | `macro_china_swap_rate` | common/daily | missing_table | `MACRO_CHINA_SWAP_RATE` | COMPLETED | 宏观但非交易核心 |
