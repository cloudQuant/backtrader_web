"""
Interface bootstrap service for akshare functions.
"""

from __future__ import annotations

import inspect
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akshare_mgmt import (
    DataInterface,
    InterfaceCategory,
    InterfaceParameter,
    ParameterType,
)


class AkshareInterfaceLoader:
    """Explicit bootstrap loader for akshare interface metadata."""

    CATEGORY_MAPPING = {
        "stock": "股票数据",
        "fund": "基金数据",
        "futures": "期货数据",
        "index": "指数数据",
        "bond": "债券数据",
        "forex": "外汇数据",
        "macro": "宏观数据",
        "economic": "经济数据",
    }

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_categories(self) -> dict[str, InterfaceCategory]:
        categories: dict[str, InterfaceCategory] = {}
        sort_order = 1
        for key, label in self.CATEGORY_MAPPING.items():
            result = await self.db.execute(
                select(InterfaceCategory).where(InterfaceCategory.name == key)
            )
            category = result.scalar_one_or_none()
            if category is None:
                category = InterfaceCategory(
                    name=key,
                    description=label,
                    sort_order=sort_order,
                )
                self.db.add(category)
                await self.db.flush()
            categories[key] = category
            sort_order += 1
        return categories

    def _discover_akshare_functions(self) -> list[tuple[str, Any]]:
        import akshare as ak

        functions: list[tuple[str, Any]] = []
        for name in dir(ak):
            if name.startswith("_"):
                continue
            attr = getattr(ak, name)
            if callable(attr):
                functions.append((name, attr))
        return functions

    def _resolve_category(self, name: str) -> str:
        for prefix in self.CATEGORY_MAPPING:
            if name.startswith(prefix):
                return prefix
        return "stock"

    def _map_param_type(self, annotation: Any) -> ParameterType:
        if annotation in {int, "int"}:
            return ParameterType.INTEGER
        if annotation in {float, "float"}:
            return ParameterType.FLOAT
        if annotation in {bool, "bool"}:
            return ParameterType.BOOLEAN
        return ParameterType.STRING

    async def bootstrap(self, refresh: bool = False) -> dict[str, int]:
        categories = await self.ensure_categories()
        created = 0
        updated = 0
        functions = self._discover_akshare_functions()
        for func_name, func in functions:
            category = categories[self._resolve_category(func_name)]
            result = await self.db.execute(
                select(DataInterface).where(DataInterface.name == func_name)
            )
            interface = result.scalar_one_or_none()
            if interface is None:
                interface = DataInterface(
                    name=func_name,
                    display_name=func_name.replace("_", " ").title(),
                    description=(inspect.getdoc(func) or "").splitlines()[0]
                    if inspect.getdoc(func)
                    else None,
                    category_id=category.id,
                    module_path="akshare",
                    function_name=func_name,
                    parameters={},
                    return_type="DataFrame",
                    extra_config={},
                    is_active=True,
                )
                self.db.add(interface)
                await self.db.flush()
                created += 1
            else:
                interface.category_id = category.id
                interface.module_path = "akshare"
                interface.function_name = func_name
                interface.display_name = func_name.replace("_", " ").title()
                updated += 1
                if refresh:
                    await self.db.execute(
                        delete(InterfaceParameter).where(
                            InterfaceParameter.interface_id == interface.id
                        )
                    )

            sig = inspect.signature(func)
            parameters: dict[str, Any] = {}
            for index, (param_name, param) in enumerate(sig.parameters.items()):
                if param_name in {"self", "kwargs"}:
                    continue
                parameters[param_name] = {
                    "required": param.default == inspect.Parameter.empty,
                    "default": None
                    if param.default == inspect.Parameter.empty
                    else str(param.default),
                }
                if interface.id:
                    param_model = InterfaceParameter(
                        interface_id=interface.id,
                        name=param_name,
                        display_name=param_name,
                        param_type=self._map_param_type(param.annotation),
                        description=f"Parameter: {param_name}",
                        default_value=None
                        if param.default == inspect.Parameter.empty
                        else str(param.default),
                        required=param.default == inspect.Parameter.empty,
                        sort_order=index,
                    )
                    self.db.add(param_model)
            interface.parameters = parameters
        await self.db.commit()
        return {"created": created, "updated": updated}
