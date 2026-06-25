"""
Service for akshare data scripts.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.data_fetch.utils.akshare_network_proxy import configure_akshare_network_proxy
from app.models.akshare_mgmt import (
    DataInterface,
    DataScript,
    ScriptFrequency,
    TaskExecution,
    TriggeredBy,
)
from app.services.akshare.data import AkshareDataService
from app.services.akshare.execution import AkshareExecutionService

settings = get_settings()

_SCRIPT_MIN_TIMEOUT_SECONDS: dict[str, float] = {
    "macro_bank_english_interest_rate": 90.0,
    "macro_china_bond_public": 150.0,
    "macro_china_insurance": 420.0,
    "macro_china_retail_price_index": 240.0,
    "macro_china_society_traffic_volume": 240.0,
    "macro_cons_gold": 240.0,
    "macro_cons_opec_month": 180.0,
    "macro_cons_silver": 180.0,
    "macro_euro_cpi_yoy": 120.0,
    "macro_euro_ppi_mom": 120.0,
    "macro_global_sox_index": 240.0,
    "macro_shipping_bdi": 120.0,
    "macro_shipping_bpi": 120.0,
    "macro_usa_api_crude_stock": 120.0,
    "macro_usa_cb_consumer_confidence": 120.0,
    "macro_usa_core_pce_price": 120.0,
    "macro_usa_eia_crude_rate": 150.0,
    "macro_usa_exist_home_sales": 120.0,
    "macro_usa_house_starts": 120.0,
    "macro_usa_industrial_production": 120.0,
    "macro_usa_initial_jobless": 180.0,
    "macro_usa_ism_pmi": 120.0,
    "macro_usa_michigan_consumer_sentiment": 120.0,
    "macro_usa_new_home_sales": 120.0,
    "macro_usa_personal_spending": 120.0,
}
_ALLOW_EMPTY_TARGET_TABLE_SCRIPT_IDS = {
    "akshare_catalog_endpoint",
    "akshare_catalog_batch",
}


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
        project_app_dir = Path(__file__).resolve().parents[2]
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
        script_row: Any = script
        script_row.updated_by = operator_id
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
        script_row: Any = script
        script_row.is_active = not script.is_active
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

        module_name = str(interface.module_path or "akshare")
        function_name = str(interface.function_name or interface.name)
        module = importlib.import_module(module_name)
        candidate = getattr(module, function_name, None)
        return candidate if callable(candidate) else None

    def _resolve_module_callable(self, module: Any, func_name: str) -> Any | None:
        candidate = getattr(module, func_name, None)
        if callable(candidate) and func_name != "main":
            return candidate

        legacy_instance = self._legacy_script_instance(module)
        if legacy_instance is not None:
            for name in (func_name, "fetch_data", "run"):
                candidate = getattr(legacy_instance, name, None)
                if callable(candidate):
                    return candidate

        candidate = getattr(module, func_name, None)
        if callable(candidate):
            return candidate

        for name in ("fetch_data", "run", "main"):
            candidate = getattr(module, name, None)
            if callable(candidate):
                return candidate

        return None

    async def _resolve_callable(self, script: DataScript) -> Any:
        func_name = str(script.function_name or "main")
        if script.source == "akshare" and not script.is_custom:
            if script.module_path:
                try:
                    module = importlib.import_module(str(script.module_path))
                except ModuleNotFoundError:
                    module = None
                if module is not None and getattr(module, "PREFER_LOCAL_SCRIPT", False):
                    candidate = self._resolve_module_callable(module, func_name)
                    if callable(candidate):
                        return candidate

            candidate = await self._resolve_callable_from_interface(script)
            if callable(candidate):
                return candidate

        if script.module_path:
            try:
                module = importlib.import_module(str(script.module_path))
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
        if isinstance(result, pd.Series):
            name = result.name if result.name is not None else "value"
            dataframe = result.to_frame(name=name)
            if result.index.name is not None or not isinstance(result.index, pd.RangeIndex):
                return dataframe.reset_index()
            return dataframe.reset_index(drop=True)
        if isinstance(result, list):
            return pd.DataFrame(result)
        if isinstance(result, dict):
            if "data" in result and isinstance(result["data"], pd.DataFrame):
                return result["data"]
            if "records" in result and isinstance(result["records"], list):
                return pd.DataFrame(result["records"])
            return pd.DataFrame([result])
        raise TypeError("Script result cannot be converted to DataFrame")

    @classmethod
    def _result_is_empty_marker(cls, result: Any) -> bool:
        if result is None or result is False:
            return True
        if isinstance(result, pd.DataFrame | pd.Series):
            return result.empty
        if isinstance(result, list | tuple | set):
            return len(result) == 0
        if isinstance(result, dict):
            if "data" in result:
                return cls._result_is_empty_marker(result["data"])
            if "records" in result:
                return cls._result_is_empty_marker(result["records"])
        return False

    @classmethod
    def _raise_if_empty_completion(
        cls,
        *,
        script_id: str,
        table_name: str | None,
        rows_before: int | None,
        rows_after: int | None,
        result: Any,
    ) -> None:
        if int(rows_before or 0) > 0 or int(rows_after or 0) > 0:
            return
        if script_id in _ALLOW_EMPTY_TARGET_TABLE_SCRIPT_IDS:
            return
        target = table_name or script_id
        detail = "returned no data" if cls._result_is_empty_marker(result) else "left no rows"
        raise RuntimeError(f"Script {script_id} {detail} and target table {target} is empty")

    @staticmethod
    def _script_timeout_seconds(
        script: DataScript | None = None,
        timeout_seconds: int | float | None = None,
    ) -> float:
        script_id = getattr(script, "script_id", None) if script is not None else None
        min_timeout = _SCRIPT_MIN_TIMEOUT_SECONDS.get(script_id, 0.0)
        if timeout_seconds is not None and float(timeout_seconds) > 0:
            return max(float(timeout_seconds), min_timeout)
        script_timeout = getattr(script, "timeout", None) if script is not None else None
        if script_timeout is not None and float(script_timeout) > 0:
            return max(float(script_timeout), min_timeout)
        raw_timeout = os.getenv("AKSHARE_SCRIPT_TIMEOUT") or os.getenv(
            "AKSHARE_CALL_TIMEOUT", "60"
        )
        try:
            return max(float(raw_timeout), min_timeout)
        except ValueError:
            return max(60.0, min_timeout)

    @staticmethod
    async def _execute_callable(
        callable_obj: Any, params: dict[str, Any], timeout_s: float
    ) -> Any:
        configure_akshare_network_proxy()
        if inspect.iscoroutinefunction(callable_obj):
            awaitable = callable_obj(**params)
        else:
            awaitable = asyncio.to_thread(callable_obj, **params)

        try:
            return await asyncio.wait_for(awaitable, timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            raise asyncio.TimeoutError(
                f"Script call timed out after {timeout_s:g} seconds"
            ) from exc

    @staticmethod
    def _normalize_parameters(parameters: Any) -> dict[str, Any]:
        if parameters is None:
            return {}
        if isinstance(parameters, dict):
            return parameters
        if isinstance(parameters, str):
            raw = parameters.strip()
            if not raw:
                return {}
            parsed: Any = raw
            for _ in range(2):
                if isinstance(parsed, dict):
                    return parsed
                if not isinstance(parsed, str):
                    break
                parsed = json.loads(parsed)
            if isinstance(parsed, dict):
                return parsed
        raise TypeError("Script parameters must be a JSON object")

    @staticmethod
    def _apply_safe_default_parameters(script_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
        today = datetime.now().strftime("%Y%m%d")
        lookback_30 = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        lookback_730 = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
        now_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lookback_1_dt = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        current_year = str(datetime.now().year)
        current_month = datetime.now().strftime("%Y%m")
        now = datetime.now()
        recent_sgx_date = (now - timedelta(days=2)).strftime("%Y%m%d")
        if now.month >= 11:
            latest_report_date = f"{now.year}0930"
            latest_report_quarter = f"{now.year}3"
        elif now.month >= 8:
            latest_report_date = f"{now.year}0630"
            latest_report_quarter = f"{now.year}2"
        elif now.month >= 5:
            latest_report_date = f"{now.year}0331"
            latest_report_quarter = f"{now.year}1"
        else:
            latest_report_date = f"{now.year - 1}1231"
            latest_report_quarter = f"{now.year - 1}4"
        notice_lookback_days = 3 if now.weekday() == 0 else 1
        recent_notice_date = (now - timedelta(days=notice_lookback_days)).strftime("%Y%m%d")
        safe_defaults = {
            "bond_buy_back_hist_em": {
                "symbol": "204001",
                "_call_timeout": 60,
            },
            "bond_info_detail_cm": {
                "symbol": "淮安农商行CDSD2022021012",
                "_call_timeout": 60,
            },
            "bond_info_cm": {"max_pages": 1, "_call_timeout": 90},
            "bond_zh_hs_spot": {
                "start_page": "1",
                "end_page": "1",
                "_call_timeout": 60,
            },
            "bond_zh_hs_cov_min": {
                "symbol": "sh110074",
                "period": "1",
                "_call_timeout": 30,
            },
            "air_quality_watch_point": {
                "city": "北京",
                "start_date": "20220408",
                "end_date": "20220409",
                "_call_timeout": 60,
            },
            "amac_aoin_info": {"_call_timeout": 60},
            "amac_fund_abs": {"max_pages": 1, "_call_timeout": 60},
            "amac_fund_account_info": {"max_pages": 1, "_call_timeout": 60},
            "amac_fund_info": {
                "start_page": "1",
                "end_page": "1",
                "_call_timeout": 60,
            },
            "amac_fund_sub_info": {"max_pages": 1, "_call_timeout": 60},
            "amac_futures_info": {"max_pages": 1, "_call_timeout": 60},
            "amac_manager_cancelled_info": {"max_pages": 1, "_call_timeout": 60},
            "amac_manager_classify_info": {
                "start_page": "1",
                "end_page": "1",
                "_call_timeout": 60,
            },
            "amac_manager_info": {
                "start_page": "1",
                "end_page": "1",
                "_call_timeout": 60,
            },
            "amac_member_info": {
                "start_page": "1",
                "end_page": "1",
                "_call_timeout": 60,
            },
            "amac_member_sub_info": {"max_pages": 1, "_call_timeout": 60},
            "amac_securities_info": {"max_pages": 1, "_call_timeout": 60},
            "article_rlab_rv": {
                "symbol": "39693",
                "_call_timeout": 60,
            },
            "bank_fjcf_table_detail": {
                "page": 1,
                "item": "分局本级",
                "begin": 1,
                "_call_timeout": 60,
            },
            "get_cffex_rank_table": {
                "date": "20240223",
                "_call_timeout": 60,
            },
            "get_receipt": {
                "start_date": "20240223",
                "end_date": "20240223",
                "vars_list": ["CU", "AL"],
                "_call_timeout": 60,
            },
            "get_rank_table_czce": {
                "date": "20240223",
                "_call_timeout": 60,
            },
            "get_roll_yield": {
                "date": "20240223",
                "var": "CU",
                "_call_timeout": 60,
            },
            "get_shfe_rank_table": {
                "date": "20240223",
                "vars_list": ["CU", "AL"],
                "_call_timeout": 60,
            },
            "fx_quote_baidu": {
                "symbol": "人民币",
                "_call_timeout": 60,
            },
            "get_us_stock_name": {
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "hurun_rank": {
                "indicator": "胡润百富榜",
                "year": "2023",
                "_call_timeout": 60,
            },
            "macro_bank_english_interest_rate": {"_call_timeout": 60},
            "macro_china_bond_public": {"_call_timeout": 120},
            "macro_china_trade_balance": {"_call_timeout": 60},
            "macro_euro_cpi_yoy": {"_call_timeout": 90},
            "macro_euro_ppi_mom": {"_call_timeout": 90},
            "macro_global_sox_index": {"_call_timeout": 180},
            "macro_usa_non_farm": {"_call_timeout": 60},
            "macro_usa_trade_balance": {"_call_timeout": 60},
            "macro_usa_unemployment_rate": {"_call_timeout": 60},
            "macro_shipping_bdi": {"_call_timeout": 90},
            "macro_shipping_bpi": {"_call_timeout": 90},
            "migration_area_baidu": {
                "area": "重庆市",
                "indicator": "move_in",
                "date": "20240601",
                "_call_timeout": 60,
            },
            "spot_hog_three_way_soozhu": {"_call_timeout": 60},
            "spot_hog_year_trend_soozhu": {"_call_timeout": 60},
            "spot_mixed_feed_soozhu": {"_call_timeout": 60},
            "stock_hold_management_detail_em": {"max_pages": 5},
            "stock_gdfx_holding_teamwork_em": {
                "symbol": "社保",
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gdfx_holding_change_em": {
                "date": latest_report_date,
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gdfx_free_holding_analyse_em": {
                "date": latest_report_date,
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gdfx_free_holding_change_em": {
                "date": latest_report_date,
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gdfx_free_holding_detail_em": {
                "date": latest_report_date,
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gdfx_free_holding_statistics_em": {
                "date": latest_report_date,
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gdfx_free_holding_teamwork_em": {
                "symbol": "社保",
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gdfx_holding_detail_em": {
                "date": latest_report_date,
                "indicator": "个人",
                "symbol": "新进",
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gdfx_holding_statistics_em": {
                "date": latest_report_date,
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_jgdy_detail_em": {
                "date": "20240601",
                "max_pages": 3,
                "_call_timeout": 90,
            },
            "stock_jgdy_tj_em": {
                "date": "20240601",
                "max_pages": 3,
                "_call_timeout": 120,
            },
            "stock_sns_sseinfo": {
                "symbol": "600000",
                "uid": "65",
                "max_pages": 3,
                "_call_timeout": 120,
            },
            "stock_zh_a_gdhs": {
                "symbol": latest_report_date,
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_zh_kcb_report_em": {"to_page": 10},
            "stock_hot_deal_xq": {
                "symbol": "最热门",
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_concept_cons_futu": {
                "symbol": "特朗普概念股",
                "_call_timeout": 60,
            },
            "stock_hot_rank_em": {"page_size": 100, "_call_timeout": 60},
            "stock_industry_clf_hist_sw": {"_call_timeout": 60},
            "stock_sse_deal_daily": {
                "date": "20241216",
                "_call_timeout": 60,
            },
            "forex_hist_em": {"symbol": "USDCNH", "_call_timeout": 8},
            "stock_share_hold_change_szse": {
                "symbol": "全部",
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_board_industry_min_em": {"max_symbols": 3, "period": "1"},
            "etf_minute_hist_em": {"max_codes": 20},
            "fund_dividend_em": {"max_codes": 5},
            "fund_detail_info": {"max_codes": 20},
            "fund_fee_em": {"limit": 1},
            "fund_portfolio_hold_em": {
                "fund_code": "000001",
                "year": "2024",
            },
            "fund_split_em": {"max_codes": 5},
            "fund_report_industry_allocation_cninfo": {
                "date": latest_report_date,
                "_call_timeout": 60,
            },
            "fund_report_stock_cninfo": {
                "date": latest_report_date,
                "_call_timeout": 60,
            },
            "fund_announcement_personnel_em": {
                "symbol": "000001",
            },
            "fund_individual_analysis_xq": {
                "fund_code": "000001",
            },
            "hk_fund_dividend_em": {
                "fund_code": "1002200683",
                "limit": 1,
            },
            "fund_portfolio_change_em": {
                "fund_code": "003567",
                "indicator": "累计买入",
                "year": "2023",
            },
            "fund_rating_ja": {"date": "20230331"},
            "fund_rating_sh": {"date": "20230630"},
            "fund_rating_zs": {"date": "20230331"},
            "fund_value_estimation_em": {
                "fund_type": "全部",
            },
            "fund_etf_fund_info_em": {
                "fund": "510300",
                "start_date": lookback_730,
                "end_date": today,
                "_call_timeout": 90,
            },
            "fund_etf_hist_em": {
                "symbol": "510300",
                "period": "daily",
                "start_date": lookback_30,
                "end_date": today,
                "adjust": "",
                "_call_timeout": 60,
            },
            "fund_etf_hist_min_em": {
                "symbol": "510300",
                "start_date": lookback_1_dt,
                "end_date": now_dt,
                "period": "5",
                "adjust": "",
                "_call_timeout": 60,
            },
            "fund_dividend_rank_em": {"max_pages": 5},
            "fund_lof_hist_min_em": {
                "symbol": "166009",
                "start_date": lookback_1_dt,
                "end_date": now_dt,
                "period": "5",
                "adjust": "",
                "_call_timeout": 60,
            },
            "fund_lof_hist_em": {
                "symbol": "166009",
                "period": "daily",
                "start_date": lookback_30,
                "end_date": today,
                "adjust": "",
                "_call_timeout": 8,
            },
            "lof_minute_hist_em": {"max_codes": 20},
            "graded_fund_hist_em": {
                "fund_codes": ["150232"],
                "max_pages": 1,
            },
            "money_fund_hist_em": {
                "fund_codes": ["000009"],
                "max_pages": 1,
            },
            "open_fund_hist_em": {"max_codes": 2, "indicators": ["unit_nav"]},
            "option_hist_czce": {
                "symbol": "白糖期权",
                "trade_date": "20191017",
                "_call_timeout": 60,
            },
            "option_hist_shfe": {
                "symbol": "铝期权",
                "trade_date": "20250418",
                "_call_timeout": 60,
            },
            "option_hist_yearly_czce": {
                "symbol": "SR",
                "year": str(now.year - 1),
                "_call_timeout": 120,
            },
            "option_current_em": {"max_pages": 1, "include_cffex": True, "_call_timeout": 60},
            "option_minute_em": {
                "max_current_pages": 1,
                "include_cffex": True,
                "_call_timeout": 60,
            },
            "option_cffex_hs300_list_sina": {"_call_timeout": 30},
            "option_cffex_sz50_list_sina": {"_call_timeout": 30},
            "option_cffex_zz1000_list_sina": {"_call_timeout": 30},
            "option_comm_info": {
                "symbol": "工业硅期权",
                "_call_timeout": 60,
            },
            "option_comm_symbol": {"_call_timeout": 30},
            "option_contract_info_ctp": {"_call_timeout": 60},
            "option_sse_codes_sina": {
                "symbol": "看涨期权",
                "trade_date": current_month,
                "underlying": "510050",
                "_call_timeout": 30,
            },
            "option_sse_expire_day_sina": {
                "trade_date": current_month,
                "symbol": "50ETF",
                "exchange": "null",
                "_call_timeout": 30,
            },
            "option_sse_list_sina": {
                "symbol": "50ETF",
                "exchange": "null",
                "_call_timeout": 30,
            },
            "option_sse_minute_sina": {
                "option_type": "看涨期权",
                "trade_date": current_month,
                "underlying": "510050",
                "_call_timeout": 60,
            },
            "reits_hist_em": {"max_symbols": 3},
            "minute_market": {"max_symbols": 5, "max_workers": 2},
            "shfe_delivery_data": {"lookback_months": 3, "max_months": 1, "sleep_seconds": 0},
            "czce_delivery_data": {"lookback_days": 10, "max_days": 1, "sleep_seconds": 0},
            "czce_to_spot": {
                "start_date": "20231228",
                "end_date": "20231228",
                "max_days": 1,
            },
            "daily_market_data": {"markets": "CFFEX", "lookback_days": 10, "max_windows": 1},
            "futures_contract_info_cffex": {
                "lookback_days": 10,
                "max_days": 1,
                "sleep_seconds": 0,
            },
            "futures_contract_info_czce": {
                "lookback_days": 10,
                "max_days": 1,
                "sleep_seconds": 0,
            },
            "futures_contract_info_ine": {
                "lookback_days": 10,
                "max_days": 1,
                "sleep_seconds": 0,
            },
            "futures_contract_info_shfe": {
                "lookback_days": 10,
                "max_days": 1,
                "sleep_seconds": 0,
            },
            "futures_delivery_match_czce": {"lookback_days": 10, "max_days": 1},
            "futures_display_main_sina": {"_call_timeout": 60},
            "futures_gfex_position_rank": {
                "date": "20240223",
                "vars_list": ["SI", "LC"],
                "_call_timeout": 60,
            },
            "futures_hist_table_em": {"_call_timeout": 60},
            "futures_hold_pos_sina": {
                "symbol": "成交量",
                "contract": "RB2405",
                "date": "20240223",
                "_call_timeout": 60,
            },
            "futures_foreign_commodity_realtime": {
                "_call_timeout": 60,
            },
            "futures_foreign_commodity_subscribe_exchange_symbol": {
                "_call_timeout": 30,
            },
            "futures_hist_em": {
                "symbol": "热卷主连",
                "period": "daily",
                "start_date": lookback_30,
                "end_date": today,
                "_call_timeout": 8,
            },
            "futures_settlement_price_sgx": {
                "date": recent_sgx_date,
                "_call_timeout": 60,
            },
            "futures_shfe_warehouse_receipt": {
                "date": "20240223",
                "_call_timeout": 60,
            },
            "futures_warehouse_receipt_czce": {
                "date": "20240223",
                "_call_timeout": 60,
            },
            "futures_zh_spot": {
                "symbol": "RB0",
                "market": "CF",
                "adjust": "0",
                "_call_timeout": 30,
            },
            "inventory_data": {"max_symbols": 5},
            "member_position_rank": {
                "exchanges": "郑商所,中金所,广期所,上期所",
                "start_date": "2024-02-23",
                "end_date": "2024-02-23",
            },
            "rank_sum_daily": {"max_symbols": 2, "lookback_days": 10, "sleep_seconds": 0},
            "shfe_stock_weekly": {
                "lookback_days": 30,
                "max_reports": 1,
                "sleep_seconds": 0,
            },
            "trading_rules": {"lookback_days": 10, "max_days": 1},
            "warehouse_receipt_czce": {
                "start_date": "20240223",
                "end_date": "20240223",
                "max_days": 1,
            },
            "warehouse_receipt_dce": {"lookback_days": 7, "max_days": 1},
            "index_constituent_weights_csindex": {"max_symbols": 3, "max_workers": 2},
            "index_daily_market_cni": {
                "max_symbols": 3,
                "lookback_days": 30,
                "max_workers": 2,
            },
            "index_detail_cni": {"max_symbols": 3, "max_months": 1},
            "index_global_hist_em": {"max_indices": 3},
            "index_global_hist_sina": {"max_indices": 3},
            "index_hist_adjust_cni": {"max_symbols": 3, "max_workers": 2},
            "index_zh_a_hist": {
                "symbol": "000300",
                "period": "daily",
                "start_date": lookback_30,
                "end_date": today,
                "_call_timeout": 60,
            },
            "index_zh_a_hist_min_em": {
                "max_symbols": 5,
                "period": "1",
                "start_date": lookback_1_dt,
                "end_date": now_dt,
                "_call_timeout": 10,
            },
            "sw_fund_index_historical": {"max_symbols": 3, "max_workers": 2},
            "sw_index_analysis_daily": {"lookback_days": 30, "max_workers": 2},
            "sw_index_components": {"max_symbols": 3, "max_workers": 2},
            "sw_index_historical": {"max_symbols": 3, "max_workers": 2},
            "sw_index_minute": {"max_symbols": 3, "max_workers": 2},
            "sw_industry_third_cons": {"max_codes": 3, "max_workers": 2},
            "stock_hk_index_daily_em": {"max_symbols": 5},
            "stock_hk_index_daily_sina": {"max_symbols": 5},
            "stock_zh_index_daily": {"max_symbols": 5},
            "stock_zh_index_daily_em": {
                "max_symbols": 5,
                "lookback_days": 30,
                "max_workers": 2,
            },
            "stock_zh_index_daily_tx": {"max_symbols": 1},
            "stock_us_daily": {"symbol": "AAPL", "adjust": ""},
            "stock_us_hist_min_em": {
                "symbol": "105.AAPL",
                "start_date": "1979-09-01 09:32:00",
                "end_date": "2222-01-01 09:32:00",
            },
            "stock_us_hist": {
                "symbol": "105.MSFT",
                "period": "daily",
                "start_date": lookback_30,
                "end_date": today,
                "adjust": "",
            },
            "stock_us_spot": {"max_pages": 1},
            "stock_us_spot_em": {"max_pages": 1, "_call_timeout": 60},
            "stock_bj_a_spot_em": {"_call_timeout": 120},
            "stock_board_concept_spot_em": {
                "symbol": "数据要素",
                "_call_timeout": 120,
            },
            "stock_board_change_em": {"_call_timeout": 60},
            "stock_board_concept_cons_em": {
                "symbol": "数据要素",
                "_call_timeout": 60,
            },
            "stock_board_concept_hist_em": {
                "symbol": "数据要素",
                "period": "daily",
                "start_date": lookback_30,
                "end_date": today,
                "adjust": "",
                "_call_timeout": 8,
            },
            "stock_board_concept_hist_min_em": {
                "symbol": "长寿药",
                "period": "5",
                "_call_timeout": 60,
            },
            "stock_board_industry_hist_em": {
                "symbol": "BK1027",
                "period": "日k",
                "start_date": lookback_30,
                "end_date": today,
                "adjust": "",
                "_call_timeout": 8,
            },
            "stock_board_industry_hist_min_em": {
                "symbol": "小金属",
                "period": "1",
                "_call_timeout": 60,
            },
            "stock_changes_em": {
                "symbol": "大笔买入",
                "_call_timeout": 60,
            },
            "stock_cy_a_spot_em": {"_call_timeout": 180},
            "stock_hk_hist": {
                "symbol": "00700",
                "period": "daily",
                "start_date": lookback_30,
                "end_date": today,
                "adjust": "",
            },
            "stock_hk_hist_min_em": {
                "symbol": "00700",
                "period": "1",
                "adjust": "",
                "start_date": lookback_1_dt,
                "end_date": now_dt,
                "_call_timeout": 60,
            },
            "stock_hk_main_board_spot_em": {"_call_timeout": 180},
            "stock_hk_spot": {"_call_timeout": 120},
            "stock_hk_spot_em": {"_call_timeout": 180},
            "stock_hk_hot_rank_latest_em": {
                "symbol": "00700",
                "_call_timeout": 90,
            },
            "stock_hk_indicator_eniu": {
                "symbol": "hk01093",
                "indicator": "市盈率",
                "_call_timeout": 90,
            },
            "stock_hk_profit_forecast_et": {
                "symbol": "00700",
                "indicator": "盈利预测概览",
                "_call_timeout": 90,
            },
            "stock_hot_search_baidu": {
                "symbol": "A股",
                "date": today,
                "time": "今日",
                "_call_timeout": 60,
            },
            "stock_hot_tweet_xq": {
                "symbol": "最热门",
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_hot_follow_xq": {
                "symbol": "最热门",
                "max_pages": 30,
                "_call_timeout": 90,
            },
            "stock_hot_up_em": {"page_size": 100, "_call_timeout": 60},
            "stock_hk_hot_rank_em": {"page_size": 100, "_call_timeout": 60},
            "stock_main_fund_flow": {"symbol": "全部股票", "_call_timeout": 240},
            "stock_info_a_code_name": {"_call_timeout": 60},
            "stock_info_bj_name_code": {"_call_timeout": 60},
            "stock_individual_info_em": {
                "symbol": "000001",
                "timeout": 20,
                "_call_timeout": 60,
            },
            "stock_bid_ask_em": {"symbol": "000001", "_call_timeout": 60},
            "stock_individual_basic_info_xq": {
                "symbol": "SH600519",
                "timeout": 20,
                "_call_timeout": 60,
            },
            "stock_individual_basic_info_hk_xq": {
                "symbol": "00700",
                "timeout": 20,
                "_call_timeout": 60,
            },
            "stock_individual_basic_info_us_xq": {
                "symbol": "NVDA",
                "timeout": 20,
                "_call_timeout": 60,
            },
            "stock_individual_fund_flow_rank": {
                "indicator": "今日",
                "_call_timeout": 180,
            },
            "stock_industry_category_cninfo": {
                "symbol": "巨潮行业分类标准",
                "_call_timeout": 60,
            },
            "stock_industry_change_cninfo": {
                "symbol": "002594",
                "start_date": "20091227",
                "end_date": today,
                "_call_timeout": 60,
            },
            "stock_zh_a_daily": {
                "symbol": "sh600000",
                "start_date": lookback_30,
                "end_date": today,
                "adjust": "",
                "_call_timeout": 60,
            },
            "stock_zh_a_cdr_daily": {
                "symbol": "sh689009",
                "start_date": lookback_30,
                "end_date": today,
                "_call_timeout": 60,
            },
            "stock_sh_a_spot_em": {"_call_timeout": 180},
            "stock_sgt_reference_exchange_rate_sse": {"_call_timeout": 60},
            "stock_sgt_reference_exchange_rate_szse": {"_call_timeout": 60},
            "stock_sgt_settlement_exchange_rate_sse": {"_call_timeout": 60},
            "stock_sgt_settlement_exchange_rate_szse": {"_call_timeout": 60},
            "stock_sz_a_spot_em": {"_call_timeout": 180},
            "stock_staq_net_stop": {"_call_timeout": 60},
            "stock_zh_a_spot": {"_call_timeout": 90},
            "stock_zh_a_spot_em": {"_call_timeout": 240},
            "stock_zh_a_disclosure_relation_cninfo": {
                "symbol": "000001",
                "market": "沪深京",
                "start_date": lookback_730,
                "end_date": today,
                "_call_timeout": 120,
            },
            "stock_zh_a_disclosure_report_cninfo": {
                "symbol": "000001",
                "market": "沪深京",
                "start_date": lookback_730,
                "end_date": today,
                "_call_timeout": 120,
            },
            "stock_zh_a_hist": {
                "symbol": "000001",
                "period": "daily",
                "start_date": lookback_30,
                "end_date": today,
                "adjust": "",
                "_call_timeout": 60,
            },
            "stock_zh_a_hist_tx": {
                "symbol": "sz000001",
                "start_date": lookback_30,
                "end_date": today,
                "adjust": "",
                "_call_timeout": 60,
            },
            "stock_zh_a_hist_min_em": {
                "symbol": "000001",
                "start_date": lookback_1_dt,
                "end_date": now_dt,
                "period": "1",
                "adjust": "",
                "_call_timeout": 60,
            },
            "stock_zh_a_hist_pre_min_em": {
                "symbol": "000001",
                "start_time": "09:30:00",
                "end_time": "15:00:00",
                "_call_timeout": 60,
            },
            "stock_zh_a_gbjg_em": {
                "symbol": "600519.SH",
                "_call_timeout": 60,
            },
            "stock_zh_a_gdhs_detail_em": {
                "symbol": "000001",
                "_call_timeout": 60,
            },
            "stock_zh_a_minute": {"symbol": "sh600519", "period": "1", "adjust": ""},
            "stock_zh_a_tick_tx_js": {
                "symbol": "sz000001",
                "_call_timeout": 120,
            },
            "stock_zh_ah_daily": {
                "symbol": "02318",
                "start_year": str(now.year - 1),
                "end_year": current_year,
                "adjust": "",
                "_call_timeout": 60,
            },
            "stock_zh_b_daily": {
                "symbol": "sh900901",
                "start_date": lookback_30,
                "end_date": today,
                "adjust": "",
                "_call_timeout": 60,
            },
            "stock_zh_b_minute": {
                "symbol": "sh900901",
                "period": "1",
                "adjust": "",
                "_call_timeout": 60,
            },
            "stock_zh_kcb_daily": {
                "symbol": "sh688399",
                "adjust": "",
                "_call_timeout": 60,
            },
            "stock_balance_sheet_by_report_delisted_em": {
                "symbol": "SZ000013",
                "_call_timeout": 90,
            },
            "stock_cash_flow_sheet_by_quarterly_em": {
                "symbol": "SH600519",
                "_call_timeout": 180,
            },
            "stock_concept_fund_flow_hist": {
                "symbol": "数据要素",
                "_call_timeout": 120,
            },
            "stock_comment_em": {"_call_timeout": 90},
            "stock_comment_detail_scrd_desire_daily_em": {
                "symbol": "600000",
                "_call_timeout": 60,
            },
            "stock_cyq_em": {
                "symbol": "600519",
                "adjust": "",
                "_call_timeout": 60,
            },
            "stock_dzjy_hygtj": {
                "symbol": "近三月",
                "_call_timeout": 60,
            },
            "stock_dzjy_hyyybtj": {
                "symbol": "近3日",
                "_call_timeout": 60,
            },
            "stock_dzjy_mrtj": {
                "start_date": "20240102",
                "end_date": "20240102",
                "_call_timeout": 60,
            },
            "stock_dzjy_sctj": {"_call_timeout": 60},
            "stock_dzjy_yybph": {
                "symbol": "近三月",
                "_call_timeout": 60,
            },
            "stock_dxsyl_em": {
                "page_size": 400,
                "_call_timeout": 60,
            },
            "stock_ebs_lg": {"_call_timeout": 60},
            "stock_esg_hz_sina": {"_call_timeout": 300},
            "stock_esg_msci_sina": {"_call_timeout": 90},
            "stock_esg_rate_sina": {"max_pages": 3, "_call_timeout": 180},
            "stock_esg_zd_sina": {"_call_timeout": 300},
            "stock_ipo_declare": {"_call_timeout": 90},
            "stock_financial_analysis_indicator": {
                "symbol": "600519",
                "start_year": "2020",
                "_call_timeout": 90,
            },
            "stock_fhps_em": {
                "date": latest_report_date,
                "_call_timeout": 60,
            },
            "stock_hk_ggt_components_em": {"_call_timeout": 60},
            "stock_hk_dividend_payout_em": {
                "symbol": "03900",
                "_call_timeout": 60,
            },
            "stock_hk_fhpx_detail_ths": {
                "symbol": "0700",
                "_call_timeout": 60,
            },
            "stock_hk_gxl_lg": {"_call_timeout": 60},
            "stock_hsgt_hist_em": {
                "symbol": "沪股通",
                "_call_timeout": 120,
            },
            "stock_hsgt_board_rank_em": {
                "symbol": "北向资金增持行业板块排行",
                "indicator": "今日",
                "page_size": 500,
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_hsgt_individual_detail_em": {
                "symbol": "002008",
                "start_date": "20240101",
                "end_date": "20240630",
                "_call_timeout": 90,
            },
            "stock_hsgt_institution_statistics_em": {
                "market": "北向持股",
                "start_date": "20240110",
                "end_date": "20240110",
                "_call_timeout": 60,
            },
            "stock_hold_change_cninfo": {
                "symbol": "全部",
                "_call_timeout": 60,
            },
            "stock_hold_control_cninfo": {
                "symbol": "全部",
                "_call_timeout": 60,
            },
            "stock_hold_num_cninfo": {
                "date": latest_report_date,
                "_call_timeout": 60,
            },
            "stock_gddh_em": {"_call_timeout": 90},
            "stock_ggcg_em": {
                "symbol": "全部",
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gpzy_pledge_ratio_detail_em": {
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gpzy_pledge_ratio_em": {
                "date": "20240906",
                "_call_timeout": 90,
            },
            "stock_gpzy_profile_em": {"_call_timeout": 60},
            "stock_gsrl_gsdt_em": {
                "date": today,
                "_call_timeout": 60,
            },
            "stock_gdfx_holding_analyse_em": {
                "date": latest_report_date,
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_gdfx_top_10_em": {
                "symbol": "sh600519",
                "date": latest_report_date,
                "_call_timeout": 60,
            },
            "stock_lhb_detail_em": {
                "start_date": lookback_30,
                "end_date": today,
                "_call_timeout": 60,
            },
            "stock_lhb_ggtj_sina": {
                "symbol": "5",
                "_call_timeout": 60,
            },
            "stock_lhb_jgstatistic_em": {
                "symbol": "近一月",
                "_call_timeout": 60,
            },
            "stock_lhb_yyb_detail_em": {
                "symbol": "10188715",
                "_call_timeout": 60,
            },
            "stock_lhb_yybph_em": {
                "symbol": "近一月",
                "_call_timeout": 60,
            },
            "stock_lhb_yytj_sina": {
                "symbol": "5",
                "_call_timeout": 90,
            },
            "stock_institute_recommend": {
                "symbol": "最新投资评级",
                "_call_timeout": 60,
            },
            "stock_institute_hold_detail": {
                "stock": "600519",
                "quarter": latest_report_quarter,
                "_call_timeout": 60,
            },
            "stock_intraday_em": {
                "symbol": "000001",
                "_call_timeout": 60,
            },
            "stock_intraday_sina": {
                "symbol": "sz000001",
                "_call_timeout": 60,
            },
            "stock_margin_account_info": {"_call_timeout": 60},
            "stock_margin_ratio_pa": {
                "symbol": "深市",
                "date": today,
                "_call_timeout": 60,
            },
            "stock_notice_report": {
                "symbol": "全部",
                "date": recent_notice_date,
                "_call_timeout": 90,
            },
            "stock_profit_forecast_em": {
                "symbol": "",
                "_call_timeout": 90,
            },
            "stock_profit_forecast_ths": {
                "symbol": "600519",
                "indicator": "预测年报每股收益",
                "_call_timeout": 60,
            },
            "stock_profit_sheet_by_quarterly_em": {
                "symbol": "SH600519",
                "_call_timeout": 180,
            },
            "stock_profit_sheet_by_yearly_em": {
                "symbol": "SH600519",
                "_call_timeout": 120,
            },
            "stock_pg_em": {"_call_timeout": 60},
            "stock_qbzf_em": {"_call_timeout": 90},
            "stock_register_bj": {"_call_timeout": 60},
            "stock_register_cyb": {"_call_timeout": 60},
            "stock_register_db": {"_call_timeout": 60},
            "stock_register_kcb": {"_call_timeout": 60},
            "stock_register_sh": {"_call_timeout": 60},
            "stock_register_sz": {"_call_timeout": 60},
            "stock_repurchase_em": {"_call_timeout": 240},
            "stock_restricted_release_detail_em": {
                "start_date": lookback_30,
                "end_date": today,
                "_call_timeout": 60,
            },
            "stock_restricted_release_queue_em": {
                "symbol": "600000",
                "_call_timeout": 60,
            },
            "stock_research_report_em": {
                "symbol": "000001",
                "_call_timeout": 60,
            },
            "stock_sector_fund_flow_hist": {
                "symbol": "有色金属",
                "_call_timeout": 120,
            },
            "stock_sector_fund_flow_summary": {
                "symbol": "非银金融",
                "indicator": "今日",
                "_call_timeout": 90,
            },
            "stock_sector_detail": {
                "sector": "gn_gfgn",
                "_call_timeout": 60,
            },
            "stock_zh_growth_comparison_em": {
                "symbol": "SZ000895",
                "_call_timeout": 60,
            },
            "stock_zh_index_value_csindex": {
                "symbol": "H30374",
                "_call_timeout": 60,
            },
            "stock_zh_index_hist_csindex": {
                "symbol": "000928",
                "start_date": lookback_30,
                "end_date": today,
                "_call_timeout": 60,
            },
            "stock_zh_scale_comparison_em": {
                "symbol": "SZ000895",
                "_call_timeout": 60,
            },
            "stock_zh_valuation_baidu": {
                "symbol": "002044",
                "indicator": "总市值",
                "period": "近一年",
                "_call_timeout": 60,
            },
            "stock_zh_valuation_comparison_em": {
                "symbol": "SZ000895",
                "_call_timeout": 60,
            },
            "stock_zh_vote_baidu": {
                "symbol": "000001",
                "indicator": "指数",
                "_call_timeout": 60,
            },
            "stock_hold_management_detail_cninfo": {
                "symbol": "增持",
                "_call_timeout": 60,
            },
            "stock_share_hold_change_bse": {
                "symbol": "430489",
                "_call_timeout": 60,
            },
            "stock_share_hold_change_sse": {
                "symbol": "600000",
                "_call_timeout": 60,
            },
            "stock_shareholder_change_ths": {
                "symbol": "688981",
                "_call_timeout": 60,
            },
            "stock_rank_cxd_ths": {
                "symbol": "创月新低",
                "max_pages": 1,
                "_call_timeout": 60,
            },
            "stock_rank_xstp_ths": {
                "symbol": "500日均线",
                "_call_timeout": 90,
            },
            "stock_rank_xxtp_ths": {
                "symbol": "500日均线",
                "_call_timeout": 90,
            },
            "stock_sy_em": {
                "date": latest_report_date,
                "_call_timeout": 90,
            },
            "stock_sy_hy_em": {
                "date": latest_report_date,
                "_call_timeout": 60,
            },
            "stock_sy_jz_em": {
                "date": latest_report_date,
                "_call_timeout": 90,
            },
            "stock_tfp_em": {
                "date": today,
                "_call_timeout": 60,
            },
            "stock_yysj_em": {"_call_timeout": 240},
            "stock_yzxdr_em": {
                "date": latest_report_date,
                "_call_timeout": 90,
            },
            "stock_zcfz_bj_em": {
                "date": latest_report_date,
                "_call_timeout": 60,
            },
            "stock_xgsglb_em": {
                "symbol": "全部股票",
                "_call_timeout": 60,
            },
            "stock_xgsr_ths": {"_call_timeout": 240},
            "stock_zdhtmx_em": {
                "start_date": lookback_730,
                "end_date": today,
                "_call_timeout": 90,
            },
            "stock_zh_kcb_report_em": {
                "from_page": 1,
                "to_page": 3,
                "_call_timeout": 60,
            },
            "stock_zh_ab_comparison_em": {"_call_timeout": 60},
            "stock_zh_ah_name": {"_call_timeout": 60},
            "stock_zh_a_new": {"_call_timeout": 60},
            "stock_zygc_em": {
                "symbol": "SH600519",
                "_call_timeout": 60,
            },
            "stock_zyjs_ths": {
                "symbol": "600519",
                "_call_timeout": 60,
            },
            "stock_zt_pool_dtgc_em": {"date": today},
            "stock_zt_pool_em": {"date": today},
            "stock_zt_pool_strong_em": {"date": today},
            "stock_zt_pool_sub_new_em": {"date": today},
            "stock_zt_pool_zbgc_em": {"date": today},
            "akshare_catalog_endpoint": {
                "endpoint_name": "air_city_table",
                "target_table": "akshare_catalog_endpoint",
                "call_timeout": 30,
            },
        }
        defaults = safe_defaults.get(script_id)
        if defaults is None:
            return parameters
        merged = dict(defaults)
        merged.update(parameters)
        return merged

    @staticmethod
    def _legacy_table_name(script: DataScript) -> str | None:
        if not script.target_table:
            return None
        return AkshareDataService.normalize_existing_table_name(script.target_table)

    @staticmethod
    def _legacy_callable_table_name(callable_obj: Any) -> str | None:
        owner = getattr(callable_obj, "__self__", None)
        if owner is None or not hasattr(owner, "save_data"):
            return None
        table_name = getattr(owner, "table_name", None)
        if not isinstance(table_name, str) or not table_name:
            return None
        return AkshareDataService.normalize_existing_table_name(table_name)

    async def run_script(
        self,
        script_id: str,
        parameters: dict[str, Any] | None = None,
        operator_id: str | None = None,
        task_id: int | None = None,
        triggered_by: TriggeredBy = TriggeredBy.MANUAL,
        timeout_seconds: int | float | None = None,
    ) -> TaskExecution:
        script = await self.get_script(script_id)
        if script is None:
            raise ValueError("Script not found")
        if not script.is_active:
            raise ValueError("Script is not active")

        params = self._apply_safe_default_parameters(
            script.script_id, self._normalize_parameters(parameters)
        )
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
            result = await self._execute_callable(
                callable_obj,
                params,
                self._script_timeout_seconds(script, timeout_seconds=timeout_seconds),
            )

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
                self._raise_if_empty_completion(
                    script_id=script.script_id,
                    table_name=table.table_name,
                    rows_before=rows_before,
                    rows_after=rows_after,
                    result=result,
                )
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
                    self._raise_if_empty_completion(
                        script_id=script.script_id,
                        table_name=table.table_name,
                        rows_before=rows_before,
                        rows_after=rows_after,
                        result=result,
                    )
                else:
                    table = await self.data_service.persist_dataframe(script, dataframe, params)
                    rows_before = dataframe_rows_before
                    rows_after = table.row_count
                    summary = {
                        "table_name": table.table_name,
                        "row_count": table.row_count,
                        "columns": list(dataframe.columns),
                    }
                    self._raise_if_empty_completion(
                        script_id=script.script_id,
                        table_name=table.table_name,
                        rows_before=rows_before,
                        rows_after=rows_after,
                        result=result,
                    )
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
