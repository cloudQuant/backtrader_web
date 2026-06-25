# AkShare Remaining Non-API Source Status

Generated after `reports/akshare_gap_priority_after_inventory_fix.json`.

Current audit baseline:

- Has data: 1007 / 1047
- Remaining gaps: 40
- API-key-only gaps excluded from repair scope: `currency_history`, `currency_convert`, `currency_currencies`, `currency_latest`, `currency_time_series`

## Direct Function Probe

No remaining non-API-key AkShare function returned a non-empty DataFrame in the 2026-06-23 probe.

## Local Repairs Applied

- Restored local AkShare export and same-source wrapper for `stock_zh_a_tick_163`.
- Repaired project wrappers for `option_hist_dce`, `futures_dce_position_rank`, `get_dce_rank_table`, `futures_warehouse_receipt_dce`, and `futures_to_spot_dce` so they use recent trade dates/months instead of stale AkShare sample defaults.
- Repaired DCE rank wrappers to flatten AkShare `dict[str, DataFrame]` results before saving.
- Repaired one-day/multi-row table definitions for DCE option, DCE rank, DCE warehouse receipt, DCE futures-to-spot, and NetEase tick scripts so a single `symbol + data_date` key will not collapse valid same-day rows.
- Repaired `xincaifu_rank` project wrapper to try current-year data and recent prior years instead of only the stale 2022 default.
- Verification on 2026-06-23: touched files pass `python -m py_compile`; smoke calls with explicit current dates/months exit cleanly but return empty data because the official source endpoints are still unavailable or publish no rows.

Observed statuses:

- DCE: project-side stale-date, dict-return, and one-day/multi-row save issues have been repaired. Official `www.dce.com.cn` endpoints still return HTTP 412 challenge; Chromium executes the challenge and sets `hNUS9DnJtejwS/T`, but the second official request still returns HTTP 400 with an empty body. Current smoke call for `futures_dce_position_rank(date="20260623")` returned HTTP 412. Affected: `option_hist_dce`, `futures_dce_position_rank`, `futures_to_spot_dce`, `futures_delivery_dce`, `futures_delivery_match_dce`, `futures_warehouse_receipt_dce`, `get_dce_rank_table`.
- SGE: official `www.sge.com.cn/graph/*` endpoints time out from this environment. Affected: `spot_hist_sge`, `spot_quotations_sge`, `spot_golden_benchmark_sge`, `spot_silver_benchmark_sge`.
- CurrencyScoop: requires API key. Affected: `currency_history`, `currency_convert`, `currency_currencies`, `currency_latest`, `currency_time_series`.
- Investing: `cn.investing.com` official page and service endpoints return Cloudflare 403 even in Chromium. Affected: `currency_pair_map`.
- NetEase 163: repaired the local AkShare export and same-source XLS wrapper for `stock_zh_a_tick_163`; current direct and project-script calls now exit cleanly with the expected columns. The official `quotes.money.163.com` tick/history pages and XLS endpoints still return HTTP 502 in this environment, so no rows can be collected yet. Affected: `stock_zh_a_tick_163`.
- Eastmoney fund LCX: official `GetLcRankList` returns `Data:null`, `TotalCount:0`. Affected: `fund_lcx_rank_em`.
- CNInfo IPO review: official `p_sysapi1098` returns `total:0`, `records:[]`; neighboring CNInfo IPO endpoints have data but are different metrics and were not substituted. Affected: `stock_new_gh_cninfo`.
- THS IPO benefit: Chromium can load the official page and same-origin AJAX after chameleon cookie, but the AJAX table body is empty. Affected: `stock_ipo_benefit_ths`.
- Caixin: official `cxdata.caixin.com` cannot resolve in current DNS. Affected: `stock_news_main_cx`.
- Chinascope: official sentiment endpoint returns non-JSON / gateway failure. Affected: `a_share_news_sentiment_index`.
- KQ index: official endpoint times out. Affected: `kq_foreign_trade_index`.
- Xincaifu: project wrapper now tries current and recent prior years instead of only 2022. Old service domain still no longer resolves; current `xcf.cn` page says historical lists should be queried through the official WeChat account during site maintenance. Affected: `xincaifu_rank`.
- Bloomberg: official page is blocked by robot check and AkShare returns an empty DataFrame. Affected: `index_bloomberg_billionaires`.
- Oxford-Man realized library: official page says the Realized Library is no longer available. Affected: `article_oman_rv`.
- Hebei air quality: current AkShare IP/path and historical same-system IP/path both time out. Affected: `air_quality_hebei`.
- Endata/Yien: old official `www.endata.com.cn/API/GetData.ashx` returns HTTP 405; current helper only covers movie box-office metrics, not the same artist/video metrics. Affected: `business_value_artist`, `online_value_artist`, `video_tv`, `video_variety_show`.
- Carbon markets: source endpoints are connection-refused, timed out, WAF/challenge, or network-unreachable depending on market. Affected: `energy_carbon_bj`, `energy_carbon_domestic`, `energy_carbon_eu`, `energy_carbon_gz`, `energy_carbon_hb`, `energy_carbon_sz`.
- ChinaMoney swap curve: repaired local AkShare logic so `macro_china_swap_rate` no longer calls unrelated `bond_china_close_return_map()` first and no longer uses the stale 2023 default window. Current direct and project-script calls now exit cleanly but the official `IfccHis` endpoint still returns no records in this environment. Affected: `macro_china_swap_rate`.

## Repair Boundary

Per the user constraint, no alternate data providers, neighboring metrics, or substitute tables were used. The remaining non-API-key gaps currently require either source-site availability changes, source-site data publication, or a same-source endpoint that has not been found yet.
