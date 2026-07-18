import typing

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.data.deps import require_data_admin_user
from app.schemas.sync import SyncConfig, SyncRequest
from app.services.sync_service import get_sync_service

router = APIRouter()


@router.get("/sync/config", response_model=None)
async def get_sync_config(
    current_user: typing.Any = Depends(require_data_admin_user),
) -> typing.Any:
    return get_sync_service().get_config()


@router.put("/sync/config", response_model=None)
async def save_sync_config(
    payload: SyncConfig, current_user: typing.Any = Depends(require_data_admin_user)
) -> typing.Any:
    return get_sync_service().save_config(payload)


@router.post("/sync/test-connection", response_model=None)
async def test_sync_connection(
    payload: SyncConfig, current_user: typing.Any = Depends(require_data_admin_user)
) -> typing.Any:
    try:
        return await get_sync_service().test_connection(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/sync/databases", response_model=None)
async def list_sync_databases(
    current_user: typing.Any = Depends(require_data_admin_user),
) -> typing.Any:
    try:
        items = await get_sync_service().list_databases(get_sync_service().get_config())
        return {"items": items}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sync/upload", status_code=status.HTTP_202_ACCEPTED, response_model=None)
async def upload_databases(
    payload: SyncRequest, current_user: typing.Any = Depends(require_data_admin_user)
) -> typing.Any:
    try:
        return await get_sync_service().start_upload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sync/download", status_code=status.HTTP_202_ACCEPTED, response_model=None)
async def download_databases(
    payload: SyncRequest, current_user: typing.Any = Depends(require_data_admin_user)
) -> typing.Any:
    try:
        return await get_sync_service().start_download(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/sync/status/{task_id}", response_model=None)
async def get_sync_status(
    task_id: str, current_user: typing.Any = Depends(require_data_admin_user)
) -> typing.Any:
    task = await get_sync_service().get_task_status(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync task not found")
    return task


@router.get("/sync/history", response_model=None)
async def get_sync_history(
    limit: int = Query(50, ge=1, le=200),
    current_user: typing.Any = Depends(require_data_admin_user),
) -> typing.Any:
    return {"items": await get_sync_service().get_history(limit=limit)}
