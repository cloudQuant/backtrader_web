"""Server-owned human authority and policy resolution for research approval."""

from __future__ import annotations

import asyncio
import hashlib
import re
import weakref
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_research_v2 import (
    ResearchApprovalGrant,
    ResearchApprovalGrantAudit,
    ResearchCandidate,
    ResearchCapabilityProfile,
    ResearchExperimentEpoch,
    ResearchRun,
)
from app.models.permission import Role, user_roles
from app.models.user import User
from app.services.research.canonical import content_hash
from app.services.research.database_clock import database_utc_now

_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
_APPROVAL_PERMISSION = "research:approve"
_MANAGE_GRANTS_PERMISSION = "research:manage-approval-grants"
_GRANT_AUTHORITY_POLICY_VERSION = "approval-grant-authority-v1"
_MAX_GRANT_TTL_SECONDS = 86_400
_LOCK_SHARD_COUNT = 64
_LOCKS_BY_LOOP: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, tuple[asyncio.Lock, ...]] = (
    weakref.WeakKeyDictionary()
)

DatabaseClock = Callable[[AsyncSession], Awaitable[datetime]]


@dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    """One immutable entry in the server approval policy catalog."""

    version: str
    promotion_policy_versions: tuple[str, ...]
    mode: str
    required_permission: str
    ttl_seconds: int
    cooldown_seconds: int
    required_challenge_keys: tuple[str, ...]
    risk_acknowledgement_required: bool

    @property
    def material(self) -> dict[str, Any]:
        """Return every policy field that can affect an approval outcome."""

        return {
            "schema_version": "ai-research-approval-policy/v2",
            "version": self.version,
            "promotion_policy_versions": list(self.promotion_policy_versions),
            "mode": self.mode,
            "required_permission": self.required_permission,
            "ttl_seconds": self.ttl_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "required_challenge_keys": list(self.required_challenge_keys),
            "risk_acknowledgement_required": self.risk_acknowledgement_required,
        }

    @property
    def material_hash(self) -> str:
        """Hash the complete catalog entry, not merely its version label."""

        return content_hash(self.material)


_SERVER_APPROVAL_POLICIES = (
    ApprovalPolicy(
        version="approval-single-v2",
        promotion_policy_versions=("promotion-v1",),
        mode="single_actor",
        required_permission=_APPROVAL_PERMISSION,
        ttl_seconds=3_600,
        cooldown_seconds=60,
        required_challenge_keys=("execution_risk", "model_risk"),
        risk_acknowledgement_required=True,
    ),
    ApprovalPolicy(
        version="approval-multi-v2",
        promotion_policy_versions=("promotion-v1",),
        mode="multi_actor",
        required_permission=_APPROVAL_PERMISSION,
        ttl_seconds=86_400,
        cooldown_seconds=0,
        required_challenge_keys=(),
        risk_acknowledgement_required=False,
    ),
)


class ApprovalPolicyCatalog:
    """Resolve only exact, fully materialized server approval policies."""

    def __init__(self, policies: tuple[ApprovalPolicy, ...] = _SERVER_APPROVAL_POLICIES) -> None:
        by_version = {policy.version: policy for policy in policies}
        if len(by_version) != len(policies):
            raise ValueError("APPROVAL_POLICY_CATALOG_INVALID")
        for policy in policies:
            _validate_policy(policy)
        self._policies = by_version

    def resolve(
        self,
        policy_version: str,
        approval_capabilities: Mapping[str, Any],
    ) -> ApprovalPolicy:
        """Bind a deployment profile to one exact catalog material hash."""

        policy = self._policies.get(policy_version)
        if policy is None:
            raise ValueError("APPROVAL_POLICY_UNSUPPORTED")
        expected = server_approval_capabilities(policy.mode, catalog=self)
        if not isinstance(approval_capabilities, Mapping):
            raise ValueError("APPROVAL_CAPABILITY_PROFILE_INVALID")
        supplied = dict(approval_capabilities)
        if set(supplied) != set(expected):
            raise ValueError("APPROVAL_CAPABILITY_PROFILE_INVALID")
        permissions = supplied.get("permissions")
        if permissions != [_APPROVAL_PERMISSION]:
            raise ValueError("APPROVAL_CAPABILITY_PROFILE_INVALID")
        if supplied.get("policy_material_hash") != policy.material_hash:
            raise ValueError("APPROVAL_POLICY_MATERIAL_MISMATCH")
        if supplied != expected:
            raise ValueError("APPROVAL_CAPABILITY_PROFILE_INVALID")
        return policy

    def by_mode(self, mode: str) -> ApprovalPolicy:
        """Return the only policy for a supported deployment actor mode."""

        matches = [policy for policy in self._policies.values() if policy.mode == mode]
        if len(matches) != 1:
            raise ValueError("APPROVAL_POLICY_UNSUPPORTED")
        return matches[0]


def resolve_server_approval_policy(policy_version: str) -> ApprovalPolicy:
    """Resolve a policy version from the immutable default catalog."""

    catalog = ApprovalPolicyCatalog()
    policy = catalog._policies.get(policy_version)
    if policy is None:
        raise ValueError("APPROVAL_POLICY_UNSUPPORTED")
    return policy


def server_approval_capabilities(
    mode: str,
    *,
    catalog: ApprovalPolicyCatalog | None = None,
) -> dict[str, Any]:
    """Return the complete server-owned approval capability declaration."""

    resolved_catalog = catalog or ApprovalPolicyCatalog()
    policy = resolved_catalog.by_mode(mode)
    return {
        "mode": policy.mode,
        "policy_version": policy.version,
        "policy_material_hash": policy.material_hash,
        "permissions": [policy.required_permission],
    }


def approval_capability_profile_material_hash(profile: ResearchCapabilityProfile) -> str:
    """Hash every persisted profile field that can alter approval authority."""

    return content_hash(
        {
            "schema_version": "ai-research-approval-capability-profile/v1",
            "id": profile.id,
            "profile_id": profile.profile_id,
            "version": profile.version,
            "topology": profile.topology,
            "actor_mode": profile.actor_mode,
            "db_engine": profile.db_engine,
            "service_identities": dict(profile.service_identities or {}),
            "queue_capabilities": dict(profile.queue_capabilities or {}),
            "storage_boundaries": dict(profile.storage_boundaries or {}),
            "network_capabilities": dict(profile.network_capabilities or {}),
            "sandbox_capabilities": dict(profile.sandbox_capabilities or {}),
            "approval_capabilities": dict(profile.approval_capabilities or {}),
            "attestation_evidence_hash": profile.evidence_hash,
            "verified_at": _as_utc(profile.verified_at),
            "expires_at": _as_utc(profile.expires_at),
            "created_at": _as_utc(profile.created_at),
        }
    )


@dataclass(frozen=True, slots=True)
class ApprovalAuthority:
    """Resolved transaction-local human, scope, policy, profile, and grant."""

    actor: User
    owner_id: str
    run: ResearchRun
    candidate: ResearchCandidate
    epoch: ResearchExperimentEpoch
    profile: ResearchCapabilityProfile
    policy: ApprovalPolicy
    database_now: datetime
    grant: ResearchApprovalGrant | None = None


class ApprovalAuthorityResolver:
    """Resolve approval authority from database state, never request assertions."""

    def __init__(
        self,
        *,
        catalog: ApprovalPolicyCatalog | None = None,
        clock: DatabaseClock = database_utc_now,
    ) -> None:
        self._catalog = catalog or ApprovalPolicyCatalog()
        self._clock = clock

    async def resolve_request_in_session(
        self,
        session: AsyncSession,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
    ) -> ApprovalAuthority:
        """Require an active owner and a current server approval profile."""

        authority = await self._resolve_base_in_session(
            session,
            authenticated_actor_id=authenticated_actor_id,
            run_id=run_id,
            candidate_id=candidate_id,
        )
        if authority.actor.id != authority.owner_id:
            raise ValueError("APPROVAL_SCOPE_NOT_FOUND")
        return authority

    async def resolve_decision_in_session(
        self,
        session: AsyncSession,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
    ) -> ApprovalAuthority:
        """Resolve one active, exact, human approval grant for the decision actor."""

        authority = await self._resolve_base_in_session(
            session,
            authenticated_actor_id=authenticated_actor_id,
            run_id=run_id,
            candidate_id=candidate_id,
            include_grant_issuers=True,
        )
        if authority.policy.mode == "single_actor":
            if authority.actor.id != authority.owner_id:
                raise ValueError("APPROVAL_SCOPE_NOT_FOUND")
        elif authority.actor.id == authority.owner_id:
            raise ValueError("APPROVAL_SEPARATION_REQUIRED")

        grants = list(
            (
                await session.scalars(
                    select(ResearchApprovalGrant)
                    .where(
                        ResearchApprovalGrant.actor_id == authority.actor.id,
                        ResearchApprovalGrant.run_id == authority.run.id,
                        ResearchApprovalGrant.permission == authority.policy.required_permission,
                    )
                    .with_for_update()
                )
            ).all()
        )
        issuer_ids = {grant.issuer_id for grant in grants}
        issuers = list(
            (
                await session.scalars(
                    select(User)
                    .where(User.id.in_(sorted(issuer_ids)))
                    .order_by(User.id)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        if {issuer.id for issuer in issuers} != issuer_ids:
            raise ValueError("APPROVAL_GRANT_AUDIT_INVALID")
        active_human_issuer_ids = {
            user.id for user in issuers if user.is_active is True and user.principal_kind == "HUMAN"
        }
        authorized_issuer_ids = set(
            (
                await session.scalars(
                    select(user_roles.c.user_id).where(
                        user_roles.c.user_id.in_(sorted(issuer_ids)),
                        user_roles.c.role == Role.RESEARCH_APPROVAL_ADMIN.value,
                    )
                )
            ).all()
        )
        current_candidates = [
            grant
            for grant in grants
            if grant.issuer_id in active_human_issuer_ids
            and grant.issuer_id in authorized_issuer_ids
            and _grant_is_current(grant, authority)
        ]
        issuing_audits = await _load_locked_issued_grant_audits(
            session,
            {grant.id for grant in current_candidates},
        )
        audits_by_grant: dict[str, list[ResearchApprovalGrantAudit]] = {}
        for audit in issuing_audits:
            audits_by_grant.setdefault(audit.grant_id, []).append(audit)
        current: list[ResearchApprovalGrant] = []
        for grant in current_candidates:
            exact_audits = audits_by_grant.get(grant.id, [])
            if len(exact_audits) != 1 or not _grant_audit_matches(exact_audits[0], grant):
                raise ValueError("APPROVAL_GRANT_AUDIT_INVALID")
            current.append(grant)
        if not current:
            raise ValueError("APPROVAL_GRANT_REQUIRED")
        if len(current) != 1:
            raise ValueError("APPROVAL_GRANT_AMBIGUOUS")
        return ApprovalAuthority(
            actor=authority.actor,
            owner_id=authority.owner_id,
            run=authority.run,
            candidate=authority.candidate,
            epoch=authority.epoch,
            profile=authority.profile,
            policy=authority.policy,
            database_now=authority.database_now,
            grant=current[0],
        )

    async def revalidate_grant_in_session(
        self,
        session: AsyncSession,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
        grant_id: str,
    ) -> ApprovalAuthority:
        """Re-resolve current authority and require the recorded exact grant."""

        authority = await self.resolve_decision_in_session(
            session,
            authenticated_actor_id=authenticated_actor_id,
            run_id=run_id,
            candidate_id=candidate_id,
        )
        if authority.grant is None or authority.grant.id != grant_id:
            raise ValueError("APPROVAL_GRANT_STALE")
        return authority

    async def replay_grant_is_historically_exact_in_session(
        self,
        session: AsyncSession,
        *,
        actor_id: str,
        run_id: str,
        workspace_id: str | None,
        grant_id: str,
        grant_hash: str,
        permission: str,
        decided_at: datetime,
    ) -> bool:
        """Verify the exact grant authority that existed when a decision was recorded."""

        run = await session.scalar(
            select(ResearchRun)
            .where(ResearchRun.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        discovered_grant = await session.scalar(
            select(ResearchApprovalGrant).where(ResearchApprovalGrant.id == grant_id)
        )
        if run is None or discovered_grant is None:
            return False
        identity_ids = {actor_id, discovered_grant.issuer_id}
        if discovered_grant.revoked_by is not None:
            identity_ids.add(discovered_grant.revoked_by)
        identities = list(
            (
                await session.scalars(
                    select(User)
                    .where(User.id.in_(sorted(identity_ids)))
                    .order_by(User.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        grant = await session.scalar(
            select(ResearchApprovalGrant)
            .where(ResearchApprovalGrant.id == grant_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if grant is None:
            return False
        human_identity_ids = {
            identity.id for identity in identities if identity.principal_kind == "HUMAN"
        }
        audits = await _load_locked_grant_audits(session, {grant.id})
        issuing_audits = [audit for audit in audits if audit.event_type == "ISSUED"]
        revoking_audits = [audit for audit in audits if audit.event_type == "REVOKED"]
        if not isinstance(decided_at, datetime):
            return False
        decision_time = _as_utc(decided_at)
        issued_at = _as_utc(grant.issued_at)
        expires_at = _as_utc(grant.expires_at)
        if grant.revoked_at is None:
            revocation_is_exact = (
                grant.revoked_by is None
                and grant.revocation_reason is None
                and not revoking_audits
                and len(audits) == len(issuing_audits)
            )
        else:
            revoked_at = _as_utc(grant.revoked_at)
            revocation_is_exact = (
                decision_time < revoked_at
                and grant.revoked_by is not None
                and grant.revoked_by in human_identity_ids
                and isinstance(grant.revocation_reason, str)
                and bool(grant.revocation_reason.strip())
                and len(revoking_audits) == 1
                and _grant_audit_matches(revoking_audits[0], grant)
                and len(audits) == len(issuing_audits) + len(revoking_audits)
            )
        return (
            grant.actor_id == actor_id
            and grant.run_id == run_id
            and grant.workspace_id == workspace_id
            and grant.permission == permission
            and grant.subject_kind == "HUMAN"
            and grant.issuer_kind == "HUMAN"
            and grant.grant_hash == grant_hash
            and actor_id in human_identity_ids
            and grant.issuer_id in human_identity_ids
            and identity_ids == human_identity_ids
            and issued_at <= decision_time < expires_at
            and revocation_is_exact
            and len(issuing_audits) == 1
            and _grant_audit_matches(issuing_audits[0], grant)
            and _SHA256_HEX.fullmatch(grant.grant_hash) is not None
            and approval_grant_hash(grant) == grant.grant_hash
        )

    async def _resolve_base_in_session(
        self,
        session: AsyncSession,
        *,
        authenticated_actor_id: str,
        run_id: str,
        candidate_id: str,
        include_grant_issuers: bool = False,
    ) -> ApprovalAuthority:
        epoch_id = await session.scalar(
            select(ResearchCandidate.experiment_epoch_id).where(
                ResearchCandidate.id == candidate_id
            )
        )
        if epoch_id is None:
            raise ValueError("APPROVAL_SCOPE_NOT_FOUND")
        epoch = await session.scalar(
            select(ResearchExperimentEpoch)
            .where(ResearchExperimentEpoch.id == epoch_id)
            .with_for_update()
        )
        candidate = await session.scalar(
            select(ResearchCandidate)
            .where(ResearchCandidate.id == candidate_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        run = await session.scalar(
            select(ResearchRun)
            .where(ResearchRun.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        identity_ids = {authenticated_actor_id}
        if run is not None:
            identity_ids.add(run.user_id)
            if include_grant_issuers:
                identity_ids.update(
                    (
                        await session.scalars(
                            select(ResearchApprovalGrant.issuer_id).where(
                                ResearchApprovalGrant.actor_id == authenticated_actor_id,
                                ResearchApprovalGrant.run_id == run.id,
                                ResearchApprovalGrant.permission == _APPROVAL_PERMISSION,
                            )
                        )
                    ).all()
                )
        identities = list(
            (
                await session.scalars(
                    select(User)
                    .where(User.id.in_(sorted(identity_ids)))
                    .order_by(User.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        by_id: dict[str, User] = {cast(str, identity.id): identity for identity in identities}
        actor = by_id.get(authenticated_actor_id)
        owner = by_id.get(run.user_id) if run is not None else None
        if (
            epoch is None
            or candidate is None
            or run is None
            or actor is None
            or owner is None
            or actor.is_active is not True
            or owner.is_active is not True
            or actor.principal_kind != "HUMAN"
            or owner.principal_kind != "HUMAN"
            or candidate.experiment_epoch_id != epoch.id
            or candidate.run_id != run.id
            or run.experiment_epoch_id != epoch.id
            or candidate.user_id != run.user_id
        ):
            raise ValueError("APPROVAL_SCOPE_NOT_FOUND")

        now = _as_utc(await self._clock(session))
        profile = await session.scalar(
            select(ResearchCapabilityProfile)
            .where(
                ResearchCapabilityProfile.profile_id == run.capability_profile_id,
                ResearchCapabilityProfile.version == run.capability_profile_version,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            profile is None
            or profile.evidence_hash != run.capability_evidence_hash
            or _SHA256_HEX.fullmatch(profile.evidence_hash) is None
            or _as_utc(profile.verified_at) > now
            or _as_utc(profile.expires_at) <= now
        ):
            raise ValueError("APPROVAL_CAPABILITY_PROFILE_INVALID")
        capabilities = profile.approval_capabilities
        if not isinstance(capabilities, Mapping):
            raise ValueError("APPROVAL_CAPABILITY_PROFILE_INVALID")
        policy_version = capabilities.get("policy_version")
        if not isinstance(policy_version, str):
            raise ValueError("APPROVAL_CAPABILITY_PROFILE_INVALID")
        policy = self._catalog.resolve(policy_version, capabilities)
        if (
            profile.actor_mode != policy.mode
            or capabilities.get("mode") != profile.actor_mode
            or run.promotion_policy_version not in policy.promotion_policy_versions
        ):
            raise ValueError("APPROVAL_POLICY_SCOPE_MISMATCH")
        return ApprovalAuthority(
            actor=actor,
            owner_id=run.user_id,
            run=run,
            candidate=candidate,
            epoch=epoch,
            profile=profile,
            policy=policy,
            database_now=now,
        )


@dataclass(frozen=True, slots=True)
class _GrantCommitProbe:
    actor_id: str
    idempotency_key: str
    event_type: str
    command_material: dict[str, Any]


class _GrantCommitOutcomeUncertain(RuntimeError):
    def __init__(self, probe: _GrantCommitProbe) -> None:
        super().__init__("APPROVAL_GRANT_COMMIT_OUTCOME_UNKNOWN")
        self.probe = probe


class ApprovalGrantService:
    """Issue and revoke exact run-scoped grants from explicit control-plane authority."""

    def __init__(self, *, clock: DatabaseClock = database_utc_now) -> None:
        self._clock = clock

    async def issue(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        subject_id: str,
        ttl_seconds: int,
        idempotency_key: str,
    ) -> ResearchApprovalGrant:
        """Issue one current human grant using server time and exact database scope."""

        _validate_grant_command_ids(
            authenticated_actor_id=authenticated_actor_id,
            run_id=run_id,
            subject_id=subject_id,
            idempotency_key=idempotency_key,
        )
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not 1 <= ttl_seconds <= _MAX_GRANT_TTL_SECONDS
        ):
            raise ValueError("APPROVAL_GRANT_TTL_INVALID")
        material = _grant_issue_command_material(
            run_id=run_id,
            subject_id=subject_id,
            ttl_seconds=ttl_seconds,
        )
        async with _grant_operation_lock(run_id, subject_id):
            replay = await self._read_replay(
                actor_id=authenticated_actor_id,
                idempotency_key=idempotency_key,
                event_type="ISSUED",
                command_material=material,
            )
            if replay is not None:
                return replay
            try:
                return await self._issue_once(
                    authenticated_actor_id=authenticated_actor_id,
                    run_id=run_id,
                    subject_id=subject_id,
                    ttl_seconds=ttl_seconds,
                    idempotency_key=idempotency_key,
                    command_material=material,
                )
            except _GrantCommitOutcomeUncertain as exc:
                try:
                    committed = await self._read_probe(exc.probe)
                except Exception:
                    raise ValueError("APPROVAL_GRANT_COMMIT_OUTCOME_UNKNOWN") from None
                if isinstance(committed, ResearchApprovalGrant):
                    return committed
                raise ValueError("APPROVAL_GRANT_COMMIT_OUTCOME_UNKNOWN") from None

    async def revoke(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        grant_id: str,
        reason: str,
        idempotency_key: str,
    ) -> ResearchApprovalGrant:
        """Perform the grant's only permitted state transition with exact replay."""

        _validate_grant_command_ids(
            authenticated_actor_id=authenticated_actor_id,
            run_id=run_id,
            subject_id=grant_id,
            idempotency_key=idempotency_key,
        )
        if not isinstance(reason, str):
            raise ValueError("APPROVAL_GRANT_REVOCATION_REASON_REQUIRED")
        reason = reason.strip()
        if not reason or len(reason) > 10_000:
            raise ValueError("APPROVAL_GRANT_REVOCATION_REASON_REQUIRED")
        material = _grant_revoke_command_material(
            run_id=run_id,
            grant_id=grant_id,
            reason=reason,
        )
        async with _grant_operation_lock(run_id, grant_id):
            replay = await self._read_replay(
                actor_id=authenticated_actor_id,
                idempotency_key=idempotency_key,
                event_type="REVOKED",
                command_material=material,
            )
            if replay is not None:
                return replay
            try:
                return await self._revoke_once(
                    authenticated_actor_id=authenticated_actor_id,
                    run_id=run_id,
                    grant_id=grant_id,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    command_material=material,
                )
            except _GrantCommitOutcomeUncertain as exc:
                try:
                    committed = await self._read_probe(exc.probe)
                except Exception:
                    raise ValueError("APPROVAL_GRANT_COMMIT_OUTCOME_UNKNOWN") from None
                if isinstance(committed, ResearchApprovalGrant):
                    return committed
                raise ValueError("APPROVAL_GRANT_COMMIT_OUTCOME_UNKNOWN") from None

    async def response_status(self, grant: ResearchApprovalGrant) -> str:
        """Project ACTIVE/EXPIRED/REVOKED using the database clock, never app time."""

        from app.db import database

        async with database.async_session_maker() as session:
            now = _as_utc(await self._clock(session))
        if grant.revoked_at is not None:
            return "REVOKED"
        if _as_utc(grant.expires_at) <= now:
            return "EXPIRED"
        return "ACTIVE"

    async def _issue_once(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        subject_id: str,
        ttl_seconds: int,
        idempotency_key: str,
        command_material: dict[str, Any],
    ) -> ResearchApprovalGrant:
        from app.db import database

        async with database.async_session_maker() as session:
            run, actor, subject = await self._resolve_manager_scope(
                session,
                authenticated_actor_id=authenticated_actor_id,
                run_id=run_id,
                subject_id=subject_id,
            )
            now = _as_utc(await self._clock(session))
            observed = list(
                (
                    await session.scalars(
                        select(ResearchApprovalGrant)
                        .where(
                            ResearchApprovalGrant.actor_id == subject.id,
                            ResearchApprovalGrant.run_id == run.id,
                            ResearchApprovalGrant.permission == _APPROVAL_PERMISSION,
                        )
                        .with_for_update()
                    )
                ).all()
            )
            if any(
                grant.revoked_at is None
                and _as_utc(grant.issued_at) <= now < _as_utc(grant.expires_at)
                and grant.workspace_id == run.workspace_id
                and grant.subject_kind == "HUMAN"
                and grant.issuer_kind == "HUMAN"
                and approval_grant_hash(grant) == grant.grant_hash
                for grant in observed
            ):
                raise ValueError("APPROVAL_GRANT_ALREADY_ACTIVE")
            grant = ResearchApprovalGrant(
                actor_id=subject.id,
                run_id=run.id,
                workspace_id=run.workspace_id,
                permission=_APPROVAL_PERMISSION,
                subject_kind="HUMAN",
                issuer_id=actor.id,
                issuer_kind="HUMAN",
                grant_hash="0" * 64,
                issued_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
                created_at=now,
            )
            grant.grant_hash = approval_grant_hash(grant)
            probe = _GrantCommitProbe(
                authenticated_actor_id,
                idempotency_key,
                "ISSUED",
                command_material,
            )
            try:
                session.add(grant)
                await session.flush()
                session.add(
                    _grant_audit_model(
                        grant=grant,
                        event_type="ISSUED",
                        actor_id=cast(str, actor.id),
                        idempotency_key=idempotency_key,
                        command_material=command_material,
                        occurred_at=now,
                        reason_hash=None,
                    )
                )
                await session.flush()
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise _GrantCommitOutcomeUncertain(probe) from exc
            except Exception as exc:
                await session.rollback()
                raise _GrantCommitOutcomeUncertain(probe) from exc
            await session.refresh(grant)
            return grant

    async def _revoke_once(
        self,
        *,
        authenticated_actor_id: str,
        run_id: str,
        grant_id: str,
        reason: str,
        idempotency_key: str,
        command_material: dict[str, Any],
    ) -> ResearchApprovalGrant:
        from app.db import database

        async with database.async_session_maker() as session:
            subject_id = await session.scalar(
                select(ResearchApprovalGrant.actor_id).where(
                    ResearchApprovalGrant.id == grant_id,
                    ResearchApprovalGrant.run_id == run_id,
                )
            )
            if subject_id is None:
                raise ValueError("APPROVAL_GRANT_NOT_FOUND")
            run, actor, subject = await self._resolve_manager_scope(
                session,
                authenticated_actor_id=authenticated_actor_id,
                run_id=run_id,
                subject_id=subject_id,
            )
            grant = await session.scalar(
                select(ResearchApprovalGrant)
                .where(ResearchApprovalGrant.id == grant_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                grant is None
                or grant.run_id != run.id
                or grant.workspace_id != run.workspace_id
                or grant.actor_id != subject.id
                or grant.permission != _APPROVAL_PERMISSION
                or grant.subject_kind != "HUMAN"
                or grant.issuer_kind != "HUMAN"
                or approval_grant_hash(grant) != grant.grant_hash
            ):
                raise ValueError("APPROVAL_GRANT_SCOPE_MISMATCH")
            if grant.revoked_at is not None:
                raise ValueError("APPROVAL_GRANT_ALREADY_REVOKED")
            now = _as_utc(await self._clock(session))
            grant.revoked_at = now
            grant.revoked_by = actor.id
            grant.revocation_reason = reason
            probe = _GrantCommitProbe(
                authenticated_actor_id,
                idempotency_key,
                "REVOKED",
                command_material,
            )
            try:
                session.add(
                    _grant_audit_model(
                        grant=grant,
                        event_type="REVOKED",
                        actor_id=cast(str, actor.id),
                        idempotency_key=idempotency_key,
                        command_material=command_material,
                        occurred_at=now,
                        reason_hash=content_hash(reason),
                    )
                )
                await session.flush()
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise _GrantCommitOutcomeUncertain(probe) from exc
            except Exception as exc:
                await session.rollback()
                raise _GrantCommitOutcomeUncertain(probe) from exc
            await session.refresh(grant)
            return grant

    async def _resolve_manager_scope(
        self,
        session: AsyncSession,
        *,
        authenticated_actor_id: str,
        run_id: str,
        subject_id: str,
    ) -> tuple[ResearchRun, User, User]:
        run = await session.scalar(
            select(ResearchRun)
            .where(ResearchRun.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        users = list(
            (
                await session.scalars(
                    select(User)
                    .where(User.id.in_(sorted({authenticated_actor_id, subject_id})))
                    .order_by(User.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        by_id: dict[str, User] = {cast(str, user.id): user for user in users}
        actor = by_id.get(authenticated_actor_id)
        subject = by_id.get(subject_id)
        roles = set(
            (
                await session.scalars(
                    select(user_roles.c.role).where(user_roles.c.user_id == authenticated_actor_id)
                )
            ).all()
        )
        if run is None or actor is None or subject is None:
            raise ValueError("APPROVAL_GRANT_SCOPE_NOT_FOUND")
        if (
            actor.is_active is not True
            or actor.principal_kind != "HUMAN"
            or Role.RESEARCH_APPROVAL_ADMIN.value not in roles
        ):
            raise ValueError("APPROVAL_GRANT_MANAGER_REQUIRED")
        if subject.is_active is not True or subject.principal_kind != "HUMAN":
            raise ValueError("APPROVAL_GRANT_SUBJECT_INVALID")
        return run, actor, subject

    async def _read_replay(
        self,
        *,
        actor_id: str,
        idempotency_key: str,
        event_type: str,
        command_material: dict[str, Any],
    ) -> ResearchApprovalGrant | None:
        from app.db import database

        async with database.async_session_maker() as session:
            discovered_audits = list(
                (
                    await session.scalars(
                        select(ResearchApprovalGrantAudit).where(
                            ResearchApprovalGrantAudit.actor_id == actor_id,
                            ResearchApprovalGrantAudit.idempotency_key == idempotency_key,
                        )
                    )
                ).all()
            )
            if len(discovered_audits) > 1:
                raise ValueError("APPROVAL_GRANT_IDEMPOTENCY_CONFLICT")
            if not discovered_audits:
                return None
            discovered_audit = discovered_audits[0]
            run_id = command_material.get("run_id")
            if not isinstance(run_id, str):
                raise ValueError("APPROVAL_GRANT_IDEMPOTENCY_CONFLICT")
            run = await session.scalar(
                select(ResearchRun)
                .where(ResearchRun.id == run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            discovered_grant = await session.scalar(
                select(ResearchApprovalGrant).where(
                    ResearchApprovalGrant.id == discovered_audit.grant_id
                )
            )
            if run is None or discovered_grant is None:
                raise ValueError("APPROVAL_GRANT_IDEMPOTENCY_CONFLICT")
            identity_ids = sorted({actor_id, discovered_grant.actor_id, discovered_grant.issuer_id})
            identities = list(
                (
                    await session.scalars(
                        select(User)
                        .where(User.id.in_(identity_ids))
                        .order_by(User.id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).all()
            )
            grant = await session.scalar(
                select(ResearchApprovalGrant)
                .where(ResearchApprovalGrant.id == discovered_audit.grant_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            audits = list(
                (
                    await session.scalars(
                        select(ResearchApprovalGrantAudit)
                        .where(
                            ResearchApprovalGrantAudit.actor_id == actor_id,
                            ResearchApprovalGrantAudit.idempotency_key == idempotency_key,
                        )
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).all()
            )
            if grant is None or len(audits) != 1:
                raise ValueError("APPROVAL_GRANT_IDEMPOTENCY_CONFLICT")
            audit = audits[0]
            if (
                audit.event_type != event_type
                or audit.policy_version != _GRANT_AUTHORITY_POLICY_VERSION
                or audit.policy_material_hash != _grant_authority_policy_hash()
                or audit.command_material_hash != content_hash(command_material)
            ):
                raise ValueError("APPROVAL_GRANT_IDEMPOTENCY_CONFLICT")
            if {
                identity.id for identity in identities if identity.principal_kind == "HUMAN"
            } != set(identity_ids) or not _grant_audit_matches(audit, grant):
                raise ValueError("APPROVAL_GRANT_IDEMPOTENCY_CONFLICT")
            return grant

    async def _read_probe(self, probe: _GrantCommitProbe) -> ResearchApprovalGrant | None:
        return await self._read_replay(
            actor_id=probe.actor_id,
            idempotency_key=probe.idempotency_key,
            event_type=probe.event_type,
            command_material=probe.command_material,
        )


def approval_grant_material(
    *,
    actor_id: str,
    run_id: str,
    workspace_id: str | None,
    permission: str,
    subject_kind: str,
    issuer_id: str,
    issuer_kind: str,
    issued_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    """Canonical immutable material signed by trusted grant provisioning."""

    return {
        "schema_version": "ai-research-approval-grant/v1",
        "actor_id": actor_id,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "permission": permission,
        "subject_kind": subject_kind,
        "issuer_id": issuer_id,
        "issuer_kind": issuer_kind,
        "issued_at": _as_utc(issued_at),
        "expires_at": _as_utc(expires_at),
    }


def approval_grant_hash(grant: ResearchApprovalGrant) -> str:
    """Recompute an approval grant's immutable authority identity."""

    return content_hash(
        approval_grant_material(
            actor_id=grant.actor_id,
            run_id=grant.run_id,
            workspace_id=grant.workspace_id,
            permission=grant.permission,
            subject_kind=grant.subject_kind,
            issuer_id=grant.issuer_id,
            issuer_kind=grant.issuer_kind,
            issued_at=grant.issued_at,
            expires_at=grant.expires_at,
        )
    )


def grant_authority_policy_material() -> dict[str, Any]:
    """Return the immutable control-plane policy used for grant commands."""

    return {
        "schema_version": "ai-research-approval-grant-authority/v1",
        "version": _GRANT_AUTHORITY_POLICY_VERSION,
        "manager_permission": _MANAGE_GRANTS_PERMISSION,
        "grant_permission": _APPROVAL_PERMISSION,
        "issuer_kind": "HUMAN",
        "subject_kind": "HUMAN",
        "max_ttl_seconds": _MAX_GRANT_TTL_SECONDS,
    }


def _grant_authority_policy_hash() -> str:
    return content_hash(grant_authority_policy_material())


def _grant_issue_command_material(
    *,
    run_id: str,
    subject_id: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    return {
        "schema_version": "ai-research-approval-grant-issue/v1",
        "run_id": run_id,
        "subject_id": subject_id,
        "permission": _APPROVAL_PERMISSION,
        "ttl_seconds": ttl_seconds,
        "policy_version": _GRANT_AUTHORITY_POLICY_VERSION,
        "policy_material_hash": _grant_authority_policy_hash(),
    }


def _grant_revoke_command_material(
    *,
    run_id: str,
    grant_id: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": "ai-research-approval-grant-revoke/v1",
        "run_id": run_id,
        "grant_id": grant_id,
        "reason_hash": content_hash(reason),
        "policy_version": _GRANT_AUTHORITY_POLICY_VERSION,
        "policy_material_hash": _grant_authority_policy_hash(),
    }


def _grant_audit_model(
    *,
    grant: ResearchApprovalGrant,
    event_type: str,
    actor_id: str,
    idempotency_key: str,
    command_material: dict[str, Any],
    occurred_at: datetime,
    reason_hash: str | None,
) -> ResearchApprovalGrantAudit:
    return ResearchApprovalGrantAudit(
        grant_id=grant.id,
        event_type=event_type,
        actor_id=actor_id,
        run_id=grant.run_id,
        workspace_id=grant.workspace_id,
        subject_id=grant.actor_id,
        permission=grant.permission,
        policy_version=_GRANT_AUTHORITY_POLICY_VERSION,
        policy_material_hash=_grant_authority_policy_hash(),
        idempotency_key=idempotency_key,
        command_material_hash=content_hash(command_material),
        reason_hash=reason_hash,
        occurred_at=occurred_at,
    )


async def _load_locked_issued_grant_audits(
    session: AsyncSession,
    grant_ids: set[str],
) -> list[ResearchApprovalGrantAudit]:
    """Lock every issuing receipt for the exact grants under consideration."""

    if not grant_ids:
        return []
    return list(
        (
            await session.scalars(
                select(ResearchApprovalGrantAudit)
                .where(
                    ResearchApprovalGrantAudit.grant_id.in_(sorted(grant_ids)),
                    ResearchApprovalGrantAudit.event_type == "ISSUED",
                )
                .order_by(ResearchApprovalGrantAudit.grant_id, ResearchApprovalGrantAudit.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )


async def _load_locked_grant_audits(
    session: AsyncSession,
    grant_ids: set[str],
) -> list[ResearchApprovalGrantAudit]:
    """Lock the complete issue/revoke history for the exact grants."""

    if not grant_ids:
        return []
    return list(
        (
            await session.scalars(
                select(ResearchApprovalGrantAudit)
                .where(ResearchApprovalGrantAudit.grant_id.in_(sorted(grant_ids)))
                .order_by(
                    ResearchApprovalGrantAudit.grant_id,
                    ResearchApprovalGrantAudit.event_type,
                    ResearchApprovalGrantAudit.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )


def _grant_audit_matches(
    audit: ResearchApprovalGrantAudit,
    grant: ResearchApprovalGrant,
) -> bool:
    if (
        audit.grant_id != grant.id
        or audit.run_id != grant.run_id
        or audit.workspace_id != grant.workspace_id
        or audit.subject_id != grant.actor_id
        or audit.permission != grant.permission
        or audit.policy_version != _GRANT_AUTHORITY_POLICY_VERSION
        or audit.policy_material_hash != _grant_authority_policy_hash()
        or _SHA256_HEX.fullmatch(audit.policy_material_hash) is None
        or _SHA256_HEX.fullmatch(audit.command_material_hash) is None
        or (audit.reason_hash is not None and _SHA256_HEX.fullmatch(audit.reason_hash) is None)
        or not audit.idempotency_key
        or approval_grant_hash(grant) != grant.grant_hash
    ):
        return False
    if audit.event_type == "ISSUED":
        ttl_seconds = int((_as_utc(grant.expires_at) - _as_utc(grant.issued_at)).total_seconds())
        material = _grant_issue_command_material(
            run_id=grant.run_id,
            subject_id=grant.actor_id,
            ttl_seconds=ttl_seconds,
        )
        return (
            audit.actor_id == grant.issuer_id
            and audit.reason_hash is None
            and _as_utc(audit.occurred_at) == _as_utc(grant.issued_at)
            and audit.command_material_hash == content_hash(material)
        )
    if audit.event_type == "REVOKED":
        if grant.revoked_at is None or grant.revoked_by is None or grant.revocation_reason is None:
            return False
        material = _grant_revoke_command_material(
            run_id=grant.run_id,
            grant_id=grant.id,
            reason=grant.revocation_reason,
        )
        return (
            audit.actor_id == grant.revoked_by
            and audit.reason_hash == content_hash(grant.revocation_reason)
            and _as_utc(audit.occurred_at) == _as_utc(grant.revoked_at)
            and audit.command_material_hash == content_hash(material)
        )
    return False


def _validate_grant_command_ids(
    *,
    authenticated_actor_id: str,
    run_id: str,
    subject_id: str,
    idempotency_key: str,
) -> None:
    values = (authenticated_actor_id, run_id, subject_id, idempotency_key)
    if (
        any(not isinstance(value, str) for value in values)
        or any(not value.strip() or value != value.strip() for value in values)
        or len(idempotency_key) > 128
    ):
        raise ValueError("APPROVAL_GRANT_COMMAND_INVALID")


def _grant_operation_lock(run_id: str, identity: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    shards = _LOCKS_BY_LOOP.get(loop)
    if shards is None:
        shards = tuple(asyncio.Lock() for _ in range(_LOCK_SHARD_COUNT))
        _LOCKS_BY_LOOP[loop] = shards
    digest = hashlib.sha256(f"{run_id}\0{identity}".encode()).digest()
    return shards[int.from_bytes(digest[:8], "big") % _LOCK_SHARD_COUNT]


def _grant_is_current(grant: ResearchApprovalGrant, authority: ApprovalAuthority) -> bool:
    if (
        grant.workspace_id != authority.run.workspace_id
        or grant.subject_kind != "HUMAN"
        or grant.issuer_kind != "HUMAN"
        or grant.revoked_at is not None
        or _as_utc(grant.issued_at) > authority.database_now
        or _as_utc(grant.expires_at) <= authority.database_now
        or _SHA256_HEX.fullmatch(grant.grant_hash) is None
        or approval_grant_hash(grant) != grant.grant_hash
    ):
        return False
    return True


def _validate_policy(policy: ApprovalPolicy) -> None:
    if (
        not policy.version.strip()
        or not policy.promotion_policy_versions
        or any(not item.strip() for item in policy.promotion_policy_versions)
        or policy.mode not in {"single_actor", "multi_actor"}
        or policy.required_permission != _APPROVAL_PERMISSION
        or policy.ttl_seconds < 1
        or policy.cooldown_seconds < 0
        or any(not key.strip() for key in policy.required_challenge_keys)
        or len(set(policy.required_challenge_keys)) != len(policy.required_challenge_keys)
    ):
        raise ValueError("APPROVAL_POLICY_CATALOG_INVALID")
    if policy.mode == "single_actor" and (
        policy.cooldown_seconds < 1
        or not policy.required_challenge_keys
        or not policy.risk_acknowledgement_required
    ):
        raise ValueError("APPROVAL_POLICY_CATALOG_INVALID")


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("APPROVAL_DATABASE_CLOCK_INVALID")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
