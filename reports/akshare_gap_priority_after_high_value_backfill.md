# AkShare Gap Priority After High Value Backfill

- Source audit: `reports/akshare_data_completeness_audit_after_high_value_backfill.json`
- Remaining gaps: 375
- Has data: 672 / 1047

## Top Remaining Gaps

| Priority | Task | Script | Category | Status | Target | Latest | Reason |
| ---: | ---: | --- | --- | --- | --- | --- | --- |
| 125 | 796 | `stock_hk_profit_forecast_et` | stocks/daily | missing_table | `STOCK_HK_PROFIT_FORECAST_ET` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick, 核心资产类别 |
| 125 | 1003 | `stock_zh_a_disclosure_report_cninfo` | stocks/daily | missing_table | `STOCK_ZH_A_DISCLOSURE_REPORT_CNINFO` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick, 核心资产类别 |
| 120 | 391 | `financial_fund_daily_em` | funds/weekly | empty_table | `FINANCIAL_FUND_DAILY_EM` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick, 核心资产类别 |
| 120 | 392 | `financial_fund_hist_em` | funds/weekly | empty_table | `FINANCIAL_FUND_HIST_EM` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick, 核心资产类别 |
| 115 | 835 | `stock_individual_fund_flow` | stocks/daily | missing_table | `STOCK_INDIVIDUAL_FUND_FLOW` | FAILED: Script stock_individual_fund_flow returned no data and target table stock_individual_fund_flow is empty | 行情历史/分钟/tick, 核心资产类别, 资金流/持仓/榜单 |
| 115 | 893 | `stock_main_fund_flow` | stocks/daily | missing_table | `STOCK_MAIN_FUND_FLOW` | FAILED: Script stock_main_fund_flow returned no data and target table stock_main_fund_flow is empty | 行情历史/分钟/tick, 核心资产类别, 资金流/持仓/榜单 |
| 115 | 904 | `stock_market_fund_flow` | stocks/daily | missing_table | `STOCK_MARKET_FUND_FLOW` | FAILED: Script stock_market_fund_flow returned no data and target table stock_market_fund_flow is empty | 行情历史/分钟/tick, 核心资产类别, 资金流/持仓/榜单 |
| 105 | 680 | `stock_balance_sheet_by_report_delisted_em` | stocks/daily | empty_table | `STOCK_BALANCE_SHEET_BY_REPORT_DELISTED_EM` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 105 | 719 | `stock_concept_fund_flow_hist` | stocks/weekly | missing_table | `STOCK_CONCEPT_FUND_FLOW_HIST` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 资金流/持仓/榜单 |
| 105 | 792 | `stock_hk_hot_rank_em` | stocks/daily | missing_table | `STOCK_HK_HOT_RANK_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 资金流/持仓/榜单 |
| 105 | 793 | `stock_hk_hot_rank_latest_em` | stocks/daily | missing_table | `STOCK_HK_HOT_RANK_LATEST_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 资金流/持仓/榜单 |
| 105 | 953 | `stock_sector_fund_flow_hist` | stocks/weekly | missing_table | `STOCK_SECTOR_FUND_FLOW_HIST` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 资金流/持仓/榜单 |
| 105 | 955 | `stock_sector_fund_flow_summary` | stocks/daily | missing_table | `STOCK_SECTOR_FUND_FLOW_SUMMARY` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 资金流/持仓/榜单 |
| 100 | 703 | `stock_cash_flow_sheet_by_quarterly_em` | stocks/daily | missing_table | `STOCK_CASH_FLOW_SHEET_BY_QUARTERLY_EM` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick |
| 100 | 741 | `stock_financial_analysis_indicator` | stocks/daily | missing_table | `STOCK_FINANCIAL_ANALYSIS_INDICATOR` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick |
| 100 | 912 | `stock_notice_report` | stocks/daily | missing_table | `STOCK_NOTICE_REPORT` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick |
| 100 | 916 | `stock_profit_forecast_em` | stocks/daily | missing_table | `STOCK_PROFIT_FORECAST_EM` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick |
| 100 | 917 | `stock_profit_forecast_ths` | stocks/daily | missing_table | `STOCK_PROFIT_FORECAST_THS` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick |
| 100 | 918 | `stock_profit_sheet_by_quarterly_em` | stocks/daily | missing_table | `STOCK_PROFIT_SHEET_BY_QUARTERLY_EM` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick |
| 100 | 921 | `stock_profit_sheet_by_yearly_em` | stocks/daily | missing_table | `STOCK_PROFIT_SHEET_BY_YEARLY_EM` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick |
| 100 | 946 | `stock_research_report_em` | stocks/daily | missing_table | `STOCK_RESEARCH_REPORT_EM` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick |
| 100 | 997 | `stock_zcfz_bj_em` | stocks/daily | missing_table | `STOCK_ZCFZ_BJ_EM` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick |
| 100 | 1034 | `stock_zh_kcb_report_em` | stocks/daily | missing_table | `STOCK_ZH_KCB_REPORT_EM` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick |
| 95 | 788 | `stock_hk_hist` | stocks/weekly | missing_table | `STOCK_HK_HIST` | FAILED: Script stock_hk_hist returned no data and target table stock_hk_hist is empty | 行情历史/分钟/tick, 核心资产类别, 最新执行已暴露失败原因 |
| 95 | 1007 | `stock_zh_a_hist` | stocks/daily | missing_table | `STOCK_ZH_A_HIST` | FAILED: Script stock_zh_a_hist returned no data and target table stock_zh_a_hist is empty | 行情历史/分钟/tick, 核心资产类别, 最新执行已暴露失败原因 |
| 90 | 399 | `fund_aum_hist_em` | funds/weekly | empty_table | `FUND_AUM_HIST_EM` | FAILED: Script fund_aum_hist_em left no rows and target table fund_aum_hist_em is empty | 行情历史/分钟/tick, 核心资产类别, 已有空表，可能只需修保存/参数 |
| 90 | 510 | `reits_hist_em` | funds/weekly | empty_table | `REITS_HIST_EM` | FAILED: Script reits_hist_em returned no data and target table reits_hist_em is empty | 行情历史/分钟/tick, 核心资产类别, 已有空表，可能只需修保存/参数 |
| 90 | 543 | `futures_index_ccidx` | futures/daily | empty_table | `FUTURES_INDEX_CCIDX` | FAILED: Script futures_index_ccidx returned no data and target table futures_index_ccidx is empty | 行情历史/分钟/tick, 核心资产类别, 已有空表，可能只需修保存/参数 |
| 85 | 627 | `index_global_hist_em` | indexs/weekly | empty_table | `index_global_hist_em` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 已有空表，可能只需修保存/参数 |
| 85 | 640 | `index_zh_a_hist_min_em` | indexs/daily | empty_table | `INDEX_ZH_A_HIST_MIN_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 已有空表，可能只需修保存/参数 |
| 85 | 651 | `stock_zh_index_daily_em` | indexs/weekly | empty_table | `STOCK_ZH_INDEX_DAILY_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 已有空表，可能只需修保存/参数 |
| 85 | 781 | `stock_hk_dividend_payout_em` | stocks/daily | missing_table | `STOCK_HK_DIVIDEND_PAYOUT_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 783 | `stock_hk_fhpx_detail_ths` | stocks/daily | missing_table | `STOCK_HK_FHPX_DETAIL_THS` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 785 | `stock_hk_ggt_components_em` | stocks/daily | missing_table | `STOCK_HK_GGT_COMPONENTS_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 787 | `stock_hk_gxl_lg` | stocks/daily | missing_table | `STOCK_HK_GXL_LG` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 789 | `stock_hk_hist_min_em` | stocks/hourly | missing_table | `STOCK_HK_HIST_MIN_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 794 | `stock_hk_indicator_eniu` | stocks/daily | missing_table | `STOCK_HK_INDICATOR_ENIU` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 984 | `stock_us_hist_min_em` | stocks/hourly | missing_table | `STOCK_US_HIST_MIN_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1000 | `stock_zh_a_cdr_daily` | stocks/daily | missing_table | `STOCK_ZH_A_CDR_DAILY` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1002 | `stock_zh_a_disclosure_relation_cninfo` | stocks/daily | missing_table | `STOCK_ZH_A_DISCLOSURE_RELATION_CNINFO` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1004 | `stock_zh_a_gbjg_em` | stocks/daily | missing_table | `STOCK_ZH_A_GBJG_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1005 | `stock_zh_a_gdhs` | stocks/daily | missing_table | `STOCK_ZH_A_GDHS` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1006 | `stock_zh_a_gdhs_detail_em` | stocks/daily | missing_table | `STOCK_ZH_A_GDHS_DETAIL_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1008 | `stock_zh_a_hist_min_em` | stocks/hourly | missing_table | `STOCK_ZH_A_HIST_MIN_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1009 | `stock_zh_a_hist_pre_min_em` | stocks/hourly | missing_table | `STOCK_ZH_A_HIST_PRE_MIN_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1012 | `stock_zh_a_new` | stocks/daily | missing_table | `STOCK_ZH_A_NEW` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1018 | `stock_zh_a_tick_163` | stocks/daily | missing_table | `STOCK_ZH_A_TICK_163` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1019 | `stock_zh_a_tick_tx_js` | stocks/daily | missing_table | `STOCK_ZH_A_TICK_TX_JS` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1020 | `stock_zh_ab_comparison_em` | stocks/daily | missing_table | `STOCK_ZH_AB_COMPARISON_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1021 | `stock_zh_ah_daily` | stocks/daily | missing_table | `STOCK_ZH_AH_DAILY` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1022 | `stock_zh_ah_name` | stocks/daily | missing_table | `STOCK_ZH_AH_NAME` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1031 | `stock_zh_index_hist_csindex` | stocks/daily | missing_table | `STOCK_ZH_INDEX_HIST_CSINDEX` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 85 | 1032 | `stock_zh_index_value_csindex` | stocks/daily | missing_table | `STOCK_ZH_INDEX_VALUE_CSINDEX` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 80 | 445 | `fund_report_industry_allocation_cninfo` | funds/weekly | missing_table | `FUND_REPORT_INDUSTRY_ALLOCATION_CNINFO` | COMPLETED | 财务/公告/报表, 核心资产类别 |
| 80 | 446 | `fund_report_stock_cninfo` | funds/weekly | missing_table | `FUND_REPORT_STOCK_CNINFO` | COMPLETED | 财务/公告/报表, 核心资产类别 |
| 80 | 455 | `graded_fund_daily_em` | funds/weekly | empty_table | `GRADED_FUND_DAILY_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 已有空表，可能只需修保存/参数 |
| 80 | 456 | `graded_fund_hist_em` | funds/weekly | empty_table | `GRADED_FUND_HIST_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 已有空表，可能只需修保存/参数 |
| 80 | 460 | `money_fund_hist_em` | funds/weekly | empty_table | `MONEY_FUND_HIST_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别, 已有空表，可能只需修保存/参数 |
| 80 | 620 | `index_bloomberg_billionaires` | indexs/daily | missing_table | `INDEX_BLOOMBERG_BILLIONAIRES` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 80 | 621 | `index_bloomberg_billionaires_hist` | indexs/weekly | missing_table | `INDEX_BLOOMBERG_BILLIONAIRES_HIST` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 80 | 639 | `index_zh_a_hist` | indexs/daily | missing_table | `INDEX_ZH_A_HIST` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 80 | 809 | `stock_hot_deal_xq` | stocks/daily | missing_table | `STOCK_HOT_DEAL_XQ` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 810 | `stock_hot_follow_xq` | stocks/daily | missing_table | `STOCK_HOT_FOLLOW_XQ` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 814 | `stock_hot_rank_em` | stocks/daily | missing_table | `STOCK_HOT_RANK_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 817 | `stock_hot_search_baidu` | stocks/daily | missing_table | `STOCK_HOT_SEARCH_BAIDU` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 818 | `stock_hot_tweet_xq` | stocks/daily | missing_table | `STOCK_HOT_TWEET_XQ` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 819 | `stock_hot_up_em` | stocks/daily | missing_table | `STOCK_HOT_UP_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 820 | `stock_hsgt_board_rank_em` | stocks/daily | missing_table | `STOCK_HSGT_BOARD_RANK_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 823 | `stock_hsgt_hist_em` | stocks/daily | missing_table | `STOCK_HSGT_HIST_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 824 | `stock_hsgt_hold_stock_em` | stocks/daily | missing_table | `STOCK_HSGT_HOLD_STOCK_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 825 | `stock_hsgt_individual_detail_em` | stocks/daily | missing_table | `STOCK_HSGT_INDIVIDUAL_DETAIL_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 827 | `stock_hsgt_institution_statistics_em` | stocks/daily | missing_table | `STOCK_HSGT_INSTITUTION_STATISTICS_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 829 | `stock_hsgt_stock_statistics_em` | stocks/daily | missing_table | `STOCK_HSGT_STOCK_STATISTICS_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 878 | `stock_lhb_detail_em` | stocks/daily | missing_table | `STOCK_LHB_DETAIL_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 879 | `stock_lhb_ggtj_sina` | stocks/daily | missing_table | `STOCK_LHB_GGTJ_SINA` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 883 | `stock_lhb_jgstatistic_em` | stocks/daily | missing_table | `STOCK_LHB_JGSTATISTIC_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 889 | `stock_lhb_yyb_detail_em` | stocks/daily | missing_table | `STOCK_LHB_YYB_DETAIL_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 890 | `stock_lhb_yybph_em` | stocks/daily | missing_table | `STOCK_LHB_YYBPH_EM` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 891 | `stock_lhb_yytj_sina` | stocks/daily | missing_table | `STOCK_LHB_YYTJ_SINA` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 899 | `stock_margin_ratio_pa` | stocks/daily | missing_table | `STOCK_MARGIN_RATIO_PA` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 963 | `stock_share_hold_change_bse` | stocks/daily | missing_table | `STOCK_SHARE_HOLD_CHANGE_BSE` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 964 | `stock_share_hold_change_sse` | stocks/daily | missing_table | `STOCK_SHARE_HOLD_CHANGE_SSE` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 965 | `stock_share_hold_change_szse` | stocks/daily | missing_table | `STOCK_SHARE_HOLD_CHANGE_SZSE` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 80 | 966 | `stock_shareholder_change_ths` | stocks/daily | missing_table | `STOCK_SHAREHOLDER_CHANGE_THS` | COMPLETED | 行情历史/分钟/tick, 资金流/持仓/榜单 |
| 75 | 409 | `fund_etf_fund_info_em` | funds/daily | missing_table | `FUND_ETF_FUND_INFO_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 410 | `fund_etf_hist_em` | funds/daily | missing_table | `FUND_ETF_HIST_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 411 | `fund_etf_hist_min_em` | funds/hourly | missing_table | `FUND_ETF_HIST_MIN_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 427 | `fund_lof_hist_em` | funds/daily | missing_table | `FUND_LOF_HIST_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 428 | `fund_lof_hist_min_em` | funds/hourly | missing_table | `FUND_LOF_HIST_MIN_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 465 | `option_cffex_hs300_list_sina` | funds/daily | missing_table | `OPTION_CFFEX_HS300_LIST_SINA` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 468 | `option_cffex_sz50_list_sina` | funds/daily | missing_table | `OPTION_CFFEX_SZ50_LIST_SINA` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 471 | `option_cffex_zz1000_list_sina` | funds/daily | missing_table | `OPTION_CFFEX_ZZ1000_LIST_SINA` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 481 | `option_current_em` | funds/daily | missing_table | `OPTION_CURRENT_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 487 | `option_hist_czce` | funds/weekly | missing_table | `OPTION_HIST_CZCE` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 488 | `option_hist_dce` | funds/weekly | missing_table | `OPTION_HIST_DCE` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 490 | `option_hist_shfe` | funds/weekly | missing_table | `OPTION_HIST_SHFE` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 491 | `option_hist_yearly_czce` | funds/weekly | missing_table | `OPTION_HIST_YEARLY_CZCE` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 495 | `option_minute_em` | funds/hourly | missing_table | `OPTION_MINUTE_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 499 | `option_sse_codes_sina` | funds/daily | missing_table | `OPTION_SSE_CODES_SINA` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 501 | `option_sse_expire_day_sina` | funds/daily | missing_table | `OPTION_SSE_EXPIRE_DAY_SINA` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 503 | `option_sse_list_sina` | funds/daily | missing_table | `OPTION_SSE_LIST_SINA` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 504 | `option_sse_minute_sina` | funds/hourly | missing_table | `OPTION_SSE_MINUTE_SINA` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 529 | `futures_display_main_sina` | futures/daily | missing_table | `FUTURES_DISPLAY_MAIN_SINA` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 536 | `futures_hist_em` | futures/daily | missing_table | `FUTURES_HIST_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 537 | `futures_hist_table_em` | futures/daily | missing_table | `FUTURES_HIST_TABLE_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 541 | `futures_hold_pos_sina` | futures/daily | missing_table | `FUTURES_HOLD_POS_SINA` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 75 | 546 | `futures_settlement_price_sgx` | futures/daily | missing_table | `FUTURES_SETTLEMENT_PRICE_SGX` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 70 | 1 | `bond_buy_back_hist_em` | bonds/daily | missing_table | `BOND_BUY_BACK_HIST_EM` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 70 | 34 | `bond_zh_hs_cov_min` | bonds/daily | missing_table | `BOND_ZH_HS_COV_MIN` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 70 | 35 | `bond_zh_hs_cov_pre_min` | bonds/daily | missing_table | `BOND_ZH_HS_COV_PRE_MIN` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 70 | 220 | `macro_china_trade_balance` | common/daily | missing_table | `MACRO_CHINA_TRADE_BALANCE` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick, 宏观但非交易核心 |
| 70 | 337 | `macro_usa_trade_balance` | common/daily | missing_table | `MACRO_USA_TRADE_BALANCE` | COMPLETED | 财务/公告/报表, 行情历史/分钟/tick, 宏观但非交易核心 |
| 70 | 589 | `a_share_news_sentiment_index` | indexs/weekly | empty_table | `A_SHARE_NEWS_SENTIMENT_INDEX` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 70 | 836 | `stock_individual_fund_flow_rank` | stocks/weekly | missing_table | `STOCK_INDIVIDUAL_FUND_FLOW_RANK` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 65 | 406 | `fund_dividend_rank_em` | funds/weekly | empty_table | `FUND_DIVIDEND_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 65 | 425 | `fund_lcx_rank_em` | funds/weekly | empty_table | `FUND_LCX_RANK_EM` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 65 | 564 | `member_position_rank` | futures/weekly | empty_table | `FUTURES_MEMBER_POSITION_RANK` | COMPLETED | 核心资产类别, 资金流/持仓/榜单, 已有空表，可能只需修保存/参数 |
| 65 | 695 | `stock_board_industry_hist_em` | stocks/daily | empty_table | `STOCK_BOARD_INDUSTRY_HIST_EM` | COMPLETED | 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 65 | 698 | `stock_board_industry_min_em` | stocks/daily | empty_table | `STOCK_BOARD_INDUSTRY_MIN_EM` | COMPLETED | 行情历史/分钟/tick, 已有空表，可能只需修保存/参数 |
| 65 | 795 | `stock_hk_main_board_spot_em` | stocks/hourly | missing_table | `STOCK_HK_MAIN_BOARD_SPOT_EM` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 65 | 799 | `stock_hk_spot` | stocks/hourly | missing_table | `STOCK_HK_SPOT` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 65 | 800 | `stock_hk_spot_em` | stocks/hourly | missing_table | `STOCK_HK_SPOT_EM` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 65 | 987 | `stock_us_spot_em` | stocks/hourly | missing_table | `STOCK_US_SPOT_EM` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 65 | 1014 | `stock_zh_a_spot` | stocks/hourly | missing_table | `STOCK_ZH_A_SPOT` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 65 | 1015 | `stock_zh_a_spot_em` | stocks/hourly | missing_table | `STOCK_ZH_A_SPOT_EM` | COMPLETED | 核心资产类别, 实时/池类数据 |
| 60 | 48 | `amac_fund_abs` | common/daily | missing_table | `AMAC_FUND_ABS` | COMPLETED | 行情历史/分钟/tick, 核心资产类别 |
| 60 | 513 | `czce_to_spot` | futures/weekly | empty_table | `FUTURES_CZCE_TO_SPOT` | COMPLETED | 核心资产类别, 实时/池类数据, 已有空表，可能只需修保存/参数 |
| 60 | 527 | `futures_dce_position_rank` | futures/weekly | missing_table | `FUTURES_DCE_POSITION_RANK` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 60 | 534 | `futures_gfex_position_rank` | futures/weekly | missing_table | `FUTURES_GFEX_POSITION_RANK` | COMPLETED | 核心资产类别, 资金流/持仓/榜单 |
| 60 | 683 | `stock_bid_ask_em` | stocks/daily | missing_table | `STOCK_BID_ASK_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 685 | `stock_board_change_em` | stocks/daily | missing_table | `STOCK_BOARD_CHANGE_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 686 | `stock_board_concept_cons_em` | stocks/daily | missing_table | `STOCK_BOARD_CONCEPT_CONS_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 687 | `stock_board_concept_hist_em` | stocks/daily | missing_table | `STOCK_BOARD_CONCEPT_HIST_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 688 | `stock_board_concept_hist_min_em` | stocks/hourly | missing_table | `STOCK_BOARD_CONCEPT_HIST_MIN_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 696 | `stock_board_industry_hist_min_em` | stocks/hourly | missing_table | `STOCK_BOARD_INDUSTRY_HIST_MIN_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 710 | `stock_changes_em` | stocks/daily | missing_table | `STOCK_CHANGES_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 712 | `stock_comment_detail_scrd_desire_daily_em` | stocks/daily | missing_table | `STOCK_COMMENT_DETAIL_SCRD_DESIRE_DAILY_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 717 | `stock_comment_em` | stocks/daily | missing_table | `STOCK_COMMENT_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 718 | `stock_concept_cons_futu` | stocks/daily | missing_table | `STOCK_CONCEPT_CONS_FUTU` | COMPLETED | 行情历史/分钟/tick |
| 60 | 721 | `stock_cyq_em` | stocks/daily | missing_table | `STOCK_CYQ_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 723 | `stock_dxsyl_em` | stocks/daily | missing_table | `STOCK_DXSYL_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 724 | `stock_dzjy_hygtj` | stocks/daily | missing_table | `STOCK_DZJY_HYGTJ` | COMPLETED | 行情历史/分钟/tick |
| 60 | 725 | `stock_dzjy_hyyybtj` | stocks/daily | missing_table | `STOCK_DZJY_HYYYBTJ` | COMPLETED | 行情历史/分钟/tick |
| 60 | 727 | `stock_dzjy_mrtj` | stocks/daily | missing_table | `STOCK_DZJY_MRTJ` | COMPLETED | 行情历史/分钟/tick |
| 60 | 728 | `stock_dzjy_sctj` | stocks/daily | missing_table | `STOCK_DZJY_SCTJ` | COMPLETED | 行情历史/分钟/tick |
| 60 | 729 | `stock_dzjy_yybph` | stocks/daily | missing_table | `STOCK_DZJY_YYBPH` | COMPLETED | 行情历史/分钟/tick |
| 60 | 730 | `stock_ebs_lg` | stocks/daily | missing_table | `STOCK_EBS_LG` | COMPLETED | 行情历史/分钟/tick |
| 60 | 731 | `stock_esg_hz_sina` | stocks/daily | missing_table | `STOCK_ESG_HZ_SINA` | COMPLETED | 行情历史/分钟/tick |
| 60 | 732 | `stock_esg_msci_sina` | stocks/daily | missing_table | `STOCK_ESG_MSCI_SINA` | COMPLETED | 行情历史/分钟/tick |
| 60 | 733 | `stock_esg_rate_sina` | stocks/daily | missing_table | `STOCK_ESG_RATE_SINA` | COMPLETED | 行情历史/分钟/tick |
| 60 | 735 | `stock_esg_zd_sina` | stocks/daily | missing_table | `STOCK_ESG_ZD_SINA` | COMPLETED | 行情历史/分钟/tick |
| 60 | 738 | `stock_fhps_em` | stocks/daily | missing_table | `STOCK_FHPS_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 756 | `stock_gddh_em` | stocks/daily | missing_table | `STOCK_GDDH_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 757 | `stock_gdfx_free_holding_analyse_em` | stocks/daily | missing_table | `STOCK_GDFX_FREE_HOLDING_ANALYSE_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 758 | `stock_gdfx_free_holding_change_em` | stocks/daily | missing_table | `STOCK_GDFX_FREE_HOLDING_CHANGE_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 759 | `stock_gdfx_free_holding_detail_em` | stocks/daily | missing_table | `STOCK_GDFX_FREE_HOLDING_DETAIL_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 760 | `stock_gdfx_free_holding_statistics_em` | stocks/daily | missing_table | `STOCK_GDFX_FREE_HOLDING_STATISTICS_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 761 | `stock_gdfx_free_holding_teamwork_em` | stocks/daily | missing_table | `STOCK_GDFX_FREE_HOLDING_TEAMWORK_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 763 | `stock_gdfx_holding_analyse_em` | stocks/daily | missing_table | `STOCK_GDFX_HOLDING_ANALYSE_EM` | COMPLETED | 行情历史/分钟/tick |
| 60 | 764 | `stock_gdfx_holding_change_em` | stocks/daily | missing_table | `STOCK_GDFX_HOLDING_CHANGE_EM` | COMPLETED | 行情历史/分钟/tick |
