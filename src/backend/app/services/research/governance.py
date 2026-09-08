"""Append-only, fail-closed governance deviations for trusted AI research."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from app.db import database
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchGovernanceDecision,
    ResearchRun,
)
from app.models.user import User

_WAIVABLE_TARGET = re.compile(r"^NFR-PERF-\d{3}$")
_ORIGINAL_STATUSES = frozenset({"FAIL", "BLOCKED", "NOT_RUN"})
_SCOPE_KEYS = frozenset({"candidate_id", "run_id"})


@dataclass(frozen=True, slots=True)
class GovernanceDeviationPolicy:
    """Server-owned allowlist for deviations that never rewrite gate outcomes."""

    version: str
    waivable_targets: frozenset[str]

    def validate(self) -> None:
        """Keep all non-performance and security-sensitive gates non-waivable by default."""

        if not self.version.strip() or any(
            _WAIVABLE_TARGET.fullmatch(target) is None for target in self.waivable_targets
        ):
            raise ValueError("GOVERNANCE_DEVIATION_POLICY_INVALID")


class GovernanceDecisionService:
    """Persist an immutable deviation record without changing any underlying gate."""

    async def record(
        self,
        *,
        actor_id: str,
        policy: GovernanceDeviationPolicy,
        target_requirement_or_gate: str,
        original_status: str,
        reason: str,
        risk: str,
        compensating_controls: Sequence[str],
        scope: Mapping[str, object],
        idempotency_key: str,
        expires_at: datetime,
        now: datetime | None = None,
    ) -> ResearchGovernanceDecision:
        """Record one policy-permitted deviation while preserving its failed status."""

        policy.validate()
        target = _required_text(target_requirement_or_gate, "GOVERNANCE_DEVIATION_TARGET_INVALID")
        if target not in policy.waivable_targets:
            raise ValueError("GOVERNANCE_DEVIATION_NON_WAIVABLE")
        if original_status not in _ORIGINAL_STATUSES:
            raise ValueError("GOVERNANCE_DEVIATION_ORIGINAL_STATUS_INVALID")
        recorded_reason = _required_text(reason, "GOVERNANCE_DEVIATION_REASON_REQUIRED")
        recorded_risk = _required_text(risk, "GOVERNANCE_DEVIATION_RISK_REQUIRED")
        controls = _controls(compensating_controls)
        key = _required_text(idempotency_key, "GOVERNANCE_DEVIATION_IDEMPOTENCY_REQUIRED")
        effective_at = _require_utc(now or _now())
        expiry = _require_utc(expires_at)
        if expiry <= effective_at:
            raise ValueError("GOVERNANCE_DEVIATION_EXPIRY_INVALID")
        normalized_scope = await self._validate_scope(actor_id, scope)
        decision_id = str(uuid5(NAMESPACE_URL, f"ai-research-governance:{actor_id}:{key}"))

        async with database.async_session_maker() as session:
            existing = await session.get(
                ResearchGovernanceDecision, decision_id, with_for_update=True
            )
            if existing is not None:
                if not _same_record(
                    existing,
                    target=target,
                    original_status=original_status,
                    reason=recorded_reason,
                    risk=recorded_risk,
                    controls=controls,
                    actor_id=actor_id,
                    scope=normalized_scope,
                    expires_at=expiry,
                ):
                    raise ValueError("GOVERNANCE_DEVIATION_IDEMPOTENCY_CONFLICT")
                return existing
            model = ResearchGovernanceDecision(
                id=decision_id,
                target_requirement_or_gate=target,
                original_status=original_status,
                reason=recorded_reason,
                risk=recorded_risk,
                compensating_controls=list(controls),
                actor_id=actor_id,
                scope=normalized_scope,
                effective_at=effective_at,
                expires_at=expiry,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return model

    async def revoke(
        self,
        *,
        decision_id: str,
        actor_id: str,
        now: datetime | None = None,
    ) -> ResearchGovernanceDecision:
        """Record revocation without deleting or rewriting the original deviation."""

        identifier = _required_text(decision_id, "GOVERNANCE_DEVIATION_ID_INVALID")
        if not actor_id.strip() or actor_id.startswith(("ai:", "llm:", "system:")):
            raise ValueError("GOVERNANCE_DEVIATION_ACTOR_DENIED")
        revoked_at = _require_utc(now or _now())
        async with database.async_session_maker() as session:
            model = await session.get(ResearchGovernanceDecision, identifier, with_for_update=True)
            if model is None:
                raise ValueError("GOVERNANCE_DEVIATION_NOT_FOUND")
            if model.actor_id != actor_id:
                raise ValueError("GOVERNANCE_DEVIATION_REVOKE_DENIED")
            if model.revoked_at is not None:
                return model
            model.revoked_at = revoked_at
            await session.commit()
            await session.refresh(model)
            return model

    @staticmethod
    async def _validate_scope(actor_id: str, scope: Mapping[str, object]) -> dict[str, str]:
        """Bind a decision to an owned candidate or run; arbitrary scope fields are forbidden."""

        if not actor_id.strip() or actor_id.startswith(("ai:", "llm:", "system:")):
            raise ValueError("GOVERNANCE_DEVIATION_ACTOR_DENIED")
        normalized = {
            key: value.strip()
            for key, value in dict(scope).items()
            if isinstance(key, str) and isinstance(value, str) and value.strip()
        }
        if (
            set(normalized) != set(scope)
            or not normalized
            or not set(normalized).issubset(_SCOPE_KEYS)
        ):
            raise ValueError("GOVERNANCE_DEVIATION_SCOPE_INVALID")
        if "candidate_id" not in normalized and "run_id" not in normalized:
            raise ValueError("GOVERNANCE_DEVIATION_SCOPE_REQUIRED")

        async with database.async_session_maker() as session:
            actor = await session.get(User, actor_id)
            if actor is None:
                raise ValueError("GOVERNANCE_DEVIATION_ACTOR_NOT_FOUND")
            candidate: ResearchCandidate | None = None
            run: ResearchRun | None = None
            if candidate_id := normalized.get("candidate_id"):
                candidate = await session.get(ResearchCandidate, candidate_id)
                if candidate is None or candidate.user_id != actor_id:
                    raise ValueError("GOVERNANCE_DEVIATION_SCOPE_DENIED")
            if run_id := normalized.get("run_id"):
                run = await session.get(ResearchRun, run_id)
                if run is None or run.user_id != actor_id:
                    raise ValueError("GOVERNANCE_DEVIATION_SCOPE_DENIED")
            if candidate is not None and run is not None and candidate.run_id != run.id:
                raise ValueError("GOVERNANCE_DEVIATION_SCOPE_MISMATCH")
        return {key: normalized[key] for key in sorted(normalized)}


def _required_text(value: str, error_code: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 10_000:
        raise ValueError(error_code)
    return normalized


def _controls(values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(
        _required_text(value, "GOVERNANCE_DEVIATION_CONTROL_INVALID") for value in values
    )
    if not normalized or len(normalized) > 32:
        raise ValueError("GOVERNANCE_DEVIATION_CONTROL_REQUIRED")
    return normalized


def _same_record(
    model: ResearchGovernanceDecision,
    *,
    target: str,
    original_status: str,
    reason: str,
    risk: str,
    controls: tuple[str, ...],
    actor_id: str,
    scope: dict[str, str],
    expires_at: datetime,
) -> bool:
    return (
        model.target_requirement_or_gate == target
        and model.original_status == original_status
        and model.reason == reason
        and model.risk == risk
        and tuple(model.compensating_controls or []) == controls
        and model.actor_id == actor_id
        and dict(model.scope or {}) == scope
        and _stored_utc(model.expires_at) == expires_at
    )


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("GOVERNANCE_DEVIATION_TIMESTAMP_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def _stored_utc(value: datetime | None) -> datetime | None:
    """Normalize SQLite's timezone-naive persisted UTC values for comparison only."""

    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)
