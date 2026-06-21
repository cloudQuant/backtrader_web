"""
API routes for akshare data tables.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data.deps import get_current_db_user
from app.db.database import get_db
from app.services.akshare.data import AkshareDataService

router = APIRouter()


def _column_names_from_metadata(metadata: object) -> list[str]:
    if not isinstance(metadata, dict):
        return []

    columns = metadata.get("columns")
    if not isinstance(columns, list):
        return []

    names: list[str] = []
    for column in columns:
        if isinstance(column, str):
            names.append(column)
        elif isinstance(column, dict) and isinstance(column.get("name"), str):
            names.append(column["name"])
    return names


def _schema_columns_from_metadata(metadata: object) -> list[dict[str, object]]:
    if not isinstance(metadata, dict):
        return []

    columns = metadata.get("columns")
    if not isinstance(columns, list):
        return []

    schema_columns: list[dict[str, object]] = []
    for column in columns:
        if isinstance(column, str):
            schema_columns.append(
                {"name": column, "type": "unknown", "nullable": True, "default": None}
            )
        elif isinstance(column, dict) and isinstance(column.get("name"), str):
            schema_columns.append(
                {
                    "name": column["name"],
                    "type": str(column.get("type") or "unknown"),
                    "nullable": bool(column.get("nullable", True)),
                    "default": column.get("default"),
                }
            )
    return schema_columns


def _warehouse_error_message(exc: Exception) -> str:
    if isinstance(exc, RuntimeError) and "AKSHARE_DATA_DATABASE_URL" in str(exc):
        return "Akshare data warehouse is not configured"
    if isinstance(exc, ValueError):
        return str(exc)
    return "Akshare data warehouse is unavailable"


@router.get("/tables")
async def list_tables(
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    service = AkshareDataService(db)
    items, total = await service.list_tables(search=search, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/tables/{table_id}")
async def get_table(
    table_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    table = await AkshareDataService(db).get_table(table_id)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


@router.get("/tables/{table_id}/schema")
async def get_table_schema(
    table_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    service = AkshareDataService(db)
    table = await service.get_table(table_id)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    try:
        columns = await service.get_table_schema(table.table_name)
        data_available = True
        error = None
    except (RuntimeError, ValueError, SQLAlchemyError) as exc:
        columns = _schema_columns_from_metadata(table.metadata_json)
        data_available = False
        error = _warehouse_error_message(exc)
    return {
        "table_name": table.table_name,
        "columns": columns,
        "row_count": table.row_count,
        "last_update_time": table.last_update_time,
        "data_available": data_available,
        "error": error,
    }


@router.get("/tables/{table_id}/data")
async def get_table_rows(
    table_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    service = AkshareDataService(db)
    table = await service.get_table(table_id)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    try:
        columns, rows, total = await service.get_table_rows(
            table.table_name,
            page=page,
            page_size=page_size,
        )
        data_available = True
        error = None
    except (RuntimeError, ValueError, SQLAlchemyError) as exc:
        columns = _column_names_from_metadata(table.metadata_json)
        rows = []
        total = 0
        data_available = False
        error = _warehouse_error_message(exc)
    return {
        "table_name": table.table_name,
        "columns": columns,
        "rows": rows,
        "page": page,
        "page_size": page_size,
        "total": total,
        "data_available": data_available,
        "error": error,
    }
