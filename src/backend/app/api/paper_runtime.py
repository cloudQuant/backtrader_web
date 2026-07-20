"""Workspace paper-runtime detail, equity, review, alert, and risk-rule APIs."""

from __future__ import annotations

import typing
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.models.paper_runtime import RiskRule
from app.schemas.paper_runtime import (
    LiveHandoffDecisionRequest,
    PaperEquityCurveResponse,
    PaperEquitySnapshotCreate,
    PaperEquitySnapshotResponse,
    PaperRuntimeAlertResponse,
    PaperRuntimePreOrderRiskRequest,
    PaperRuntimePreOrderRiskResponse,
    PaperRuntimeResponse,
    PaperRuntimeReviewRequest,
    RiskRuleCreate,
    RiskRuleResponse,
    RiskRuleUpdate,
)
from app.services.paper_runtime_service import PaperRuntimeService

router = APIRouter()

_PUBLIC_RUNTIME_ROW_FIELDS = {
    "positions": {
        "data_name",
        "symbol",
        "direction",
        "size",
        "price",
        "current_price",
        "market_value",
        "margin_value",
        "pnl",
        "pnlcomm",
        "position_pnl",
        "updated_at",
        "data_time",
        "source",
        "valuation_status",
    },
    "orders": {
        "id",
        "order_id",
        "symbol",
        "data_name",
        "side",
        "direction",
        "status",
        "size",
        "filled_size",
        "price",
        "average_price",
        "value",
        "created_at",
        "updated_at",
    },
    "trades": {
        "id",
        "trade_id",
        "symbol",
        "data_name",
        "direction",
        "size",
        "price",
        "value",
        "commission",
        "pnl",
        "pnlcomm",
        "datetime",
        "dtopen",
        "dtclose",
    },
    "signals": {"id", "symbol", "data_name", "side", "direction", "signal", "price", "datetime"},
}


def get_paper_runtime_service() -> PaperRuntimeService:
    """Provide the workspace paper-runtime service."""
    return PaperRuntimeService()


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper runtime not found")


def _snapshot_response(snapshot: typing.Any) -> PaperEquitySnapshotResponse:
    return PaperEquitySnapshotResponse(
        id=snapshot.id,
        observed_at=snapshot.observed_at,
        source=snapshot.source,
        total_equity=snapshot.total_equity,
        cash=snapshot.cash,
        position_value=snapshot.position_value,
        unrealized_pnl=snapshot.unrealized_pnl,
        realized_pnl=snapshot.realized_pnl,
    )


def _public_runtime_rows(snapshot: typing.Any, key: str) -> list[dict[str, typing.Any]]:
    """Return allowlisted snapshot rows; runner metadata can contain sensitive config."""
    values = snapshot.get(key) if isinstance(snapshot, dict) else None
    if not isinstance(values, list):
        return []
    allowed = _PUBLIC_RUNTIME_ROW_FIELDS[key]
    return [
        {field: row[field] for field in allowed if field in row}
        for row in values
        if isinstance(row, dict)
    ]


@router.get(
    "/{instance_id}", response_model=PaperRuntimeResponse, summary="Get paper runtime detail"
)
async def get_paper_runtime(
    instance_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> PaperRuntimeResponse:
    """Return an owned workspace runtime without exposing account-engine identifiers."""
    runtime = await service.get_runtime(current_user.sub, instance_id)
    if runtime is None:
        raise _not_found()
    workspace, unit = runtime
    latest = await service.latest_snapshot(current_user.sub, instance_id)
    trading_snapshot = dict(unit.trading_snapshot or {})
    return PaperRuntimeResponse(
        instance_id=instance_id,
        workspace_id=workspace.id,
        unit_id=unit.id,
        workspace_name=workspace.name,
        unit_name=unit.strategy_name or unit.id,
        symbol=unit.symbol or "",
        status=unit.run_status or "idle",
        paused=bool(unit.lock_running),
        positions=_public_runtime_rows(trading_snapshot, "positions"),
        orders=_public_runtime_rows(trading_snapshot, "orders"),
        trades=_public_runtime_rows(trading_snapshot, "trades"),
        signals=_public_runtime_rows(trading_snapshot, "signals"),
        latest_equity=_snapshot_response(latest) if latest is not None else None,
    )


@router.get(
    "/{instance_id}/equity",
    response_model=PaperEquityCurveResponse,
    summary="Get paper equity curve",
)
async def get_paper_equity_curve(
    instance_id: str,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    max_points: int = Query(1000, ge=1, le=1000),
    cursor: str | None = None,
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> PaperEquityCurveResponse:
    """List UTC snapshots with deterministic down-sampling and empty-data semantics."""
    try:
        page = await service.list_snapshot_page(
            current_user.sub,
            instance_id,
            start_at=start_at,
            end_at=end_at,
            max_points=max_points,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if page is None:
        raise _not_found()
    return PaperEquityCurveResponse(
        instance_id=instance_id,
        points=[_snapshot_response(point) for point in page.points],
        next_cursor=page.next_cursor,
        sampled=page.sampled,
        sampling=page.sampling,
    )


@router.post(
    "/{instance_id}/equity",
    response_model=PaperEquitySnapshotResponse,
    summary="Record paper equity snapshot",
)
async def record_paper_equity_snapshot(
    instance_id: str,
    request: PaperEquitySnapshotCreate,
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> PaperEquitySnapshotResponse:
    """Record a retry-safe snapshot for the current user's canonical runtime."""
    snapshot = await service.record_snapshot(
        current_user.sub,
        instance_id,
        request.model_dump(),
    )
    if snapshot is None:
        raise _not_found()
    return _snapshot_response(snapshot)


@router.get(
    "/{instance_id}/alerts",
    response_model=list[PaperRuntimeAlertResponse],
    summary="List paper runtime alerts",
)
async def list_paper_runtime_alerts(
    instance_id: str,
    limit: int = Query(100, ge=1, le=500),
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> list[PaperRuntimeAlertResponse]:
    """List durable, scoped alerts for one runtime."""
    alerts = await service.list_alerts(current_user.sub, instance_id, limit)
    if alerts is None:
        raise _not_found()
    return [
        PaperRuntimeAlertResponse(
            id=alert.id,
            alert_type=alert.alert_type,
            severity=alert.severity,
            status=alert.status,
            title=alert.title,
            message=alert.message,
            instance_id=alert.instance_id,
            workspace_id=alert.workspace_id,
            unit_id=alert.unit_id,
            created_at=alert.created_at,
        )
        for alert in alerts
    ]


@router.post(
    "/{instance_id}/pre-order-check",
    response_model=PaperRuntimePreOrderRiskResponse,
    summary="Evaluate paper runtime risk before order submission",
)
async def check_paper_runtime_pre_order_risk(
    instance_id: str,
    request: PaperRuntimePreOrderRiskRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> PaperRuntimePreOrderRiskResponse:
    """Return a durable fail-closed risk decision for an owned paper runtime."""
    decision = await service.evaluate_pre_order(
        current_user.sub,
        instance_id,
        **request.model_dump(),
    )
    if decision.reason == "Runtime not found":
        raise _not_found()
    return PaperRuntimePreOrderRiskResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        rule_ids=list(decision.rule_ids),
    )


@router.post("/{instance_id}/reviews", summary="Create paper review report")
async def create_paper_runtime_review(
    instance_id: str,
    request: PaperRuntimeReviewRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> dict[str, str]:
    """Persist a structured review report for later audit and handoff."""
    review = await service.create_review(current_user.sub, instance_id, request.model_dump())
    if review is None:
        raise _not_found()
    return {"id": review.id, "status": review.status}


@router.post("/{instance_id}/handoff-decisions", summary="Record paper-to-live handoff decision")
async def decide_paper_runtime_handoff(
    instance_id: str,
    request: LiveHandoffDecisionRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> dict[str, str]:
    """Record approved, rejected, or requested_changes without collapsing statuses."""
    review = await service.decide_handoff(current_user.sub, instance_id, request.model_dump())
    if review is None:
        raise _not_found()
    return {"id": review.id, "decision": review.decision}


@router.post("/{instance_id}/pause", summary="Pause paper runtime")
async def pause_paper_runtime(
    instance_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> dict[str, bool]:
    """Persist a runner-visible pause lock for an owned runtime."""
    runtime = await service.pause_runtime(current_user.sub, instance_id)
    if runtime is None:
        raise _not_found()
    from app.services.paper_runtime_scheduler import get_paper_runtime_snapshot_scheduler

    await get_paper_runtime_snapshot_scheduler().stop(instance_id)
    return {"paused": True}


@router.get("/risk-rules/", response_model=list[RiskRuleResponse], summary="List risk rules")
async def list_risk_rules(
    instance_id: str | None = None,
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> list[RiskRule]:
    """List the current user's rules, including broad scopes for one runtime."""
    return await service.list_rules(current_user.sub, instance_id)


@router.post("/risk-rules/", response_model=RiskRuleResponse, summary="Create risk rule")
async def create_risk_rule(
    request: RiskRuleCreate,
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> RiskRule:
    """Create a rule bound to an owned runtime when an instance is supplied."""
    try:
        return await service.create_rule(current_user.sub, request.model_dump())
    except LookupError as exc:
        raise _not_found() from exc


@router.patch("/risk-rules/{rule_id}", response_model=RiskRuleResponse, summary="Update risk rule")
async def update_risk_rule(
    rule_id: str,
    request: RiskRuleUpdate,
    current_user: typing.Any = Depends(get_current_user),
    service: PaperRuntimeService = Depends(get_paper_runtime_service),
) -> RiskRule:
    """Patch an owned risk rule."""
    rule = await service.update_rule(
        current_user.sub, rule_id, request.model_dump(exclude_unset=True)
    )
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk rule not found")
    return rule
