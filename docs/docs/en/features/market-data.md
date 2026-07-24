# Market data and trust

The market-data page separates viewing local data from actively refreshing online quotes. This keeps page loads deterministic when upstream sources are slow and prevents a failed AkShare request from replacing usable data.

## Local first, explicit refresh

- Snapshots, history, coverage, and quality information are read by default from the local MySQL market-data warehouse configured by `AKSHARE_DATA_DATABASE_URL`.
- Choosing an asset type or instrument does not call AkShare.
- Only **Query** makes an online-refresh request; successful online history can be stored in a fill-in cache.
- If the online request fails, does not cover the selected range, or is invalid, MySQL data is retained and the UI shows a readable message without raw database credentials.

## Page behavior

| Behavior | Description |
| --- | --- |
| Instrument memory | The last concrete instrument is remembered separately for each asset type; selections do not leak across types. |
| History order | Newest dates are displayed first. |
| Coverage and quality | The page shows data ranges, gaps, and quality warnings; run preflight checks before a backtest. |
| Snapshot and indicators | Built from currently valid history; invalid online data does not replace local results. |

## Recommended use

1. Check instrument, timeframe, date range, and local coverage first.
2. Click Query only when a fresh online quote is needed, and record the source and date range.
3. If MySQL is unavailable, check warehouse connectivity and grants. The API returns actionable guidance, not server, user, or password details.
4. Store validated data ranges with the strategy configuration in the research workspace for reproducibility.

The application `DATABASE_URL` and the market-warehouse `AKSHARE_DATA_DATABASE_URL` are separate connections. See [Configuration](../reference/configuration.md).
