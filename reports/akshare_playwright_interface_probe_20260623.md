# AkShare Playwright Interface Probe 2026-06-23

Baseline audit:

- Report: `reports/akshare_data_completeness_audit_after_playwright_interface_fixes.json`
- Has data: 1007 / 1047
- Remaining gaps: 40
- Non-API-key gaps: 35
- API-key-only gaps: 5 (`currency_history`, `currency_convert`, `currency_currencies`, `currency_latest`, `currency_time_series`)

## Fixed Locally

- DCE delivery interfaces:
  - `futures_delivery_dce`
  - `futures_delivery_match_dce`
  - `futures_to_spot_dce`
  - `option_hist_dce`
  - `futures_warehouse_receipt_dce`
  - Fix: official challenge/empty HTML now returns stable empty DataFrames with expected columns instead of raising `ValueError` or returning columnless empty frames.
- SGE spot interfaces:
  - `spot_hist_sge`
  - `spot_quotations_sge`
  - `spot_golden_benchmark_sge`
  - `spot_silver_benchmark_sge`
  - Fix: request timeout/retry budget reduced so project calls return structured empty frames before `AKSHARE_CALL_TIMEOUT`.
- Chinascope:
  - `index_news_sentiment_scope`
  - Fix: non-JSON/gateway response now returns an empty DataFrame with expected columns.
- Caixin:
  - `stock_news_main_cx`
  - Fix: DNS/request/JSON errors now return an empty DataFrame with expected columns.
- KQ textile:
  - `index_kq_fz`
  - Fix: request timeout/JSON errors now return an empty DataFrame with the symbol-specific expected columns.
- Eastmoney LCX:
  - `fund_lcx_rank_em`
  - Fix: official `Data:null` response now returns an empty DataFrame with expected columns.
- Oxford-Man project wrapper:
  - `article_oman_rv`
  - Fix: project wrapper now supports AkShare's `Series` return shape by converting non-empty Series to a DataFrame before saving.

## Playwright Results

- DCE official pages/API:
  - Browser opened DCE pages and received HTTP 412/400.
  - Browser challenge execution set `hNUS9DnJtejwS` and `hNUS9DnJtejwT`, but same-origin API retry still returned HTTP 400 with empty response.
  - JSON endpoints `dayQuotes`, `memberDealPosi/batchDownload`, and `wbillWeeklyQuotes` returned HTTP 412 challenge pages.
- SGE:
  - `https://www.sge.com.cn/sjzx/mrhq` timed out in Playwright.
  - `/graph/quotations`, `/graph/Dailyhq`, and `/graph/DayilyJzj` also timed out through Playwright request.
- NetEase 163:
  - Tick page and XLS endpoint returned HTTP 502.
- Eastmoney LCX:
  - Page opened with HTTP 200.
  - Official `GetLcRankList` returned HTTP 200 with `Data:null`, `TotalCount:0`.
- CNInfo:
  - Page opened with HTTP 200.
  - Official `p_sysapi1098` returned HTTP 200 with `records:[]`, `total:0`.
- THS IPO benefit:
  - Page opened with HTTP 200.
  - DOM table row count was 0.
  - Same-origin AJAX returned only table header, no `page_info`, no data rows.
- Caixin:
  - `cxdata.caixin.com` failed DNS resolution.
- Chinascope:
  - Official page navigation failed/interrupted to Chrome error page; API returned non-JSON in direct probe.
- KQ textile:
  - Official page timed out.
- Xincaifu:
  - Old page redirects to current `xcf.cn` path but returns no body content for the historical rank data.
- Bloomberg:
  - Official page returned HTTP 403 robot check.
- Oxford-Man:
  - Official domain failed DNS resolution in Playwright; direct AkShare returns empty Series.
- Hebei air quality:
  - Official app page timed out.
- Endata/Yien:
  - Old artist/video pages redirect to the new generic Endata homepage; old API remains unavailable for these metrics.
- Carbon markets:
  - Beijing carbon returned HTTP 521 security check.
  - CERX domestic/outer pages timed out.
  - HBETS timed out.
  - CNEmission returned HTTP 418 WAF block.
- ChinaMoney swap:
  - Page opened with HTTP 200.
  - Official `IfccHis` returned HTTP 200 but `records:[]` with `rep_code:500`.
- Investing:
  - Official currency page returned HTTP 403 Cloudflare verification.

## Current Unsuccessful Tasks

The remaining task list is in `reports/akshare_gap_priority_after_playwright_interface_fixes.md`. No alternate providers or neighboring metrics were used. The remaining non-API-key tasks are still unsuccessful because the official source pages/APIs are blocked, timed out, DNS-failing, or returning no rows.
