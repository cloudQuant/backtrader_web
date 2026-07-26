# ADR-009: Alembic Linear Migration Chain Enforcement

**Status:** Accepted
**Date:** 2026-05-20
**Deciders:** cloud

## Context

The Alembic migration history developed a branching issue: two migrations (`0002_add_ai_trading_logs` and `0002_add_performance_indexes`) both pointed to `0001_baseline` as their `down_revision`, creating two heads. This made `alembic upgrade head` ambiguous and `alembic check` fail in CI.

The root cause was that `0002_add_ai_trading_logs` was created after the `0002→0003→0004` chain already existed, but was incorrectly given `down_revision = "0001_baseline"` instead of pointing to the latest migration.

## Decision

1. **Enforce a single linear chain:** Rename `0002_add_ai_trading_logs` to `0005_add_ai_trading_logs` and set its `down_revision` to `0004_add_composite_listing_indexes`
2. **CI validation:** The existing `scripts/check_alembic_heads.py` script verifies single-head in CI — this caught the issue
3. **Convention:** Migration files are numbered sequentially (`0001`, `0002`, ...) and each must have exactly one `down_revision` pointing to the previous migration
4. **No merge migrations:** Avoid Alembic's `merge` command; instead, fix the chain by renumbering

The final chain: `base → 0001_baseline → 0002_add_performance_indexes → 0003_add_trading_workspace_fields → 0004_add_composite_listing_indexes → 0005_add_ai_trading_logs`

## Consequences

### Positive

- `alembic upgrade head` works unambiguously
- `alembic check` passes in CI
- Clear sequential ordering makes it easy to understand migration history
- No merge migrations to confuse the dependency graph

### Negative

- Renaming a migration file means any database that already applied the old `0002_add_ai_trading_logs` will need manual intervention (update `alembic_version` table)
- Sequential numbering can conflict if multiple developers create migrations simultaneously (mitigated by CI check)

### Neutral

- The migration content (table creation SQL) is unchanged — only the revision ID and down_revision pointer changed
