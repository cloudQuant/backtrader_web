"""Restricted, append-only control plane for model-promotion projections."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import (
    AssetModelRegistry,
    AssetModelStatusEvent,
    AssetSignalPrediction,
)
from app.schemas.asset_research import (
    AssetAdminSignalCandidateResponse,
    AssetModelCardResponse,
    AssetModelScopeResponse,
    AssetModelStatusEventResponse,
    AssetModelStatusTransitionRequest,
    AssetModelStatusTransitionResponse,
    ResearchDecision,
)
from app.services.asset_research.promotion import (
    has_complete_t2_metrics,
    has_required_model_approvals,
    verified_promotion_scope,
)

_SYSTEM_CANDIDATE_OWNER_SCOPES = frozenset({"PUBLIC_SHADOW", "ADMIN_EVAL"})
_ALLOWED_STATUS_TRANSITIONS = {
    "DRAFT": frozenset({"SHADOW"}),
    "SHADOW": frozenset({"PROMOTED"}),
    "PROMOTED": frozenset({"SUSPENDED", "RETIRED"}),
    "SUSPENDED": frozenset({"SHADOW"}),
    "RETIRED": frozenset(),
}


class AssetModelGovernanceError(ValueError):
    """Stable model-governance error mapped at the restricted API boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive DATETIME reads and aware production reads."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AssetModelGovernanceService:
    """Expose verified model state without allowing scope/evidence mutation by HTTP."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_system_candidate(
        self, *, prediction_id: str
    ) -> AssetAdminSignalCandidateResponse:
        """Read only an unpublished system-shadow candidate for a privileged evaluator.

        User-owned prediction candidates remain private even when the caller has
        data-administration privileges.  The public, published-decision routes
        remain the only user-facing signal surface.
        """
        prediction = (
            await self.db.execute(
                select(AssetSignalPrediction).where(
                    AssetSignalPrediction.id == prediction_id,
                    AssetSignalPrediction.owner_scope.in_(_SYSTEM_CANDIDATE_OWNER_SCOPES),
                    AssetSignalPrediction.actionability == "RESEARCH_ONLY",
                )
            )
        ).scalar_one_or_none()
        if prediction is None:
            raise AssetModelGovernanceError("PREDICTION_CANDIDATE_NOT_FOUND")
        try:
            candidate = ResearchDecision.model_validate(prediction.candidate_decision_json)
        except ValidationError as exc:
            raise AssetModelGovernanceError("PREDICTION_CANDIDATE_INVALID") from exc
        return AssetAdminSignalCandidateResponse(
            prediction_id=prediction.id,
            owner_scope=prediction.owner_scope,
            asset_type=prediction.asset_type,
            canonical_id=prediction.canonical_id,
            as_of_at=prediction.as_of_at,
            horizon_code=prediction.horizon_code,
            candidate_decision=candidate,
        )

    async def list_model_scopes(
        self,
        *,
        asset_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[AssetModelScopeResponse]:
        """List current registry projections with a visible scope-verification result."""
        query = select(AssetModelRegistry).order_by(
            desc(AssetModelRegistry.created_at), desc(AssetModelRegistry.id)
        )
        if asset_type is not None:
            query = query.where(AssetModelRegistry.asset_type == asset_type)
        if status is not None:
            query = query.where(AssetModelRegistry.status == status)
        records = list((await self.db.execute(query.limit(max(1, min(limit, 100))))).scalars())
        return [self.model_scope_payload(record) for record in records]

    async def get_model_card(self, *, registry_id: str) -> AssetModelCardResponse | None:
        """Return a deterministic model-card projection for one registry row."""
        record = await self.db.get(AssetModelRegistry, registry_id)
        if record is None:
            return None
        metrics = record.metrics_json if isinstance(record.metrics_json, dict) else {}
        approvals = record.approval_set_json if isinstance(record.approval_set_json, dict) else {}
        quality_approval = approvals.get("model_quality")
        owner = "unassigned"
        if isinstance(quality_approval, dict):
            owner = str(quality_approval.get("owner") or owner)
        return AssetModelCardResponse(
            registry_id=record.id,
            model_name=record.model_version,
            head_spec_hash=record.head_spec_hash,
            owner=owner,
            evaluation_manifest_hash=str(
                metrics.get("all_attempts_manifest_hash") or "0" * 64
            ),
            model_card_hash=str(metrics.get("model_card_hash") or "0" * 64),
            limitations=[
                str(item) for item in metrics.get("limitations") or []
                if isinstance(item, str)
            ],
            failure_modes=[
                str(item) for item in metrics.get("failure_modes") or []
                if isinstance(item, str)
            ],
        )

    async def transition_model_scope(
        self,
        *,
        registry_id: str,
        actor_id: str,
        request: AssetModelStatusTransitionRequest,
    ) -> AssetModelStatusTransitionResponse:
        """Atomically update the status projection and append its immutable event.

        This endpoint deliberately cannot set model metrics, approvals, scope,
        evidence, or effective dates.  A ``SHADOW -> PROMOTED`` request only
        succeeds when those pre-existing registry facts already satisfy the
        exact T2 gate used at runtime.
        """
        normalized_actor_id = actor_id.strip()
        if not normalized_actor_id:
            raise AssetModelGovernanceError("MODEL_TRANSITION_ACTOR_INVALID")
        record = (
            await self.db.execute(
                select(AssetModelRegistry)
                .where(AssetModelRegistry.id == registry_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if record is None:
            raise AssetModelGovernanceError("MODEL_SCOPE_NOT_FOUND")

        from_status = record.status
        to_status = request.to_status
        if to_status not in _ALLOWED_STATUS_TRANSITIONS.get(from_status, frozenset()):
            raise AssetModelGovernanceError("MODEL_STATUS_TRANSITION_INVALID")
        if verified_promotion_scope(record) is None:
            raise AssetModelGovernanceError("MODEL_SCOPE_INVALID")

        if to_status == "PROMOTED":
            self._validate_promotion_transition(record, request=request)

        record.status = to_status
        event = AssetModelStatusEvent(
            model_registry_id=record.id,
            from_status=from_status,
            to_status=to_status,
            reason_codes_json=list(request.reason_codes),
            metrics_snapshot_json=deepcopy(record.metrics_json),
            evidence_uri=record.evidence_uri,
            evidence_content_hash=record.evidence_content_hash,
            actor_id=normalized_actor_id,
        )
        self.db.add(event)
        await self.db.flush()
        return AssetModelStatusTransitionResponse(
            model_scope=self.model_scope_payload(record),
            event=self.model_status_event_payload(event),
        )

    @staticmethod
    def model_scope_payload(record: AssetModelRegistry) -> AssetModelScopeResponse:
        """Serialize the full registry projection without silently repairing malformed scope JSON."""
        return AssetModelScopeResponse(
            registry_id=record.id,
            promotion_scope_key=record.promotion_scope_key,
            promotion_scope_type=record.promotion_scope_type,
            asset_type=record.asset_type,
            instrument_class=record.instrument_class,
            canonical_id_scope=record.canonical_id_scope,
            venue_scope=record.venue_scope,
            product_type_scope=record.product_type_scope,
            scope_parameters=record.scope_parameters_json,
            scope_verified=verified_promotion_scope(record) is not None,
            signal_head=record.signal_head,
            horizon_code=record.horizon_code,
            head_spec_hash=record.head_spec_hash,
            target_spec_version=record.target_spec_version,
            scoreability_rule_version=record.scoreability_rule_version,
            baseline_version=record.baseline_version,
            policy_version=record.policy_version,
            model_version=record.model_version,
            probability_artifact_hash=record.probability_artifact_hash,
            calibration_version=record.calibration_version,
            calibration_artifact_hash=record.calibration_artifact_hash,
            training_cutoff_at=record.training_cutoff_at,
            status=record.status,
            metrics=record.metrics_json,
            approvals=record.approval_set_json,
            evidence_uri=record.evidence_uri,
            evidence_content_hash=record.evidence_content_hash,
            approved_at=record.approved_at,
            effective_from=record.effective_from,
            effective_to=record.effective_to,
            created_at=record.created_at,
        )

    @staticmethod
    def model_status_event_payload(event: AssetModelStatusEvent) -> AssetModelStatusEventResponse:
        """Serialize one append-only status event without exposing mutable registry fields."""
        return AssetModelStatusEventResponse(
            event_id=event.id,
            registry_id=event.model_registry_id,
            from_status=event.from_status,
            to_status=event.to_status,
            reason_codes=list(event.reason_codes_json or []),
            metrics_snapshot=event.metrics_snapshot_json,
            evidence_uri=event.evidence_uri,
            evidence_content_hash=event.evidence_content_hash,
            actor_id=event.actor_id,
            created_at=event.created_at,
        )

    @staticmethod
    def _validate_promotion_transition(
        record: AssetModelRegistry, *, request: AssetModelStatusTransitionRequest
    ) -> None:
        """Require the same frozen scope, evidence and T2 proof as the publication gate."""
        if "COMMON.T2_GATE_PASSED" not in request.reason_codes:
            raise AssetModelGovernanceError("MODEL_PROMOTION_REASON_REQUIRED")
        now = _now()
        approved_at = record.approved_at or now
        if _as_utc(approved_at) > now:
            raise AssetModelGovernanceError("MODEL_PROMOTION_EVIDENCE_INCOMPLETE")
        if (
            record.effective_from is None
            or not has_required_model_approvals(record)
            or not has_complete_t2_metrics(record, approved_at=approved_at)
        ):
            raise AssetModelGovernanceError("MODEL_PROMOTION_EVIDENCE_INCOMPLETE")
        record.approved_at = approved_at
