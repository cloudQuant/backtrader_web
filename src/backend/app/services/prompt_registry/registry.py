from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session_maker
from app.models.prompt_template import PromptTemplate

_VARIABLE_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
_VALID_STATUSES = {"draft", "active", "archived"}


@dataclass(frozen=True)
class PromptRenderResult:
    template_id: str
    name: str
    version: str
    rendered_prompt: str
    missing_variables: list[str]


class PromptTemplateConflictError(ValueError):
    pass


class PromptRegistryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_templates(self, name: str | None = None) -> list[PromptTemplate]:
        stmt = select(PromptTemplate).order_by(PromptTemplate.name.asc(), PromptTemplate.created_at.desc())
        if name:
            stmt = stmt.where(PromptTemplate.name == name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_template(
        self,
        *,
        name: str,
        version: str,
        content: str,
        variables: list[str],
        created_by: str | None,
        status: str = "draft",
        rollout_percentage: int = 0,
    ) -> PromptTemplate:
        if status not in _VALID_STATUSES:
            raise ValueError("Invalid prompt template status")
        if rollout_percentage < 0 or rollout_percentage > 100:
            raise ValueError("rollout_percentage must be between 0 and 100")
        template = PromptTemplate(
            name=name,
            version=version,
            content=content,
            variables=variables,
            status=status,
            rollout_percentage=rollout_percentage,
            created_by=created_by,
        )
        self.db.add(template)
        try:
            if status == "active":
                await self.db.flush()
                await self._archive_other_active_versions(template)
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise PromptTemplateConflictError("Prompt template version already exists") from exc
        await self.db.refresh(template)
        return template

    async def activate_template(self, template_id: str) -> PromptTemplate | None:
        template = await self.db.get(PromptTemplate, template_id)
        if template is None:
            return None
        await self._archive_other_active_versions(template)
        template.status = "active"
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def get_active_template(self, name: str) -> PromptTemplate | None:
        result = await self.db.execute(
            select(PromptTemplate)
            .where(PromptTemplate.name == name, PromptTemplate.status == "active")
            .order_by(PromptTemplate.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def test_template(
        self,
        template_id: str,
        variables: dict[str, Any],
    ) -> PromptRenderResult | None:
        template = await self.db.get(PromptTemplate, template_id)
        if template is None:
            return None
        return self.render_template(template, variables)

    async def render_active_template(
        self,
        name: str,
        variables: dict[str, Any],
        user_id: str | None = None,
    ) -> PromptRenderResult | None:
        template = await self._select_template_for_user(name=name, user_id=user_id)
        if template is None:
            return None
        return self.render_template(template, variables)

    def render_template(self, template: PromptTemplate, variables: dict[str, Any]) -> PromptRenderResult:
        missing: list[str] = []

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            value = variables.get(key)
            if value is None:
                if key not in missing:
                    missing.append(key)
                return ""
            return str(value)

        rendered = _VARIABLE_PATTERN.sub(replace, template.content)
        declared_variables = template.variables if isinstance(template.variables, list) else []
        for key in declared_variables:
            if key not in variables and key not in missing:
                missing.append(str(key))
        return PromptRenderResult(
            template_id=str(template.id),
            name=str(template.name),
            version=str(template.version),
            rendered_prompt=rendered,
            missing_variables=missing,
        )

    async def _archive_other_active_versions(self, template: PromptTemplate) -> None:
        await self.db.execute(
            update(PromptTemplate)
            .where(
                PromptTemplate.name == template.name,
                PromptTemplate.id != template.id,
                PromptTemplate.status == "active",
            )
            .values(status="archived")
        )

    async def _select_template_for_user(
        self,
        *,
        name: str,
        user_id: str | None,
    ) -> PromptTemplate | None:
        stable = await self.get_active_template(name)
        if user_id:
            result = await self.db.execute(
                select(PromptTemplate)
                .where(
                    PromptTemplate.name == name,
                    PromptTemplate.status != "archived",
                    PromptTemplate.rollout_percentage > 0,
                )
                .order_by(PromptTemplate.created_at.desc())
                .limit(1)
            )
            candidate = result.scalar_one_or_none()
            if candidate is not None and _is_rollout_selected(
                user_id=user_id,
                template_name=name,
                template_version=str(candidate.version),
                rollout_percentage=int(candidate.rollout_percentage or 0),
            ):
                return candidate
        return stable


class PromptRegistry:
    async def render_active_template(
        self,
        name: str,
        variables: dict[str, Any],
        user_id: str | None = None,
    ) -> PromptRenderResult | None:
        async with async_session_maker() as session:
            return await PromptRegistryService(session).render_active_template(name, variables, user_id)


def _is_rollout_selected(
    *,
    user_id: str,
    template_name: str,
    template_version: str,
    rollout_percentage: int,
) -> bool:
    if rollout_percentage <= 0:
        return False
    if rollout_percentage >= 100:
        return True
    bucket = zlib.crc32(f"{template_name}:{template_version}:{user_id}".encode()) % 100
    return bucket < rollout_percentage
