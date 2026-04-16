"""
API routes for akshare interfaces.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.data_management_deps import require_data_admin_user
from app.db.database import get_db
from app.models.akshare_mgmt import DataInterface, InterfaceCategory
from app.schemas.akshare_mgmt import DataInterfaceCreate, DataInterfaceUpdate
from app.services.akshare_interface_loader import AkshareInterfaceLoader

router = APIRouter()


@router.get("/interfaces/categories")
async def list_interface_categories(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    result = await db.execute(select(InterfaceCategory).order_by(InterfaceCategory.sort_order))
    return list(result.scalars().all())


@router.get("/interfaces")
async def list_interfaces(
    category_id: int | None = None,
    search: str | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    stmt = select(DataInterface).options(selectinload(DataInterface.params))
    count_stmt = select(func.count(DataInterface.id))
    if category_id is not None:
        stmt = stmt.where(DataInterface.category_id == category_id)
        count_stmt = count_stmt.where(DataInterface.category_id == category_id)
    if search:
        stmt = stmt.where(
            (DataInterface.name.ilike(f"%{search}%"))
            | (DataInterface.display_name.ilike(f"%{search}%"))
            | (DataInterface.description.ilike(f"%{search}%"))
        )
        count_stmt = count_stmt.where(
            (DataInterface.name.ilike(f"%{search}%"))
            | (DataInterface.display_name.ilike(f"%{search}%"))
            | (DataInterface.description.ilike(f"%{search}%"))
        )
    if is_active is not None:
        stmt = stmt.where(DataInterface.is_active == is_active)
        count_stmt = count_stmt.where(DataInterface.is_active == is_active)
    total = int((await db.execute(count_stmt)).scalar() or 0)
    stmt = stmt.order_by(DataInterface.id).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return {
        "items": list(result.scalars().all()),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/interfaces/{interface_id}")
async def get_interface(
    interface_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    result = await db.execute(
        select(DataInterface)
        .options(selectinload(DataInterface.params))
        .where(DataInterface.id == interface_id)
    )
    interface = result.scalar_one_or_none()
    if interface is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interface not found")
    return interface


@router.post("/interfaces", status_code=status.HTTP_201_CREATED)
async def create_interface(
    payload: DataInterfaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    interface = DataInterface(**payload.model_dump())
    db.add(interface)
    await db.commit()
    await db.refresh(interface)
    return interface


@router.put("/interfaces/{interface_id}")
async def update_interface(
    interface_id: int,
    payload: DataInterfaceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    interface = await db.get(DataInterface, interface_id)
    if interface is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interface not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(interface, key, value)
    await db.commit()
    await db.refresh(interface)
    return interface


@router.delete("/interfaces/{interface_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interface(
    interface_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    interface = await db.get(DataInterface, interface_id)
    if interface is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interface not found")
    await db.delete(interface)
    await db.commit()


@router.post("/interfaces/bootstrap")
async def bootstrap_interfaces(
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    return await AkshareInterfaceLoader(db).bootstrap(refresh=refresh)
