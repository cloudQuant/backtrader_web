from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable


def _normalize_identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_").lower()
    if not normalized:
        normalized = "data"
    if normalized[0].isdigit():
        normalized = f"t_{normalized}"
    return normalized


def normalize_mysql_column_names(columns: Iterable[str]) -> list[str]:
    used: set[str] = set()
    counters: dict[str, int] = {}
    normalized_columns: list[str] = []

    for index, column in enumerate(columns, start=1):
        raw_column = str(column)
        base_name = _normalize_identifier(raw_column)
        if base_name == "data" and raw_column.strip() and not re.search(
            r"[A-Za-z0-9_]", raw_column
        ):
            base_name = f"col_{index}"

        column_name = base_name
        while column_name in used:
            counters[base_name] = counters.get(base_name, 1) + 1
            column_name = f"{base_name}_{counters[base_name]}"
        used.add(column_name)
        normalized_columns.append(column_name)

    return normalized_columns


def make_akcat_table_name(endpoint_name: str) -> str:
    return f"akcat_{_normalize_identifier(endpoint_name)}"[:100]


def select_endpoint_batch(
    endpoint_names: list[str], batch_size: int, batch_index: int
) -> list[str]:
    if batch_size <= 0 or not endpoint_names:
        return []
    start = (batch_index * batch_size) % len(endpoint_names)
    selected: list[str] = []
    for offset in range(min(batch_size, len(endpoint_names))):
        selected.append(endpoint_names[(start + offset) % len(endpoint_names)])
    return selected


def default_batch_index_utc() -> int:
    return datetime.now(timezone.utc).toordinal()
