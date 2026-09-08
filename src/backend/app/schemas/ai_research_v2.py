"""API contracts for the trusted AI research protocol v2."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_OPAQUE_OBJECT_RECEIPT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")


class ResearchHypothesisDraftRequest(BaseModel):
    """Create a server-owned v2 hypothesis draft."""

    payload: dict[str, Any] = Field(default_factory=dict)
    workspace_id: str | None = Field(default=None, max_length=36)
    source_mandate_id: str | None = Field(default=None, max_length=36)


class ResearchHypothesisRevisionRequest(BaseModel):
    """Revise a draft in place or fork a confirmed version."""

    payload: dict[str, Any] = Field(default_factory=dict)


class ResearchHypothesisConfirmRequest(BaseModel):
    """Bind an explicit UI confirmation to the current server content hash."""

    request_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class ResearchHypothesisResponse(BaseModel):
    """Safe owner-scoped representation of a v2 hypothesis version."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    hypothesis_id: str
    workspace_id: str | None = None
    version_no: int
    parent_version_id: str | None = None
    status: str
    canonical_payload: dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    source_mandate_id: str | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime


class ResearchDatasetCreateRequest(BaseModel):
    """Create an Explorer-visible snapshot from a server-issued object receipt.

    The client may name an opaque receipt that was registered by a trusted
    ingestion/control-plane service.  It must never supply a storage URI,
    object version, digest, or other object-identity assertion.
    """

    model_config = ConfigDict(extra="forbid")

    dataset_policy_version: str = Field(min_length=1, max_length=128)
    partition_kind: Literal["DISCOVERY", "ITERATION_VALIDATION"]
    instrument_manifest: dict[str, Any] = Field(default_factory=dict)
    split_manifest: dict[str, Any] = Field(default_factory=dict)
    source_manifest: dict[str, Any] = Field(default_factory=dict)
    execution_policy: dict[str, Any] = Field(default_factory=dict)
    point_in_time_cutoff: datetime
    object_receipt_id: str = Field(min_length=1, max_length=256)
    license_tags: list[str] = Field(min_length=1)

    @field_validator("object_receipt_id")
    @classmethod
    def require_opaque_object_receipt(cls, value: str) -> str:
        """Reject URI-shaped input instead of treating it as a receipt identifier."""

        if _OPAQUE_OBJECT_RECEIPT_ID.fullmatch(value) is None:
            raise ValueError("DATASET_OBJECT_RECEIPT_OPAQUE_ID_REQUIRED")
        return value


class ResearchDatasetResponse(BaseModel):
    """Safe data read model; storage location is deliberately omitted."""

    id: str
    dataset_policy_version: str
    partition_kind: str
    instrument_manifest: dict[str, Any] = Field(default_factory=dict)
    split_manifest: dict[str, Any] = Field(default_factory=dict)
    source_manifest: dict[str, Any] = Field(default_factory=dict)
    execution_policy: dict[str, Any] = Field(default_factory=dict)
    point_in_time_cutoff: datetime
    content_hash: str


class ResearchEpochCreateRequest(BaseModel):
    """Open a finite search epoch for one confirmed hypothesis."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_version_id: str = Field(min_length=1, max_length=36)
    search_budget: dict[str, Any] = Field(default_factory=dict)
    dataset_policy_version: str = Field(min_length=1, max_length=128)


class ResearchEpochResponse(BaseModel):
    """Owner-scoped bounded search epoch summary."""

    id: str
    hypothesis_version_id: str
    family_hash: str
    search_budget: dict[str, Any] = Field(default_factory=dict)
    dataset_policy_version: str
    holdout_budget: int
    status: str
    selected_candidate_id: str | None = None
    opened_at: datetime


class ResearchConfigProfileCreateRequest(BaseModel):
    """Create a user-scoped, secret-free protocol-v2 research profile."""

    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=10_000)
    config: dict[str, Any] = Field(default_factory=dict)
    workspace_id: str | None = Field(default=None, max_length=36)


class ResearchConfigProfileResponse(BaseModel):
    """Owner-scoped profile projection with credential references but no credentials."""

    id: str
    workspace_id: str | None = None
    name: str
    description: str
    config: dict[str, Any] = Field(default_factory=dict)
    credential_refs: dict[str, str] = Field(default_factory=dict)
    status: str
    created_at: datetime
    updated_at: datetime


class ResearchDataPrecheckRequest(BaseModel):
    """Build server-owned data and execution evidence for one launch request."""

    hypothesis_version_id: str = Field(min_length=1, max_length=36)
    dataset_snapshot_id: str = Field(min_length=1, max_length=36)
    experiment_epoch_id: str = Field(min_length=1, max_length=36)
    profile_id: str = Field(min_length=1, max_length=128)
    profile_version: str = Field(min_length=1, max_length=128)
    promotion_policy_version: str = Field(min_length=1, max_length=128)
    request_json: dict[str, Any] = Field(default_factory=dict)
    workspace_id: str | None = Field(default=None, max_length=36)
    ttl_seconds: int = Field(default=900, ge=1, le=3600)


class ResearchDataPrecheckResponse(BaseModel):
    """URI-free, immutable evidence receipt displayed before submission."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    hypothesis_version_id: str
    dataset_snapshot_id: str
    experiment_epoch_id: str
    profile_id: str
    profile_version: str
    promotion_policy_version: str
    input_hash: str
    evidence_hash: str
    status: Literal["PASS", "FAIL", "BLOCKED"]
    reason_code: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime
    expires_at: datetime


class ResearchRunSubmitRequest(BaseModel):
    """Submit a protocol-v2 run bound to confirmed immutable inputs."""

    hypothesis_version_id: str = Field(min_length=1, max_length=36)
    dataset_snapshot_id: str = Field(min_length=1, max_length=36)
    experiment_epoch_id: str = Field(min_length=1, max_length=36)
    profile_id: str = Field(min_length=1, max_length=128)
    profile_version: str = Field(min_length=1, max_length=128)
    promotion_policy_version: str = Field(min_length=1, max_length=128)
    request_json: dict[str, Any] = Field(default_factory=dict)
    precheck_id: str = Field(min_length=1, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)


class ResearchRunResponse(BaseModel):
    """Safe run state shown by the v2 evidence workbench."""

    id: str
    hypothesis_version_id: str
    dataset_snapshot_id: str | None = None
    data_precheck_id: str | None = None
    experiment_epoch_id: str | None = None
    protocol_version: str
    workflow_version: str
    status: str
    stage_cursor: str
    promotion_policy_version: str
    request_hash: str
    capability_profile_id: str
    capability_profile_version: str
    capability_evidence_hash: str
    trace_id: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ResearchTaskResponse(BaseModel):
    """Safe durable task state without raw request content or lease secret."""

    id: str
    run_id: str
    status: str
    stage_cursor: str
    error_code: str | None = None
    trace_id: str | None = None
    cancel_requested_at: datetime | None = None
    attempt_count: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ResearchTaskListResponse(BaseModel):
    """Cursor-paginated owner-scoped task summaries."""

    items: list[ResearchTaskResponse] = Field(default_factory=list)
    next_cursor: str | None = None


class ResearchTaskEventResponse(BaseModel):
    """Safe append-only task transition summary for polling clients."""

    id: str
    task_id: str
    run_id: str
    sequence_no: int
    event_type: str
    stage: str
    status: str
    error_code: str | None = None
    stage_attempt_id: str | None = None
    trace_id: str | None = None
    created_at: datetime


class ResearchTaskEventListResponse(BaseModel):
    """Cursor-paginated safe event stream with a resumable boundary."""

    items: list[ResearchTaskEventResponse] = Field(default_factory=list)
    next_cursor: str | None = None
    resume_cursor: str


class ResearchRunSubmissionResponse(BaseModel):
    """Idempotent v2 submit receipt."""

    run: ResearchRunResponse
    task: ResearchTaskResponse


class ResearchCandidateFreezeRequest(BaseModel):
    """Bind explicit human confirmation to the current candidate identity."""

    model_config = ConfigDict(extra="forbid")

    expected_candidate_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class ResearchCandidateResponse(BaseModel):
    """URI-free candidate identity; freezing is not an evaluation or approval."""

    id: str
    run_id: str
    experiment_epoch_id: str
    source_version_id: str | None = None
    dataset_snapshot_id: str
    code_artifact_id: str
    dependency_artifact_id: str
    candidate_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    environment_hash: str
    cost_model_hash: str
    params: dict[str, Any] = Field(default_factory=dict)
    freeze_status: Literal["MUTABLE", "FROZEN"]
    frozen_at: datetime | None = None


class ResearchHoldoutEvaluationRequest(BaseModel):
    """Ask the server to queue holdout work for one exact frozen candidate."""

    model_config = ConfigDict(extra="forbid")

    expected_candidate_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class ResearchHoldoutEvaluationCommandResponse(BaseModel):
    """Safe queued-command projection without sealed data or token material."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    status: Literal[
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
        "RECONCILING",
    ]
    stage: Literal["REQUEST_HOLDOUT", "HOLDOUT_PENDING"]
    candidate_id: str
    candidate_hash: str
    experiment_epoch_id: str
    dataset_snapshot_id: str
    policy_version: str
    evaluator_identity: str
    capability_profile_id: str
    capability_profile_version: str
    capability_evidence_hash: str
    error_code: str | None = None
    request_hash: str
    created_at: datetime
    updated_at: datetime


class ResearchModelInvocationSummary(BaseModel):
    """Safe model lineage displayed by the evidence workbench."""

    id: str
    provider: str
    requested_model: str
    resolved_model: str
    prompt_template_version: str
    token_usage: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    created_at: datetime


class ResearchEvaluationSummary(BaseModel):
    """Closed, metric-free evaluation identity suitable for browser recovery."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    experiment_epoch_id: str
    candidate_id: str
    dataset_snapshot_id: str
    evaluation_type: Literal["SEALED_HOLDOUT", "ITERATION_VALIDATION"]
    evaluator_identity: str
    evaluator_version: str
    policy_version: str
    status: Literal["PENDING", "RUNNING", "PASSED", "REJECTED", "FAILED", "EXPIRED"]
    completed_at: datetime | None = None


class ResearchEvidencePackageSummary(BaseModel):
    """Manifest identity only; the controlled manifest itself is not exported."""

    id: str
    candidate_id: str
    command_id: str | None = None
    evaluation_id: str | None = None
    promotion_policy_version: str
    gate_input_evidence_hash: str
    manifest_hash: str
    approval_binding_hash: str
    status: str
    created_at: datetime


class ResearchGovernanceDecisionSummary(BaseModel):
    """A visible limitation record that never changes the underlying gate outcome."""

    id: str
    target_requirement_or_gate: str
    original_status: Literal["FAIL", "BLOCKED", "NOT_RUN"]
    reason: str
    risk: str
    compensating_controls: list[str] = Field(default_factory=list)
    effective_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


class ResearchGovernanceDecisionCreateRequest(BaseModel):
    """Request one server-policy-approved deviation without changing any gate."""

    model_config = ConfigDict(extra="forbid")

    target_requirement_or_gate: str = Field(min_length=1, max_length=128)
    original_status: Literal["FAIL", "BLOCKED", "NOT_RUN"]
    reason: str = Field(min_length=1, max_length=10_000)
    risk: str = Field(min_length=1, max_length=10_000)
    compensating_controls: list[str] = Field(min_length=1, max_length=32)
    scope: dict[str, str] = Field(min_length=1, max_length=2)
    expires_at: datetime


class ResearchGovernanceDecisionResponse(ResearchGovernanceDecisionSummary):
    """Safe browser projection of one governance deviation."""


class ResearchApprovalRequestCreate(BaseModel):
    """Non-authoritative evidence references for a server-owned approval request."""

    model_config = ConfigDict(extra="forbid")

    gate_input_evidence_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    evidence_package_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class ResearchApprovalGrantIssueCreate(BaseModel):
    """Request a bounded run-scoped human approval grant."""

    model_config = ConfigDict(extra="forbid")

    subject_id: str = Field(min_length=1, max_length=36)
    ttl_seconds: int = Field(ge=1, le=86_400)


class ResearchApprovalGrantRevokeCreate(BaseModel):
    """Request the single permitted revocation transition for a grant."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=10_000)

    @field_validator("reason")
    @classmethod
    def require_nonempty_reason(cls, value: str) -> str:
        """Normalize the audit reason and reject whitespace-only values."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("APPROVAL_GRANT_REVOCATION_REASON_REQUIRED")
        return normalized


class ResearchApprovalGrantResponse(BaseModel):
    """Minimal grant receipt for the explicit high-authority management API."""

    model_config = ConfigDict(extra="forbid")

    id: str
    run_id: str
    workspace_id: str | None = None
    subject_id: str
    permission: Literal["research:approve"]
    status: Literal["ACTIVE", "EXPIRED", "REVOKED"]
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


class ResearchApprovalDecisionCreate(BaseModel):
    """Human decision content; identity, policy, mode, time, and grant stay server-owned."""

    model_config = ConfigDict(extra="forbid")

    approval_request_id: str = Field(min_length=1, max_length=36)
    decision: Literal["APPROVED", "REJECTED", "REQUESTED_CHANGES"]
    reason: str = Field(min_length=1, max_length=10_000)
    gate_input_evidence_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    evidence_package_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    challenge_responses: dict[str, str] = Field(default_factory=dict, max_length=32)
    residual_risk_acknowledgement: str | None = Field(default=None, max_length=10_000)

    @field_validator("reason")
    @classmethod
    def require_nonempty_reason(cls, value: str) -> str:
        """Normalize the persisted reason and reject whitespace-only decisions."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("APPROVAL_REASON_REQUIRED")
        return normalized

    @field_validator("challenge_responses")
    @classmethod
    def validate_challenge_responses(cls, value: dict[str, str]) -> dict[str, str]:
        """Bound challenge keys and content without treating either as authority."""

        if any(
            not key.strip() or len(key) > 128 or not isinstance(answer, str) or len(answer) > 10_000
            for key, answer in value.items()
        ):
            raise ValueError("APPROVAL_CHALLENGE_INVALID")
        return value


class ResearchApprovalContextResponse(BaseModel):
    """Safe server-derived approval capabilities without grant or actor internals."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    run_id: str
    candidate_id: str
    candidate_hash: str
    policy_version: str
    policy_material_hash: str
    approval_mode: Literal["single_actor", "multi_actor"]
    can_request: bool
    can_decide: bool
    can_approve: bool
    request_blocked_reason: str | None = None
    decision_blocked_reason: str | None = None
    cooldown_seconds: int = Field(ge=0)
    required_challenge_keys: list[str] = Field(default_factory=list)
    risk_acknowledgement_required: bool
    current_request: ResearchApprovalRequestResponse | None = None
    latest_decision: ResearchApprovalDecisionResponse | None = None
    machine_evidence_summary: ResearchApprovalMachineEvidenceSummary | None = None


class ResearchApprovalRequestResponse(BaseModel):
    """Safe request receipt with no requester identity or authority internals."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    run_id: str
    candidate_id: str
    evidence_package_id: str
    policy_version: str
    policy_material_hash: str
    approval_mode: Literal["single_actor", "multi_actor"]
    gate_input_evidence_hash: str
    evidence_package_hash: str
    request_material_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    status: Literal["PENDING", "DECIDED", "EXPIRED", "REVOKED"]
    requested_at: datetime
    eligible_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None


class ResearchApprovalDecisionResponse(BaseModel):
    """Safe immutable decision receipt without actor, grant, or permission details."""

    model_config = ConfigDict(extra="forbid")

    id: str
    run_id: str
    candidate_id: str
    approval_request_id: str
    decision: Literal["APPROVED", "REJECTED", "REQUESTED_CHANGES"]
    policy_version: str
    policy_material_hash: str
    approval_mode: Literal["single_actor", "multi_actor"]
    gate_input_evidence_hash: str
    evidence_package_hash: str
    decision_material_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    decision_intent_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    risk_acknowledgement: bool
    challenge_keys: list[str] = Field(default_factory=list)
    reason: str
    decided_at: datetime
    expires_at: datetime


class ResearchApprovalEvidencePackageSummary(BaseModel):
    """Closed active-package identity without raw manifest or sealed measurements."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    candidate_id: str
    status: Literal["ACTIVE"]
    promotion_policy_version: str
    command_id: str
    evaluation_id: str
    gate_input_evidence_hash: str
    manifest_hash: str
    approval_binding_hash: str


class ResearchApprovalGateSummary(BaseModel):
    """Allowlisted hard-gate evidence suitable for independent human review."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    gate_code: str
    status: Literal["PASS"]
    reason_code: str
    input_evidence_hash: str
    executor_version: str
    evaluated_at: datetime


class ResearchApprovalMachineEvidenceSummary(BaseModel):
    """Exactly thirteen revalidated gates bound to one active package."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    package: ResearchApprovalEvidencePackageSummary
    gates: list[ResearchApprovalGateSummary] = Field(min_length=13, max_length=13)


class ResearchHumanDecisionSummary(BaseModel):
    """Safe workbench row that labels legacy audit records separately from v2 authority."""

    model_config = ConfigDict(extra="forbid")

    authority_version: Literal["legacy", "v2"]
    id: str
    run_id: str | None = None
    candidate_id: str
    approval_request_id: str | None = None
    decision: Literal["APPROVED", "REJECTED", "REQUESTED_CHANGES"]
    policy_version: str
    policy_material_hash: str | None = None
    approval_mode: str
    gate_input_evidence_hash: str | None = None
    evidence_package_hash: str
    decision_material_hash: str | None = None
    decision_intent_hash: str | None = None
    risk_acknowledgement: bool
    challenge_keys: list[str] = Field(default_factory=list)
    reason: str = ""
    decided_at: datetime
    expires_at: datetime | None = None


class ResearchWorkbenchResponse(BaseModel):
    """Evidence-only view consumed by the trusted research workbench."""

    run: ResearchRunResponse
    task: ResearchTaskResponse | None = None
    hypothesis: dict[str, Any] | None = None
    dataset: ResearchDatasetResponse | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    holdout_commands: list[ResearchHoldoutEvaluationCommandResponse]
    ledger: list[dict[str, Any]] = Field(default_factory=list)
    model_invocations: list[ResearchModelInvocationSummary] = Field(default_factory=list)
    evaluations: list[ResearchEvaluationSummary] = Field(default_factory=list)
    gates: list[dict[str, Any]] = Field(default_factory=list)
    approval_requests: list[ResearchApprovalRequestResponse] = Field(default_factory=list)
    decisions: list[ResearchHumanDecisionSummary] = Field(default_factory=list)
    governance_decisions: list[ResearchGovernanceDecisionSummary] = Field(default_factory=list)
    evidence_packages: list[ResearchEvidencePackageSummary] = Field(default_factory=list)
    evidence_class: str
