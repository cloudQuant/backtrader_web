"""Server-authorized human decision boundary for trusted research promotion."""

from __future__ import annotations

import asyncio
import hashlib
import re
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import database
from app.models.ai_research_v2 import (
    ResearchApprovalDenialFence,
    ResearchApprovalRequest,
    ResearchEvidencePackage,
    ResearchGateDecision,
    ResearchHumanDecision,
)
from app.services.research.approval_authority import (
    ApprovalAuthority,
    ApprovalAuthorityResolver,
    ApprovalPolicy,
    approval_capability_profile_material_hash,
    approval_grant_hash,
)
from app.services.research.canonical import content_hash
from app.services.research.evidence_package import EvidencePackageService
from app.services.research.holdout_execution_contract import REQUIRED_HOLDOUT_GATE_CODES
from app.services.research.promotion import PromotionGateEngine
from app.services.research.redaction import redact_sensitive_payload

_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
_VALID_DECISIONS = frozenset({"APPROVED", "REJECTED", "REQUESTED_CHANGES"})
_MAX_HUMAN_TEXT_LENGTH = 10_000
_MAX_CHALLENGE_COUNT = 32
_MAX_CHALLENGE_KEY_LENGTH = 128
_SAFE_GATE_EXECUTOR_VERSIONS = frozenset({"promotion-gate-v2", "sealed-evaluator-receipt-v1"})
_URI_SCHEME = re.compile(r"(?:^|[^A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*:(?=\S)")
_PATH_PREFIX = r"(?:^|[^A-Za-z0-9])"
_POSIX_ABSOLUTE_PATH = re.compile(rf"{_PATH_PREFIX}/(?!/)[^\s,;?)\]}}]+")
_WINDOWS_ABSOLUTE_PATH = re.compile(rf"{_PATH_PREFIX}[A-Za-z]:[\\/][^\s,;?)\]}}]+")
_UNC_ABSOLUTE_PATH = re.compile(rf"{_PATH_PREFIX}(?:\\\\|//)[^\\/\s]+[\\/]\S+")
_LOCK_SHARD_COUNT = 64
_LOCKS_BY_LOOP: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, tuple[asyncio.Lock, ...]] = (
    weakref.WeakKeyDictionary()
)


@dataclass(frozen=True, slots=True)
class ApprovalRequestSummary:
    """Safe recovery state for the current pending request."""

    id: str
    run_id: str
    candidate_id: str
    evidence_package_id: str
    policy_version: str
    policy_material_hash: str
    approval_mode: str
    gate_input_evidence_hash: str
    evidence_package_hash: str
    request_material_hash: str
    status: str
    requested_at: datetime
    eligible_at: datetime
    expires_at: datetime
    decided_at: datetime | None


@dataclass(frozen=True, slots=True)
class ApprovalDecisionSummary:
    """Safe recovery state for the latest immutable human decision."""

    id: str
    run_id: str
    candidate_id: str
    approval_request_id: str
    decision: str
    policy_version: str
    policy_material_hash: str
    approval_mode: str
    gate_input_evidence_hash: str
    evidence_package_hash: str
    decision_material_hash: str
    decision_intent_hash: str
    risk_acknowledgement: bool
    challenge_keys: tuple[str, ...]
    reason: str
    decided_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ApprovalEvidencePackageSummary:
    """Closed package identity; its manifest and sealed payload remain private."""

    id: str
    candidate_id: str
    status: str
    promotion_policy_version: str
    command_id: str
    evaluation_id: str
    gate_input_evidence_hash: str
    manifest_hash: str
    approval_binding_hash: str


@dataclass(frozen=True, slots=True)
class ApprovalGateSummary:
    """One safe, immutable hard-gate outcome for human review."""

    gate_code: str
    status: str
    reason_code: str
    input_evidence_hash: str
    executor_version: str
    evaluated_at: datetime


@dataclass(frozen=True, slots=True)
class ApprovalMachineEvidenceSummary:
    """Complete machine evidence needed to avoid blind approval."""

    package: ApprovalEvidencePackageSummary
    gates: tuple[ApprovalGateSummary, ...]


@dataclass(frozen=True, slots=True)
class ApprovalContext:
    """Safe UI context with no grant internals or permission catalog details."""

    run_id: str
    candidate_id: str
    candidate_hash: str
    policy_version: str
    policy_material_hash: str
    approval_mode: str
    can_request: bool
    can_decide: bool
    can_approve: bool
    request_blocked_reason: str | None
    decision_blocked_reason: str | None
    cooldown_seconds: int
    required_challenge_keys: tuple[str, ...]
    risk_acknowledgement_required: bool
    current_request: ApprovalRequestSummary | None = None
    latest_decision: ApprovalDecisionSummary | None = None
    machine_evidence_summary: ApprovalMachineEvidenceSummary | None = None


@dataclass(frozen=True, slots=True)
class _RequestProbe:
    request_id: str
    candidate_id: str
    idempotency_key: str
    material: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _DecisionProbe:
    decision_id: str
    candidate_id: str
    idempotency_key: str
    material: dict[str, Any]


class _RequestCommitOutcomeUncertain(RuntimeError):
    def __init__(self, probe: _RequestProbe) -> None:
        super().__init__("APPROVAL_REQUEST_COMMIT_OUTCOME_UNKNOWN")
        self.probe = probe


class _DecisionCommitOutcomeUncertain(RuntimeError):
    def __init__(self, probe: _DecisionProbe) -> None:
        super().__init__("APPROVAL_DECISION_COMMIT_OUTCOME_UNKNOWN")
        self.probe = probe


class ApprovalService:
    """Write exact, append-only human decisions from server-resolved authority."""

    def __init__(
        self,
        *,
        evidence_packages: EvidencePackageService | None = None,
        authority_resolver: ApprovalAuthorityResolver | None = None,
        promotion_gates: PromotionGateEngine | None = None,
    ) -> None:
        self._evidence_packages = evidence_packages or EvidencePackageService()
        self._authority = authority_resolver or ApprovalAuthorityResolver()
        self._promotion_gates = promotion_gates or PromotionGateEngine()

    async def request_approval(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
        idempotency_key: str,
    ) -> ResearchApprovalRequest:
        """Open a server-timed request; no caller authority fields are accepted."""

        _validate_common_input(
            run_id=run_id,
            candidate_id=candidate_id,
            gate_input_evidence_hash=gate_input_evidence_hash,
            evidence_package_hash=evidence_package_hash,
            idempotency_key=idempotency_key,
        )
        async with _operation_lock(candidate_id):
            replay = await self._read_existing_request_replay(
                authenticated_actor_id=authenticated_actor_id,
                run_id=run_id,
                candidate_id=candidate_id,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
                idempotency_key=idempotency_key,
            )
            if replay is not None:
                return replay
            try:
                return await self._request_once(
                    authenticated_actor_id=authenticated_actor_id,
                    run_id=run_id,
                    candidate_id=candidate_id,
                    gate_input_evidence_hash=gate_input_evidence_hash,
                    evidence_package_hash=evidence_package_hash,
                    idempotency_key=idempotency_key,
                )
            except _RequestCommitOutcomeUncertain as exc:
                committed = await self._read_request_probe(exc.probe)
                if committed is not None:
                    return committed
                raise ValueError("APPROVAL_REQUEST_COMMIT_OUTCOME_UNKNOWN") from None

    async def decide(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
        approval_request_id: str,
        decision: str,
        reason: str,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
        idempotency_key: str,
        challenge_responses: Mapping[str, str] | None = None,
        residual_risk_acknowledgement: str | None = None,
    ) -> ResearchHumanDecision:
        """Record one exact decision using a current human grant and DB clock."""

        _validate_common_input(
            run_id=run_id,
            candidate_id=candidate_id,
            gate_input_evidence_hash=gate_input_evidence_hash,
            evidence_package_hash=evidence_package_hash,
            idempotency_key=idempotency_key,
        )
        reason, challenge_responses, residual_risk_acknowledgement = _validate_decision_input(
            approval_request_id=approval_request_id,
            decision=decision,
            reason=reason,
            challenge_responses=challenge_responses,
            residual_risk_acknowledgement=residual_risk_acknowledgement,
        )
        async with _operation_lock(candidate_id):
            replay = await self._read_existing_decision_replay(
                authenticated_actor_id=authenticated_actor_id,
                run_id=run_id,
                candidate_id=candidate_id,
                approval_request_id=approval_request_id,
                decision=decision,
                reason=reason,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
                idempotency_key=idempotency_key,
                challenge_responses=challenge_responses,
                residual_risk_acknowledgement=residual_risk_acknowledgement,
            )
            if replay is not None:
                return replay
            try:
                return await self._decide_once(
                    authenticated_actor_id=authenticated_actor_id,
                    run_id=run_id,
                    candidate_id=candidate_id,
                    approval_request_id=approval_request_id,
                    decision=decision,
                    reason=reason,
                    gate_input_evidence_hash=gate_input_evidence_hash,
                    evidence_package_hash=evidence_package_hash,
                    idempotency_key=idempotency_key,
                    challenge_responses=challenge_responses,
                    residual_risk_acknowledgement=residual_risk_acknowledgement,
                )
            except _DecisionCommitOutcomeUncertain as exc:
                committed = await self._read_decision_probe(exc.probe)
                if committed is not None:
                    return committed
                raise ValueError("APPROVAL_DECISION_COMMIT_OUTCOME_UNKNOWN") from None

    async def approval_context(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
    ) -> ApprovalContext:
        """Return safe capabilities for an owner or exact granted reviewer."""

        async with database.async_session_maker() as session:
            request_blocked_reason: str | None
            decision_blocked_reason: str | None
            try:
                request_authority = await self._authority.resolve_request_in_session(
                    session,
                    authenticated_actor_id=authenticated_actor_id,
                    run_id=run_id,
                    candidate_id=candidate_id,
                )
            except ValueError as request_error:
                try:
                    authority = await self._authority.resolve_decision_in_session(
                        session,
                        authenticated_actor_id=authenticated_actor_id,
                        run_id=run_id,
                        candidate_id=candidate_id,
                    )
                except ValueError:
                    # Preserve the non-disclosing owner/scope error.  In particular,
                    # an ungranted foreign actor must not learn that a run exists.
                    raise request_error from None
                can_request, can_decide = False, True
                request_blocked_reason = "OWNER_REQUIRED"
                decision_blocked_reason = None
            else:
                authority = request_authority
                can_request = True
                request_blocked_reason = None
                try:
                    authority = await self._authority.resolve_decision_in_session(
                        session,
                        authenticated_actor_id=authenticated_actor_id,
                        run_id=run_id,
                        candidate_id=candidate_id,
                    )
                except ValueError:
                    can_decide = False
                    decision_blocked_reason = "AUTHORITY_REQUIRED"
                else:
                    can_decide = True
                    decision_blocked_reason = None

            pending_requests = list(
                (
                    await session.scalars(
                        select(ResearchApprovalRequest)
                        .where(
                            ResearchApprovalRequest.run_id == authority.run.id,
                            ResearchApprovalRequest.candidate_id == authority.candidate.id,
                            ResearchApprovalRequest.status == "PENDING",
                            ResearchApprovalRequest.request_material_hash.is_not(None),
                        )
                        .order_by(
                            ResearchApprovalRequest.requested_at.desc(),
                            ResearchApprovalRequest.id.desc(),
                        )
                    )
                ).all()
            )
            current_request_model = next(
                (
                    item
                    for item in pending_requests
                    if _as_utc(item.expires_at) > authority.database_now
                ),
                None,
            )
            latest_decision_model = await session.scalar(
                select(ResearchHumanDecision)
                .where(
                    ResearchHumanDecision.run_id == authority.run.id,
                    ResearchHumanDecision.candidate_id == authority.candidate.id,
                    ResearchHumanDecision.decision_material_hash.is_not(None),
                )
                .order_by(
                    ResearchHumanDecision.decided_at.desc(),
                    ResearchHumanDecision.id.desc(),
                )
                .limit(1)
            )
            machine_evidence_summary = None
            evidence_is_current = False
            context_package_model: ResearchEvidencePackage | None = None
            denial_fence_model: ResearchApprovalDenialFence | None = None
            if current_request_model is not None:
                try:
                    package = await self._validate_machine_authority(
                        session,
                        authority=authority,
                        gate_input_evidence_hash=current_request_model.gate_input_evidence_hash,
                        evidence_package_hash=current_request_model.evidence_package_hash,
                    )
                    _require_request_binding(
                        current_request_model,
                        authority=authority,
                        package=package,
                        gate_input_evidence_hash=current_request_model.gate_input_evidence_hash,
                        evidence_package_hash=current_request_model.evidence_package_hash,
                    )
                    machine_evidence_summary = await self._load_machine_evidence_summary(
                        session,
                        package=package,
                    )
                    evidence_is_current = True
                    context_package_model = package
                except ValueError:
                    pass
            else:
                active_packages = list(
                    (
                        await session.scalars(
                            select(ResearchEvidencePackage)
                            .where(
                                ResearchEvidencePackage.run_id == authority.run.id,
                                ResearchEvidencePackage.candidate_id == authority.candidate.id,
                                ResearchEvidencePackage.promotion_policy_version
                                == authority.run.promotion_policy_version,
                                ResearchEvidencePackage.status == "ACTIVE",
                            )
                            .order_by(
                                ResearchEvidencePackage.created_at.desc(),
                                ResearchEvidencePackage.id.desc(),
                            )
                            .with_for_update()
                        )
                    ).all()
                )
                if len(active_packages) != 1:
                    if can_request:
                        can_request = False
                        request_blocked_reason = (
                            "EVIDENCE_AMBIGUOUS"
                            if len(active_packages) > 1
                            else "EVIDENCE_NOT_CURRENT"
                        )
                else:
                    context_package = active_packages[0]
                    try:
                        package = await self._validate_machine_authority(
                            session,
                            authority=authority,
                            gate_input_evidence_hash=context_package.gate_input_evidence_hash,
                            evidence_package_hash=context_package.manifest_hash,
                        )
                        machine_evidence_summary = await self._load_machine_evidence_summary(
                            session,
                            package=package,
                        )
                        evidence_is_current = True
                        context_package_model = package
                    except ValueError:
                        if can_request:
                            can_request = False
                            request_blocked_reason = "EVIDENCE_NOT_CURRENT"
            if evidence_is_current and context_package_model is not None:
                denial_scope = _denial_scope_material(
                    authority,
                    package=context_package_model,
                    gate_input_evidence_hash=context_package_model.gate_input_evidence_hash,
                    evidence_package_hash=context_package_model.manifest_hash,
                )
                denial_fence_model = await _load_denial_fence(session, denial_scope)
                if denial_fence_model is not None:
                    can_request = False
                    can_decide = False
                    request_blocked_reason = "APPROVAL_EVIDENCE_DENIED"
                    decision_blocked_reason = "APPROVAL_EVIDENCE_DENIED"
                    latest_decision_model = await _load_denial_decision(
                        session,
                        fence=denial_fence_model,
                    )
            if can_decide and current_request_model is None:
                can_decide = False
                decision_blocked_reason = "REQUEST_REQUIRED"
            elif (
                can_decide
                and current_request_model is not None
                and _as_utc(current_request_model.eligible_at) > authority.database_now
            ):
                can_decide = False
                decision_blocked_reason = "COOLDOWN_ACTIVE"
            elif can_decide and not evidence_is_current:
                can_decide = False
                decision_blocked_reason = "EVIDENCE_NOT_CURRENT"
            can_approve = bool(
                can_decide
                and current_request_model is not None
                and evidence_is_current
                and denial_fence_model is None
            )
        return ApprovalContext(
            run_id=authority.run.id,
            candidate_id=authority.candidate.id,
            candidate_hash=authority.candidate.candidate_hash,
            policy_version=authority.policy.version,
            policy_material_hash=authority.policy.material_hash,
            approval_mode=authority.policy.mode,
            can_request=can_request,
            can_decide=can_decide,
            can_approve=can_approve,
            request_blocked_reason=request_blocked_reason,
            decision_blocked_reason=decision_blocked_reason,
            cooldown_seconds=authority.policy.cooldown_seconds,
            required_challenge_keys=authority.policy.required_challenge_keys,
            risk_acknowledgement_required=authority.policy.risk_acknowledgement_required,
            current_request=(
                _approval_request_summary(current_request_model)
                if current_request_model is not None
                else None
            ),
            latest_decision=(
                _approval_decision_summary(latest_decision_model)
                if latest_decision_model is not None
                else None
            ),
            machine_evidence_summary=machine_evidence_summary,
        )

    async def is_currently_approved(
        self,
        *,
        run_id: str,
        candidate_id: str,
        promotion_policy_version: str,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
    ) -> bool:
        """Revalidate latest decision, package, gates, grant, user, profile, and policy."""

        if (
            not run_id.strip()
            or not candidate_id.strip()
            or not promotion_policy_version.strip()
            or _SHA256_HEX.fullmatch(gate_input_evidence_hash) is None
            or _SHA256_HEX.fullmatch(evidence_package_hash) is None
        ):
            return False
        async with _operation_lock(candidate_id):
            return await self._is_currently_approved_locked(
                run_id=run_id,
                candidate_id=candidate_id,
                promotion_policy_version=promotion_policy_version,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
            )

    async def _is_currently_approved_locked(
        self,
        *,
        run_id: str,
        candidate_id: str,
        promotion_policy_version: str,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
    ) -> bool:
        """Recheck currentness while the candidate write order is fenced."""

        async with database.async_session_maker() as session:
            discovery = await session.execute(
                select(
                    ResearchHumanDecision.id,
                    ResearchHumanDecision.actor_id,
                    ResearchHumanDecision.grant_id,
                )
                .where(
                    ResearchHumanDecision.run_id == run_id,
                    ResearchHumanDecision.candidate_id == candidate_id,
                    ResearchHumanDecision.decision_material_hash.is_not(None),
                )
                .order_by(
                    ResearchHumanDecision.decided_at.desc(),
                    ResearchHumanDecision.id.desc(),
                )
                .limit(1)
            )
            discovered = discovery.one_or_none()
            if discovered is None or discovered.grant_id is None:
                return False
            try:
                authority = await self._authority.revalidate_grant_in_session(
                    session,
                    authenticated_actor_id=discovered.actor_id,
                    run_id=run_id,
                    candidate_id=candidate_id,
                    grant_id=discovered.grant_id,
                )
                if (
                    authority.run.promotion_policy_version != promotion_policy_version
                    or not await self._promotion_gates.is_eligible_in_session(
                        session,
                        candidate_id=candidate_id,
                        policy_version=promotion_policy_version,
                        input_evidence_hash=gate_input_evidence_hash,
                    )
                ):
                    return False
                package = await self._evidence_packages.validate_for_approval_in_session(
                    session,
                    candidate_id=candidate_id,
                    promotion_policy_version=promotion_policy_version,
                    gate_input_evidence_hash=gate_input_evidence_hash,
                    evidence_package_hash=evidence_package_hash,
                )
                denial_scope = _denial_scope_material(
                    authority,
                    package=package,
                    gate_input_evidence_hash=gate_input_evidence_hash,
                    evidence_package_hash=evidence_package_hash,
                )
                if await _load_denial_fence(session, denial_scope) is not None:
                    return False
            except ValueError:
                return False
            latest = (
                await session.execute(
                    select(
                        ResearchHumanDecision.id,
                        ResearchHumanDecision.actor_id,
                        ResearchHumanDecision.grant_id,
                    )
                    .where(
                        ResearchHumanDecision.run_id == run_id,
                        ResearchHumanDecision.candidate_id == candidate_id,
                        ResearchHumanDecision.decision_material_hash.is_not(None),
                    )
                    .order_by(
                        ResearchHumanDecision.decided_at.desc(),
                        ResearchHumanDecision.id.desc(),
                    )
                    .limit(1)
                )
            ).one_or_none()
            if latest is None or latest.id != discovered.id:
                return False
            decision = await session.scalar(
                select(ResearchHumanDecision)
                .where(ResearchHumanDecision.id == discovered.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if decision is None:
                return False
            return _decision_is_current(
                decision,
                authority=authority,
                package=package,
                gate_input_evidence_hash=gate_input_evidence_hash,
            )

    async def _request_once(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
        idempotency_key: str,
    ) -> ResearchApprovalRequest:
        async with database.async_session_maker() as session:
            authority = await self._authority.resolve_request_in_session(
                session,
                authenticated_actor_id=authenticated_actor_id,
                run_id=run_id,
                candidate_id=candidate_id,
            )
            package = await self._validate_machine_authority(
                session,
                authority=authority,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
            )
            material = _request_material(
                authority,
                package=package,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
            )
            existing = await session.scalar(
                select(ResearchApprovalRequest)
                .where(
                    ResearchApprovalRequest.candidate_id == candidate_id,
                    ResearchApprovalRequest.idempotency_key == idempotency_key,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if existing is not None:
                if not _request_matches(existing, material):
                    raise ValueError("APPROVAL_REQUEST_IDEMPOTENCY_CONFLICT")
                return existing
            await _require_no_denial_fence(
                session,
                authority=authority,
                package=package,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
            )
            requested_at = authority.database_now
            model = ResearchApprovalRequest(
                candidate_id=candidate_id,
                run_id=run_id,
                workspace_id=authority.run.workspace_id,
                evidence_package_id=package.id,
                requested_by=authenticated_actor_id,
                policy_version=authority.policy.version,
                policy_material_hash=authority.policy.material_hash,
                approval_mode=authority.policy.mode,
                capability_profile_id=authority.profile.profile_id,
                capability_profile_version=authority.profile.version,
                capability_evidence_hash=approval_capability_profile_material_hash(
                    authority.profile
                ),
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
                idempotency_key=idempotency_key,
                request_material_hash=content_hash(material),
                status="PENDING",
                requested_at=requested_at,
                eligible_at=requested_at + timedelta(seconds=authority.policy.cooldown_seconds),
                expires_at=requested_at + timedelta(seconds=authority.policy.ttl_seconds),
            )
            session.add(model)
            try:
                await session.flush()
            except IntegrityError as exc:
                await session.rollback()
                probe = _RequestProbe(model.id, candidate_id, idempotency_key, material)
                raise _RequestCommitOutcomeUncertain(probe) from exc
            probe = _RequestProbe(model.id, candidate_id, idempotency_key, material)
            try:
                await session.commit()
            except Exception as exc:
                await session.rollback()
                raise _RequestCommitOutcomeUncertain(probe) from exc
            await session.refresh(model)
            return model

    async def _decide_once(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
        approval_request_id: str,
        decision: str,
        reason: str,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
        idempotency_key: str,
        challenge_responses: Mapping[str, str] | None,
        residual_risk_acknowledgement: str | None,
    ) -> ResearchHumanDecision:
        async with database.async_session_maker() as session:
            authority = await self._authority.resolve_decision_in_session(
                session,
                authenticated_actor_id=authenticated_actor_id,
                run_id=run_id,
                candidate_id=candidate_id,
            )
            package = await self._validate_machine_authority(
                session,
                authority=authority,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
            )
            request = await session.get(
                ResearchApprovalRequest,
                approval_request_id,
                with_for_update=True,
            )
            _require_request_binding(
                request,
                authority=authority,
                package=package,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
            )
            challenge_records = _challenge_records(
                authority.policy,
                challenge_responses,
                require_complete=decision == "APPROVED",
            )
            risk_text = (residual_risk_acknowledgement or "").strip()
            if (
                decision == "APPROVED"
                and authority.policy.risk_acknowledgement_required
                and not risk_text
            ):
                raise ValueError("APPROVAL_RISK_ACKNOWLEDGEMENT_REQUIRED")
            decision_material = _decision_material(
                authority,
                package=package,
                request_id=request.id if request is not None else "",
                decision=decision,
                reason=reason,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
                challenge_records=challenge_records,
                residual_risk_acknowledgement=risk_text,
            )
            existing = await session.scalar(
                select(ResearchHumanDecision)
                .where(
                    ResearchHumanDecision.candidate_id == candidate_id,
                    ResearchHumanDecision.idempotency_key == idempotency_key,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if existing is not None:
                if not _decision_matches(existing, decision_material):
                    raise ValueError("APPROVAL_IDEMPOTENCY_CONFLICT")
                return existing
            denial_scope = _denial_scope_material(
                authority,
                package=package,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
            )
            existing_fence = await _load_denial_fence(session, denial_scope)
            if decision == "APPROVED" and existing_fence is not None:
                raise ValueError("APPROVAL_EVIDENCE_DENIED")
            if request is None:
                raise ValueError("APPROVAL_REQUEST_NOT_FOUND")
            if request.status != "PENDING":
                raise ValueError("APPROVAL_REQUEST_NOT_PENDING")
            now = authority.database_now
            if _as_utc(request.expires_at) <= now:
                raise ValueError("APPROVAL_REQUEST_EXPIRED")
            if decision == "APPROVED" and _as_utc(request.eligible_at) > now:
                raise ValueError("APPROVAL_COOLDOWN_ACTIVE")
            grant = authority.grant
            if grant is None:
                raise ValueError("APPROVAL_GRANT_REQUIRED")
            expires_at = min(
                _as_utc(request.expires_at),
                _as_utc(grant.expires_at),
                _as_utc(authority.profile.expires_at),
                now + timedelta(seconds=authority.policy.ttl_seconds),
            )
            request.status = "DECIDED"
            request.decided_at = now
            model = ResearchHumanDecision(
                candidate_id=candidate_id,
                run_id=run_id,
                workspace_id=authority.run.workspace_id,
                approval_request_id=request.id,
                evidence_package_id=package.id,
                decision=decision,
                actor_id=authenticated_actor_id,
                domain_permissions=[authority.policy.required_permission],
                policy_version=authority.policy.version,
                policy_material_hash=authority.policy.material_hash,
                approval_mode=authority.policy.mode,
                capability_profile_id=authority.profile.profile_id,
                capability_profile_version=authority.profile.version,
                capability_evidence_hash=approval_capability_profile_material_hash(
                    authority.profile
                ),
                grant_id=grant.id,
                grant_hash=grant.grant_hash,
                single_actor=authority.policy.mode == "single_actor",
                risk_acknowledgement=bool(risk_text),
                comment=reason,
                challenge_records=challenge_records,
                challenge_hash=content_hash(challenge_records),
                risk_acknowledgement_hash=content_hash(risk_text),
                reason_hash=content_hash(reason),
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
                idempotency_key=idempotency_key,
                decision_material_hash=content_hash(decision_material),
                requested_at=request.requested_at,
                eligible_at=request.eligible_at,
                decided_at=now,
                expires_at=expires_at,
            )
            session.add(model)
            try:
                await session.flush()
                if decision in {"REJECTED", "REQUESTED_CHANGES"}:
                    if existing_fence is None:
                        session.add(
                            ResearchApprovalDenialFence(
                                candidate_id=candidate_id,
                                run_id=run_id,
                                evidence_package_id=package.id,
                                decision_id=model.id,
                                decision=decision,
                                promotion_policy_version=authority.run.promotion_policy_version,
                                approval_policy_version=authority.policy.version,
                                approval_policy_material_hash=authority.policy.material_hash,
                                gate_input_evidence_hash=gate_input_evidence_hash,
                                evidence_package_hash=evidence_package_hash,
                                approval_binding_hash=package.approval_binding_hash,
                                fence_scope_hash=content_hash(denial_scope),
                                created_at=now,
                            )
                        )
                        await session.flush()
            except IntegrityError as exc:
                await session.rollback()
                probe = _DecisionProbe(model.id, candidate_id, idempotency_key, decision_material)
                raise _DecisionCommitOutcomeUncertain(probe) from exc
            probe = _DecisionProbe(model.id, candidate_id, idempotency_key, decision_material)
            try:
                await session.commit()
            except Exception as exc:
                await session.rollback()
                raise _DecisionCommitOutcomeUncertain(probe) from exc
            await session.refresh(model)
            return model

    async def _validate_machine_authority(
        self,
        session: Any,
        *,
        authority: ApprovalAuthority,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
    ) -> ResearchEvidencePackage:
        if not await self._promotion_gates.is_eligible_in_session(
            session,
            candidate_id=authority.candidate.id,
            policy_version=authority.run.promotion_policy_version,
            input_evidence_hash=gate_input_evidence_hash,
        ):
            raise ValueError("APPROVAL_HARD_GATES_NOT_PASS")
        package = await self._evidence_packages.validate_for_approval_in_session(
            session,
            candidate_id=authority.candidate.id,
            promotion_policy_version=authority.run.promotion_policy_version,
            gate_input_evidence_hash=gate_input_evidence_hash,
            evidence_package_hash=evidence_package_hash,
        )
        if package.user_id != authority.owner_id or package.run_id != authority.run.id:
            raise ValueError("APPROVAL_SCOPE_NOT_FOUND")
        return package

    async def _load_machine_evidence_summary(
        self,
        session: Any,
        *,
        package: ResearchEvidencePackage,
    ) -> ApprovalMachineEvidenceSummary:
        """Load the exact thirteen allowlisted gates for a validated active package."""

        if (
            package.status != "ACTIVE"
            or package.command_id is None
            or package.evaluation_id is None
            or _SHA256_HEX.fullmatch(package.approval_binding_hash) is None
        ):
            raise ValueError("APPROVAL_MACHINE_EVIDENCE_INCOMPLETE")
        rows = list(
            (
                await session.scalars(
                    select(ResearchGateDecision).where(
                        ResearchGateDecision.candidate_id == package.candidate_id,
                        ResearchGateDecision.evaluation_id == package.evaluation_id,
                        ResearchGateDecision.policy_version == package.promotion_policy_version,
                        ResearchGateDecision.input_evidence_hash
                        == package.gate_input_evidence_hash,
                    )
                )
            ).all()
        )
        by_code = {row.gate_code: row for row in rows}
        if (
            len(rows) != len(REQUIRED_HOLDOUT_GATE_CODES)
            or set(by_code) != set(REQUIRED_HOLDOUT_GATE_CODES)
            or any(
                row.status != "PASS"
                or _SHA256_HEX.fullmatch(row.input_evidence_hash) is None
                or not row.executor_version.strip()
                for row in rows
            )
        ):
            raise ValueError("APPROVAL_MACHINE_EVIDENCE_INCOMPLETE")
        return ApprovalMachineEvidenceSummary(
            package=ApprovalEvidencePackageSummary(
                id=package.id,
                candidate_id=package.candidate_id,
                status=package.status,
                promotion_policy_version=package.promotion_policy_version,
                command_id=package.command_id,
                evaluation_id=package.evaluation_id,
                gate_input_evidence_hash=package.gate_input_evidence_hash,
                manifest_hash=package.manifest_hash,
                approval_binding_hash=package.approval_binding_hash,
            ),
            gates=tuple(
                ApprovalGateSummary(
                    gate_code=code,
                    status=by_code[code].status,
                    reason_code=f"HOLDOUT_{code}_PASSED",
                    input_evidence_hash=by_code[code].input_evidence_hash,
                    executor_version=(
                        by_code[code].executor_version
                        if by_code[code].executor_version in _SAFE_GATE_EXECUTOR_VERSIONS
                        else "RESEARCH_GATE_EXECUTOR_REDACTED"
                    ),
                    evaluated_at=by_code[code].evaluated_at,
                )
                for code in REQUIRED_HOLDOUT_GATE_CODES
            ),
        )

    async def _read_request_probe(self, probe: _RequestProbe) -> ResearchApprovalRequest | None:
        async with database.async_session_maker() as session:
            model = await session.scalar(
                select(ResearchApprovalRequest).where(
                    ResearchApprovalRequest.candidate_id == probe.candidate_id,
                    ResearchApprovalRequest.idempotency_key == probe.idempotency_key,
                )
            )
        if model is None:
            return None
        if not _request_matches(model, probe.material):
            raise ValueError("APPROVAL_REQUEST_IDEMPOTENCY_CONFLICT")
        return model

    async def _read_existing_request_replay(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
        idempotency_key: str,
    ) -> ResearchApprovalRequest | None:
        """Read an already committed exact command before live authority revalidation."""

        async with database.async_session_maker() as session:
            model = await session.scalar(
                select(ResearchApprovalRequest).where(
                    ResearchApprovalRequest.candidate_id == candidate_id,
                    ResearchApprovalRequest.idempotency_key == idempotency_key,
                )
            )
            if model is None:
                return None
            if (
                model.run_id != run_id
                or model.candidate_id != candidate_id
                or model.requested_by != authenticated_actor_id
            ):
                raise ValueError("APPROVAL_SCOPE_NOT_FOUND")
            package = (
                await session.get(ResearchEvidencePackage, model.evidence_package_id)
                if model.evidence_package_id is not None
                else None
            )
            material = _stored_request_material(model, package=package)
            if (
                model.gate_input_evidence_hash != gate_input_evidence_hash
                or model.evidence_package_hash != evidence_package_hash
                or material is None
                or not _request_matches(model, material)
            ):
                raise ValueError("APPROVAL_REQUEST_IDEMPOTENCY_CONFLICT")
            return model

    async def _read_decision_probe(self, probe: _DecisionProbe) -> ResearchHumanDecision | None:
        async with database.async_session_maker() as session:
            model = await session.scalar(
                select(ResearchHumanDecision).where(
                    ResearchHumanDecision.candidate_id == probe.candidate_id,
                    ResearchHumanDecision.idempotency_key == probe.idempotency_key,
                )
            )
        if model is None:
            return None
        if not _decision_matches(model, probe.material):
            raise ValueError("APPROVAL_IDEMPOTENCY_CONFLICT")
        return model

    async def _read_existing_decision_replay(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
        approval_request_id: str,
        decision: str,
        reason: str,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
        idempotency_key: str,
        challenge_responses: Mapping[str, str] | None,
        residual_risk_acknowledgement: str | None,
    ) -> ResearchHumanDecision | None:
        """Return only the same committed decision, even after live authority expires."""

        async with database.async_session_maker() as session:
            model = await session.scalar(
                select(ResearchHumanDecision).where(
                    ResearchHumanDecision.candidate_id == candidate_id,
                    ResearchHumanDecision.idempotency_key == idempotency_key,
                )
            )
            if model is None:
                return None
            if (
                model.run_id != run_id
                or model.candidate_id != candidate_id
                or model.actor_id != authenticated_actor_id
            ):
                raise ValueError("APPROVAL_SCOPE_NOT_FOUND")
            stored_challenge_order = tuple(
                item["key"]
                for item in list(model.challenge_records or [])
                if isinstance(item, dict) and isinstance(item.get("key"), str)
            )
            challenge_records = _replay_challenge_records(
                challenge_responses,
                stored_order=stored_challenge_order,
            )
            risk_text = (residual_risk_acknowledgement or "").strip()
            material = _stored_decision_material(model)
            grant_is_exact = (
                material is not None
                and await self._authority.replay_grant_is_historically_exact_in_session(
                    session,
                    actor_id=model.actor_id,
                    run_id=model.run_id or "",
                    workspace_id=model.workspace_id,
                    grant_id=model.grant_id or "",
                    grant_hash=model.grant_hash or "",
                    permission=material["permission"],
                    decided_at=model.decided_at,
                )
            )
            if (
                model.approval_request_id != approval_request_id
                or model.decision != decision
                or (model.comment or "") != reason
                or model.gate_input_evidence_hash != gate_input_evidence_hash
                or model.evidence_package_hash != evidence_package_hash
                or model.challenge_hash != content_hash(challenge_records)
                or model.risk_acknowledgement_hash != content_hash(risk_text)
                or material is None
                or not _decision_matches(model, material)
                or not grant_is_exact
            ):
                raise ValueError("APPROVAL_IDEMPOTENCY_CONFLICT")
            return model


def _validate_common_input(
    *,
    run_id: str,
    candidate_id: str,
    gate_input_evidence_hash: str,
    evidence_package_hash: str,
    idempotency_key: str,
) -> None:
    strings = (run_id, candidate_id, idempotency_key)
    if (
        any(not isinstance(value, str) for value in strings)
        or any(not value.strip() for value in strings)
        or run_id != run_id.strip()
        or candidate_id != candidate_id.strip()
        or idempotency_key != idempotency_key.strip()
        or len(idempotency_key) > 128
        or not isinstance(gate_input_evidence_hash, str)
        or not isinstance(evidence_package_hash, str)
        or _SHA256_HEX.fullmatch(gate_input_evidence_hash) is None
        or _SHA256_HEX.fullmatch(evidence_package_hash) is None
    ):
        raise ValueError("APPROVAL_IDEMPOTENCY_OR_EVIDENCE_INVALID")


def _validate_decision_input(
    *,
    approval_request_id: object,
    decision: object,
    reason: object,
    challenge_responses: object,
    residual_risk_acknowledgement: object,
) -> tuple[str, dict[str, str], str | None]:
    """Validate the public service boundary independently of Pydantic/API callers."""

    if (
        not isinstance(approval_request_id, str)
        or not approval_request_id.strip()
        or approval_request_id != approval_request_id.strip()
        or len(approval_request_id) > 36
    ):
        raise ValueError("APPROVAL_REQUEST_REQUIRED")
    if not isinstance(decision, str) or decision not in _VALID_DECISIONS:
        raise ValueError("APPROVAL_DECISION_INVALID")
    if not isinstance(reason, str) or len(reason) > _MAX_HUMAN_TEXT_LENGTH:
        raise ValueError("APPROVAL_REASON_REQUIRED")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValueError("APPROVAL_REASON_REQUIRED")
    if challenge_responses is None:
        responses: dict[str, str] = {}
    elif isinstance(challenge_responses, Mapping):
        if len(challenge_responses) > _MAX_CHALLENGE_COUNT:
            raise ValueError("APPROVAL_CHALLENGE_INVALID")
        responses = {}
        for key, answer in challenge_responses.items():
            if (
                not isinstance(key, str)
                or not key.strip()
                or key != key.strip()
                or len(key) > _MAX_CHALLENGE_KEY_LENGTH
                or not isinstance(answer, str)
                or len(answer) > _MAX_HUMAN_TEXT_LENGTH
            ):
                raise ValueError("APPROVAL_CHALLENGE_INVALID")
            responses[key] = answer
    else:
        raise ValueError("APPROVAL_CHALLENGE_INVALID")
    if residual_risk_acknowledgement is not None and (
        not isinstance(residual_risk_acknowledgement, str)
        or len(residual_risk_acknowledgement) > _MAX_HUMAN_TEXT_LENGTH
    ):
        raise ValueError("APPROVAL_RISK_ACKNOWLEDGEMENT_INVALID")
    return normalized_reason, responses, residual_risk_acknowledgement


def _approval_request_summary(model: ResearchApprovalRequest) -> ApprovalRequestSummary:
    """Build the allowlisted current-request projection."""

    if (
        model.run_id is None
        or model.evidence_package_id is None
        or model.policy_material_hash is None
        or model.approval_mode is None
        or model.request_material_hash is None
    ):
        raise ValueError("APPROVAL_REQUEST_EVIDENCE_MISMATCH")
    return ApprovalRequestSummary(
        id=model.id,
        run_id=model.run_id,
        candidate_id=model.candidate_id,
        evidence_package_id=model.evidence_package_id,
        policy_version=model.policy_version,
        policy_material_hash=model.policy_material_hash,
        approval_mode=model.approval_mode,
        gate_input_evidence_hash=model.gate_input_evidence_hash,
        evidence_package_hash=model.evidence_package_hash,
        request_material_hash=model.request_material_hash,
        status=model.status,
        requested_at=model.requested_at,
        eligible_at=model.eligible_at,
        expires_at=model.expires_at,
        decided_at=model.decided_at,
    )


def _approval_decision_summary(model: ResearchHumanDecision) -> ApprovalDecisionSummary:
    """Build the allowlisted latest-decision projection."""

    if (
        model.run_id is None
        or model.approval_request_id is None
        or model.policy_material_hash is None
        or model.gate_input_evidence_hash is None
        or model.expires_at is None
        or model.decision_material_hash is None
    ):
        raise ValueError("APPROVAL_DECISION_EVIDENCE_MISMATCH")
    return ApprovalDecisionSummary(
        id=model.id,
        run_id=model.run_id,
        candidate_id=model.candidate_id,
        approval_request_id=model.approval_request_id,
        decision=model.decision,
        policy_version=model.policy_version,
        policy_material_hash=model.policy_material_hash,
        approval_mode=model.approval_mode,
        gate_input_evidence_hash=model.gate_input_evidence_hash,
        evidence_package_hash=model.evidence_package_hash,
        decision_material_hash=model.decision_material_hash,
        decision_intent_hash=approval_decision_record_intent_hash(model),
        risk_acknowledgement=model.risk_acknowledgement,
        challenge_keys=tuple(
            item["key"]
            for item in list(model.challenge_records or [])
            if isinstance(item, dict) and isinstance(item.get("key"), str)
        ),
        reason=safe_approval_human_text(model.comment or ""),
        decided_at=model.decided_at,
        expires_at=model.expires_at,
    )


def safe_approval_human_text(value: str) -> str:
    """Return bounded human text while denying URI and sealed-value leakage."""

    redacted = str(redact_sensitive_payload(value))
    if (
        redacted != value
        or _URI_SCHEME.search(redacted)
        or _POSIX_ABSOLUTE_PATH.search(redacted)
        or _WINDOWS_ABSOLUTE_PATH.search(redacted)
        or _UNC_ABSOLUTE_PATH.search(redacted)
        or re.search(r"\b(?:sealed|raw)(?:\b|[_-])", redacted, re.IGNORECASE)
    ):
        return "[REDACTED]"
    return redacted[:_MAX_HUMAN_TEXT_LENGTH]


def approval_decision_intent_hash(
    *,
    approval_request_id: str,
    decision: str,
    reason: str,
    gate_input_evidence_hash: str,
    evidence_package_hash: str,
    challenge_keys: tuple[str, ...] | list[str],
    challenge_responses: Mapping[str, str] | None,
    residual_risk_acknowledgement: str | None,
) -> str:
    """Hash the normalized browser-known decision intent without retaining human text.

    Text is stripped, then represented only by canonical SHA-256 identities. Challenge
    records follow the server-provided policy key order. The returned hash is SHA-256
    over canonical JSON (`sort_keys`, compact separators, UTF-8, no ASCII escaping).
    """

    reason_text = reason.strip()
    risk_text = (residual_risk_acknowledgement or "").strip()
    responses = dict(challenge_responses or {})
    ordered_keys = tuple(challenge_keys)
    if (
        not approval_request_id.strip()
        or decision not in _VALID_DECISIONS
        or not reason_text
        or len(set(ordered_keys)) != len(ordered_keys)
        or any(not isinstance(key, str) or not key.strip() for key in ordered_keys)
        or set(responses) - set(ordered_keys)
        or any(not isinstance(value, str) for value in responses.values())
        or _SHA256_HEX.fullmatch(gate_input_evidence_hash) is None
        or _SHA256_HEX.fullmatch(evidence_package_hash) is None
    ):
        raise ValueError("APPROVAL_DECISION_INTENT_INVALID")
    challenge_records = [
        {"key": key, "answer_hash": content_hash(responses[key].strip())}
        for key in ordered_keys
        if key in responses and responses[key].strip()
    ]
    return content_hash(
        _decision_intent_material(
            approval_request_id=approval_request_id,
            decision=decision,
            reason_hash=content_hash(reason_text),
            gate_input_evidence_hash=gate_input_evidence_hash,
            evidence_package_hash=evidence_package_hash,
            challenge_hash=content_hash(challenge_records),
            risk_acknowledgement_hash=content_hash(risk_text),
        )
    )


def approval_decision_record_intent_hash(model: ResearchHumanDecision) -> str:
    """Derive the public intent receipt from one integrity-checked stored decision."""

    hashes = (
        model.reason_hash,
        model.challenge_hash,
        model.risk_acknowledgement_hash,
        model.gate_input_evidence_hash,
        model.evidence_package_hash,
    )
    if (
        model.approval_request_id is None
        or model.decision not in _VALID_DECISIONS
        or any(not isinstance(item, str) or _SHA256_HEX.fullmatch(item) is None for item in hashes)
    ):
        raise ValueError("APPROVAL_DECISION_EVIDENCE_MISMATCH")
    return content_hash(
        _decision_intent_material(
            approval_request_id=model.approval_request_id,
            decision=model.decision,
            reason_hash=cast(str, model.reason_hash),
            gate_input_evidence_hash=cast(str, model.gate_input_evidence_hash),
            evidence_package_hash=model.evidence_package_hash,
            challenge_hash=cast(str, model.challenge_hash),
            risk_acknowledgement_hash=cast(str, model.risk_acknowledgement_hash),
        )
    )


def _decision_intent_material(
    *,
    approval_request_id: str,
    decision: str,
    reason_hash: str,
    gate_input_evidence_hash: str,
    evidence_package_hash: str,
    challenge_hash: str,
    risk_acknowledgement_hash: str,
) -> dict[str, str]:
    return {
        "schema_version": "ai-research-human-decision-intent/v1",
        "approval_request_id": approval_request_id,
        "decision": decision,
        "reason_hash": reason_hash,
        "gate_input_evidence_hash": gate_input_evidence_hash,
        "evidence_package_hash": evidence_package_hash,
        "challenge_hash": challenge_hash,
        "risk_acknowledgement_hash": risk_acknowledgement_hash,
    }


def _request_material(
    authority: ApprovalAuthority,
    *,
    package: ResearchEvidencePackage,
    gate_input_evidence_hash: str,
    evidence_package_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": "ai-research-approval-request/v2",
        "run_id": authority.run.id,
        "workspace_id": authority.run.workspace_id,
        "candidate_id": authority.candidate.id,
        "requested_by": authority.actor.id,
        "evidence_package_id": package.id,
        "evidence_package_hash": evidence_package_hash,
        "gate_input_evidence_hash": gate_input_evidence_hash,
        "promotion_policy_version": authority.run.promotion_policy_version,
        "approval_policy_version": authority.policy.version,
        "approval_policy_material_hash": authority.policy.material_hash,
        "approval_mode": authority.policy.mode,
        "capability_profile_id": authority.profile.profile_id,
        "capability_profile_version": authority.profile.version,
        "capability_evidence_hash": approval_capability_profile_material_hash(authority.profile),
    }


def _request_matches(model: ResearchApprovalRequest, material: Mapping[str, Any]) -> bool:
    return (
        model.run_id == material["run_id"]
        and model.workspace_id == material["workspace_id"]
        and model.candidate_id == material["candidate_id"]
        and model.requested_by == material["requested_by"]
        and model.evidence_package_id == material["evidence_package_id"]
        and model.evidence_package_hash == material["evidence_package_hash"]
        and model.gate_input_evidence_hash == material["gate_input_evidence_hash"]
        and model.policy_version == material["approval_policy_version"]
        and model.policy_material_hash == material["approval_policy_material_hash"]
        and model.approval_mode == material["approval_mode"]
        and model.capability_profile_id == material["capability_profile_id"]
        and model.capability_profile_version == material["capability_profile_version"]
        and model.capability_evidence_hash == material["capability_evidence_hash"]
        and model.request_material_hash == content_hash(dict(material))
    )


def _stored_request_material(
    model: ResearchApprovalRequest,
    *,
    package: ResearchEvidencePackage | None,
) -> dict[str, Any] | None:
    """Reconstruct immutable request material without consulting live authority."""

    required_strings = (
        model.run_id,
        model.evidence_package_id,
        model.policy_material_hash,
        model.approval_mode,
        model.capability_profile_id,
        model.capability_profile_version,
        model.capability_evidence_hash,
        model.request_material_hash,
    )
    if any(not isinstance(item, str) or not item for item in required_strings):
        return None
    if (
        package is None
        or package.id != model.evidence_package_id
        or package.run_id != model.run_id
        or package.candidate_id != model.candidate_id
        or package.manifest_hash != model.evidence_package_hash
        or package.gate_input_evidence_hash != model.gate_input_evidence_hash
    ):
        return None
    hashes = (
        model.evidence_package_hash,
        model.gate_input_evidence_hash,
        model.policy_material_hash,
        model.capability_evidence_hash,
        model.request_material_hash,
    )
    if any(not isinstance(item, str) or _SHA256_HEX.fullmatch(item) is None for item in hashes):
        return None
    return {
        "schema_version": "ai-research-approval-request/v2",
        "run_id": model.run_id,
        "workspace_id": model.workspace_id,
        "candidate_id": model.candidate_id,
        "requested_by": model.requested_by,
        "evidence_package_id": model.evidence_package_id,
        "evidence_package_hash": model.evidence_package_hash,
        "gate_input_evidence_hash": model.gate_input_evidence_hash,
        "promotion_policy_version": package.promotion_policy_version,
        "approval_policy_version": model.policy_version,
        "approval_policy_material_hash": model.policy_material_hash,
        "approval_mode": model.approval_mode,
        "capability_profile_id": model.capability_profile_id,
        "capability_profile_version": model.capability_profile_version,
        "capability_evidence_hash": model.capability_evidence_hash,
    }


def _require_request_binding(
    request: ResearchApprovalRequest | None,
    *,
    authority: ApprovalAuthority,
    package: ResearchEvidencePackage,
    gate_input_evidence_hash: str,
    evidence_package_hash: str,
) -> None:
    if request is None:
        raise ValueError("APPROVAL_REQUEST_NOT_FOUND")
    material = _request_material(
        authority,
        package=package,
        gate_input_evidence_hash=gate_input_evidence_hash,
        evidence_package_hash=evidence_package_hash,
    )
    material["requested_by"] = authority.owner_id
    if not _request_matches(request, material):
        raise ValueError("APPROVAL_REQUEST_EVIDENCE_MISMATCH")


def _challenge_records(
    policy: ApprovalPolicy,
    challenge_responses: Mapping[str, str] | None,
    *,
    require_complete: bool,
) -> list[dict[str, str]]:
    responses = dict(challenge_responses or {})
    if set(responses) - set(policy.required_challenge_keys):
        raise ValueError("APPROVAL_CHALLENGE_INVALID")
    if require_complete:
        missing = [
            key
            for key in policy.required_challenge_keys
            if not isinstance(responses.get(key), str) or not responses[key].strip()
        ]
        if missing:
            raise ValueError(f"APPROVAL_CHALLENGE_INCOMPLETE:{','.join(missing)}")
    return [
        {"key": key, "answer_hash": content_hash(responses[key].strip())}
        for key in policy.required_challenge_keys
        if isinstance(responses.get(key), str) and responses[key].strip()
    ]


def _replay_challenge_records(
    challenge_responses: Mapping[str, str] | None,
    *,
    stored_order: tuple[str, ...],
) -> list[dict[str, str]]:
    """Hash caller challenge semantics without needing today's policy catalog."""

    responses = dict(challenge_responses or {})
    invalid = [
        key
        for key, value in responses.items()
        if not isinstance(key, str) or not key.strip() or not isinstance(value, str)
    ]
    if invalid:
        raise ValueError("APPROVAL_IDEMPOTENCY_CONFLICT")
    nonempty = {key: value.strip() for key, value in responses.items() if value.strip()}
    ordered_keys = (*stored_order, *sorted(set(nonempty) - set(stored_order)))
    return [
        {"key": key, "answer_hash": content_hash(nonempty[key])}
        for key in ordered_keys
        if key in nonempty
    ]


def _decision_material(
    authority: ApprovalAuthority,
    *,
    package: ResearchEvidencePackage,
    request_id: str,
    decision: str,
    reason: str,
    gate_input_evidence_hash: str,
    evidence_package_hash: str,
    challenge_records: list[dict[str, str]],
    residual_risk_acknowledgement: str,
) -> dict[str, Any]:
    if authority.grant is None:
        raise ValueError("APPROVAL_GRANT_REQUIRED")
    return {
        "schema_version": "ai-research-human-decision/v2",
        "run_id": authority.run.id,
        "workspace_id": authority.run.workspace_id,
        "candidate_id": authority.candidate.id,
        "approval_request_id": request_id,
        "decision": decision,
        "actor_id": authority.actor.id,
        "grant_id": authority.grant.id,
        "grant_hash": authority.grant.grant_hash,
        "permission": authority.policy.required_permission,
        "approval_policy_version": authority.policy.version,
        "approval_policy_material_hash": authority.policy.material_hash,
        "approval_mode": authority.policy.mode,
        "capability_profile_id": authority.profile.profile_id,
        "capability_profile_version": authority.profile.version,
        "capability_evidence_hash": approval_capability_profile_material_hash(authority.profile),
        "evidence_package_id": package.id,
        "evidence_package_hash": evidence_package_hash,
        "gate_input_evidence_hash": gate_input_evidence_hash,
        "challenge_hash": content_hash(challenge_records),
        "risk_acknowledgement_hash": content_hash(residual_risk_acknowledgement),
        "reason_hash": content_hash(reason),
    }


def _decision_matches(model: ResearchHumanDecision, material: Mapping[str, Any]) -> bool:
    return (
        model.run_id == material["run_id"]
        and model.workspace_id == material["workspace_id"]
        and model.candidate_id == material["candidate_id"]
        and model.approval_request_id == material["approval_request_id"]
        and model.decision == material["decision"]
        and model.actor_id == material["actor_id"]
        and model.grant_id == material["grant_id"]
        and model.grant_hash == material["grant_hash"]
        and model.domain_permissions == [material["permission"]]
        and model.policy_version == material["approval_policy_version"]
        and model.policy_material_hash == material["approval_policy_material_hash"]
        and model.approval_mode == material["approval_mode"]
        and model.capability_profile_id == material["capability_profile_id"]
        and model.capability_profile_version == material["capability_profile_version"]
        and model.capability_evidence_hash == material["capability_evidence_hash"]
        and model.evidence_package_id == material["evidence_package_id"]
        and model.evidence_package_hash == material["evidence_package_hash"]
        and model.gate_input_evidence_hash == material["gate_input_evidence_hash"]
        and model.challenge_hash == material["challenge_hash"]
        and model.risk_acknowledgement_hash == material["risk_acknowledgement_hash"]
        and model.reason_hash == material["reason_hash"]
        and model.decision_material_hash == content_hash(dict(material))
    )


def _stored_decision_material(model: ResearchHumanDecision) -> dict[str, Any] | None:
    """Reconstruct the immutable decision envelope from the committed record."""

    required_strings = (
        model.run_id,
        model.approval_request_id,
        model.evidence_package_id,
        model.policy_material_hash,
        model.capability_profile_id,
        model.capability_profile_version,
        model.capability_evidence_hash,
        model.grant_id,
        model.grant_hash,
        model.challenge_hash,
        model.risk_acknowledgement_hash,
        model.reason_hash,
        model.gate_input_evidence_hash,
        model.decision_material_hash,
    )
    if any(not isinstance(item, str) or not item for item in required_strings):
        return None
    hashes = (
        model.policy_material_hash,
        model.capability_evidence_hash,
        model.grant_hash,
        model.challenge_hash,
        model.risk_acknowledgement_hash,
        model.reason_hash,
        model.gate_input_evidence_hash,
        model.evidence_package_hash,
        model.decision_material_hash,
    )
    challenge_records = list(model.challenge_records or [])
    if (
        any(not isinstance(item, str) or _SHA256_HEX.fullmatch(item) is None for item in hashes)
        or model.challenge_hash != content_hash(challenge_records)
        or model.reason_hash != content_hash(model.comment or "")
        or (not model.risk_acknowledgement and model.risk_acknowledgement_hash != content_hash(""))
        or not isinstance(model.domain_permissions, list)
        or len(model.domain_permissions) != 1
        or not isinstance(model.domain_permissions[0], str)
    ):
        return None
    return {
        "schema_version": "ai-research-human-decision/v2",
        "run_id": model.run_id,
        "workspace_id": model.workspace_id,
        "candidate_id": model.candidate_id,
        "approval_request_id": model.approval_request_id,
        "decision": model.decision,
        "actor_id": model.actor_id,
        "grant_id": model.grant_id,
        "grant_hash": model.grant_hash,
        "permission": model.domain_permissions[0],
        "approval_policy_version": model.policy_version,
        "approval_policy_material_hash": model.policy_material_hash,
        "approval_mode": model.approval_mode,
        "capability_profile_id": model.capability_profile_id,
        "capability_profile_version": model.capability_profile_version,
        "capability_evidence_hash": model.capability_evidence_hash,
        "evidence_package_id": model.evidence_package_id,
        "evidence_package_hash": model.evidence_package_hash,
        "gate_input_evidence_hash": model.gate_input_evidence_hash,
        "challenge_hash": model.challenge_hash,
        "risk_acknowledgement_hash": model.risk_acknowledgement_hash,
        "reason_hash": model.reason_hash,
    }


def _decision_is_current(
    model: ResearchHumanDecision,
    *,
    authority: ApprovalAuthority,
    package: ResearchEvidencePackage,
    gate_input_evidence_hash: str,
) -> bool:
    grant = authority.grant
    if model.decision != "APPROVED" or grant is None or model.expires_at is None:
        return False
    if _as_utc(model.expires_at) <= authority.database_now:
        return False
    material = _decision_material(
        authority,
        package=package,
        request_id=model.approval_request_id or "",
        decision=model.decision,
        reason=model.comment or "",
        gate_input_evidence_hash=gate_input_evidence_hash,
        evidence_package_hash=package.manifest_hash,
        challenge_records=list(model.challenge_records or []),
        residual_risk_acknowledgement="",
    )
    # The acknowledgement plaintext is deliberately not retained.  Replace its
    # derived field with the persisted hash before checking the canonical record.
    material["risk_acknowledgement_hash"] = model.risk_acknowledgement_hash
    return model.grant_hash == approval_grant_hash(grant) and _decision_matches(model, material)


async def _load_denial_fence(
    session: Any,
    material: Mapping[str, Any],
) -> ResearchApprovalDenialFence | None:
    """Lock and validate one exact immutable denial fence."""

    scope_hash = content_hash(dict(material))
    model = await session.scalar(
        select(ResearchApprovalDenialFence)
        .where(ResearchApprovalDenialFence.fence_scope_hash == scope_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if model is None:
        return None
    if not _denial_fence_matches(model, material):
        raise ValueError("APPROVAL_DENIAL_FENCE_CONFLICT")
    return model


async def _load_denial_decision(
    session: Any,
    *,
    fence: ResearchApprovalDenialFence,
) -> ResearchHumanDecision:
    """Require the fence's immutable negative decision instead of timestamp ordering."""

    decision = await session.scalar(
        select(ResearchHumanDecision)
        .where(ResearchHumanDecision.id == fence.decision_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    material = _stored_decision_material(decision) if decision is not None else None
    if (
        decision is None
        or material is None
        or not _decision_matches(decision, material)
        or decision.run_id != fence.run_id
        or decision.candidate_id != fence.candidate_id
        or decision.evidence_package_id != fence.evidence_package_id
        or decision.evidence_package_hash != fence.evidence_package_hash
        or decision.gate_input_evidence_hash != fence.gate_input_evidence_hash
        or decision.policy_version != fence.approval_policy_version
        or decision.policy_material_hash != fence.approval_policy_material_hash
        or decision.decision != fence.decision
        or decision.decision not in {"REJECTED", "REQUESTED_CHANGES"}
    ):
        raise ValueError("APPROVAL_DENIAL_FENCE_CONFLICT")
    return decision


async def _require_no_denial_fence(
    session: Any,
    *,
    authority: ApprovalAuthority,
    package: ResearchEvidencePackage,
    gate_input_evidence_hash: str,
    evidence_package_hash: str,
) -> None:
    material = _denial_scope_material(
        authority,
        package=package,
        gate_input_evidence_hash=gate_input_evidence_hash,
        evidence_package_hash=evidence_package_hash,
    )
    if await _load_denial_fence(session, material) is not None:
        raise ValueError("APPROVAL_EVIDENCE_DENIED")


def _denial_scope_material(
    authority: ApprovalAuthority,
    *,
    package: ResearchEvidencePackage,
    gate_input_evidence_hash: str,
    evidence_package_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": "ai-research-approval-denial-fence/v1",
        "run_id": authority.run.id,
        "candidate_id": authority.candidate.id,
        "evidence_package_id": package.id,
        "evidence_package_hash": evidence_package_hash,
        "gate_input_evidence_hash": gate_input_evidence_hash,
        "approval_binding_hash": package.approval_binding_hash,
        "promotion_policy_version": authority.run.promotion_policy_version,
        "approval_policy_version": authority.policy.version,
        "approval_policy_material_hash": authority.policy.material_hash,
    }


def _denial_fence_matches(
    model: ResearchApprovalDenialFence,
    material: Mapping[str, Any],
) -> bool:
    return (
        model.run_id == material["run_id"]
        and model.candidate_id == material["candidate_id"]
        and model.evidence_package_id == material["evidence_package_id"]
        and model.evidence_package_hash == material["evidence_package_hash"]
        and model.gate_input_evidence_hash == material["gate_input_evidence_hash"]
        and model.approval_binding_hash == material["approval_binding_hash"]
        and model.promotion_policy_version == material["promotion_policy_version"]
        and model.approval_policy_version == material["approval_policy_version"]
        and model.approval_policy_material_hash == material["approval_policy_material_hash"]
        and model.decision in {"REJECTED", "REQUESTED_CHANGES"}
        and model.fence_scope_hash == content_hash(dict(material))
    )


def _operation_lock(candidate_id: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    shards = _LOCKS_BY_LOOP.get(loop)
    if shards is None:
        shards = tuple(asyncio.Lock() for _ in range(_LOCK_SHARD_COUNT))
        _LOCKS_BY_LOOP[loop] = shards
    digest = hashlib.sha256(candidate_id.encode()).digest()
    return shards[int.from_bytes(digest[:8], "big") % _LOCK_SHARD_COUNT]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
