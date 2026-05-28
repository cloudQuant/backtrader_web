"""Quote source registry plus default symbols / fields configuration.

These structures used to live as module-level state in
``app.services.quote_service``. Iteration 174 (C4) split them out so the
~190-line config block doesn't bloat the service module.

Public state (read-only — populated once at import time):

- ``SOURCE_REGISTRY`` / ``SOURCE_TO_LABEL`` — broker / exchange directory.
- ``DEFAULT_SYMBOLS`` / ``DEFAULT_ASSET_TYPES`` / ``DEFAULT_SYMBOLS_BY_ASSET``
  — derived from ``config/default_symbols.yaml``.
- ``GENERIC_QUOTE_FIELDS`` / ``QUOTE_FIELDS_BY_SOURCE`` — derived from
  ``config/quote_fields.yaml`` (with a built-in fallback).

Helpers:

- :func:`resolve_quote_fields` — pick the fields to expose in a tick payload.
- :func:`first_present` / :func:`has_quote_field_value` — tiny tick helpers.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_SOURCE_REGISTRY: list[dict[str, Any]] = [
    {
        "source": "CTP",
        "source_label": "CTP",
        "capabilities": ["quote", "search", "chart"],
    },
    {
        "source": "IB_WEB",
        "source_label": "IB",
        "capabilities": ["quote", "search", "chart"],
    },
    {
        "source": "MT5",
        "source_label": "MT5",
        "capabilities": ["quote", "search", "chart"],
    },
    {
        "source": "BINANCE",
        "source_label": "Binance",
        "capabilities": ["quote", "search"],
    },
    {
        "source": "OKX",
        "source_label": "OKX",
        "capabilities": ["quote", "search"],
    },
]
SOURCE_REGISTRY = _SOURCE_REGISTRY  # public alias
SOURCE_TO_LABEL: dict[str, str] = {s["source"]: s["source_label"] for s in _SOURCE_REGISTRY}


_SYMBOLS_CONFIG_FILE = (
    Path(__file__).resolve().parents[3] / "config" / "default_symbols.yaml"
)
_QUOTE_FIELDS_CONFIG_FILE = (
    Path(__file__).resolve().parents[3] / "config" / "quote_fields.yaml"
)


def load_symbols_config() -> dict[str, Any]:
    """Load default symbols config from YAML file. Returns ``{}`` on error."""
    if not _SYMBOLS_CONFIG_FILE.is_file():
        logger.warning("Default symbols config not found: %s", _SYMBOLS_CONFIG_FILE)
        return {}
    try:
        import yaml

        with _SYMBOLS_CONFIG_FILE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001 - tolerate any yaml failure
        logger.warning("Failed to load %s: %s", _SYMBOLS_CONFIG_FILE, exc)
        return {}


def build_symbols_from_config() -> tuple[
    dict[str, list[dict[str, str]]],
    dict[str, str],
    dict[tuple[str, str], list[dict[str, str]]],
]:
    """Compose ``(symbols, default_asset_types, symbols_by_asset)`` from YAML."""
    cfg = load_symbols_config()
    symbols: dict[str, list[dict[str, str]]] = cfg.get("symbols", {})
    asset_types: dict[str, str] = cfg.get("default_asset_types", {})
    symbols_by_asset: dict[tuple[str, str], list[dict[str, str]]] = {}

    for source, asset_map in cfg.get("symbols_by_asset", {}).items():
        if isinstance(asset_map, dict):
            for asset_type, sym_list in asset_map.items():
                if isinstance(sym_list, list):
                    symbols_by_asset[(source, asset_type)] = sym_list

    for source, default_at in asset_types.items():
        key = (source, default_at)
        if key not in symbols_by_asset and source in symbols:
            symbols_by_asset[key] = symbols[source]

    for source in symbols:
        if (source, "SPOT") not in symbols_by_asset:
            symbols_by_asset[(source, "SPOT")] = symbols[source]

    return symbols, asset_types, symbols_by_asset


DEFAULT_SYMBOLS, DEFAULT_ASSET_TYPES, DEFAULT_SYMBOLS_BY_ASSET = build_symbols_from_config()


GENERIC_QUOTE_FIELDS: list[dict[str, Any]] = [
    {"prop": "symbol", "label": "代码", "visible": True, "always_show": True},
    {"prop": "name", "label": "名称", "visible": True, "always_show": False},
    {"prop": "category", "label": "分类", "visible": True, "always_show": False},
    {"prop": "last_price", "label": "最新价", "visible": True, "always_show": False},
    {"prop": "change", "label": "涨跌", "visible": True, "always_show": False},
    {"prop": "change_pct", "label": "涨跌幅", "visible": True, "always_show": False},
    {"prop": "bid_price", "label": "买价", "visible": True, "always_show": False},
    {"prop": "ask_price", "label": "卖价", "visible": True, "always_show": False},
    {"prop": "high_price", "label": "最高", "visible": True, "always_show": False},
    {"prop": "low_price", "label": "最低", "visible": True, "always_show": False},
    {"prop": "open_price", "label": "开盘", "visible": True, "always_show": False},
    {"prop": "prev_close", "label": "昨收", "visible": True, "always_show": False},
    {"prop": "volume", "label": "成交量", "visible": True, "always_show": False},
    {"prop": "turnover", "label": "成交额", "visible": True, "always_show": False},
    {"prop": "open_interest", "label": "持仓量", "visible": True, "always_show": False},
    {"prop": "update_time", "label": "更新时间", "visible": True, "always_show": False},
]


def normalize_quote_fields_config(fields: Any) -> list[dict[str, Any]]:
    """Coerce a YAML ``fields:`` block into a normalised list of field dicts."""
    normalized: list[dict[str, Any]] = []
    if not isinstance(fields, list):
        return normalized
    for item in fields:
        if not isinstance(item, dict):
            continue
        prop = str(item.get("prop") or "").strip()
        if not prop:
            continue
        normalized.append(
            {
                "prop": prop,
                "label": str(item.get("label") or prop),
                "visible": bool(item.get("visible", True)),
                "always_show": bool(item.get("always_show", False)),
            }
        )
    return normalized


def load_quote_fields_by_source() -> dict[str, list[dict[str, Any]]]:
    """Load ``config/quote_fields.yaml`` into a ``{source: [field, ...]}`` map."""
    if not _QUOTE_FIELDS_CONFIG_FILE.is_file():
        logger.warning("Quote fields config not found: %s", _QUOTE_FIELDS_CONFIG_FILE)
        return {}
    try:
        import yaml

        with _QUOTE_FIELDS_CONFIG_FILE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:  # noqa: BLE001 - tolerate any yaml failure
        logger.warning("Failed to load %s: %s", _QUOTE_FIELDS_CONFIG_FILE, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    raw_sources = data.get("sources", {})
    if not isinstance(raw_sources, dict):
        return {}
    normalized_sources: dict[str, list[dict[str, Any]]] = {}
    for source, fields in raw_sources.items():
        normalized_fields = normalize_quote_fields_config(fields)
        if normalized_fields:
            normalized_sources[str(source).strip().upper()] = normalized_fields
    return normalized_sources


QUOTE_FIELDS_BY_SOURCE = load_quote_fields_by_source()


def has_quote_field_value(value: Any) -> bool:
    """Return ``True`` if the field value should be displayed."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return True


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    """Return the first non-empty value among the candidate keys."""
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def resolve_quote_fields(
    source: str, ticks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve the ordered list of quote fields to expose for ``source``.

    Includes a field if it is configured as ``always_show`` or if at least one
    tick in ``ticks`` carries a non-empty value.
    """
    configured_fields = QUOTE_FIELDS_BY_SOURCE.get(source, GENERIC_QUOTE_FIELDS)
    resolved: list[dict[str, Any]] = []
    for field in configured_fields:
        prop = str(field.get("prop") or "").strip()
        if not prop:
            continue
        if field.get("always_show") or any(
            has_quote_field_value(tick.get(prop)) for tick in ticks
        ):
            resolved.append(dict(field))
    return resolved
