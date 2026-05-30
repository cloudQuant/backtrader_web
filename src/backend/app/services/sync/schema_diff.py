"""Pure schema-diff and SQL-building helpers for the MySQL sync service.

This module owns the *stateless* half of ``SyncService``: SQL string
construction, ``information_schema`` summary parsing, schema-delta computation,
``CREATE TABLE`` / ``CREATE VIEW`` parsing and the incremental ``ALTER TABLE``
synthesis. None of these functions touch I/O, ``self`` state, or transport;
they are deterministic transforms over strings and dicts, which makes them
directly unit-testable without a live MySQL/SSH environment.

``SyncService`` keeps thin facade methods that delegate here so existing call
sites and tests stay unchanged (see ``app/services/sync/transport.py`` for the
same pattern).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

# ---------------------------------------------------------------------------
# Quoting
# ---------------------------------------------------------------------------


def quote_sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


# ---------------------------------------------------------------------------
# information_schema summary SQL
# ---------------------------------------------------------------------------


def build_database_info_sql(databases: list[str]) -> str:
    in_clause = ", ".join(quote_sql_string(name) for name in databases)
    return (
        "SELECT TABLE_SCHEMA, "
        "COALESCE(SUM(DATA_LENGTH + INDEX_LENGTH), 0) AS size_bytes, "
        "COUNT(*) AS table_count "
        "FROM information_schema.TABLES "
        f"WHERE TABLE_SCHEMA IN ({in_clause}) "
        "GROUP BY TABLE_SCHEMA"
    )


def build_table_names_sql(database: str) -> str:
    return (
        "SELECT TABLE_NAME "
        "FROM information_schema.TABLES "
        f"WHERE TABLE_SCHEMA = {quote_sql_string(database)} "
        "ORDER BY TABLE_NAME"
    )


def build_table_columns_sql(database: str, table: str) -> str:
    return (
        "SELECT COLUMN_NAME "
        "FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA = {quote_sql_string(database)} "
        f"AND TABLE_NAME = {quote_sql_string(table)} "
        "ORDER BY ORDINAL_POSITION"
    )


def build_index_metadata_sql(database: str, table: str) -> str:
    return (
        "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME "
        "FROM information_schema.STATISTICS "
        f"WHERE TABLE_SCHEMA = {quote_sql_string(database)} "
        f"AND TABLE_NAME = {quote_sql_string(table)} "
        "AND (INDEX_NAME = 'PRIMARY' OR NON_UNIQUE = 0) "
        "ORDER BY CASE WHEN INDEX_NAME = 'PRIMARY' THEN 0 ELSE 1 END, INDEX_NAME, SEQ_IN_INDEX"
    )


def build_table_key_values_sql(
    database: str,
    table: str,
    key_columns: tuple[str, ...],
) -> str:
    key_select = ", ".join(quote_identifier(column) for column in key_columns)
    return f"SELECT {key_select} FROM {quote_identifier(database)}.{quote_identifier(table)}"


def build_row_hash_expression(key_columns: tuple[str, ...]) -> str:
    json_items = ", ".join(quote_identifier(column) for column in key_columns)
    return f"SHA2(CAST(JSON_ARRAY({json_items}) AS CHAR), 256)"


def build_table_row_hash_values_sql(
    database: str,
    table: str,
    key_columns: tuple[str, ...],
) -> str:
    row_hash = build_row_hash_expression(key_columns)
    return f"SELECT {row_hash} FROM {quote_identifier(database)}.{quote_identifier(table)}"


def build_ensure_database_sql(database: str) -> str:
    identifier = quote_identifier(database)
    return f"CREATE DATABASE IF NOT EXISTS {identifier} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"


def build_database_exists_sql(database: str) -> str:
    return (
        "SELECT SCHEMA_NAME "
        "FROM information_schema.SCHEMATA "
        f"WHERE SCHEMA_NAME = {quote_sql_string(database)} "
        "LIMIT 1"
    )


def build_schema_table_summary_sql(database: str) -> str:
    return (
        "SELECT JSON_ARRAY("
        "'TABLE', TABLE_NAME, COALESCE(TABLE_TYPE, ''), COALESCE(ENGINE, ''), COALESCE(TABLE_COLLATION, '')"
        ") "
        "FROM information_schema.TABLES "
        f"WHERE TABLE_SCHEMA = {quote_sql_string(database)} "
        "ORDER BY TABLE_NAME"
    )


def build_schema_column_summary_sql(database: str) -> str:
    return (
        "SELECT JSON_ARRAY("
        "'COLUMN', TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, "
        "IF(COLUMN_DEFAULT IS NULL, '__SYNC_NULL__', COLUMN_DEFAULT), COALESCE(EXTRA, ''), "
        "COALESCE(CHARACTER_SET_NAME, ''), COALESCE(COLLATION_NAME, '')"
        ") "
        "FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA = {quote_sql_string(database)} "
        "ORDER BY TABLE_NAME, ORDINAL_POSITION"
    )


def build_schema_index_summary_sql(database: str) -> str:
    return (
        "SELECT JSON_ARRAY("
        "'INDEX', TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, "
        "IF(SUB_PART IS NULL, -1, SUB_PART), COALESCE(COLLATION, ''), COALESCE(INDEX_TYPE, '')"
        ") "
        "FROM information_schema.STATISTICS "
        f"WHERE TABLE_SCHEMA = {quote_sql_string(database)} "
        "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX"
    )


def build_schema_view_summary_sql(database: str) -> str:
    return (
        "SELECT JSON_ARRAY("
        "'VIEW', TABLE_NAME, VIEW_DEFINITION, COALESCE(CHECK_OPTION, ''), "
        "COALESCE(IS_UPDATABLE, ''), COALESCE(SECURITY_TYPE, '')"
        ") "
        "FROM information_schema.VIEWS "
        f"WHERE TABLE_SCHEMA = {quote_sql_string(database)} "
        "ORDER BY TABLE_NAME"
    )


def build_schema_summary_sql_list(database: str) -> tuple[str, ...]:
    return (
        build_schema_table_summary_sql(database),
        build_schema_column_summary_sql(database),
        build_schema_index_summary_sql(database),
        build_schema_view_summary_sql(database),
    )


# ---------------------------------------------------------------------------
# Incremental key-row helpers
# ---------------------------------------------------------------------------


def select_incremental_key_columns(stdout: str) -> tuple[str, ...]:
    indexes: dict[str, list[tuple[int, str]]] = {}
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        index_name, _non_unique, seq_in_index, column_name = parts
        indexes.setdefault(index_name, []).append((int(seq_in_index), column_name))
    if not indexes:
        return ()
    if "PRIMARY" in indexes:
        selected = indexes["PRIMARY"]
    else:
        first_name = next(iter(indexes))
        selected = indexes[first_name]
    return tuple(column for _, column in sorted(selected, key=lambda item: item[0]))


def parse_table_columns(stdout: str, database: str, table: str) -> tuple[str, ...]:
    columns = tuple(line.strip() for line in stdout.splitlines() if line.strip())
    if not columns:
        raise RuntimeError(f"数据表 {database}.{table} 未读取到可用列，无法执行增量同步")
    return columns


def build_missing_rows(
    source_rows: list[tuple[str | None, ...]],
    target_rows: list[tuple[str | None, ...]],
) -> list[tuple[str | None, ...]]:
    remaining: Counter[tuple[str | None, ...]] = Counter(source_rows)
    remaining.subtract(target_rows)
    missing_rows: list[tuple[str | None, ...]] = []
    for row in source_rows:
        if remaining[row] > 0:
            missing_rows.append(row)
            remaining[row] -= 1
    return missing_rows


def parse_key_rows(stdout: str, expected_columns: int) -> list[tuple[str | None, ...]]:
    rows: list[tuple[str | None, ...]] = []
    for line in stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != expected_columns:
            continue
        rows.append(tuple(None if value == "\\N" else value for value in parts))
    return rows


def chunk_keys(
    keys: list[tuple[str | None, ...]],
    batch_size: int,
) -> list[list[tuple[str | None, ...]]]:
    return [keys[index : index + batch_size] for index in range(0, len(keys), batch_size)]


def build_missing_keys_where_sql(
    key_columns: tuple[str, ...],
    key_rows: list[tuple[str | None, ...]],
) -> str:
    clauses: list[str] = []
    for row in key_rows:
        parts: list[str] = []
        for column, value in zip(key_columns, row, strict=False):
            identifier = quote_identifier(column)
            if value is None:
                parts.append(f"{identifier} IS NULL")
            else:
                parts.append(f"{identifier} = {quote_sql_string(value)}")
        clauses.append("(" + " AND ".join(parts) + ")")
    return " OR ".join(clauses) if clauses else "1 = 0"


def build_missing_row_hashes_where_sql(
    key_columns: tuple[str, ...],
    key_rows: list[tuple[str | None, ...]],
) -> str:
    row_hash = build_row_hash_expression(key_columns)
    values = [row[0] for row in key_rows if row and row[0] is not None]
    if not values:
        return "1 = 0"
    in_clause = ", ".join(quote_sql_string(str(value)) for value in values)
    return f"{row_hash} IN ({in_clause})"


# ---------------------------------------------------------------------------
# Schema summary parsing + delta
# ---------------------------------------------------------------------------


def normalize_schema_dump(payload: str) -> str:
    normalized = payload.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"AUTO_INCREMENT=\d+", "AUTO_INCREMENT=0", normalized)
    normalized = re.sub(r"DEFINER=`[^`]+`@`[^`]+`", "DEFINER=CURRENT_USER", normalized)
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    return "\n".join(lines)


def parse_schema_summary(payload: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tables": {},
        "columns": {},
        "indexes": {},
        "views": {},
    }
    for line in payload.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, list) or not row:
            continue
        kind = str(row[0])
        if kind == "TABLE" and len(row) >= 5:
            table_name = str(row[1])
            summary["tables"][table_name] = {
                "table_type": str(row[2]),
                "engine": str(row[3]),
                "collation": str(row[4]),
            }
            continue
        if kind == "COLUMN" and len(row) >= 10:
            table_name = str(row[1])
            ordinal = int(row[2])
            column_name = str(row[3])
            summary["columns"].setdefault(table_name, {})[column_name] = {
                "ordinal": ordinal,
                "signature": json.dumps(row[3:], ensure_ascii=False, separators=(",", ":")),
            }
            continue
        if kind == "INDEX" and len(row) >= 9:
            table_name = str(row[1])
            index_name = str(row[2])
            table_indexes = summary["indexes"].setdefault(table_name, {})
            entry = table_indexes.setdefault(
                index_name,
                {
                    "non_unique": int(row[3]),
                    "index_type": str(row[8]),
                    "parts": [],
                },
            )
            entry["parts"].append(
                (
                    int(row[4]),
                    str(row[5]),
                    int(row[6]),
                    str(row[7]),
                )
            )
            continue
        if kind == "VIEW" and len(row) >= 6:
            view_name = str(row[1])
            summary["views"][view_name] = json.dumps(
                row[2:], ensure_ascii=False, separators=(",", ":")
            )
    for table_indexes in summary["indexes"].values():
        for index_meta in table_indexes.values():
            index_meta["parts"].sort(key=lambda item: item[0])
            index_meta["signature"] = json.dumps(
                [index_meta["non_unique"], index_meta["index_type"], index_meta["parts"]],
                ensure_ascii=False,
                separators=(",", ":"),
            )
    return summary


def build_schema_delta(
    source_summary: dict[str, Any],
    target_summary: dict[str, Any],
) -> dict[str, Any]:
    source_tables = {
        name: meta
        for name, meta in source_summary.get("tables", {}).items()
        if str(meta.get("table_type", "")).upper() == "BASE TABLE"
    }
    target_tables = {
        name: meta
        for name, meta in target_summary.get("tables", {}).items()
        if str(meta.get("table_type", "")).upper() == "BASE TABLE"
    }
    missing_tables = sorted(set(source_tables) - set(target_tables))
    common_tables = sorted(set(source_tables) & set(target_tables))
    table_changes: dict[str, dict[str, list[str]]] = {}
    for table in common_tables:
        source_columns = source_summary.get("columns", {}).get(table, {})
        target_columns = target_summary.get("columns", {}).get(table, {})
        source_order = [
            name
            for name, _meta in sorted(source_columns.items(), key=lambda item: item[1]["ordinal"])
        ]
        add_columns = [name for name in source_order if name not in target_columns]
        modify_columns = [
            name
            for name in source_order
            if name in target_columns
            and source_columns[name]["signature"] != target_columns[name]["signature"]
        ]
        source_indexes = source_summary.get("indexes", {}).get(table, {})
        target_indexes = target_summary.get("indexes", {}).get(table, {})
        add_indexes = sorted(name for name in source_indexes if name not in target_indexes)
        rebuild_indexes = sorted(
            name
            for name in source_indexes
            if name in target_indexes
            and source_indexes[name]["signature"] != target_indexes[name]["signature"]
        )
        if add_columns or modify_columns or add_indexes or rebuild_indexes:
            table_changes[table] = {
                "add_columns": add_columns,
                "modify_columns": modify_columns,
                "add_indexes": add_indexes,
                "rebuild_indexes": rebuild_indexes,
            }
    source_views = source_summary.get("views", {})
    target_views = target_summary.get("views", {})
    views_to_upsert = sorted(
        name for name, signature in source_views.items() if target_views.get(name) != signature
    )
    return {
        "missing_tables": missing_tables,
        "table_changes": table_changes,
        "views_to_upsert": views_to_upsert,
    }


def schema_delta_is_empty(delta: dict[str, Any]) -> bool:
    return (
        not delta["missing_tables"] and not delta["table_changes"] and not delta["views_to_upsert"]
    )


# ---------------------------------------------------------------------------
# CREATE TABLE / VIEW parsing + incremental ALTER synthesis
# ---------------------------------------------------------------------------


def extract_create_table_statement(payload: str, table: str) -> str:
    quoted_table = re.escape(quote_identifier(table))
    match = re.search(rf"CREATE TABLE {quoted_table} \(.*?\)[^;]*;", payload, re.S)
    if match is None:
        raise RuntimeError(f"未找到数据表 {table} 的 CREATE TABLE 语句")
    return match.group(0).strip()


def _extract_balanced_paren_body(payload: str, table: str) -> str:
    """Return the text between the outermost ``( ... )`` of a CREATE TABLE.

    A naive ``\\(.*?\\)`` regex stops at the first ``)`` — which for a column
    type such as ``varchar(20)`` or ``decimal(10,2)`` is *inside* the column
    definition, truncating it and dropping every index line. We instead scan
    for the matching close paren with a depth counter, skipping parentheses
    that appear inside backtick-quoted identifiers or single-quoted strings
    (e.g. string ``DEFAULT`` values).
    """
    quoted_table = re.escape(quote_identifier(table))
    header = re.search(rf"CREATE TABLE {quoted_table}\s*\(", payload)
    if header is None:
        raise RuntimeError(f"未找到数据表 {table} 的字段定义")
    start = header.end()  # position just after the opening paren
    depth = 1
    in_backtick = False
    in_quote = False
    index = start
    length = len(payload)
    while index < length:
        char = payload[index]
        if in_backtick:
            if char == "`":
                in_backtick = False
        elif in_quote:
            if char == "\\":
                index += 1  # skip escaped char inside a string literal
            elif char == "'":
                in_quote = False
        elif char == "`":
            in_backtick = True
        elif char == "'":
            in_quote = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return payload[start:index]
        index += 1
    raise RuntimeError(f"未找到数据表 {table} 的字段定义")


def extract_create_table_definitions(payload: str, table: str) -> dict[str, dict[str, str]]:
    body = _extract_balanced_paren_body(payload, table)
    column_defs: dict[str, str] = {}
    index_defs: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip().rstrip(",")
        if not line:
            continue
        if line.startswith("`"):
            column_name = line.split("`", 2)[1]
            column_defs[column_name] = line
            continue
        if line.startswith("PRIMARY KEY"):
            index_defs["PRIMARY"] = line
            continue
        index_match = re.match(r"(?:UNIQUE KEY|FULLTEXT KEY|SPATIAL KEY|KEY) `([^`]+)`", line)
        if index_match is not None:
            index_defs[index_match.group(1)] = line
    return {
        "columns": column_defs,
        "indexes": index_defs,
    }


def build_column_position_clause(
    source_order: list[str],
    current_columns: set[str],
    column_name: str,
) -> str:
    column_index = source_order.index(column_name)
    for previous_name in reversed(source_order[:column_index]):
        if previous_name in current_columns:
            return f" AFTER {quote_identifier(previous_name)}"
    return " FIRST"


def build_incremental_table_alter_sql(
    database: str,
    table: str,
    table_delta: dict[str, list[str]],
    source_summary: dict[str, Any],
    target_summary: dict[str, Any],
    source_schema_sql: str,
) -> str | None:
    parsed = extract_create_table_definitions(source_schema_sql, table)
    source_columns = source_summary.get("columns", {}).get(table, {})
    target_columns = target_summary.get("columns", {}).get(table, {})
    source_order = [
        name for name, _meta in sorted(source_columns.items(), key=lambda item: item[1]["ordinal"])
    ]
    current_columns = set(target_columns)
    clauses: list[str] = []
    for column_name in source_order:
        if column_name in table_delta["add_columns"]:
            column_definition = parsed["columns"].get(column_name)
            if column_definition is None:
                raise RuntimeError(f"未找到数据表 {table}.{column_name} 的字段定义")
            position_clause = build_column_position_clause(
                source_order, current_columns, column_name
            )
            clauses.append(f"ADD COLUMN {column_definition}{position_clause}")
            current_columns.add(column_name)
        elif column_name in table_delta["modify_columns"]:
            column_definition = parsed["columns"].get(column_name)
            if column_definition is None:
                raise RuntimeError(f"未找到数据表 {table}.{column_name} 的字段定义")
            clauses.append(f"MODIFY COLUMN {column_definition}")
    for index_name in table_delta["rebuild_indexes"]:
        index_definition = parsed["indexes"].get(index_name)
        if index_definition is None:
            raise RuntimeError(f"未找到数据表 {table} 索引 {index_name} 的定义")
        if index_name == "PRIMARY":
            clauses.append("DROP PRIMARY KEY")
            clauses.append(f"ADD {index_definition}")
        else:
            clauses.append(f"DROP INDEX {quote_identifier(index_name)}")
            clauses.append(f"ADD {index_definition}")
    for index_name in table_delta["add_indexes"]:
        index_definition = parsed["indexes"].get(index_name)
        if index_definition is None:
            raise RuntimeError(f"未找到数据表 {table} 索引 {index_name} 的定义")
        clauses.append(f"ADD {index_definition}")
    if not clauses:
        return None
    return f"ALTER TABLE {quote_identifier(database)}.{quote_identifier(table)} " + ", ".join(
        clauses
    )


def build_show_create_view_sql(database: str, view_name: str) -> str:
    return f"SHOW CREATE VIEW {quote_identifier(database)}.{quote_identifier(view_name)}"


def normalize_create_view_sql(payload: str, view_name: str) -> str:
    parts = payload.split("\t", 3)
    if len(parts) < 2:
        raise RuntimeError(f"未找到视图 {view_name} 的 CREATE VIEW 语句")
    create_sql = parts[1].replace("\\n", "\n").replace("\\t", "\t")
    create_sql = re.sub(r"\sDEFINER=`[^`]+`@`[^`]+`", "", create_sql, count=1)
    if create_sql.startswith("CREATE "):
        create_sql = create_sql.replace("CREATE ", "CREATE OR REPLACE ", 1)
    return create_sql.strip()


def build_database_scoped_sql(database: str, sql: str) -> str:
    statement = sql.strip()
    if statement.endswith(";"):
        statement = statement[:-1]
    return f"USE {quote_identifier(database)}; {statement};"


# ---------------------------------------------------------------------------
# Progress percentage math (pure)
# ---------------------------------------------------------------------------


def build_table_step_progress(*, index: int, total: int, step: int, step_count: int) -> int:
    table_start = 45 + int((index / max(total, 1)) * 45)
    table_end = 45 + int(((index + 1) / max(total, 1)) * 45)
    span = max(table_end - table_start, 1)
    normalized_step = min(max(step, 0), max(step_count, 1))
    return min(table_start + int((normalized_step / max(step_count, 1)) * span), 90)
