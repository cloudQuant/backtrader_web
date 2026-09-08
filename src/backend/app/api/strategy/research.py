"""v2 trusted AI research endpoints.

Legacy AI-research routes remain in ``base.py``.  This router intentionally
owns only protocol-v2 resources and never changes their legacy semantics.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy import select

from app.api._dependencies import get_current_user
from app.config import get_settings
from app.db.database import async_session_maker
from app.models.permission import ROLE_PERMISSIONS, Permission, Role, user_roles
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.ai_research_v2 import (
    ResearchApprovalContextResponse,
    ResearchApprovalDecisionCreate,
    ResearchApprovalDecisionResponse,
    ResearchApprovalGrantIssueCreate,
    ResearchApprovalGrantResponse,
    ResearchApprovalGrantRevokeCreate,
    ResearchApprovalRequestCreate,
    ResearchApprovalRequestResponse,
    ResearchCandidateFreezeRequest,
    ResearchCandidateResponse,
    ResearchConfigProfileCreateRequest,
    ResearchConfigProfileResponse,
    ResearchDataPrecheckRequest,
    ResearchDataPrecheckResponse,
    ResearchDatasetCreateRequest,
    ResearchDatasetResponse,
    ResearchEpochCreateRequest,
    ResearchEpochResponse,
    ResearchGovernanceDecisionCreateRequest,
    ResearchGovernanceDecisionResponse,
    ResearchHoldoutEvaluationCommandResponse,
    ResearchHoldoutEvaluationRequest,
    ResearchHypothesisConfirmRequest,
    ResearchHypothesisDraftRequest,
    ResearchHypothesisResponse,
    ResearchHypothesisRevisionRequest,
    ResearchRunSubmissionResponse,
    ResearchRunSubmitRequest,
    ResearchTaskEventListResponse,
    ResearchTaskListResponse,
    ResearchTaskResponse,
    ResearchWorkbenchResponse,
)
from app.services.research.approval import (
    ApprovalService,
    approval_decision_record_intent_hash,
    safe_approval_human_text,
)
from app.services.research.approval_authority import ApprovalGrantService
from app.services.research.candidate_registry import CandidateRegistry
from app.services.research.data_precheck import ResearchDataPrecheckService
from app.services.research.dataset_integrity import DatasetObjectResolver
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.evidence_package import EvidencePackageService
from app.services.research.experiment_registry import ExperimentEpochRegistry
from app.services.research.governance import GovernanceDecisionService, GovernanceDeviationPolicy
from app.services.research.holdout_request import (
    HoldoutRequestCapabilityError,
    HoldoutRequestService,
)
from app.services.research.hypothesis_registry import HypothesisRegistry
from app.services.research.orchestrator import ResearchOrchestrator
from app.services.research.profile_migration import ProfileMigrationService
from app.services.research.redaction import redact_sensitive_payload
from app.services.research.resolver_factory import resolve_configured_dataset_object_resolver
from app.services.research.task_runner import ResearchTaskService

router = APIRouter(prefix="/ai-research/v2", tags=["Trusted AI Research"])

_HOLDOUT_REQUEST_RATE_LIMIT = "30/minute"
_HOLDOUT_REQUEST_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": ResearchHoldoutEvaluationRequest.model_json_schema(mode="validation")
            }
        },
    },
    "parameters": [
        {
            "name": "Idempotency-Key",
            "in": "header",
            "required": True,
            "schema": {"type": "string", "minLength": 1, "maxLength": 128},
        }
    ],
}
_APPROVAL_PUBLIC_ERROR_CATALOG_VERSION = "ai-research-approval-errors/v1"
# This tuple is the single machine-readable authority for public approval errors.
# Each entry is ``(stable code, HTTP status, retryable)`` and is deliberately sorted.
_APPROVAL_PUBLIC_ERROR_CATALOG = (
    ("APPROVAL_CAPABILITY_PROFILE_INVALID", 409, False),
    ("APPROVAL_CHALLENGE_INCOMPLETE", 422, False),
    ("APPROVAL_CHALLENGE_INVALID", 422, False),
    ("APPROVAL_COOLDOWN_ACTIVE", 409, False),
    ("APPROVAL_DECISION_COMMIT_OUTCOME_UNKNOWN", 503, True),
    ("APPROVAL_DECISION_INVALID", 422, False),
    ("APPROVAL_EVIDENCE_DENIED", 422, False),
    ("APPROVAL_EVIDENCE_PACKAGE_CORRUPT", 409, False),
    ("APPROVAL_EVIDENCE_PACKAGE_NOT_FOUND", 404, False),
    ("APPROVAL_EVIDENCE_PACKAGE_STALE", 409, False),
    ("APPROVAL_EVIDENCE_PACKAGE_UNVERIFIABLE", 409, False),
    ("APPROVAL_EVIDENCE_PACKAGE_VERSION_UNSUPPORTED", 409, False),
    ("APPROVAL_EVIDENCE_PACKAGE_WITHDRAWN", 409, False),
    ("APPROVAL_GRANT_ALREADY_ACTIVE", 409, False),
    ("APPROVAL_GRANT_ALREADY_REVOKED", 409, False),
    ("APPROVAL_GRANT_AMBIGUOUS", 403, False),
    ("APPROVAL_GRANT_AUDIT_INVALID", 403, False),
    ("APPROVAL_GRANT_COMMAND_INVALID", 422, False),
    ("APPROVAL_GRANT_COMMIT_OUTCOME_UNKNOWN", 503, True),
    ("APPROVAL_GRANT_IDEMPOTENCY_CONFLICT", 409, False),
    ("APPROVAL_GRANT_MANAGER_REQUIRED", 403, False),
    ("APPROVAL_GRANT_NOT_FOUND", 404, False),
    ("APPROVAL_GRANT_REQUIRED", 403, False),
    ("APPROVAL_GRANT_REVOCATION_REASON_REQUIRED", 422, False),
    ("APPROVAL_GRANT_SCOPE_MISMATCH", 409, False),
    ("APPROVAL_GRANT_SCOPE_NOT_FOUND", 404, False),
    ("APPROVAL_GRANT_STALE", 422, False),
    ("APPROVAL_GRANT_SUBJECT_INVALID", 422, False),
    ("APPROVAL_GRANT_TTL_INVALID", 422, False),
    ("APPROVAL_HARD_GATES_NOT_PASS", 409, False),
    ("APPROVAL_IDEMPOTENCY_CONFLICT", 409, False),
    ("APPROVAL_IDEMPOTENCY_KEY_REQUIRED", 422, False),
    ("APPROVAL_IDEMPOTENCY_OR_EVIDENCE_INVALID", 422, False),
    ("APPROVAL_POLICY_MATERIAL_MISMATCH", 409, False),
    ("APPROVAL_POLICY_SCOPE_MISMATCH", 409, False),
    ("APPROVAL_POLICY_UNSUPPORTED", 409, False),
    ("APPROVAL_REASON_REQUIRED", 422, False),
    ("APPROVAL_REQUEST_COMMIT_OUTCOME_UNKNOWN", 503, True),
    ("APPROVAL_REQUEST_EVIDENCE_MISMATCH", 409, False),
    ("APPROVAL_REQUEST_EXPIRED", 409, False),
    ("APPROVAL_REQUEST_IDEMPOTENCY_CONFLICT", 409, False),
    ("APPROVAL_REQUEST_NOT_FOUND", 422, False),
    ("APPROVAL_REQUEST_NOT_PENDING", 409, False),
    ("APPROVAL_REQUEST_REQUIRED", 422, False),
    ("APPROVAL_RISK_ACKNOWLEDGEMENT_INVALID", 422, False),
    ("APPROVAL_RISK_ACKNOWLEDGEMENT_REQUIRED", 422, False),
    ("APPROVAL_SCOPE_NOT_FOUND", 404, False),
    ("APPROVAL_SEPARATION_REQUIRED", 403, False),
)
_APPROVAL_PUBLIC_ERROR_BY_CODE = {
    code: (http_status, retryable)
    for code, http_status, retryable in _APPROVAL_PUBLIC_ERROR_CATALOG
}
_APPROVAL_PUBLIC_ERROR_CODES = frozenset(_APPROVAL_PUBLIC_ERROR_BY_CODE)
if len(_APPROVAL_PUBLIC_ERROR_CODES) != len(_APPROVAL_PUBLIC_ERROR_CATALOG):
    raise RuntimeError("APPROVAL_PUBLIC_ERROR_CATALOG_DUPLICATE")
_APPROVAL_PUBLIC_ERROR_CATALOG_HASH = hashlib.sha256(
    json.dumps(
        {
            "entries": _APPROVAL_PUBLIC_ERROR_CATALOG,
            "version": _APPROVAL_PUBLIC_ERROR_CATALOG_VERSION,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()


def _holdout_request_rate_limit_key(request: Request) -> str:
    """Share one bounded rejection bucket per authenticated actor and remote IP."""

    actor_id = str(getattr(request.state, "user_id", "unauthenticated"))
    return f"ai-research-holdout:{actor_id}:{get_remote_address(request)}"


def require_protocol_v2_write_enabled() -> None:
    """Keep new v2 mutations opt-in while preserving existing evidence reads."""

    if not get_settings().AI_RESEARCH_PROTOCOL_V2_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI_RESEARCH_PROTOCOL_V2_DISABLED",
        )


@lru_cache
def get_hypothesis_registry() -> HypothesisRegistry:
    """Return the stateless v2 hypothesis aggregate owner."""

    return HypothesisRegistry()


def get_dataset_object_resolver() -> DatasetObjectResolver | None:
    """Return the deployment-owned dataset-attestation resolver when configured.

    A browser cannot select this dependency.  The default is deliberately
    absent, which makes dataset creation fail closed until a deployment wires
    a trusted resolver.  Tests override this seam with an in-memory resolver.
    """

    try:
        return resolve_configured_dataset_object_resolver(get_settings())
    except ValueError as exc:
        code = str(exc)
        if code not in {
            "DATASET_OBJECT_RESOLVER_TYPE_DENIED",
            "DATASET_OBJECT_RESOLVER_CONFIGURATION_INVALID",
        }:
            code = "DATASET_OBJECT_RESOLVER_CONFIGURATION_INVALID"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=code) from None


def get_dataset_registry(
    object_resolver: Any = Depends(get_dataset_object_resolver),
) -> DatasetRegistry:
    """Return a dataset registry bound to the server-owned resolver seam."""

    return DatasetRegistry(object_resolver=object_resolver)


def get_data_precheck_service(
    dataset_registry: DatasetRegistry = Depends(get_dataset_registry),
) -> ResearchDataPrecheckService:
    """Return the precheck authority bound to this request's dataset resolver."""

    return ResearchDataPrecheckService(dataset_registry=dataset_registry)


def get_candidate_registry(
    dataset_registry: DatasetRegistry = Depends(get_dataset_registry),
) -> CandidateRegistry:
    """Bind irreversible candidate freezing to the trusted dataset resolver."""

    return CandidateRegistry(dataset_registry=dataset_registry)


def get_holdout_request_service(
    dataset_registry: DatasetRegistry = Depends(get_dataset_registry),
) -> HoldoutRequestService:
    """Bind queued holdout intents to the deployment-owned object resolver."""

    return HoldoutRequestService(dataset_registry=dataset_registry)


def get_approval_service(
    dataset_registry: DatasetRegistry = Depends(get_dataset_registry),
) -> ApprovalService:
    """Bind approval package validation to the server-owned dataset resolver."""

    return ApprovalService(
        evidence_packages=EvidencePackageService(dataset_registry=dataset_registry)
    )


@lru_cache
def get_approval_grant_service() -> ApprovalGrantService:
    """Return the explicit approval-grant control-plane service."""

    return ApprovalGrantService()


async def require_approval_grant_manager(
    current_user: Any = Depends(get_current_user),
) -> Any:
    """Require an active human with the dedicated non-default grant permission."""

    async with async_session_maker() as session:
        user = await session.scalar(select(User).where(User.id == current_user.sub))
        roles = set(
            (
                await session.scalars(
                    select(user_roles.c.role).where(user_roles.c.user_id == current_user.sub)
                )
            ).all()
        )
    granted = {
        permission
        for role_value in roles
        for role in Role
        if role.value == role_value
        for permission in ROLE_PERMISSIONS.get(role, ())
    }
    if (
        user is None
        or user.is_active is not True
        or user.principal_kind != "HUMAN"
        or Permission.MANAGE_APPROVAL_GRANTS not in granted
    ):
        raise _candidate_http_error(
            status.HTTP_403_FORBIDDEN,
            "APPROVAL_GRANT_MANAGER_REQUIRED",
        )
    return current_user


@lru_cache
def get_config_profile_service() -> ProfileMigrationService:
    """Return the user-scoped v2 configuration profile authority."""

    return ProfileMigrationService()


@lru_cache
def get_experiment_epoch_registry() -> ExperimentEpochRegistry:
    """Return the stateless v2 experiment epoch aggregate owner."""

    return ExperimentEpochRegistry()


def get_research_orchestrator(
    data_prechecks: ResearchDataPrecheckService = Depends(get_data_precheck_service),
) -> ResearchOrchestrator:
    """Return a task facade sharing the current request's dataset precheck fence."""

    return ResearchOrchestrator(
        task_service=ResearchTaskService(
            data_prechecks=data_prechecks,
            workflow_version=get_settings().AI_RESEARCH_PROTOCOL_V2_WORKFLOW_VERSION,
        )
    )


@lru_cache
def get_governance_decision_service() -> GovernanceDecisionService:
    """Return the stateless append-only governance-decision owner."""

    return GovernanceDecisionService()


def get_governance_deviation_policy() -> GovernanceDeviationPolicy:
    """Resolve the deployment-owned deviation allowlist without a browser override."""

    settings = get_settings()
    return GovernanceDeviationPolicy(
        version=settings.AI_RESEARCH_PROTOCOL_V2_GOVERNANCE_POLICY_VERSION,
        waivable_targets=frozenset(
            target.strip()
            for target in settings.AI_RESEARCH_PROTOCOL_V2_WAIVABLE_TARGETS.split(",")
            if target.strip()
        ),
    )


@router.post(
    "/hypotheses",
    response_model=ResearchHypothesisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a trusted AI research hypothesis draft",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def create_hypothesis_draft(
    data: ResearchHypothesisDraftRequest,
    current_user: Any = Depends(get_current_user),
    registry: HypothesisRegistry = Depends(get_hypothesis_registry),
) -> ResearchHypothesisResponse:
    """Create an unconfirmed v2 hypothesis owned by the authenticated user."""

    try:
        return ResearchHypothesisResponse.model_validate(
            await registry.create_draft(
                current_user.sub,
                data.payload,
                workspace_id=data.workspace_id,
                source_mandate_id=data.source_mandate_id,
            )
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/hypotheses/{version_id}",
    response_model=ResearchHypothesisResponse,
    summary="Get an owner-scoped v2 hypothesis version",
)
async def get_hypothesis_version(
    version_id: str,
    current_user: Any = Depends(get_current_user),
    registry: HypothesisRegistry = Depends(get_hypothesis_registry),
) -> ResearchHypothesisResponse:
    """Read a v2 hypothesis without disclosing another user's resource."""

    model = await registry.get_version(current_user.sub, version_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Research hypothesis not found"
        )
    return ResearchHypothesisResponse.model_validate(model)


@router.post(
    "/hypotheses/{version_id}/confirm",
    response_model=ResearchHypothesisResponse,
    summary="Confirm a complete v2 hypothesis",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def confirm_hypothesis_version(
    version_id: str,
    data: ResearchHypothesisConfirmRequest,
    current_user: Any = Depends(get_current_user),
    registry: HypothesisRegistry = Depends(get_hypothesis_registry),
) -> ResearchHypothesisResponse:
    """Confirm a server-validated draft and bind the authenticated actor."""

    try:
        return ResearchHypothesisResponse.model_validate(
            await registry.confirm(current_user.sub, version_id, request_hash=data.request_hash)
        )
    except ValueError as exc:
        raise _hypothesis_error(exc) from exc


@router.put(
    "/hypotheses/{version_id}",
    response_model=ResearchHypothesisResponse,
    summary="Revise a trusted AI research hypothesis",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def revise_hypothesis_version(
    version_id: str,
    data: ResearchHypothesisRevisionRequest,
    current_user: Any = Depends(get_current_user),
    registry: HypothesisRegistry = Depends(get_hypothesis_registry),
) -> ResearchHypothesisResponse:
    """Update a draft or fork an immutable confirmed version."""

    try:
        return ResearchHypothesisResponse.model_validate(
            await registry.revise(current_user.sub, version_id, data.payload)
        )
    except ValueError as exc:
        raise _hypothesis_error(exc) from exc


@router.post(
    "/datasets",
    response_model=ResearchDatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an Explorer-visible v2 data snapshot",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def create_dataset_snapshot(
    data: ResearchDatasetCreateRequest,
    current_user: Any = Depends(get_current_user),
    registry: DatasetRegistry = Depends(get_dataset_registry),
) -> ResearchDatasetResponse:
    """Create a non-sealed snapshot and return the URI-free Explorer projection."""

    try:
        model = await registry.create_attested_snapshot(
            user_id=current_user.sub,
            object_receipt_id=data.object_receipt_id,
            dataset_policy_version=data.dataset_policy_version,
            partition_kind=data.partition_kind,
            instrument_manifest=data.instrument_manifest,
            split_manifest=data.split_manifest,
            source_manifest=data.source_manifest,
            execution_policy=data.execution_policy,
            point_in_time_cutoff=data.point_in_time_cutoff,
            license_tags=data.license_tags,
        )
        visible = await registry.get_for_explorer(current_user.sub, model.id)
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return _dataset_response(visible)


@router.post(
    "/config-profiles",
    response_model=ResearchConfigProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user-scoped, secret-free v2 research profile",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def create_config_profile(
    data: ResearchConfigProfileCreateRequest,
    current_user: Any = Depends(get_current_user),
    service: ProfileMigrationService = Depends(get_config_profile_service),
) -> ResearchConfigProfileResponse:
    """Create a profile owned by the authenticated user, never by the process."""

    try:
        profile = await service.create(
            user_id=current_user.sub,
            name=data.name,
            description=data.description,
            config=data.config,
            workspace_id=data.workspace_id,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return _config_profile_response(profile)


@router.get(
    "/config-profiles",
    response_model=list[ResearchConfigProfileResponse],
    summary="List active v2 research profiles owned by the authenticated user",
)
async def list_config_profiles(
    workspace_id: str | None = Query(default=None, max_length=36),
    current_user: Any = Depends(get_current_user),
    service: ProfileMigrationService = Depends(get_config_profile_service),
) -> list[ResearchConfigProfileResponse]:
    """List only the caller's active profiles; unclaimed imports remain invisible."""

    profiles = await service.list_for_user(user_id=current_user.sub, workspace_id=workspace_id)
    return [_config_profile_response(profile) for profile in profiles]


@router.get(
    "/config-profiles/{profile_id}",
    response_model=ResearchConfigProfileResponse,
    summary="Get an active owner-scoped v2 research profile",
)
async def get_config_profile(
    profile_id: str,
    current_user: Any = Depends(get_current_user),
    service: ProfileMigrationService = Depends(get_config_profile_service),
) -> ResearchConfigProfileResponse:
    """Avoid cross-user profile enumeration by treating it as absent."""

    profile = await service.get_for_user(user_id=current_user.sub, profile_id=profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="RESEARCH_CONFIG_PROFILE_NOT_FOUND"
        )
    return _config_profile_response(profile)


@router.post(
    "/epochs",
    response_model=ResearchEpochResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a bounded v2 experiment epoch",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def create_experiment_epoch(
    data: ResearchEpochCreateRequest,
    current_user: Any = Depends(get_current_user),
    registry: ExperimentEpochRegistry = Depends(get_experiment_epoch_registry),
) -> ResearchEpochResponse:
    """Create an OPEN epoch only from a confirmed owner-scoped hypothesis."""

    try:
        model = await registry.create_epoch(
            user_id=current_user.sub,
            hypothesis_version_id=data.hypothesis_version_id,
            search_budget=data.search_budget,
            dataset_policy_version=data.dataset_policy_version,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return ResearchEpochResponse.model_validate(
        {
            "id": model.id,
            "hypothesis_version_id": model.hypothesis_version_id,
            "family_hash": model.family_hash,
            "search_budget": model.search_budget,
            "dataset_policy_version": model.dataset_policy_version,
            "holdout_budget": model.holdout_budget,
            "status": model.status,
            "selected_candidate_id": model.selected_candidate_id,
            "opened_at": model.opened_at,
        }
    )


@router.post(
    "/data-prechecks",
    response_model=ResearchDataPrecheckResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create server-bound v2 data precheck evidence",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def create_data_precheck(
    data: ResearchDataPrecheckRequest,
    current_user: Any = Depends(get_current_user),
    service: ResearchDataPrecheckService = Depends(get_data_precheck_service),
) -> ResearchDataPrecheckResponse:
    """Evaluate a launch binding once and return its expiry-bound evidence receipt."""

    try:
        model = await service.create(
            user_id=current_user.sub,
            hypothesis_version_id=data.hypothesis_version_id,
            dataset_snapshot_id=data.dataset_snapshot_id,
            experiment_epoch_id=data.experiment_epoch_id,
            profile_id=data.profile_id,
            profile_version=data.profile_version,
            promotion_policy_version=data.promotion_policy_version,
            request_json=data.request_json,
            workspace_id=data.workspace_id,
            ttl_seconds=data.ttl_seconds,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return ResearchDataPrecheckResponse.model_validate(model)


@router.post(
    "/runs",
    response_model=ResearchRunSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a durable protocol-v2 research run",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def submit_research_run(
    data: ResearchRunSubmitRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Any = Depends(get_current_user),
    orchestrator: ResearchOrchestrator = Depends(get_research_orchestrator),
) -> ResearchRunSubmissionResponse:
    """Submit only confirmed/dataset-bound inputs with a caller-supplied idempotency key."""

    if idempotency_key is None or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="RESEARCH_TASK_IDEMPOTENCY_KEY_REQUIRED",
        )
    try:
        result = await orchestrator.submit(
            user_id=current_user.sub,
            hypothesis_version_id=data.hypothesis_version_id,
            dataset_snapshot_id=data.dataset_snapshot_id,
            experiment_epoch_id=data.experiment_epoch_id,
            profile_id=data.profile_id,
            profile_version=data.profile_version,
            promotion_policy_version=data.promotion_policy_version,
            request_json=data.request_json,
            precheck_id=data.precheck_id,
            idempotency_key=idempotency_key,
            workspace_id=data.workspace_id,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return ResearchRunSubmissionResponse.model_validate(result)


@router.get(
    "/tasks",
    response_model=ResearchTaskListResponse,
    summary="List owner-scoped protocol-v2 tasks",
)
async def list_research_tasks(
    cursor: str | None = Query(default=None, max_length=256),
    limit: int = Query(default=20, ge=1, le=100),
    active_only: bool = Query(default=False),
    current_user: Any = Depends(get_current_user),
    orchestrator: ResearchOrchestrator = Depends(get_research_orchestrator),
) -> ResearchTaskListResponse:
    """Return a safe task projection without raw request or lease fields."""

    try:
        result = await orchestrator.list_tasks(
            user_id=current_user.sub,
            cursor=cursor,
            limit=limit,
            active_only=active_only,
        )
    except ValueError as exc:
        if str(exc) == "RESEARCH_TASK_CURSOR_INVALID":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="RESEARCH_TASK_CURSOR_INVALID",
            ) from exc
        raise
    return ResearchTaskListResponse.model_validate(result)


@router.get(
    "/tasks/{task_id}",
    response_model=ResearchTaskResponse,
    summary="Read one owner-scoped protocol-v2 task",
)
async def get_research_task(
    task_id: str,
    current_user: Any = Depends(get_current_user),
    orchestrator: ResearchOrchestrator = Depends(get_research_orchestrator),
) -> ResearchTaskResponse:
    """Avoid cross-user task enumeration by treating foreign resources as absent."""

    result = await orchestrator.get_task(user_id=current_user.sub, task_id=task_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RESEARCH_TASK_NOT_FOUND")
    return ResearchTaskResponse.model_validate(result)


@router.get(
    "/tasks/{task_id}/events",
    response_model=ResearchTaskEventListResponse,
    summary="Read display-safe protocol-v2 task events",
)
async def list_research_task_events(
    task_id: str,
    cursor: str | None = Query(default=None, max_length=256),
    limit: int = Query(default=100, ge=1, le=100),
    current_user: Any = Depends(get_current_user),
    orchestrator: ResearchOrchestrator = Depends(get_research_orchestrator),
) -> ResearchTaskEventListResponse:
    """Return only the v2 append-only summary stream, never legacy raw payloads."""

    try:
        result = await orchestrator.list_task_events(
            user_id=current_user.sub,
            task_id=task_id,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        if str(exc) == "RESEARCH_TASK_CURSOR_INVALID":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="RESEARCH_TASK_CURSOR_INVALID",
            ) from exc
        raise
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RESEARCH_TASK_NOT_FOUND")
    return ResearchTaskEventListResponse.model_validate(result)


@router.post(
    "/governance-deviations",
    response_model=ResearchGovernanceDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a server-policy-approved v2 governance deviation",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def create_governance_decision(
    data: ResearchGovernanceDecisionCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Any = Depends(get_current_user),
    service: GovernanceDecisionService = Depends(get_governance_decision_service),
) -> ResearchGovernanceDecisionResponse:
    """Append a scope-bound limitation record; no underlying gate is changed."""

    if idempotency_key is None or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="GOVERNANCE_DEVIATION_IDEMPOTENCY_REQUIRED",
        )
    try:
        decision = await service.record(
            actor_id=current_user.sub,
            policy=get_governance_deviation_policy(),
            target_requirement_or_gate=data.target_requirement_or_gate,
            original_status=data.original_status,
            reason=data.reason,
            risk=data.risk,
            compensating_controls=data.compensating_controls,
            scope=data.scope,
            idempotency_key=idempotency_key,
            expires_at=data.expires_at,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return _governance_decision_response(decision)


@router.post(
    "/governance-deviations/{decision_id}/revoke",
    response_model=ResearchGovernanceDecisionResponse,
    summary="Revoke a trusted-research governance deviation",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def revoke_governance_decision(
    decision_id: str,
    current_user: Any = Depends(get_current_user),
    service: GovernanceDecisionService = Depends(get_governance_decision_service),
) -> ResearchGovernanceDecisionResponse:
    """Record revocation while retaining the original deviation and gate status."""

    try:
        decision = await service.revoke(decision_id=decision_id, actor_id=current_user.sub)
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return _governance_decision_response(decision)


@router.get(
    "/runs/{run_id}",
    response_model=ResearchWorkbenchResponse,
    summary="Read a URI-free v2 evidence workbench",
)
async def get_research_workbench(
    run_id: str,
    current_user: Any = Depends(get_current_user),
    orchestrator: ResearchOrchestrator = Depends(get_research_orchestrator),
) -> ResearchWorkbenchResponse:
    """Read only owner-scoped v2 evidence; legacy records are not promoted here."""

    result = await orchestrator.get_workbench(current_user.sub, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RESEARCH_RUN_NOT_FOUND")
    return ResearchWorkbenchResponse.model_validate(result)


@router.get(
    "/runs/{run_id}/candidates/{candidate_id}/approval-context",
    response_model=ResearchApprovalContextResponse,
    summary="Read server-derived approval capabilities for one candidate",
)
async def get_research_approval_context(
    run_id: str,
    candidate_id: str,
    current_user: Any = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
) -> ResearchApprovalContextResponse:
    """Expose only safe capabilities; identity, grant, and policy catalogs stay private."""

    try:
        context = await service.approval_context(
            authenticated_actor_id=current_user.sub,
            run_id=run_id,
            candidate_id=candidate_id,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return ResearchApprovalContextResponse.model_validate(context)


@router.post(
    "/runs/{run_id}/approval-grants",
    response_model=ResearchApprovalGrantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a run-scoped human approval grant",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def issue_research_approval_grant(
    run_id: str,
    data: ResearchApprovalGrantIssueCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Any = Depends(require_approval_grant_manager),
    service: ApprovalGrantService = Depends(get_approval_grant_service),
) -> ResearchApprovalGrantResponse:
    """Issue authority using only the authenticated manager and server policy."""

    key = _require_approval_idempotency_key(idempotency_key)
    try:
        grant = await service.issue(
            authenticated_actor_id=current_user.sub,
            run_id=run_id,
            subject_id=data.subject_id,
            ttl_seconds=data.ttl_seconds,
            idempotency_key=key,
        )
        grant_status = await service.response_status(grant)
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return _approval_grant_response(grant, status_value=grant_status)


@router.post(
    "/runs/{run_id}/approval-grants/{grant_id}/revoke",
    response_model=ResearchApprovalGrantResponse,
    summary="Revoke a run-scoped human approval grant",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def revoke_research_approval_grant(
    run_id: str,
    grant_id: str,
    data: ResearchApprovalGrantRevokeCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Any = Depends(require_approval_grant_manager),
    service: ApprovalGrantService = Depends(get_approval_grant_service),
) -> ResearchApprovalGrantResponse:
    """Apply the grant's only state transition and return a minimal receipt."""

    key = _require_approval_idempotency_key(idempotency_key)
    try:
        grant = await service.revoke(
            authenticated_actor_id=current_user.sub,
            run_id=run_id,
            grant_id=grant_id,
            reason=data.reason,
            idempotency_key=key,
        )
        grant_status = await service.response_status(grant)
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return _approval_grant_response(grant, status_value=grant_status)


@router.post(
    "/runs/{run_id}/candidates/{candidate_id}/approval-requests",
    response_model=ResearchApprovalRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an evidence-bound human approval request",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def create_research_approval_request(
    run_id: str,
    candidate_id: str,
    data: ResearchApprovalRequestCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Any = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
) -> ResearchApprovalRequestResponse:
    """Use the authenticated token actor and resolve every authority field server-side."""

    key = _require_approval_idempotency_key(idempotency_key)
    try:
        request_model = await service.request_approval(
            authenticated_actor_id=current_user.sub,
            run_id=run_id,
            candidate_id=candidate_id,
            gate_input_evidence_hash=data.gate_input_evidence_hash,
            evidence_package_hash=data.evidence_package_hash,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return ResearchApprovalRequestResponse.model_validate(request_model)


@router.post(
    "/runs/{run_id}/candidates/{candidate_id}/approval-decisions",
    response_model=ResearchApprovalDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an immutable server-authorized human approval decision",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def create_research_approval_decision(
    run_id: str,
    candidate_id: str,
    data: ResearchApprovalDecisionCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: Any = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
) -> ResearchApprovalDecisionResponse:
    """Ignore no identity assertion: the only decision actor is the verified token subject."""

    key = _require_approval_idempotency_key(idempotency_key)
    try:
        decision_model = await service.decide(
            authenticated_actor_id=current_user.sub,
            run_id=run_id,
            candidate_id=candidate_id,
            approval_request_id=data.approval_request_id,
            decision=data.decision,
            reason=data.reason,
            gate_input_evidence_hash=data.gate_input_evidence_hash,
            evidence_package_hash=data.evidence_package_hash,
            idempotency_key=key,
            challenge_responses=data.challenge_responses,
            residual_risk_acknowledgement=data.residual_risk_acknowledgement,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return _approval_decision_response(decision_model)


@router.post(
    "/candidates/{candidate_id}/freeze",
    response_model=ResearchCandidateResponse,
    summary="Freeze a fully published discovery candidate",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def freeze_research_candidate(
    candidate_id: str,
    data: ResearchCandidateFreezeRequest,
    current_user: Any = Depends(get_current_user),
    registry: CandidateRegistry = Depends(get_candidate_registry),
) -> ResearchCandidateResponse:
    """Select an owner-scoped candidate without granting evaluation or trading rights."""

    try:
        candidate = await registry.freeze_discovery(
            user_id=current_user.sub,
            candidate_id=candidate_id,
            frozen_by=current_user.sub,
            expected_candidate_hash=data.expected_candidate_hash,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return _candidate_response(candidate)


@router.post(
    "/candidates/{candidate_id}/holdout-evaluation",
    response_model=ResearchHoldoutEvaluationCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue independent holdout evaluation for a frozen candidate",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
    openapi_extra=_HOLDOUT_REQUEST_OPENAPI,
)
@limiter.shared_limit(
    _HOLDOUT_REQUEST_RATE_LIMIT,
    scope="ai-research-holdout-request",
    key_func=_holdout_request_rate_limit_key,
)
async def request_holdout_evaluation(
    candidate_id: str,
    request: Request,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        include_in_schema=False,
    ),
    current_user: Any = Depends(get_current_user),
    service: HoldoutRequestService = Depends(get_holdout_request_service),
) -> ResearchHoldoutEvaluationCommandResponse:
    """Persist only a queued intent; token issuance and evaluation happen elsewhere."""

    try:
        raw_data = await request.json()
    except (ValueError, UnicodeDecodeError):
        await _audit_holdout_route_rejection(
            service,
            user_id=current_user.sub,
            candidate_id=candidate_id,
            expected_candidate_hash=None,
            reason_code="HOLDOUT_REQUEST_BODY_INVALID",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="HOLDOUT_REQUEST_BODY_INVALID",
        ) from None
    raw_expected_hash = (
        raw_data.get("expected_candidate_hash") if isinstance(raw_data, dict) else None
    )
    try:
        data = ResearchHoldoutEvaluationRequest.model_validate(raw_data)
    except ValidationError:
        await _audit_holdout_route_rejection(
            service,
            user_id=current_user.sub,
            candidate_id=candidate_id,
            expected_candidate_hash=raw_expected_hash,
            reason_code="HOLDOUT_REQUEST_BODY_INVALID",
        )
        raise _v2_error(ValueError("HOLDOUT_REQUEST_BODY_INVALID")) from None
    if idempotency_key is None or not idempotency_key.strip():
        await _audit_holdout_route_rejection(
            service,
            user_id=current_user.sub,
            candidate_id=candidate_id,
            expected_candidate_hash=data.expected_candidate_hash,
            reason_code="HOLDOUT_REQUEST_IDEMPOTENCY_KEY_REQUIRED",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="HOLDOUT_REQUEST_IDEMPOTENCY_KEY_REQUIRED",
        )
    if len(idempotency_key) > 128:
        await _audit_holdout_route_rejection(
            service,
            user_id=current_user.sub,
            candidate_id=candidate_id,
            expected_candidate_hash=data.expected_candidate_hash,
            reason_code="HOLDOUT_REQUEST_IDEMPOTENCY_KEY_INVALID",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="HOLDOUT_REQUEST_IDEMPOTENCY_KEY_INVALID",
        )
    try:
        command = await service.request(
            user_id=current_user.sub,
            candidate_id=candidate_id,
            expected_candidate_hash=data.expected_candidate_hash,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc
    return ResearchHoldoutEvaluationCommandResponse.model_validate(command)


@router.get(
    "/holdout-evaluations/{command_id}",
    response_model=ResearchHoldoutEvaluationCommandResponse,
    summary="Read one owner-scoped holdout evaluation command",
)
async def get_holdout_evaluation_command(
    command_id: str,
    current_user: Any = Depends(get_current_user),
    service: HoldoutRequestService = Depends(get_holdout_request_service),
) -> ResearchHoldoutEvaluationCommandResponse:
    """Recover safe queue state without exposing foreign operation identifiers."""

    command = await service.get(user_id=current_user.sub, command_id=command_id)
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HOLDOUT_REQUEST_NOT_FOUND",
        )
    return ResearchHoldoutEvaluationCommandResponse.model_validate(command)


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=ResearchTaskResponse,
    summary="Request cancellation of a durable v2 task",
    dependencies=[Depends(require_protocol_v2_write_enabled)],
)
async def cancel_research_task(
    task_id: str,
    current_user: Any = Depends(get_current_user),
    orchestrator: ResearchOrchestrator = Depends(get_research_orchestrator),
) -> ResearchTaskResponse:
    """Cancel queued work immediately or persist intent for its lease owner."""

    result = await orchestrator.request_cancel(current_user.sub, task_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RESEARCH_TASK_NOT_FOUND")
    return ResearchTaskResponse.model_validate(result)


def _hypothesis_error(error: ValueError) -> HTTPException:
    code = str(error)
    if code == "HYPOTHESIS_NOT_FOUND":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=code)
    if code.startswith("HYPOTHESIS_REQUIRED_FIELDS_MISSING"):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=code)
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=code)


async def _audit_holdout_route_rejection(
    service: HoldoutRequestService,
    *,
    user_id: str,
    candidate_id: str,
    expected_candidate_hash: object,
    reason_code: str,
) -> None:
    """Persist a route-local rejection without retaining the submitted body."""

    try:
        await service.record_rejected_request(
            user_id=user_id,
            candidate_id=candidate_id,
            expected_candidate_hash=expected_candidate_hash,
            reason_code=reason_code,
        )
    except ValueError as exc:
        raise _v2_error(exc) from exc


def _v2_error(error: ValueError) -> HTTPException:
    if isinstance(error, HoldoutRequestCapabilityError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": error.code,
                "message": error.code,
                "missing_capabilities": list(error.missing_capabilities),
            },
        )
    code = str(error)
    if code.startswith("APPROVAL_"):
        if code.startswith("APPROVAL_CHALLENGE_INCOMPLETE:"):
            code = "APPROVAL_CHALLENGE_INCOMPLETE"
        elif code not in _APPROVAL_PUBLIC_ERROR_CODES:
            code = "RESEARCH_APPROVAL_OPERATION_FAILED"
        http_status, retryable = _APPROVAL_PUBLIC_ERROR_BY_CODE.get(code, (422, False))
        return _candidate_http_error(http_status, code, retryable=retryable)
    if code == "RESEARCH_CONFIG_PROFILE_NOT_FOUND":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=code)
    if code.startswith("RESEARCH_CONFIG_PROFILE_"):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=code)
    if code == "CANDIDATE_NOT_FOUND":
        return _candidate_http_error(status.HTTP_404_NOT_FOUND, code)
    if code == "CANDIDATE_FREEZE_VERIFICATION_UNAVAILABLE":
        return _candidate_http_error(status.HTTP_503_SERVICE_UNAVAILABLE, code, retryable=True)
    if code.startswith("CANDIDATE_"):
        return _candidate_http_error(status.HTTP_409_CONFLICT, code)
    if code in {
        "HOLDOUT_REQUEST_PERSISTENCE_FAILED",
        "HOLDOUT_REQUEST_AUDIT_UNAVAILABLE",
        "HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN",
        "HOLDOUT_REQUEST_SNAPSHOT_FAILURE_PERSISTENCE_FAILED",
        "DATASET_OBJECT_REVALIDATION_UNAVAILABLE",
    }:
        return _candidate_http_error(status.HTTP_503_SERVICE_UNAVAILABLE, code, retryable=True)
    if code == "HOLDOUT_SNAPSHOT_SELECTION_AMBIGUOUS":
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=code)
    if code in {
        "HOLDOUT_REQUEST_BODY_INVALID",
        "HOLDOUT_REQUEST_IDEMPOTENCY_KEY_REQUIRED",
        "HOLDOUT_REQUEST_IDEMPOTENCY_KEY_INVALID",
    }:
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=code)
    if code.startswith(("HOLDOUT_REQUEST_", "BLOCKED_TOPOLOGY_CAPABILITY")):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=code)
    if code.endswith("_NOT_FOUND") or code.endswith("_DENIED"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=code)
    if code.startswith("GOVERNANCE_DEVIATION_"):
        if code in {
            "GOVERNANCE_DEVIATION_NON_WAIVABLE",
            "GOVERNANCE_DEVIATION_IDEMPOTENCY_CONFLICT",
        }:
            return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=code)
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=code)
    if code.startswith(("DATASET_", "EXPERIMENT_EPOCH_", "RESEARCH_TASK_")):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=code)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=code)


def _candidate_http_error(status_code: int, code: str, *, retryable: bool = False) -> HTTPException:
    """Keep the stable business code in structured details and the visible message."""

    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": code, "retryable": retryable},
    )


def _require_approval_idempotency_key(value: str | None) -> str:
    """Validate a bounded command identity before entering approval services."""

    if value is None or not value.strip() or len(value) > 128:
        raise _v2_error(ValueError("APPROVAL_IDEMPOTENCY_KEY_REQUIRED"))
    return value.strip()


def _dataset_response(visible: Any) -> ResearchDatasetResponse:
    return ResearchDatasetResponse.model_validate(
        {
            "id": visible.id,
            "dataset_policy_version": visible.dataset_policy_version,
            "partition_kind": visible.partition_kind,
            "instrument_manifest": visible.instrument_manifest,
            "split_manifest": visible.split_manifest,
            "source_manifest": visible.source_manifest,
            "execution_policy": visible.execution_policy,
            "point_in_time_cutoff": visible.point_in_time_cutoff,
            "content_hash": visible.content_hash,
        }
    )


def _candidate_response(model: Any) -> ResearchCandidateResponse:
    """Return only the immutable identity shown in the freeze confirmation."""

    return ResearchCandidateResponse.model_validate(
        {
            "id": model.id,
            "run_id": model.run_id,
            "experiment_epoch_id": model.experiment_epoch_id,
            "source_version_id": model.source_version_id,
            "dataset_snapshot_id": model.dataset_snapshot_id,
            "code_artifact_id": model.code_artifact_id,
            "dependency_artifact_id": model.dependency_artifact_id,
            "candidate_hash": model.candidate_hash,
            "environment_hash": model.environment_hash,
            "cost_model_hash": model.cost_model_hash,
            "params": redact_sensitive_payload(model.params),
            "freeze_status": model.freeze_status,
            "frozen_at": model.frozen_at,
        }
    )


def _config_profile_response(model: Any) -> ResearchConfigProfileResponse:
    return ResearchConfigProfileResponse.model_validate(
        {
            "id": model.id,
            "workspace_id": model.workspace_id,
            "name": model.name,
            "description": model.description,
            "config": dict(model.config or {}),
            "credential_refs": dict(model.credential_refs or {}),
            "status": model.status,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )


def _governance_decision_response(model: Any) -> ResearchGovernanceDecisionResponse:
    """Return a limitation summary without raw actor identity or scope values."""

    return ResearchGovernanceDecisionResponse.model_validate(
        {
            "id": model.id,
            "target_requirement_or_gate": model.target_requirement_or_gate,
            "original_status": model.original_status,
            "reason": redact_sensitive_payload(model.reason),
            "risk": redact_sensitive_payload(model.risk),
            "compensating_controls": redact_sensitive_payload(model.compensating_controls or []),
            "effective_at": _as_utc_datetime(model.effective_at),
            "expires_at": _as_utc_datetime(model.expires_at),
            "revoked_at": _as_utc_datetime(model.revoked_at),
        }
    )


def _approval_decision_response(model: Any) -> ResearchApprovalDecisionResponse:
    """Project an immutable receipt without human or grant authority details."""

    return ResearchApprovalDecisionResponse.model_validate(
        {
            "id": model.id,
            "run_id": model.run_id,
            "candidate_id": model.candidate_id,
            "approval_request_id": model.approval_request_id,
            "decision": model.decision,
            "policy_version": model.policy_version,
            "policy_material_hash": model.policy_material_hash,
            "approval_mode": model.approval_mode,
            "gate_input_evidence_hash": model.gate_input_evidence_hash,
            "evidence_package_hash": model.evidence_package_hash,
            "decision_material_hash": model.decision_material_hash,
            "decision_intent_hash": approval_decision_record_intent_hash(model),
            "risk_acknowledgement": model.risk_acknowledgement,
            "challenge_keys": [
                item["key"]
                for item in list(model.challenge_records or [])
                if isinstance(item, dict) and isinstance(item.get("key"), str)
            ],
            "reason": safe_approval_human_text(model.comment or ""),
            "decided_at": _as_utc_datetime(model.decided_at),
            "expires_at": _as_utc_datetime(model.expires_at),
        }
    )


def _approval_grant_response(
    model: Any,
    *,
    status_value: str,
) -> ResearchApprovalGrantResponse:
    """Project a management receipt without issuer, hash, or audit internals."""

    return ResearchApprovalGrantResponse.model_validate(
        {
            "id": model.id,
            "run_id": model.run_id,
            "workspace_id": model.workspace_id,
            "subject_id": model.actor_id,
            "permission": model.permission,
            "status": status_value,
            "issued_at": _as_utc_datetime(model.issued_at),
            "expires_at": _as_utc_datetime(model.expires_at),
            "revoked_at": _as_utc_datetime(model.revoked_at),
        }
    )


def _as_utc_datetime(value: datetime | None) -> datetime | None:
    """Normalize SQLite's timezone-naive persisted UTC values for API evidence."""

    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
