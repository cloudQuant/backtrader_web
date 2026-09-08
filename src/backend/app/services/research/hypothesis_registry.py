"""Authoritative state transitions for immutable v2 research hypotheses."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.db import database
from app.models.ai_research_v2 import ResearchHypothesisVersion
from app.services.research.canonical import canonical_json, content_hash

_REQUIRED_FIELDS = (
    "research_question",
    "economic_mechanism",
    "asset_scope",
    "frequency",
    "time_window",
    "information_cutoff",
    "cost_model",
    "execution_model",
    "primary_metric",
    "secondary_metrics",
    "capacity_assumptions",
    "falsification_criteria",
    "search_space",
    "max_budget",
    "dataset_policy_version",
)


class HypothesisRegistry:
    """Create, confirm, and revise research specifications without mutation.

    This registry is the only v2 application service permitted to advance a
    hypothesis version.  A task references a confirmed version by its content
    hash; it never writes the version while executing research stages.
    """

    async def create_draft(
        self,
        user_id: str,
        payload: dict[str, Any],
        *,
        workspace_id: str | None = None,
        source_mandate_id: str | None = None,
    ) -> ResearchHypothesisVersion:
        """Persist a new, unconfirmed hypothesis family root."""

        canonical_payload = _canonical_payload(payload)
        model = ResearchHypothesisVersion(
            user_id=user_id,
            hypothesis_id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            version_no=1,
            status="DRAFT",
            canonical_payload=canonical_payload,
            content_hash=content_hash(canonical_payload),
            source_mandate_id=source_mandate_id,
        )
        async with database.async_session_maker() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
        return model

    async def get_version(
        self,
        user_id: str,
        version_id: str,
    ) -> ResearchHypothesisVersion | None:
        """Return an owner-scoped version without disclosing foreign rows."""

        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchHypothesisVersion).where(
                    ResearchHypothesisVersion.id == version_id,
                    ResearchHypothesisVersion.user_id == user_id,
                )
            )
            return result.scalar_one_or_none()

    async def confirm(
        self,
        user_id: str,
        version_id: str,
        *,
        request_hash: str,
    ) -> ResearchHypothesisVersion:
        """Confirm a complete draft whose supplied hash matches server truth."""

        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchHypothesisVersion)
                .where(
                    ResearchHypothesisVersion.id == version_id,
                    ResearchHypothesisVersion.user_id == user_id,
                )
                .with_for_update()
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise ValueError("HYPOTHESIS_NOT_FOUND")
            if model.status != "DRAFT":
                raise ValueError("HYPOTHESIS_NOT_CONFIRMABLE")

            missing = _missing_required_fields(model.canonical_payload)
            if missing:
                raise ValueError(f"HYPOTHESIS_REQUIRED_FIELDS_MISSING:{','.join(missing)}")
            invalid = _invalid_required_fields(model.canonical_payload)
            if invalid:
                raise ValueError(f"HYPOTHESIS_REQUIRED_FIELDS_INVALID:{','.join(invalid)}")
            server_hash = content_hash(model.canonical_payload)
            if model.content_hash != server_hash or request_hash != server_hash:
                raise ValueError("HYPOTHESIS_CONFIRMATION_HASH_MISMATCH")

            model.status = "CONFIRMED"
            model.confirmed_by = user_id
            model.confirmed_at = _now()
            await session.commit()
            await session.refresh(model)
            return model

    async def revise(
        self,
        user_id: str,
        version_id: str,
        payload: dict[str, Any],
    ) -> ResearchHypothesisVersion:
        """Update a draft or fork a confirmed version into a new draft child."""

        canonical_payload = _canonical_payload(payload)
        new_hash = content_hash(canonical_payload)
        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchHypothesisVersion)
                .where(
                    ResearchHypothesisVersion.id == version_id,
                    ResearchHypothesisVersion.user_id == user_id,
                )
                .with_for_update()
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise ValueError("HYPOTHESIS_NOT_FOUND")
            if model.status == "SUPERSEDED":
                raise ValueError("HYPOTHESIS_VERSION_SUPERSEDED")
            if model.status == "DRAFT":
                model.canonical_payload = canonical_payload
                model.content_hash = new_hash
                await session.commit()
                await session.refresh(model)
                return model

            next_version = await session.scalar(
                select(func.max(ResearchHypothesisVersion.version_no)).where(
                    ResearchHypothesisVersion.user_id == user_id,
                    ResearchHypothesisVersion.hypothesis_id == model.hypothesis_id,
                )
            )
            child = ResearchHypothesisVersion(
                user_id=user_id,
                hypothesis_id=model.hypothesis_id,
                workspace_id=model.workspace_id,
                version_no=int(next_version or 0) + 1,
                parent_version_id=model.id,
                status="DRAFT",
                canonical_payload=canonical_payload,
                content_hash=new_hash,
                source_mandate_id=model.source_mandate_id,
            )
            model.status = "SUPERSEDED"
            session.add(child)
            await session.commit()
            await session.refresh(child)
            return child


def _canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("HYPOTHESIS_PAYLOAD_INVALID")
    return json.loads(canonical_json(payload))


def _missing_required_fields(payload: dict[str, Any]) -> list[str]:
    return [field for field in _REQUIRED_FIELDS if not _has_value(payload.get(field))]


def _invalid_required_fields(payload: dict[str, Any]) -> list[str]:
    """Validate the minimum semantic contract before a draft can be frozen."""

    invalid: list[str] = []
    if not _valid_symbols(payload.get("asset_scope")):
        invalid.append("asset_scope")
    if not _valid_time_window(payload.get("time_window")):
        invalid.append("time_window")
    if not _valid_timestamp(payload.get("information_cutoff")):
        invalid.append("information_cutoff")
    if not _valid_cost_model(payload.get("cost_model")):
        invalid.append("cost_model")
    if not _valid_secondary_metrics(payload.get("secondary_metrics")):
        invalid.append("secondary_metrics")
    if not _valid_capacity(payload.get("capacity_assumptions")):
        invalid.append("capacity_assumptions")
    if not _valid_max_budget(payload.get("max_budget")):
        invalid.append("max_budget")
    return invalid


def _valid_symbols(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and isinstance(value.get("symbols"), list)
        and value["symbols"]
        and all(isinstance(symbol, str) and symbol.strip() for symbol in value["symbols"])
    )


def _valid_time_window(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    start = _parse_timestamp(value.get("start"))
    end = _parse_timestamp(value.get("end"))
    return start is not None and end is not None and start < end


def _valid_timestamp(value: Any) -> bool:
    return _parse_timestamp(value) is not None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _valid_cost_model(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return all(
        isinstance(value.get(field), (int, float))
        and not isinstance(value.get(field), bool)
        and float(value[field]) >= 0
        for field in ("commission_bps", "slippage_bps")
    )


def _valid_secondary_metrics(value: Any) -> bool:
    return bool(
        isinstance(value, list)
        and value
        and all(isinstance(metric, str) and metric.strip() for metric in value)
    )


def _valid_capacity(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    participation = value.get("max_participation_rate")
    return bool(
        isinstance(participation, (int, float))
        and not isinstance(participation, bool)
        and 0 < float(participation) <= 1
    )


def _valid_max_budget(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    max_trials = value.get("max_trials")
    return bool(isinstance(max_trials, int) and not isinstance(max_trials, bool) and max_trials > 0)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _now() -> datetime:
    return datetime.now(timezone.utc)
