"""Workspace configuration helpers and normalisation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.workspace import StrategyUnit, Workspace
from app.schemas.workspace import WorkspaceResponse

_DEFAULT_UNIT_START_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)

_ALLOWED_RUNTIME_FILE_EXTENSIONS = frozenset(
    {".log", ".yaml", ".yml", ".json", ".txt", ".py", ".md", ".csv"}
)


def _default_workspace_settings() -> dict[str, Any]:
    return {
        "data_source": {
            "type": "csv",
            "csv": {
                "directory_path": "",
                "delimiter": ",",
                "encoding": "utf-8",
                "has_header": True,
            },
            "mysql": {
                "host": "127.0.0.1",
                "port": 3306,
                "database": "",
                "username": "",
                "password": "",
                "table": "",
            },
            "postgresql": {
                "host": "127.0.0.1",
                "port": 5432,
                "database": "",
                "schema": "public",
                "username": "",
                "password": "",
                "table": "",
            },
            "mongodb": {
                "uri": "mongodb://127.0.0.1:27017",
                "database": "",
                "collection": "",
                "username": "",
                "password": "",
                "auth_source": "admin",
            },
        }
    }


def _normalize_workspace_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "trading" if text == "trading" else "research"


def _is_trading_workspace(value: Any) -> bool:
    return _normalize_workspace_type(value) == "trading"


def _normalize_workspace_trading_config(config: dict[str, Any] | None) -> dict[str, Any]:
    return dict(config) if isinstance(config, dict) else {}


def _normalize_workspace_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _default_workspace_settings()
    if not isinstance(settings, dict):
        return normalized

    for key, value in settings.items():
        if key != "data_source":
            normalized[key] = value

    data_source = settings.get("data_source")
    if isinstance(data_source, dict):
        merged_data_source = dict(normalized["data_source"])
        for key, value in data_source.items():
            if key in {"csv", "mysql", "postgresql", "mongodb"} and isinstance(value, dict):
                section = dict(merged_data_source[key])
                if (
                    key == "csv"
                    and "directory_path" not in value
                    and isinstance(value.get("file_path"), str)
                ):
                    section["directory_path"] = value["file_path"]
                for section_key, section_value in value.items():
                    if key == "csv" and section_key == "file_path":
                        continue
                    section[section_key] = section_value
                merged_data_source[key] = section
            else:
                merged_data_source[key] = value
        normalized["data_source"] = merged_data_source

    return normalized


def _aggregate_workspace_status(units: list[StrategyUnit]) -> str:
    """Compute workspace status from child unit statuses."""
    if not units:
        return "idle"
    statuses = {u.run_status for u in units}
    if statuses & {"running", "queued"}:
        return "running"
    if all(s == "completed" for s in statuses):
        return "completed"
    if "failed" in statuses and not (statuses & {"running", "queued"}):
        return "error"
    return "idle"


def _workspace_settings_dict(ws: Workspace) -> dict[str, Any]:
    raw_settings = ws.__dict__.get("settings")
    if isinstance(raw_settings, dict):
        return _normalize_workspace_settings(raw_settings)
    return _normalize_workspace_settings(None)


def _default_unit_start_date_iso() -> str:
    return _DEFAULT_UNIT_START_DATE.isoformat()


def _default_unit_end_date_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _normalize_unit_data_config(data_config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(data_config or {})
    range_type = str(normalized.get("range_type") or "date").strip().lower()
    normalized["range_type"] = range_type if range_type in {"date", "sample"} else "date"
    if normalized["range_type"] == "date":
        if not str(normalized.get("start_date") or "").strip():
            normalized["start_date"] = _default_unit_start_date_iso()
        normalized["use_end_date"] = normalized.get("use_end_date") is not False
        if normalized["use_end_date"] and not str(normalized.get("end_date") or "").strip():
            normalized["end_date"] = _default_unit_end_date_iso()
        normalized.pop("sample_count", None)
        normalized.pop("bar_count", None)
    else:
        if normalized.get("sample_count") in (None, "", 0):
            normalized["sample_count"] = 1000
    return normalized


def _workspace_to_response(ws: Workspace) -> WorkspaceResponse:
    """Convert a Workspace ORM object to a WorkspaceResponse, including aggregated fields."""
    units = ws.strategy_units or []
    completed_count = sum(1 for u in units if u.run_status == "completed")
    return WorkspaceResponse(
        id=ws.id,
        user_id=ws.user_id,
        name=ws.name,
        description=ws.description,
        workspace_type=_normalize_workspace_type(getattr(ws, "workspace_type", None)),
        settings=_normalize_workspace_settings(ws.settings),
        trading_config=_normalize_workspace_trading_config(getattr(ws, "trading_config", None)),
        unit_count=len(units),
        completed_count=completed_count,
        status=_aggregate_workspace_status(units),
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )

