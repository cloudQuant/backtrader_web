"""Strategy CRUD service plus AI copilot orchestration.

The module-level helpers were moved to ``inference.py``, ``ai_draft.py`` and
``templates.py`` in iteration 174 (C5) to keep this file focused on the service
class. Public names are re-exported here so that legacy
``from app.services.strategy_service import X`` imports continue to work.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.sql_repository import SQLRepository
from app.models.strategy import Strategy
from app.schemas.strategy import (
    AIStrategyDraft,
    ParamSpec,
    StrategyCopilotBacktestRequest,
    StrategyCopilotBacktestResponse,
    StrategyCopilotDraftRequest,
    StrategyCopilotDraftResponse,
    StrategyCopilotRunResult,
    StrategyCreate,
    StrategyDraftWorkspaceAddRequest,
    StrategyDraftWorkspaceAddResponse,
    StrategyListResponse,
    StrategyResponse,
    StrategyTemplate,
    StrategyType,
    StrategyUpdate,
)
from app.services.strategy import ai_draft as _ai_draft
from app.services.strategy import inference as _inference
from app.services.strategy import templates as _templates
from app.services.strategy.ai_draft import build_ai_strategy_draft, render_ai_strategy_draft_answer
from app.services.strategy.templates import STRATEGIES_DIR
from app.utils.response_cache import invalidate_cache
from app.utils.tracing import business_span

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backward-compatible aliases (legacy private names).
# These keep external tests / callers that imported ``_xxx`` directly from
# ``app.services.strategy_service`` (which is sys.modules-aliased to this
# module) working without modification.
#
# The functions that consume ``STRATEGIES_DIR`` are wrapped (rather than
# straight aliased) so that ``monkeypatch.setattr(ss, "STRATEGIES_DIR", ...)``
# applied on the legacy module name keeps working: we forward the patched
# value to the implementation module before delegating.
# ---------------------------------------------------------------------------
_infer_category = _inference.infer_category
_strategy_name_from_prompt = _inference.strategy_name_from_prompt
_class_name_from_prompt = _inference.class_name_from_prompt
_infer_timeframe = _inference.infer_timeframe
_infer_data_source_type = _inference.infer_data_source_type
_build_ai_param_specs = _inference.build_ai_param_specs
_render_param_default = _inference.render_param_default
_strategy_param_defaults = _ai_draft.strategy_param_defaults
_get_templates_for_type = _templates._get_templates_for_type
_get_template_map = _templates._get_template_map


def _sync_strategies_dir() -> None:
    """Mirror ``core.STRATEGIES_DIR`` into the templates module.

    Some tests use ``monkeypatch.setattr(strategy_service, 'STRATEGIES_DIR', ...)``
    to redirect template scanning at a temporary directory. After the move to
    the strategy subpackage the templates module owns its own copy of
    ``STRATEGIES_DIR``, so we re-sync it on every entry point that reads it.
    """
    _templates.STRATEGIES_DIR = STRATEGIES_DIR


def _scan_strategies_folder(strategy_type: StrategyType) -> list[StrategyTemplate]:
    _sync_strategies_dir()
    return _templates.scan_strategies_folder(strategy_type)


def _sync_user_strategy_runtime_files(strategy: StrategyResponse) -> None:
    _sync_strategies_dir()
    _templates.sync_user_strategy_runtime_files(strategy)


def get_strategy_dir(strategy_id: str) -> Path:
    _sync_strategies_dir()
    return _templates.get_strategy_dir(strategy_id)


def get_strategy_readme(
    template_id: str, strategy_type: StrategyType | None = None
) -> str | None:
    _sync_strategies_dir()
    return _templates.get_strategy_readme(template_id, strategy_type)


def get_template_by_id(
    template_id: str, strategy_type: StrategyType | None = None
) -> StrategyTemplate | None:
    _sync_strategies_dir()
    # Bypass the lru_cache so monkeypatched STRATEGIES_DIR is honored
    # in unit tests; the production path calls this rarely enough that
    # the extra scan is acceptable.
    if strategy_type:
        for tpl in _templates.scan_strategies_folder(strategy_type):
            if tpl.id == template_id:
                return tpl
        return None
    for st in (StrategyType.backtest, StrategyType.simulate, StrategyType.live):
        for tpl in _templates.scan_strategies_folder(st):
            if tpl.id == template_id:
                return tpl
    return None


def get_all_strategy_templates() -> list[StrategyTemplate]:
    _sync_strategies_dir()
    return (
        list(_templates.scan_strategies_folder(StrategyType.backtest))
        + list(_templates.scan_strategies_folder(StrategyType.simulate))
        + list(_templates.scan_strategies_folder(StrategyType.live))
    )


__all__ = [
    "STRATEGIES_DIR",
    "StrategyService",
    "build_ai_strategy_draft",
    "get_all_strategy_templates",
    "get_strategy_dir",
    "get_strategy_readme",
    "get_template_by_id",
    "render_ai_strategy_draft_answer",
]


class StrategyService:
    """Service for managing user-defined strategies."""

    def __init__(self) -> None:
        """Initialize the StrategyService.

        Attributes:
            strategy_repo: Repository for strategy CRUD operations.
        """
        self.strategy_repo = SQLRepository(Strategy)

    async def create_strategy(
        self, user_id: str, strategy_create: StrategyCreate
    ) -> StrategyResponse:
        """Create a new user strategy.

        Args:
            user_id: The ID of the user creating the strategy.
            strategy_create: Strategy creation data.

        Returns:
            StrategyResponse: The created strategy.
        """
        # Iteration 175 §5.2 — backtrader.strategy.submit business span.
        # ``submit`` here is the user-initiated act of registering a strategy
        # (the term aligns with design §5 phase set ``{submit, version_create}``).
        with business_span("backtrader.strategy.submit", user_id=user_id):
            strategy = Strategy(
                user_id=user_id,
                name=strategy_create.name,
                description=strategy_create.description,
                code=strategy_create.code,
                params={k: v.model_dump() for k, v in strategy_create.params.items()},
                category=strategy_create.category,
            )

            strategy = await self.strategy_repo.create(strategy)
            response = self._to_response(strategy)
            _sync_user_strategy_runtime_files(response)
            await invalidate_cache("strategies")
            return response

    async def generate_copilot_draft(
        self, user_id: str, request: StrategyCopilotDraftRequest
    ) -> StrategyCopilotDraftResponse:
        """Generate a structured strategy draft for the copilot flow."""
        if request.knowledge_base_id:
            from app.services.rag_service import RAGService

            rag_result = await RAGService().ask(
                request.knowledge_base_id,
                user_id,
                request.prompt,
                top_k=10,
                min_similarity=0.0,
                assistant_mode="backtrader_strategy",
                thinking_mode=request.thinking_mode,
            )
            draft_payload = rag_result.get("strategy_draft")
            draft = (
                AIStrategyDraft.model_validate(draft_payload)
                if draft_payload
                else build_ai_strategy_draft(request.prompt)
            )
            answer = rag_result.get("answer") or render_ai_strategy_draft_answer(draft)
            return StrategyCopilotDraftResponse(
                answer=answer,
                strategy_draft=draft,
                citations=rag_result.get("citations") or [],
                context_chunks_used=int(rag_result.get("context_chunks_used") or 0),
                tokens_used=int(rag_result.get("tokens_used") or 0),
                model_id=rag_result.get("model_id"),
                reasoning=rag_result.get("reasoning"),
            )

        draft = build_ai_strategy_draft(request.prompt)
        return StrategyCopilotDraftResponse(
            answer=render_ai_strategy_draft_answer(draft),
            strategy_draft=draft,
            citations=[],
            context_chunks_used=0,
            tokens_used=0,
            model_id=None,
            reasoning=None,
        )

    async def add_copilot_draft_to_workspace(
        self, user_id: str, workspace_id: str, request: StrategyDraftWorkspaceAddRequest
    ) -> StrategyDraftWorkspaceAddResponse | None:
        """Persist a copilot draft and add it into a workspace unit."""
        from app.schemas.workspace import StrategyUnitCreate
        from app.services.workspace_service import WorkspaceService

        workspace_service = WorkspaceService()
        workspace = await workspace_service.get_workspace(workspace_id, user_id)
        if workspace is None:
            return None

        if request.strategy_id:
            strategy = await self.get_strategy(request.strategy_id, user_id)
            if strategy is None:
                return None
            created_strategy = False
        else:
            strategy = await self.create_strategy(
                user_id,
                StrategyCreate(
                    name=request.strategy_draft.name,
                    description=request.strategy_draft.description,
                    code=request.strategy_draft.code,
                    params=request.strategy_draft.params,
                    category=request.strategy_draft.category,
                ),
            )
            created_strategy = True

        _sync_user_strategy_runtime_files(strategy)

        strategy_params = {
            name: spec.default for name, spec in request.strategy_draft.params.items()
        }
        timeframe = (
            request.timeframe
            or request.strategy_draft.data_source.timeframe
            or request.strategy_draft.suggested_timeframe
            or "1d"
        )
        symbol = (
            request.symbol
            or request.strategy_draft.data_source.symbol
            or request.strategy_draft.suggested_symbol
            or ""
        )
        symbol_name = request.symbol_name or symbol
        data_config = {
            "symbol": symbol,
            "symbol_name": symbol_name,
            "timeframe": timeframe,
            "timeframe_n": request.timeframe_n or request.strategy_draft.data_source.timeframe_n,
            "start_date": request.strategy_draft.data_source.start_date,
            "end_date": request.strategy_draft.data_source.end_date,
            "adjustment": request.strategy_draft.data_source.adjustment,
            **request.data_config,
        }

        unit = await workspace_service.create_unit(
            workspace_id,
            user_id,
            StrategyUnitCreate(
                group_name=request.group_name or request.strategy_draft.name,
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                symbol=symbol,
                symbol_name=symbol_name,
                timeframe=timeframe,
                timeframe_n=request.timeframe_n,
                category=request.strategy_draft.category,
                data_config=data_config,
                unit_settings=request.unit_settings,
                params=strategy_params,
                optimization_config=request.optimization_config,
            ),
        )
        if unit is None:
            return None

        return StrategyDraftWorkspaceAddResponse(
            workspace_id=workspace.id,
            created_strategy=created_strategy,
            strategy=strategy,
            unit=unit,
        )

    async def backtest_copilot_draft(
        self, user_id: str, workspace_id: str, request: StrategyCopilotBacktestRequest
    ) -> StrategyCopilotBacktestResponse | None:
        """Persist a copilot draft, add it to workspace, and trigger backtest."""
        from app.schemas.workspace import UnitStatusResponse
        from app.services.workspace_service import WorkspaceService

        workspace_service = WorkspaceService()
        added = await self.add_copilot_draft_to_workspace(user_id, workspace_id, request)
        if added is None:
            return None

        run_results = await workspace_service.run_units(
            workspace_id,
            user_id,
            [added.unit.id],
            parallel=request.parallel,
        )
        run_result_payload = next(
            (item for item in run_results if str(item.get("unit_id")) == added.unit.id),
            None,
        )
        if run_result_payload is None:
            run_result_payload = {
                "unit_id": added.unit.id,
                "task_id": None,
                "status": "failed",
                "error": "Backtest task submission failed",
            }

        unit_status = None
        statuses = await workspace_service.get_units_status(workspace_id, user_id)
        if statuses:

            def _status_id(item: Any) -> str:
                if isinstance(item, dict):
                    return str(item.get("id"))
                return str(getattr(item, "id", ""))

            matched = next(
                (item for item in statuses if _status_id(item) == added.unit.id), None
            )
            if matched is not None:
                unit_status = (
                    matched
                    if isinstance(matched, UnitStatusResponse)
                    else UnitStatusResponse.model_validate(matched)
                )

        report = None
        report_ready = False
        if (
            request.report_config is not None
            and unit_status is not None
            and str(unit_status.run_status) == "completed"
        ):
            cfg = request.report_config
            report = await workspace_service.get_workspace_report(
                workspace_id,
                user_id,
                start_date=cfg.start_date,
                end_date=cfg.end_date,
                max_cash=cfg.max_cash,
                calc_method=cfg.calc_method,
                annual_days=cfg.annual_days,
                weight_mode=cfg.weight_mode,
                weights=cfg.weights,
            )
            report_ready = report is not None

        return StrategyCopilotBacktestResponse(
            workspace_id=workspace_id,
            created_strategy=added.created_strategy,
            strategy=added.strategy,
            unit=added.unit,
            run_result=StrategyCopilotRunResult.model_validate(run_result_payload),
            unit_status=unit_status,
            report_ready=report_ready,
            report=report,
        )

    async def _get_owned_strategy(self, strategy_id: str, user_id: str) -> Strategy | None:
        strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy or strategy.user_id != user_id:
            return None
        return strategy

    async def get_strategy(
        self, strategy_id: str, user_id: str | None = None
    ) -> StrategyResponse | None:
        """Get strategy details by ID.

        Args:
            strategy_id: The unique identifier for the strategy.
            user_id: Optional owner identifier used to enforce access control.

        Returns:
            StrategyResponse if found and accessible, None otherwise.
        """
        if user_id is not None:
            strategy = await self._get_owned_strategy(strategy_id, user_id)
        else:
            strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy:
            return None
        return self._to_response(strategy)

    async def update_strategy(
        self, strategy_id: str, user_id: str, strategy_update: StrategyUpdate
    ) -> StrategyResponse | None:
        """Update an existing strategy.

        Args:
            strategy_id: The unique identifier for the strategy.
            user_id: The ID of the user requesting the update.
            strategy_update: Strategy update data.

        Returns:
            Updated StrategyResponse if successful, None if not found
            or unauthorized.
        """
        strategy = await self._get_owned_strategy(strategy_id, user_id)
        if strategy is None:
            return None

        update_data: dict[str, object] = {}
        if strategy_update.name is not None:
            update_data["name"] = strategy_update.name
        if strategy_update.description is not None:
            update_data["description"] = strategy_update.description
        if strategy_update.code is not None:
            update_data["code"] = strategy_update.code
        if strategy_update.params is not None:
            update_data["params"] = {
                k: v.model_dump() for k, v in strategy_update.params.items()
            }
        if strategy_update.category is not None:
            update_data["category"] = strategy_update.category

        if update_data:
            update_data["updated_at"] = datetime.now(timezone.utc)
            updated = await self.strategy_repo.update(strategy_id, update_data)
            if updated is not None:
                strategy = updated
        response = self._to_response(strategy)
        _sync_user_strategy_runtime_files(response)
        await invalidate_cache("strategies")
        return response

    async def delete_strategy(self, strategy_id: str, user_id: str) -> bool:
        """Delete a strategy.

        Args:
            strategy_id: The unique identifier for the strategy.
            user_id: The ID of the user requesting deletion.

        Returns:
            True if deletion succeeded, False if not found or unauthorized.
        """
        strategy = await self._get_owned_strategy(strategy_id, user_id)
        if strategy is None:
            return False

        result = await self.strategy_repo.delete(strategy_id)
        if result:
            await invalidate_cache("strategies")
        return result

    async def list_strategies(
        self, user_id: str, limit: int = 20, offset: int = 0, category: str | None = None
    ) -> StrategyListResponse:
        """List user strategies with optional filtering.

        Args:
            user_id: The ID of the user.
            limit: Maximum number of results to return.
            offset: Number of results to skip.
            category: Optional category filter.

        Returns:
            StrategyListResponse containing total count and list of strategies.
        """
        filters = {"user_id": user_id}
        if category:
            filters["category"] = category

        strategies = await self.strategy_repo.list(filters=filters, skip=offset, limit=limit)
        total = await self.strategy_repo.count(filters=filters)

        items = [self._to_response(s) for s in strategies]

        return StrategyListResponse(total=total, items=items)

    async def get_templates(
        self, strategy_type: StrategyType | None = None
    ) -> list[StrategyTemplate]:
        """Get all available strategy templates.

        Args:
            strategy_type: Optional filter by strategy type.

        Returns:
            List of StrategyTemplate objects.
        """
        if strategy_type == StrategyType.backtest:
            return list(_get_templates_for_type(StrategyType.backtest)[0])
        elif strategy_type == StrategyType.simulate:
            return list(_get_templates_for_type(StrategyType.simulate)[0])
        elif strategy_type == StrategyType.live:
            return list(_get_templates_for_type(StrategyType.live)[0])

        all_templates = (
            list(_get_templates_for_type(StrategyType.backtest)[0])
            + list(_get_templates_for_type(StrategyType.simulate)[0])
            + list(_get_templates_for_type(StrategyType.live)[0])
        )
        return all_templates

    def _to_response(self, strategy: Strategy) -> StrategyResponse:
        """Convert strategy model to response format.

        Args:
            strategy: The Strategy model instance.

        Returns:
            StrategyResponse with formatted data.
        """
        params = {}
        if strategy.params:
            for k, v in strategy.params.items():
                if isinstance(v, ParamSpec):
                    params[k] = v
                elif isinstance(v, dict):
                    params[k] = ParamSpec(**v)
                else:
                    if isinstance(v, bool):
                        ptype = "bool"
                    elif isinstance(v, int):
                        ptype = "int"
                    elif isinstance(v, float):
                        ptype = "float"
                    else:
                        ptype = "string"
                    params[k] = ParamSpec(
                        type=ptype, default=v, min=None, max=None, options=None, description=k
                    )

        return StrategyResponse(
            id=strategy.id,
            user_id=strategy.user_id,
            name=strategy.name,
            description=strategy.description,
            code=strategy.code,
            params=params,
            category=strategy.category,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
        )
