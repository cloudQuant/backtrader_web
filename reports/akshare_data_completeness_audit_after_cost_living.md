# AkShare Data Completeness Audit

- Generated: 2026-06-22T19:33:53.424815+00:00
- TODO tasks: 1047 ({'done': 1047})
- Physical tables: 1007 total, 997 non-empty, 10 empty
- Task data status: {'has_data': 993, 'rows_after_zero_but_physical_data': 672, 'missing_table': 44, 'checked_without_data': 54, 'empty_table': 10}
- Rows-after-zero but physical data exists: 672
- Checked tasks without physical data: 54

## Category Breakdown

| Category | Has Data | Empty Table | Missing Table | Checked Without Data | Rows After Zero But Data |
| --- | ---: | ---: | ---: | ---: | ---: |
| bonds | 39 | 0 | 0 | 0 | 33 |
| common | 310 | 2 | 35 | 37 | 250 |
| funds | 122 | 2 | 1 | 3 | 82 |
| futures | 56 | 4 | 3 | 7 | 37 |
| indexs | 90 | 2 | 1 | 3 | 82 |
| stocks | 376 | 0 | 4 | 4 | 188 |

## First Missing Or Empty Tasks

| Task | Script | Category | Status | Target | Matched Table | Rows | Latest Execution |
| ---: | --- | --- | --- | --- | --- | ---: | --- |
| 41 | `air_quality_hebei` | common/daily | missing_table | `AIR_QUALITY_HEBEI` | `` |  | COMPLETED rows_after=0 |
| 63 | `article_oman_rv` | common/daily | missing_table | `ARTICLE_OMAN_RV` | `` |  | COMPLETED rows_after=0 |
| 66 | `business_value_artist` | common/daily | missing_table | `BUSINESS_VALUE_ARTIST` | `` |  | COMPLETED rows_after=0 |
| 80 | `currency_convert` | common/daily | missing_table | `CURRENCY_CONVERT` | `` |  | COMPLETED rows_after=0 |
| 81 | `currency_currencies` | common/daily | missing_table | `CURRENCY_CURRENCIES` | `` |  | COMPLETED rows_after=0 |
| 83 | `currency_latest` | common/daily | missing_table | `CURRENCY_LATEST` | `` |  | COMPLETED rows_after=0 |
| 84 | `currency_pair_map` | common/daily | missing_table | `CURRENCY_PAIR_MAP` | `` |  | COMPLETED rows_after=0 |
| 85 | `currency_time_series` | common/daily | missing_table | `CURRENCY_TIME_SERIES` | `` |  | COMPLETED rows_after=0 |
| 86 | `energy_carbon_bj` | common/daily | missing_table | `ENERGY_CARBON_BJ` | `` |  | COMPLETED rows_after=0 |
| 87 | `energy_carbon_domestic` | common/daily | missing_table | `ENERGY_CARBON_DOMESTIC` | `` |  | COMPLETED rows_after=0 |
| 88 | `energy_carbon_eu` | common/daily | missing_table | `ENERGY_CARBON_EU` | `` |  | COMPLETED rows_after=0 |
| 89 | `energy_carbon_gz` | common/daily | missing_table | `ENERGY_CARBON_GZ` | `` |  | COMPLETED rows_after=0 |
| 90 | `energy_carbon_hb` | common/daily | missing_table | `ENERGY_CARBON_HB` | `` |  | COMPLETED rows_after=0 |
| 91 | `energy_carbon_sz` | common/daily | missing_table | `ENERGY_CARBON_SZ` | `` |  | COMPLETED rows_after=0 |
| 197 | `macro_china_nbs_nation` | common/daily | empty_table | `MACRO_CHINA_NBS_NATION` | `MACRO_CHINA_NBS_NATION` | 0 | COMPLETED rows_after=0 |
| 198 | `macro_china_nbs_region` | common/daily | empty_table | `MACRO_CHINA_NBS_REGION` | `MACRO_CHINA_NBS_REGION` | 0 | COMPLETED rows_after=0 |
| 219 | `macro_china_swap_rate` | common/daily | missing_table | `MACRO_CHINA_SWAP_RATE` | `` |  | COMPLETED rows_after=0 |
| 221 | `macro_china_urban_unemployment` | common/daily | missing_table | `MACRO_CHINA_URBAN_UNEMPLOYMENT` | `` |  | COMPLETED rows_after=0 |
| 342 | `movie_boxoffice_cinema_daily` | common/daily | missing_table | `MOVIE_BOXOFFICE_CINEMA_DAILY` | `` |  | COMPLETED rows_after=0 |
| 344 | `movie_boxoffice_daily` | common/daily | missing_table | `MOVIE_BOXOFFICE_DAILY` | `` |  | COMPLETED rows_after=0 |
| 348 | `movie_boxoffice_yearly` | common/daily | missing_table | `MOVIE_BOXOFFICE_YEARLY` | `` |  | COMPLETED rows_after=0 |
| 349 | `movie_boxoffice_yearly_first_week` | common/daily | missing_table | `MOVIE_BOXOFFICE_YEARLY_FIRST_WEEK` | `` |  | COMPLETED rows_after=0 |
| 357 | `online_value_artist` | common/daily | missing_table | `ONLINE_VALUE_ARTIST` | `` |  | COMPLETED rows_after=0 |
| 384 | `video_tv` | common/daily | missing_table | `VIDEO_TV` | `` |  | COMPLETED rows_after=0 |
| 385 | `video_variety_show` | common/daily | missing_table | `VIDEO_VARIETY_SHOW` | `` |  | COMPLETED rows_after=0 |
| 346 | `movie_boxoffice_realtime` | common/hourly | missing_table | `MOVIE_BOXOFFICE_REALTIME` | `` |  | COMPLETED rows_after=0 |
| 367 | `spot_golden_benchmark_sge` | common/hourly | missing_table | `SPOT_GOLDEN_BENCHMARK_SGE` | `` |  | COMPLETED rows_after=0 |
| 368 | `spot_hist_sge` | common/hourly | missing_table | `SPOT_HIST_SGE` | `` |  | COMPLETED rows_after=0 |
| 377 | `spot_quotations_sge` | common/hourly | missing_table | `SPOT_QUOTATIONS_SGE` | `` |  | COMPLETED rows_after=0 |
| 378 | `spot_silver_benchmark_sge` | common/hourly | missing_table | `SPOT_SILVER_BENCHMARK_SGE` | `` |  | COMPLETED rows_after=0 |
| 345 | `movie_boxoffice_monthly` | common/monthly | missing_table | `MOVIE_BOXOFFICE_MONTHLY` | `` |  | COMPLETED rows_after=0 |
| 42 | `air_quality_hist` | common/weekly | missing_table | `AIR_QUALITY_HIST` | `` |  | COMPLETED rows_after=0 |
| 82 | `currency_history` | common/weekly | missing_table | `CURRENCY_HISTORY` | `` |  | COMPLETED rows_after=0 |
| 104 | `get_dce_rank_table` | common/weekly | missing_table | `GET_DCE_RANK_TABLE` | `` |  | COMPLETED rows_after=0 |
| 343 | `movie_boxoffice_cinema_weekly` | common/weekly | missing_table | `MOVIE_BOXOFFICE_CINEMA_WEEKLY` | `` |  | COMPLETED rows_after=0 |
| 347 | `movie_boxoffice_weekly` | common/weekly | missing_table | `MOVIE_BOXOFFICE_WEEKLY` | `` |  | COMPLETED rows_after=0 |
| 386 | `xincaifu_rank` | common/weekly | missing_table | `XINCAIFU_RANK` | `` |  | COMPLETED rows_after=0 |
| 391 | `financial_fund_daily_em` | funds/weekly | empty_table | `FINANCIAL_FUND_DAILY_EM` | `FINANCIAL_FUND_DAILY_EM` | 0 | COMPLETED rows_after=0 |
| 425 | `fund_lcx_rank_em` | funds/weekly | empty_table | `FUND_LCX_RANK_EM` | `FUND_LCX_RANK_EM` | 0 | COMPLETED rows_after=0 |
| 488 | `option_hist_dce` | funds/weekly | missing_table | `OPTION_HIST_DCE` | `` |  | COMPLETED rows_after=0 |
| 554 | `futures_to_spot_dce` | futures/hourly | missing_table | `FUTURES_TO_SPOT_DCE` | `` |  | COMPLETED rows_after=0 |
| 516 | `dce_delivery_data` | futures/monthly | empty_table | `FUTURES_DELIVERY_DCE` | `FUTURES_DELIVERY_DCE` | 0 | COMPLETED rows_after=0 |
| 517 | `dce_delivery_match` | futures/weekly | empty_table | `FUTURES_DELIVERY_MATCH_DCE` | `FUTURES_DELIVERY_MATCH_DCE` | 0 | COMPLETED rows_after=0 |
| 527 | `futures_dce_position_rank` | futures/weekly | missing_table | `FUTURES_DCE_POSITION_RANK` | `` |  | COMPLETED rows_after=0 |
| 557 | `futures_warehouse_receipt_dce` | futures/weekly | missing_table | `FUTURES_WAREHOUSE_RECEIPT_DCE` | `` |  | COMPLETED rows_after=0 |
| 563 | `inventory_data` | futures/weekly | empty_table | `FUTURES_INVENTORY_DATA` | `FUTURES_INVENTORY_DATA` | 0 | COMPLETED rows_after=0 |
| 574 | `warehouse_receipt_dce` | futures/weekly | empty_table | `FUTURES_DCE_WAREHOUSE_RECEIPT` | `FUTURES_DCE_WAREHOUSE_RECEIPT` | 0 | COMPLETED rows_after=0 |
| 620 | `index_bloomberg_billionaires` | indexs/daily | missing_table | `INDEX_BLOOMBERG_BILLIONAIRES` | `` |  | COMPLETED rows_after=0 |
| 589 | `a_share_news_sentiment_index` | indexs/weekly | empty_table | `A_SHARE_NEWS_SENTIMENT_INDEX` | `A_SHARE_NEWS_SENTIMENT_INDEX` | 0 | COMPLETED rows_after=0 |
| 643 | `kq_foreign_trade_index` | indexs/weekly | empty_table | `KQ_FOREIGN_TRADE_INDEX` | `KQ_FOREIGN_TRADE_INDEX` | 0 | COMPLETED rows_after=0 |
| 864 | `stock_ipo_benefit_ths` | stocks/daily | missing_table | `STOCK_IPO_BENEFIT_THS` | `` |  | COMPLETED rows_after=0 |
| 911 | `stock_news_main_cx` | stocks/daily | missing_table | `STOCK_NEWS_MAIN_CX` | `` |  | COMPLETED rows_after=0 |
| 1018 | `stock_zh_a_tick_163` | stocks/daily | missing_table | `STOCK_ZH_A_TICK_163` | `` |  | COMPLETED rows_after=0 |
| 908 | `stock_new_gh_cninfo` | stocks/weekly | missing_table | `STOCK_NEW_GH_CNINFO` | `` |  | COMPLETED rows_after=0 |

## Top Orphan Non-Empty Tables

| Table | Rows | Date Column | Min | Max |
| --- | ---: | --- | --- | --- |
| `ETF_REALTIME_QUOTE_EM` | 1184 | BASEDATE | 2025-07-12T11:30:07 | 2025-07-12T11:30:07 |
| `LOF_REALTIME_QUOTE_EM` | 785 | BASEDATE | 2025-07-12T10:35:37 | 2025-07-25T22:37:38 |
| `STOCK_BOARD_INDUSTRY_EM` | 496 | BASEDATE | 2026-06-22 | 2026-06-22 |
| `akcat_air_city_table` | 168 |  |  |  |
