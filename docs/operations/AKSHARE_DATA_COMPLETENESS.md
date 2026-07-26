# AkShare Data Completeness Rules

For scheduled AkShare data jobs, the default backfill window must preserve table
completeness:

- If a target table already has data, start from the latest stored date itself,
  not the following day.
- Fetch through the current intended end date, normally today unless the source
  only publishes through an earlier date.
- Re-fetching the latest stored date is expected. Use unique-key upsert or delete
  the overlapping date before insert so duplicate rows do not accumulate.
- If the target table is empty, use the documented full-history start date for
  that source.
- Do not use default symbol/sample limits to make scheduled jobs faster. Empty
  parameters should mean the full configured universe for that task.
