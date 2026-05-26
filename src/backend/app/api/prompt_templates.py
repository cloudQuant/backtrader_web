from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data_management_deps import require_data_admin_user
from app.db.database import get_db
from app.models.prompt_template import PromptTemplate
from app.models.user import User
from app.services.prompt_registry.registry import PromptRegistryService, PromptTemplateConflictError

router = APIRouter()


class PromptTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    version: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=1)
    variables: list[str] = Field(default_factory=list)
    status: str = "draft"
    rollout_percentage: int = Field(default=0, ge=0, le=100)


class PromptTemplateTestRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class PromptTemplateRead(BaseModel):
    id: str
    name: str
    version: str
    content: str
    status: str
    variables: list[str]
    rollout_percentage: int
    created_at: datetime
    created_by: str | None


class PromptTemplateTestResponse(BaseModel):
    template_id: str
    name: str
    version: str
    rendered_prompt: str
    missing_variables: list[str]


def _serialize_template(template: PromptTemplate) -> PromptTemplateRead:
    variables = template.variables if isinstance(template.variables, list) else []
    return PromptTemplateRead(
        id=str(template.id),
        name=str(template.name),
        version=str(template.version),
        content=str(template.content),
        status=str(template.status),
        variables=[str(item) for item in variables],
        rollout_percentage=int(template.rollout_percentage or 0),
        created_at=template.created_at,
        created_by=str(template.created_by) if template.created_by else None,
    )


@router.get("/admin/prompt-templates")
async def list_prompt_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_data_admin_user),
) -> dict[str, list[PromptTemplateRead]]:
    templates = await PromptRegistryService(db).list_templates()
    return {"items": [_serialize_template(template) for template in templates]}


@router.post("/admin/prompt-templates", status_code=status.HTTP_201_CREATED)
async def create_prompt_template(
    payload: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_data_admin_user),
) -> PromptTemplateRead:
    try:
        template = await PromptRegistryService(db).create_template(
            name=payload.name,
            version=payload.version,
            content=payload.content,
            variables=payload.variables,
            status=payload.status,
            rollout_percentage=payload.rollout_percentage,
            created_by=current_user.id,
        )
    except PromptTemplateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _serialize_template(template)


@router.patch("/admin/prompt-templates/{template_id}/activate")
async def activate_prompt_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_data_admin_user),
) -> PromptTemplateRead:
    template = await PromptRegistryService(db).activate_template(template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt template not found")
    return _serialize_template(template)


@router.post("/admin/prompt-templates/{template_id}/test")
async def test_prompt_template(
    template_id: str,
    payload: PromptTemplateTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_data_admin_user),
) -> PromptTemplateTestResponse:
    result = await PromptRegistryService(db).test_template(template_id, payload.variables)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt template not found")
    return PromptTemplateTestResponse(
        template_id=result.template_id,
        name=result.name,
        version=result.version,
        rendered_prompt=result.rendered_prompt,
        missing_variables=result.missing_variables,
    )
