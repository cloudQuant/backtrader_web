"""Owner-scoped creation of bounded v2 experiment epochs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import database
from app.models.ai_research_v2 import ResearchExperimentEpoch, ResearchHypothesisVersion
from app.services.research.canonical import content_hash

_FAMILY_IDENTITY_FIELDS = (
    "research_question",
    "asset_scope",
    "frequency",
    "time_window",
    "primary_metric",
    "search_space",
)


class ExperimentEpochRegistry:
    """Create search budgets only from confirmed, immutable hypotheses."""

    async def create_epoch(
        self,
        *,
        user_id: str,
        hypothesis_version_id: str,
        search_budget: dict[str, Any],
        dataset_policy_version: str,
        holdout_budget: int = 1,
        parent_epoch_id: str | None = None,
    ) -> ResearchExperimentEpoch:
        """Persist one OPEN epoch with an explicit finite disclosure budget."""

        if not dataset_policy_version.strip() or not isinstance(search_budget, dict):
            raise ValueError("EXPERIMENT_EPOCH_POLICY_OR_BUDGET_INVALID")
        if holdout_budget != 1:
            raise ValueError("EXPERIMENT_EPOCH_HOLDOUT_BUDGET_MUST_BE_ONE")
        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchHypothesisVersion).where(
                    ResearchHypothesisVersion.id == hypothesis_version_id,
                    ResearchHypothesisVersion.user_id == user_id,
                    ResearchHypothesisVersion.status == "CONFIRMED",
                )
            )
            hypothesis = result.scalar_one_or_none()
            if hypothesis is None:
                raise ValueError("EXPERIMENT_EPOCH_HYPOTHESIS_NOT_CONFIRMED")
            family_hash = family_hash_for_hypothesis(hypothesis.canonical_payload or {})
            existing = await session.scalar(
                select(ResearchExperimentEpoch).where(
                    ResearchExperimentEpoch.user_id == user_id,
                    ResearchExperimentEpoch.family_hash == family_hash,
                )
            )
            if existing is not None:
                if _same_open_epoch_request(
                    existing,
                    hypothesis_version_id=hypothesis.id,
                    search_budget=search_budget,
                    dataset_policy_version=dataset_policy_version,
                    parent_epoch_id=parent_epoch_id,
                ):
                    return existing
                raise ValueError("EXPERIMENT_EPOCH_FAMILY_ALREADY_EXISTS")
            if parent_epoch_id is not None:
                parent = await session.get(ResearchExperimentEpoch, parent_epoch_id)
                if parent is None or parent.user_id != user_id or parent.status != "CLOSED":
                    raise ValueError("EXPERIMENT_EPOCH_PARENT_NOT_CLOSED")
            model = ResearchExperimentEpoch(
                user_id=user_id,
                hypothesis_version_id=hypothesis.id,
                family_hash=family_hash,
                search_budget=dict(search_budget),
                dataset_policy_version=dataset_policy_version,
                holdout_budget=holdout_budget,
                parent_epoch_id=parent_epoch_id,
            )
            session.add(model)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("EXPERIMENT_EPOCH_FAMILY_ALREADY_EXISTS") from exc
            await session.refresh(model)
            return model


def family_hash_for_hypothesis(payload: dict[str, Any]) -> str:
    """Derive an epoch family identity from immutable preregistration fields.

    The client may choose a new hypothesis revision, but it cannot choose an
    arbitrary family partition to obtain another sealed-holdout opportunity.
    """

    if any(field not in payload for field in _FAMILY_IDENTITY_FIELDS):
        raise ValueError("EXPERIMENT_EPOCH_FAMILY_FIELDS_INVALID")
    return content_hash({field: payload[field] for field in _FAMILY_IDENTITY_FIELDS})


def _same_open_epoch_request(
    epoch: ResearchExperimentEpoch,
    *,
    hypothesis_version_id: str,
    search_budget: dict[str, Any],
    dataset_policy_version: str,
    parent_epoch_id: str | None,
) -> bool:
    """Allow only an exact retry before the family has selected a candidate."""

    return bool(
        epoch.status == "OPEN"
        and epoch.hypothesis_version_id == hypothesis_version_id
        and epoch.dataset_policy_version == dataset_policy_version
        and epoch.parent_epoch_id == parent_epoch_id
        and content_hash(epoch.search_budget) == content_hash(search_budget)
    )
