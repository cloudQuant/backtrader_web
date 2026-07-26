import typing

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.database import get_db
from app.services.scanner_plan import ScannerPlanService
from app.services.scanner_service import get_scanner_service
from app.services.scanner_universe import parse_symbol_text

router = APIRouter(prefix="/scanners", tags=["Scanners"])


def _user_id(current_user: typing.Any) -> str:
    return str(getattr(current_user, "sub", "") or "default")


@router.get("/universe-pools", response_model=None)
async def list_universe_pools(current_user: typing.Any = Depends(get_current_user)) -> typing.Any:
    return get_scanner_service().universe_service.list_pools(_user_id(current_user))


@router.post("/universe-pools/{pool_id}/refresh", response_model=None)
async def refresh_universe_pool(
    pool_id: str, current_user: typing.Any = Depends(get_current_user)
) -> typing.Any:
    try:
        return get_scanner_service().universe_service.refresh_pool(pool_id, _user_id(current_user))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/universe-pools/{pool_id}/precompute", response_model=None)
async def precompute_universe_pool_metrics(
    pool_id: str,
    payload: dict | None = None,
    current_user: typing.Any = Depends(get_current_user),
) -> typing.Any:
    try:
        payload = payload or {}
        return get_scanner_service().universe_service.precompute_pool_metrics(
            user_id=_user_id(current_user),
            pool_id=pool_id,
            lookback_days=int(payload.get("lookback_days") or 20),
            timeframe=str(payload.get("timeframe") or "1d"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/universe-pools/custom", response_model=None)
async def save_custom_universe_pool(
    payload: dict, current_user: typing.Any = Depends(get_current_user)
) -> typing.Any:
    try:
        instruments = payload.get("instruments")
        if not instruments and payload.get("symbols_text"):
            instruments = parse_symbol_text(str(payload.get("symbols_text") or ""))
        return get_scanner_service().universe_service.save_custom_pool(
            _user_id(current_user),
            {**payload, "instruments": instruments or []},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/plans", response_model=None)
async def save_scanner_plan(
    payload: dict,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    try:
        return await ScannerPlanService(db, get_scanner_service()).save_plan(
            _user_id(current_user),
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/plans", response_model=None)
async def list_scanner_plans(
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    return await ScannerPlanService(db, get_scanner_service()).list_plans(_user_id(current_user))


@router.patch("/plans/{plan_id}", response_model=None)
async def update_scanner_plan(
    plan_id: str,
    payload: dict,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    try:
        result = await ScannerPlanService(db, get_scanner_service()).update_plan(
            _user_id(current_user),
            plan_id,
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_plan_not_found")
    return result


@router.delete("/plans/{plan_id}", response_model=None)
async def delete_scanner_plan(
    plan_id: str,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    result = await ScannerPlanService(db, get_scanner_service()).delete_plan(
        _user_id(current_user),
        plan_id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_plan_not_found")
    return {"deleted": True}


@router.post("/plans/daily-runs", response_model=None)
async def run_daily_scanner_plans(
    payload: dict | None = None,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    payload = payload or {}
    return await ScannerPlanService(db, get_scanner_service()).run_daily_plans(
        _user_id(current_user),
        run_date=payload.get("run_date"),
    )


@router.post("/plans/{plan_id}/result-table", response_model=None)
async def create_scanner_plan_result_table(
    plan_id: str,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    try:
        result = await ScannerPlanService(db, get_scanner_service()).create_result_table(
            _user_id(current_user),
            plan_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_plan_not_found")
    return result


@router.delete("/plans/{plan_id}/result-table", response_model=None)
async def delete_scanner_plan_result_table(
    plan_id: str,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    try:
        result = await ScannerPlanService(db, get_scanner_service()).delete_result_table(
            _user_id(current_user),
            plan_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_plan_not_found")
    return result


@router.post("/plans/{plan_id}/runs", response_model=None)
async def run_scanner_plan(
    plan_id: str,
    payload: dict | None = None,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    payload = payload or {}
    result = await ScannerPlanService(db, get_scanner_service()).run_plan(
        _user_id(current_user),
        plan_id,
        run_date=payload.get("run_date"),
        force=bool(payload.get("force")),
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_plan_not_found")
    return result


@router.get("/plans/{plan_id}/runs", response_model=None)
async def list_scanner_plan_runs(
    plan_id: str,
    current_user: typing.Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> typing.Any:
    result = await ScannerPlanService(db, get_scanner_service()).list_runs(
        _user_id(current_user),
        plan_id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_plan_not_found")
    return result


@router.post("/run", response_model=None)
async def run_scanner(
    payload: dict, current_user: typing.Any = Depends(get_current_user)
) -> typing.Any:
    try:
        return get_scanner_service().run(
            list(payload.get("universe") or []),
            str(payload.get("condition") or ""),
            lookback_days=int(payload.get("lookback_days") or 20),
            timeframe=str(payload.get("timeframe") or "1d"),
            universe_pool_id=payload.get("universe_pool_id") or payload.get("pool_id"),
            user_id=_user_id(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/tasks/{task_id}", response_model=None)
async def get_scanner_task(
    task_id: str, current_user: typing.Any = Depends(get_current_user)
) -> typing.Any:
    payload = get_scanner_service().get_task(task_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scanner_task_not_found")
    return payload
