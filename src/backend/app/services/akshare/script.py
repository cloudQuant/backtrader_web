"""
Service for akshare data scripts.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.akshare_mgmt import DataInterface, DataScript, ScriptFrequency, TriggeredBy
from app.services.akshare_data_service import AkshareDataService
from app.services.akshare_execution_service import AkshareExecutionService

settings = get_settings()


class AkshareScriptService:
    """CRUD, scan and execution service for akshare scripts."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.data_service = AkshareDataService(db)
        self.execution_service = AkshareExecutionService(db)

    def _script_root(self) -> Path:
        configured = Path(settings.AKSHARE_SCRIPT_ROOT)
        if configured.is_absolute():
            return configured
        project_app_dir = Path(__file__).resolve().parents[1]
        if configured.parts and configured.parts[0] == "app":
            configured = Path(*configured.parts[1:])
        return project_app_dir / configured

    async def list_scripts(
        self,
        category: str | None = None,
        keyword: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DataScript], int]:
        stmt = select(DataScript)
        count_stmt = select(func.count(DataScript.id))
        filters = []
        if category:
            filters.append(DataScript.category == category)
        if is_active is not None:
            filters.append(DataScript.is_active == is_active)
        if keyword:
            filters.append(
                or_(
                    DataScript.script_id.ilike(f"%{keyword}%"),
                    DataScript.script_name.ilike(f"%{keyword}%"),
                    DataScript.description.ilike(f"%{keyword}%"),
                )
            )
        if filters:
            for item in filters:
                stmt = stmt.where(item)
                count_stmt = count_stmt.where(item)
        total = int((await self.db.execute(count_stmt)).scalar() or 0)
        stmt = (
            stmt.order_by(DataScript.category, DataScript.script_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_script(self, script_id: str) -> DataScript | None:
        result = await self.db.execute(select(DataScript).where(DataScript.script_id == script_id))
        return result.scalar_one_or_none()

    async def get_categories(self) -> list[str]:
        result = await self.db.execute(
            select(DataScript.category).distinct().order_by(DataScript.category)
        )
        return [row[0] for row in result.all()]

    async def get_stats(self) -> dict[str, Any]:
        total = int((await self.db.execute(select(func.count(DataScript.id)))).scalar() or 0)
        active = int(
            (
                await self.db.execute(
                    select(func.count(DataScript.id)).where(DataScript.is_active.is_(True))
                )
            ).scalar()
            or 0
        )
        custom = int(
            (
                await self.db.execute(
                    select(func.count(DataScript.id)).where(DataScript.is_custom.is_(True))
                )
            ).scalar()
            or 0
        )
        return {
            "total_scripts": total,
            "active_scripts": active,
            "custom_scripts": custom,
            "categories": await self.get_categories(),
        }

    async def create_script(
        self, payload: dict[str, Any], operator_id: str | None = None
    ) -> DataScript:
        script = DataScript(
            **payload, is_custom=True, created_by=operator_id, updated_by=operator_id
        )
        self.db.add(script)
        await self.db.commit()
        await self.db.refresh(script)
        return script

    async def update_script(
        self,
        script_id: str,
        payload: dict[str, Any],
        operator_id: str | None = None,
    ) -> DataScript | None:
        script = await self.get_script(script_id)
        if script is None:
            return None
        for key, value in payload.items():
            if value is not None and hasattr(script, key):
                setattr(script, key, value)
        script.updated_by = operator_id
        await self.db.commit()
        await self.db.refresh(script)
        return script

    async def delete_script(self, script_id: str) -> bool:
        script = await self.get_script(script_id)
        if script is None:
            return False
        if not script.is_custom:
            raise ValueError("Built-in scripts cannot be deleted")
        await self.db.delete(script)
        await self.db.commit()
        return True

    async def toggle_script(self, script_id: str) -> DataScript | None:
        script = await self.get_script(script_id)
        if script is None:
            return None
        script.is_active = not script.is_active
        await self.db.commit()
        await self.db.refresh(script)
        return script

    def _derive_script_metadata(self, file_path: Path, root: Path) -> dict[str, Any]:
        relative = file_path.relative_to(root)
        parts = list(relative.parts)
        stem = file_path.stem
        module_path = "app.data_fetch.scripts." + ".".join(parts).replace(".py", "")
        category = parts[0] if parts else "misc"
        sub_category = parts[1] if len(parts) > 2 else None
        return {
            "script_id": stem,
            "script_name": stem.replace("_", " ").title(),
            "category": category,
            "sub_category": sub_category,
            "module_path": module_path,
            "function_name": "main",
            "target_table": stem,
            "frequency": ScriptFrequency.MANUAL,
        }

    def _legacy_script_instance(self, module: Any) -> Any | None:
        for obj in module.__dict__.values():
            if (
                isinstance(obj, type)
                and obj.__module__ == module.__name__
                and (hasattr(obj, "fetch_data") or hasattr(obj, "run"))
            ):
                try:
                    return obj()
                except Exception:
                    continue
        return None

    def _extract_module_metadata(self, module: Any, metadata: dict[str, Any]) -> dict[str, Any]:
        extracted = dict(metadata)
        extracted["script_name"] = getattr(module, "SCRIPT_NAME", extracted["script_name"])
        extracted["description"] = getattr(module, "DESCRIPTION", extracted.get("description"))
        extracted["target_table"] = getattr(module, "TARGET_TABLE", extracted["target_table"])
        extracted["function_name"] = getattr(module, "ENTRYPOINT", extracted["function_name"])

        legacy_instance = self._legacy_script_instance(module)
        if legacy_instance is None:
            return extracted

        legacy_table_name = getattr(legacy_instance, "table_name", None)
        if isinstance(legacy_table_name, str) and legacy_table_name:
            extracted["target_table"] = legacy_table_name

        if extracted["function_name"] == "main":
            if hasattr(legacy_instance, "fetch_data"):
                extracted["function_name"] = "fetch_data"
            elif hasattr(legacy_instance, "run"):
                extracted["function_name"] = "run"

        extracted["description"] = extracted.get("description") or inspect.getdoc(
            legacy_instance.__class__
        )
        return extracted

    def _derive_interface_script_metadata(self, interface: DataInterface) -> dict[str, Any]:
        category_name = interface.category.name if interface.category is not None else "misc"
        function_name = interface.function_name or interface.name
        return {
            "script_id": interface.name,
            "script_name": interface.display_name or interface.name.replace("_", " ").title(),
            "category": category_name,
            "sub_category": None,
            "module_path": interface.module_path or "akshare",
            "function_name": function_name,
            "target_table": function_name,
            "frequency": ScriptFrequency.MANUAL,
            "description": interface.description,
            "source": "akshare",
        }

    async def _sync_scripts_from_interfaces(self) -> dict[str, Any]:
        registered = 0
        updated = 0
        errors: list[str] = []
        result = await self.db.execute(
            select(DataInterface)
            .options(selectinload(DataInterface.category))
            .where(DataInterface.is_active.is_(True))
        )
        interfaces = list(result.scalars().all())
        for interface in interfaces:
            try:
                metadata = self._derive_interface_script_metadata(interface)
                existing = await self.get_script(metadata["script_id"])
                if existing is None:
                    script = DataScript(**metadata, is_active=True, is_custom=False)
                    self.db.add(script)
                    registered += 1
                    continue

                if existing.is_custom:
                    continue

                preserved_is_active = existing.is_active
                preserved_target_table = existing.target_table
                for key, value in metadata.items():
                    setattr(existing, key, value)
                existing.is_active = preserved_is_active
                existing.target_table = preserved_target_table or metadata["target_table"]
                updated += 1
            except Exception as exc:
                errors.append(f"{interface.name}: {exc}")

        return {"registered": registered, "updated": updated, "errors": errors}

    async def scan_and_register_scripts(self) -> dict[str, Any]:
        root = self._script_root()
        registered = 0
        updated = 0
        errors: list[str] = []
        if root.exists():
            for file_path in sorted(root.rglob("*.py")):
                if file_path.name.startswith("__"):
                    continue
                metadata = self._derive_script_metadata(file_path, root)
                try:
                    module = importlib.import_module(metadata["module_path"])
                    metadata = self._extract_module_metadata(module, metadata)
                    existing = await self.get_script(metadata["script_id"])
                    if existing is None:
                        script = DataScript(**metadata, is_active=True, is_custom=False)
                        self.db.add(script)
                        registered += 1
                    else:
                        for key, value in metadata.items():
                            setattr(existing, key, value)
                        updated += 1
                except Exception as exc:
                    errors.append(f"{file_path.name}: {exc}")
        else:
            errors.append(f"Script root not found: {root}")

        interface_result = await self._sync_scripts_from_interfaces()
        registered += interface_result["registered"]
        updated += interface_result["updated"]
        errors.extend(interface_result["errors"])
        await self.db.commit()
        return {"registered": registered, "updated": updated, "errors": errors}

    async def _resolve_callable_from_interface(self, script: DataScript) -> Any | None:
        filters = [DataInterface.name == script.script_id]
        if script.function_name:
            filters.append(DataInterface.function_name == script.function_name)
        result = await self.db.execute(
            select(DataInterface).where(or_(*filters)).order_by(DataInterface.id.asc())
        )
        interface = result.scalar_one_or_none()
        if interface is None:
            return None

        module_name = interface.module_path or "akshare"
        function_name = interface.function_name or interface.name
        module = importlib.import_module(module_name)
        candidate = getattr(module, function_name, None)
        return candidate if callable(candidate) else None

    def _resolve_module_callable(self, module: Any, func_name: str) -> Any | None:
        candidate = getattr(module, func_name, None)
        if callable(candidate):
            return candidate

        for name in ("fetch_data", "run", "main"):
            candidate = getattr(module, name, None)
            if callable(candidate):
                return candidate

        legacy_instance = self._legacy_script_instance(module)
        if legacy_instance is None:
            return None

        for name in (func_name, "fetch_data", "run"):
            candidate = getattr(legacy_instance, name, None)
            if callable(candidate):
                return candidate

        return None

    async def _resolve_callable(self, script: DataScript) -> Any:
        func_name = script.function_name or "main"
        if script.module_path:
            try:
                module = importlib.import_module(script.module_path)
            except ModuleNotFoundError:
                module = None
            if module is not None:
                candidate = self._resolve_module_callable(module, func_name)
                if callable(candidate):
                    return candidate

        candidate = await self._resolve_callable_from_interface(script)
        if callable(candidate):
            return candidate
        raise AttributeError(f"No callable entrypoint found for script {script.script_id}")

    def _coerce_to_dataframe(self, result: Any) -> pd.DataFrame:
        if isinstance(result, pd.DataFrame):
            return result
        if isinstance(result, list):
            return pd.DataFrame(result)
        if isinstance(result, dict):
            if "data" in result and isinstance(result["data"], pd.DataFrame):
                return result["data"]
            if "records" in result and isinstance(result["records"], list):
                return pd.DataFrame(result["records"])
            return pd.DataFrame([result])
        raise TypeError("Script result cannot be converted to DataFrame")

    @staticmethod
    def _legacy_table_name(script: DataScript) -> str | None:
        if not script.target_table:
            return None
        return AkshareDataService._validate_table_name(
            AkshareDataService._normalize_identifier(script.target_table)
        )

    @staticmethod
    def _legacy_callable_table_name(callable_obj: Any) -> str | None:
        owner = getattr(callable_obj, "__self__", None)
        if owner is None or not hasattr(owner, "save_data"):
            return None
        table_name = getattr(owner, "table_name", None)
        if not isinstance(table_name, str) or not table_name:
            return None
        return AkshareDataService._validate_table_name(
            AkshareDataService._normalize_identifier(table_name)
        )

    async def run_script(
        self,
        script_id: str,
        parameters: dict[str, Any] | None = None,
        operator_id: str | None = None,
        task_id: int | None = None,
        triggered_by: TriggeredBy = TriggeredBy.MANUAL,
    ):
        script = await self.get_script(script_id)
        if script is None:
            raise ValueError("Script not found")
        if not script.is_active:
            raise ValueError("Script is not active")

        params = parameters or {}
        execution = await self.execution_service.create_execution(
            script_id=script.script_id,
            task_id=task_id,
            params=params,
            triggered_by=triggered_by,
            operator_id=operator_id,
        )
        await self.execution_service.mark_running(execution)

        try:
            callable_obj = await self._resolve_callable(script)
            dataframe_table_name = self.data_service.build_table_name(script, params)
            legacy_table_name = self._legacy_callable_table_name(
                callable_obj
            ) or self._legacy_table_name(script)
            dataframe_rows_before = await self.data_service.get_row_count(dataframe_table_name)
            legacy_rows_before = (
                await self.data_service.get_row_count(legacy_table_name)
                if legacy_table_name and legacy_table_name != dataframe_table_name
                else dataframe_rows_before
            )
            if inspect.iscoroutinefunction(callable_obj):
                result = await callable_obj(**params)
            else:
                result = await asyncio.to_thread(callable_obj, **params)

            if self._legacy_callable_table_name(callable_obj) is not None:
                table = await self.data_service.sync_existing_table_metadata(
                    script,
                    legacy_table_name,
                    params,
                )
                rows_before = legacy_rows_before
                rows_after = table.row_count
                summary = {
                    "table_name": table.table_name,
                    "row_count": table.row_count,
                    "columns": table.metadata_json.get("columns", []),
                }
            else:
                try:
                    dataframe = self._coerce_to_dataframe(result)
                except TypeError:
                    if legacy_table_name is None:
                        raise
                    table = await self.data_service.sync_existing_table_metadata(
                        script,
                        legacy_table_name,
                        params,
                    )
                    rows_before = legacy_rows_before
                    rows_after = table.row_count
                    summary = {
                        "table_name": table.table_name,
                        "row_count": table.row_count,
                        "columns": table.metadata_json.get("columns", []),
                    }
                else:
                    table = await self.data_service.persist_dataframe(script, dataframe, params)
                    rows_before = dataframe_rows_before
                    rows_after = table.row_count
                    summary = {
                        "table_name": table.table_name,
                        "row_count": table.row_count,
                        "columns": list(dataframe.columns),
                    }
            execution = await self.execution_service.mark_completed(
                execution,
                result=summary,
                rows_before=rows_before,
                rows_after=rows_after,
            )
            return execution
        except Exception as exc:
            execution = await self.execution_service.mark_failed(execution, str(exc))
            raise
