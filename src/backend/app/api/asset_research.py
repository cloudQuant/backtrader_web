"""HTTP surface for canonical multi-asset research discovery and analysis."""

from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._dependencies import get_current_user
from app.api.data.deps import require_data_admin_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.asset_research import (
    ApprovedScheduleManifestCreateRequest,
    ApprovedScheduleManifestResponse,
    ApprovedScheduleManifestRetireRequest,
    AssetAdminSignalCandidateResponse,
    AssetAnalysisCreateRequest,
    AssetAnalysisExportCreateRequest,
    AssetAnalysisExportResponse,
    AssetAnalysisResultResponse,
    AssetAnalysisTaskResponse,
    AssetModelCardResponse,
    AssetModelScopeResponse,
    AssetModelStatusTransitionRequest,
    AssetModelStatusTransitionResponse,
    AssetReportPublicationCreateRequest,
    AssetReportPublicationResponse,
    AssetResearchReportResponse,
    AssetSignalEvidenceResponse,
    AssetSignalHistoryResponse,
    AssetSignalOutcomeResponse,
    AssetSignalRunResponse,
    AssetSignalScheduleCreateRequest,
    AssetSignalScheduleListResponse,
    AssetSignalScheduleResponse,
    AssetSignalScheduleUpdateRequest,
    AssetType,
    IdentityLevel,
    InstrumentIdentity,
    InstrumentResolveRequest,
    ModelStatus,
    PositionContextCreateRequest,
    PositionContextSnapshotResponse,
    PublicAssetType,
    SignalSummaryResponse,
    StockResearchCompatibilityHistoryResponse,
)
from app.schemas.auth import TokenPayload
from app.services.asset_research.artifacts import (
    AssetResearchArtifactError,
    AssetResearchReportArtifactsService,
)
from app.services.asset_research.data import DEFAULT_ASSET_RESEARCH_SOURCE_ID
from app.services.asset_research.identity import (
    InstrumentResolutionError,
    InstrumentResolver,
)
from app.services.asset_research.master_data import ApprovedInstrumentCatalog
from app.services.asset_research.model_governance import (
    AssetModelGovernanceError,
    AssetModelGovernanceService,
)
from app.services.asset_research.orchestrator import (
    AssetResearchOrchestrationError,
    AssetResearchOrchestrator,
)
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY
from app.services.asset_research.reports import render_markdown
from app.services.asset_research.source_registry import AssetSourceRegistryPolicy
from app.services.asset_research.stock_compat import StockResearchCompatibilityAdapter
from app.services.asset_research.task_runner import get_asset_research_task_runner
from app.services.stock_signal.service import StockSignalService

router = APIRouter()


def get_instrument_resolver(
    db: AsyncSession = Depends(get_db),
) -> InstrumentResolver:
    """Resolve only an approved, versioned master identity from the database."""
    return InstrumentResolver(ApprovedInstrumentCatalog(db))


def get_asset_research_orchestrator(
    db: AsyncSession = Depends(get_db),
) -> AssetResearchOrchestrator:
    """Construct a request-scoped persistence/orchestration service."""
    return AssetResearchOrchestrator(db)


def get_asset_research_artifacts(
    db: AsyncSession = Depends(get_db),
) -> AssetResearchReportArtifactsService:
    """Construct a request-scoped public-report export/publication service."""
    return AssetResearchReportArtifactsService(db)


def get_asset_model_governance(
    db: AsyncSession = Depends(get_db),
) -> AssetModelGovernanceService:
    """Construct the restricted model-governance control plane for one request."""
    return AssetModelGovernanceService(db)


@router.get("/capabilities", response_model=None)
async def get_capabilities(
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> dict[str, object]:
    """Expose the server-owned asset capabilities without any execution permission."""
    del current_user
    enabled_asset_types = await AssetSourceRegistryPolicy(db).enabled_asset_types(
        source_ids=(DEFAULT_ASSET_RESEARCH_SOURCE_ID,)
    )
    catalog_asset_types = await ApprovedInstrumentCatalog(db).active_asset_types()
    return {
        "capability_version": AssetResearchOrchestrator.CAPABILITY_VERSION,
        "execution_disabled": True,
        "asset_types": [
            {
                "asset_type": plugin.asset_type,
                "source_capability_enabled": plugin.asset_type in enabled_asset_types,
                "instrument_catalog_ready": plugin.asset_type in catalog_asset_types,
                "research_enabled": (
                    plugin.asset_type in enabled_asset_types
                    and plugin.asset_type in catalog_asset_types
                ),
                "availability_reason": (
                    None
                    if (
                        plugin.asset_type in enabled_asset_types
                        and plugin.asset_type in catalog_asset_types
                    )
                    else (
                        "SOURCE_CAPABILITY_UNAVAILABLE"
                        if plugin.asset_type not in enabled_asset_types
                        else "INSTRUMENT_CATALOG_UNAVAILABLE"
                    )
                ),
                "short_open_research_allowed": False,
                "reason_codes": list(plugin.reason_codes),
            }
            for plugin in DEFAULT_ASSET_RESEARCH_REGISTRY.plugins()
        ],
    }


@router.get("/stock-compat/signals", response_model=StockResearchCompatibilityHistoryResponse)
async def get_stock_compatibility_history(
    symbol: str = Query(..., min_length=1, max_length=32),
    source: str | None = Query(None, max_length=32),
    limit: int = Query(30, ge=1, le=100),
    cursor: str | None = Query(None, max_length=64),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StockResearchCompatibilityHistoryResponse:
    """Expose a read-only, explicitly lossy bridge to legacy stock signals."""
    return await StockResearchCompatibilityAdapter(StockSignalService(db)).get_visible_history(
        user_id=current_user.sub,
        symbol=symbol,
        source=source,
        limit=limit,
        cursor=cursor,
    )


@router.get("/admin/stock-compat/reconcile", response_model=None)
async def reconcile_stock_compatibility(
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(require_data_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Run one bounded structured compatibility audit for legacy system signals."""
    del current_user
    summary = await StockResearchCompatibilityAdapter(StockSignalService(db)).reconcile_system(
        limit=limit,
    )
    return {
        "mapping_version": summary.mapping_version,
        "defect_count": summary.defect_count,
        "has_unsupported_defect": summary.has_unsupported_defect,
        "rows": [
            {
                "classification": row.classification,
                "legacy_reference": row.legacy_reference,
                "reason": row.reason,
            }
            for row in summary.rows
        ],
    }


@router.get("/instruments/search", response_model=None)
async def search_instruments(
    asset_type: PublicAssetType = Query(...),
    query: str = Query(..., min_length=1, max_length=128),
    identity_level: IdentityLevel | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    current_user: TokenPayload = Depends(get_current_user),
    resolver: InstrumentResolver = Depends(get_instrument_resolver),
) -> dict[str, object]:
    """Return candidates only; users must explicitly resolve one before analysis."""
    del current_user
    return {
        "asset_type": asset_type,
        "items": await resolver.search(
            asset_type=asset_type,
            query=query,
            identity_level=identity_level,
            limit=limit,
        ),
    }


@router.post("/instruments/resolve", response_model=InstrumentIdentity)
async def resolve_instrument(
    payload: InstrumentResolveRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
    resolver: InstrumentResolver = Depends(get_instrument_resolver),
) -> InstrumentIdentity:
    """Confirm and persist one exact identity version before a task can reference it."""
    del current_user
    try:
        identity = await resolver.resolve(payload)
    except InstrumentResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error_code": exc.code},
        ) from exc
    await service.persist_identity(identity)
    await service.db.commit()
    return identity


@router.post(
    "/position-contexts",
    status_code=status.HTTP_201_CREATED,
    response_model=PositionContextSnapshotResponse,
)
async def create_position_context(
    payload: PositionContextCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> PositionContextSnapshotResponse:
    """Store a declared research context without reading or connecting an account."""
    try:
        snapshot = await service.create_position_context(
            user_id=current_user.sub,
            request=payload,
            idempotency_key=idempotency_key,
        )
    except AssetResearchOrchestrationError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
                if exc.code == "IDEMPOTENCY_CONFLICT"
                else status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail={"error_code": exc.code},
        ) from exc
    await service.db.commit()
    response = await service.get_position_context(user_id=current_user.sub, snapshot_id=snapshot.id)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="POSITION_CONTEXT_NOT_FOUND"
        )
    return response


@router.get("/position-contexts/{snapshot_id}", response_model=PositionContextSnapshotResponse)
async def get_position_context(
    snapshot_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> PositionContextSnapshotResponse:
    """Read only the authenticated owner's immutable context metadata."""
    response = await service.get_position_context(user_id=current_user.sub, snapshot_id=snapshot_id)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="POSITION_CONTEXT_NOT_FOUND"
        )
    return response


def _asset_research_http_error(exc: AssetResearchOrchestrationError) -> HTTPException:
    """Map stable service errors without exposing database/provider internals."""
    if exc.code in {"TASK_NOT_FOUND", "SCHEDULE_NOT_FOUND", "SCHEDULE_MANIFEST_NOT_FOUND"}:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": exc.code})
    if exc.code in {
        "IDEMPOTENCY_CONFLICT",
        "SCHEDULE_MANIFEST_VERSION_CONFLICT",
        "SCHEDULE_MANIFEST_ACTIVE_EXISTS",
        "SCHEDULE_MANIFEST_TARGET_ACTIVE",
        "SCHEDULE_MANIFEST_LEASE_ACTIVE",
        "SCHEDULE_MANIFEST_RETRY_PENDING",
    }:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error_code": exc.code})
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error_code": exc.code},
    )


def _artifact_http_error(exc: AssetResearchArtifactError) -> HTTPException:
    if exc.code in {"REPORT_NOT_FOUND", "PUBLICATION_TARGET_NOT_FOUND"}:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": exc.code})
    if exc.code == "IDEMPOTENCY_CONFLICT":
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error_code": exc.code})
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error_code": exc.code},
    )


def _model_governance_http_error(exc: AssetModelGovernanceError) -> HTTPException:
    """Map restricted control-plane failures without exposing database details."""
    if exc.code in {"MODEL_SCOPE_NOT_FOUND", "PREDICTION_CANDIDATE_NOT_FOUND"}:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": exc.code})
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error_code": exc.code},
    )


def _report_response(
    report: object, artifacts: AssetResearchReportArtifactsService
) -> AssetResearchReportResponse:
    """Serialize a report from public fields only, even if a legacy row is malformed."""
    payload = artifacts.public_report_payload(report)  # type: ignore[arg-type]
    return AssetResearchReportResponse(
        report_id=report.id,  # type: ignore[attr-defined]
        task_id=report.task_id,  # type: ignore[attr-defined]
        prediction_id=report.prediction_id,  # type: ignore[attr-defined]
        report=payload,
        rendered_markdown=render_markdown(payload),
        content_hash=report.content_hash,  # type: ignore[attr-defined]
        created_at=report.created_at,  # type: ignore[attr-defined]
    )


def _export_response(export: object) -> AssetAnalysisExportResponse:
    """Return only the caller-authorized download route, never a storage path."""
    status_value = export.status  # type: ignore[attr-defined]
    return AssetAnalysisExportResponse(
        export_id=export.id,  # type: ignore[attr-defined]
        report_id=export.report_id,  # type: ignore[attr-defined]
        format=export.format,  # type: ignore[attr-defined]
        status=status_value,
        content_hash=export.content_hash,  # type: ignore[attr-defined]
        error_code=export.error_code,  # type: ignore[attr-defined]
        download_url=(
            f"/api/v1/asset-research/exports/{export.id}/download"  # type: ignore[attr-defined]
            if status_value == "SUCCEEDED"
            else None
        ),
        created_at=export.created_at,  # type: ignore[attr-defined]
        completed_at=export.completed_at,  # type: ignore[attr-defined]
    )


def _publication_response(publication: object) -> AssetReportPublicationResponse:
    return AssetReportPublicationResponse(
        publication_id=publication.id,  # type: ignore[attr-defined]
        report_id=publication.report_id,  # type: ignore[attr-defined]
        target_type=publication.target_type,  # type: ignore[attr-defined]
        target_ref=publication.target_ref,  # type: ignore[attr-defined]
        status=publication.status,  # type: ignore[attr-defined]
        external_ref=publication.external_ref,  # type: ignore[attr-defined]
        content_hash=publication.content_hash,  # type: ignore[attr-defined]
        error_code=publication.error_code,  # type: ignore[attr-defined]
        created_at=publication.created_at,  # type: ignore[attr-defined]
        completed_at=publication.completed_at,  # type: ignore[attr-defined]
    )


@router.post(
    "/schedules",
    status_code=status.HTTP_201_CREATED,
    response_model=AssetSignalScheduleResponse,
)
async def create_schedule(
    payload: AssetSignalScheduleCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetSignalScheduleResponse:
    """Create a confirmed single-asset shadow schedule with UNKNOWN position context."""
    try:
        schedule = await service.create_schedule(
            user_id=current_user.sub,
            request=payload,
            idempotency_key=idempotency_key,
        )
    except AssetResearchOrchestrationError as exc:
        raise _asset_research_http_error(exc) from exc
    await service.db.commit()
    return service.schedule_payload(schedule)


@router.get("/schedules", response_model=AssetSignalScheduleListResponse)
async def list_schedules(
    limit: int = Query(50, ge=1, le=100),
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetSignalScheduleListResponse:
    """List only the caller's future shadow schedules."""
    schedules = await service.list_schedules(user_id=current_user.sub, limit=limit)
    return AssetSignalScheduleListResponse(
        items=[service.schedule_payload(item) for item in schedules]
    )


@router.post(
    "/admin/schedule-manifests",
    status_code=status.HTTP_201_CREATED,
    response_model=ApprovedScheduleManifestResponse,
)
async def create_approved_schedule_manifest(
    payload: ApprovedScheduleManifestCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(require_data_admin_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> ApprovedScheduleManifestResponse:
    """Admin-only expansion of approved static entries into exact system schedules."""
    try:
        manifest = await service.create_approved_schedule_manifest(
            actor_id=str(current_user.id),
            request=payload,
            idempotency_key=idempotency_key,
        )
    except AssetResearchOrchestrationError as exc:
        raise _asset_research_http_error(exc) from exc
    await service.db.commit()
    return await service.schedule_manifest_payload(manifest)


@router.get("/admin/schedule-manifests", response_model=list[ApprovedScheduleManifestResponse])
async def list_approved_schedule_manifests(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_data_admin_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> list[ApprovedScheduleManifestResponse]:
    """Admin-only list of configuration evidence and persisted exact entries."""
    del current_user
    manifests = await service.list_approved_schedule_manifests(limit=limit)
    return [await service.schedule_manifest_payload(manifest) for manifest in manifests]


@router.get(
    "/admin/schedule-manifests/{manifest_id}",
    response_model=ApprovedScheduleManifestResponse,
)
async def get_approved_schedule_manifest(
    manifest_id: str,
    current_user: User = Depends(require_data_admin_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> ApprovedScheduleManifestResponse:
    """Admin-only retrieval of a static-manifest audit record."""
    del current_user
    manifest = await service.get_approved_schedule_manifest(manifest_id=manifest_id)
    if manifest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "SCHEDULE_MANIFEST_NOT_FOUND"},
        )
    return await service.schedule_manifest_payload(manifest)


@router.post(
    "/admin/schedule-manifests/{manifest_id}/retire",
    response_model=ApprovedScheduleManifestResponse,
)
async def retire_approved_schedule_manifest(
    manifest_id: str,
    payload: ApprovedScheduleManifestRetireRequest,
    current_user: User = Depends(require_data_admin_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> ApprovedScheduleManifestResponse:
    """Disable future system fires while retaining immutable audit history."""
    try:
        manifest = await service.retire_approved_schedule_manifest(
            actor_id=str(current_user.id),
            manifest_id=manifest_id,
            reason_codes=payload.reason_codes,
        )
    except AssetResearchOrchestrationError as exc:
        raise _asset_research_http_error(exc) from exc
    await service.db.commit()
    return await service.schedule_manifest_payload(manifest)


@router.patch("/schedules/{schedule_id}", response_model=AssetSignalScheduleResponse)
async def update_schedule(
    schedule_id: str,
    payload: AssetSignalScheduleUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetSignalScheduleResponse:
    """Version future configuration; historical run snapshots stay immutable."""
    try:
        schedule = await service.update_schedule(
            user_id=current_user.sub,
            schedule_id=schedule_id,
            request=payload,
        )
    except AssetResearchOrchestrationError as exc:
        raise _asset_research_http_error(exc) from exc
    await service.db.commit()
    return service.schedule_payload(schedule)


@router.post(
    "/schedules/{schedule_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AssetSignalRunResponse,
)
async def run_schedule(
    schedule_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetSignalRunResponse:
    """Manually trigger one idempotent shadow run; it neither creates orders nor an account link."""
    try:
        run = await service.run_schedule(user_id=current_user.sub, schedule_id=schedule_id)
    except AssetResearchOrchestrationError as exc:
        raise _asset_research_http_error(exc) from exc
    await service.db.commit()
    return service.run_payload(run)


@router.get(
    "/admin/signals/{prediction_id}/candidate",
    response_model=AssetAdminSignalCandidateResponse,
)
async def get_admin_signal_candidate(
    prediction_id: str,
    current_user: User = Depends(require_data_admin_user),
    service: AssetModelGovernanceService = Depends(get_asset_model_governance),
) -> AssetAdminSignalCandidateResponse:
    """Read a restricted system-shadow candidate without expanding user data access."""
    del current_user
    try:
        return await service.get_system_candidate(prediction_id=prediction_id)
    except AssetModelGovernanceError as exc:
        raise _model_governance_http_error(exc) from exc


@router.get("/admin/model-scopes", response_model=list[AssetModelScopeResponse])
async def list_admin_model_scopes(
    asset_type: AssetType | None = Query(default=None),
    status_filter: ModelStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_data_admin_user),
    service: AssetModelGovernanceService = Depends(get_asset_model_governance),
) -> list[AssetModelScopeResponse]:
    """Read model scope, frozen evidence and scope-verification state for an admin."""
    del current_user
    return await service.list_model_scopes(
        asset_type=asset_type,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/admin/model-cards/{registry_id}",
    response_model=AssetModelCardResponse,
)
async def get_admin_model_card(
    registry_id: str,
    current_user: User = Depends(require_data_admin_user),
    service: AssetModelGovernanceService = Depends(get_asset_model_governance),
) -> AssetModelCardResponse:
    """Read the deterministic model-card projection for one evidence-backed scope."""
    del current_user
    card = await service.get_model_card(registry_id=registry_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "MODEL_SCOPE_NOT_FOUND"},
        )
    return card


@router.post(
    "/admin/model-scopes/{registry_id}/transitions",
    response_model=AssetModelStatusTransitionResponse,
)
async def transition_admin_model_scope(
    registry_id: str,
    payload: AssetModelStatusTransitionRequest,
    current_user: User = Depends(require_data_admin_user),
    service: AssetModelGovernanceService = Depends(get_asset_model_governance),
) -> AssetModelStatusTransitionResponse:
    """Append one audited status event; scope, metrics and evidence cannot be overwritten."""
    try:
        response = await service.transition_model_scope(
            registry_id=registry_id,
            actor_id=str(current_user.id),
            request=payload,
        )
    except AssetModelGovernanceError as exc:
        raise _model_governance_http_error(exc) from exc
    await service.db.commit()
    return response


@router.get("/signals", response_model=AssetSignalHistoryResponse)
async def get_signal_history(
    asset_type: PublicAssetType = Query(...),
    canonical_id: str = Query(..., min_length=3, max_length=512),
    limit: int = Query(30, ge=1, le=100),
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetSignalHistoryResponse:
    """List the caller's own and published public-shadow immutable predictions."""
    return await service.get_signal_history(
        user_id=current_user.sub,
        asset_type=asset_type,
        canonical_id=canonical_id,
        limit=limit,
    )


@router.get("/signals/summary", response_model=SignalSummaryResponse)
async def get_signal_summary(
    asset_type: PublicAssetType = Query(...),
    canonical_id: str = Query(..., min_length=3, max_length=512),
    head_spec_hash: str | None = Query(default=None, pattern=r"^[0-9a-f]{64}$"),
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> SignalSummaryResponse:
    """Return explicit scorecard denominators instead of an unqualified success rate."""
    try:
        return await service.get_signal_summary(
            user_id=current_user.sub,
            asset_type=asset_type,
            canonical_id=canonical_id,
            head_spec_hash=head_spec_hash,
        )
    except AssetResearchOrchestrationError as exc:
        raise _asset_research_http_error(exc) from exc


@router.get("/signals/{prediction_id}/evidence", response_model=AssetSignalEvidenceResponse)
async def get_signal_evidence(
    prediction_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetSignalEvidenceResponse:
    """Read a redacted evidence manifest for an owned published prediction."""
    evidence = await service.get_signal_evidence(
        user_id=current_user.sub, prediction_id=prediction_id
    )
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PREDICTION_NOT_FOUND")
    return AssetSignalEvidenceResponse.model_validate(evidence)


@router.get("/signals/{prediction_id}/outcomes", response_model=list[AssetSignalOutcomeResponse])
async def get_signal_outcomes(
    prediction_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> list[AssetSignalOutcomeResponse]:
    """Read existing outcome records only; this endpoint never re-scores a prediction."""
    outcomes = await service.get_signal_outcomes(
        user_id=current_user.sub, prediction_id=prediction_id
    )
    if outcomes is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PREDICTION_NOT_FOUND")
    return outcomes


@router.post(
    "/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AssetAnalysisTaskResponse,
)
async def create_analysis_task(
    payload: AssetAnalysisCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetAnalysisTaskResponse:
    """Queue analysis after a prior exact identity confirmation; never place an order."""
    try:
        task = await service.create_pending(
            user_id=current_user.sub,
            request=payload,
            idempotency_key=idempotency_key,
        )
    except AssetResearchOrchestrationError as exc:
        raise _asset_research_http_error(exc) from exc
    await service.db.commit()
    response = await service.get_task(user_id=current_user.sub, task_id=task.id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TASK_NOT_FOUND")
    get_asset_research_task_runner().wake()
    return response


@router.get("/tasks/{task_id}", response_model=AssetAnalysisTaskResponse)
async def get_analysis_task(
    task_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetAnalysisTaskResponse:
    """Read a task only inside the authenticated user's owner scope."""
    response = await service.get_task(user_id=current_user.sub, task_id=task_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TASK_NOT_FOUND")
    return response


@router.get("/tasks/{task_id}/result", response_model=AssetAnalysisResultResponse)
async def get_analysis_result(
    task_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetAnalysisResultResponse:
    """Return only a published decision and report, never a shadow candidate."""
    response = await service.get_result(user_id=current_user.sub, task_id=task_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TASK_NOT_FOUND")
    return response


@router.post("/tasks/{task_id}/cancel", response_model=AssetAnalysisTaskResponse)
async def cancel_analysis_task(
    task_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetAnalysisTaskResponse:
    """Cancel a queued/running research lifecycle only; no external action exists."""
    response = await service.cancel_task(user_id=current_user.sub, task_id=task_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TASK_NOT_FOUND")
    await service.db.commit()
    return response


@router.post(
    "/tasks/{task_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AssetAnalysisTaskResponse,
)
async def retry_analysis_task(
    task_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: AssetResearchOrchestrator = Depends(get_asset_research_orchestrator),
) -> AssetAnalysisTaskResponse:
    """Create a new queued task; completed records remain immutable."""
    try:
        task = await service.retry_task(user_id=current_user.sub, task_id=task_id)
    except AssetResearchOrchestrationError as exc:
        raise _asset_research_http_error(exc) from exc
    await service.db.commit()
    response = await service.get_task(user_id=current_user.sub, task_id=task.id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TASK_NOT_FOUND")
    get_asset_research_task_runner().wake()
    return response


@router.get("/reports/latest", response_model=AssetResearchReportResponse | None)
async def get_latest_report(
    asset_type: PublicAssetType = Query(...),
    canonical_id: str = Query(..., min_length=3, max_length=512),
    current_user: TokenPayload = Depends(get_current_user),
    artifacts: AssetResearchReportArtifactsService = Depends(get_asset_research_artifacts),
) -> AssetResearchReportResponse | None:
    """Return the caller's newest public report for one canonical identity."""
    report = await artifacts.get_latest_report(
        user_id=current_user.sub,
        asset_type=asset_type,
        canonical_id=canonical_id,
    )
    return _report_response(report, artifacts) if report is not None else None


@router.get("/reports/{report_id}", response_model=AssetResearchReportResponse)
async def get_report(
    report_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    artifacts: AssetResearchReportArtifactsService = Depends(get_asset_research_artifacts),
) -> AssetResearchReportResponse:
    """Read a public report only inside the task owner's scope."""
    report = await artifacts.get_report(user_id=current_user.sub, report_id=report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="REPORT_NOT_FOUND")
    return _report_response(report, artifacts)


@router.post(
    "/reports/{report_id}/exports",
    status_code=status.HTTP_201_CREATED,
    response_model=AssetAnalysisExportResponse,
)
async def create_report_export(
    report_id: str,
    payload: AssetAnalysisExportCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: TokenPayload = Depends(get_current_user),
    artifacts: AssetResearchReportArtifactsService = Depends(get_asset_research_artifacts),
) -> AssetAnalysisExportResponse:
    """Create an auditable Markdown/PDF export from the public report only."""
    try:
        export = await artifacts.request_export(
            user_id=current_user.sub,
            report_id=report_id,
            export_format=payload.format,
            idempotency_key=idempotency_key,
        )
    except AssetResearchArtifactError as exc:
        raise _artifact_http_error(exc) from exc
    await artifacts.db.commit()
    return _export_response(export)


@router.get("/exports/{export_id}", response_model=AssetAnalysisExportResponse)
async def get_report_export(
    export_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    artifacts: AssetResearchReportArtifactsService = Depends(get_asset_research_artifacts),
) -> AssetAnalysisExportResponse:
    """Return export status and an authorized download route without a write side effect."""
    export = await artifacts.get_export(user_id=current_user.sub, export_id=export_id)
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EXPORT_NOT_FOUND")
    return _export_response(export)


@router.get("/exports/{export_id}/download", response_model=None)
async def download_report_export(
    export_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    artifacts: AssetResearchReportArtifactsService = Depends(get_asset_research_artifacts),
) -> StreamingResponse:
    """Download an already-created authorized artifact; never regenerate it on GET."""
    result = await artifacts.read_export(user_id=current_user.sub, export_id=export_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EXPORT_NOT_FOUND")
    export, content = result
    media_type = (
        "text/markdown; charset=utf-8" if export.format == "MARKDOWN" else "application/pdf"
    )
    extension = "md" if export.format == "MARKDOWN" else "pdf"
    return StreamingResponse(
        BytesIO(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="asset-research-{export.id}.{extension}"'
        },
    )


@router.post(
    "/reports/{report_id}/publications",
    status_code=status.HTTP_201_CREATED,
    response_model=AssetReportPublicationResponse,
)
async def publish_report(
    report_id: str,
    payload: AssetReportPublicationCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: TokenPayload = Depends(get_current_user),
    artifacts: AssetResearchReportArtifactsService = Depends(get_asset_research_artifacts),
) -> AssetReportPublicationResponse:
    """Save the public report to a caller-owned knowledge base or research workspace."""
    try:
        publication = await artifacts.publish(
            user_id=current_user.sub,
            report_id=report_id,
            target_type=payload.target_type,
            target_ref=payload.target_ref,
            title=payload.title,
            idempotency_key=idempotency_key,
        )
    except AssetResearchArtifactError as exc:
        raise _artifact_http_error(exc) from exc
    await artifacts.db.commit()
    return _publication_response(publication)


@router.get("/publications/{publication_id}", response_model=AssetReportPublicationResponse)
async def get_report_publication(
    publication_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    artifacts: AssetResearchReportArtifactsService = Depends(get_asset_research_artifacts),
) -> AssetReportPublicationResponse:
    """Read publication audit status without external credentials or candidate data."""
    publication = await artifacts.get_publication(
        user_id=current_user.sub,
        publication_id=publication_id,
    )
    if publication is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PUBLICATION_NOT_FOUND")
    return _publication_response(publication)
