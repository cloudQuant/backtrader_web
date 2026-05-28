#!/usr/bin/env python3
"""Iteration 175 §8.6/§8.7/§8.8 — Alembic migration safety lint.

Scans Alembic revision files added or modified in the current PR and surfaces
warnings (NOT errors) for risky operations:

  a) ``op.add_column`` with ``nullable=False`` and no ``server_default``
  b) ``op.drop_column`` / ``op.drop_table``
  c) ``op.alter_column`` that changes column type (``type_=...`` arg)
  d) ``op.create_index`` without ``postgresql_concurrently=True``

Also verifies that each new migration file has a header comment of the form::

  # alembic-meta: estimated_rows=<N>; lock_kind=<short|long>

within the first 20 lines.

This script *never* fails the build — it only emits warnings via
``::warning`` annotations and a job-summary block. The hard schema-drift
check (check_orm_schema_drift.py) is what actually blocks merges.

Usage::

  python scripts/ci/check_migration_safety.py [--base-ref origin/master]
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_DIR = REPO_ROOT / "src" / "backend" / "alembic" / "versions"

META_REGEX = re.compile(
    r"#\s*alembic-meta:\s*estimated_rows\s*=\s*(\d+)\s*;\s*lock_kind\s*=\s*(short|long)\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Warning:
    file: Path
    line: int
    code: str
    message: str
    suggestion: str = ""


def _changed_migration_files(base_ref: str) -> list[Path]:
    cmd = [
        "git",
        "diff",
        "--name-only",
        "--diff-filter=AM",
        f"{base_ref}...HEAD",
        "--",
        "src/backend/alembic/versions/*.py",
    ]
    try:
        out = subprocess.check_output(cmd, text=True, cwd=REPO_ROOT, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        # Local invocation without git history — fall back to scanning all files.
        return sorted(ALEMBIC_DIR.glob("*.py")) if ALEMBIC_DIR.exists() else []
    paths = [REPO_ROOT / line.strip() for line in out.splitlines() if line.strip().endswith(".py")]
    return [p for p in paths if p.exists()]


def _check_alembic_meta(path: Path) -> Warning | None:
    head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:20])
    if META_REGEX.search(head):
        return None
    return Warning(
        file=path,
        line=1,
        code="missing-alembic-meta",
        message=(
            "missing `# alembic-meta: estimated_rows=<N>; lock_kind=<short|long>` "
            "header comment within first 20 lines"
        ),
        suggestion="add a header line per `docs/how-to/database-migration-playbook.md`.",
    )


def _is_op_call(node: ast.Call, name: str) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute):
        target = func.value
        return func.attr == name and isinstance(target, ast.Name) and target.id == "op"
    return False


def _has_kwarg_truthy(call: ast.Call, key: str) -> bool:
    for kw in call.keywords:
        if kw.arg == key:
            value = kw.value
            if isinstance(value, ast.Constant):
                return bool(value.value)
            return True
    return False


def _has_kwarg(call: ast.Call, key: str) -> bool:
    return any(kw.arg == key for kw in call.keywords)


def _kwarg_value(call: ast.Call, key: str):
    for kw in call.keywords:
        if kw.arg == key:
            return kw.value
    return None


def _check_calls(path: Path) -> list[Warning]:
    text = path.read_text(encoding="utf-8")
    warnings: list[Warning] = []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        warnings.append(Warning(path, exc.lineno or 1, "parse-error", f"syntax: {exc.msg}"))
        return warnings

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # (a) op.add_column with nullable=False and no server_default
        if _is_op_call(node, "add_column"):
            # The Column ctor is the second positional arg of op.add_column,
            # but Column may also be passed as keyword `column=`.
            col_arg = None
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Call):
                col_arg = node.args[1]
            if col_arg is None:
                col_arg = _kwarg_value(node, "column")
            if isinstance(col_arg, ast.Call):
                # nullable=False + no server_default => danger
                nullable = None
                for kw in col_arg.keywords:
                    if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
                        nullable = bool(kw.value.value)
                if nullable is False and not _has_kwarg(col_arg, "server_default"):
                    warnings.append(Warning(
                        file=path,
                        line=node.lineno,
                        code="add-column-not-null-no-default",
                        message="op.add_column with nullable=False and no server_default — table rewrite risk",
                        suggestion="add server_default OR perform 2-step migration (add nullable, backfill, alter to NOT NULL).",
                    ))

        # (b) op.drop_column / op.drop_table
        if _is_op_call(node, "drop_column"):
            warnings.append(Warning(
                file=path, line=node.lineno, code="drop-column",
                message="op.drop_column — irreversible & may break in-flight readers",
                suggestion="prefer 2-step deprecation (stop writing, then remove later).",
            ))
        if _is_op_call(node, "drop_table"):
            warnings.append(Warning(
                file=path, line=node.lineno, code="drop-table",
                message="op.drop_table — irreversible",
                suggestion="rename the table first; remove only after a release boundary.",
            ))

        # (c) op.alter_column with type_=
        if _is_op_call(node, "alter_column") and _has_kwarg(node, "type_"):
            warnings.append(Warning(
                file=path, line=node.lineno, code="alter-column-type",
                message="op.alter_column with type_= changes column type — full-table rewrite on most engines",
                suggestion="use shadow column + dual-write + cutover; never alter type in-place on PG > 100 GB tables.",
            ))

        # (d) op.create_index without postgresql_concurrently=True
        if _is_op_call(node, "create_index") and not _has_kwarg_truthy(node, "postgresql_concurrently"):
            warnings.append(Warning(
                file=path, line=node.lineno, code="index-no-concurrently",
                message="op.create_index without postgresql_concurrently=True — locks the table for writes",
                suggestion="add postgresql_concurrently=True (and run with a connection that supports it).",
            ))

    return warnings


def _emit_summary(warnings: list[Warning]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n### Alembic Migration Safety (175 §8)\n\n")
        if not warnings:
            f.write("_No risky operations detected on this PR's migration changes._\n")
            return
        f.write("| 迁移文件 | 行号 | 危险操作 | 风险描述 | 推荐写法 |\n")
        f.write("|---|---:|---|---|---|\n")
        for w in warnings:
            f.write(
                f"| `{w.file.relative_to(REPO_ROOT)}` | {w.line} | {w.code} | {w.message} | {w.suggestion} |\n"
            )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-ref", default=os.environ.get("BASE_REF", "origin/master"))
    args = p.parse_args()

    files = _changed_migration_files(args.base_ref)
    warnings: list[Warning] = []
    for path in files:
        if (m := _check_alembic_meta(path)) is not None:
            warnings.append(m)
        warnings.extend(_check_calls(path))

    for w in warnings:
        print(
            f"::warning file={w.file.relative_to(REPO_ROOT)},line={w.line}::"
            f"[{w.code}] {w.message} | suggestion: {w.suggestion}"
        )
    _emit_summary(warnings)
    if not warnings:
        print("OK: no risky migration operations detected on this PR")
    else:
        print(f"WARN: {len(warnings)} risky operation(s) flagged (advisory)")
    # Always exit 0 — this is an advisory warning channel.
    return 0


if __name__ == "__main__":
    sys.exit(main())
