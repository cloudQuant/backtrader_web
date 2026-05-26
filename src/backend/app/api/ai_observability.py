from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data_management_deps import get_current_db_user, require_data_admin_user
from app.db.database import get_db
from app.models.user import User
from app.services.ai_observability.stats import AICallStatsService
from app.services.ai_router.health import AIProviderHealthService, build_provider_health_payload
from app.services.ai_router.preferences import AIModelPreferenceService

router = APIRouter()


class AIModelPreferenceUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None


@router.get("/admin/ai/usage")
async def get_admin_ai_usage(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    user_id: str | None = Query(default=None),
    service_name: str | None = Query(default=None),
    model_name: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_data_admin_user),
) -> dict[str, Any]:
    return await AICallStatsService(db).get_usage(
        start_at=start_at,
        end_at=end_at,
        user_id=user_id,
        service_name=service_name,
        model_name=model_name,
        include_user_breakdown=True,
    )


@router.get("/admin/ai/failures")
async def get_admin_ai_failures(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    service_name: str | None = Query(default=None),
    model_name: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_data_admin_user),
) -> dict[str, Any]:
    return await AICallStatsService(db).get_failures(
        start_at=start_at,
        end_at=end_at,
        service_name=service_name,
        model_name=model_name,
        limit=limit,
    )


@router.get("/admin/ai/slow-calls")
async def get_admin_ai_slow_calls(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    service_name: str | None = Query(default=None),
    model_name: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_data_admin_user),
) -> dict[str, Any]:
    return await AICallStatsService(db).get_slow_calls(
        start_at=start_at,
        end_at=end_at,
        service_name=service_name,
        model_name=model_name,
        limit=limit,
    )


@router.get("/admin/ai/providers/health")
async def get_admin_ai_provider_health(
    current_user: User = Depends(require_data_admin_user),
) -> dict[str, Any]:
    providers = await AIProviderHealthService().check_all()
    return build_provider_health_payload(providers)


@router.get("/me/ai/usage")
async def get_my_ai_usage(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    service_name: str | None = Query(default=None),
    model_name: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
) -> dict[str, Any]:
    return await AICallStatsService(db).get_usage(
        start_at=start_at,
        end_at=end_at,
        user_id=current_user.id,
        service_name=service_name,
        model_name=model_name,
        include_user_breakdown=False,
    )


@router.get("/me/ai/available-models")
async def get_my_ai_available_models(
    current_user: User = Depends(get_current_db_user),
) -> dict[str, Any]:
    return AIModelPreferenceService().get_available_models_payload(current_user)


@router.patch("/me/ai/preferences")
async def update_my_ai_preferences(
    payload: AIModelPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
) -> dict[str, Any]:
    service = AIModelPreferenceService()
    if not service.is_model_available(provider=payload.provider, model=payload.model):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected AI model is not available",
        )
    current_user.ai_preferred_provider = payload.provider
    current_user.ai_preferred_model = payload.model
    await db.commit()
    await db.refresh(current_user)
    return {"preferences": service.get_preferences(current_user)}


@router.post("/me/ai/preferences/test")
async def test_my_ai_preferences(
    payload: AIModelPreferenceUpdate,
    current_user: User = Depends(get_current_db_user),
) -> dict[str, Any]:
    service = AIModelPreferenceService()
    if not service.is_model_available(provider=payload.provider, model=payload.model):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected AI model is not available",
        )
    providers = await AIProviderHealthService().check_all()
    selected = next((provider for provider in providers if provider.name == payload.provider), None)
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected AI provider is not available",
        )
    return {
        "provider": selected.name,
        "model": payload.model,
        "available": selected.available and (payload.model in selected.models),
        "provider_type": selected.provider_type,
        "base_url": selected.base_url,
        "error": selected.error,
    }
