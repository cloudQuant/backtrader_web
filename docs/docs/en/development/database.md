# Database and data boundaries

The project separates application state from the market-data warehouse so strategy/user data and high-volume market data do not share one responsibility boundary.

## Two connections

| Connection | Configuration | Contents |
| --- | --- | --- |
| Application database | `DATABASE_TYPE`, `DATABASE_URL` | Users, authorization, strategies, versions, backtest tasks, workspaces, portfolios, and audit-related state |
| Market-data warehouse | `AKSHARE_DATA_DATABASE_URL` | AkShare market data, coverage, quality-support data, and online fill-in cache |

The application database supports SQLite, PostgreSQL, and MySQL. SQLite is suitable for local development; teams and production should use managed PostgreSQL or MySQL with backup, access controls, and monitoring.

## Access principles

- The backend uses asynchronous SQLAlchemy sessions and repository/service layers for application data; never concatenate SQL in pages or routes.
- If warehouse reads fail, market-data APIs return general actionable guidance, not a connection string, host, user, or password.
- Use parameterized SQL, least-privilege accounts, and reversible migrations for writes; do not treat runtime auto-create as a production migration process.
- Data synchronization and application-database migration are separate operations and should be tested against backup or non-production data first.

## Bootstrap and migrations

Development may opt into `DB_AUTO_CREATE_SCHEMA` and `DB_AUTO_CREATE_DEFAULT_ADMIN` through `.env`. Production should keep automatic bootstrap off and use the project’s Alembic/operations migration process. Detailed procedures are in `docs/operations/DATABASE_INIT.md` and `docs/how-to/database-migration-playbook.md`.

## Reproducible data

A backtest should be attributable to strategy version, instrument, timeframe, data range, capital, commission, and run time. When online fill-in data is used, record its source and range, and re-check coverage and quality when reproducing results.
