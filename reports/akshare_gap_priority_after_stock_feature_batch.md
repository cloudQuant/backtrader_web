# AkShare Gap Priority After Stock Feature Batch

- Source audit: `reports/akshare_data_completeness_audit_after_stock_feature_batch.json`
- Remaining gaps: 250
- Has data: 797 / 1047

## Top Remaining Gaps

| Priority | Task | Script | Category | Status | Target | Latest | Reason |
| ---: | ---: | --- | --- | --- | --- | --- | --- |
| 110 | 391 | `financial_fund_daily_em` | funds/weekly | empty_table | `FINANCIAL_FUND_DAILY_EM` | COMPLETED | 核心资产类别, 财务/公告/报表, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 110 | 392 | `financial_fund_hist_em` | funds/weekly | empty_table | `FINANCIAL_FUND_HIST_EM` | COMPLETED | 核心资产类别, 财务/公告/报表, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 100 | 719 | `stock_concept_fund_flow_hist` | stocks/weekly | missing_table | `STOCK_CONCEPT_FUND_FLOW_HIST` | FAILED: Script stock_concept_fund_flow_hist returned no data and target table stock_concept_fund_flow_hist is empty | 核心资产类别, 行情历史/分钟/tick, 资金流/持仓/榜单, 最新执行已暴露失败原因 |
| 100 | 953 | `stock_sector_fund_flow_hist` | stocks/weekly | missing_table | `STOCK_SECTOR_FUND_FLOW_HIST` | FAILED: Script stock_sector_fund_flow_hist returned no data and target table stock_sector_fund_flow_hist is empty | 核心资产类别, 行情历史/分钟/tick, 资金流/持仓/榜单, 最新执行已暴露失败原因 |
| 80 | 510 | `reits_hist_em` | funds/weekly | empty_table | `REITS_HIST_EM` | FAILED: Script reits_hist_em returned no data and target table reits_hist_em is empty | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数, 最新执行已暴露失败原因 |
| 75 | 788 | `stock_hk_hist` | stocks/weekly | missing_table | `STOCK_HK_HIST` | FAILED: Script stock_hk_hist returned no data and target table stock_hk_hist is empty | 核心资产类别, 行情历史/分钟/tick, 最新执行已暴露失败原因 |
| 75 | 1007 | `stock_zh_a_hist` | stocks/daily | missing_table | `STOCK_ZH_A_HIST` | FAILED: Script stock_zh_a_hist returned no data and target table stock_zh_a_hist is empty | 核心资产类别, 行情历史/分钟/tick, 最新执行已暴露失败原因 |
| 70 | 455 | `graded_fund_daily_em` | funds/weekly | empty_table | `GRADED_FUND_DAILY_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 70 | 627 | `index_global_hist_em` | indexs/weekly | empty_table | `index_global_hist_em` | COMPLETED | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 70 | 640 | `index_zh_a_hist_min_em` | indexs/daily | empty_table | `INDEX_ZH_A_HIST_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 70 | 651 | `stock_zh_index_daily_em` | indexs/weekly | empty_table | `STOCK_ZH_INDEX_DAILY_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 70 | 695 | `stock_board_industry_hist_em` | stocks/daily | empty_table | `STOCK_BOARD_INDUSTRY_HIST_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 65 | 1 | `bond_buy_back_hist_em` | bonds/daily | missing_table | `BOND_BUY_BACK_HIST_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 410 | `fund_etf_hist_em` | funds/daily | missing_table | `FUND_ETF_HIST_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 411 | `fund_etf_hist_min_em` | funds/hourly | missing_table | `FUND_ETF_HIST_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 427 | `fund_lof_hist_em` | funds/daily | missing_table | `FUND_LOF_HIST_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 428 | `fund_lof_hist_min_em` | funds/hourly | missing_table | `FUND_LOF_HIST_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 487 | `option_hist_czce` | funds/weekly | missing_table | `OPTION_HIST_CZCE` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 488 | `option_hist_dce` | funds/weekly | missing_table | `OPTION_HIST_DCE` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 490 | `option_hist_shfe` | funds/weekly | missing_table | `OPTION_HIST_SHFE` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 495 | `option_minute_em` | funds/hourly | missing_table | `OPTION_MINUTE_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 504 | `option_sse_minute_sina` | funds/hourly | missing_table | `OPTION_SSE_MINUTE_SINA` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 536 | `futures_hist_em` | futures/daily | missing_table | `FUTURES_HIST_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 621 | `index_bloomberg_billionaires_hist` | indexs/weekly | missing_table | `INDEX_BLOOMBERG_BILLIONAIRES_HIST` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 639 | `index_zh_a_hist` | indexs/daily | missing_table | `INDEX_ZH_A_HIST` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 687 | `stock_board_concept_hist_em` | stocks/daily | missing_table | `STOCK_BOARD_CONCEPT_HIST_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 688 | `stock_board_concept_hist_min_em` | stocks/hourly | missing_table | `STOCK_BOARD_CONCEPT_HIST_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 696 | `stock_board_industry_hist_min_em` | stocks/hourly | missing_table | `STOCK_BOARD_INDUSTRY_HIST_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 712 | `stock_comment_detail_scrd_desire_daily_em` | stocks/daily | missing_table | `STOCK_COMMENT_DETAIL_SCRD_DESIRE_DAILY_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 789 | `stock_hk_hist_min_em` | stocks/hourly | missing_table | `STOCK_HK_HIST_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 835 | `stock_individual_fund_flow` | stocks/daily | missing_table | `STOCK_INDIVIDUAL_FUND_FLOW` | FAILED: Script stock_individual_fund_flow returned no data and target table stock_individual_fund_flow is empty | 核心资产类别, 资金流/持仓/榜单, 最新执行已暴露失败原因 |
| 65 | 841 | `stock_industry_clf_hist_sw` | stocks/weekly | missing_table | `STOCK_INDUSTRY_CLF_HIST_SW` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 893 | `stock_main_fund_flow` | stocks/daily | missing_table | `STOCK_MAIN_FUND_FLOW` | FAILED: Script stock_main_fund_flow returned no data and target table stock_main_fund_flow is empty | 核心资产类别, 资金流/持仓/榜单, 最新执行已暴露失败原因 |
| 65 | 904 | `stock_market_fund_flow` | stocks/daily | missing_table | `STOCK_MARKET_FUND_FLOW` | FAILED: Script stock_market_fund_flow returned no data and target table stock_market_fund_flow is empty | 核心资产类别, 资金流/持仓/榜单, 最新执行已暴露失败原因 |
| 65 | 968 | `stock_sse_deal_daily` | stocks/daily | missing_table | `STOCK_SSE_DEAL_DAILY` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 984 | `stock_us_hist_min_em` | stocks/hourly | missing_table | `STOCK_US_HIST_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1000 | `stock_zh_a_cdr_daily` | stocks/daily | missing_table | `STOCK_ZH_A_CDR_DAILY` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1008 | `stock_zh_a_hist_min_em` | stocks/hourly | missing_table | `STOCK_ZH_A_HIST_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1009 | `stock_zh_a_hist_pre_min_em` | stocks/hourly | missing_table | `STOCK_ZH_A_HIST_PRE_MIN_EM` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1018 | `stock_zh_a_tick_163` | stocks/daily | missing_table | `STOCK_ZH_A_TICK_163` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1019 | `stock_zh_a_tick_tx_js` | stocks/daily | missing_table | `STOCK_ZH_A_TICK_TX_JS` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1021 | `stock_zh_ah_daily` | stocks/daily | missing_table | `STOCK_ZH_AH_DAILY` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1025 | `stock_zh_b_daily` | stocks/daily | missing_table | `STOCK_ZH_B_DAILY` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1026 | `stock_zh_b_minute` | stocks/daily | missing_table | `STOCK_ZH_B_MINUTE` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1031 | `stock_zh_index_hist_csindex` | stocks/daily | missing_table | `STOCK_ZH_INDEX_HIST_CSINDEX` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 65 | 1033 | `stock_zh_kcb_daily` | stocks/daily | missing_table | `STOCK_ZH_KCB_DAILY` | COMPLETED | 核心资产类别, 行情历史/分钟/tick |
| 60 | 406 | `fund_dividend_rank_em` | funds/weekly | empty_table | `FUND_DIVIDEND_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 60 | 425 | `fund_lcx_rank_em` | funds/weekly | empty_table | `FUND_LCX_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 60 | 436 | `fund_portfolio_hold_em` | funds/weekly | empty_table | `FUND_PORTFOLIO_HOLD_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 60 | 564 | `member_position_rank` | futures/weekly | empty_table | `FUTURES_MEMBER_POSITION_RANK` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 55 | 368 | `spot_hist_sge` | common/hourly | missing_table | `SPOT_HIST_SGE` | COMPLETED | 行情历史/分钟/tick, 实时/池类数据 |
| 55 | 527 | `futures_dce_position_rank` | futures/weekly | missing_table | `FUTURES_DCE_POSITION_RANK` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 534 | `futures_gfex_position_rank` | futures/weekly | missing_table | `FUTURES_GFEX_POSITION_RANK` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 541 | `futures_hold_pos_sina` | futures/daily | missing_table | `FUTURES_HOLD_POS_SINA` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 757 | `stock_gdfx_free_holding_analyse_em` | stocks/daily | missing_table | `STOCK_GDFX_FREE_HOLDING_ANALYSE_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 758 | `stock_gdfx_free_holding_change_em` | stocks/daily | missing_table | `STOCK_GDFX_FREE_HOLDING_CHANGE_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 760 | `stock_gdfx_free_holding_statistics_em` | stocks/daily | missing_table | `STOCK_GDFX_FREE_HOLDING_STATISTICS_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 761 | `stock_gdfx_free_holding_teamwork_em` | stocks/daily | missing_table | `STOCK_GDFX_FREE_HOLDING_TEAMWORK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 766 | `stock_gdfx_holding_statistics_em` | stocks/daily | missing_table | `STOCK_GDFX_HOLDING_STATISTICS_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 792 | `stock_hk_hot_rank_em` | stocks/daily | missing_table | `STOCK_HK_HOT_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 810 | `stock_hot_follow_xq` | stocks/daily | missing_table | `STOCK_HOT_FOLLOW_XQ` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 814 | `stock_hot_rank_em` | stocks/daily | missing_table | `STOCK_HOT_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 817 | `stock_hot_search_baidu` | stocks/daily | missing_table | `STOCK_HOT_SEARCH_BAIDU` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 818 | `stock_hot_tweet_xq` | stocks/daily | missing_table | `STOCK_HOT_TWEET_XQ` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 819 | `stock_hot_up_em` | stocks/daily | missing_table | `STOCK_HOT_UP_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 820 | `stock_hsgt_board_rank_em` | stocks/daily | missing_table | `STOCK_HSGT_BOARD_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 824 | `stock_hsgt_hold_stock_em` | stocks/daily | missing_table | `STOCK_HSGT_HOLD_STOCK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 825 | `stock_hsgt_individual_detail_em` | stocks/daily | missing_table | `STOCK_HSGT_INDIVIDUAL_DETAIL_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 827 | `stock_hsgt_institution_statistics_em` | stocks/daily | missing_table | `STOCK_HSGT_INSTITUTION_STATISTICS_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 829 | `stock_hsgt_stock_statistics_em` | stocks/daily | missing_table | `STOCK_HSGT_STOCK_STATISTICS_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 836 | `stock_individual_fund_flow_rank` | stocks/weekly | missing_table | `STOCK_INDIVIDUAL_FUND_FLOW_RANK` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 883 | `stock_lhb_jgstatistic_em` | stocks/daily | missing_table | `STOCK_LHB_JGSTATISTIC_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 889 | `stock_lhb_yyb_detail_em` | stocks/daily | missing_table | `STOCK_LHB_YYB_DETAIL_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 890 | `stock_lhb_yybph_em` | stocks/daily | missing_table | `STOCK_LHB_YYBPH_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 891 | `stock_lhb_yytj_sina` | stocks/daily | missing_table | `STOCK_LHB_YYTJ_SINA` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 924 | `stock_rank_cxd_ths` | stocks/weekly | missing_table | `STOCK_RANK_CXD_THS` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 933 | `stock_rank_xstp_ths` | stocks/weekly | missing_table | `STOCK_RANK_XSTP_THS` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 55 | 934 | `stock_rank_xxtp_ths` | stocks/weekly | missing_table | `STOCK_RANK_XXTP_THS` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 50 | 513 | `czce_to_spot` | futures/weekly | empty_table | `FUTURES_CZCE_TO_SPOT` | COMPLETED | 核心资产类别, 实时/池类数据, 已有空表，可能只需修保存/参数 |
| 45 | 38 | `bond_zh_hs_spot` | bonds/hourly | missing_table | `BOND_ZH_HS_SPOT` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 45 | 95 | `forex_hist_em` | common/daily | empty_table | `FOREX_HIST_EM` | COMPLETED | 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 45 | 481 | `option_current_em` | funds/daily | missing_table | `OPTION_CURRENT_EM` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 45 | 552 | `futures_spot_sys` | futures/hourly | missing_table | `FUTURES_SPOT_SYS` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 45 | 554 | `futures_to_spot_dce` | futures/hourly | missing_table | `FUTURES_TO_SPOT_DCE` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 45 | 555 | `futures_to_spot_shfe` | futures/hourly | missing_table | `FUTURES_TO_SPOT_SHFE` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 45 | 987 | `stock_us_spot_em` | stocks/hourly | missing_table | `STOCK_US_SPOT_EM` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 40 | 42 | `air_quality_hist` | common/weekly | missing_table | `AIR_QUALITY_HIST` | COMPLETED | 行情历史/分钟/tick |
| 40 | 82 | `currency_history` | common/weekly | missing_table | `CURRENCY_HISTORY` | COMPLETED | 行情历史/分钟/tick |
| 40 | 342 | `movie_boxoffice_cinema_daily` | common/daily | missing_table | `MOVIE_BOXOFFICE_CINEMA_DAILY` | COMPLETED | 行情历史/分钟/tick |
| 40 | 344 | `movie_boxoffice_daily` | common/daily | missing_table | `MOVIE_BOXOFFICE_DAILY` | COMPLETED | 行情历史/分钟/tick |
| 35 | 19 | `bond_info_cm` | bonds/weekly | empty_table | `BOND_INFO_CM` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 220 | `macro_china_trade_balance` | common/daily | missing_table | `MACRO_CHINA_TRADE_BALANCE` | COMPLETED | 财务/公告/报表, 宏观但非交易核心 |
| 35 | 337 | `macro_usa_trade_balance` | common/daily | missing_table | `MACRO_USA_TRADE_BALANCE` | COMPLETED | 财务/公告/报表, 宏观但非交易核心 |
| 35 | 395 | `fund_announcement_personnel_em` | funds/weekly | empty_table | `FUND_ANNOUNCEMENT_PERSONNEL_EM` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 419 | `fund_individual_analysis_xq` | funds/weekly | empty_table | `FUND_ANALYSIS_XQ` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 435 | `fund_portfolio_change_em` | funds/weekly | empty_table | `FUND_PORTFOLIO_CHANGE_EM` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 440 | `fund_rating_all` | funds/weekly | empty_table | `FUND_RATING_ALL` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 441 | `fund_rating_ja` | funds/weekly | empty_table | `FUND_RATING_JA` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 442 | `fund_rating_sh` | funds/weekly | empty_table | `FUND_RATING_SH` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 443 | `fund_rating_zs` | funds/weekly | empty_table | `FUND_RATING_ZS` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 449 | `fund_scale_open_sina` | funds/weekly | empty_table | `FUND_SCALE_OPEN_SINA` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 454 | `fund_value_estimation_em` | funds/weekly | empty_table | `FUND_VALUE_ESTIMATION_EM` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 457 | `hk_fund_dividend_em` | funds/weekly | empty_table | `HK_FUND_DIVIDEND_EM` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 516 | `dce_delivery_data` | futures/monthly | empty_table | `FUTURES_DELIVERY_DCE` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 517 | `dce_delivery_match` | futures/weekly | empty_table | `FUTURES_DELIVERY_MATCH_DCE` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 535 | `futures_gfex_warehouse_receipt` | futures/weekly | empty_table | `FUTURES_GFEX_WAREHOUSE_RECEIPT` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 563 | `inventory_data` | futures/weekly | empty_table | `FUTURES_INVENTORY_DATA` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 567 | `shfe_delivery_data` | futures/monthly | empty_table | `FUTURES_DELIVERY_SHFE` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 568 | `shfe_stock_weekly` | futures/weekly | empty_table | `FUTURES_STOCK_WEEKLY_SHFE` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 573 | `warehouse_receipt_czce` | futures/weekly | empty_table | `FUTURES_CZCE_WAREHOUSE_RECEIPT` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 574 | `warehouse_receipt_dce` | futures/weekly | empty_table | `FUTURES_DCE_WAREHOUSE_RECEIPT` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 589 | `a_share_news_sentiment_index` | indexs/weekly | empty_table | `A_SHARE_NEWS_SENTIMENT_INDEX` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 611 | `emission_rights_index` | indexs/weekly | empty_table | `EMISSION_RIGHTS_INDEX` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 613 | `highway_logistics_index` | indexs/weekly | empty_table | `HIGHWAY_LOGISTICS_INDEX` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 614 | `highway_logistics_volume` | indexs/weekly | empty_table | `HIGHWAY_LOGISTICS_VOLUME` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 643 | `kq_foreign_trade_index` | indexs/weekly | empty_table | `KQ_FOREIGN_TRADE_INDEX` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 35 | 698 | `stock_board_industry_min_em` | stocks/daily | empty_table | `STOCK_BOARD_INDUSTRY_MIN_EM` | COMPLETED | 核心资产类别, 已有空表，可能只需修保存/参数 |
| 30 | 21 | `bond_info_detail_cm` | bonds/weekly | missing_table | `BOND_INFO_DETAIL_CM` | COMPLETED | 核心资产类别 |
| 30 | 34 | `bond_zh_hs_cov_min` | bonds/daily | missing_table | `BOND_ZH_HS_COV_MIN` | COMPLETED | 核心资产类别 |
| 30 | 35 | `bond_zh_hs_cov_pre_min` | bonds/daily | missing_table | `BOND_ZH_HS_COV_PRE_MIN` | COMPLETED | 核心资产类别 |
| 30 | 103 | `get_cffex_rank_table` | common/weekly | missing_table | `GET_CFFEX_RANK_TABLE` | COMPLETED | 资金流/持仓/榜单 |
| 30 | 104 | `get_dce_rank_table` | common/weekly | missing_table | `GET_DCE_RANK_TABLE` | COMPLETED | 资金流/持仓/榜单 |
| 30 | 105 | `get_rank_table_czce` | common/weekly | missing_table | `GET_RANK_TABLE_CZCE` | COMPLETED | 资金流/持仓/榜单 |
| 30 | 109 | `get_shfe_rank_table` | common/weekly | missing_table | `GET_SHFE_RANK_TABLE` | COMPLETED | 资金流/持仓/榜单 |
| 30 | 113 | `hurun_rank` | common/weekly | missing_table | `HURUN_RANK` | COMPLETED | 资金流/持仓/榜单 |
| 30 | 386 | `xincaifu_rank` | common/weekly | missing_table | `XINCAIFU_RANK` | COMPLETED | 资金流/持仓/榜单 |
| 30 | 529 | `futures_display_main_sina` | futures/daily | missing_table | `FUTURES_DISPLAY_MAIN_SINA` | COMPLETED | 核心资产类别 |
| 30 | 547 | `futures_shfe_warehouse_receipt` | futures/weekly | missing_table | `FUTURES_SHFE_WAREHOUSE_RECEIPT` | COMPLETED | 核心资产类别 |
| 30 | 556 | `futures_warehouse_receipt_czce` | futures/weekly | missing_table | `FUTURES_WAREHOUSE_RECEIPT_CZCE` | COMPLETED | 核心资产类别 |
| 30 | 557 | `futures_warehouse_receipt_dce` | futures/weekly | missing_table | `FUTURES_WAREHOUSE_RECEIPT_DCE` | COMPLETED | 核心资产类别 |
| 30 | 620 | `index_bloomberg_billionaires` | indexs/daily | missing_table | `INDEX_BLOOMBERG_BILLIONAIRES` | COMPLETED | 核心资产类别 |
| 30 | 683 | `stock_bid_ask_em` | stocks/daily | missing_table | `STOCK_BID_ASK_EM` | COMPLETED | 核心资产类别 |
| 30 | 718 | `stock_concept_cons_futu` | stocks/daily | missing_table | `STOCK_CONCEPT_CONS_FUTU` | COMPLETED | 核心资产类别 |
| 30 | 723 | `stock_dxsyl_em` | stocks/daily | missing_table | `STOCK_DXSYL_EM` | COMPLETED | 核心资产类别 |
| 30 | 727 | `stock_dzjy_mrtj` | stocks/daily | missing_table | `STOCK_DZJY_MRTJ` | COMPLETED | 核心资产类别 |
| 30 | 731 | `stock_esg_hz_sina` | stocks/daily | missing_table | `STOCK_ESG_HZ_SINA` | COMPLETED | 核心资产类别 |
| 30 | 733 | `stock_esg_rate_sina` | stocks/daily | missing_table | `STOCK_ESG_RATE_SINA` | COMPLETED | 核心资产类别 |
| 30 | 735 | `stock_esg_zd_sina` | stocks/daily | missing_table | `STOCK_ESG_ZD_SINA` | COMPLETED | 核心资产类别 |
| 30 | 770 | `stock_gpzy_distribute_statistics_bank_em` | stocks/daily | missing_table | `STOCK_GPZY_DISTRIBUTE_STATISTICS_BANK_EM` | COMPLETED | 核心资产类别 |
| 30 | 771 | `stock_gpzy_distribute_statistics_company_em` | stocks/daily | missing_table | `STOCK_GPZY_DISTRIBUTE_STATISTICS_COMPANY_EM` | COMPLETED | 核心资产类别 |
| 30 | 837 | `stock_individual_info_em` | stocks/daily | missing_table | `STOCK_INDIVIDUAL_INFO_EM` | COMPLETED | 核心资产类别 |
| 30 | 864 | `stock_ipo_benefit_ths` | stocks/daily | missing_table | `STOCK_IPO_BENEFIT_THS` | COMPLETED | 核心资产类别 |
| 30 | 865 | `stock_ipo_declare` | stocks/daily | missing_table | `STOCK_IPO_DECLARE` | COMPLETED | 核心资产类别 |
| 30 | 870 | `stock_jgdy_detail_em` | stocks/daily | missing_table | `STOCK_JGDY_DETAIL_EM` | COMPLETED | 核心资产类别 |
| 30 | 871 | `stock_jgdy_tj_em` | stocks/daily | missing_table | `STOCK_JGDY_TJ_EM` | COMPLETED | 核心资产类别 |
| 30 | 874 | `stock_lh_yyb_capital` | stocks/daily | missing_table | `STOCK_LH_YYB_CAPITAL` | COMPLETED | 核心资产类别 |
| 30 | 876 | `stock_lh_yyb_most` | stocks/daily | missing_table | `STOCK_LH_YYB_MOST` | COMPLETED | 核心资产类别 |
| 30 | 908 | `stock_new_gh_cninfo` | stocks/weekly | missing_table | `STOCK_NEW_GH_CNINFO` | COMPLETED | 核心资产类别 |
| 30 | 911 | `stock_news_main_cx` | stocks/daily | missing_table | `STOCK_NEWS_MAIN_CX` | COMPLETED | 核心资产类别 |
| 30 | 945 | `stock_repurchase_em` | stocks/daily | missing_table | `STOCK_REPURCHASE_EM` | COMPLETED | 核心资产类别 |
