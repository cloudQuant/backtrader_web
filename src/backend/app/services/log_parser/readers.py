"""Low-level log file readers.

These helpers do *not* know anything about the semantics of trade/value/order
logs — they only convert raw file bytes into a list of dictionaries that the
domain-specific parsers in :mod:`log_parser_service` then interpret.

Four formats are supported:

- **TSV** with a header line.
- **JSON Lines** (one JSON object per line).
- **Pipe-delimited** with a leading datetime + event field then ``key=value``
  pairs (legacy backtrader/cerebro logs).
- **Pipe-delimited key/value** without the implicit event slot (workspace
  simulate logs).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_tsv(filepath: Path) -> list[dict[str, str]]:
    """Parse a tab-separated log file and return a list of dictionaries.

    Args:
        filepath: Path to the TSV file.

    Returns:
        A list of dictionaries where each dictionary represents a row
        with column headers as keys.
    """
    if not filepath.is_file():
        return []

    rows = []
    with open(filepath, encoding="utf-8") as f:
        header_line = f.readline().strip()
        if not header_line:
            return []
        if header_line.startswith("{") or header_line.startswith("["):
            return []
        if "\t" not in header_line:
            return []
        headers = header_line.split("\t")

        for line in f:
            line = line.strip()
            if not line:
                continue
            values = line.split("\t")
            row = {}
            for i, h in enumerate(headers):
                row[h] = values[i] if i < len(values) else ""
            rows.append(row)

    return rows


def parse_json_lines(filepath: Path) -> list[dict[str, Any]]:
    """Parse a JSON-Lines file. Returns ``[]`` on any decoding error."""
    if not filepath.is_file():
        return []

    rows: list[dict[str, Any]] = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return []
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def parse_pipe_lines(filepath: Path) -> list[dict[str, str]]:
    """Parse legacy pipe-separated logs of the form ``dt|event|k=v|k=v|...``."""
    if not filepath.is_file():
        return []

    rows: list[dict[str, str]] = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text or "|" not in text:
                continue
            parts = [part.strip() for part in text.split("|")]
            if len(parts) < 2:
                continue
            row: dict[str, str] = {"datetime": parts[0], "event": parts[1]}
            for part in parts[2:]:
                if not part or "=" not in part:
                    continue
                key, value = part.split("=", 1)
                row[key.strip().lower()] = value.strip()
            rows.append(row)
    return rows


def parse_pipe_key_value_lines(filepath: Path) -> list[dict[str, str]]:
    """Parse simulate/workspace pipe-separated logs of the form ``log_time|k=v|...``.

    Differs from :func:`parse_pipe_lines` in that the second slot is *not*
    treated as an event name; instead, any unlabeled tokens are collected into
    a synthetic ``event`` field.
    """
    if not filepath.is_file():
        return []

    rows: list[dict[str, str]] = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text or "|" not in text:
                continue
            parts = [part.strip() for part in text.split("|")]
            if len(parts) < 2:
                continue
            row: dict[str, str] = {"log_time": parts[0]}
            unlabeled: list[str] = []
            for part in parts[1:]:
                if not part:
                    continue
                if "=" in part:
                    key, value = part.split("=", 1)
                    row[key.strip()] = value.strip()
                    continue
                unlabeled.append(part)
            if unlabeled:
                row["event"] = unlabeled[0]
            rows.append(row)
    return rows
