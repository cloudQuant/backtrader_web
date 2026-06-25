# AkShare Data Completeness Audit

- Generated: 2026-06-22T07:38:23.976579+00:00
- TODO tasks: 1047 ({'done': 1040, 'failed': 7})
- Physical tables: 888 total, 847 non-empty, 41 empty
- Task data status: {'has_data': 843, 'rows_after_zero_but_physical_data': 671, 'missing_table': 163, 'checked_without_data': 197, 'empty_table': 41}
- Rows-after-zero but physical data exists: 671
- Checked tasks without physical data: 197

## Category Breakdown

| Category | Has Data | Empty Table | Missing Table | Checked Without Data | Rows After Zero But Data |
| --- | ---: | ---: | ---: | ---: | ---: |
| bonds | 36 | 1 | 2 | 3 | 33 |
| common | 256 | 3 | 88 | 91 | 249 |
| funds | 102 | 16 | 7 | 23 | 82 |
| futures | 46 | 10 | 7 | 17 | 37 |
| indexs | 82 | 9 | 2 | 10 | 82 |
| stocks | 321 | 2 | 57 | 53 | 188 |

## First Missing Or Empty Tasks

| Task | Script | Category | Status | Target | Matched Table | Rows | Latest Execution |
| ---: | --- | --- | --- | --- | --- | ---: | --- |
| 34 | `bond_zh_hs_cov_min` | bonds/daily | missing_table | `BOND_ZH_HS_COV_MIN` | `` |  | COMPLETED rows_after=0 |
| 35 | `bond_zh_hs_cov_pre_min` | bonds/daily | missing_table | `BOND_ZH_HS_COV_PRE_MIN` | `` |  | COMPLETED rows_after=0 |
| 19 | `bond_info_cm` | bonds/weekly | empty_table | `BOND_INFO_CM` | `BOND_INFO_CM` | 0 | COMPLETED rows_after=0 |
| 41 | `air_quality_hebei` | common/daily | missing_table | `AIR_QUALITY_HEBEI` | `` |  | COMPLETED rows_after=0 |
| 44 | `air_quality_watch_point` | common/daily | missing_table | `AIR_QUALITY_WATCH_POINT` | `` |  | COMPLETED rows_after=0 |
| 46 | `akshare_catalog_endpoint` | common/daily | missing_table | `akshare_catalog_endpoint` | `` |  | COMPLETED rows_after=0 |
| 48 | `amac_fund_abs` | common/daily | missing_table | `AMAC_FUND_ABS` | `` |  | COMPLETED rows_after=0 |
| 63 | `article_oman_rv` | common/daily | missing_table | `ARTICLE_OMAN_RV` | `` |  | COMPLETED rows_after=0 |
| 64 | `article_rlab_rv` | common/daily | missing_table | `ARTICLE_RLAB_RV` | `` |  | COMPLETED rows_after=0 |
| 66 | `business_value_artist` | common/daily | missing_table | `BUSINESS_VALUE_ARTIST` | `` |  | COMPLETED rows_after=0 |
| 74 | `cost_living` | common/daily | missing_table | `COST_LIVING` | `` |  | COMPLETED rows_after=0 |
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
| 95 | `forex_hist_em` | common/daily | empty_table | `FOREX_HIST_EM` | `FOREX_HIST_EM` | 0 | COMPLETED rows_after=0 |
| 106 | `get_receipt` | common/daily | missing_table | `GET_RECEIPT` | `` |  | COMPLETED rows_after=0 |
| 107 | `get_roll_yield` | common/daily | missing_table | `GET_ROLL_YIELD` | `` |  | COMPLETED rows_after=0 |
| 124 | `macro_bank_english_interest_rate` | common/daily | missing_table | `MACRO_BANK_ENGLISH_INTEREST_RATE` | `` |  | COMPLETED rows_after=0 |
| 147 | `macro_china_bond_public` | common/daily | missing_table | `MACRO_CHINA_BOND_PUBLIC` | `` |  | COMPLETED rows_after=0 |
| 186 | `macro_china_insurance` | common/daily | missing_table | `MACRO_CHINA_INSURANCE` | `` |  | COMPLETED rows_after=0 |
| 197 | `macro_china_nbs_nation` | common/daily | empty_table | `MACRO_CHINA_NBS_NATION` | `MACRO_CHINA_NBS_NATION` | 0 | COMPLETED rows_after=0 |
| 198 | `macro_china_nbs_region` | common/daily | empty_table | `MACRO_CHINA_NBS_REGION` | `MACRO_CHINA_NBS_REGION` | 0 | COMPLETED rows_after=0 |
| 211 | `macro_china_retail_price_index` | common/daily | missing_table | `MACRO_CHINA_RETAIL_PRICE_INDEX` | `` |  | COMPLETED rows_after=0 |
| 216 | `macro_china_society_traffic_volume` | common/daily | missing_table | `MACRO_CHINA_SOCIETY_TRAFFIC_VOLUME` | `` |  | COMPLETED rows_after=0 |
| 219 | `macro_china_swap_rate` | common/daily | missing_table | `MACRO_CHINA_SWAP_RATE` | `` |  | COMPLETED rows_after=0 |
| 221 | `macro_china_urban_unemployment` | common/daily | missing_table | `MACRO_CHINA_URBAN_UNEMPLOYMENT` | `` |  | COMPLETED rows_after=0 |
| 228 | `macro_cons_gold` | common/daily | missing_table | `MACRO_CONS_GOLD` | `` |  | COMPLETED rows_after=0 |
| 229 | `macro_cons_opec_month` | common/daily | missing_table | `MACRO_CONS_OPEC_MONTH` | `` |  | COMPLETED rows_after=0 |
| 230 | `macro_cons_silver` | common/daily | missing_table | `MACRO_CONS_SILVER` | `` |  | COMPLETED rows_after=0 |
| 232 | `macro_euro_cpi_yoy` | common/daily | missing_table | `MACRO_EURO_CPI_YOY` | `` |  | COMPLETED rows_after=0 |
| 240 | `macro_euro_ppi_mom` | common/daily | missing_table | `MACRO_EURO_PPI_MOM` | `` |  | COMPLETED rows_after=0 |
| 256 | `macro_global_sox_index` | common/daily | missing_table | `MACRO_GLOBAL_SOX_INDEX` | `` |  | COMPLETED rows_after=0 |
| 267 | `macro_shipping_bdi` | common/daily | missing_table | `MACRO_SHIPPING_BDI` | `` |  | COMPLETED rows_after=0 |
| 268 | `macro_shipping_bpi` | common/daily | missing_table | `MACRO_SHIPPING_BPI` | `` |  | COMPLETED rows_after=0 |
| 291 | `macro_usa_api_crude_stock` | common/daily | missing_table | `MACRO_USA_API_CRUDE_STOCK` | `` |  | COMPLETED rows_after=0 |
| 294 | `macro_usa_cb_consumer_confidence` | common/daily | missing_table | `MACRO_USA_CB_CONSUMER_CONFIDENCE` | `` |  | COMPLETED rows_after=0 |
| 301 | `macro_usa_core_pce_price` | common/daily | missing_table | `MACRO_USA_CORE_PCE_PRICE` | `` |  | COMPLETED rows_after=0 |
| 308 | `macro_usa_eia_crude_rate` | common/daily | missing_table | `MACRO_USA_EIA_CRUDE_RATE` | `` |  | COMPLETED rows_after=0 |
| 309 | `macro_usa_exist_home_sales` | common/daily | missing_table | `MACRO_USA_EXIST_HOME_SALES` | `` |  | COMPLETED rows_after=0 |
| 314 | `macro_usa_house_starts` | common/daily | missing_table | `MACRO_USA_HOUSE_STARTS` | `` |  | COMPLETED rows_after=0 |
| 316 | `macro_usa_industrial_production` | common/daily | missing_table | `MACRO_USA_INDUSTRIAL_PRODUCTION` | `` |  | COMPLETED rows_after=0 |
| 317 | `macro_usa_initial_jobless` | common/daily | missing_table | `MACRO_USA_INITIAL_JOBLESS` | `` |  | COMPLETED rows_after=0 |
| 319 | `macro_usa_ism_pmi` | common/daily | missing_table | `MACRO_USA_ISM_PMI` | `` |  | COMPLETED rows_after=0 |
| 322 | `macro_usa_michigan_consumer_sentiment` | common/daily | missing_table | `MACRO_USA_MICHIGAN_CONSUMER_SENTIMENT` | `` |  | COMPLETED rows_after=0 |
| 324 | `macro_usa_new_home_sales` | common/daily | missing_table | `MACRO_USA_NEW_HOME_SALES` | `` |  | COMPLETED rows_after=0 |
| 328 | `macro_usa_personal_spending` | common/daily | missing_table | `MACRO_USA_PERSONAL_SPENDING` | `` |  | COMPLETED rows_after=0 |
| 340 | `migration_area_baidu` | common/daily | missing_table | `MIGRATION_AREA_BAIDU` | `` |  | COMPLETED rows_after=0 |
| 342 | `movie_boxoffice_cinema_daily` | common/daily | missing_table | `MOVIE_BOXOFFICE_CINEMA_DAILY` | `` |  | COMPLETED rows_after=0 |
| 344 | `movie_boxoffice_daily` | common/daily | missing_table | `MOVIE_BOXOFFICE_DAILY` | `` |  | COMPLETED rows_after=0 |
| 348 | `movie_boxoffice_yearly` | common/daily | missing_table | `MOVIE_BOXOFFICE_YEARLY` | `` |  | COMPLETED rows_after=0 |
| 349 | `movie_boxoffice_yearly_first_week` | common/daily | missing_table | `MOVIE_BOXOFFICE_YEARLY_FIRST_WEEK` | `` |  | COMPLETED rows_after=0 |
| 357 | `online_value_artist` | common/daily | missing_table | `ONLINE_VALUE_ARTIST` | `` |  | COMPLETED rows_after=0 |
| 384 | `video_tv` | common/daily | missing_table | `VIDEO_TV` | `` |  | COMPLETED rows_after=0 |
| 385 | `video_variety_show` | common/daily | missing_table | `VIDEO_VARIETY_SHOW` | `` |  | COMPLETED rows_after=0 |
| 100 | `fx_quote_baidu` | common/hourly | missing_table | `FX_QUOTE_BAIDU` | `` |  | COMPLETED rows_after=0 |
| 346 | `movie_boxoffice_realtime` | common/hourly | missing_table | `MOVIE_BOXOFFICE_REALTIME` | `` |  | COMPLETED rows_after=0 |
| 367 | `spot_golden_benchmark_sge` | common/hourly | missing_table | `SPOT_GOLDEN_BENCHMARK_SGE` | `` |  | COMPLETED rows_after=0 |
| 368 | `spot_hist_sge` | common/hourly | missing_table | `SPOT_HIST_SGE` | `` |  | COMPLETED rows_after=0 |
| 372 | `spot_hog_three_way_soozhu` | common/hourly | missing_table | `SPOT_HOG_THREE_WAY_SOOZHU` | `` |  | COMPLETED rows_after=0 |
| 373 | `spot_hog_year_trend_soozhu` | common/hourly | missing_table | `SPOT_HOG_YEAR_TREND_SOOZHU` | `` |  | COMPLETED rows_after=0 |
| 374 | `spot_mixed_feed_soozhu` | common/hourly | missing_table | `SPOT_MIXED_FEED_SOOZHU` | `` |  | COMPLETED rows_after=0 |
| 377 | `spot_quotations_sge` | common/hourly | missing_table | `SPOT_QUOTATIONS_SGE` | `` |  | COMPLETED rows_after=0 |
| 378 | `spot_silver_benchmark_sge` | common/hourly | missing_table | `SPOT_SILVER_BENCHMARK_SGE` | `` |  | COMPLETED rows_after=0 |
| 345 | `movie_boxoffice_monthly` | common/monthly | missing_table | `MOVIE_BOXOFFICE_MONTHLY` | `` |  | COMPLETED rows_after=0 |
| 42 | `air_quality_hist` | common/weekly | missing_table | `AIR_QUALITY_HIST` | `` |  | COMPLETED rows_after=0 |
| 47 | `amac_aoin_info` | common/weekly | missing_table | `AMAC_AOIN_INFO` | `` |  | COMPLETED rows_after=0 |
| 49 | `amac_fund_account_info` | common/weekly | missing_table | `AMAC_FUND_ACCOUNT_INFO` | `` |  | COMPLETED rows_after=0 |
| 50 | `amac_fund_info` | common/weekly | missing_table | `AMAC_FUND_INFO` | `` |  | COMPLETED rows_after=0 |
| 51 | `amac_fund_sub_info` | common/weekly | missing_table | `AMAC_FUND_SUB_INFO` | `` |  | COMPLETED rows_after=0 |
| 52 | `amac_futures_info` | common/weekly | missing_table | `AMAC_FUTURES_INFO` | `` |  | COMPLETED rows_after=0 |
| 53 | `amac_manager_cancelled_info` | common/weekly | missing_table | `AMAC_MANAGER_CANCELLED_INFO` | `` |  | COMPLETED rows_after=0 |
| 54 | `amac_manager_classify_info` | common/weekly | missing_table | `AMAC_MANAGER_CLASSIFY_INFO` | `` |  | COMPLETED rows_after=0 |

## Top Orphan Non-Empty Tables

| Table | Rows | Date Column | Min | Max |
| --- | ---: | --- | --- | --- |
| `ETF_REALTIME_QUOTE_EM` | 1184 | BASEDATE | 2025-07-12T11:30:07 | 2025-07-12T11:30:07 |
| `LOF_REALTIME_QUOTE_EM` | 785 | BASEDATE | 2025-07-12T10:35:37 | 2025-07-25T22:37:38 |
| `STOCK_BOARD_INDUSTRY_EM` | 496 | BASEDATE | 2026-06-22 | 2026-06-22 |
| `akcat_air_city_table` | 168 |  |  |  |
