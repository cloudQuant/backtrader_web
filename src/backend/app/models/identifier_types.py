"""Portable SQL types for protocol identifiers with exact comparison semantics."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.dialects import mysql, postgresql


def exact_identifier_string(length: int) -> String:
    """Return a bytewise type for identifiers that must not case-fold.

    SQLite's explicit ``BINARY``, MySQL's ``utf8mb4_bin`` and PostgreSQL's
    ``C`` collation prevent a database default from treating two protocol
    identifiers, such as ``RB0`` and ``rb0``, as the same value.
    """
    return (
        String(length, collation="BINARY")
        .with_variant(mysql.VARCHAR(length, collation="utf8mb4_bin"), "mysql")
        .with_variant(postgresql.VARCHAR(length, collation="C"), "postgresql")
    )
