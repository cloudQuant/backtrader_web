"""
Storage and query service for akshare data warehouse tables.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import func, inspect, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.akshare_data_database import _get_akshare_data_engine
from app.models.akshare_mgmt import DataScript, DataTable

_VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AkshareDataService:
    """Service for persisting and previewing akshare data tables."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
        normalized = re.sub(r"_+", "_", normalized).strip("_").lower()
        if not normalized:
            normalized = "data"
        if normalized[0].isdigit():
            normalized = f"t_{normalized}"
        return normalized

    @staticmethod
    def _validate_table_name(table_name: str) -> str:
        if not _VALID_IDENTIFIER.match(table_name):
            raise ValueError(f"Invalid table name: {table_name}")
        return table_name

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return f"`{AkshareDataService._validate_table_name(identifier)}`"

    def build_table_name(self, script: DataScript, parameters: dict[str, Any]) -> str:
        """Build the physical warehouse table name for one script execution."""
        base_name = script.target_table or script.script_id
        base_name = self._normalize_identifier(base_name)
        symbol = parameters.get("symbol") or parameters.get("code") or parameters.get("ticker")
        if symbol:
            base_name = f"{base_name}_{self._normalize_identifier(str(symbol))}"
        return self._validate_table_name(base_name)

    def normalize_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names and cell values before persistence."""
        normalized = dataframe.copy()
        normalized.columns = [
            self._normalize_identifier(str(column)) for column in normalized.columns
        ]
        normalized = normalized.where(pd.notnull(normalized), None)
        return normalized

    async def get_row_count(self, table_name: str) -> int:
        """Return the current row count of a warehouse table."""
        if _get_akshare_data_engine() is None:
            raise RuntimeError("AKSHARE_DATA_DATABASE_URL is not configured")

        quoted_name = self._quote_identifier(table_name)
        async with _get_akshare_data_engine().connect() as conn:
            try:
                result = await conn.execute(text(f"SELECT COUNT(*) FROM {quoted_name}"))
            except Exception:
                return 0
        return int(result.scalar() or 0)

    def _infer_date_range(self, dataframe: pd.DataFrame) -> tuple[datetime | None, datetime | None]:
        date_like_columns = [
            column
            for column in dataframe.columns
            if column.lower() in {"date", "trade_date", "datetime", "timestamp"}
        ]
        for column in date_like_columns:
            parsed = pd.to_datetime(dataframe[column], errors="coerce")
            parsed = parsed.dropna()
            if not parsed.empty:
                return parsed.min().to_pydatetime(), parsed.max().to_pydatetime()
        return None, None

    async def _upsert_table_metadata(
        self,
        script: DataScript,
        table_name: str,
        row_count: int,
        parameters: dict[str, Any],
        status: str,
        columns: list[str],
        data_start: datetime | None = None,
        data_end: datetime | None = None,
    ) -> DataTable:
        metadata_result = await self.db.execute(
            text("SELECT id FROM ak_data_tables WHERE table_name = :table_name"),
            {"table_name": table_name},
        )
        existing_id = metadata_result.scalar_one_or_none()
        if existing_id is None:
            record = DataTable(
                table_name=table_name,
                table_comment=script.script_name,
                category=script.category,
                script_id=script.script_id,
                row_count=row_count,
                last_update_time=datetime.utcnow(),
                last_update_status=status,
                data_start_date=data_start.date() if data_start else None,
                data_end_date=data_end.date() if data_end else None,
                symbol_raw=str(parameters.get("symbol")) if parameters.get("symbol") else None,
                symbol_normalized=self._normalize_identifier(str(parameters.get("symbol")))
                if parameters.get("symbol")
                else None,
                market=str(parameters.get("market")) if parameters.get("market") else None,
                asset_type=str(parameters.get("asset_type"))
                if parameters.get("asset_type")
                else None,
                metadata_json={"columns": columns},
            )
            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)
            return record

        table = await self.db.get(DataTable, existing_id)
        table.table_comment = script.script_name
        table.category = script.category
        table.script_id = script.script_id
        table.row_count = row_count
        table.last_update_time = datetime.utcnow()
        table.last_update_status = status
        table.data_start_date = data_start.date() if data_start else None
        table.data_end_date = data_end.date() if data_end else None
        table.symbol_raw = str(parameters.get("symbol")) if parameters.get("symbol") else None
        table.symbol_normalized = (
            self._normalize_identifier(str(parameters.get("symbol")))
            if parameters.get("symbol")
            else None
        )
        table.market = str(parameters.get("market")) if parameters.get("market") else None
        table.asset_type = (
            str(parameters.get("asset_type")) if parameters.get("asset_type") else None
        )
        table.metadata_json = {"columns": columns}
        await self.db.commit()
        await self.db.refresh(table)
        return table

    async def sync_existing_table_metadata(
        self,
        script: DataScript,
        table_name: str,
        parameters: dict[str, Any],
        status: str = "success",
    ) -> DataTable:
        normalized_table_name = self._validate_table_name(self._normalize_identifier(table_name))
        row_count = await self.get_row_count(normalized_table_name)
        try:
            schema = await self.get_table_schema(normalized_table_name)
            columns = [column["name"] for column in schema]
        except Exception:
            columns = []
        return await self._upsert_table_metadata(
            script=script,
            table_name=normalized_table_name,
            row_count=row_count,
            parameters=parameters,
            status=status,
            columns=columns,
            data_start=None,
            data_end=None,
        )

    async def persist_dataframe(
        self,
        script: DataScript,
        dataframe: pd.DataFrame,
        parameters: dict[str, Any],
        status: str = "success",
    ) -> DataTable:
        """Persist a dataframe into the warehouse and update metadata."""
        if _get_akshare_data_engine() is None:
            raise RuntimeError("AKSHARE_DATA_DATABASE_URL is not configured")

        normalized_df = self.normalize_dataframe(dataframe)
        table_name = self.build_table_name(script, parameters)
        row_count = len(normalized_df.index)
        data_start, data_end = self._infer_date_range(normalized_df)

        async with _get_akshare_data_engine().begin() as conn:
            await conn.run_sync(
                lambda sync_conn: normalized_df.to_sql(
                    table_name,
                    con=sync_conn,
                    if_exists="replace",
                    index=False,
                )
            )

        return await self._upsert_table_metadata(
            script=script,
            table_name=table_name,
            row_count=row_count,
            parameters=parameters,
            status=status,
            columns=list(normalized_df.columns),
            data_start=data_start,
            data_end=data_end,
        )

    async def list_tables(
        self,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DataTable], int]:
        """List akshare data tables from metadata storage."""
        stmt = select(DataTable)
        count_stmt = select(func.count(DataTable.id))
        if search:
            pattern = f"%{search}%"
            filters = or_(
                DataTable.table_name.ilike(pattern),
                DataTable.table_comment.ilike(pattern),
            )
            stmt = stmt.where(filters)
            count_stmt = count_stmt.where(filters)

        total = int((await self.db.execute(count_stmt)).scalar() or 0)
        stmt = (
            stmt.order_by(DataTable.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_table(self, table_id: int) -> DataTable | None:
        """Get one metadata table by ID."""
        return await self.db.get(DataTable, table_id)

    async def get_table_schema(self, table_name: str) -> list[dict[str, Any]]:
        """Inspect a warehouse table schema."""
        if _get_akshare_data_engine() is None:
            raise RuntimeError("AKSHARE_DATA_DATABASE_URL is not configured")

        self._validate_table_name(table_name)

        async with _get_akshare_data_engine().connect() as conn:
            columns = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_columns(table_name)
            )
        return [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": bool(column.get("nullable", True)),
                "default": column.get("default"),
            }
            for column in columns
        ]

    async def get_table_rows(
        self,
        table_name: str,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[str], list[dict[str, Any]], int]:
        """Preview rows from a warehouse table."""
        if _get_akshare_data_engine() is None:
            raise RuntimeError("AKSHARE_DATA_DATABASE_URL is not configured")

        quoted_name = self._quote_identifier(table_name)
        offset = (page - 1) * page_size

        async with _get_akshare_data_engine().connect() as conn:
            total_result = await conn.execute(text(f"SELECT COUNT(*) FROM {quoted_name}"))
            total = int(total_result.scalar() or 0)
            result = await conn.execute(
                text(f"SELECT * FROM {quoted_name} LIMIT :limit OFFSET :offset"),
                {"limit": page_size, "offset": offset},
            )
            mappings = result.mappings().all()

        rows = [dict(row) for row in mappings]
        columns = list(rows[0].keys()) if rows else []
        return columns, rows, total
