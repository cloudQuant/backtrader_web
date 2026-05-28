# Database Migration Playbook

> Iteration 175 §8.9 — operating manual for safe Alembic migrations against
> PostgreSQL production. The CI gate is two-tier:
>
> 1. `scripts/ci/check_orm_schema_drift.py` — **blocking**: ORM and migration
>    chain must agree.
> 2. `scripts/ci/check_migration_safety.py` — **advisory**: flags risky
>    operations as warnings and emits a markdown table to job summary.

## Long-lock & full-table-scan risks: identification, recommended writes, and PR review checklist

### Hazard quick-reference

| # | Operation | Why it is dangerous | Recommended substitute |
|---|---|---|---|
| 1 | `op.add_column(<col>, nullable=False)` without `server_default` | PG must rewrite every row to populate the new column → ACCESS EXCLUSIVE lock for minutes-to-hours on large tables. | 2-step migration: add nullable → backfill in batches → `ALTER COLUMN ... SET NOT NULL`. |
| 2 | `op.drop_column` / `op.drop_table` | Loss is irreversible; in-flight readers and replicas can break mid-deploy. | First **stop writing** to the column/table and ship that release; remove only after a stable release boundary. |
| 3 | `op.alter_column(type_=<NewType>)` | PG rewrites the table for most type changes (varchar(50)→text excepted). | Add a shadow column with the new type → dual-write → backfill → cutover reads → drop the old column. |
| 4 | `op.create_index` without `postgresql_concurrently=True` | Locks the table for writes for the duration of the index build. | Always pass `postgresql_concurrently=True` and run from a connection that allows it. |

### PG recommended write — examples

#### `SET lock_timeout` for inline migrations

```python
def upgrade() -> None:
    # alembic-meta: estimated_rows=10000000; lock_kind=long
    bind = op.get_bind()
    bind.execute(sa.text("SET lock_timeout = '5s'"))
    op.add_column(
        "users",
        sa.Column("region", sa.String(8), nullable=True),
    )
```

#### `CREATE INDEX CONCURRENTLY`

```python
def upgrade() -> None:
    # alembic-meta: estimated_rows=50000000; lock_kind=short
    op.create_index(
        "ix_orders_user_id",
        "orders",
        ["user_id"],
        postgresql_concurrently=True,
    )
```

> Note: `postgresql_concurrently=True` requires the migration to run **outside
> a transaction**. Configure the env per
> https://alembic.sqlalchemy.org/en/latest/cookbook.html#run-multiple-alembic-commands-in-one-connection.

#### Batched backfill

```python
def upgrade() -> None:
    # alembic-meta: estimated_rows=200000000; lock_kind=long
    bind = op.get_bind()
    while True:
        result = bind.execute(sa.text("""
            UPDATE users
               SET region = COALESCE(region, 'unknown')
             WHERE id IN (
                 SELECT id FROM users WHERE region IS NULL ORDER BY id LIMIT 5000
             )
        """))
        if result.rowcount == 0:
            break
```

### Reading `check_migration_safety.py` output

Each warning emitted in CI follows this pattern:

```
::warning file=src/backend/alembic/versions/<rev>.py,line=<n>::[<code>] <description> | suggestion: <fix>
```

The same data is rendered as a table in the job summary under "Alembic
Migration Safety (175 §8)". Codes:

| Code | Severity | What to do |
|---|---|---|
| `add-column-not-null-no-default` | high — likely table rewrite | switch to 2-step add-then-set-not-null. |
| `drop-column` / `drop-table` | high — irreversible | confirm the column/table is not referenced anywhere; defer if uncertain. |
| `alter-column-type` | high — table rewrite | use shadow column pattern. |
| `index-no-concurrently` | medium — write lock | add `postgresql_concurrently=True`. |
| `missing-alembic-meta` | low — observability gap | add the header comment. |

### PR review checklist (≥ 5 items)

- [ ] Migration carries an `# alembic-meta:` header within the first 20 lines, with realistic `estimated_rows` and a `lock_kind` of `short` or `long`.
- [ ] No code path drops or mutates a production column without an immediately-prior release that stopped writing it.
- [ ] All new indexes on tables with > 1 M rows pass `postgresql_concurrently=True`.
- [ ] Schema drift check (`scripts/ci/check_orm_schema_drift.py`) is green; any reported diff is explained in the PR body.
- [ ] Risk warnings (`check_migration_safety.py`) are reviewed; each flagged operation has an explicit comment in the migration explaining why it is acceptable.
- [ ] Long-running migrations (`lock_kind=long`) carry a `SET lock_timeout` and / or batching strategy.

## How to update this document

Append new hazard categories above whenever `check_migration_safety.py`
gains a new rule. Keep examples runnable — copy them from a real merged
migration when possible.
