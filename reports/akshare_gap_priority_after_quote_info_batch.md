# AkShare Gap Priority After Quote Info Batch

- Source audit: `reports/akshare_data_completeness_audit_after_quote_info_batch.json`
- Remaining gaps: 127
- Has data: 920 / 1047

## Top Remaining Gaps

| Priority | Task | Script | Category | Status | Target | Latest | Reason |
| ---: | ---: | --- | --- | --- | --- | --- | --- |
| 110 | 391 | `financial_fund_daily_em` | funds/weekly | empty_table | `FINANCIAL_FUND_DAILY_EM` | COMPLETED | 核心资产类别, 财务/公告/报表, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 110 | 392 | `financial_fund_hist_em` | funds/weekly | empty_table | `FINANCIAL_FUND_HIST_EM` | COMPLETED | 核心资产类别, 财务/公告/报表, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 100 | 719 | `stock_concept_fund_flow_hist` | stocks/weekly | missing_table | `STOCK_CONCEPT_FUND_FLOW_HIST` | FAILED: Script stock_concept_fund_flow_hist returned no data and target table stock_concept_fund_flow_hist is empty | 核心资产类别, 行情历史/分钟/tick, 资金流/持仓/榜单, 最新执行已暴露失败原因 |
| 100 | 953 | `stock_sector_fund_flow_hist` | stocks/weekly | missing_table | `STOCK_SECTOR_FUND_FLOW_HIST` | FAILED: Script stock_sector_fund_flow_hist returned no data and target table stock_sector_fund_flow_hist is empty | 核心资产类别, 行情历史/分钟/tick, 资金流/持仓/榜单, 最新执行已暴露失败原因 |
| 80 | 510 | `reits_hist_em` | funds/weekly | empty_table | `REITS_HIST_EM` | FAILED: Script reits_hist_em returned no data and target table reits_hist_em is empty | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数, 最新执行已暴露失败原因 |
| 80 | 639 | `index_zh_a_hist` | indexs/daily | empty_table | `INDEX_ZH_A_HIST` | FAILED: Script index_zh_a_hist returned no data and target table index_zh_a_hist is empty | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数, 最新执行已暴露失败原因 |
| 75 | 788 | `stock_hk_hist` | stocks/weekly | missing_table | `STOCK_HK_HIST` | FAILED: Script stock_hk_hist returned no data and target table stock_hk_hist is empty | 核心资产类别, 行情历史/分钟/tick, 最新执行已暴露失败原因 |
| 75 | 789 | `stock_hk_hist_min_em` | stocks/hourly | missing_table | `STOCK_HK_HIST_MIN_EM` | FAILED: Script stock_hk_hist_min_em returned no data and target table stock_hk_hist_min_em is empty | 核心资产类别, 行情历史/分钟/tick, 最新执行已暴露失败原因 |
| 75 | 1007 | `stock_zh_a_hist` | stocks/daily | missing_table | `STOCK_ZH_A_HIST` | FAILED: Script stock_zh_a_hist returned no data and target table stock_zh_a_hist is empty | 核心资产类别, 行情历史/分钟/tick, 最新执行已暴露失败原因 |
| 75 | 1008 | `stock_zh_a_hist_min_em` | stocks/hourly | missing_table | `STOCK_ZH_A_HIST_MIN_EM` | FAILED: Script stock_zh_a_hist_min_em returned no data and target table stock_zh_a_hist_min_em is empty | 核心资产类别, 行情历史/分钟/tick, 最新执行已暴露失败原因 |
| 70 | 455 | `graded_fund_daily_em` | funds/weekly | empty_table | `GRADED_FUND_DAILY_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 70 | 627 | `index_global_hist_em` | indexs/weekly | empty_table | `index_global_hist_em` | COMPLETED | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 70 | 640 | `index_zh_a_hist_min_em` | indexs/daily | empty_table | `INDEX_ZH_A_HIST_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 70 | 651 | `stock_zh_index_daily_em` | indexs/weekly | empty_table | `STOCK_ZH_INDEX_DAILY_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 70 | 695 | `stock_board_industry_hist_em` | stocks/daily | empty_table | `STOCK_BOARD_INDUSTRY_HIST_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 65 | 427 | `fund_lof_hist_em` | funds/daily | missing_table | `FUND_LOF_HIST_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 488 | `option_hist_dce` | funds/weekly | missing_table | `OPTION_HIST_DCE` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 504 | `option_sse_minute_sina` | funds/hourly | missing_table | `OPTION_SSE_MINUTE_SINA` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 536 | `futures_hist_em` | futures/daily | missing_table | `FUTURES_HIST_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 621 | `index_bloomberg_billionaires_hist` | indexs/weekly | missing_table | `INDEX_BLOOMBERG_BILLIONAIRES_HIST` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 687 | `stock_board_concept_hist_em` | stocks/daily | missing_table | `STOCK_BOARD_CONCEPT_HIST_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 712 | `stock_comment_detail_scrd_desire_daily_em` | stocks/daily | missing_table | `STOCK_COMMENT_DETAIL_SCRD_DESIRE_DAILY_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 984 | `stock_us_hist_min_em` | stocks/hourly | missing_table | `STOCK_US_HIST_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1018 | `stock_zh_a_tick_163` | stocks/daily | missing_table | `STOCK_ZH_A_TICK_163` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 60 | 406 | `fund_dividend_rank_em` | funds/weekly | empty_table | `FUND_DIVIDEND_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 60 | 425 | `fund_lcx_rank_em` | funds/weekly | empty_table | `FUND_LCX_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 55 | 368 | `spot_hist_sge` | common/hourly | missing_table | `SPOT_HIST_SGE` | COMPLETED | 行情历史/分钟/tick, 实时/池类数据 |
| 55 | 527 | `futures_dce_position_rank` | futures/weekly | missing_table | `FUTURES_DCE_POSITION_RANK` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 820 | `stock_hsgt_board_rank_em` | stocks/daily | missing_table | `STOCK_HSGT_BOARD_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 824 | `stock_hsgt_hold_stock_em` | stocks/daily | missing_table | `STOCK_HSGT_HOLD_STOCK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 825 | `stock_hsgt_individual_detail_em` | stocks/daily | missing_table | `STOCK_HSGT_INDIVIDUAL_DETAIL_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 827 | `stock_hsgt_institution_statistics_em` | stocks/daily | missing_table | `STOCK_HSGT_INSTITUTION_STATISTICS_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 829 | `stock_hsgt_stock_statistics_em` | stocks/daily | missing_table | `STOCK_HSGT_STOCK_STATISTICS_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 50 | 513 | `czce_to_spot` | futures/weekly | empty_table | `FUTURES_CZCE_TO_SPOT` | COMPLETED | 核心资产类别, 实时/池类数据, 已有空表，可能只需修保存/参数 |
| 45 | 95 | `forex_hist_em` | common/daily | empty_table | `FOREX_HIST_EM` | COMPLETED | 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 45 | 552 | `futures_spot_sys` | futures/hourly | missing_table | `FUTURES_SPOT_SYS` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 45 | 554 | `futures_to_spot_dce` | futures/hourly | missing_table | `FUTURES_TO_SPOT_DCE` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 45 | 555 | `futures_to_spot_shfe` | futures/hourly | missing_table | `FUTURES_TO_SPOT_SHFE` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 40 | 42 | `air_quality_hist` | common/weekly | missing_table | `AIR_QUALITY_HIST` | COMPLETED | 行情历史/分钟/tick |
| 40 | 82 | `currency_history` | common/weekly | missing_table | `CURRENCY_HISTORY` | COMPLETED | 行情历史/分钟/tick |
| 40 | 342 | `movie_boxoffice_cinema_daily` | common/daily | missing_table | `MOVIE_BOXOFFICE_CINEMA_DAILY` | COMPLETED | 行情历史/分钟/tick |
| 40 | 344 | `movie_boxoffice_daily` | common/daily | missing_table | `MOVIE_BOXOFFICE_DAILY` | COMPLETED | 行情历史/分钟/tick |
| 35 | 457 | `hk_fund_dividend_em` | funds/weekly | empty_table | `HK_FUND_DIVIDEND_EM` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 516 | `dce_delivery_data` | futures/monthly | empty_table | `FUTURES_DELIVERY_DCE` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 517 | `dce_delivery_match` | futures/weekly | empty_table | `FUTURES_DELIVERY_MATCH_DCE` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 563 | `inventory_data` | futures/weekly | empty_table | `FUTURES_INVENTORY_DATA` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 567 | `shfe_delivery_data` | futures/monthly | empty_table | `FUTURES_DELIVERY_SHFE` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 568 | `shfe_stock_weekly` | futures/weekly | empty_table | `FUTURES_STOCK_WEEKLY_SHFE` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 574 | `warehouse_receipt_dce` | futures/weekly | empty_table | `FUTURES_DCE_WAREHOUSE_RECEIPT` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 589 | `a_share_news_sentiment_index` | indexs/weekly | empty_table | `A_SHARE_NEWS_SENTIMENT_INDEX` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 611 | `emission_rights_index` | indexs/weekly | empty_table | `EMISSION_RIGHTS_INDEX` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 613 | `highway_logistics_index` | indexs/weekly | empty_table | `HIGHWAY_LOGISTICS_INDEX` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 614 | `highway_logistics_volume` | indexs/weekly | empty_table | `HIGHWAY_LOGISTICS_VOLUME` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 643 | `kq_foreign_trade_index` | indexs/weekly | empty_table | `KQ_FOREIGN_TRADE_INDEX` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 30 | 34 | `bond_zh_hs_cov_min` | bonds/daily | missing_table | `BOND_ZH_HS_COV_MIN` | COMPLETED | 核心资产类别 |
| 30 | 35 | `bond_zh_hs_cov_pre_min` | bonds/daily | missing_table | `BOND_ZH_HS_COV_PRE_MIN` | COMPLETED | 核心资产类别 |
| 30 | 104 | `get_dce_rank_table` | common/weekly | missing_table | `GET_DCE_RANK_TABLE` | COMPLETED | 资金流/持仓/榜单 |
| 30 | 386 | `xincaifu_rank` | common/weekly | missing_table | `XINCAIFU_RANK` | COMPLETED | 资金流/持仓/榜单 |
| 30 | 557 | `futures_warehouse_receipt_dce` | futures/weekly | missing_table | `FUTURES_WAREHOUSE_RECEIPT_DCE` | COMPLETED | 核心资产类别 |
| 30 | 620 | `index_bloomberg_billionaires` | indexs/daily | missing_table | `INDEX_BLOOMBERG_BILLIONAIRES` | COMPLETED | 核心资产类别 |
| 30 | 718 | `stock_concept_cons_futu` | stocks/daily | missing_table | `STOCK_CONCEPT_CONS_FUTU` | COMPLETED | 核心资产类别 |
| 30 | 723 | `stock_dxsyl_em` | stocks/daily | missing_table | `STOCK_DXSYL_EM` | COMPLETED | 核心资产类别 |
| 30 | 770 | `stock_gpzy_distribute_statistics_bank_em` | stocks/daily | missing_table | `STOCK_GPZY_DISTRIBUTE_STATISTICS_BANK_EM` | COMPLETED | 核心资产类别 |
| 30 | 771 | `stock_gpzy_distribute_statistics_company_em` | stocks/daily | missing_table | `STOCK_GPZY_DISTRIBUTE_STATISTICS_COMPANY_EM` | COMPLETED | 核心资产类别 |
| 30 | 864 | `stock_ipo_benefit_ths` | stocks/daily | missing_table | `STOCK_IPO_BENEFIT_THS` | COMPLETED | 核心资产类别 |
| 30 | 865 | `stock_ipo_declare` | stocks/daily | missing_table | `STOCK_IPO_DECLARE` | COMPLETED | 核心资产类别 |
| 30 | 908 | `stock_new_gh_cninfo` | stocks/weekly | missing_table | `STOCK_NEW_GH_CNINFO` | COMPLETED | 核心资产类别 |
| 30 | 911 | `stock_news_main_cx` | stocks/daily | missing_table | `STOCK_NEWS_MAIN_CX` | COMPLETED | 核心资产类别 |
| 20 | 346 | `movie_boxoffice_realtime` | common/hourly | missing_table | `MOVIE_BOXOFFICE_REALTIME` | COMPLETED | 实时/池类数据 |
| 20 | 367 | `spot_golden_benchmark_sge` | common/hourly | missing_table | `SPOT_GOLDEN_BENCHMARK_SGE` | COMPLETED | 实时/池类数据 |
| 20 | 377 | `spot_quotations_sge` | common/hourly | missing_table | `SPOT_QUOTATIONS_SGE` | COMPLETED | 实时/池类数据 |
| 20 | 378 | `spot_silver_benchmark_sge` | common/hourly | missing_table | `SPOT_SILVER_BENCHMARK_SGE` | COMPLETED | 实时/池类数据 |
| 5 | 41 | `air_quality_hebei` | common/daily | missing_table | `AIR_QUALITY_HEBEI` | COMPLETED |  |
| 5 | 46 | `akshare_catalog_endpoint` | common/daily | missing_table | `akshare_catalog_endpoint` | COMPLETED |  |
| 5 | 63 | `article_oman_rv` | common/daily | missing_table | `ARTICLE_OMAN_RV` | COMPLETED |  |
| 5 | 66 | `business_value_artist` | common/daily | missing_table | `BUSINESS_VALUE_ARTIST` | COMPLETED |  |
| 5 | 74 | `cost_living` | common/daily | missing_table | `COST_LIVING` | COMPLETED |  |
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
| 5 | 100 | `fx_quote_baidu` | common/hourly | missing_table | `FX_QUOTE_BAIDU` | COMPLETED |  |
| 5 | 340 | `migration_area_baidu` | common/daily | missing_table | `MIGRATION_AREA_BAIDU` | COMPLETED |  |
| 5 | 343 | `movie_boxoffice_cinema_weekly` | common/weekly | missing_table | `MOVIE_BOXOFFICE_CINEMA_WEEKLY` | COMPLETED |  |
| 5 | 345 | `movie_boxoffice_monthly` | common/monthly | missing_table | `MOVIE_BOXOFFICE_MONTHLY` | COMPLETED |  |
| 5 | 347 | `movie_boxoffice_weekly` | common/weekly | missing_table | `MOVIE_BOXOFFICE_WEEKLY` | COMPLETED |  |
| 5 | 348 | `movie_boxoffice_yearly` | common/daily | missing_table | `MOVIE_BOXOFFICE_YEARLY` | COMPLETED |  |
| 5 | 349 | `movie_boxoffice_yearly_first_week` | common/daily | missing_table | `MOVIE_BOXOFFICE_YEARLY_FIRST_WEEK` | COMPLETED |  |
| 5 | 357 | `online_value_artist` | common/daily | missing_table | `ONLINE_VALUE_ARTIST` | COMPLETED |  |
| 5 | 384 | `video_tv` | common/daily | missing_table | `VIDEO_TV` | COMPLETED |  |
| 5 | 385 | `video_variety_show` | common/daily | missing_table | `VIDEO_VARIETY_SHOW` | COMPLETED |  |
| 0 | 197 | `macro_china_nbs_nation` | common/daily | empty_table | `MACRO_CHINA_NBS_NATION` | COMPLETED | 已有空表，可能只需修保存/参数, 宏观但非交易核心 |
| 0 | 198 | `macro_china_nbs_region` | common/daily | empty_table | `MACRO_CHINA_NBS_REGION` | COMPLETED | 已有空表，可能只需修保存/参数, 宏观但非交易核心 |
| -5 | 124 | `macro_bank_english_interest_rate` | common/daily | missing_table | `MACRO_BANK_ENGLISH_INTEREST_RATE` | COMPLETED | 宏观但非交易核心 |
| -5 | 147 | `macro_china_bond_public` | common/daily | missing_table | `MACRO_CHINA_BOND_PUBLIC` | COMPLETED | 宏观但非交易核心 |
| -5 | 186 | `macro_china_insurance` | common/daily | missing_table | `MACRO_CHINA_INSURANCE` | COMPLETED | 宏观但非交易核心 |
| -5 | 211 | `macro_china_retail_price_index` | common/daily | missing_table | `MACRO_CHINA_RETAIL_PRICE_INDEX` | COMPLETED | 宏观但非交易核心 |
| -5 | 216 | `macro_china_society_traffic_volume` | common/daily | missing_table | `MACRO_CHINA_SOCIETY_TRAFFIC_VOLUME` | COMPLETED | 宏观但非交易核心 |
| -5 | 219 | `macro_china_swap_rate` | common/daily | missing_table | `MACRO_CHINA_SWAP_RATE` | COMPLETED | 宏观但非交易核心 |
| -5 | 221 | `macro_china_urban_unemployment` | common/daily | missing_table | `MACRO_CHINA_URBAN_UNEMPLOYMENT` | COMPLETED | 宏观但非交易核心 |
| -5 | 228 | `macro_cons_gold` | common/daily | missing_table | `MACRO_CONS_GOLD` | COMPLETED | 宏观但非交易核心 |
| -5 | 229 | `macro_cons_opec_month` | common/daily | missing_table | `MACRO_CONS_OPEC_MONTH` | COMPLETED | 宏观但非交易核心 |
| -5 | 230 | `macro_cons_silver` | common/daily | missing_table | `MACRO_CONS_SILVER` | COMPLETED | 宏观但非交易核心 |
| -5 | 232 | `macro_euro_cpi_yoy` | common/daily | missing_table | `MACRO_EURO_CPI_YOY` | COMPLETED | 宏观但非交易核心 |
| -5 | 240 | `macro_euro_ppi_mom` | common/daily | missing_table | `MACRO_EURO_PPI_MOM` | COMPLETED | 宏观但非交易核心 |
| -5 | 256 | `macro_global_sox_index` | common/daily | missing_table | `MACRO_GLOBAL_SOX_INDEX` | COMPLETED | 宏观但非交易核心 |
| -5 | 267 | `macro_shipping_bdi` | common/daily | missing_table | `MACRO_SHIPPING_BDI` | COMPLETED | 宏观但非交易核心 |
| -5 | 268 | `macro_shipping_bpi` | common/daily | missing_table | `MACRO_SHIPPING_BPI` | COMPLETED | 宏观但非交易核心 |
| -5 | 291 | `macro_usa_api_crude_stock` | common/daily | missing_table | `MACRO_USA_API_CRUDE_STOCK` | COMPLETED | 宏观但非交易核心 |
| -5 | 294 | `macro_usa_cb_consumer_confidence` | common/daily | missing_table | `MACRO_USA_CB_CONSUMER_CONFIDENCE` | COMPLETED | 宏观但非交易核心 |
| -5 | 301 | `macro_usa_core_pce_price` | common/daily | missing_table | `MACRO_USA_CORE_PCE_PRICE` | COMPLETED | 宏观但非交易核心 |
| -5 | 308 | `macro_usa_eia_crude_rate` | common/daily | missing_table | `MACRO_USA_EIA_CRUDE_RATE` | COMPLETED | 宏观但非交易核心 |
| -5 | 309 | `macro_usa_exist_home_sales` | common/daily | missing_table | `MACRO_USA_EXIST_HOME_SALES` | COMPLETED | 宏观但非交易核心 |
| -5 | 314 | `macro_usa_house_starts` | common/daily | missing_table | `MACRO_USA_HOUSE_STARTS` | COMPLETED | 宏观但非交易核心 |
| -5 | 316 | `macro_usa_industrial_production` | common/daily | missing_table | `MACRO_USA_INDUSTRIAL_PRODUCTION` | COMPLETED | 宏观但非交易核心 |
| -5 | 317 | `macro_usa_initial_jobless` | common/daily | missing_table | `MACRO_USA_INITIAL_JOBLESS` | COMPLETED | 宏观但非交易核心 |
| -5 | 319 | `macro_usa_ism_pmi` | common/daily | missing_table | `MACRO_USA_ISM_PMI` | COMPLETED | 宏观但非交易核心 |
| -5 | 322 | `macro_usa_michigan_consumer_sentiment` | common/daily | missing_table | `MACRO_USA_MICHIGAN_CONSUMER_SENTIMENT` | COMPLETED | 宏观但非交易核心 |
| -5 | 324 | `macro_usa_new_home_sales` | common/daily | missing_table | `MACRO_USA_NEW_HOME_SALES` | COMPLETED | 宏观但非交易核心 |
| -5 | 328 | `macro_usa_personal_spending` | common/daily | missing_table | `MACRO_USA_PERSONAL_SPENDING` | COMPLETED | 宏观但非交易核心 |
