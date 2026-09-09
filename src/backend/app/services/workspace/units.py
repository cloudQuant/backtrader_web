"""Unit management operations (simple CRUD subset).

Handles delete, bulk-delete, reorder, and rename operations for strategy
units. These methods have no dependency on ``TradingWorkspaceService`` and
can be extracted cleanly.

The more complex unit operations (create, batch_create, list, get, update)
remain on :class:`app.services.workspace_service.WorkspaceService` because
they depend on ``self.trading_service`` for hydration and normalization.
"""

from __future__ import annotations

import hmac
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.backtest import BacktestTask
from app.models.strategy import Strategy
from app.models.workspace import StrategyUnit, Workspace
from app.schemas.workspace import (
    GroupRenameRequest,
    StrategyUnitCreate,
    StrategyUnitUpdate,
    UnitRenameRequest,
    UnitRuntimeInfoResponse,
)
from app.services import workspace_unit_runtime
from app.services.ai_research_provenance import (
    AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_FIELD,
    AI_RESEARCH_PAPER_RUNTIME_ANCHOR_FIELD,
    is_server_owned_ai_research_strategy_snapshot,
    verify_ai_research_live_handoff_unit_anchor,
    verify_ai_research_run_record,
)
from app.services.param_optimization_service import get_optimization_progress
from app.services.workspace._helpers import compute_rename

logger = logging.getLogger(__name__)


_JSON_FIELD_NAMES = {
    "data_config",
    "unit_settings",
    "params",
    "optimization_config",
    "gateway_config",
    "trading_snapshot",
    "metrics_snapshot",
}

_MARKET_DATA_BINDING_REQUIRED_KEY = "market_data_binding_required"
_MARKET_DATA_BINDING_KEY_PREFIX = "market_data_binding_"
_BOUND_UNIT_WINDOW_KEYS = frozenset(
    {
        "range_type",
        "start_date",
        "end_date",
        "use_end_date",
        "sample_count",
        "bar_count",
    }
)
_BOUND_UNIT_IDENTITY_FIELDS = frozenset({"category", "symbol", "timeframe", "timeframe_n"})
_AI_RESEARCH_SERVER_OWNED_PREFIX = "ai_research"
_AI_RESEARCH_SERVER_OWNED_JSON_FIELDS = (
    "data_config",
    "unit_settings",
    "params",
    "optimization_config",
    "gateway_config",
)


class MarketDataBindingUnitMutationError(ValueError):
    """Reject a client attempt to weaken a server-issued data binding."""

    def __init__(self, code: str = "MARKET_DATA_BINDING_UNIT_MUTATION_FORBIDDEN") -> None:
        self.code = code
        super().__init__(self.code)


class AIStrategyResearchUnitMutationError(ValueError):
    """Reject browser writes to server-owned AI-research paper state."""

    def __init__(self, code: str = "AI_RESEARCH_UNIT_SERVER_OWNED_STATE_FORBIDDEN") -> None:
        self.code = code
        super().__init__(self.code)


class AIStrategyResearchPaperRuntimeStartError(ValueError):
    """Reject a direct runtime launch that lacks paper-research attestation."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(self.code)


class AIStrategyResearchLiveHandoffRuntimeStartError(ValueError):
    """Reject a live handoff whose signed source/configuration no longer matches."""

    def __init__(self, code: str = "AI_RESEARCH_LIVE_HANDOFF_PROVENANCE_INVALID") -> None:
        self.code = code
        super().__init__(self.code)


class AIStrategyResearchPaperRuntimeStopError(ValueError):
    """Reject a public stop that would invalidate protected paper evidence."""

    def __init__(self, code: str = "AI_RESEARCH_PAPER_RUNTIME_STOP_FORBIDDEN") -> None:
        self.code = code
        super().__init__(self.code)


class AIStrategyResearchPaperRuntimeDeleteError(ValueError):
    """Reject a public delete that would discard protected paper evidence."""

    def __init__(self, code: str = "AI_RESEARCH_PAPER_RUNTIME_DELETE_FORBIDDEN") -> None:
        self.code = code
        super().__init__(self.code)


def _server_owned_ai_research_path(value: Any, *, path: tuple[str, ...] = ()) -> str | None:
    """Find a reserved research key in nested user-provided unit JSON."""
    if isinstance(value, dict):
        for raw_key, nested_value in value.items():
            key = str(raw_key).strip()
            normalized = key.casefold()
            next_path = (*path, key)
            if normalized == _AI_RESEARCH_SERVER_OWNED_PREFIX or normalized.startswith(
                f"{_AI_RESEARCH_SERVER_OWNED_PREFIX}_"
            ):
                return ".".join(next_path)
            nested = _server_owned_ai_research_path(nested_value, path=next_path)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            nested = _server_owned_ai_research_path(nested_value, path=(*path, str(index)))
            if nested is not None:
                return nested
    return None


def is_server_owned_ai_research_paper_runtime(unit: StrategyUnit) -> bool:
    """Return whether ``unit`` carries an anchored AI-research paper runtime.

    A lineage marker is intentionally copied into a prepared live handoff for
    audit.  It is not paper evidence, and must never route a live runtime
    through the paper-anchor start guard.
    """
    if str(getattr(unit, "trading_mode", "") or "").strip().casefold() != "paper":
        return False
    settings = getattr(unit, "unit_settings", None)
    return isinstance(settings, dict) and isinstance(
        settings.get(AI_RESEARCH_PAPER_RUNTIME_ANCHOR_FIELD),
        dict,
    )


def is_server_owned_ai_research_live_handoff_unit(unit: StrategyUnit) -> bool:
    """Return whether a server-prepared live unit still carries its handoff.

    Public create/update payloads reject every ``ai_research`` namespace, so
    this marker can only originate from the trusted prepare writer.  Keep its
    CRUD/configuration lock distinct from the paper-runtime predicate above:
    a legitimate live start has no paper anchor to verify.
    """
    if str(getattr(unit, "trading_mode", "") or "").strip().casefold() != "live":
        return False
    settings = getattr(unit, "unit_settings", None)
    handoff = settings.get("ai_research_live_handoff") if isinstance(settings, dict) else None
    return isinstance(handoff, dict) and bool(str(handoff.get("run_id") or "").strip())


def is_server_owned_ai_research_unit(unit: StrategyUnit) -> bool:
    """Return whether public writes must preserve server-owned research state."""
    return is_server_owned_ai_research_paper_runtime(
        unit
    ) or is_server_owned_ai_research_live_handoff_unit(unit)


async def has_server_owned_ai_research_strategy_reference(
    strategy_id: str,
    user_id: str,
) -> bool:
    """Return whether a user's strategy backs a protected research-paper unit.

    User strategy source files are shared templates.  Allowing their ordinary
    CRUD path to rewrite a template after the AI paper unit is attested would
    replace code/configuration at the next runtime sync without changing the
    unit row.  This lookup is deliberately service-level so simulation config
    and strategy CRUD use the same ownership and marker predicate.
    """
    normalized_strategy_id = str(strategy_id or "").strip()
    normalized_user_id = str(user_id or "").strip()
    if not normalized_strategy_id or not normalized_user_id:
        return False
    async with async_session_maker() as session:
        strategy = await session.scalar(
            select(Strategy).where(
                Strategy.id == normalized_strategy_id,
                Strategy.user_id == normalized_user_id,
            )
        )
        if strategy is not None and is_server_owned_ai_research_strategy_snapshot(
            strategy.description,
            user_id=normalized_user_id,
            strategy_id=normalized_strategy_id,
        ):
            # This reservation is written atomically with snapshot strategy
            # creation, before any paper/live unit can reference it.  It
            # closes the public template-update window between snapshot birth
            # and the later unit anchor.
            return True
        result = await session.execute(
            select(StrategyUnit)
            .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
            .where(
                Workspace.user_id == normalized_user_id,
                StrategyUnit.strategy_id == normalized_strategy_id,
            )
        )
        return any(is_server_owned_ai_research_unit(unit) for unit in result.scalars().all())


async def assert_ai_research_paper_runtime_start_allowed(
    instance_id: str,
    user_id: str | None,
) -> str | bool | None:
    """Fail closed before the global instance manager launches an attested unit.

    ``LiveTradingManager`` is reachable through both the live and simulation
    APIs, including their ``start-all`` routes.  Resolve the persisted unit
    here rather than relying on the workspace route so every instance start
    preserves the same research-paper identity and lock constraints.
    """
    normalized_instance_id = str(instance_id or "").strip()
    if not normalized_instance_id:
        return None
    async with async_session_maker() as session:
        query = (
            select(StrategyUnit, Workspace)
            .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
            .where(StrategyUnit.trading_instance_id == normalized_instance_id)
        )
        normalized_user_id = str(user_id or "").strip()
        if normalized_user_id:
            query = query.where(Workspace.user_id == normalized_user_id)
        row = (await session.execute(query)).first()
    if row is None:
        # ``None`` is intentionally distinct from ``False`` below.  The
        # manager uses it to fail closed when an instance claims a managed
        # workspace-unit runtime but its unit attachment has not committed
        # yet (or was deleted), while normal mapped workspace units remain
        # launchable through their existing routes.
        return None

    unit, workspace = row
    if not is_server_owned_ai_research_paper_runtime(unit):
        return False
    if bool(getattr(unit, "lock_running", False)):
        raise AIStrategyResearchPaperRuntimeStartError("AI_RESEARCH_PAPER_RUNTIME_LOCK_RUNNING")
    if bool(getattr(unit, "lock_trading", False)):
        raise AIStrategyResearchPaperRuntimeStartError("AI_RESEARCH_PAPER_RUNTIME_LOCK_TRADING")
    if str(getattr(unit, "trading_mode", "") or "").strip().casefold() != "paper":
        raise AIStrategyResearchPaperRuntimeStartError(
            "AI_RESEARCH_PAPER_RUNTIME_MODE_INVALID"
        )

    from app.services.ai_research_provenance import (
        AI_RESEARCH_PAPER_RUNTIME_ANCHOR_FIELD,
        verify_ai_research_paper_runtime_anchor_for_unit,
    )

    settings = getattr(unit, "unit_settings", None)
    anchor = settings.get(AI_RESEARCH_PAPER_RUNTIME_ANCHOR_FIELD) if isinstance(settings, dict) else None
    if not verify_ai_research_paper_runtime_anchor_for_unit(
        anchor,
        user_id=str(workspace.user_id),
        paper_workspace_id=str(unit.workspace_id),
        paper_unit_id=str(unit.id),
        unit=unit,
        workspace_settings=(
            workspace.settings if isinstance(getattr(workspace, "settings", None), dict) else {}
        ),
        require_runtime_snapshot=True,
    ):
        raise AIStrategyResearchPaperRuntimeStartError(
            "AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID"
        )
    runtime_snapshot_digest = anchor.get("runtime_snapshot_digest") if isinstance(anchor, dict) else None
    if not isinstance(runtime_snapshot_digest, str) or len(runtime_snapshot_digest) != 64:
        raise AIStrategyResearchPaperRuntimeStartError(
            "AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID"
        )
    return runtime_snapshot_digest


async def assert_ai_research_live_handoff_runtime_start_allowed(
    unit: StrategyUnit,
    user_id: str,
) -> bool:
    """Verify a prepared live handoff against its signed source run.

    ``ai_research_live_handoff`` reserves browser mutation from the instant
    the unit is created.  Before a trusted server path unlocks and starts it,
    this second gate verifies the source run's HMAC plus the exact live unit
    identity/configuration seal.  A visible marker or risk-gate JSON never
    grants authority by itself.
    """
    if not is_server_owned_ai_research_live_handoff_unit(unit):
        return False
    settings = getattr(unit, "unit_settings", None)
    anchor = (
        settings.get(AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_FIELD)
        if isinstance(settings, dict)
        else None
    )
    if not isinstance(anchor, dict):
        raise AIStrategyResearchLiveHandoffRuntimeStartError()
    research_workspace_id = str(anchor.get("research_workspace_id") or "").strip()
    run_id = str(anchor.get("run_id") or "").strip()
    if not research_workspace_id or not run_id:
        raise AIStrategyResearchLiveHandoffRuntimeStartError()
    # Workspace settings are public storage, so the raw record must verify
    # before it can supply approval/risk authority for this runtime.
    async with async_session_maker() as session:
        source_workspace = await session.scalar(
            select(Workspace).where(
                Workspace.id == research_workspace_id,
                Workspace.user_id == user_id,
            )
        )
    raw_settings = (
        source_workspace.settings
        if source_workspace is not None and isinstance(source_workspace.settings, dict)
        else {}
    )
    raw_research = raw_settings.get("ai_research") if isinstance(raw_settings, dict) else None
    if not isinstance(raw_research, dict):
        raise AIStrategyResearchLiveHandoffRuntimeStartError()
    # ``last_run`` is the server writer's canonical current revision.  Do
    # not rank arbitrary history entries: a valid but older approved record
    # with the same run id must not outvote a later signed revocation.
    raw_last = raw_research.get("last_run")
    if not isinstance(raw_last, dict):
        raise AIStrategyResearchLiveHandoffRuntimeStartError()
    from app.schemas.ai_strategy_research import AIStrategyResearchRunRecord

    if str(raw_last.get("run_id") or "").strip() != run_id:
        raise AIStrategyResearchLiveHandoffRuntimeStartError()
    try:
        matched = AIStrategyResearchRunRecord.model_validate(raw_last)
    except (TypeError, ValueError) as exc:
        raise AIStrategyResearchLiveHandoffRuntimeStartError() from exc
    if not verify_ai_research_run_record(
        matched,
        user_id=user_id,
        workspace_id=research_workspace_id,
    ):
        raise AIStrategyResearchLiveHandoffRuntimeStartError()
    canonical_signature = str(matched.server_provenance_signature or "").strip()
    if not canonical_signature:
        raise AIStrategyResearchLiveHandoffRuntimeStartError()
    if not verify_ai_research_live_handoff_unit_anchor(
        anchor,
        user_id=user_id,
        research_workspace_id=research_workspace_id,
        live_workspace_id=str(unit.workspace_id),
        live_unit_id=str(unit.id),
        run_id=run_id,
        source_run_signature=canonical_signature,
        unit=unit,
    ):
        raise AIStrategyResearchLiveHandoffRuntimeStartError()
    raw_runs = raw_research.get("runs")
    if isinstance(raw_runs, list):
        for raw in raw_runs:
            if not isinstance(raw, dict) or str(raw.get("run_id") or "").strip() != run_id:
                continue
            try:
                historical = AIStrategyResearchRunRecord.model_validate(raw)
            except (TypeError, ValueError):
                continue
            if not verify_ai_research_run_record(
                historical,
                user_id=user_id,
                workspace_id=research_workspace_id,
            ):
                continue
            if not hmac.compare_digest(
                str(historical.server_provenance_signature or "").strip(),
                canonical_signature,
            ):
                raise AIStrategyResearchLiveHandoffRuntimeStartError(
                    "AI_RESEARCH_LIVE_HANDOFF_SOURCE_REVISION_AMBIGUOUS"
                )

    approval = matched.live_handoff_approval
    package = matched.live_handoff
    if (
        not matched.live_trading_prepared
        or str(matched.live_workspace_id or "") != str(unit.workspace_id)
        or str(matched.live_unit_id or "") != str(unit.id)
        or package is None
        or not package.ready_for_live
        or not approval
        or not approval.approved
    ):
        raise AIStrategyResearchLiveHandoffRuntimeStartError()
    live_risk_gate = settings.get("live_risk_gate") if isinstance(settings, dict) else None
    if not isinstance(live_risk_gate, dict) or live_risk_gate.get("passed") is not True:
        raise AIStrategyResearchLiveHandoffRuntimeStartError(
            "AI_RESEARCH_LIVE_HANDOFF_RISK_GATE_INVALID"
        )
    package_handoff = package.handoff if isinstance(package.handoff, dict) else {}
    prepared_handoff = package_handoff.get("live_trading_prepare")
    source_risk_gate = (
        prepared_handoff.get("live_risk_gate")
        if isinstance(prepared_handoff, dict)
        else None
    )
    if (
        isinstance(source_risk_gate, dict)
        and source_risk_gate.get("passed") is not True
    ):
        raise AIStrategyResearchLiveHandoffRuntimeStartError(
            "AI_RESEARCH_LIVE_HANDOFF_RISK_GATE_INVALID"
        )
    return True


async def get_ai_research_live_handoff_unit_for_instance(
    instance_id: str,
    user_id: str | None,
) -> StrategyUnit | None:
    """Resolve a reserved live-handoff unit for a manager instance.

    This lookup deliberately returns the *structural* live reservation rather
    than treating it as an execution authorization.  The instance manager
    uses it to reject every public/direct start before a server-only activation
    capability is supplied.  The capability path separately calls
    :func:`assert_ai_research_live_handoff_runtime_start_allowed`, which
    verifies the HMAC-bound source run and live-unit seal.
    """
    normalized_instance_id = str(instance_id or "").strip()
    if not normalized_instance_id:
        return None
    async with async_session_maker() as session:
        query = (
            select(StrategyUnit, Workspace)
            .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
            .where(StrategyUnit.trading_instance_id == normalized_instance_id)
        )
        normalized_user_id = str(user_id or "").strip()
        if normalized_user_id:
            query = query.where(Workspace.user_id == normalized_user_id)
        row = (await session.execute(query)).first()
    if row is None:
        return None
    unit, _workspace = row
    return unit if is_server_owned_ai_research_live_handoff_unit(unit) else None


async def assert_ai_research_paper_runtime_stop_allowed(
    instance_id: str,
    user_id: str | None,
    *,
    allow_server_owned_ai_research_stop: bool = False,
    allow_server_owned_ai_research_live_handoff_stop: bool = False,
) -> bool:
    """Reject user-initiated stops of an attested AI paper runtime.

    The instance manager is shared by simulation, live-trading, workspace and
    scheduler routes.  Its JSON instance store alone cannot tell a public
    stop from the review workflow's server-owned failure stop, so resolve the
    authoritative unit link here before process state is changed.  A stopped
    runtime must never leave a still-promotable paper review behind.
    """
    normalized_instance_id = str(instance_id or "").strip()
    if not normalized_instance_id:
        return False
    async with async_session_maker() as session:
        query = (
            select(StrategyUnit, Workspace)
            .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
            .where(StrategyUnit.trading_instance_id == normalized_instance_id)
        )
        normalized_user_id = str(user_id or "").strip()
        if normalized_user_id:
            query = query.where(Workspace.user_id == normalized_user_id)
        row = (await session.execute(query)).first()
    if row is None:
        return False

    unit, _workspace = row
    if not is_server_owned_ai_research_unit(unit):
        return False
    # The only current server-owned stop is the paper-review failure path.
    # A prepared live handoff has no corresponding public or scheduler stop
    # capability: allowing the paper exception here would make an approved
    # live unit restartable through a stale source record.
    if is_server_owned_ai_research_live_handoff_unit(unit):
        if not allow_server_owned_ai_research_live_handoff_stop or user_id is None:
            raise AIStrategyResearchPaperRuntimeStopError(
                "AI_RESEARCH_LIVE_HANDOFF_RUNTIME_STOP_FORBIDDEN"
            )
        settings = getattr(unit, "unit_settings", None)
        anchor = (
            settings.get(AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_FIELD)
            if isinstance(settings, dict)
            else None
        )
        source_signature = (
            str(anchor.get("source_run_signature") or "").strip()
            if isinstance(anchor, dict)
            else ""
        )
        if not (
            isinstance(anchor, dict)
            and source_signature
            and verify_ai_research_live_handoff_unit_anchor(
                anchor,
                user_id=user_id,
                research_workspace_id=str(anchor.get("research_workspace_id") or ""),
                live_workspace_id=str(unit.workspace_id),
                live_unit_id=str(unit.id),
                run_id=str(anchor.get("run_id") or ""),
                source_run_signature=source_signature,
                unit=unit,
            )
        ):
            raise AIStrategyResearchPaperRuntimeStopError(
                "AI_RESEARCH_LIVE_HANDOFF_PROVENANCE_INVALID"
            )
        return True
    if not allow_server_owned_ai_research_stop:
        raise AIStrategyResearchPaperRuntimeStopError()
    return True


async def assert_ai_research_paper_runtime_delete_allowed(
    instance_id: str,
    user_id: str | None,
) -> bool:
    """Reject browser deletion of a runtime bound to a protected paper unit.

    A direct simulation/live instance delete bypasses workspace-unit CRUD.  It
    must therefore resolve the authoritative unit association before removing
    the process and JSON record, otherwise a signed paper-review source can be
    orphaned from the server-owned identity that protects it.
    """
    normalized_instance_id = str(instance_id or "").strip()
    if not normalized_instance_id:
        return False
    async with async_session_maker() as session:
        query = (
            select(StrategyUnit, Workspace)
            .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
            .where(StrategyUnit.trading_instance_id == normalized_instance_id)
        )
        normalized_user_id = str(user_id or "").strip()
        if normalized_user_id:
            query = query.where(Workspace.user_id == normalized_user_id)
        row = (await session.execute(query)).first()
    if row is None:
        return False

    unit, _workspace = row
    if not is_server_owned_ai_research_unit(unit):
        return False
    raise AIStrategyResearchPaperRuntimeDeleteError()


def _reject_untrusted_ai_research_unit_payload(
    data: StrategyUnitCreate | StrategyUnitUpdate,
    *,
    allow_server_owned_ai_research_state: bool,
) -> None:
    """Reserve research evidence/lineage keys for the internal workflow only."""
    if allow_server_owned_ai_research_state:
        return
    fields_set = getattr(data, "model_fields_set", set())
    for field in _AI_RESEARCH_SERVER_OWNED_JSON_FIELDS:
        if isinstance(data, StrategyUnitUpdate) and field not in fields_set:
            continue
        reserved_path = _server_owned_ai_research_path(getattr(data, field, None), path=(field,))
        if reserved_path is not None:
            raise AIStrategyResearchUnitMutationError()
    if isinstance(data, StrategyUnitCreate):
        if "trading_snapshot" in fields_set:
            raise AIStrategyResearchUnitMutationError("AI_RESEARCH_UNIT_RUNTIME_STATE_FORBIDDEN")
    elif "trading_snapshot" in fields_set or "trading_instance_id" in fields_set:
        raise AIStrategyResearchUnitMutationError("AI_RESEARCH_UNIT_RUNTIME_STATE_FORBIDDEN")


def _requires_market_data_binding(data_config: object) -> bool:
    """Recognize a persisted required binding without accepting a downgrade."""
    if not isinstance(data_config, dict):
        return False
    value = data_config.get(_MARKET_DATA_BINDING_REQUIRED_KEY)
    return value is True or (
        isinstance(value, str) and value.strip().casefold() in {"1", "true", "yes", "on"}
    )


def _contains_market_data_binding_payload(data_config: object) -> bool:
    """Identify any browser-supplied attempt to create a sealed binding unit."""
    return isinstance(data_config, dict) and any(
        str(key).casefold().startswith(_MARKET_DATA_BINDING_KEY_PREFIX)
        for key in data_config
    )


def _reject_untrusted_market_data_binding_payload(
    data_config: object,
    *,
    allow_server_bound_research_data: bool,
) -> None:
    """Reserve binding attachment for the internal AI-research capability."""
    if _contains_market_data_binding_payload(data_config) and not allow_server_bound_research_data:
        raise MarketDataBindingUnitMutationError("MARKET_DATA_BINDING_CONSUMER_CREATE_FORBIDDEN")


def _merged_bound_unit_data_config(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    """Preserve sealed binding fields while allowing a narrower run window.

    ``StrategyUnitUpdate.data_config`` is a replacement payload.  Treating it
    as one for a bound unit would let an ordinary browser update remove
    ``market_data_binding_required`` and fall back to a legacy CSV search.  A
    caller may change only the run-window controls; every other provided value
    must exactly match the server-owned persisted metadata.
    """
    current = dict(existing or {})
    if not _requires_market_data_binding(current) or not isinstance(incoming, dict):
        raise MarketDataBindingUnitMutationError()

    merged = dict(current)
    for key, value in incoming.items():
        if key in _BOUND_UNIT_WINDOW_KEYS:
            merged[key] = value
            continue
        if key not in current or current[key] != value:
            raise MarketDataBindingUnitMutationError()
    return merged


def _validate_bound_unit_identity_update(unit: StrategyUnit, update_data: dict[str, Any]) -> None:
    """Keep the unit identity aligned with the signed binding semantics."""
    for key in _BOUND_UNIT_IDENTITY_FIELDS:
        if key in update_data and update_data[key] != getattr(unit, key):
            raise MarketDataBindingUnitMutationError()


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    return value


async def create_unit(
    workspace_id: str,
    user_id: str,
    data: StrategyUnitCreate,
    trading_service: Any,
    *,
    allow_server_bound_research_data: bool = False,
    allow_server_owned_ai_research_state: bool = False,
) -> dict[str, Any] | None:
    from app.services.workspace_service import WorkspaceService, _normalize_unit_data_config

    _reject_untrusted_market_data_binding_payload(
        data.data_config,
        allow_server_bound_research_data=allow_server_bound_research_data,
    )
    _reject_untrusted_ai_research_unit_payload(
        data,
        allow_server_owned_ai_research_state=allow_server_owned_ai_research_state,
    )
    if (
        not allow_server_owned_ai_research_state
        and str(data.strategy_id or "").strip()
        and await has_server_owned_ai_research_strategy_reference(data.strategy_id, user_id)
    ):
        raise AIStrategyResearchUnitMutationError(
            "AI_RESEARCH_STRATEGY_SNAPSHOT_UNIT_CREATE_FORBIDDEN"
        )
    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None

        max_order_q = select(func.coalesce(func.max(StrategyUnit.sort_order), -1)).where(
            StrategyUnit.workspace_id == workspace_id
        )
        max_order = (await session.execute(max_order_q)).scalar() or 0

        unit = StrategyUnit(
            workspace_id=workspace_id,
            group_name=data.group_name,
            strategy_id=data.strategy_id,
            strategy_name=data.strategy_name,
            symbol=data.symbol,
            symbol_name=data.symbol_name,
            timeframe=data.timeframe,
            timeframe_n=data.timeframe_n,
            category=data.category,
            sort_order=max_order + 1,
            data_config=_json_safe_value(_normalize_unit_data_config(data.data_config)),
            unit_settings=_json_safe_value(data.unit_settings),
            params=_json_safe_value(data.params),
            optimization_config=_json_safe_value(data.optimization_config),
            trading_mode=trading_service.normalize_trading_mode(data.trading_mode),
            gateway_config=_json_safe_value(
                trading_service.normalize_gateway_config(
                    data.gateway_config.model_dump()
                    if hasattr(data.gateway_config, "model_dump")
                    else data.gateway_config
                )
            ),
            lock_trading=bool(data.lock_trading),
            lock_running=bool(data.lock_running),
            trading_snapshot=_json_safe_value(
                data.trading_snapshot.model_dump()
                if hasattr(data.trading_snapshot, "model_dump")
                else data.trading_snapshot
            ),
        )
        session.add(unit)
        await session.commit()
        await session.refresh(unit)
        workspace_unit_runtime.sync_workspace_unit_runtime(
            unit,
            cast("dict[str, Any]", ws.settings) or {},
            str(ws.workspace_type),
        )
        return WorkspaceService._unit_to_dict(unit)


async def batch_create_units(
    workspace_id: str,
    user_id: str,
    units_data: list[StrategyUnitCreate],
    trading_service: Any,
    *,
    allow_server_bound_research_data: bool = False,
    allow_server_owned_ai_research_state: bool = False,
) -> list[dict[str, Any]] | None:
    from app.services.workspace_service import WorkspaceService, _normalize_unit_data_config

    for data in units_data:
        _reject_untrusted_market_data_binding_payload(
            data.data_config,
            allow_server_bound_research_data=allow_server_bound_research_data,
        )
        _reject_untrusted_ai_research_unit_payload(
            data,
            allow_server_owned_ai_research_state=allow_server_owned_ai_research_state,
        )
        if (
            not allow_server_owned_ai_research_state
            and str(data.strategy_id or "").strip()
            and await has_server_owned_ai_research_strategy_reference(data.strategy_id, user_id)
        ):
            raise AIStrategyResearchUnitMutationError(
                "AI_RESEARCH_STRATEGY_SNAPSHOT_UNIT_CREATE_FORBIDDEN"
            )
    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None

        max_order_q = select(func.coalesce(func.max(StrategyUnit.sort_order), -1)).where(
            StrategyUnit.workspace_id == workspace_id
        )
        max_order = (await session.execute(max_order_q)).scalar() or 0

        created = []
        for i, data in enumerate(units_data):
            unit = StrategyUnit(
                workspace_id=workspace_id,
                group_name=data.group_name,
                strategy_id=data.strategy_id,
                strategy_name=data.strategy_name,
                symbol=data.symbol,
                symbol_name=data.symbol_name,
                timeframe=data.timeframe,
                timeframe_n=data.timeframe_n,
                category=data.category,
                sort_order=max_order + 1 + i,
                data_config=_json_safe_value(_normalize_unit_data_config(data.data_config)),
                unit_settings=_json_safe_value(data.unit_settings),
                params=_json_safe_value(data.params),
                optimization_config=_json_safe_value(data.optimization_config),
                trading_mode=trading_service.normalize_trading_mode(data.trading_mode),
                gateway_config=_json_safe_value(
                    trading_service.normalize_gateway_config(
                        data.gateway_config.model_dump()
                        if hasattr(data.gateway_config, "model_dump")
                        else data.gateway_config
                    )
                ),
                lock_trading=bool(data.lock_trading),
                lock_running=bool(data.lock_running),
                trading_snapshot=_json_safe_value(
                    data.trading_snapshot.model_dump()
                    if hasattr(data.trading_snapshot, "model_dump")
                    else data.trading_snapshot
                ),
            )
            session.add(unit)
            created.append(unit)

        await session.commit()
        for unit in created:
            await session.refresh(unit)
            workspace_unit_runtime.sync_workspace_unit_runtime(
                unit,
                cast("dict[str, Any]", ws.settings) or {},
                str(ws.workspace_type),
            )
        return [WorkspaceService._unit_to_dict(unit) for unit in created]


async def list_units(
    workspace_id: str,
    user_id: str,
    trading_service: Any,
) -> list[dict[str, Any]] | None:
    from app.services.backtest.service import BacktestService
    from app.services.workspace_service import WorkspaceService, _normalize_workspace_type

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None

        q = (
            select(StrategyUnit)
            .where(StrategyUnit.workspace_id == workspace_id)
            .order_by(StrategyUnit.sort_order)
        )
        result = await session.execute(q)
        units = list(result.scalars().all())

        if _normalize_workspace_type(getattr(ws, "workspace_type", None)) == "trading":
            # Initial table rendering must stay local: full log parsing and
            # broker gateway reads are reserved for explicit detail/status
            # refreshes, otherwise a workspace with many units blocks the UI.
            changed = await trading_service.hydrate_units(
                units,
                user_id,
                full_log=False,
                refresh_gateway=False,
            )
            if changed:
                await session.commit()
            return [WorkspaceService._unit_to_dict(unit) for unit in units]

        task_ids = [
            str(cast(Any, unit).last_task_id) for unit in units if cast(Any, unit).last_task_id
        ]
        task_by_id: dict[str, BacktestTask] = {}
        if task_ids:
            task_result = await session.execute(
                select(BacktestTask).where(BacktestTask.id.in_(task_ids))
            )
            task_by_id = {str(task.id): task for task in task_result.scalars().all()}

        changed = False
        backtest_service = None
        for unit in units:
            unit_obj = cast(Any, unit)
            last_task_id = str(unit_obj.last_task_id or "").strip()
            if not last_task_id:
                continue

            task = task_by_id.get(last_task_id)
            elapsed_seconds = WorkspaceService._task_elapsed_seconds(task)
            if elapsed_seconds is not None and unit_obj.last_run_time != elapsed_seconds:
                unit_obj.last_run_time = elapsed_seconds
                changed = True

            if str(unit_obj.run_status or "") != "completed":
                continue

            if backtest_service is None:
                backtest_service = BacktestService()

            resolved_bar_count = await WorkspaceService._resolve_unit_bar_count(
                backtest_service,
                last_task_id,
                user_id,
            )
            if resolved_bar_count > 0 and int(unit_obj.bar_count or 0) != resolved_bar_count:
                unit_obj.bar_count = resolved_bar_count
                changed = True

        if changed:
            await session.commit()

        opt_progress_map: dict[str, dict[str, Any]] = {}
        opt_task_ids = {
            str(cast(Any, unit).last_optimization_task_id)
            for unit in units
            if cast(Any, unit).last_optimization_task_id
        }
        if opt_task_ids:
            for task_id in opt_task_ids:
                try:
                    progress = get_optimization_progress(task_id, user_id=user_id, use_db=True)
                    opt_info = WorkspaceService._optimization_progress_response_to_opt_info(
                        progress
                    )
                    if opt_info:
                        opt_progress_map[task_id] = opt_info
                except Exception:
                    logger.debug(
                        "Failed to load optimization progress for task %s", task_id, exc_info=True
                    )

        return [
            WorkspaceService._unit_to_dict(
                unit,
                opt_progress_map.get(
                    str(cast(Any, unit).last_optimization_task_id),
                    {},
                )
                if cast(Any, unit).last_optimization_task_id
                else {},
            )
            for unit in units
        ]


async def get_unit(
    workspace_id: str,
    unit_id: str,
    user_id: str,
    trading_service: Any,
) -> dict[str, Any] | None:
    from app.services.workspace_service import WorkspaceService, _normalize_workspace_type

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return None
        if _normalize_workspace_type(getattr(ws, "workspace_type", None)) == "trading":
            changed = await trading_service.hydrate_units([unit], user_id)
            if changed:
                await session.commit()
        return WorkspaceService._unit_to_dict(unit)


async def get_unit_runtime_info(
    workspace_id: str,
    unit_id: str,
    user_id: str,
    trading_service: Any,
) -> dict[str, Any] | None:
    from app.services.workspace_service import WorkspaceService, _normalize_workspace_type

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return None
        if _normalize_workspace_type(getattr(ws, "workspace_type", None)) == "trading":
            changed = await trading_service.hydrate_units([unit], user_id)
            if changed:
                await session.commit()

        runtime_dir = workspace_unit_runtime.unit_dir(workspace_id, unit_id)
        if not runtime_dir.is_dir():
            return None

        log_dir = runtime_dir / "logs"
        files: list[dict[str, Any]] = []
        for relative_path in WorkspaceService._collect_runtime_files(runtime_dir):
            file_path = runtime_dir / relative_path
            if not file_path.is_file():
                continue
            files.append(
                {
                    "name": file_path.name,
                    "relative_path": relative_path.as_posix(),
                    "size": file_path.stat().st_size,
                    "kind": WorkspaceService._runtime_file_kind(relative_path),
                }
            )

        return UnitRuntimeInfoResponse(
            unit_id=unit_id,
            runtime_dir=str(runtime_dir),
            log_dir=str(log_dir) if log_dir.is_dir() else None,
            files=files,
        ).model_dump()


async def get_unit_runtime_dir(
    workspace_id: str,
    unit_id: str,
    user_id: str,
) -> Path | None:
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return None
        runtime_dir = workspace_unit_runtime.unit_dir(workspace_id, unit_id)
        return runtime_dir if runtime_dir.is_dir() else None


async def read_unit_runtime_file(
    workspace_id: str,
    unit_id: str,
    user_id: str,
    relative_path: str,
    tail: int | None = None,
) -> str | None:
    from app.services.workspace_service import WorkspaceService

    runtime_dir = await get_unit_runtime_dir(workspace_id, unit_id, user_id)
    if runtime_dir is None:
        return None
    file_path = WorkspaceService._resolve_runtime_file(runtime_dir, relative_path)
    if file_path is None or not file_path.is_file():
        return None

    content = file_path.read_text(encoding="utf-8", errors="replace")
    if tail is not None and tail > 0:
        lines = content.splitlines()
        content = "\n".join(lines[-tail:])
    return content


async def open_unit_runtime_dir(
    workspace_id: str,
    unit_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    from app.services.workspace_service import WorkspaceService

    runtime_dir = await get_unit_runtime_dir(workspace_id, unit_id, user_id)
    if runtime_dir is None:
        return None
    WorkspaceService._open_path_in_file_manager(runtime_dir)
    return {
        "unit_id": unit_id,
        "runtime_dir": str(runtime_dir),
        "message": "策略单元目录已打开",
    }


async def update_unit(
    workspace_id: str,
    unit_id: str,
    user_id: str,
    data: StrategyUnitUpdate,
    trading_service: Any,
    *,
    allow_server_owned_ai_research_state: bool = False,
    sync_runtime: bool = True,
) -> dict[str, Any] | None:
    from app.services.workspace_service import WorkspaceService, _normalize_unit_data_config

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        _reject_untrusted_ai_research_unit_payload(
            data,
            allow_server_owned_ai_research_state=allow_server_owned_ai_research_state,
        )
        replacement_strategy_id = str(update_data.get("strategy_id") or "").strip()
        if (
            replacement_strategy_id
            and not allow_server_owned_ai_research_state
            and await has_server_owned_ai_research_strategy_reference(
                replacement_strategy_id,
                user_id,
            )
        ):
            raise AIStrategyResearchUnitMutationError(
                "AI_RESEARCH_STRATEGY_SNAPSHOT_UNIT_CREATE_FORBIDDEN"
            )
        if (
            update_data
            and is_server_owned_ai_research_unit(unit)
            and not allow_server_owned_ai_research_state
        ):
            # A public replacement JSON payload could otherwise first erase the
            # marker and then change its strategy/instance/runtime evidence on
            # the next request.  Paper-review identity is server-owned.
            raise AIStrategyResearchUnitMutationError()
        existing_data_config = cast(dict[str, Any] | None, unit.data_config)
        binding_required = _requires_market_data_binding(existing_data_config)
        if binding_required:
            _validate_bound_unit_identity_update(unit, update_data)
        for key, value in update_data.items():
            if key == "data_config":
                if binding_required:
                    value = _merged_bound_unit_data_config(
                        existing_data_config,
                        cast(dict[str, Any] | None, value),
                    )
                value = _normalize_unit_data_config(cast(dict[str, Any] | None, value))
            elif key == "trading_mode":
                value = trading_service.normalize_trading_mode(value)
            elif key == "gateway_config":
                value = trading_service.normalize_gateway_config(
                    value.model_dump()
                    if hasattr(value, "model_dump")
                    else cast(dict[str, Any], value)
                )
            elif key == "trading_snapshot":
                value = (
                    value.model_dump()
                    if hasattr(value, "model_dump")
                    else cast(dict[str, Any], value)
                )
            if key in _JSON_FIELD_NAMES:
                value = _json_safe_value(value)
            setattr(unit, key, value)
        await session.commit()
        await session.refresh(unit)
        if sync_runtime:
            workspace_unit_runtime.sync_workspace_unit_runtime(
                unit,
                cast("dict[str, Any]", ws.settings) or {},
                str(ws.workspace_type),
            )
        return WorkspaceService._unit_to_dict(unit)


async def delete_unit(workspace_id: str, unit_id: str, user_id: str) -> bool:
    """Delete a single strategy unit and its runtime directory."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return False
        if is_server_owned_ai_research_unit(unit):
            raise AIStrategyResearchUnitMutationError(
                "AI_RESEARCH_UNIT_SERVER_OWNED_DELETE_FORBIDDEN"
            )
        await session.delete(unit)
        await session.commit()
        workspace_unit_runtime.remove_unit_dir(workspace_id, unit_id)
        return True


async def bulk_delete_units(workspace_id: str, user_id: str, unit_ids: list[str]) -> int:
    """Delete multiple units in one transaction."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return 0

        candidates = (
            await session.execute(
                select(StrategyUnit).where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(unit_ids),
                )
            )
        ).scalars().all()
        if any(is_server_owned_ai_research_unit(unit) for unit in candidates):
            raise AIStrategyResearchUnitMutationError(
                "AI_RESEARCH_UNIT_SERVER_OWNED_DELETE_FORBIDDEN"
            )

        result = await session.execute(
            sa_delete(StrategyUnit).where(
                StrategyUnit.workspace_id == workspace_id,
                StrategyUnit.id.in_(unit_ids),
            )
        )
        await session.commit()
        for uid in unit_ids:
            workspace_unit_runtime.remove_unit_dir(workspace_id, uid)
        return result.rowcount or 0


async def reorder_units(workspace_id: str, user_id: str, unit_ids: list[str]) -> bool:
    """Set ``sort_order`` for units based on the provided id list."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False
        for idx, uid in enumerate(unit_ids):
            unit = await WorkspaceService._get_unit(session, workspace_id, uid)
            if unit:
                unit_row: Any = unit
                unit_row.sort_order = idx
        await session.commit()
        return True


async def rename_group(workspace_id: str, user_id: str, req: GroupRenameRequest) -> bool:
    """Rename the group for a set of units."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False

        q = select(StrategyUnit).where(
            StrategyUnit.workspace_id == workspace_id,
            StrategyUnit.id.in_(req.unit_ids),
        )
        result = await session.execute(q)
        units = list(result.scalars().all())

        for unit in units:
            unit.group_name = compute_rename(unit, req.mode, req.value, req.search, req.replace)

        await session.commit()
        return True


async def rename_unit(workspace_id: str, user_id: str, req: UnitRenameRequest) -> bool:
    """Rename a single unit's strategy_name."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False
        unit = await WorkspaceService._get_unit(session, workspace_id, req.unit_id)
        if unit is None:
            return False
        unit_row: Any = unit
        unit_row.strategy_name = compute_rename(unit, req.mode, req.value, req.search, req.replace)
        await session.commit()
        return True
