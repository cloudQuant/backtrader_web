from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data.deps import (
    get_current_db_user,
    require_data_admin_user,
    user_has_admin_access,
)
from app.db.database import get_db
from app.models.user import User
from app.services.broker_profiles import BrokerProfileService, get_broker_profile_service

router = APIRouter(prefix="/brokers", tags=["Brokers"])


async def _get_service(db: AsyncSession = Depends(get_db)) -> BrokerProfileService:
    return await get_broker_profile_service(db)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


async def _load_profile_for_user(
    profile_id: str,
    current_user: User,
    db: AsyncSession,
    service: BrokerProfileService,
):
    profile = await service.get_profile(
        profile_id,
        user_id=current_user.id,
        allow_admin=await user_has_admin_access(db, current_user),
    )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="broker_profile_not_found")
    return profile


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
async def create_broker_profile(
    payload: dict,
    current_user: User = Depends(get_current_db_user),
    service: BrokerProfileService = Depends(_get_service),
):
    return await service.create_profile(
        user_id=current_user.id,
        broker_id=str(payload.get("broker_id") or "gateway_bridge"),
        account_alias=str(payload.get("account_alias") or "gateway"),
        capabilities=[str(item) for item in list(payload.get("capabilities") or [])],
        credentials_ref={
            str(key): str(value)
            for key, value in dict(payload.get("credentials_ref") or {}).items()
            if value is not None
        },
        runtime_gateway_key=str(payload.get("runtime_gateway_key") or "") or None,
        runtime_account_id=str(payload.get("runtime_account_id") or "") or None,
        credentials_rotated_at=_parse_datetime(payload.get("credentials_rotated_at")),
    )


@router.get("/profiles")
async def list_broker_profiles(
    current_user: User = Depends(get_current_db_user),
    service: BrokerProfileService = Depends(_get_service),
):
    return await service.list_profiles(user_id=current_user.id)


@router.get("/profiles/{profile_id}/health")
async def get_broker_profile_health(
    profile_id: str,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
    service: BrokerProfileService = Depends(_get_service),
):
    profile = await _load_profile_for_user(profile_id, current_user, db, service)
    return await service.health(profile)


@router.get("/profiles/{profile_id}/accounts")
async def get_broker_profile_accounts(
    profile_id: str,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
    service: BrokerProfileService = Depends(_get_service),
):
    profile = await _load_profile_for_user(profile_id, current_user, db, service)
    items = await service.list_accounts(profile)
    return {"items": items, "total": len(items)}


@router.get("/profiles/{profile_id}/positions")
async def get_broker_profile_positions(
    profile_id: str,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
    service: BrokerProfileService = Depends(_get_service),
):
    profile = await _load_profile_for_user(profile_id, current_user, db, service)
    items = await service.list_positions(profile)
    return {"items": items, "total": len(items)}


@router.get("/profiles/{profile_id}/orders")
async def get_broker_profile_orders(
    profile_id: str,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
    service: BrokerProfileService = Depends(_get_service),
):
    profile = await _load_profile_for_user(profile_id, current_user, db, service)
    items = await service.list_orders(profile)
    return {"items": items, "total": len(items)}


@router.get("/profiles/{profile_id}/quotes")
async def get_broker_profile_quote(
    profile_id: str,
    symbol: str = Query(...),
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
    service: BrokerProfileService = Depends(_get_service),
):
    profile = await _load_profile_for_user(profile_id, current_user, db, service)
    return await service.get_quote(profile, symbol, user_id=current_user.id)


@router.post("/profiles/{profile_id}/enable-write")
async def enable_broker_profile_live_write(
    profile_id: str,
    payload: dict,
    current_user: User = Depends(require_data_admin_user),
    db: AsyncSession = Depends(get_db),
    service: BrokerProfileService = Depends(_get_service),
):
    profile = await service.get_profile(profile_id, user_id=current_user.id, allow_admin=True)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="broker_profile_not_found")
    confirmation_text = str(payload.get("confirmation_text") or "").strip()
    expected_confirmation_text = service.get_enable_write_confirmation_text(profile)
    if confirmation_text != expected_confirmation_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="write_enable_confirmation_required",
        )

    return await service.enable_live_write(
        profile,
        actor_user_id=current_user.id,
        confirmation_text=confirmation_text,
        idempotency_key=str(payload.get("idempotency_key") or "").strip() or None,
    )
