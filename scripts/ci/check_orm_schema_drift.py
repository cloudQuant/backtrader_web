#!/usr/bin/env python3
"""Iteration 175 §8 — ORM ↔ Alembic schema drift detector.

Workflow:
  1. Apply the full migration chain to a throwaway SQLite DB.
  2. Reflect the resulting schema via SQLAlchemy.
  3. Compare against the application's ORM ``Base.metadata``.
  4. Output a markdown diff table on mismatch (exit 1) or
     ``OK: schema aligned`` on match (exit 0).
  5. Any internal failure (alembic upgrade error, reflect failure, etc.)
     exits 2 with stderr describing the failure.

The script honours a 120-second wall-clock budget. SQLite is used as the
target dialect because it has no external service requirement and matches
what the project's own dev workflow uses.

Comparison rules (Requirement 8.1):
  - tables: by name set
  - columns: by name set per table
  - column types: SQLAlchemy class category (e.g. Integer ≠ BigInteger,
    String(50) == String(100), String != Text)
  - server_default literal differences are ignored
  - indexes: by (name, sorted column tuple)
  - foreign keys: by (src_table.src_col → tgt_table.tgt_col)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "src" / "backend"
TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class Diff:
    kind: str  # 'table' | 'column' | 'column_type' | 'index' | 'foreign_key'
    object_name: str
    expected: str
    actual: str
    note: str = ""


def _run_alembic_upgrade(db_path: Path) -> None:
    env = os.environ.copy()
    # The project's alembic env.py uses ``async_engine_from_config`` which
    # requires an async driver. Default both URLs to ``sqlite+aiosqlite``
    # (the project's default async SQLite driver).
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    env.setdefault("ASYNC_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_SRC,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS - 10,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed (rc={res.returncode}):\n"
            f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        )


def _normalise_type(t: object) -> str:
    """Reduce SQLAlchemy and SQLite-reflected types to logical categories."""
    name = type(t).__name__
    aliases = {
        "BIGINT": "BigInteger",
        "BOOLEAN": "Boolean",
        "CHAR": "String",
        "DATE": "Date",
        "DATETIME": "DateTime",
        "Enum": "String",  # SQLite persists SQLAlchemy enums as strings.
        "FLOAT": "Float",
        "INTEGER": "Integer",
        "NUMERIC": "Numeric",
        "NVARCHAR": "String",
        "REAL": "Float",
        "SMALLINT": "SmallInteger",
        "TEXT": "Text",
        "TIME": "Time",
        "VARCHAR": "String",
    }
    return aliases.get(name, name)


def _compare(expected_md, actual_md) -> list[Diff]:
    diffs: list[Diff] = []
    expected_tables = set(expected_md.tables)
    # Alembic owns this bookkeeping table; it is intentionally not an ORM model.
    actual_tables = set(actual_md.tables) - {"alembic_version"}

    for missing in sorted(expected_tables - actual_tables):
        diffs.append(
            Diff(
                "table", missing, "present", "missing", "expected in ORM, not migrated"
            )
        )
    for extra in sorted(actual_tables - expected_tables):
        diffs.append(Diff("table", extra, "missing", "present", "in DB but not in ORM"))

    for tname in sorted(expected_tables & actual_tables):
        et = expected_md.tables[tname]
        at = actual_md.tables[tname]

        ec = {c.name: c for c in et.columns}
        ac = {c.name: c for c in at.columns}
        for missing in sorted(ec.keys() - ac.keys()):
            diffs.append(Diff("column", f"{tname}.{missing}", "present", "missing"))
        for extra in sorted(ac.keys() - ec.keys()):
            diffs.append(Diff("column", f"{tname}.{extra}", "missing", "present"))

        for cname in sorted(ec.keys() & ac.keys()):
            et_t = _normalise_type(ec[cname].type)
            at_t = _normalise_type(ac[cname].type)
            if et_t != at_t:
                diffs.append(
                    Diff(
                        "column_type",
                        f"{tname}.{cname}",
                        et_t,
                        at_t,
                    )
                )

        # Indexes (best-effort — SQLite reflects implicit FK indexes inconsistently)
        ei = {
            (i.name, tuple(sorted(c.name for c in i.columns)))
            for i in et.indexes
            if i.name
        }
        ai = {
            (i.name, tuple(sorted(c.name for c in i.columns)))
            for i in at.indexes
            if i.name
        }
        for missing in sorted(ei - ai):
            diffs.append(
                Diff("index", f"{tname}.{missing[0]}", str(missing), "missing")
            )
        for extra in sorted(ai - ei):
            diffs.append(Diff("index", f"{tname}.{extra[0]}", "missing", str(extra)))

        # Foreign keys
        ef = {
            (fk.parent.name, fk.column.table.name, fk.column.name)
            for fk in et.foreign_keys
        }
        af = {
            (fk.parent.name, fk.column.table.name, fk.column.name)
            for fk in at.foreign_keys
        }
        for missing in sorted(ef - af):
            diffs.append(
                Diff(
                    "foreign_key",
                    f"{tname}.{missing[0]}",
                    f"{tname}.{missing[0]} → {missing[1]}.{missing[2]}",
                    "missing",
                )
            )
        for extra in sorted(af - ef):
            diffs.append(
                Diff(
                    "foreign_key",
                    f"{tname}.{extra[0]}",
                    "missing",
                    f"{tname}.{extra[0]} → {extra[1]}.{extra[2]}",
                )
            )

    return diffs


def _print_markdown(diffs: list[Diff]) -> None:
    print("| 类型 | 对象名 | 期望 | 实际 | 差异说明 |")
    print("|---|---|---|---|---|")
    for d in diffs:
        print(f"| {d.kind} | {d.object_name} | {d.expected} | {d.actual} | {d.note} |")


def main() -> int:
    sys.path.insert(0, str(BACKEND_SRC))

    tmp_dir = Path(tempfile.mkdtemp(prefix="orm_drift_check_"))
    db_path = tmp_dir / "drift.db"
    try:
        _run_alembic_upgrade(db_path)

        # Lazy imports — only needed after migrations succeed.
        try:
            from sqlalchemy import MetaData, create_engine

            import app.models  # noqa: F401  # Register every ORM model with Base.metadata.
            from app.db.database import Base  # type: ignore
        except Exception as exc:
            print(
                "ERROR: failed to import SQLAlchemy / app.db.base — cannot perform drift check:\n"
                f"  {exc!r}",
                file=sys.stderr,
            )
            return 2

        engine = create_engine(f"sqlite:///{db_path}", future=True)
        actual = MetaData()
        actual.reflect(bind=engine)

        diffs = _compare(Base.metadata, actual)
        if not diffs:
            print("OK: schema aligned")
            return 0
        print(f"FAIL: {len(diffs)} drift(s) detected")
        _print_markdown(diffs)
        return 1
    except subprocess.TimeoutExpired:
        print(
            f"ERROR: alembic upgrade exceeded {TIMEOUT_SECONDS}s budget",
            file=sys.stderr,
        )
        return 2
    except Exception:
        print("ERROR: drift check failed:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
