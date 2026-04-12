"""
API routes for akshare data tables.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data_management_deps import get_current_db_user
from app.db.database import get_db
from app.services.akshare_data_service import AkshareDataService

router = APIRouter()


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
    columns = await service.get_table_schema(table.table_name)
    return {
        "table_name": table.table_name,
        "columns": columns,
        "row_count": table.row_count,
        "last_update_time": table.last_update_time,
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
    columns, rows, total = await service.get_table_rows(
        table.table_name,
        page=page,
        page_size=page_size,
    )
    return {
        "table_name": table.table_name,
        "columns": columns,
        "rows": rows,
        "page": page,
        "page_size": page_size,
        "total": total,
    }
