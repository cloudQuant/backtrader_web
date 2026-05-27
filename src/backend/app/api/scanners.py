from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.services.scanner_service import get_scanner_service

router = APIRouter(prefix="/scanners", tags=["Scanners"])


@router.post("/run")
async def run_scanner(payload: dict, current_user=Depends(get_current_user)):
    try:
        return get_scanner_service().run(
            list(payload.get("universe") or []),
            str(payload.get("condition") or ""),
            lookback_days=int(payload.get("lookback_days") or 20),
            timeframe=str(payload.get("timeframe") or "1d"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/tasks/{task_id}")
async def get_scanner_task(task_id: str, current_user=Depends(get_current_user)):
    payload = get_scanner_service().get_task(task_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_task_not_found")
    return payload
