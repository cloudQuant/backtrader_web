"""
Strategy API routes.
"""

import logging
import typing
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import get_current_user
from app.config import get_settings
from app.db.database import get_db
from app.schemas.ai_strategy_research import (
    AIStrategyLiveHandoffApprovalRequest,
    AIStrategyLiveHandoffPackage,
    AIStrategyLiveTradingPrepare,
    AIStrategyLiveTradingPrepareRequest,
    AIStrategyPaperTradingReview,
    AIStrategyPaperTradingStart,
    AIStrategyPaperTradingStartRequest,
    AIStrategyResearchConfigProfile,
    AIStrategyResearchConfigProfileCreate,
    AIStrategyResearchConfigProfileImportRequest,
    AIStrategyResearchConfigProfileImportResponse,
    AIStrategyResearchConfigProfileListResponse,
    AIStrategyResearchConfigProfileUpdate,
    AIStrategyResearchObjectiveOptimizeRequest,
    AIStrategyResearchObjectiveOptimizeResponse,
    AIStrategyResearchRunContinueRequest,
    AIStrategyResearchRunListResponse,
    AIStrategyResearchRunRecord,
    AIStrategyResearchRunRequest,
    AIStrategyResearchRunResponse,
    AIStrategyResearchTaskContinueRequest,
    AIStrategyResearchTaskListResponse,
    AIStrategyResearchTaskResponse,
    AIStrategyResearchVersionCompareResponse,
    AIStrategyResearchVersionListResponse,
    AIStrategyResearchVersionResponse,
    InvestmentMandateCreate,
    InvestmentMandateResponse,
    ResearchTimelineResponse,
)
from app.schemas.strategy import (
    StrategyCopilotBacktestRequest,
    StrategyCopilotBacktestResponse,
    StrategyCopilotDraftRequest,
    StrategyCopilotDraftResponse,
    StrategyCreate,
    StrategyDraftWorkspaceAddRequest,
    StrategyDraftWorkspaceAddResponse,
    StrategyListResponse,
    StrategyResponse,
    StrategyUpdate,
)
from app.services.ai_research_provenance import (
    verify_ai_research_run_record,
    verify_ai_research_task_snapshot,
)
from app.services.ai_strategy_research_config_profiles import (
    AIStrategyResearchConfigProfileService,
)
from app.services.ai_strategy_research_objective_optimizer import (
    AIStrategyResearchObjectiveOptimizer,
)
from app.services.ai_strategy_research_service import (
    AIStrategyResearchService,
    redact_ai_strategy_research_payload,
)
from app.services.ai_strategy_research_task_manager import (
    AIStrategyResearchTaskManager,
    get_ai_strategy_research_task_manager,
)
from app.services.ai_strategy_research_version_service import AIStrategyResearchVersionService
from app.services.investment_mandate_service import InvestmentMandateService
from app.services.research_pipeline_event_service import ResearchPipelineEventService
from app.services.strategy_service import (
    StrategyService,
    get_strategy_dir,
    get_strategy_readme,
    get_template_by_id,
)
from app.services.workspace.units import (
    MarketDataBindingUnitMutationError,
    has_server_owned_ai_research_strategy_reference,
)
from app.utils.response_cache import cache_response

_logger = logging.getLogger(__name__)

router = APIRouter()

_MARKET_DATA_BINDING_ERROR_PREFIX = "MARKET_DATA_BINDING_"
_MARKET_DATA_BRIDGE_DISABLED_CODE = "MARKET_DATA_BRIDGE_DISABLED"


@lru_cache
def get_strategy_service() -> typing.Any:
    return StrategyService()


@lru_cache
def get_ai_strategy_research_service() -> typing.Any:
    return AIStrategyResearchService()


@lru_cache
def get_ai_strategy_research_objective_optimizer() -> typing.Any:
    return AIStrategyResearchObjectiveOptimizer()


@lru_cache
def get_ai_strategy_research_tasks() -> typing.Any:
    return get_ai_strategy_research_task_manager()


class _MarketDataResearchBindingRequestFactory:
    """Open a v2 database session only while the enabled bridge binds a request."""

    def __init__(self, *, artifact_root: Path, signing_key: str) -> None:
        self._artifact_root = artifact_root
        self._signing_key = signing_key

    async def bind_request(
        self,
        *,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        intent_id: str,
    ) -> AIStrategyResearchRunRequest:
        """Compose and use the v2 service inside one short-lived DB session."""
        database_dependency = get_db()
        try:
            db = await database_dependency.__anext__()
            from app.api.data.base import get_legacy_market_data_query_contract_resolver
            from app.api.data.deps import get_market_data_access_authorizer
            from app.api.data.queries import get_market_data_query_service
            from app.services.market_data.research_binding import MarketDataResearchBindingService

            service = MarketDataResearchBindingService(
                db,
                get_market_data_query_service(db),
                get_legacy_market_data_query_contract_resolver(db),
                get_market_data_access_authorizer(db),
                self._artifact_root,
                binding_signing_key=self._signing_key,
            )
            return await service.bind_request(
                user_id=user_id,
                request=request,
                intent_id=intent_id,
            )
        except StopAsyncIteration as exc:
            raise RuntimeError("AI research market-data database dependency is unavailable") from exc
        finally:
            await database_dependency.aclose()


def get_ai_strategy_research_market_data_binding_service() -> typing.Any | None:
    """Build the enabled Iteration 197 research-data request factory.

    V2 imports, database sessions, and provider-policy construction are all
    delayed until ``bind_request`` and therefore absent from legacy API calls
    while the default-disabled bridge remains off.
    """
    settings = get_settings()
    if not (
        bool(getattr(settings, "MARKET_DATA_QUERY_V2_ENABLED", False))
        and bool(getattr(settings, "MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_ENABLED", False))
    ):
        return None
    return _MarketDataResearchBindingRequestFactory(
        artifact_root=Path(str(settings.MARKET_DATA_RESEARCH_ARTIFACT_ROOT)),
        signing_key=str(settings.MARKET_DATA_RESEARCH_ARTIFACT_SIGNING_KEY),
    )


def _market_data_research_request_preparer(
    binding_service: typing.Any | None,
    *,
    user_id: str,
    mandate_service: InvestmentMandateService,
    trusted_auto_prompt: str | None = None,
    trusted_auto_mandate_id: str | None = None,
    allow_server_continuation: bool = False,
) -> typing.Callable[[str, AIStrategyResearchRunRequest], typing.Any]:
    """Return the fail-closed mandate validator and optional server-side binder.

    The task manager invokes this hook before it creates observable task state
    or writes a workspace snapshot.  Keeping mandate validation ahead of the
    market-data binder also prevents a rejected request from materializing an
    artifact or a ``MdResearchDataBinding`` record.
    """

    async def prepare(
        intent_id: str,
        request: AIStrategyResearchRunRequest,
    ) -> AIStrategyResearchRunRequest:
        if not allow_server_continuation:
            _reject_client_continuation_fields(request)
        if trusted_auto_prompt is not None or trusted_auto_mandate_id is not None:
            request = await mandate_service.restore_auto_continuation_request(
                user_id,
                request,
                trusted_auto_prompt=trusted_auto_prompt,
                trusted_auto_mandate_id=trusted_auto_mandate_id,
            )
        mandate = await mandate_service.ensure_for_request(user_id, request)
        request = request.model_copy(update={"mandate_id": mandate.id})
        if binding_service is None:
            return request
        return await binding_service.bind_request(
            user_id=user_id,
            request=request,
            intent_id=intent_id,
        )

    return prepare


def _reject_client_continuation_fields(request: AIStrategyResearchRunRequest) -> None:
    """Reject internal continuation state on a fresh public research request.

    The dedicated task/run continuation routes rebuild this state from a
    trusted source. Accepting it on ``/run`` or ``/tasks`` would let browser
    text become LLM improvement feedback or redirect the strategy lineage.
    """
    if request.continuation_context:
        raise ValueError("AI_RESEARCH_CONTINUATION_CONTEXT_CLIENT_FORBIDDEN")
    if request.continue_from_run_id or request.seed_strategy_id:
        raise ValueError("AI_RESEARCH_CONTINUATION_LINEAGE_CLIENT_FORBIDDEN")


def _model_has_persisted_field(value: typing.Any, field: str) -> bool:
    """Return whether a Pydantic record actually persisted a field.

    Default values on legacy task snapshots and run records are not evidence
    that a source request was blank-auto.  ``model_fields_set`` preserves that
    distinction when an older persisted JSON object is parsed.
    """
    fields = getattr(value, "model_fields_set", None)
    if fields is None:
        fields = getattr(value, "__fields_set__", set())
    return field in fields


def _trusted_auto_continuation_source(
    *,
    prompt: typing.Any,
    workflow_mode: typing.Any,
    mandate_id: typing.Any,
    request_explicit_fields: typing.Any,
    explicit_fields_persisted: bool,
) -> tuple[str | None, str | None]:
    """Return a source prompt only when persisted metadata proves blank-auto.

    The browser may send a complete request as continuation overrides.  Its
    ``prompt`` is not trusted by itself: this helper only returns the prompt
    stored with a server-created source whose request explicitly omitted that
    field.  The mandate service still verifies the source mandate's auto-basis
    digest before removing the inherited text.
    """
    if not explicit_fields_persisted or str(workflow_mode or "").strip() != "auto":
        return None, None
    explicit_fields = (
        {str(item).strip() for item in request_explicit_fields if str(item).strip()}
        if isinstance(request_explicit_fields, (list, tuple, set))
        else set()
    )
    if "prompt" in explicit_fields:
        return None, None
    source_prompt = str(prompt or "").strip()
    source_mandate_id = str(mandate_id or "").strip()
    if not source_prompt or not source_mandate_id:
        return None, None
    return source_prompt, source_mandate_id


def _request_explicit_fields_are_server_persisted(value: typing.Any) -> bool:
    """Return whether a source carries the explicit-fields provenance marker.

    Pydantic fills missing legacy fields with defaults during API serialization,
    so the list alone cannot prove that an empty value was server persisted.
    Both the boolean marker and its own persisted-field evidence are required.
    """
    return bool(getattr(value, "request_explicit_fields_persisted", False)) and (
        _model_has_persisted_field(value, "request_explicit_fields_persisted")
        and _model_has_persisted_field(value, "request_explicit_fields")
    )


def _trusted_auto_continuation_source_from_task(
    task: AIStrategyResearchTaskResponse,
    *,
    user_id: str,
) -> tuple[str | None, str | None]:
    """Read a blank-auto source only from a task's persisted request snapshot."""
    workspace_id = str(task.research_workspace_id or "").strip()
    if not workspace_id or not verify_ai_research_task_snapshot(
        task,
        user_id=user_id,
        workspace_id=workspace_id,
    ):
        return None, None
    snapshot = task.request_snapshot if isinstance(task.request_snapshot, dict) else {}
    snapshot_mandate_id = str(snapshot.get("mandate_id") or "").strip()
    task_mandate_id = str(task.mandate_id or "").strip()
    if snapshot_mandate_id and task_mandate_id and snapshot_mandate_id != task_mandate_id:
        return None, None
    return _trusted_auto_continuation_source(
        prompt=snapshot.get("prompt"),
        workflow_mode=snapshot.get("workflow_mode"),
        mandate_id=snapshot_mandate_id or task_mandate_id,
        request_explicit_fields=task.request_explicit_fields,
        explicit_fields_persisted=_request_explicit_fields_are_server_persisted(task),
    )


def _trusted_auto_continuation_source_from_run_record(
    record: typing.Any,
    *,
    user_id: str,
) -> tuple[str | None, str | None]:
    """Read a blank-auto source only from a run record's persisted metadata."""
    if not isinstance(record, AIStrategyResearchRunRecord):
        return None, None
    workspace_id = str(record.research_workspace_id or "").strip()
    if not workspace_id or not verify_ai_research_run_record(
        record,
        user_id=user_id,
        workspace_id=workspace_id,
    ):
        return None, None
    return _trusted_auto_continuation_source(
        prompt=record.prompt,
        workflow_mode=record.workflow_mode,
        mandate_id=record.mandate_id,
        request_explicit_fields=record.request_explicit_fields,
        explicit_fields_persisted=_request_explicit_fields_are_server_persisted(record),
    )


async def _prepare_ai_research_run_request(
    binding_service: typing.Any | None,
    *,
    user_id: str,
    request: AIStrategyResearchRunRequest,
    mandate_service: InvestmentMandateService,
) -> AIStrategyResearchRunRequest:
    """Validate a run mandate before it can bind data or create workspace work."""
    preparer = _market_data_research_request_preparer(
        binding_service,
        user_id=user_id,
        mandate_service=mandate_service,
    )
    return await preparer(str(uuid.uuid4()), request)


def _market_data_binding_http_exception(error: Exception) -> HTTPException | None:
    """Translate stable binding failures without exposing internal traces."""
    code = str(getattr(error, "code", "") or "").strip()
    if not code:
        # The direct service guard intentionally uses ``ValueError`` so callers
        # outside HTTP do not depend on an API exception type.  Its message is
        # a stable code and is still safe to map at this boundary.
        code = str(error).strip()
    if code != _MARKET_DATA_BRIDGE_DISABLED_CODE and not code.startswith(
        _MARKET_DATA_BINDING_ERROR_PREFIX
    ):
        return None

    normalized = code.upper()
    if normalized.endswith(
        (
            "_ACCESS_DENIED",
            "_OWNER_DENIED",
            "_PERMISSION_DENIED",
            "_UNAUTHORIZED",
        )
    ):
        status_code = status.HTTP_403_FORBIDDEN
    elif any(
        token in normalized
        for token in (
            "UNAVAILABLE",
            "DISABLED",
            "SIGNING_KEY",
            "LOCAL_QUERY",
            "LOCAL_INCOMPLETE",
            "FETCH_FORBIDDEN",
            "PAGINATION_FORBIDDEN",
            "OHLC_REQUIRED",
            "NO_OBSERVATIONS",
            "WRITE_CONFLICT",
            "WRITE_FAILED",
        )
    ):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail={"code": code})


def _raise_ai_research_request_error(error: Exception) -> None:
    """Raise the bounded HTTP error for a known bridge failure, if any."""
    binding_error = _market_data_binding_http_exception(error)
    if binding_error is not None:
        raise binding_error from error


@lru_cache
def get_ai_strategy_research_config_profiles() -> typing.Any:
    return AIStrategyResearchConfigProfileService()


@lru_cache
def get_investment_mandate_service() -> typing.Any:
    return InvestmentMandateService()


@lru_cache
def get_research_pipeline_event_service() -> typing.Any:
    return ResearchPipelineEventService()


@lru_cache
def get_ai_strategy_research_version_service() -> typing.Any:
    return AIStrategyResearchVersionService()


@router.post("/", response_model=StrategyResponse, summary="Create strategy")
async def create_strategy(
    strategy: StrategyCreate,
    current_user: typing.Any = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
) -> typing.Any:
    """Create a new strategy.

    Args:
        strategy: Strategy payload.
        current_user: Authenticated user.
        service: Strategy service dependency.

    Returns:
        The created strategy.
    """
    result = await service.create_strategy(current_user.sub, strategy)
    return result


@router.get("/", response_model=StrategyListResponse, summary="List strategies")
@cache_response(ttl=30, key_prefix="strategies")
async def list_strategies(
    request: Request,
    current_user: typing.Any = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: str = Query(None, description="Filter by category"),
) -> typing.Any:
    """List strategies for the current user.

    Args:
        current_user: Authenticated user.
        service: Strategy service dependency.
        limit: Maximum number of records to return.
        offset: Number of records to skip.
        category: Optional category filter.

    Returns:
        List of strategies.
    """
    results = await service.list_strategies(current_user.sub, limit, offset, category)
    return results


@router.get("/templates", summary="Get strategy templates", response_model=None)
async def get_templates(
    category: str = Query(None, description="Filter by category"),
    strategy_type: str = Query(
        None, description="Filter by strategy type (backtest/simulate/live)"
    ),
    service: StrategyService = Depends(get_strategy_service),
) -> typing.Any:
    """Get built-in strategy templates (optionally filtered by category).

    Args:
        category: Optional category filter.
        strategy_type: Optional strategy type filter.
        service: Strategy service dependency.

    Returns:
        Dictionary containing templates and total count.
    """
    from app.schemas.strategy import StrategyType

    stype = None
    if strategy_type:
        try:
            stype = StrategyType(strategy_type)
        except ValueError as e:
            _logger.debug(f"Invalid strategy_type '{strategy_type}': {e}")

    templates = await service.get_templates(stype)
    if category:
        templates = [t for t in templates if t.category == category]
    return {"templates": templates, "total": len(templates)}


@router.get(
    "/templates/{template_id:path}/readme",
    summary="Get strategy README documentation",
    response_model=None,
)
async def get_template_readme(template_id: str) -> typing.Any:
    """Get the template README.md content (Markdown).

    Args:
        template_id: The strategy template identifier.

    Returns:
        Dictionary containing template_id and README content.

    Raises:
        HTTPException: If README not found.
    """
    readme = get_strategy_readme(template_id)
    if readme is None:
        raise HTTPException(status_code=404, detail="README not found")
    return {"template_id": template_id, "content": readme}


@router.get(
    "/templates/{template_id:path}/config",
    summary="Get strategy configuration",
    response_model=None,
)
async def get_template_config(template_id: str) -> typing.Any:
    """Read `config.yaml` for a strategy template.

    Args:
        template_id: The strategy template identifier.

    Returns:
        A dict containing:
        - strategy: name/description/author
        - params: parameter specs (including defaults)
        - data: data settings (symbol, data type)
        - backtest: backtest settings (initial cash, commission)

    Raises:
        HTTPException: If config file not found.
    """
    import yaml as _yaml

    try:
        config_path = get_strategy_dir(template_id) / "config.yaml"
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not config_path.is_file():
        raise HTTPException(status_code=404, detail="Strategy configuration file not found")

    with open(config_path, encoding="utf-8") as f:
        config = _yaml.safe_load(f) or {}

    return {
        "strategy_id": template_id,
        "strategy": config.get("strategy", {}),
        "params": config.get("params", {}),
        "data": config.get("data", {}),
        "backtest": config.get("backtest", {}),
    }


@router.get(
    "/templates/{template_id:path}", summary="Get strategy template detail", response_model=None
)
async def get_template_detail(template_id: str) -> typing.Any:
    """Get a single strategy template (includes code and params).

    Args:
        template_id: The strategy template identifier.

    Returns:
        The strategy template.

    Raises:
        HTTPException: If template not found.
    """
    template = get_template_by_id(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Strategy template not found")
    return template


@router.post(
    "/copilot/draft",
    response_model=StrategyCopilotDraftResponse,
    summary="Generate strategy copilot draft",
)
async def generate_strategy_copilot_draft(
    data: StrategyCopilotDraftRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
) -> typing.Any:
    """Generate a structured strategy draft from natural language input."""
    return await service.generate_copilot_draft(current_user.sub, data)


@router.post(
    "/ai-research/run",
    response_model=AIStrategyResearchRunResponse,
    summary="Run AI strategy research loop",
)
async def run_ai_strategy_research_loop(
    data: AIStrategyResearchRunRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    mandate_service: InvestmentMandateService = Depends(get_investment_mandate_service),
    binding_service: typing.Any | None = Depends(
        get_ai_strategy_research_market_data_binding_service
    ),
) -> typing.Any:
    """Generate, backtest, improve, and optionally start paper trading."""
    try:
        request = await _prepare_ai_research_run_request(
            binding_service,
            user_id=current_user.sub,
            request=data,
            mandate_service=mandate_service,
        )
        return redact_ai_strategy_research_payload(await service.run(current_user.sub, request))
    except Exception as exc:
        _raise_ai_research_request_error(exc)
        if not isinstance(exc, ValueError):
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ai-research/objectives/optimize",
    response_model=AIStrategyResearchObjectiveOptimizeResponse,
    summary="Optimize an AI strategy research objective with the configured model",
)
async def optimize_ai_strategy_research_objective(
    data: AIStrategyResearchObjectiveOptimizeRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchObjectiveOptimizer = Depends(
        get_ai_strategy_research_objective_optimizer
    ),
) -> typing.Any:
    """Refine a deterministic objective only when the user explicitly requests it."""
    try:
        return await service.optimize(current_user.sub, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ai-research/mandates",
    response_model=InvestmentMandateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Parse and confirm an AI investment research mandate",
)
async def create_ai_research_mandate(
    data: InvestmentMandateCreate,
    current_user: typing.Any = Depends(get_current_user),
    service: InvestmentMandateService = Depends(get_investment_mandate_service),
) -> typing.Any:
    """Create a structured investment demand before launching AI research."""
    return await service.create_mandate(current_user.sub, data)


@router.get(
    "/ai-research/mandates/{mandate_id}",
    response_model=InvestmentMandateResponse,
    summary="Get an AI investment research mandate",
)
async def get_ai_research_mandate(
    mandate_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: InvestmentMandateService = Depends(get_investment_mandate_service),
) -> typing.Any:
    """Return one confirmed investment mandate."""
    mandate = await service.get_mandate(current_user.sub, mandate_id)
    if mandate is None:
        raise HTTPException(status_code=404, detail="Investment mandate not found")
    return mandate


@router.get(
    "/ai-research/config-profiles",
    response_model=AIStrategyResearchConfigProfileListResponse,
    summary="List local AI strategy research configuration profiles",
)
async def list_ai_strategy_research_config_profiles(
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchConfigProfileService = Depends(
        get_ai_strategy_research_config_profiles
    ),
) -> typing.Any:
    """List reusable AI research form profiles from the local YAML file."""
    del current_user
    try:
        return await service.list_profiles()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ai-research/config-profiles",
    response_model=AIStrategyResearchConfigProfile,
    status_code=status.HTTP_201_CREATED,
    summary="Create a local AI strategy research configuration profile",
)
async def create_ai_strategy_research_config_profile(
    data: AIStrategyResearchConfigProfileCreate,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchConfigProfileService = Depends(
        get_ai_strategy_research_config_profiles
    ),
) -> typing.Any:
    """Create a reusable AI research form profile in the local YAML file."""
    del current_user
    try:
        return await service.create_profile(data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ai-research/config-profiles/import",
    response_model=AIStrategyResearchConfigProfileImportResponse,
    summary="Import AI strategy research configuration profiles from YAML",
)
async def import_ai_strategy_research_config_profiles(
    data: AIStrategyResearchConfigProfileImportRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchConfigProfileService = Depends(
        get_ai_strategy_research_config_profiles
    ),
) -> typing.Any:
    """Import selected YAML content into the local AI research profile file."""
    del current_user
    try:
        return await service.import_profiles(
            data.raw_yaml,
            fallback_name=data.name,
            fallback_profile_id=data.profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/ai-research/config-profiles/{profile_id}",
    response_model=AIStrategyResearchConfigProfile,
    summary="Get a local AI strategy research configuration profile",
)
async def get_ai_strategy_research_config_profile(
    profile_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchConfigProfileService = Depends(
        get_ai_strategy_research_config_profiles
    ),
) -> typing.Any:
    """Return one reusable AI research form profile."""
    del current_user
    try:
        profile = await service.get_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AI research config profile not found"
        )
    return profile


@router.put(
    "/ai-research/config-profiles/{profile_id}",
    response_model=AIStrategyResearchConfigProfile,
    summary="Update a local AI strategy research configuration profile",
)
async def update_ai_strategy_research_config_profile(
    profile_id: str,
    data: AIStrategyResearchConfigProfileUpdate,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchConfigProfileService = Depends(
        get_ai_strategy_research_config_profiles
    ),
) -> typing.Any:
    """Update a reusable AI research form profile in the local YAML file."""
    del current_user
    try:
        profile = await service.update_profile(profile_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AI research config profile not found"
        )
    return profile


@router.delete(
    "/ai-research/config-profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a local AI strategy research configuration profile",
    response_model=None,
)
async def delete_ai_strategy_research_config_profile(
    profile_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchConfigProfileService = Depends(
        get_ai_strategy_research_config_profiles
    ),
) -> typing.Any:
    """Delete a reusable AI research form profile from the local YAML file."""
    del current_user
    try:
        deleted = await service.delete_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AI research config profile not found"
        )


@router.post(
    "/ai-research/tasks",
    response_model=AIStrategyResearchTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit AI strategy research loop task",
)
async def submit_ai_strategy_research_task(
    data: AIStrategyResearchRunRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    task_manager: AIStrategyResearchTaskManager = Depends(get_ai_strategy_research_tasks),
    mandate_service: InvestmentMandateService = Depends(get_investment_mandate_service),
    binding_service: typing.Any | None = Depends(
        get_ai_strategy_research_market_data_binding_service
    ),
) -> typing.Any:
    """Submit a long-running AI research loop and poll it by task id."""
    try:
        request_preparer = _market_data_research_request_preparer(
            binding_service,
            user_id=current_user.sub,
            mandate_service=mandate_service,
        )
        submit_kwargs: dict[str, typing.Any] = {
            "service": service,
            "request_preparer": request_preparer,
        }
        return await task_manager.submit(current_user.sub, data, **submit_kwargs)
    except Exception as exc:
        _raise_ai_research_request_error(exc)
        if not isinstance(exc, ValueError):
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/ai-research/tasks",
    response_model=AIStrategyResearchTaskListResponse,
    summary="List AI strategy research tasks",
)
async def list_ai_strategy_research_tasks(
    current_user: typing.Any = Depends(get_current_user),
    task_manager: AIStrategyResearchTaskManager = Depends(get_ai_strategy_research_tasks),
    active_only: bool = Query(False, description="Only return non-terminal tasks"),
    limit: int = Query(20, ge=1, le=100),
) -> typing.Any:
    """List in-process AI research tasks for the authenticated user."""
    items = await task_manager.list_tasks(
        current_user.sub,
        active_only=active_only,
        limit=limit,
    )
    return AIStrategyResearchTaskListResponse(total=len(items), items=items)


@router.get(
    "/ai-research/tasks/{task_id}",
    response_model=AIStrategyResearchTaskResponse,
    summary="Get AI strategy research task status",
)
async def get_ai_strategy_research_task(
    task_id: str,
    current_user: typing.Any = Depends(get_current_user),
    task_manager: AIStrategyResearchTaskManager = Depends(get_ai_strategy_research_tasks),
) -> typing.Any:
    """Return task status and result when the AI research loop has finished."""
    task = await task_manager.get_task(current_user.sub, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="AI research task not found")
    return task


@router.post(
    "/ai-research/tasks/{task_id}/cancel",
    response_model=AIStrategyResearchTaskResponse,
    summary="Cancel AI strategy research task",
)
async def cancel_ai_strategy_research_task(
    task_id: str,
    current_user: typing.Any = Depends(get_current_user),
    task_manager: AIStrategyResearchTaskManager = Depends(get_ai_strategy_research_tasks),
) -> typing.Any:
    """Cancel a running AI research loop task."""
    task = await task_manager.cancel_task(current_user.sub, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="AI research task not found")
    return task


@router.post(
    "/ai-research/tasks/{task_id}/continue",
    response_model=AIStrategyResearchTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Continue AI strategy research from a task snapshot",
)
async def continue_ai_strategy_research_task(
    task_id: str,
    data: AIStrategyResearchTaskContinueRequest | None = None,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    task_manager: AIStrategyResearchTaskManager = Depends(get_ai_strategy_research_tasks),
    mandate_service: InvestmentMandateService = Depends(get_investment_mandate_service),
    binding_service: typing.Any | None = Depends(
        get_ai_strategy_research_market_data_binding_service
    ),
) -> typing.Any:
    """Submit a new research task rebuilt from a saved task snapshot."""
    try:
        source_task = await task_manager.get_task(current_user.sub, task_id)
        if source_task is None:
            raise HTTPException(status_code=404, detail="AI research task not found")
        trusted_auto_prompt, trusted_auto_mandate_id = _trusted_auto_continuation_source_from_task(
            source_task,
            user_id=current_user.sub,
        )
        request_preparer = _market_data_research_request_preparer(
            binding_service,
            user_id=current_user.sub,
            mandate_service=mandate_service,
            trusted_auto_prompt=trusted_auto_prompt,
            trusted_auto_mandate_id=trusted_auto_mandate_id,
            allow_server_continuation=True,
        )
        continue_kwargs: dict[str, typing.Any] = {
            "service": service,
            "request_preparer": request_preparer,
        }
        task = await task_manager.continue_task(
            current_user.sub,
            task_id,
            overrides=data.overrides if data is not None else {},
            **continue_kwargs,
        )
    except Exception as exc:
        _raise_ai_research_request_error(exc)
        if not isinstance(exc, ValueError):
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="AI research task not found")
    return task


@router.get(
    "/ai-research/runs",
    response_model=AIStrategyResearchRunListResponse,
    summary="List AI strategy research runs",
)
async def list_ai_strategy_research_runs(
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
    limit: int = Query(20, ge=1, le=100),
) -> typing.Any:
    """List persisted AI strategy research run records."""
    try:
        return await service.list_run_records(
            current_user.sub,
            research_workspace_id=research_workspace_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/ai-research/runs/{run_id}",
    response_model=AIStrategyResearchRunRecord,
    summary="Get AI strategy research run",
)
async def get_ai_strategy_research_run(
    run_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
) -> typing.Any:
    """Get one persisted AI strategy research run record."""
    try:
        record = await service.get_run_record(
            current_user.sub,
            run_id,
            research_workspace_id=research_workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AI research run not found"
        )
    return record


@router.get(
    "/ai-research/runs/{run_id}/timeline",
    response_model=ResearchTimelineResponse,
    summary="Get AI strategy research timeline",
)
async def get_ai_strategy_research_timeline(
    run_id: str,
    current_user: typing.Any = Depends(get_current_user),
    run_service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    event_service: ResearchPipelineEventService = Depends(get_research_pipeline_event_service),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
) -> typing.Any:
    """Return persisted stage events for a research run, with legacy fallback."""
    try:
        timeline = await event_service.list_events(
            current_user.sub,
            run_id,
            workspace_id=research_workspace_id,
        )
        if timeline.items:
            return timeline
        record = await run_service.get_run_record(
            current_user.sub,
            run_id,
            research_workspace_id=research_workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AI research run not found"
        )
    return event_service.synthesize_from_run_record(record)


@router.get(
    "/ai-research/runs/{run_id}/versions",
    response_model=AIStrategyResearchVersionListResponse,
    summary="List AI strategy research versions for a run",
)
async def list_ai_strategy_research_versions(
    run_id: str,
    current_user: typing.Any = Depends(get_current_user),
    run_service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    version_service: AIStrategyResearchVersionService = Depends(
        get_ai_strategy_research_version_service
    ),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
) -> typing.Any:
    """Return strategy code versions produced by a research run."""
    versions = await version_service.list_versions(current_user.sub, run_id)
    if versions.items:
        return versions
    try:
        record = await run_service.get_run_record(
            current_user.sub,
            run_id,
            research_workspace_id=research_workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AI research run not found"
        )
    return version_service.synthesize_from_run_record(record)


@router.get(
    "/ai-research/versions/{left_id}/compare/{right_id}",
    response_model=AIStrategyResearchVersionCompareResponse,
    summary="Compare two AI strategy research versions",
)
async def compare_ai_strategy_research_versions(
    left_id: str,
    right_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchVersionService = Depends(get_ai_strategy_research_version_service),
) -> typing.Any:
    """Compare metrics, gate status and code between two persisted AI research versions."""
    try:
        comparison = await service.compare_versions(current_user.sub, left_id, right_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if comparison is None:
        raise HTTPException(status_code=404, detail="AI research version not found")
    return comparison


@router.get(
    "/ai-research/versions/{version_id}",
    response_model=AIStrategyResearchVersionResponse,
    summary="Get one AI strategy research version",
)
async def get_ai_strategy_research_version(
    version_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchVersionService = Depends(get_ai_strategy_research_version_service),
) -> typing.Any:
    """Return one persisted AI research strategy version."""
    version = await service.get_version(current_user.sub, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="AI research version not found")
    return version


@router.post(
    "/ai-research/runs/{run_id}/continue",
    response_model=AIStrategyResearchTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Continue AI strategy research from a persisted run",
)
async def continue_ai_strategy_research_run(
    run_id: str,
    data: AIStrategyResearchRunContinueRequest | None = None,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    task_manager: AIStrategyResearchTaskManager = Depends(get_ai_strategy_research_tasks),
    mandate_service: InvestmentMandateService = Depends(get_investment_mandate_service),
    binding_service: typing.Any | None = Depends(
        get_ai_strategy_research_market_data_binding_service
    ),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
) -> typing.Any:
    """Submit a newly bound AI research task derived from a saved run record."""
    try:
        request = await service.build_continuation_request_from_run_record(
            current_user.sub,
            run_id,
            overrides=data.overrides if data is not None else {},
            research_workspace_id=research_workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if request is None:
        raise HTTPException(status_code=404, detail="AI research run not found")
    try:
        source_record = await service.get_run_record(
            current_user.sub,
            run_id,
            research_workspace_id=research_workspace_id,
            trusted_for_continuation=True,
        )
        trusted_auto_prompt, trusted_auto_mandate_id = (
            _trusted_auto_continuation_source_from_run_record(
                source_record,
                user_id=current_user.sub,
            )
            if source_record is not None
            else (None, None)
        )
        request_preparer = _market_data_research_request_preparer(
            binding_service,
            user_id=current_user.sub,
            mandate_service=mandate_service,
            trusted_auto_prompt=trusted_auto_prompt,
            trusted_auto_mandate_id=trusted_auto_mandate_id,
            allow_server_continuation=True,
        )
        submit_kwargs: dict[str, typing.Any] = {
            "service": service,
            "request_preparer": request_preparer,
        }
        return await task_manager.submit(current_user.sub, request, **submit_kwargs)
    except Exception as exc:
        _raise_ai_research_request_error(exc)
        if not isinstance(exc, ValueError):
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ai-research/runs/{run_id}/paper-trading",
    response_model=AIStrategyPaperTradingStart,
    summary="Start paper trading from an AI strategy research run",
)
async def start_ai_strategy_research_paper_trading(
    run_id: str,
    data: AIStrategyPaperTradingStartRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
) -> typing.Any:
    """Promote an achieved AI research run into paper trading."""
    try:
        return redact_ai_strategy_research_payload(
            await service.start_paper_trading_from_run(current_user.sub, run_id, data)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/ai-research/runs/{run_id}/paper-trading/review",
    response_model=AIStrategyPaperTradingReview,
    summary="Review paper trading validation for an AI strategy research run",
)
async def review_ai_strategy_research_paper_trading(
    run_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
) -> typing.Any:
    """Evaluate a promoted paper trading unit against its AI monitoring plan."""
    try:
        return redact_ai_strategy_research_payload(
            await service.review_paper_trading_run(
                current_user.sub,
                run_id,
                research_workspace_id=research_workspace_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/ai-research/runs/{run_id}/live-handoff",
    response_model=AIStrategyLiveHandoffPackage,
    summary="Build live handoff package for an AI strategy research run",
)
async def build_ai_strategy_research_live_handoff(
    run_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
) -> typing.Any:
    """Build a manual-approval package for a paper-trading live candidate."""
    try:
        return redact_ai_strategy_research_payload(
            await service.build_live_handoff_package(
                current_user.sub,
                run_id,
                research_workspace_id=research_workspace_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ai-research/runs/{run_id}/live-handoff/approval",
    response_model=AIStrategyLiveHandoffPackage,
    summary="Record manual approval for an AI strategy live handoff package",
)
async def approve_ai_strategy_research_live_handoff(
    run_id: str,
    data: AIStrategyLiveHandoffApprovalRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
) -> typing.Any:
    """Persist a human approval or rejection decision for a live handoff package."""
    try:
        return redact_ai_strategy_research_payload(
            await service.record_live_handoff_approval(
                current_user.sub,
                run_id,
                data,
                research_workspace_id=research_workspace_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ai-research/runs/{run_id}/live-trading/prepare",
    response_model=AIStrategyLiveTradingPrepare,
    summary="Prepare a locked live trading unit from an approved AI live handoff",
)
async def prepare_ai_strategy_research_live_trading(
    run_id: str,
    data: AIStrategyLiveTradingPrepareRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
) -> typing.Any:
    """Create a locked live trading unit after live handoff approval."""
    try:
        if research_workspace_id:
            data = data.model_copy(update={"research_workspace_id": research_workspace_id})
        return redact_ai_strategy_research_payload(
            await service.prepare_live_trading_from_run(current_user.sub, run_id, data)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ai-research/runs/{run_id}/live-trading/activate",
    response_model=AIStrategyLiveTradingPrepare,
    summary="Activate one approved AI live handoff through the server-only gate",
)
async def activate_ai_strategy_research_live_trading(
    run_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
) -> typing.Any:
    """Launch a prepared live handoff after final paper-evidence revalidation.

    Public workspace and instance start routes deliberately reject prepared
    handoffs.  This boundary owns the short-lived manager capability and
    restores the unit locks after the one server-authorized launch attempt.
    """
    try:
        return redact_ai_strategy_research_payload(
            await service.activate_prepared_live_trading_from_run(
                current_user.sub,
                run_id,
                research_workspace_id=research_workspace_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/ai-research/runs/{run_id}/live-trading/deactivate",
    response_model=AIStrategyLiveTradingPrepare,
    summary="Stop and revoke one AI live handoff through the server-only gate",
)
async def deactivate_ai_strategy_research_live_trading(
    run_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: AIStrategyResearchService = Depends(get_ai_strategy_research_service),
    research_workspace_id: str | None = Query(None, description="Optional research workspace ID"),
) -> typing.Any:
    """Stop protected execution and invalidate its prior approval atomically."""
    try:
        return redact_ai_strategy_research_payload(
            await service.deactivate_prepared_live_trading_from_run(
                current_user.sub,
                run_id,
                research_workspace_id=research_workspace_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/copilot/workspaces/{workspace_id}/units",
    response_model=StrategyDraftWorkspaceAddResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add strategy copilot draft to workspace",
)
async def add_strategy_copilot_draft_to_workspace(
    workspace_id: str,
    data: StrategyDraftWorkspaceAddRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
) -> typing.Any:
    """Persist a strategy draft and add it to a workspace unit."""
    try:
        result = await service.add_copilot_draft_to_workspace(current_user.sub, workspace_id, data)
    except MarketDataBindingUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code},
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Workspace or strategy not found")
    return result


@router.post(
    "/copilot/workspaces/{workspace_id}/backtest",
    response_model=StrategyCopilotBacktestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add strategy copilot draft to workspace and run backtest",
)
async def backtest_strategy_copilot_draft(
    workspace_id: str,
    data: StrategyCopilotBacktestRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
) -> typing.Any:
    """Persist a strategy draft, create a workspace unit, and trigger backtest."""
    try:
        result = await service.backtest_copilot_draft(current_user.sub, workspace_id, data)
    except MarketDataBindingUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code},
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Workspace or strategy not found")
    return result


@router.get("/{strategy_id}", response_model=StrategyResponse, summary="Get strategy detail")
async def get_strategy(
    strategy_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
) -> typing.Any:
    """Get a strategy detail by id.

    Args:
        strategy_id: The strategy ID.
        current_user: Authenticated user.
        service: Strategy service dependency.

    Returns:
        The strategy details.

    Raises:
        HTTPException: If strategy not found.
    """
    strategy = await service.get_strategy(strategy_id, current_user.sub)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse, summary="Update strategy")
async def update_strategy(
    strategy_id: str,
    strategy_update: StrategyUpdate,
    current_user: typing.Any = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
) -> typing.Any:
    """Update a strategy.

    Args:
        strategy_id: The strategy ID.
        strategy_update: Strategy update payload.
        current_user: Authenticated user.
        service: Strategy service dependency.

    Returns:
        The updated strategy.

    Raises:
        HTTPException: If strategy not found or no permission.
    """
    if await has_server_owned_ai_research_strategy_reference(strategy_id, current_user.sub):
        # StrategyService synchronizes code and parameter defaults directly
        # into the shared template consumed by paper unit runtime materialization.
        # A signed paper identity therefore freezes public template mutations.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "AI_RESEARCH_PAPER_STRATEGY_MUTATION_FORBIDDEN"},
        )
    try:
        result = await service.update_strategy(strategy_id, current_user.sub, strategy_update)
    except ValueError as exc:
        if str(exc) == "AI_RESEARCH_PAPER_STRATEGY_MUTATION_FORBIDDEN":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "AI_RESEARCH_PAPER_STRATEGY_MUTATION_FORBIDDEN"},
            ) from exc
        raise
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found or no permission to modify",
        )
    return result


@router.delete("/{strategy_id}", summary="Delete strategy", response_model=None)
async def delete_strategy(
    strategy_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
) -> typing.Any:
    """Delete a strategy.

    Args:
        strategy_id: The strategy ID.
        current_user: Authenticated user.
        service: Strategy service dependency.

    Returns:
        Success message.

    Raises:
        HTTPException: If strategy not found or no permission.
    """
    if await has_server_owned_ai_research_strategy_reference(strategy_id, current_user.sub):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "AI_RESEARCH_PAPER_STRATEGY_MUTATION_FORBIDDEN"},
        )
    try:
        success = await service.delete_strategy(strategy_id, current_user.sub)
    except ValueError as exc:
        if str(exc) == "AI_RESEARCH_PAPER_STRATEGY_MUTATION_FORBIDDEN":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "AI_RESEARCH_PAPER_STRATEGY_MUTATION_FORBIDDEN"},
            ) from exc
        raise
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found or no permission to delete",
        )
    return {"message": "Deleted successfully"}
