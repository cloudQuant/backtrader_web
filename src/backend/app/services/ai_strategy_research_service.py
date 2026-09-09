"""AI-driven strategy research loop orchestration."""

from __future__ import annotations

# Backwards-compatible research service facade; workflow helpers come from ``research``.
# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405
import re
import uuid

from app.config import get_settings, production_security_mode
from app.schemas.market_data_trust import DataPrecheckRequest
from app.services import research as _research_helpers
from app.services.ai_research_provenance import (
    AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_FIELD,
    AI_RESEARCH_PAPER_RUNTIME_METRICS_OBSERVATION_FIELD,
    issue_ai_research_live_handoff_unit_anchor,
    issue_ai_research_paper_runtime_anchor,
    sign_ai_research_run_record,
    verify_ai_research_live_handoff_unit_anchor,
    verify_ai_research_paper_runtime_metrics_observation,
    verify_ai_research_run_record,
)
from app.services.live_trading.metadata import (
    SERVER_RUNTIME_LAUNCH_ID_FIELD,
    SERVER_RUNTIME_LAUNCH_STARTED_AT_FIELD,
)
from app.services.live_trading_manager import get_live_trading_manager
from app.services.market_data_precheck_service import get_market_data_precheck_service
from app.services.research.shared import *
from app.utils.logger import get_logger
from app.utils.tracing import business_span

logger = get_logger(__name__)

_MARKET_DATA_BINDING_KEY_PREFIX = "market_data_binding_"
_MARKET_DATA_RUNTIME_BINDING_KEY = "market_data_binding"
_MARKET_DATA_REQUIRED_BINDING_KEYS = frozenset(
    {
        "market_data_binding_id",
        "market_data_binding_hash",
        "market_data_binding_signature",
        "market_data_binding_intent_id",
        "market_data_binding_required",
    }
)
_MARKET_DATA_BINDING_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_MARKET_DATA_BINDING_SIGNATURE_BODY_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
_MARKET_DATA_BINDING_INTENT_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")


def _trusted_historic_run_record_for_stop(
    workspace: WorkspaceResponse,
    *,
    user_id: str,
    run_id: str,
    source_signature: str,
) -> AIStrategyResearchRunRecord | None:
    """Return one verified historical revision for a stop-only recovery.

    This is intentionally not the normal trusted-record lookup.  Normal
    state-changing flows require the matching canonical ``last_run`` so a
    stale approved history row can never be selected for activation.  A
    protected process that was already launched still needs a way to be
    stopped after a later run displaces that pointer.  The live-unit anchor
    proves which run is being stopped; this helper merely finds an HMAC-valid
    row to carry the durable stop-pending/revoked transition.
    """
    normalized_run_id = str(run_id or "").strip()
    workspace_id = str(workspace.id or "").strip()
    expected_signature = str(source_signature or "").strip()
    if not normalized_run_id or not workspace_id or not expected_signature:
        return None
    settings = dict(workspace.settings or {})
    ai_research = settings.get("ai_research")
    if not isinstance(ai_research, dict):
        return None

    raw_candidates: list[Any] = []
    raw_last = ai_research.get("last_run")
    if isinstance(raw_last, dict):
        raw_candidates.append(raw_last)
    raw_runs = ai_research.get("runs")
    if isinstance(raw_runs, list):
        raw_candidates.extend(item for item in raw_runs if isinstance(item, dict))

    verified: dict[str, AIStrategyResearchRunRecord] = {}
    for raw in raw_candidates:
        if (
            str(raw.get("run_id") or "").strip() != normalized_run_id
            or not verify_ai_research_run_record(
                raw,
                user_id=user_id,
                workspace_id=workspace_id,
            )
        ):
            continue
        record = _coerce_research_run_record_raw(raw)
        if record is None or str(record.research_workspace_id or "").strip() != workspace_id:
            continue
        signature = str(record.server_provenance_signature or "").strip()
        if signature:
            verified.setdefault(signature, record)

    # The original launch revision is ideal.  Paper-target invalidation can
    # legitimately re-sign this same run without its now-stale live ids; if
    # the durable history has exactly one valid current revision, it remains
    # safe to use it *only* for revocation.  Any unresolved multi-revision
    # conflict fails closed instead of selecting an old approval by rank.
    if expected_signature in verified:
        return verified[expected_signature]
    return next(iter(verified.values())) if len(verified) == 1 else None


def _paper_runtime_observation_payload(
    instance_id: str | None,
    started_at: str | None,
    launch_id: str | None,
) -> dict[str, str] | None:
    """Return the signed, non-reusable manager epoch used for paper readiness.

    ``started_at`` is only second precision in the persisted instance store, so
    it cannot distinguish a stop/restart that occurs in one second.  The
    execution service emits a fresh server-only UUID at every successful
    spawn; binding it to the review record prevents a restarted process from
    inheriting an earlier ready or approved observation window.
    """
    normalized_instance_id = str(instance_id or "").strip()
    normalized_started_at = str(started_at or "").strip()
    normalized_launch_id = str(launch_id or "").strip()
    try:
        canonical_launch_id = uuid.UUID(normalized_launch_id).hex
    except (AttributeError, TypeError, ValueError):
        return None
    parsed_started_at = _parse_utc_datetime(normalized_started_at)
    if (
        not normalized_instance_id
        or parsed_started_at is None
        or parsed_started_at > datetime.now(timezone.utc)
    ):
        return None
    return {
        "source": "server_live_trading_manager",
        "instance_id": normalized_instance_id,
        "started_at": normalized_started_at,
        "launch_id": canonical_launch_id,
    }


def _paper_runtime_observation_from_handoff(
    handoff: dict[str, Any] | None,
) -> dict[str, str] | None:
    raw = _dict_payload((handoff or {}).get("paper_runtime_observation"))
    return _paper_runtime_observation_payload(
        str(raw.get("instance_id") or ""),
        str(raw.get("started_at") or ""),
        str(raw.get("launch_id") or ""),
    )


def _paper_handoff_with_runtime_observation(
    handoff: dict[str, Any] | None,
    observation: dict[str, str] | None,
) -> dict[str, Any]:
    """Persist only a current server manager epoch in the signed run record."""
    payload = dict(handoff or {})
    if observation is None:
        payload.pop("paper_runtime_observation", None)
    else:
        payload["paper_runtime_observation"] = dict(observation)
    return payload


def _paper_runtime_metrics_observation_is_trusted(
    *,
    user_id: str,
    unit: StrategyUnitResponse | None,
    unit_status: UnitStatusResponse | None,
    instance_id: str | None,
    launch_id: str | None,
) -> bool:
    """Require metrics produced after this exact server-issued launch.

    A manager epoch says the process is alive, not that its current metrics
    were produced by that process.  The post-fill writer signs a receipt over
    the metrics payload and launch UUID; old log metrics therefore cannot be
    promoted after a stop/restart, including when the observation window is
    configured as zero days.
    """
    if unit is None:
        return False
    settings = unit.unit_settings if isinstance(unit.unit_settings, dict) else {}
    receipt = settings.get(AI_RESEARCH_PAPER_RUNTIME_METRICS_OBSERVATION_FIELD)
    metrics = (
        _dict_payload(unit_status.metrics_snapshot)
        if unit_status is not None and isinstance(unit_status.metrics_snapshot, dict)
        else _dict_payload(unit.metrics_snapshot)
    )
    if not metrics:
        return False
    return verify_ai_research_paper_runtime_metrics_observation(
        receipt,
        user_id=user_id,
        paper_workspace_id=str(unit.workspace_id),
        paper_unit_id=str(unit.id),
        instance_id=str(instance_id or unit.trading_instance_id or ""),
        launch_id=str(launch_id or ""),
        metrics_snapshot=metrics,
    )


def _apply_market_data_research_binding_guard(
    request: AIStrategyResearchRunRequest,
) -> AIStrategyResearchRunRequest:
    """Require a structurally valid server-issued v2 binding when enabled.

    The API/task boundary obtains this binding from the strict local-only
    market-data service before any workspace exists.  Direct service callers
    still need a fail-closed guard, but this layer deliberately does not claim
    to revalidate database facts, artifact bytes, or the signature; the
    isolated runtime loader performs those checks immediately before it reads
    the bound CSV.  Validation windows may narrow the server-bound interval
    only through the runtime's signed binding semantics.
    """
    data_config = request.data_config
    has_market_data_bridge_markers = isinstance(data_config, dict) and any(
        str(key).casefold() == "market_data_asset_type"
        or str(key).casefold() == _MARKET_DATA_RUNTIME_BINDING_KEY
        or str(key).casefold().startswith(_MARKET_DATA_BINDING_KEY_PREFIX)
        for key in data_config
    )
    settings = get_settings()
    bridge_enabled = bool(getattr(settings, "MARKET_DATA_QUERY_V2_ENABLED", False)) and bool(
        getattr(settings, "MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_ENABLED", False)
    )
    if not bridge_enabled:
        if has_market_data_bridge_markers:
            raise ValueError("MARKET_DATA_BRIDGE_DISABLED")
        return request

    if not isinstance(data_config, dict):
        raise ValueError("MARKET_DATA_BINDING_REQUIRED")

    binding_keys = {
        str(key)
        for key in data_config
        if str(key).casefold().startswith(_MARKET_DATA_BINDING_KEY_PREFIX)
    }
    if binding_keys - _MARKET_DATA_REQUIRED_BINDING_KEYS:
        raise ValueError("MARKET_DATA_BINDING_INVALID")
    if binding_keys != _MARKET_DATA_REQUIRED_BINDING_KEYS:
        raise ValueError("MARKET_DATA_BINDING_REQUIRED")
    if data_config.get("market_data_binding_required") is not True:
        raise ValueError("MARKET_DATA_BINDING_INVALID")

    binding_id = data_config.get("market_data_binding_id")
    try:
        uuid.UUID(str(binding_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("MARKET_DATA_BINDING_INVALID") from exc

    binding_hash = str(data_config.get("market_data_binding_hash") or "")
    if _MARKET_DATA_BINDING_HASH_PATTERN.fullmatch(binding_hash) is None:
        raise ValueError("MARKET_DATA_BINDING_INVALID")

    signature = data_config.get("market_data_binding_signature")
    if not isinstance(signature, str) or not signature.strip() or len(signature) > 16384:
        raise ValueError("MARKET_DATA_BINDING_INVALID")
    signature_body, separator, signature_digest = signature.strip().partition(".")
    if (
        not separator
        or "." in signature_digest
        or _MARKET_DATA_BINDING_SIGNATURE_BODY_PATTERN.fullmatch(signature_body) is None
        or _MARKET_DATA_BINDING_HASH_PATTERN.fullmatch(signature_digest) is None
    ):
        raise ValueError("MARKET_DATA_BINDING_INVALID")
    intent_id = data_config.get("market_data_binding_intent_id")
    if (
        not isinstance(intent_id, str)
        or _MARKET_DATA_BINDING_INTENT_PATTERN.fullmatch(intent_id.strip()) is None
    ):
        raise ValueError("MARKET_DATA_BINDING_INVALID")
    return request


def _apply_production_promotion_guards(
    request: AIStrategyResearchRunRequest,
) -> AIStrategyResearchRunRequest:
    """Force server-side paper-promotion guards in production.

    Request validation keeps the two robustness flags internally consistent, but
    the public service boundary is the authority for a production promotion.
    This prevents direct service callers from using a stale or crafted model to
    bypass validation before a paper unit is created.
    """
    if not request.start_paper_trading or not production_security_mode(get_settings()):
        return request
    return request.model_copy(
        update={
            "robustness_validation": True,
            "require_robustness_validation": True,
        }
    )


async def _apply_production_data_precheck(
    request: AIStrategyResearchRunRequest,
) -> AIStrategyResearchRunRequest:
    """Fail closed before an AI-research run can create workspace work in production.

    The interactive precheck is useful feedback, but it cannot authorize a
    promotion.  Persisting the successful server-side result in ``data_config``
    keeps the generated unit and its audit timeline tied to the exact check.
    """
    if not production_security_mode(get_settings()):
        return request
    try:
        precheck = await get_market_data_precheck_service().precheck(
            DataPrecheckRequest(
                asset_type=str(request.data_config.get("asset_type") or "") or None,
                symbol=request.symbol,
                timeframe=request.timeframe,
                provider=str(request.data_config.get("data_provider") or "") or None,
                start_date=request.start_date,
                end_date=request.end_date,
            )
        )
    except Exception as exc:
        raise ValueError("AI research data precheck is unavailable; promotion is blocked") from exc
    if not precheck.passed:
        reasons = "; ".join(precheck.reasons) or "data precheck failed"
        raise ValueError(f"AI research data precheck failed: {reasons}")
    return request.model_copy(
        update={
            "data_config": {
                **request.data_config,
                "data_precheck": precheck.model_dump(mode="json"),
            }
        }
    )


class LocalStrategyImprover:
    """Deterministic local/test fallback for the AI strategy improver contract."""

    async def improve(
        self,
        draft: AIStrategyDraft,
        *,
        iteration: int,
        metrics: dict[str, Any],
        target_sharpe: float,
        quality_gate_failures: list[str] | None = None,
        user_id: str | None = None,
        request: AIStrategyResearchRunRequest | None = None,
    ) -> StrategyImprovement:
        improved = draft.model_copy(deep=True)
        notes: list[str] = []
        failures = [str(item) for item in quality_gate_failures or []]
        research_feedback = _dict_payload(metrics.get("research_feedback"))
        failure_categories = {
            str(item)
            for item in [
                *_string_list(metrics.get("failure_categories")),
                *_string_list(research_feedback.get("failure_categories")),
            ]
            if str(item).strip()
        }
        sharpe = _metric_float(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
        max_drawdown = _metric_float(metrics, "max_drawdown", "maxDrawdown", default=0.0)
        total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
        drawdown_failed = "drawdown" in failure_categories or any(
            "drawdown" in item.lower() or "回撤" in item for item in failures
        )
        out_of_sample_failed = "out_of_sample" in failure_categories
        robustness_failed = "robustness" in failure_categories
        execution_cost_failed = "execution_cost" in failure_categories
        valuation_context_failed = "valuation_context" in failure_categories
        live_handoff_rejected = "live_handoff_rejected" in failure_categories
        iteration_progress = _dict_payload(metrics.get("iteration_progress"))
        progress_status = str(iteration_progress.get("status") or "").strip().lower()
        regressed = progress_status == "regressed"
        stalled = progress_status == "stalled"
        suffix = f" v{iteration + 1}"
        base_name = re.sub(r"\s+v\d+$", "", improved.name).strip()
        improved.name = f"{base_name}{suffix}"[:100]
        improved.description = (
            f"{improved.description or ''}\n"
            f"AI research revision {iteration + 1}: previous Sharpe {sharpe:.3f}, "
            f"target {target_sharpe:.3f}."
        ).strip()
        trade_count_failed = (
            (request is not None and total_trades < max(int(request.min_total_trades), 1))
            or "trade_count" in failure_categories
            or any("trade" in item.lower() or "交易" in item for item in failures)
        )
        if trade_count_failed and request is not None:
            rebuilt = build_ai_strategy_draft(request.prompt)
            improved = _normalize_research_draft(rebuilt, request)
            improved.name = f"{base_name}{suffix}"[:100]
            improved.description = (
                f"{improved.description or ''}\n"
                f"AI research revision {iteration + 1}: rebuilt after trade-count failure; "
                f"previous closed trades {total_trades}, target {request.min_total_trades}."
            ).strip()
            notes.append(
                "上一轮缺少闭合交易，本轮重建为带止损、止盈和最长持仓退出的基础模板，"
                "优先生成可计数的完成交易。"
            )

        params = improved.params
        if regressed:
            notes.append("上一轮自动改稿相对前一轮退化，本轮切换为保守修复。")
        elif stalled:
            notes.append("上一轮自动改稿基本停滞，本轮将扩大信号和风控结构调整幅度。")
        if out_of_sample_failed:
            notes.append("样本外验证未通过，本轮降低参数敏感度并优先保留稳健信号。")
        if robustness_failed:
            notes.append("稳健性验证未通过，本轮降低过拟合和参数敏感性风险。")
        if execution_cost_failed:
            notes.append("执行成本或滑点压力偏高，本轮降低换手和无效交易。")
        if valuation_context_failed:
            notes.append("资产规格或估值上下文存在风险，本轮保留交易约束并避免扩大杠杆暴露。")
        if live_handoff_rejected:
            notes.append("实盘交接人工审批未通过，本轮按审批意见降低上线风险并重新验证。")

        if "risk_pct" in params:
            current = _param_float(params["risk_pct"], 0.01)
            risk_scale = (
                0.65
                if regressed
                else 0.7
                if live_handoff_rejected
                else 0.75
                if out_of_sample_failed
                else 0.8
            )
            next_value = max(round(current * risk_scale, 5), 0.001)
            _set_param_default(params, "risk_pct", next_value)
            notes.append(f"将单笔风险从 {current:g} 下调到 {next_value:g}")

        if "stop_loss_pct" in params and (max_drawdown < -10 or drawdown_failed):
            current = _param_float(params["stop_loss_pct"], 0.05)
            stop_scale = 0.7 if regressed else 0.8
            next_value = max(round(current * stop_scale, 4), 0.01)
            _set_param_default(params, "stop_loss_pct", next_value)
            notes.append(f"最大回撤偏大，止损比例从 {current:g} 收紧到 {next_value:g}")

        if "take_profit_pct" in params and sharpe < target_sharpe:
            current = _param_float(params["take_profit_pct"], 0.1)
            take_profit_scale = 1.03 if regressed else 1.15 if stalled else 1.1
            next_value = round(current * take_profit_scale, 4)
            _set_param_default(params, "take_profit_pct", next_value)
            notes.append(f"盈亏比不足，止盈比例从 {current:g} 提高到 {next_value:g}")

        if "atr_stop_multiplier" in params:
            current = _param_float(params["atr_stop_multiplier"], 2.0)
            atr_scale = 0.8 if regressed else 0.85 if stalled else 0.9
            next_value = round(max(current * atr_scale, 1.0), 3)
            _set_param_default(params, "atr_stop_multiplier", next_value)
            notes.append(f"ATR 止损倍数从 {current:g} 调整到 {next_value:g}")

        if "fast_period" in params and "slow_period" in params:
            fast = _param_int(params["fast_period"], 10)
            slow = _param_int(params["slow_period"], 30)
            if execution_cost_failed:
                next_fast = fast + 1
                next_slow = max(slow + 3, next_fast + 2)
            elif total_trades < 3:
                next_fast = max(fast - (2 if stalled else 1), 2)
                next_slow = max(slow + (4 if stalled else 2), next_fast + 2)
            elif regressed:
                next_fast = fast
                next_slow = max(slow + 1, next_fast + 2)
            elif stalled:
                next_fast = max(fast - 1, 2)
                next_slow = max(slow + 3, next_fast + 2)
            else:
                next_fast = fast
                next_slow = max(slow + 2, next_fast + 2)
            if next_fast != fast or next_slow != slow:
                _set_param_default(params, "fast_period", next_fast)
                _set_param_default(params, "slow_period", next_slow)
                notes.append(f"调整均线窗口为 fast={next_fast}, slow={next_slow}")

        if "rsi_period" in params and sharpe < target_sharpe:
            current = _param_int(params["rsi_period"], 14)
            if total_trades < 3:
                next_value = max(current - (2 if stalled else 1), 5)
            else:
                next_value = current + (2 if regressed or stalled else 1)
            _set_param_default(params, "rsi_period", next_value)
            notes.append(f"RSI 周期从 {current} 调整到 {next_value}")

        if failures:
            notes.append("本轮未通过验收门槛：" + "；".join(failures))

        if not notes:
            notes.append("上一轮指标未达标，保留策略结构并创建新版本继续验证")

        improved.code = _rewrite_code_param_defaults(improved.code, improved.params)
        improved.risk_points = list(
            dict.fromkeys(
                [
                    *improved.risk_points,
                    "该版本由自动投研循环基于上一轮回测指标生成，需要继续做样本外验证。",
                ]
            )
        )
        improved.next_steps = [
            "继续回测新版本并比较 Sharpe、回撤和交易次数",
            "达标后进入 paper 模拟交易并观察实盘风控指标",
        ]
        return StrategyImprovement(
            draft=improved,
            notes=notes,
            metadata={
                "source": "local_rules",
                "provider": "local",
                "model_id": None,
            },
        )


class AIStrategyImprover:
    """Use configured AI models to improve strategy drafts, with local fallback."""

    def __init__(
        self,
        *,
        local_improver: LocalStrategyImprover | None = None,
        ai_router: AIChatRouter | None = None,
        preference_service: AIModelPreferenceService | None = None,
        settings: Any | None = None,
    ) -> None:
        self.local_improver = local_improver or LocalStrategyImprover()
        self.ai_router = ai_router or get_ai_chat_router()
        self.preference_service = preference_service or AIModelPreferenceService()
        self.settings = settings or get_settings()

    async def improve(
        self,
        draft: AIStrategyDraft,
        *,
        iteration: int,
        metrics: dict[str, Any],
        target_sharpe: float,
        quality_gate_failures: list[str] | None = None,
        user_id: str | None = None,
        request: AIStrategyResearchRunRequest | None = None,
    ) -> StrategyImprovement:
        preference = await self._resolve_preference(user_id)
        if preference is None:
            return await self.local_improver.improve(
                draft,
                iteration=iteration,
                metrics=metrics,
                target_sharpe=target_sharpe,
                quality_gate_failures=quality_gate_failures,
                user_id=user_id,
                request=request,
            )

        try:
            response = await self.ai_router.chat_completion(
                messages=_build_improvement_messages(
                    draft,
                    iteration=iteration,
                    metrics=metrics,
                    target_sharpe=target_sharpe,
                    quality_gate_failures=quality_gate_failures,
                    request=request,
                ),
                model=preference.model,
                provider=preference.provider,
                base_url=preference.base_url,
                api_key=preference.api_key,
                timeout=float(getattr(self.settings, "AI_CHAT_TIMEOUT", 120.0) or 120.0),
                max_tokens=int(getattr(self.settings, "AI_CHAT_MAX_TOKENS", 4000) or 4000),
                temperature=min(
                    float(getattr(self.settings, "AI_CHAT_TEMPERATURE", 0.2) or 0.2),
                    0.3,
                ),
            )
            improved = _merge_ai_improvement(
                draft,
                _parse_ai_improvement_payload(response.content),
                iteration=iteration,
                model_id=response.model,
                provider=response.provider,
                total_tokens=response.total_tokens,
            )
            return improved
        except Exception as exc:
            fallback = await self.local_improver.improve(
                draft,
                iteration=iteration,
                metrics=metrics,
                target_sharpe=target_sharpe,
                quality_gate_failures=quality_gate_failures,
                user_id=user_id,
                request=request,
            )
            return StrategyImprovement(
                draft=fallback.draft,
                notes=[
                    f"AI模型改稿不可用，已使用本地规则回退：{exc}",
                    *fallback.notes,
                ],
                metadata={
                    **dict(fallback.metadata or {}),
                    "source": "local_fallback",
                    "fallback_reason": str(exc),
                    "failed_ai_provider": preference.provider,
                    "failed_ai_model": preference.model,
                },
            )

    async def _resolve_preference(
        self,
        user_id: str | None,
    ) -> ResolvedAIModelPreference | None:
        preference = await self.preference_service.resolve_for_user(user_id)
        if preference is not None:
            return preference if preference.configured else None

        if not bool(getattr(self.settings, "AI_CHAT_ENABLED", False)):
            return None
        model = str(getattr(self.settings, "AI_CHAT_MODEL", "") or "").strip()
        base_url = str(getattr(self.settings, "AI_CHAT_BASE_URL", "") or "").strip()
        api_key = str(getattr(self.settings, "AI_CHAT_API_KEY", "") or "").strip()
        if not (model and base_url and api_key):
            return None
        return ResolvedAIModelPreference(
            provider="openai_compatible",
            model=model,
            base_url=base_url,
            api_key=api_key,
            configured=True,
        )


class AIStrategyResearchService:
    """Orchestrate generate -> backtest -> improve -> paper trading."""

    def __init__(
        self,
        *,
        strategy_service: StrategyService | None = None,
        workspace_service: WorkspaceService | None = None,
        backtest_service: Any | None = None,
        improver: Any | None = None,
        mandate_service: InvestmentMandateService | None = None,
        event_service: ResearchPipelineEventService | None = None,
        version_service: AIStrategyResearchVersionService | None = None,
        risk_gate_service: RiskGateService | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.strategy_service = strategy_service or StrategyService()
        self.workspace_service = workspace_service or WorkspaceService()
        self.backtest_service = backtest_service
        self.improver = improver or AIStrategyImprover()
        self.mandate_service = mandate_service or InvestmentMandateService()
        self.event_service = event_service or ResearchPipelineEventService()
        self.version_service = version_service or AIStrategyResearchVersionService()
        self.risk_gate_service = risk_gate_service or RiskGateService()
        self.sleep = sleep or asyncio.sleep

    async def _record_pipeline_event(
        self,
        *,
        user_id: str,
        run_id: str,
        request: AIStrategyResearchRunRequest,
        stage: str,
        status: str,
        workspace_id: str | None = None,
        iteration: int | None = None,
        summary: str | None = None,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with business_span(
            "backtrader.ai.research_stage",
            user_id=user_id,
            run_id=run_id,
            research_stage=stage,
            research_status=status,
        ):
            await self.event_service.safe_create_event(
                user_id=user_id,
                run_id=run_id,
                workspace_id=workspace_id or request.research_workspace_id,
                mandate_id=request.mandate_id,
                stage=stage,
                status=status,
                iteration=iteration,
                summary=summary,
                input_payload=input_payload,
                output_payload=output_payload,
                metrics=metrics,
                error=error,
            )

    async def _persist_iteration_version(
        self,
        *,
        user_id: str,
        run_id: str,
        request: AIStrategyResearchRunRequest,
        workspace_id: str | None,
        iteration: AIStrategyResearchIteration,
    ) -> None:
        try:
            await self.version_service.create_from_iteration(
                user_id=user_id,
                run_id=run_id,
                workspace_id=workspace_id,
                mandate_id=request.mandate_id,
                iteration=iteration,
            )
        except Exception:
            await self._record_pipeline_event(
                user_id=user_id,
                run_id=run_id,
                request=request,
                workspace_id=workspace_id,
                stage="versioning",
                status="failed",
                iteration=iteration.iteration,
                summary="策略版本落库失败，但投研主流程继续运行。",
                error="Failed to persist AI research strategy version",
            )

    async def run(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> AIStrategyResearchRunResponse:
        """Run the research pipeline through a compact public orchestration facade."""
        guarded_request = _apply_market_data_research_binding_guard(request)
        guarded_request = _apply_production_promotion_guards(guarded_request)
        guarded_request = await _apply_production_data_precheck(guarded_request)
        return await self._run_pipeline(
            user_id,
            guarded_request,
            progress_callback=progress_callback,
        )

    async def _run_pipeline(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> AIStrategyResearchRunResponse:
        run_id = str(uuid.uuid4())
        started_at = _utc_iso_now()
        mandate = await self.mandate_service.ensure_for_request(user_id, request)
        request = request.model_copy(update={"mandate_id": mandate.id})
        await self._record_pipeline_event(
            user_id=user_id,
            run_id=run_id,
            request=request,
            stage="mandate",
            status="completed",
            summary="投资需求已结构化并确认。",
            output_payload=mandate.model_dump(mode="json"),
        )
        await self._record_pipeline_event(
            user_id=user_id,
            run_id=run_id,
            request=request,
            stage="initializing",
            status="started",
            summary="AI投研流水线开始初始化。",
            input_payload={
                "symbol": request.symbol,
                "timeframe": request.timeframe,
                "target_sharpe": request.target_sharpe,
                "max_iterations": request.max_iterations,
            },
        )
        await _emit_research_progress(
            progress_callback,
            {
                "run_id": run_id,
                "current_stage": "initializing",
                "progress": 2.0,
                "iteration_count": 0,
                "max_iterations": request.max_iterations,
                "message": "AI research loop is initializing",
            },
        )
        request, draft = await self._prepare_initial_draft(user_id, request)
        research_workspace = await self._ensure_research_workspace(user_id, request)
        await self._record_pipeline_event(
            user_id=user_id,
            run_id=run_id,
            request=request,
            workspace_id=research_workspace.id,
            stage="workspace_ready",
            status="completed",
            summary="AI投研研究工作区已就绪。",
            output_payload={"research_workspace_id": research_workspace.id},
        )
        await _emit_research_progress(
            progress_callback,
            {
                "run_id": run_id,
                "research_workspace_id": research_workspace.id,
                "current_stage": "workspace_ready",
                "progress": 4.0,
                "iteration_count": 0,
                "max_iterations": request.max_iterations,
                "message": "AI research workspace is ready",
            },
        )
        configuration_failure = _required_research_configuration_failure(request)
        if configuration_failure:
            await self._record_pipeline_event(
                user_id=user_id,
                run_id=run_id,
                request=request,
                workspace_id=research_workspace.id,
                stage="configuration_invalid",
                status="failed",
                summary="AI投研配置校验未通过。",
                error=configuration_failure,
            )
            await _emit_research_progress(
                progress_callback,
                {
                    "run_id": run_id,
                    "research_workspace_id": research_workspace.id,
                    "current_stage": "configuration_invalid",
                    "progress": 100.0,
                    "iteration_count": 0,
                    "max_iterations": request.max_iterations,
                    "message": configuration_failure,
                },
            )
            completed_at = _utc_iso_now()
            pipeline = _pipeline_summary(
                status="configuration_invalid",
                achieved=False,
                iteration_count=0,
                max_iterations=request.max_iterations,
                out_of_sample_validation=request.out_of_sample_validation,
                validation_status=None,
                robustness_validation=request.robustness_validation,
                robustness_status=None,
                paper_trading_started=False,
                paper_trading_error=None,
                paper_review_status=None,
                paper_review_ready_for_live=False,
                workflow_mode=request.workflow_mode,
                workflow_steps=request.workflow_steps,
            )
            response = AIStrategyResearchRunResponse(
                run_id=run_id,
                status="configuration_invalid",
                achieved=False,
                target_sharpe=request.target_sharpe,
                started_at=started_at,
                completed_at=completed_at,
                best_iteration=None,
                best_quality_score=0.0,
                best_quality_gate_evaluations=[],
                best_diagnostics=_configuration_failure_diagnostics(configuration_failure),
                best_metrics={},
                research_workspace=research_workspace,
                mandate_id=request.mandate_id,
                iterations=[],
                best_strategy=None,
                paper_trading=None,
                paper_monitoring_plan=[],
                pipeline=pipeline,
                promotion_audit=[],
                next_actions=_run_next_actions(
                    status="configuration_invalid",
                    achieved=False,
                    request=request,
                    result_iteration=None,
                    paper_trading=None,
                    run_failures=[configuration_failure],
                ),
                message=configuration_failure,
            )
            run_record = _build_research_run_record(
                run_id=run_id,
                request=request,
                response=response,
                started_at=started_at,
                completed_at=completed_at,
            )
            run_record = sign_ai_research_run_record(
                run_record,
                user_id=user_id,
                workspace_id=str(research_workspace.id),
            )
            response = response.model_copy(update={"promotion_audit": run_record.promotion_audit})
            research_workspace = await self._persist_research_run_record(
                user_id,
                research_workspace,
                run_record,
            )
            return response.model_copy(
                update={
                    "research_workspace": research_workspace,
                    "run_record": run_record,
                }
            )
        initial_draft_notes: list[str] = []
        iterations: list[AIStrategyResearchIteration] = []
        best_iteration: AIStrategyResearchIteration | None = None
        selected_iteration: AIStrategyResearchIteration | None = None
        run_failures: list[str] = []
        if draft is None:
            await self._record_pipeline_event(
                user_id=user_id,
                run_id=run_id,
                request=request,
                workspace_id=research_workspace.id,
                stage="drafting",
                status="started",
                summary="开始生成首轮策略草案。",
            )
            await _emit_research_progress(
                progress_callback,
                {
                    "current_stage": "drafting",
                    "progress": 5.0,
                    "iteration_count": 0,
                    "max_iterations": request.max_iterations,
                    "message": "Generating initial strategy draft",
                },
            )
            try:
                draft_response = await self.strategy_service.generate_copilot_draft(
                    user_id,
                    StrategyCopilotDraftRequest(
                        prompt=_build_research_draft_prompt(request),
                        knowledge_base_id=request.knowledge_base_id,
                        thinking_mode=request.thinking_mode,
                    ),
                )
                initial_draft_metadata = _initial_generation_metadata_from_response(
                    draft_response,
                    source="ai_initial_draft",
                    request=request,
                )
                draft = _normalize_research_draft(draft_response.strategy_draft, request)
                draft, initial_draft_notes = _ensure_runnable_initial_draft(draft, request)
            except asyncio.CancelledError:
                fallback_draft = _normalize_research_draft(
                    build_ai_strategy_draft(request.prompt),
                    request,
                )
                await self._persist_cancelled_research_run(
                    user_id=user_id,
                    request=request,
                    research_workspace=research_workspace,
                    run_id=run_id,
                    started_at=started_at,
                    iterations=iterations,
                    best_iteration=best_iteration,
                    selected_iteration=selected_iteration,
                    run_failures=[
                        *run_failures,
                        "AI research cancelled while generating initial strategy draft",
                    ],
                    draft=fallback_draft,
                )
                raise
            except Exception as exc:
                await self._record_pipeline_event(
                    user_id=user_id,
                    run_id=run_id,
                    request=request,
                    workspace_id=research_workspace.id,
                    stage="drafting",
                    status="failed",
                    summary="AI首轮策略草案生成失败，准备使用本地可运行草案继续。",
                    error=str(exc),
                )
                await _emit_research_progress(
                    progress_callback,
                    {
                        "current_stage": "draft_generation_failed",
                        "progress": 6.0,
                        "iteration_count": 0,
                        "max_iterations": request.max_iterations,
                        "message": f"Initial strategy draft generation failed: {exc}",
                    },
                )
                draft = _normalize_research_draft(build_ai_strategy_draft(request.prompt), request)
                _validate_strategy_code_draft(draft.code)
                initial_draft_metadata = {
                    "source": "local_initial_fallback",
                    "provider": "local",
                    "fallback_reason": str(exc),
                }
                initial_draft_notes = [
                    f"AI初始策略生成失败，已使用本地可运行草案继续投研：{exc}",
                ]
        else:
            draft, initial_draft_notes = _ensure_runnable_seed_draft(draft, request)
            initial_draft_metadata = _seed_generation_metadata(request)

        await self._record_pipeline_event(
            user_id=user_id,
            run_id=run_id,
            request=request,
            workspace_id=research_workspace.id,
            stage="drafting",
            status="completed",
            summary="首轮策略草案已准备完成。",
            output_payload={
                "strategy_name": draft.name,
                "metadata": initial_draft_metadata,
                "notes": initial_draft_notes,
            },
        )

        pending_improvement_notes: list[str] = initial_draft_notes
        pending_generation_metadata: dict[str, Any] = dict(initial_draft_metadata)
        continuation_failures = _continuation_quality_gate_failures(request.continuation_context)
        validation_window = _out_of_sample_window(request)
        if continuation_failures:
            try:
                improvement = await self._improve_draft(
                    draft,
                    iteration=0,
                    metrics=_continuation_improvement_metrics(
                        request.continuation_context,
                        request,
                    ),
                    target_sharpe=request.target_sharpe,
                    quality_gate_failures=continuation_failures,
                    user_id=user_id,
                    request=request,
                )
            except asyncio.CancelledError:
                await self._persist_cancelled_research_run(
                    user_id=user_id,
                    request=request,
                    research_workspace=research_workspace,
                    run_id=run_id,
                    started_at=started_at,
                    iterations=iterations,
                    best_iteration=best_iteration,
                    selected_iteration=selected_iteration,
                    run_failures=[
                        *run_failures,
                        "AI research cancelled while preparing continuation draft",
                    ],
                    draft=draft,
                )
                raise
            draft = _normalize_research_draft(improvement.draft, request)
            continuation_source = str(request.continuation_context.get("source") or "")
            if continuation_source == "paper_trading_failed":
                continuation_note = "基于上一轮模拟交易启动失败原因生成 continuation 改进版。"
            elif continuation_source == "research_cancelled":
                continuation_note = "基于上一轮取消前已完成迭代的失败指标生成 continuation 改进版。"
            elif continuation_source == "research_failure":
                continuation_note = "基于上一轮投研未达标原因生成 continuation 改进版。"
            elif continuation_source == "live_handoff_rejected":
                continuation_note = "基于上一轮实盘交接驳回意见生成 continuation 改进版。"
            else:
                continuation_note = "基于上一轮模拟交易复核结果生成 continuation 改进版。"
            pending_improvement_notes = [
                continuation_note,
                *improvement.notes,
            ]
            pending_generation_metadata = _strategy_generation_metadata(
                improvement.metadata,
                phase="continuation_improvement",
                iteration=1,
            )
        achieved = False

        for iteration in range(1, request.max_iterations + 1):
            failure_reason: str | None = None
            await self._record_pipeline_event(
                user_id=user_id,
                run_id=run_id,
                request=request,
                workspace_id=research_workspace.id,
                stage="backtesting",
                status="started",
                iteration=iteration,
                summary=f"开始第 {iteration} 轮回测。",
            )
            await _emit_research_progress(
                progress_callback,
                {
                    "current_stage": "backtesting",
                    "progress": _research_loop_progress(iteration - 1, request.max_iterations),
                    "current_iteration": iteration,
                    "iteration_count": len(iterations),
                    "max_iterations": request.max_iterations,
                    "message": f"Running AI research backtest iteration {iteration}",
                },
            )
            try:
                (
                    draft,
                    pending_improvement_notes,
                    pending_generation_metadata,
                ) = await self._ensure_valid_draft_before_backtest(
                    draft,
                    user_id=user_id,
                    request=request,
                    iteration=iteration,
                    iteration_count=len(iterations),
                    pending_improvement_notes=pending_improvement_notes,
                    pending_generation_metadata=pending_generation_metadata,
                    progress_callback=progress_callback,
                )
            except asyncio.CancelledError:
                await self._persist_cancelled_research_run(
                    user_id=user_id,
                    request=request,
                    research_workspace=research_workspace,
                    run_id=run_id,
                    started_at=started_at,
                    iterations=iterations,
                    best_iteration=best_iteration,
                    selected_iteration=selected_iteration,
                    run_failures=[
                        *run_failures,
                        f"AI research cancelled while validating strategy draft for iteration {iteration}",
                    ],
                    draft=draft,
                )
                raise
            backtest_request = self._build_backtest_request(
                draft,
                request,
                user_id=user_id,
                start_date=validation_window.train_start if validation_window else None,
                end_date=validation_window.train_end if validation_window else None,
                group_name_suffix=" 训练样本" if validation_window else "",
            )
            try:
                backtest_response = await self.strategy_service.backtest_copilot_draft(
                    user_id,
                    research_workspace.id,
                    backtest_request,
                )
                if backtest_response is None:
                    raise ValueError("Research workspace or generated strategy was not found")
            except asyncio.CancelledError:
                await self._persist_cancelled_research_run(
                    user_id=user_id,
                    request=request,
                    research_workspace=research_workspace,
                    run_id=run_id,
                    started_at=started_at,
                    iterations=iterations,
                    best_iteration=best_iteration,
                    selected_iteration=selected_iteration,
                    run_failures=[
                        *run_failures,
                        f"AI research cancelled while submitting backtest iteration {iteration}",
                    ],
                    draft=draft,
                )
                raise
            except Exception as exc:
                failure_reason = f"Backtest submission failed before iteration {iteration}: {exc}"
                run_failures.append(failure_reason)
                await self._record_pipeline_event(
                    user_id=user_id,
                    run_id=run_id,
                    request=request,
                    workspace_id=research_workspace.id,
                    stage="backtest_submission_failed",
                    status="failed",
                    iteration=iteration,
                    summary="回测任务提交失败。",
                    metrics={
                        "backtest_submission_failed": True,
                        "failure_count": len(run_failures),
                    },
                    error=failure_reason,
                )
                await _emit_research_progress(
                    progress_callback,
                    {
                        "current_stage": "backtest_submission_failed",
                        "progress": _research_loop_progress(iteration - 1, request.max_iterations),
                        "current_iteration": iteration,
                        "iteration_count": len(iterations),
                        "max_iterations": request.max_iterations,
                        "current_backtest_task_id": None,
                        "message": failure_reason,
                    },
                )
                if iteration < request.max_iterations:
                    await self._record_pipeline_event(
                        user_id=user_id,
                        run_id=run_id,
                        request=request,
                        workspace_id=research_workspace.id,
                        stage="optimization_loop",
                        status="started",
                        iteration=iteration + 1,
                        summary=f"根据第 {iteration} 轮提交失败原因准备下一版策略。",
                        input_payload={"failure_reason": failure_reason},
                    )
                    await _emit_research_progress(
                        progress_callback,
                        {
                            "current_stage": "improving",
                            "progress": min(
                                _research_loop_progress(iteration, request.max_iterations) + 2.0,
                                82.0,
                            ),
                            "current_iteration": iteration + 1,
                            "iteration_count": len(iterations),
                            "max_iterations": request.max_iterations,
                            "message": f"Improving strategy for iteration {iteration + 1}",
                        },
                    )
                    try:
                        improvement = await self._improve_draft(
                            draft,
                            iteration=iteration,
                            metrics={
                                "backtest_submission_failed": True,
                                "backtest_submission_failure_count": len(run_failures),
                            },
                            target_sharpe=request.target_sharpe,
                            quality_gate_failures=[failure_reason],
                            user_id=user_id,
                            request=request,
                        )
                    except asyncio.CancelledError:
                        await self._persist_cancelled_research_run(
                            user_id=user_id,
                            request=request,
                            research_workspace=research_workspace,
                            run_id=run_id,
                            started_at=started_at,
                            iterations=iterations,
                            best_iteration=best_iteration,
                            selected_iteration=selected_iteration,
                            run_failures=run_failures,
                            draft=draft,
                        )
                        raise
                    draft = _normalize_research_draft(improvement.draft, request)
                    pending_improvement_notes = [
                        f"第 {iteration} 轮回测提交失败，已基于失败原因生成下一版策略：{failure_reason}",
                        *improvement.notes,
                    ]
                    pending_generation_metadata = _strategy_generation_metadata(
                        improvement.metadata,
                        phase="backtest_submission_repair",
                        iteration=iteration + 1,
                    )
                    await self._record_pipeline_event(
                        user_id=user_id,
                        run_id=run_id,
                        request=request,
                        workspace_id=research_workspace.id,
                        stage="optimization_loop",
                        status="completed",
                        iteration=iteration + 1,
                        summary="提交失败修复版策略已生成。",
                        output_payload={
                            "notes": pending_improvement_notes,
                            "metadata": pending_generation_metadata,
                        },
                    )
                    continue
                break
            await self._record_pipeline_event(
                user_id=user_id,
                run_id=run_id,
                request=request,
                workspace_id=research_workspace.id,
                stage="backtesting",
                status="submitted",
                iteration=iteration,
                summary=f"第 {iteration} 轮回测任务已提交。",
                output_payload={
                    "strategy_id": backtest_response.strategy.id,
                    "unit_id": backtest_response.unit.id,
                    "task_id": backtest_response.run_result.task_id,
                },
            )
            await _emit_research_progress(
                progress_callback,
                {
                    "current_stage": "backtesting",
                    "progress": min(
                        _research_loop_progress(iteration - 1, request.max_iterations) + 4.0,
                        80.0,
                    ),
                    "current_iteration": iteration,
                    "iteration_count": len(iterations),
                    "max_iterations": request.max_iterations,
                    "current_backtest_task_id": backtest_response.run_result.task_id,
                    "message": f"Backtest task submitted for iteration {iteration}",
                },
            )

            try:
                unit_status, failure_reason = await self._wait_for_unit_status(
                    research_workspace.id,
                    user_id,
                    backtest_response.unit.id,
                    initial_status=backtest_response.unit_status,
                    timeout_seconds=request.backtest_timeout_seconds,
                    poll_interval_seconds=request.poll_interval_seconds,
                )
            except asyncio.CancelledError:
                cancelled_iterations = [
                    *iterations,
                    _cancelled_submitted_iteration(
                        request=request,
                        iteration=iteration,
                        backtest_response=backtest_response,
                        pending_improvement_notes=pending_improvement_notes,
                    ),
                ]
                await self._persist_cancelled_research_run(
                    user_id=user_id,
                    request=request,
                    research_workspace=research_workspace,
                    run_id=run_id,
                    started_at=started_at,
                    iterations=cancelled_iterations,
                    best_iteration=best_iteration,
                    selected_iteration=selected_iteration,
                    run_failures=run_failures,
                )
                raise
            metrics = dict(unit_status.metrics_snapshot if unit_status else {})
            sharpe = _metric_float(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
            total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
            quality_gate_failures = _quality_gate_failures(request, metrics)
            passed = (
                unit_status is not None
                and unit_status.run_status == "completed"
                and not quality_gate_failures
            )
            quality_score = _quality_score(
                request,
                metrics,
                run_status=unit_status.run_status if unit_status else None,
            )
            quality_gate_evaluations = _quality_gate_evaluations(
                request,
                metrics,
                run_status=unit_status.run_status if unit_status else None,
            )
            if (
                not failure_reason
                and unit_status is not None
                and unit_status.run_status != "completed"
            ):
                failure_reason = f"Backtest finished with status {unit_status.run_status}"
            if not failure_reason and quality_gate_failures:
                failure_reason = "; ".join(quality_gate_failures)

            validation_unit: StrategyUnitResponse | None = None
            validation_run_result: StrategyCopilotRunResult | None = None
            validation_unit_status: UnitStatusResponse | None = None
            validation_status: str | None = None
            validation_metrics: dict[str, Any] = {}
            validation_gate_evaluations: list[dict[str, Any]] = []
            validation_failures: list[str] = []
            validation_failure_reason: str | None = None
            validation_window_payload = validation_window.as_dict() if validation_window else None
            robustness_status: str | None = None
            robustness_result: dict[str, Any] = {}
            robustness_gate_evaluations: list[dict[str, Any]] = []
            robustness_failures: list[str] = []
            robustness_failure_reason: str | None = None

            if passed and request.out_of_sample_validation:
                if validation_window is None:
                    validation_status = "skipped"
                    validation_failure_reason = (
                        "Out-of-sample validation skipped because start_date/end_date "
                        "do not define a splittable range"
                    )
                    if request.require_out_of_sample_validation:
                        validation_failures = [validation_failure_reason]
                        quality_gate_failures = [*quality_gate_failures, validation_failure_reason]
                        failure_reason = validation_failure_reason
                        passed = False
                else:
                    await self._record_pipeline_event(
                        user_id=user_id,
                        run_id=run_id,
                        request=request,
                        workspace_id=research_workspace.id,
                        stage="validating",
                        status="started",
                        iteration=iteration,
                        summary=f"开始第 {iteration} 轮样本外验证。",
                        input_payload={"validation_window": validation_window_payload},
                    )
                    await _emit_research_progress(
                        progress_callback,
                        {
                            "current_stage": "validating",
                            "progress": min(
                                _research_loop_progress(iteration, request.max_iterations) + 1.0,
                                83.0,
                            ),
                            "current_iteration": iteration,
                            "iteration_count": len(iterations),
                            "max_iterations": request.max_iterations,
                            "latest_iteration": {
                                "iteration": iteration,
                                "validation_window": validation_window_payload,
                            },
                            "message": f"Running out-of-sample validation for iteration {iteration}",
                        },
                    )
                    validation_request = self._build_backtest_request(
                        draft,
                        request,
                        user_id=user_id,
                        start_date=validation_window.validation_start,
                        end_date=validation_window.validation_end,
                        group_name_suffix=" 样本外验证",
                    )
                    try:
                        validation_response = await self.strategy_service.backtest_copilot_draft(
                            user_id,
                            research_workspace.id,
                            validation_request,
                        )
                        if validation_response is None:
                            raise ValueError(
                                "Research workspace or generated validation strategy was not found"
                            )
                        validation_unit = validation_response.unit
                        validation_run_result = validation_response.run_result
                        await _emit_research_progress(
                            progress_callback,
                            {
                                "current_stage": "validating",
                                "progress": min(
                                    _research_loop_progress(iteration, request.max_iterations)
                                    + 2.0,
                                    84.0,
                                ),
                                "current_iteration": iteration,
                                "iteration_count": len(iterations),
                                "max_iterations": request.max_iterations,
                                "current_backtest_task_id": validation_response.run_result.task_id,
                                "latest_iteration": {
                                    "iteration": iteration,
                                    "validation_window": validation_window_payload,
                                },
                                "message": (
                                    "Out-of-sample validation task submitted "
                                    f"for iteration {iteration}"
                                ),
                            },
                        )
                        (
                            validation_unit_status,
                            validation_wait_failure,
                        ) = await self._wait_for_unit_status(
                            research_workspace.id,
                            user_id,
                            validation_response.unit.id,
                            initial_status=validation_response.unit_status,
                            timeout_seconds=request.backtest_timeout_seconds,
                            poll_interval_seconds=request.poll_interval_seconds,
                        )
                        validation_metrics = dict(
                            validation_unit_status.metrics_snapshot
                            if validation_unit_status
                            else {}
                        )
                        validation_run_status = (
                            validation_unit_status.run_status if validation_unit_status else None
                        )
                        validation_gate_evaluations = _out_of_sample_gate_evaluations(
                            request,
                            validation_metrics,
                            run_status=validation_run_status,
                        )
                        validation_failures = _out_of_sample_failures(
                            request,
                            validation_metrics,
                            run_status=validation_run_status,
                        )
                        validation_status = "passed" if not validation_failures else "failed"
                        if validation_wait_failure and validation_run_status != "completed":
                            validation_failure_reason = validation_wait_failure
                        if validation_failures:
                            validation_failure_reason = "; ".join(validation_failures)
                            quality_gate_failures = [*quality_gate_failures, *validation_failures]
                            failure_reason = validation_failure_reason
                            passed = False
                    except Exception as exc:
                        validation_status = "failed"
                        validation_failure_reason = (
                            f"Out-of-sample validation failed to start: {exc}"
                        )
                        validation_failures = [validation_failure_reason]
                        quality_gate_failures = [*quality_gate_failures, validation_failure_reason]
                        failure_reason = validation_failure_reason
                        passed = False
            if validation_status:
                await self._record_pipeline_event(
                    user_id=user_id,
                    run_id=run_id,
                    request=request,
                    workspace_id=research_workspace.id,
                    stage="validating",
                    status="completed" if validation_status == "passed" else "failed",
                    iteration=iteration,
                    summary=f"第 {iteration} 轮样本外验证{validation_status}。",
                    output_payload={
                        "validation_status": validation_status,
                        "validation_window": validation_window_payload,
                        "gate_evaluations": validation_gate_evaluations,
                        "failures": validation_failures,
                    },
                    metrics=validation_metrics,
                    error=validation_failure_reason,
                )
            if passed and request.robustness_validation:
                await self._record_pipeline_event(
                    user_id=user_id,
                    run_id=run_id,
                    request=request,
                    workspace_id=research_workspace.id,
                    stage="robustness_validation",
                    status="started",
                    iteration=iteration,
                    summary=f"开始第 {iteration} 轮稳健性验证。",
                    input_payload={
                        "backtest_id": backtest_response.run_result.task_id,
                        "methods": request.robustness_methods,
                        "min_robustness_score": request.min_robustness_score,
                    },
                )
                await _emit_research_progress(
                    progress_callback,
                    {
                        "current_stage": "robustness_validation",
                        "progress": min(
                            _research_loop_progress(iteration, request.max_iterations) + 1.5,
                            84.5,
                        ),
                        "current_iteration": iteration,
                        "iteration_count": len(iterations),
                        "max_iterations": request.max_iterations,
                        "current_backtest_task_id": backtest_response.run_result.task_id,
                        "latest_iteration": {
                            "iteration": iteration,
                            "robustness_status": "running",
                        },
                        "message": f"Running robustness validation for iteration {iteration}",
                    },
                )
                robustness_status = "failed"
                try:
                    task_id = str(backtest_response.run_result.task_id or "").strip()
                    if not task_id:
                        raise ValueError(
                            "Robustness validation requires a completed backtest task id"
                        )
                    robustness = await get_robustness_validation_service().run_for_backtest(
                        backtest_id=task_id,
                        user_id=user_id,
                        request=_robustness_validation_request(request, run_id=run_id),
                    )
                    robustness_result = robustness.model_dump(mode="json")
                    robustness_status = robustness.status
                    robustness_gate_evaluations = _robustness_gate_payloads(robustness_result)
                    robustness_failures = _robustness_failures_from_result(
                        robustness_result,
                        require_robustness=request.require_robustness_validation,
                    )
                    if robustness_failures:
                        robustness_failure_reason = "; ".join(robustness_failures)
                        if request.require_robustness_validation:
                            quality_gate_failures = [
                                *quality_gate_failures,
                                *robustness_failures,
                            ]
                            failure_reason = robustness_failure_reason
                            passed = False
                except Exception as exc:
                    robustness_failure_reason = f"Robustness validation failed to run: {exc}"
                    robustness_failures = [robustness_failure_reason]
                    robustness_result = {"status": "failed", "error_message": str(exc)}
                    if request.require_robustness_validation:
                        quality_gate_failures = [
                            *quality_gate_failures,
                            robustness_failure_reason,
                        ]
                        failure_reason = robustness_failure_reason
                        passed = False
                await self._record_pipeline_event(
                    user_id=user_id,
                    run_id=run_id,
                    request=request,
                    workspace_id=research_workspace.id,
                    stage="robustness_validation",
                    status="completed" if not robustness_failures else "failed",
                    iteration=iteration,
                    summary=f"第 {iteration} 轮稳健性验证{robustness_status}。",
                    output_payload={
                        "robustness_status": robustness_status,
                        "gate_evaluations": robustness_gate_evaluations,
                        "failures": robustness_failures,
                        "result": robustness_result,
                    },
                    metrics=dict(robustness_result.get("metrics") or {}),
                    error=robustness_failure_reason,
                )
            previous_iteration = iterations[-1] if iterations else None
            diagnostics = _iteration_diagnostics(
                request,
                iteration=iteration,
                metrics=metrics,
                run_status=unit_status.run_status if unit_status else None,
                quality_gate_failures=quality_gate_failures,
                quality_gate_evaluations=quality_gate_evaluations,
                failure_reason=failure_reason,
                previous_iteration=previous_iteration,
                quality_score=quality_score,
            )
            if request.out_of_sample_validation:
                diagnostics["out_of_sample_validation"] = {
                    "status": validation_status or "not_required",
                    "window": validation_window_payload,
                    "metrics": validation_metrics,
                    "gate_evaluations": validation_gate_evaluations,
                    "failures": validation_failures,
                    "failure_reason": validation_failure_reason,
                }
                if validation_failures:
                    diagnostics["promotion_ready"] = False
                    diagnostics["summary"] = (
                        f"第 {iteration} 轮训练样本达标，但样本外验证未通过："
                        + "；".join(validation_failures)
                    )
            if request.robustness_validation:
                diagnostics["robustness_validation"] = {
                    "status": robustness_status or "not_required",
                    "result": robustness_result,
                    "gate_evaluations": robustness_gate_evaluations,
                    "failures": robustness_failures,
                    "failure_reason": robustness_failure_reason,
                }
                if robustness_failures:
                    diagnostics["promotion_ready"] = False
                    diagnostics["summary"] = (
                        f"第 {iteration} 轮训练/验证门槛达标，但稳健性验证未通过："
                        + "；".join(robustness_failures)
                    )
            generation_metadata = _strategy_generation_metadata(
                pending_generation_metadata,
                iteration=iteration,
            )
            if generation_metadata:
                diagnostics["strategy_generation"] = generation_metadata
            improvement_plan = list(diagnostics.get("improvement_plan") or [])

            item = AIStrategyResearchIteration(
                iteration=iteration,
                strategy=backtest_response.strategy,
                unit=backtest_response.unit,
                run_result=backtest_response.run_result,
                unit_status=unit_status,
                metrics=metrics,
                sharpe_ratio=sharpe,
                total_trades=total_trades,
                validation_unit=validation_unit,
                validation_run_result=validation_run_result,
                validation_unit_status=validation_unit_status,
                validation_status=validation_status,
                validation_window=validation_window_payload,
                validation_metrics=validation_metrics,
                validation_gate_evaluations=validation_gate_evaluations,
                validation_failures=validation_failures,
                validation_failure_reason=validation_failure_reason,
                robustness_status=robustness_status,
                robustness_result=robustness_result,
                robustness_gate_evaluations=robustness_gate_evaluations,
                robustness_failures=robustness_failures,
                robustness_failure_reason=robustness_failure_reason,
                quality_score=quality_score,
                quality_gate_evaluations=quality_gate_evaluations,
                passed=passed,
                failure_reason=None if passed else failure_reason,
                quality_gate_failures=quality_gate_failures,
                diagnostics=diagnostics,
                improvement_plan=improvement_plan,
                improvement_notes=pending_improvement_notes,
                next_actions=_iteration_next_actions(
                    iteration=iteration,
                    max_iterations=request.max_iterations,
                    passed=passed,
                    run_status=unit_status.run_status if unit_status else None,
                    quality_gate_failures=quality_gate_failures,
                    failure_reason=failure_reason,
                ),
            )
            iterations.append(item)
            await self._record_pipeline_event(
                user_id=user_id,
                run_id=run_id,
                request=request,
                workspace_id=research_workspace.id,
                stage="backtesting",
                status="completed" if passed or unit_status is not None else "failed",
                iteration=iteration,
                summary=f"第 {iteration} 轮回测完成。",
                output_payload={
                    "unit_id": item.unit.id,
                    "task_id": item.run_result.task_id,
                    "run_status": unit_status.run_status if unit_status else None,
                    "robustness_status": robustness_status,
                    "quality_gate_failures": quality_gate_failures,
                },
                metrics=metrics,
                error=None if passed else failure_reason,
            )
            await self._record_pipeline_event(
                user_id=user_id,
                run_id=run_id,
                request=request,
                workspace_id=research_workspace.id,
                stage="strategy_review",
                status="completed",
                iteration=iteration,
                summary=str(diagnostics.get("summary") or "策略审查已完成。"),
                output_payload={
                    "diagnostics": diagnostics,
                    "improvement_plan": improvement_plan,
                    "quality_gate_evaluations": quality_gate_evaluations,
                },
                metrics=metrics,
                error=None if passed else failure_reason,
            )
            await self._persist_iteration_version(
                user_id=user_id,
                run_id=run_id,
                request=request,
                workspace_id=research_workspace.id,
                iteration=item,
            )
            await _emit_research_progress(
                progress_callback,
                {
                    "current_stage": "evaluating",
                    "progress": _research_loop_progress(iteration, request.max_iterations),
                    "current_iteration": iteration,
                    "iteration_count": len(iterations),
                    "max_iterations": request.max_iterations,
                    "latest_iteration": _compact_research_iteration(item),
                    "message": f"Completed AI research iteration {iteration}",
                },
            )
            if best_iteration is None or _is_better_research_candidate(item, best_iteration):
                best_iteration = item
            if passed:
                achieved = True
                selected_iteration = item
                break

            if iteration < request.max_iterations:
                await self._record_pipeline_event(
                    user_id=user_id,
                    run_id=run_id,
                    request=request,
                    workspace_id=research_workspace.id,
                    stage="optimization_loop",
                    status="started",
                    iteration=iteration + 1,
                    summary=f"根据第 {iteration} 轮审查结果准备下一版策略。",
                    input_payload={
                        "quality_gate_failures": quality_gate_failures,
                        "metrics": metrics,
                    },
                )
                await _emit_research_progress(
                    progress_callback,
                    {
                        "current_stage": "improving",
                        "progress": min(
                            _research_loop_progress(iteration, request.max_iterations) + 2.0,
                            82.0,
                        ),
                        "current_iteration": iteration + 1,
                        "iteration_count": len(iterations),
                        "max_iterations": request.max_iterations,
                        "latest_iteration": _compact_research_iteration(item),
                        "message": f"Improving strategy for iteration {iteration + 1}",
                    },
                )
                try:
                    improvement_base_draft = draft
                    rollback_note = None
                    iteration_progress = diagnostics.get("iteration_progress")
                    progress_status = (
                        str(iteration_progress.get("status") or "").strip()
                        if isinstance(iteration_progress, dict)
                        else ""
                    )
                    if (
                        progress_status == "regressed"
                        and best_iteration is not None
                        and best_iteration.iteration != item.iteration
                    ):
                        improvement_base_draft = _draft_from_strategy(
                            best_iteration.strategy,
                            request,
                        )
                        rollback_note = (
                            f"第 {iteration} 轮自动改稿退化，下一版回退到当前最佳第 "
                            f"{best_iteration.iteration} 轮策略后继续改进。"
                        )
                    improvement = await self._improve_draft(
                        improvement_base_draft,
                        iteration=iteration,
                        metrics=_improvement_metrics(
                            metrics,
                            validation_metrics,
                            iteration_progress=diagnostics.get("iteration_progress"),
                            diagnostics=diagnostics,
                        ),
                        target_sharpe=request.target_sharpe,
                        quality_gate_failures=quality_gate_failures,
                        user_id=user_id,
                        request=request,
                    )
                except asyncio.CancelledError:
                    await self._persist_cancelled_research_run(
                        user_id=user_id,
                        request=request,
                        research_workspace=research_workspace,
                        run_id=run_id,
                        started_at=started_at,
                        iterations=iterations,
                        best_iteration=best_iteration,
                        selected_iteration=selected_iteration,
                        run_failures=run_failures,
                    )
                    raise
                draft = _normalize_research_draft(improvement.draft, request)
                pending_improvement_notes = (
                    [rollback_note, *improvement.notes] if rollback_note else improvement.notes
                )
                pending_generation_metadata = _strategy_generation_metadata(
                    improvement.metadata,
                    phase="quality_gate_improvement",
                    iteration=iteration + 1,
                )
                await self._record_pipeline_event(
                    user_id=user_id,
                    run_id=run_id,
                    request=request,
                    workspace_id=research_workspace.id,
                    stage="optimization_loop",
                    status="completed",
                    iteration=iteration + 1,
                    summary=f"第 {iteration + 1} 轮策略改稿已完成。",
                    output_payload={
                        "notes": pending_improvement_notes,
                        "metadata": pending_generation_metadata,
                    },
                )

        paper_trading = None
        paper_trading_error = None
        result_iteration = selected_iteration or best_iteration
        if achieved and request.start_paper_trading and result_iteration is not None:
            await self._record_pipeline_event(
                user_id=user_id,
                run_id=run_id,
                request=request,
                workspace_id=research_workspace.id,
                stage="paper_trading",
                status="started",
                iteration=result_iteration.iteration,
                summary="达标策略开始进入模拟交易。",
            )
            await _emit_research_progress(
                progress_callback,
                {
                    "current_stage": "paper_trading",
                    "progress": 88.0,
                    "iteration_count": len(iterations),
                    "max_iterations": request.max_iterations,
                    "latest_iteration": _compact_research_iteration(result_iteration),
                    "message": "Starting paper trading for achieved strategy",
                },
            )
            try:
                paper_trading = await self._start_paper_trading(
                    user_id,
                    request,
                    result_iteration,
                    run_id=run_id,
                    research_workspace_id=research_workspace.id,
                )
                paper_trading_error = _paper_trading_start_error(paper_trading)
                if paper_trading_error:
                    await self._record_pipeline_event(
                        user_id=user_id,
                        run_id=run_id,
                        request=request,
                        workspace_id=research_workspace.id,
                        stage="paper_trading",
                        status="failed",
                        iteration=result_iteration.iteration,
                        summary="模拟交易启动失败。",
                        error=paper_trading_error,
                    )
                    await _emit_research_progress(
                        progress_callback,
                        {
                            "current_stage": "paper_trading_failed",
                            "progress": 92.0,
                            "iteration_count": len(iterations),
                            "max_iterations": request.max_iterations,
                            "latest_iteration": _compact_research_iteration(result_iteration),
                            "message": f"Paper trading start failed: {paper_trading_error}",
                        },
                    )
            except asyncio.CancelledError:
                await self._persist_cancelled_research_run(
                    user_id=user_id,
                    request=request,
                    research_workspace=research_workspace,
                    run_id=run_id,
                    started_at=started_at,
                    iterations=iterations,
                    best_iteration=best_iteration,
                    selected_iteration=selected_iteration,
                    run_failures=run_failures,
                )
                raise
            except Exception as exc:
                paper_trading_error = str(exc)
                await self._record_pipeline_event(
                    user_id=user_id,
                    run_id=run_id,
                    request=request,
                    workspace_id=research_workspace.id,
                    stage="paper_trading",
                    status="failed",
                    iteration=result_iteration.iteration,
                    summary="模拟交易启动异常。",
                    error=paper_trading_error,
                )
                await _emit_research_progress(
                    progress_callback,
                    {
                        "current_stage": "paper_trading_failed",
                        "progress": 92.0,
                        "iteration_count": len(iterations),
                        "max_iterations": request.max_iterations,
                        "latest_iteration": _compact_research_iteration(result_iteration),
                        "message": f"Paper trading start failed: {paper_trading_error}",
                    },
                )
            if paper_trading is not None and not paper_trading_error:
                await self._record_pipeline_event(
                    user_id=user_id,
                    run_id=run_id,
                    request=request,
                    workspace_id=research_workspace.id,
                    stage="paper_trading",
                    status="completed",
                    iteration=result_iteration.iteration,
                    summary="模拟交易已启动。",
                    output_payload={
                        "paper_workspace_id": paper_trading.workspace.id,
                        "paper_unit_id": paper_trading.unit.id,
                    },
                )

        status = "achieved" if achieved else "max_iterations_reached"
        if (
            iterations
            and iterations[-1].unit_status
            and iterations[-1].unit_status.run_status == "timeout"
        ):
            status = "timeout"
        if not iterations and run_failures and not achieved:
            status = "backtest_submission_failed"
        best_metrics = dict(result_iteration.metrics) if result_iteration else {}
        run_failure_diagnostics = _run_failure_diagnostics(run_failures)
        fallback_strategy = None
        if result_iteration is None and run_failures:
            fallback_strategy = await self._persist_research_draft_strategy(
                user_id,
                draft,
                request,
                run_id=run_id,
            )
        paper_monitoring_plan = (
            _paper_monitoring_plan(request, result_iteration)
            if achieved and result_iteration is not None
            else []
        )
        message = _research_completion_message(
            request=request,
            achieved=achieved,
            result_iteration=result_iteration,
            run_failures=run_failures,
        )
        completed_at = _utc_iso_now()
        next_actions = _run_next_actions(
            status=status,
            achieved=achieved,
            request=request,
            result_iteration=result_iteration,
            paper_trading=paper_trading,
            paper_trading_error=paper_trading_error,
            run_failures=run_failures,
        )
        pipeline = _pipeline_summary(
            status=status,
            achieved=achieved,
            iteration_count=len(iterations),
            max_iterations=request.max_iterations,
            out_of_sample_validation=request.out_of_sample_validation,
            validation_status=result_iteration.validation_status if result_iteration else None,
            robustness_validation=request.robustness_validation,
            robustness_status=result_iteration.robustness_status if result_iteration else None,
            paper_trading_started=bool(paper_trading.started) if paper_trading else False,
            paper_trading_error=paper_trading_error,
            paper_review_status=None,
            paper_review_ready_for_live=False,
            workflow_mode=request.workflow_mode,
            workflow_steps=request.workflow_steps,
        )
        response = AIStrategyResearchRunResponse(
            run_id=run_id,
            status=status,
            achieved=achieved,
            target_sharpe=request.target_sharpe,
            started_at=started_at,
            completed_at=completed_at,
            best_iteration=result_iteration.iteration if result_iteration else None,
            best_quality_score=_promotion_quality_score(result_iteration),
            best_quality_gate_evaluations=_promotion_gate_evaluations(result_iteration)
            if result_iteration
            else [],
            robustness_validation=_iteration_robustness_payload(result_iteration),
            best_diagnostics=result_iteration.diagnostics
            if result_iteration
            else run_failure_diagnostics,
            best_metrics=best_metrics,
            research_workspace=research_workspace,
            mandate_id=request.mandate_id,
            iterations=iterations,
            best_strategy=result_iteration.strategy if result_iteration else fallback_strategy,
            paper_trading=paper_trading,
            paper_monitoring_plan=paper_monitoring_plan,
            pipeline=pipeline,
            promotion_audit=[],
            next_actions=next_actions,
            message=message,
        )
        run_record = _build_research_run_record(
            run_id=run_id,
            request=request,
            response=response,
            started_at=started_at,
            completed_at=completed_at,
        )
        run_record = _apply_initial_paper_review_to_run_record(
            run_record,
            paper_trading=paper_trading,
            user_id=user_id,
        )
        run_record = _apply_initial_live_handoff_to_run_record(run_record)
        run_record = sign_ai_research_run_record(
            run_record,
            user_id=user_id,
            workspace_id=str(research_workspace.id),
        )
        response_updates: dict[str, Any] = {}
        if run_record.pipeline != response.pipeline:
            response_updates["pipeline"] = run_record.pipeline
        if run_record.next_actions != response.next_actions:
            response_updates["next_actions"] = run_record.next_actions
        if run_record.promotion_audit != response.promotion_audit:
            response_updates["promotion_audit"] = run_record.promotion_audit
        if response_updates:
            response = response.model_copy(update=response_updates)
        await self._record_pipeline_event(
            user_id=user_id,
            run_id=run_id,
            request=request,
            workspace_id=research_workspace.id,
            stage=status,
            status="completed" if achieved else "failed",
            summary=message,
            output_payload={"pipeline": response.pipeline, "next_actions": response.next_actions},
            metrics=best_metrics,
            error=run_failures[-1] if run_failures and not achieved else paper_trading_error,
        )
        research_workspace = await self._persist_research_run_record(
            user_id,
            research_workspace,
            run_record,
        )
        return response.model_copy(
            update={
                "research_workspace": research_workspace,
                "run_record": run_record,
            }
        )

    async def list_run_records(
        self,
        user_id: str,
        *,
        research_workspace_id: str | None = None,
        limit: int = 20,
    ) -> AIStrategyResearchRunListResponse:
        limit = max(min(int(limit or 20), 100), 1)
        if research_workspace_id:
            workspace = await self.workspace_service.get_workspace(research_workspace_id, user_id)
            if workspace is None:
                raise ValueError("Research workspace not found")
            workspace_records = _research_run_records_from_workspace(workspace, user_id=user_id)
            workspace_records = await self._freshen_trusted_history_run_records(
                user_id,
                workspace,
                workspace_records,
            )
            return AIStrategyResearchRunListResponse(
                total=len(workspace_records),
                items=workspace_records[:limit],
            )

        _, workspaces = await self.workspace_service.list_workspaces(
            user_id,
            skip=0,
            limit=100,
            workspace_type="research",
        )
        all_records: list[AIStrategyResearchRunRecord] = []
        for workspace in workspaces:
            workspace_records = _research_run_records_from_workspace(workspace, user_id=user_id)
            workspace_records = await self._freshen_trusted_history_run_records(
                user_id,
                workspace,
                workspace_records,
            )
            all_records.extend(workspace_records)
        all_records.sort(key=lambda item: item.completed_at, reverse=True)
        return AIStrategyResearchRunListResponse(
            total=len(all_records),
            items=all_records[:limit],
        )

    async def get_run_record(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
        trusted_for_continuation: bool = False,
    ) -> AIStrategyResearchRunRecord | None:
        """Read a run record, requiring a server attestation when requested.

        Historical unsigned records remain inspectable through read-only
        history endpoints.  They are never freshened or used to cause a
        continuation, promotion, paper, or live-state mutation.
        """
        found = await self._find_research_run_record_with_workspace(
            user_id,
            run_id,
            research_workspace_id=research_workspace_id,
            require_trusted=trusted_for_continuation,
        )
        return found[1] if found is not None else None

    async def _freshen_trusted_history_run_records(
        self,
        user_id: str,
        workspace: WorkspaceResponse,
        records: list[AIStrategyResearchRunRecord],
    ) -> list[AIStrategyResearchRunRecord]:
        """Refresh only raw records authenticated in this workspace snapshot.

        Workspace settings are publicly editable history storage. Listing that
        history may still display unsigned legacy records, but it must never
        use one to inspect a paper runtime, stop a unit, add a review lock, or
        write a newly signed replacement. Keep the exact raw signature as the
        source identity through the refresh so duplicate run IDs cannot cross
        that boundary either.
        """
        trusted_signatures = _trusted_run_record_signatures_from_workspace(
            workspace,
            user_id=user_id,
        )
        trusted_records = [
            record
            for record in records
            if str(record.server_provenance_signature or "").strip()
            in trusted_signatures.get(str(record.run_id or "").strip(), set())
        ]
        if not trusted_records:
            return records

        # Apply signed-record-only presentation freshness first.  In
        # particular, an expired live-readiness receipt must be revoked and
        # persisted when it is encountered through the list endpoint too;
        # previously that transition happened only in the single-record
        # reader.  Unsigned display history never reaches this branch.
        pipeline_freshened_records = [
            _research_run_record_with_pipeline(record) for record in trusted_records
        ]
        freshened_records, changed_run_ids = await self._freshen_run_records_with_paper_state(
            user_id,
            pipeline_freshened_records,
        )
        changed_run_ids.update(
            updated.run_id
            for source, updated in zip(trusted_records, freshened_records, strict=True)
            if updated != source
        )
        await self._persist_freshened_run_records(
            user_id,
            workspace,
            freshened_records,
            changed_run_ids=changed_run_ids,
        )
        freshened_by_source = {
            (
                str(record.run_id or "").strip(),
                str(record.server_provenance_signature or "").strip(),
            ): record
            for record in freshened_records
        }
        return [
            freshened_by_source.get(
                (
                    str(record.run_id or "").strip(),
                    str(record.server_provenance_signature or "").strip(),
                ),
                record,
            )
            for record in records
        ]

    async def build_continuation_request_from_run_record(
        self,
        user_id: str,
        run_id: str,
        *,
        overrides: dict[str, Any] | None = None,
        research_workspace_id: str | None = None,
    ) -> AIStrategyResearchRunRequest | None:
        record = await self._find_research_run_record(
            user_id,
            run_id,
            research_workspace_id=research_workspace_id,
            require_trusted=True,
        )
        if record is None:
            return None
        return _continuation_request_from_run_record(record, overrides or {})

    async def continuation_task_updates(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
    ) -> dict[str, Any]:
        """Expose record-derived continuation context before the long task completes."""

        continued_from = str(request.continue_from_run_id or "").strip()
        if not continued_from:
            return {}
        record = await self._find_research_run_record(
            user_id,
            continued_from,
            research_workspace_id=request.research_workspace_id,
            require_trusted=True,
        )
        if record is None:
            return {}

        runtime_context = _record_runtime_context(record)
        context = _continuation_context_from_record(record)
        if context:
            context = _enriched_continuation_context(
                {
                    **dict(request.continuation_context or {}),
                    **context,
                },
                request,
            )

        updates: dict[str, Any] = {"continued_from_run_id": record.run_id}
        source = _continuation_source_from_context(context)
        if source:
            updates["continuation_source"] = source
        if context:
            updates["continuation_context"] = _research_record_continuation_context(context)
        asset_specs = runtime_context.get("asset_specs")
        if isinstance(asset_specs, dict) and asset_specs:
            updates["asset_specs"] = _summarize_asset_specs_for_prompt(asset_specs)
        backtest_environment = runtime_context.get("backtest_environment")
        if isinstance(backtest_environment, dict) and backtest_environment:
            updates["backtest_environment"] = dict(backtest_environment)
        return updates

    async def _freshen_run_records_with_paper_state(
        self,
        user_id: str,
        records: list[AIStrategyResearchRunRecord],
    ) -> tuple[list[AIStrategyResearchRunRecord], set[str]]:
        freshened: list[AIStrategyResearchRunRecord] = []
        changed_run_ids: set[str] = set()
        for record in records:
            updated = await self._freshen_run_record_with_latest_backtests(user_id, record)
            updated = await self._freshen_run_record_with_paper_state(user_id, updated)
            freshened.append(updated)
            if updated != record:
                changed_run_ids.add(updated.run_id)
        return freshened, changed_run_ids

    async def _freshen_run_record_with_latest_backtests(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
    ) -> AIStrategyResearchRunRecord:
        """Refresh persisted iteration metrics after a workspace unit is rerun.

        AI research records keep an immutable-looking summary of each iteration,
        while users can rerun an iteration from its workspace.  Without this
        reconciliation the page keeps rendering the old task ID and metrics,
        including an obsolete ``total_trades=0`` after a repaired strategy has
        produced closed trades.
        """
        if not record.research_workspace_id or not record.iterations:
            return record

        statuses = await self.workspace_service.get_units_status(
            record.research_workspace_id,
            user_id,
        )
        status_by_unit_id = {
            str(payload.get("id") or "").strip(): payload
            for payload in (_dict_payload(item) for item in statuses or [])
            if str(payload.get("id") or "").strip()
        }
        if not status_by_unit_id:
            return record

        refreshed_iterations: list[dict[str, Any]] = []
        changed = False
        for raw_iteration in record.iterations:
            iteration = _dict_payload(raw_iteration)
            unit_id = str(
                _dict_payload(iteration.get("unit")).get("id")
                or iteration.get("unit_id")
                or _dict_payload(iteration.get("run_result")).get("unit_id")
                or ""
            ).strip()
            status_payload = status_by_unit_id.get(unit_id)
            if not unit_id or status_payload is None:
                refreshed_iterations.append(iteration)
                continue

            refreshed = dict(iteration)
            refreshed["unit_status"] = status_payload
            run_result = _dict_payload(iteration.get("run_result"))
            latest_task_id = str(status_payload.get("last_task_id") or "").strip()
            latest_status = str(status_payload.get("run_status") or "").strip()
            if latest_task_id:
                run_result["task_id"] = latest_task_id
            if latest_status:
                run_result["status"] = latest_status
            if unit_id:
                run_result.setdefault("unit_id", unit_id)
            refreshed["run_result"] = run_result

            metrics = _dict_payload(status_payload.get("metrics_snapshot"))
            if metrics:
                refreshed["metrics"] = metrics
                refreshed["sharpe_ratio"] = _metric_float(
                    metrics,
                    "sharpe_ratio",
                    "sharpe",
                    "sharpeRatio",
                )
                refreshed["total_trades"] = _metric_int(
                    metrics,
                    "total_trades",
                    "totalTrades",
                    "trades",
                )

            refreshed_iterations.append(refreshed)
            changed = changed or refreshed != iteration

        if not changed:
            return record

        updates: dict[str, Any] = {"iterations": refreshed_iterations}
        best_iteration = record.best_iteration
        best_payload = next(
            (
                payload
                for payload in refreshed_iterations
                if _optional_gate_int(payload.get("iteration")) == best_iteration
            ),
            None,
        )
        if best_payload is not None:
            best_metrics = _dict_payload(best_payload.get("metrics"))
            if best_metrics:
                updates["best_metrics"] = best_metrics
                updates["best_sharpe"] = _metric_float(
                    best_metrics,
                    "sharpe_ratio",
                    "sharpe",
                    "sharpeRatio",
                )
        return record.model_copy(update=updates)

    async def _freshen_run_record_with_paper_state(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
    ) -> AIStrategyResearchRunRecord:
        if not _run_record_should_auto_refresh_paper_review(record):
            if not (
                record.achieved
                and record.paper_trading_started
                and record.paper_workspace_id
                and _run_record_should_invalidate_missing_paper_target(record)
            ):
                return record
            workspace = await self.workspace_service.get_workspace(
                record.paper_workspace_id,
                user_id,
            )
            if workspace is None:
                return _run_record_with_missing_paper_target(
                    record,
                    reason=f"Paper trading workspace {record.paper_workspace_id} was not found",
                )
            if not record.paper_unit_id:
                return _run_record_with_missing_paper_target(
                    record,
                    reason="Paper trading unit ID is missing",
                )
            unit = _coerce_strategy_unit_response(
                await self.workspace_service.get_unit(
                    workspace.id,
                    record.paper_unit_id,
                    user_id,
                )
            )
            if unit is None:
                return _run_record_with_missing_paper_target(
                    record,
                    reason=f"Paper trading unit {record.paper_unit_id} was not found",
                )
            return record

        workspace = None
        unit = None
        unit_status = None
        if record.paper_workspace_id:
            workspace = await self.workspace_service.get_workspace(
                record.paper_workspace_id,
                user_id,
            )
        if workspace is None:
            if _run_record_should_invalidate_missing_paper_target(record):
                return _run_record_with_missing_paper_target(
                    record,
                    reason=f"Paper trading workspace {record.paper_workspace_id} was not found",
                )
            return record
        if not record.paper_unit_id:
            if _run_record_should_invalidate_missing_paper_target(record):
                return _run_record_with_missing_paper_target(
                    record,
                    reason="Paper trading unit ID is missing",
                )
            return record
        unit = _coerce_strategy_unit_response(
            await self.workspace_service.get_unit(
                workspace.id,
                record.paper_unit_id,
                user_id,
            )
        )
        if unit is None:
            if _run_record_should_invalidate_missing_paper_target(record):
                return _run_record_with_missing_paper_target(
                    record,
                    reason=f"Paper trading unit {record.paper_unit_id} was not found",
                )
            return record
        statuses = await self.workspace_service.get_units_status(workspace.id, user_id)
        unit_status = _find_unit_status(statuses or [], record.paper_unit_id)

        runtime_anchor_trusted = _paper_runtime_evidence_is_trusted(
            user_id=user_id,
            record=record,
            workspace=workspace,
            unit=unit,
        )
        (
            runtime_observation_active,
            runtime_started_at,
            runtime_launch_id,
            runtime_observation_reason,
        ) = await self._observe_active_paper_runtime(
            user_id,
            unit=unit,
            unit_status=unit_status,
        )
        runtime_metrics_observation_trusted = (
            runtime_observation_active
            and _paper_runtime_metrics_observation_is_trusted(
                user_id=user_id,
                unit=unit,
                unit_status=unit_status,
                instance_id=unit.trading_instance_id if unit is not None else None,
                launch_id=runtime_launch_id,
            )
        )
        runtime_evidence_trusted = (
            runtime_anchor_trusted
            and runtime_observation_active
            and runtime_metrics_observation_trusted
        )
        monitoring_plan = _resolve_paper_monitoring_plan(
            record,
            unit if runtime_evidence_trusted else None,
        )
        evaluations = _evaluate_paper_monitoring_plan(
            monitoring_plan,
            record=record,
            unit=unit,
            unit_status=unit_status,
            runtime_evidence_trusted=runtime_evidence_trusted,
            runtime_started_at=runtime_started_at,
        )
        ready_for_live = (
            runtime_evidence_trusted and bool(evaluations) and all(item.passed for item in evaluations)
        )
        review_status = _paper_review_status(
            record,
            workspace=workspace,
            unit=unit,
            evaluations=evaluations,
            ready_for_live=ready_for_live,
            runtime_anchor_trusted=runtime_anchor_trusted,
            runtime_observation_active=runtime_observation_active,
            runtime_metrics_observation_trusted=runtime_metrics_observation_trusted,
            runtime_observation_reason=runtime_observation_reason,
        )
        runtime_observation = _paper_runtime_observation_payload(
            unit.trading_instance_id if runtime_observation_active else None,
            runtime_started_at if runtime_observation_active else None,
            runtime_launch_id if runtime_observation_active else None,
        )
        evaluation_payload = [item.model_dump(mode="json") for item in evaluations]
        next_actions = _paper_review_next_actions(
            review_status,
            evaluations=evaluations,
            monitoring_plan=monitoring_plan,
            live_readiness_expires_at=record.live_readiness_expires_at,
        )
        unit_needs_review_lock = _paper_unit_needs_review_lock(unit, review_status)
        if (
            not _paper_review_refresh_has_meaningful_change(
                record,
                monitoring_plan=monitoring_plan,
                review_status=review_status,
                ready_for_live=ready_for_live,
                evaluation_payload=evaluation_payload,
                next_actions=next_actions,
                runtime_observation=runtime_observation,
            )
            and not unit_needs_review_lock
        ):
            return record

        reviewed_at = _utc_iso_now()
        live_readiness_expires_at = (
            _utc_iso_add_days(reviewed_at, _LIVE_READINESS_VALID_DAYS) if ready_for_live else None
        )
        next_actions = _paper_review_next_actions(
            review_status,
            evaluations=evaluations,
            monitoring_plan=monitoring_plan,
            live_readiness_expires_at=live_readiness_expires_at,
        )
        locked_unit, next_actions, review_lock = await self._lock_paper_unit_for_review_failure(
            user_id,
            record=record,
            workspace=workspace,
            unit=unit,
            review_status=review_status,
            reviewed_at=reviewed_at,
            evaluations=evaluations,
            next_actions=next_actions,
        )
        if locked_unit is not None:
            unit = locked_unit
        live_readiness_checklist = _live_readiness_checklist(
            record,
            status=review_status,
            evaluations=evaluations,
            monitoring_plan=monitoring_plan,
            reviewed_at=reviewed_at,
            expires_at=live_readiness_expires_at,
        )
        pipeline = _pipeline_summary_from_record(
            record,
            paper_trading_started=record.paper_trading_started,
            paper_review_status=review_status,
            paper_review_ready_for_live=ready_for_live,
            live_readiness_checklist=live_readiness_checklist,
            live_readiness_expires_at=live_readiness_expires_at,
        )
        if runtime_observation is not None:
            pipeline["paper_runtime_observation"] = dict(runtime_observation)
        else:
            pipeline.pop("paper_runtime_observation", None)
        pipeline = _pipeline_with_paper_review_lock(pipeline, review_lock)
        paper_handoff = _research_record_handoff_payload(
            _paper_handoff_with_review_lock(
                _paper_handoff_with_live_readiness(
                    _paper_handoff_with_runtime_observation(
                        record.paper_handoff,
                        runtime_observation,
                    ),
                    live_readiness_checklist,
                    expires_at=live_readiness_expires_at,
                ),
                review_lock,
            )
        )
        updated_record = _research_run_record_with_promotion_audit(
            record.model_copy(
                update={
                    "paper_monitoring_plan": [dict(item) for item in monitoring_plan],
                    "paper_review_status": review_status,
                    "paper_review_ready_for_live": ready_for_live,
                    "paper_reviewed_at": reviewed_at,
                    "paper_review_evaluations": evaluation_payload,
                    "paper_review_next_actions": next_actions,
                    "live_readiness_checklist": live_readiness_checklist,
                    "live_readiness_expires_at": live_readiness_expires_at,
                    "paper_handoff": paper_handoff,
                    "pipeline": pipeline,
                    "next_actions": next_actions,
                    # A changed or absent server observation revokes a human
                    # approval.  A later runtime restart must be observed and
                    # reviewed again rather than inheriting an old approval.
                    "live_handoff": (
                        record.live_handoff
                        if ready_for_live
                        and _paper_runtime_observation_from_handoff(record.paper_handoff)
                        == runtime_observation
                        else None
                    ),
                    "live_handoff_approval": (
                        record.live_handoff_approval
                        if ready_for_live
                        and _paper_runtime_observation_from_handoff(record.paper_handoff)
                        == runtime_observation
                        else None
                    ),
                }
            )
        )
        if ready_for_live and review_status == "ready_for_live_candidate":
            package = _build_live_handoff_package(updated_record)
            return _run_record_with_live_handoff(updated_record, package)
        if updated_record.live_handoff is not None:
            package = _build_live_handoff_package(updated_record)
            return _run_record_with_live_handoff(updated_record, package)
        return updated_record

    async def _observe_active_paper_runtime(
        self,
        user_id: str,
        *,
        unit: StrategyUnitResponse | None,
        unit_status: UnitStatusResponse | None,
    ) -> tuple[bool, str | None, str | None, str]:
        """Read a current server-owned process observation for paper review.

        Unit snapshots and paper-equity timestamps are intentionally excluded:
        public APIs can submit or retain those payloads, and a stopped process
        must not accrue a review window from their wall-clock values.  The
        manager re-checks the process while loading its persisted instance;
        its running state and start epoch are therefore the authoritative
        observation for this request.
        """
        if unit is None:
            return False, None, None, "paper_runtime_observation_missing"
        if bool(unit.lock_running) or bool(unit.lock_trading):
            return False, None, None, "paper_runtime_locked"
        if str(unit.trading_mode or "").strip().casefold() != "paper":
            return False, None, None, "paper_runtime_not_running"
        if str(unit.run_status or "").strip().casefold() != "running":
            return False, None, None, "paper_runtime_not_running"
        if unit_status is not None:
            if bool(unit_status.lock_running) or bool(unit_status.lock_trading):
                return False, None, None, "paper_runtime_locked"
            if str(unit_status.run_status or "").strip().casefold() != "running":
                return False, None, None, "paper_runtime_not_running"

        instance_id = str(unit.trading_instance_id or "").strip()
        if not instance_id:
            return False, None, None, "paper_runtime_observation_missing"
        if unit_status is not None:
            status_instance_id = str(unit_status.trading_instance_id or "").strip()
            if status_instance_id and status_instance_id != instance_id:
                return False, None, None, "paper_runtime_observation_missing"

        try:
            instance = await asyncio.to_thread(
                get_live_trading_manager().get_instance,
                instance_id,
                user_id=user_id,
            )
        except Exception:
            logger.warning(
                "Unable to observe paper runtime %s during live-handoff review",
                instance_id,
                exc_info=True,
            )
            return False, None, None, "paper_runtime_observation_missing"
        if not isinstance(instance, dict) or str(instance.get("status") or "").strip().casefold() != "running":
            return False, None, None, "paper_runtime_not_running"
        if not instance.get("pid"):
            return False, None, None, "paper_runtime_observation_missing"
        # Do not consume the legacy user-visible ``started_at`` value: it is
        # local-time, second precision and can be reconstructed by recovery
        # code.  Only the private spawn-time UTC epoch is admissible.
        started_at = str(instance.get(SERVER_RUNTIME_LAUNCH_STARTED_AT_FIELD) or "").strip()
        launch_id = str(instance.get(SERVER_RUNTIME_LAUNCH_ID_FIELD) or "").strip()
        if _paper_runtime_observation_payload(instance_id, started_at, launch_id) is None:
            return False, None, None, "paper_runtime_observation_missing"
        return True, started_at, launch_id, "server_manager"

    async def _assert_active_paper_runtime_for_live_handoff(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
    ) -> None:
        """Recheck current paper execution at approval and live-prepare time."""
        if not record.paper_workspace_id or not record.paper_unit_id:
            raise ValueError("AI_RESEARCH_PAPER_RUNTIME_OBSERVATION_REQUIRED")
        workspace = await self.workspace_service.get_workspace(record.paper_workspace_id, user_id)
        if workspace is None:
            raise ValueError("AI_RESEARCH_PAPER_RUNTIME_OBSERVATION_REQUIRED")
        unit = _coerce_strategy_unit_response(
            await self.workspace_service.get_unit(workspace.id, record.paper_unit_id, user_id)
        )
        if unit is None or not _paper_runtime_evidence_is_trusted(
            user_id=user_id,
            record=record,
            workspace=workspace,
            unit=unit,
        ):
            raise ValueError("AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID")
        statuses = await self.workspace_service.get_units_status(workspace.id, user_id)
        unit_status = _find_unit_status(statuses or [], unit.id)
        active, started_at, launch_id, reason = await self._observe_active_paper_runtime(
            user_id,
            unit=unit,
            unit_status=unit_status,
        )
        if not active:
            raise ValueError(f"AI_RESEARCH_PAPER_RUNTIME_{reason.upper()}")
        current_observation = _paper_runtime_observation_payload(
            unit.trading_instance_id,
            started_at,
            launch_id,
        )
        if current_observation is None or (
            _paper_runtime_observation_from_handoff(record.paper_handoff)
            != current_observation
        ):
            raise ValueError("AI_RESEARCH_PAPER_RUNTIME_OBSERVATION_STALE")

    async def _revalidate_paper_runtime_for_live_handoff(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
    ) -> AIStrategyResearchRunRecord:
        """Refresh paper evidence immediately before an approval or promotion.

        Human approval is evidence about a particular server-observed paper
        runtime, not a permanent waiver of its monitoring gates. Recompute
        the plan from the current anchored unit/status before the final
        launch-epoch assertion. If the runtime has deteriorated, the normal freshening
        path clears the prior handoff/approval and persists that revocation
        before callers can create a live unit.
        """
        refreshed = await self._freshen_run_record_with_paper_state(user_id, record)
        if refreshed == record:
            return record

        workspace = await self.workspace_service.get_workspace(
            record.research_workspace_id,
            user_id,
        )
        if workspace is not None:
            await self._persist_research_run_record(user_id, workspace, refreshed)
        return refreshed

    async def start_paper_trading_from_run(
        self,
        user_id: str,
        run_id: str,
        request: AIStrategyPaperTradingStartRequest,
    ) -> AIStrategyPaperTradingStart:
        record = await self._find_research_run_record(
            user_id,
            run_id,
            research_workspace_id=request.research_workspace_id,
        )
        if record is None:
            raise ValueError("AI research run record not found")
        if not record.achieved:
            raise ValueError("AI research run has not achieved its quality gates")
        robustness_failure = _record_robustness_promotion_failure(record)
        if robustness_failure:
            raise ValueError(robustness_failure)
        if record.paper_trading_started:
            target_missing, reusable_workspace = await self._paper_trading_target_missing(
                user_id,
                record,
            )
            if not target_missing:
                raise ValueError("AI research run has already started paper trading")
            if reusable_workspace is not None and not request.trading_workspace_id:
                request = request.model_copy(update={"trading_workspace_id": reusable_workspace.id})

        record, strategy, unit = await self._resolve_run_record_strategy_unit(user_id, record)
        iteration_payload = _best_iteration_payload(record)

        run_request = _paper_start_request_from_record(record, request)
        iteration = _iteration_from_record_payload(
            record,
            strategy=strategy,
            unit=unit,
            payload=iteration_payload or {},
        )
        try:
            paper_trading = await self._start_paper_trading(
                user_id,
                run_request,
                iteration,
                run_id=record.run_id,
                research_workspace_id=record.research_workspace_id,
            )
        except Exception as exc:
            await self._mark_run_record_paper_start_failed(user_id, record, str(exc))
            raise ValueError(str(exc)) from exc
        paper_trading_error = _paper_trading_start_error(paper_trading)
        if paper_trading_error:
            updated_record = await self._mark_run_record_paper_start_failed(
                user_id,
                record,
                paper_trading_error,
                paper_trading=paper_trading,
            )
            return paper_trading.model_copy(update={"run_record": updated_record})
        updated_record = await self._mark_run_record_paper_started(user_id, record, paper_trading)
        return paper_trading.model_copy(update={"run_record": updated_record})

    async def review_paper_trading_run(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
    ) -> AIStrategyPaperTradingReview:
        record = await self._find_research_run_record(
            user_id,
            run_id,
            research_workspace_id=research_workspace_id,
            # This endpoint is the authoritative review pass.  A preceding
            # history freshen can itself lock a failing paper unit, making the
            # subsequent explicit review observe only that induced lock and
            # lose the metric evidence it must report.
            freshen=False,
        )
        if record is None:
            raise ValueError("AI research run record not found")

        workspace = None
        unit = None
        unit_status = None
        if record.paper_workspace_id:
            workspace = await self.workspace_service.get_workspace(
                record.paper_workspace_id, user_id
            )
        if workspace is not None and record.paper_unit_id:
            unit = _coerce_strategy_unit_response(
                await self.workspace_service.get_unit(
                    workspace.id,
                    record.paper_unit_id,
                    user_id,
                )
            )
            statuses = await self.workspace_service.get_units_status(workspace.id, user_id)
            unit_status = _find_unit_status(statuses or [], record.paper_unit_id)

        runtime_anchor_trusted = _paper_runtime_evidence_is_trusted(
            user_id=user_id,
            record=record,
            workspace=workspace,
            unit=unit,
        )
        (
            runtime_observation_active,
            runtime_started_at,
            runtime_launch_id,
            runtime_observation_reason,
        ) = await self._observe_active_paper_runtime(
            user_id,
            unit=unit,
            unit_status=unit_status,
        )
        runtime_metrics_observation_trusted = (
            runtime_observation_active
            and _paper_runtime_metrics_observation_is_trusted(
                user_id=user_id,
                unit=unit,
                unit_status=unit_status,
                instance_id=unit.trading_instance_id if unit is not None else None,
                launch_id=runtime_launch_id,
            )
        )
        runtime_evidence_trusted = (
            runtime_anchor_trusted
            and runtime_observation_active
            and runtime_metrics_observation_trusted
        )
        monitoring_plan = _resolve_paper_monitoring_plan(
            record,
            unit if runtime_evidence_trusted else None,
        )
        evaluations = _evaluate_paper_monitoring_plan(
            monitoring_plan,
            record=record,
            unit=unit,
            unit_status=unit_status,
            runtime_evidence_trusted=runtime_evidence_trusted,
            runtime_started_at=runtime_started_at,
        )
        ready_for_live = (
            runtime_evidence_trusted and bool(evaluations) and all(item.passed for item in evaluations)
        )
        review_status = _paper_review_status(
            record,
            workspace=workspace,
            unit=unit,
            evaluations=evaluations,
            ready_for_live=ready_for_live,
            runtime_anchor_trusted=runtime_anchor_trusted,
            runtime_observation_active=runtime_observation_active,
            runtime_metrics_observation_trusted=runtime_metrics_observation_trusted,
            runtime_observation_reason=runtime_observation_reason,
        )
        runtime_observation = _paper_runtime_observation_payload(
            unit.trading_instance_id if runtime_observation_active and unit is not None else None,
            runtime_started_at if runtime_observation_active else None,
            runtime_launch_id if runtime_observation_active else None,
        )
        reviewed_at = _utc_iso_now()
        live_readiness_expires_at = (
            _utc_iso_add_days(reviewed_at, _LIVE_READINESS_VALID_DAYS) if ready_for_live else None
        )
        live_readiness_checklist = _live_readiness_checklist(
            record,
            status=review_status,
            evaluations=evaluations,
            monitoring_plan=monitoring_plan,
            reviewed_at=reviewed_at,
            expires_at=live_readiness_expires_at,
        )
        next_actions = _paper_review_next_actions(
            review_status,
            evaluations=evaluations,
            monitoring_plan=monitoring_plan,
            live_readiness_expires_at=live_readiness_expires_at,
        )
        locked_unit, next_actions, review_lock = await self._lock_paper_unit_for_review_failure(
            user_id,
            record=record,
            workspace=workspace,
            unit=unit,
            review_status=review_status,
            reviewed_at=reviewed_at,
            evaluations=evaluations,
            next_actions=next_actions,
        )
        if locked_unit is not None:
            unit = locked_unit
        pipeline = _pipeline_summary_from_record(
            record,
            paper_trading_started=record.paper_trading_started,
            paper_review_status=review_status,
            paper_review_ready_for_live=ready_for_live,
            live_readiness_checklist=live_readiness_checklist,
            live_readiness_expires_at=live_readiness_expires_at,
        )
        if runtime_observation is not None:
            pipeline["paper_runtime_observation"] = dict(runtime_observation)
        else:
            pipeline.pop("paper_runtime_observation", None)
        pipeline = _pipeline_with_paper_review_lock(pipeline, review_lock)
        review = AIStrategyPaperTradingReview(
            run_id=record.run_id,
            research_workspace_id=record.research_workspace_id,
            paper_workspace_id=record.paper_workspace_id,
            paper_unit_id=record.paper_unit_id,
            paper_trading_started=record.paper_trading_started,
            workspace=workspace,
            unit=unit,
            unit_status=unit_status,
            monitoring_plan=monitoring_plan,
            evaluations=evaluations,
            ready_for_live=ready_for_live,
            status=review_status,
            reviewed_at=reviewed_at,
            live_readiness_checklist=live_readiness_checklist,
            live_readiness_expires_at=live_readiness_expires_at,
            pipeline=pipeline,
            next_actions=next_actions,
        )
        updated_record = await self._mark_run_record_paper_reviewed(user_id, record, review)
        if updated_record is not None and updated_record.live_handoff is not None:
            review = review.model_copy(
                update={
                    "live_handoff": updated_record.live_handoff,
                    "pipeline": updated_record.pipeline,
                    "next_actions": updated_record.next_actions,
                }
            )
        return review

    async def _lock_paper_unit_for_review_failure(
        self,
        user_id: str,
        *,
        record: AIStrategyResearchRunRecord,
        workspace: WorkspaceResponse | None,
        unit: StrategyUnitResponse | None,
        review_status: str,
        reviewed_at: str,
        evaluations: list[AIStrategyPaperTradingRuleEvaluation],
        next_actions: list[str],
    ) -> tuple[StrategyUnitResponse | None, list[str], dict[str, Any] | None]:
        if not _paper_review_status_requires_unit_lock(review_status):
            return None, next_actions, None
        if workspace is None or unit is None:
            return None, next_actions, None
        if not _paper_unit_needs_review_lock(unit, review_status):
            existing_lock = _paper_review_lock_payload_for_record(
                (unit.unit_settings or {}).get("ai_research_review_lock"),
                record,
            )
            stop_results = [
                dict(item)
                for item in (existing_lock or {}).get("stop_results", [])
                if isinstance(item, dict)
            ]
            lock_payload = _paper_review_unit_lock_payload(
                record,
                review_status=review_status,
                reviewed_at=reviewed_at,
                evaluations=evaluations,
                next_actions=next_actions,
                stop_results=stop_results,
            )
            unit_settings = dict(unit.unit_settings or {})
            unit_settings["ai_research_review_lock"] = lock_payload
            try:
                updated = await self.workspace_service.update_unit(
                    workspace.id,
                    unit.id,
                    user_id,
                    StrategyUnitUpdate(
                        unit_settings=unit_settings,
                        lock_trading=True,
                        lock_running=True,
                    ),
                    allow_server_owned_ai_research_state=True,
                )
            except Exception:
                updated = None
            if updated is not None:
                return (
                    StrategyUnitResponse.model_validate(updated),
                    _append_unique_text(
                        next_actions,
                        "模拟复核未通过，模拟交易单元已处于停止/锁定状态，需继续投研或人工解锁后再运行。",
                    ),
                    lock_payload,
                )
            return (
                None,
                _append_unique_text(
                    next_actions,
                    "模拟复核未通过，模拟交易单元已处于停止/锁定状态，需继续投研或人工解锁后再运行。",
                ),
                lock_payload,
            )

        stop_results, next_actions = await self._stop_paper_unit_for_review_failure(
            user_id,
            workspace=workspace,
            unit=unit,
            next_actions=next_actions,
        )
        lock_payload = _paper_review_unit_lock_payload(
            record,
            review_status=review_status,
            reviewed_at=reviewed_at,
            evaluations=evaluations,
            next_actions=next_actions,
            stop_results=stop_results,
        )
        unit_settings = dict(unit.unit_settings or {})
        unit_settings["ai_research_review_lock"] = lock_payload
        try:
            updated = await self.workspace_service.update_unit(
                workspace.id,
                unit.id,
                user_id,
                StrategyUnitUpdate(
                    unit_settings=unit_settings,
                    lock_trading=True,
                    lock_running=True,
                ),
                allow_server_owned_ai_research_state=True,
            )
        except Exception as exc:
            return (
                None,
                _append_unique_text(
                    next_actions,
                    f"模拟复核未通过，但自动锁定模拟交易单元失败：{exc}",
                ),
                None,
            )

        if updated is None:
            return (
                None,
                _append_unique_text(
                    next_actions,
                    "模拟复核未通过，但未找到可锁定的模拟交易单元。",
                ),
                None,
            )

        locked_unit = StrategyUnitResponse.model_validate(updated)
        return (
            locked_unit,
            _append_unique_text(
                next_actions,
                "模拟复核未通过，已自动停止并锁定模拟交易单元，需继续投研或人工解锁后再运行。",
            ),
            lock_payload,
        )

    async def _stop_paper_unit_for_review_failure(
        self,
        user_id: str,
        *,
        workspace: WorkspaceResponse,
        unit: StrategyUnitResponse,
        next_actions: list[str],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        stop_units = getattr(self.workspace_service, "stop_units", None)
        if stop_units is None:
            return [], _append_unique_text(
                next_actions,
                "模拟复核未通过，但当前工作区服务不支持自动停止模拟单元。",
            )
        try:
            raw_results = await stop_units(
                workspace.id,
                user_id,
                [unit.id],
                allow_server_owned_ai_research_stop=True,
            )
        except Exception as exc:
            return [], _append_unique_text(
                next_actions,
                f"模拟复核未通过，但自动停止模拟交易单元失败：{exc}",
            )

        stop_results = [dict(item) for item in raw_results or [] if isinstance(item, dict)]
        if stop_results:
            return stop_results, _append_unique_text(
                next_actions,
                "模拟复核未通过，已自动请求停止模拟交易单元。",
            )
        return stop_results, _append_unique_text(
            next_actions,
            "模拟复核未通过，已尝试停止模拟交易单元但未返回停止结果。",
        )

    async def build_live_handoff_package(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
    ) -> AIStrategyLiveHandoffPackage:
        record = await self._find_research_run_record(
            user_id,
            run_id,
            research_workspace_id=research_workspace_id,
        )
        if record is None:
            raise ValueError("AI research run record not found")
        record = _research_run_record_with_pipeline(record)
        package = _build_live_handoff_package(record)
        updated_record = _run_record_with_live_handoff(record, package)
        await self._mark_run_record_live_handoff_built(user_id, record, package)
        return updated_record.live_handoff or package

    async def record_live_handoff_approval(
        self,
        user_id: str,
        run_id: str,
        request: AIStrategyLiveHandoffApprovalRequest,
        *,
        research_workspace_id: str | None = None,
    ) -> AIStrategyLiveHandoffPackage:
        record = await self._find_research_run_record(
            user_id,
            run_id,
            research_workspace_id=research_workspace_id,
            freshen=False,
        )
        if record is None:
            raise ValueError("AI research run record not found")
        record = await self._revalidate_paper_runtime_for_live_handoff(user_id, record)
        record = _research_run_record_with_pipeline(record)
        package = _build_live_handoff_package(record)
        approval = _build_live_handoff_approval_record(
            user_id=user_id,
            record=record,
            package=package,
            request=request,
        )
        await self._mark_run_record_live_handoff_approval(user_id, record, package, approval)
        return _build_live_handoff_package(
            _run_record_with_live_handoff_approval(
                _run_record_with_live_handoff(record, package),
                approval,
            )
        )

    async def prepare_live_trading_from_run(
        self,
        user_id: str,
        run_id: str,
        request: AIStrategyLiveTradingPrepareRequest,
    ) -> AIStrategyLiveTradingPrepare:
        record = await self._find_research_run_record(
            user_id,
            run_id,
            research_workspace_id=request.research_workspace_id,
            freshen=False,
        )
        if record is None:
            raise ValueError("AI research run record not found")
        record = await self._revalidate_paper_runtime_for_live_handoff(user_id, record)
        record = _research_run_record_with_pipeline(record)
        package = _build_live_handoff_package(record)
        if not (
            package.ready_for_live
            and package.status == "approved_for_live"
            and package.approval is not None
            and package.approval.approved
        ):
            raise ValueError("AI research live handoff has not been approved for live trading")

        existing = await self._prepared_live_trading_target(user_id, record)
        if existing is not None:
            workspace, unit = existing
            self.risk_gate_service.assert_trading_unit_pre_run(
                unit,
                workspace_settings=dict(workspace.settings or {}),
            )
            return AIStrategyLiveTradingPrepare(
                workspace=workspace,
                unit=unit,
                prepared=True,
                handoff=_live_trading_prepare_handoff(record, package, workspace, unit),
                next_actions=_live_trading_prepare_next_actions(unit),
            )

        record, strategy, source_unit = await self._resolve_run_record_strategy_unit(
            user_id,
            record,
            prefer_attested_paper_unit=True,
        )
        package = _build_live_handoff_package(record)
        risk_gate = self.risk_gate_service.evaluate_live_preparation(
            record=record,
            package=package,
            request=request,
            source_unit=source_unit,
        )
        if not risk_gate.get("passed"):
            blockers = [
                str(item).strip() for item in risk_gate.get("blockers", []) if str(item).strip()
            ]
            detail = "；".join(blockers[:3]) if blockers else "存在未通过的风控项"
            raise ValueError(f"风控检查未通过: {detail}")
        workspace = None
        if request.trading_workspace_id:
            workspace = await self.workspace_service.get_workspace(
                request.trading_workspace_id,
                user_id,
            )
            if workspace is None:
                raise ValueError("Live trading workspace not found")
        if workspace is None:
            workspace = await self.workspace_service.create_workspace(
                user_id,
                WorkspaceCreate(
                    name=request.live_workspace_name
                    or _bounded_name(f"AI实盘准备 - {strategy.name}", 200),
                    description="AI research approved live handoff workspace",
                    workspace_type="trading",
                ),
            )

        # Workspace/strategy resolution above can take long enough for a
        # running paper process to publish a materially different status. Do
        # the signed runtime refresh immediately before the irreversible live
        # unit write, and consume only this final observation/evaluation.
        record = await self._revalidate_paper_runtime_for_live_handoff(user_id, record)
        record = _research_run_record_with_pipeline(record)
        # Resolve the source again after the final runtime observation.  The
        # live payload must be derived from the sealed paper unit that was
        # actually revalidated, never from an earlier in-memory source or a
        # mutable research iteration row.
        record, strategy, source_unit = await self._resolve_run_record_strategy_unit(
            user_id,
            record,
            prefer_attested_paper_unit=True,
        )
        package = _build_live_handoff_package(record)
        if not (
            package.ready_for_live
            and package.status == "approved_for_live"
            and package.approval is not None
            and package.approval.approved
        ):
            raise ValueError("AI research live handoff has not been approved for live trading")
        risk_gate = self.risk_gate_service.evaluate_live_preparation(
            record=record,
            package=package,
            request=request,
            source_unit=source_unit,
        )
        if not risk_gate.get("passed"):
            blockers = [
                str(item).strip() for item in risk_gate.get("blockers", []) if str(item).strip()
            ]
            detail = "；".join(blockers[:3]) if blockers else "存在未通过的风控项"
            raise ValueError(f"风控检查未通过: {detail}")

        unit_payload = _live_trading_unit_payload_from_record(
            record,
            package=package,
            strategy=strategy,
            source_unit=source_unit,
            request=request,
            risk_gate=risk_gate,
        )
        created_unit = await self.workspace_service.create_unit(
            workspace.id,
            user_id,
            unit_payload,
            allow_server_owned_ai_research_state=True,
        )
        if created_unit is None:
            raise ValueError("Failed to create live trading unit")
        unit = StrategyUnitResponse.model_validate(created_unit)

        handoff = _live_trading_prepare_handoff(
            record,
            package,
            workspace,
            unit,
            risk_gate=risk_gate,
        )
        sealed_data_config = {
            **dict(unit.data_config or {}),
            "ai_research_run_id": record.run_id,
            "ai_research_workspace_id": record.research_workspace_id,
            "ai_research_live_handoff_status": package.status,
        }
        sealed_unit_settings = {
            **dict(unit.unit_settings or {}),
            "ai_research_live_handoff": handoff,
        }
        unit = unit.model_copy(
            update={
                "data_config": sealed_data_config,
                "unit_settings": sealed_unit_settings,
            }
        )
        persisted_unit = await self.workspace_service.update_unit(
            workspace.id,
            unit.id,
            user_id,
            StrategyUnitUpdate(
                data_config=unit.data_config,
                unit_settings=unit.unit_settings,
            ),
            allow_server_owned_ai_research_state=True,
        )
        if persisted_unit is not None:
            unit = StrategyUnitResponse.model_validate(persisted_unit)
        workspace = await self._persist_live_trading_handoff(user_id, workspace, handoff)
        await self._mark_run_record_live_trading_prepared(
            user_id,
            record,
            package,
            workspace=workspace,
            unit=unit,
            handoff=handoff,
        )
        # The source signature is only final after the prepared handoff has
        # been persisted.  Bind the live-unit seal to that canonical revision
        # rather than to an earlier approved record, so a later signed
        # revocation or conflicting same-run history cannot authorize launch.
        prepared_record = await self._find_research_run_record(
            user_id,
            record.run_id,
            research_workspace_id=record.research_workspace_id,
            freshen=False,
        )
        source_signature = (
            str(prepared_record.server_provenance_signature or "").strip()
            if prepared_record is not None
            else ""
        )
        if not source_signature:
            raise ValueError("AI_RESEARCH_LIVE_HANDOFF_PROVENANCE_INVALID")
        live_unit_anchor = issue_ai_research_live_handoff_unit_anchor(
            user_id=user_id,
            research_workspace_id=record.research_workspace_id,
            live_workspace_id=workspace.id,
            live_unit_id=unit.id,
            run_id=record.run_id,
            source_run_signature=source_signature,
            unit=unit,
        )
        if live_unit_anchor is None:
            raise ValueError("AI_RESEARCH_LIVE_HANDOFF_PROVENANCE_INVALID")
        sealed_unit_settings = {
            **dict(unit.unit_settings or {}),
            AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_FIELD: live_unit_anchor,
        }
        persisted_unit = await self.workspace_service.update_unit(
            workspace.id,
            unit.id,
            user_id,
            StrategyUnitUpdate(unit_settings=sealed_unit_settings),
            allow_server_owned_ai_research_state=True,
            sync_runtime=False,
        )
        if persisted_unit is None:
            raise ValueError("AI_RESEARCH_LIVE_HANDOFF_PROVENANCE_INVALID")
        unit = StrategyUnitResponse.model_validate(persisted_unit)
        return AIStrategyLiveTradingPrepare(
            workspace=workspace,
            unit=unit,
            prepared=True,
            handoff=handoff,
            next_actions=_live_trading_prepare_next_actions(unit),
        )

    async def activate_prepared_live_trading_from_run(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
    ) -> AIStrategyLiveTradingPrepare:
        """Start one prepared live handoff through the server-only boundary.

        Prepared units remain locked so generic workspace routes cannot turn a
        historical approval into execution.  This is the only activation path:
        it refreshes the current paper evidence twice, temporarily clears the
        locks for the manager preflight, and restores them regardless of the
        start result.  The manager then independently verifies the sealed live
        unit against the HMAC-attested source run.
        """
        record = await self._find_research_run_record(
            user_id,
            run_id,
            research_workspace_id=research_workspace_id,
            freshen=False,
        )
        if record is None:
            raise ValueError("AI research run record not found")
        record = await self._revalidate_paper_runtime_for_live_handoff(user_id, record)
        record = _research_run_record_with_pipeline(record)
        package = _build_live_handoff_package(record)
        if not (
            package.ready_for_live
            and package.status == "approved_for_live"
            and package.approval is not None
            and package.approval.approved
        ):
            raise ValueError("AI research live handoff has not been approved for live trading")
        target = await self._prepared_live_trading_target(user_id, record)
        if target is None:
            raise ValueError("AI research live handoff has not been prepared")
        workspace, unit = target

        # The final review must happen after every lookup/allocation above and
        # immediately before changing the live unit's execution locks.
        record = await self._revalidate_paper_runtime_for_live_handoff(user_id, record)
        record = _research_run_record_with_pipeline(record)
        package = _build_live_handoff_package(record)
        if not (
            package.ready_for_live
            and package.status == "approved_for_live"
            and package.approval is not None
            and package.approval.approved
        ):
            raise ValueError("AI research live handoff has not been approved for live trading")

        unlocked = await self.workspace_service.update_unit(
            workspace.id,
            unit.id,
            user_id,
            StrategyUnitUpdate(lock_trading=False, lock_running=False),
            allow_server_owned_ai_research_state=True,
            sync_runtime=False,
        )
        if unlocked is None:
            raise ValueError("AI research live handoff unit was not found")
        unlocked_unit = StrategyUnitResponse.model_validate(unlocked)

        async def validate_immediately_before_live_spawn() -> None:
            """Re-observe the exact paper source after runtime materialization."""
            current = await self._revalidate_paper_runtime_for_live_handoff(user_id, record)
            current = _research_run_record_with_pipeline(current)
            current_package = _build_live_handoff_package(current)
            if not (
                current_package.ready_for_live
                and current_package.status == "approved_for_live"
                and current_package.approval is not None
                and current_package.approval.approved
            ):
                raise ValueError("AI research live handoff has not been approved for live trading")

        try:
            # A second revalidation closes the unlock-to-manager boundary: if
            # the paper source changes here, relock before any live process is
            # launched.  ``run_units`` separately checks the live-unit seal.
            record = await self._revalidate_paper_runtime_for_live_handoff(user_id, record)
            record = _research_run_record_with_pipeline(record)
            package = _build_live_handoff_package(record)
            if not (
                package.ready_for_live
                and package.status == "approved_for_live"
                and package.approval is not None
                and package.approval.approved
            ):
                raise ValueError("AI research live handoff has not been approved for live trading")
            results = await self.workspace_service.run_units(
                workspace.id,
                user_id,
                [unlocked_unit.id],
                allow_server_owned_ai_research_live_handoff_start=True,
                live_handoff_pre_start_validator=validate_immediately_before_live_spawn,
            )
            started = next((item for item in results if item.get("unit_id") == unlocked_unit.id), None)
            if not isinstance(started, dict) or str(started.get("status") or "") != "running":
                raise ValueError(str((started or {}).get("error") or "Failed to start live handoff"))
        finally:
            # Preserve the post-approval execution fence even after a valid
            # start. The manager owns the running process; browser routes may
            # not use this temporary unlock to mutate/restart it.
            relocked = await self.workspace_service.update_unit(
                workspace.id,
                unit.id,
                user_id,
                StrategyUnitUpdate(lock_trading=True, lock_running=True),
                allow_server_owned_ai_research_state=True,
                sync_runtime=False,
            )
        if relocked is None:
            raise ValueError("AI research live handoff relock failed")
        live_unit = StrategyUnitResponse.model_validate(relocked)
        handoff = _live_trading_prepare_handoff(record, package, workspace, live_unit)
        return AIStrategyLiveTradingPrepare(
            workspace=workspace,
            unit=live_unit,
            prepared=True,
            activated=True,
            activation_status="running",
            activation_instance_id=str(live_unit.trading_instance_id or "") or None,
            handoff=handoff,
            next_actions=_live_trading_prepare_next_actions(live_unit),
        )

    async def deactivate_prepared_live_trading_from_run(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
    ) -> AIStrategyLiveTradingPrepare:
        """Stop and revoke one prepared live handoff through a server boundary.

        Generic workspace, simulation, and live-manager stop routes must not
        be able to alter protected handoffs.  This operation is the sole
        deactivation path: it validates the sealed unit identity, stops the
        process with an internal capability, then persists a newly signed
        revocation so the former human approval cannot be reused to restart.
        """
        found = await self._find_research_run_record_with_workspace(
            user_id,
            run_id,
            research_workspace_id=research_workspace_id,
            freshen=False,
        )
        research_workspace: WorkspaceResponse | None = None
        target: tuple[WorkspaceResponse, StrategyUnitResponse] | None = None
        historic_stop_recovery = found is None
        if found is not None:
            research_workspace, record = found
            target = await self._prepared_live_trading_target(user_id, record)
        else:
            # ``last_run`` is intentionally the only canonical source for a
            # state-changing launch.  A later, unrelated run can therefore
            # displace an active handoff from it.  Emergency stop has a
            # narrower recovery rule: locate a sealed live target first and
            # then load one raw HMAC-valid historical revision for the exact
            # workspace/run so revocation can be made durable.  This path is
            # never used by activation or any strategy/paper promotion.
            recovered = await self._historic_live_handoff_stop_source(
                user_id,
                run_id,
                research_workspace_id=research_workspace_id,
            )
            if recovered is None:
                raise ValueError("AI research run record not found")
            research_workspace, record, target = recovered
        if target is None:
            # Paper-target invalidation intentionally clears the mutable
            # live-target fields from the run record.  That must not strand a
            # still-running, sealed live unit behind public stop guards.  The
            # fallback scans only the owner's live workspaces and accepts a
            # target solely when its HMAC live-unit anchor binds this exact
            # research workspace/run.  It is stop-only: activation still
            # requires the canonical approved source record.
            target = await self._sealed_live_handoff_target_for_stop(
                user_id,
                research_workspace_id=record.research_workspace_id,
                run_id=record.run_id,
            )
        if target is None:
            raise ValueError("AI research live handoff has not been prepared")
        workspace, unit = target
        if not (
            record.live_trading_prepared
            and record.live_workspace_id == workspace.id
            and record.live_unit_id == unit.id
        ):
            # Retain the verified fallback identity in the pending/failed
            # server state so a failed emergency stop remains retryable.
            record = record.model_copy(
                update={
                    "live_workspace_id": workspace.id,
                    "live_workspace_name": workspace.name,
                    "live_unit_id": unit.id,
                    "live_trading_prepared": True,
                }
            )
        settings = dict(unit.unit_settings or {})
        anchor = settings.get(AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_FIELD)
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
                research_workspace_id=record.research_workspace_id,
                live_workspace_id=workspace.id,
                live_unit_id=unit.id,
                run_id=record.run_id,
                source_run_signature=source_signature,
                unit=unit,
            )
        ):
            raise ValueError("AI_RESEARCH_LIVE_HANDOFF_PROVENANCE_INVALID")

        if research_workspace is None or str(research_workspace.id) != str(
            record.research_workspace_id
        ):
            research_workspace = await self.workspace_service.get_workspace(
                record.research_workspace_id,
                user_id,
            )
        if research_workspace is None:
            raise ValueError("Research workspace not found")

        # A normal record is the canonical ``last_run`` and may use the
        # regular writer.  Historic emergency recovery must preserve a later
        # unrelated canonical run: mutate only the exact authenticated A
        # history entry used to stop A, never overwrite B's ``last_run``.
        historic_source_signature = str(record.server_provenance_signature or "").strip()

        async def persist_stop_state(
            updated_record: AIStrategyResearchRunRecord,
        ) -> AIStrategyResearchRunRecord:
            nonlocal research_workspace, historic_source_signature
            if not historic_stop_recovery:
                research_workspace = await self._persist_research_run_record(
                    user_id,
                    research_workspace,
                    updated_record,
                )
                return updated_record
            research_workspace, signed_record = await self._persist_historic_live_handoff_stop_record(
                user_id,
                research_workspace,
                updated_record,
                source_signature=historic_source_signature,
            )
            historic_source_signature = str(signed_record.server_provenance_signature or "").strip()
            return signed_record

        # Revocation has to reach durable server-owned state *before* asking
        # the runtime to stop.  A successful stop followed by a persistence
        # failure must not leave the old approved source record available for
        # a public restart.  Keep the target ids so this same endpoint can
        # retry a failed emergency stop, but remove every approval/package
        # that could authorize a new launch.
        pending_pipeline = dict(record.pipeline or {})
        pending_pipeline.update(
            {
                "current_stage": "live_handoff_stop_pending",
                "live_handoff_status": "stop_pending",
                "live_handoff_approved": False,
                "live_handoff_stop_pending": True,
                "live_handoff_stop_failed": False,
                "live_unit_locked": True,
                "live_trading_prepared": True,
            }
        )
        pending_record = record.model_copy(
            update={
                "paper_review_status": "live_handoff_stop_pending",
                "paper_review_ready_for_live": False,
                "live_handoff": None,
                "live_handoff_approval": None,
                # Preserve these fields solely to let this server-owned stop
                # boundary find/retry the already-sealed live target.
                "live_trading_prepared": True,
                "pipeline": pending_pipeline,
                "next_actions": [
                    "实盘交接正在由受控服务端入口停止，当前批准已失效。",
                    "停止确认前不得重新启动该实盘单元。",
                ],
            }
        )
        try:
            pending_record = await persist_stop_state(pending_record)
        except Exception as exc:
            raise ValueError(
                "AI_RESEARCH_LIVE_HANDOFF_DEACTIVATION_STATE_PERSIST_FAILED"
            ) from exc

        async def record_stop_failure(reason: str) -> None:
            """Persist a non-authorizing retry state without reviving approval."""
            failed_pipeline = dict(pending_record.pipeline or {})
            failed_pipeline.update(
                {
                    "current_stage": "live_handoff_stop_failed",
                    "live_handoff_status": "stop_failed",
                    "live_handoff_stop_pending": False,
                    "live_handoff_stop_failed": True,
                    "live_handoff_stop_error": str(reason or "stop verification failed"),
                    "live_handoff_approved": False,
                    "live_unit_locked": True,
                }
            )
            failed_record = pending_record.model_copy(
                update={
                    "paper_review_status": "live_handoff_stop_failed",
                    "paper_review_ready_for_live": False,
                    "live_handoff": None,
                    "live_handoff_approval": None,
                    "live_trading_prepared": True,
                    "pipeline": failed_pipeline,
                    "next_actions": [
                        "实盘交接停止未被服务端确认，批准保持撤销。",
                        "请通过受控停机入口重试；在确认停止前不得重新上线。",
                    ],
                }
            )
            try:
                await persist_stop_state(failed_record)
            except Exception:
                # The prior ``stop_pending`` record is already durable and
                # non-authorizing.  Never turn a secondary audit write error
                # into a path that proceeds with revocation success.
                logger.warning(
                    "Unable to persist AI live-handoff stop failure for run {}",
                    record.run_id,
                    exc_info=True,
                )

        try:
            stop_results = await self.workspace_service.stop_units(
                workspace.id,
                user_id,
                [unit.id],
                allow_server_owned_ai_research_live_handoff_stop=True,
            )
        except Exception as exc:
            await record_stop_failure(str(exc))
            raise ValueError("AI_RESEARCH_LIVE_HANDOFF_DEACTIVATION_STOP_FAILED") from exc

        confirmed_stop = next(
            (
                item
                for item in (stop_results or [])
                if isinstance(item, dict) and str(item.get("unit_id") or "") == str(unit.id)
            ),
            None,
        )
        if not isinstance(confirmed_stop, dict) or confirmed_stop.get("cancelled") is not True:
            await record_stop_failure(
                str((confirmed_stop or {}).get("error") or "runtime stop was not confirmed")
            )
            raise ValueError("AI_RESEARCH_LIVE_HANDOFF_DEACTIVATION_STOP_FAILED")

        instance_id = str(unit.trading_instance_id or "").strip()
        if instance_id:
            try:
                instance = await asyncio.to_thread(
                    get_live_trading_manager().get_instance,
                    instance_id,
                    user_id=user_id,
                )
            except Exception as exc:
                await record_stop_failure("runtime state could not be verified")
                raise ValueError("AI_RESEARCH_LIVE_HANDOFF_DEACTIVATION_STOP_FAILED") from exc
            runtime_status = (
                str(instance.get("status") or "").strip().casefold()
                if isinstance(instance, dict)
                else ""
            )
            if runtime_status not in {"stopped", "idle", "error", "failed", "cancelled"}:
                await record_stop_failure("runtime remains active after stop request")
                raise ValueError("AI_RESEARCH_LIVE_HANDOFF_DEACTIVATION_STOP_FAILED")

        stopped_payload = await self.workspace_service.get_unit(workspace.id, unit.id, user_id)
        stopped_unit = (
            StrategyUnitResponse.model_validate(stopped_payload)
            if stopped_payload is not None
            else unit
        )
        pipeline = dict(record.pipeline or {})
        pipeline.update(
            {
                "current_stage": "live_handoff_deactivated",
                "live_handoff_status": "deactivated",
                "live_handoff_approved": False,
                "live_unit_locked": True,
                "live_trading_prepared": False,
            }
        )
        revocation_event = {
            "stage": "live_handoff_deactivated",
            "status": "completed",
            "at": _utc_iso_now(),
            "live_workspace_id": workspace.id,
            "live_unit_id": unit.id,
            "reason": "server_controlled_deactivation",
        }
        revoked = pending_record.model_copy(
            update={
                "paper_review_status": "live_handoff_deactivated",
                "paper_review_ready_for_live": False,
                "live_handoff": None,
                "live_handoff_approval": None,
                "live_trading_prepared": False,
                "live_trading_prepared_at": None,
                "pipeline": pipeline,
                "promotion_audit": [*list(record.promotion_audit or []), revocation_event],
                "next_actions": [
                    "实盘交接已由受控服务端入口停止并撤销。",
                    "若需再次上线，必须重新复核模拟盘并获得新的人工审批。",
                ],
            }
        )
        await persist_stop_state(revoked)
        return AIStrategyLiveTradingPrepare(
            workspace=workspace,
            unit=stopped_unit,
            prepared=False,
            activated=False,
            activation_status="deactivated",
            activation_instance_id=str(stopped_unit.trading_instance_id or "") or None,
            handoff={
                "run_id": record.run_id,
                "live_workspace_id": workspace.id,
                "live_unit_id": unit.id,
                "status": "deactivated",
            },
            next_actions=[
                "已停止并撤销该实盘交接。",
                "重新上线前需要新的模拟盘复核和人工审批。",
            ],
        )

    async def _resolve_run_record_strategy_unit(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        *,
        prefer_attested_paper_unit: bool = False,
    ) -> tuple[AIStrategyResearchRunRecord, StrategyResponse, StrategyUnitResponse]:
        """Resolve a promotion source without reading a mutable research unit.

        A run record is HMAC-attested, but a workspace unit row is intentionally
        editable during research.  Promotion must therefore use either the
        signed iteration snapshots or, for an already running paper handoff,
        the separately anchored paper unit.  Fetching ``iteration.unit_id``
        from the research workspace here would let a later public update alter
        the configuration copied into paper or live execution.
        """
        iteration_payload = _best_iteration_payload(record)
        if (
            not record.best_strategy_id
            and not _strategy_id_from_iteration_payload(iteration_payload or {})
            and not _iteration_payload_has_strategy_snapshot(iteration_payload or {})
        ):
            raise ValueError("AI research run record has no best strategy to promote")

        if prefer_attested_paper_unit:
            paper_unit = await self._attested_paper_promotion_unit(user_id, record)
            if paper_unit is not None:
                # Prefer the signed source code even after paper promotion.
                # The paper anchor verifies the current template digest as a
                # fallback for old records, but a new live target should not
                # obtain executable code from that mutable strategy row.
                strategy = (
                    _strategy_from_iteration_snapshot(
                        record,
                        iteration_payload,
                        user_id=user_id,
                    )
                    if iteration_payload is not None
                    else None
                )
                if strategy is not None:
                    strategy = await self._persist_strategy_snapshot_for_promotion(
                        user_id,
                        record,
                        strategy,
                    )
                    record = record.model_copy(
                        update={
                            "best_strategy_id": strategy.id,
                            "best_strategy_name": strategy.name,
                        }
                    )
                else:
                    # Legacy records without an executable signed snapshot
                    # remain promotable only while the verified paper anchor
                    # proves the current shared template is byte-for-byte the
                    # one that paper execution sealed.
                    strategy = await self.strategy_service.get_strategy(
                        paper_unit.strategy_id,
                        user_id,
                    )
                if strategy is None:
                    raise ValueError("Attested paper strategy is no longer available")
                return record, strategy, paper_unit

        # Before the first paper handoff there is no protected strategy
        # template yet.  Materialize a new strategy from the signed snapshot
        # instead of re-reading ``best_strategy_id``: that shared source can
        # otherwise be changed between research completion and paper start.
        strategy = None
        if iteration_payload is not None:
            strategy = _strategy_from_iteration_snapshot(
                record,
                iteration_payload,
                user_id=user_id,
            )
            if strategy is not None:
                strategy = await self._persist_strategy_snapshot_for_promotion(
                    user_id,
                    record,
                    strategy,
                )
                record = record.model_copy(
                    update={
                        "best_strategy_id": strategy.id,
                        "best_strategy_name": strategy.name,
                    }
                )
        if strategy is None and iteration_payload is not None:
            raise ValueError("AI research run record has no signed strategy snapshot to promote")
        if strategy is None and record.best_strategy_id:
            # A record without an iteration payload cannot provide a sealed
            # unit snapshot either. Keep this branch only for the precise
            # validation error below rather than trusting a mutable strategy.
            raise ValueError("AI research run record has no signed strategy snapshot to promote")
        if strategy is None:
            raise ValueError("Best strategy not found and run record has no strategy snapshot")

        unit = (
            _unit_from_iteration_snapshot(
                record,
                strategy=strategy,
                payload=iteration_payload,
            )
            if iteration_payload is not None
            else None
        )
        if unit is None:
            raise ValueError("AI research run record has no signed unit snapshot to promote")
        return record, strategy, unit

    async def _attested_paper_promotion_unit(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
    ) -> StrategyUnitResponse | None:
        """Return the current paper source only when its anchor still verifies."""
        has_paper_target = bool(record.paper_workspace_id or record.paper_unit_id)
        if not has_paper_target:
            return None
        if not record.paper_workspace_id or not record.paper_unit_id:
            raise ValueError("AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID")
        workspace = await self.workspace_service.get_workspace(record.paper_workspace_id, user_id)
        if workspace is None:
            raise ValueError("AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID")
        unit = _coerce_strategy_unit_response(
            await self.workspace_service.get_unit(workspace.id, record.paper_unit_id, user_id)
        )
        if unit is None or not _paper_runtime_evidence_is_trusted(
            user_id=user_id,
            record=record,
            workspace=workspace,
            unit=unit,
        ):
            raise ValueError("AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID")
        return unit

    async def _prepared_live_trading_target(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
    ) -> tuple[WorkspaceResponse, StrategyUnitResponse] | None:
        if not (record.live_trading_prepared and record.live_workspace_id and record.live_unit_id):
            return None
        workspace = await self.workspace_service.get_workspace(record.live_workspace_id, user_id)
        if workspace is None:
            return None
        unit = _coerce_strategy_unit_response(
            await self.workspace_service.get_unit(workspace.id, record.live_unit_id, user_id)
        )
        if unit is None:
            return None
        return workspace, unit

    async def _sealed_live_handoff_target_for_stop(
        self,
        user_id: str,
        *,
        research_workspace_id: str,
        run_id: str,
    ) -> tuple[WorkspaceResponse, StrategyUnitResponse] | None:
        """Find one HMAC-sealed live target only for emergency stop recovery.

        A paper-target-missing refresh deliberately removes the cached live
        ids from the signed run.  The protected process remains public-stop
        forbidden, so the controlled deactivation boundary needs a separate
        recovery lookup.  It must never become an activation resolver: caller
        code still has to pass the regular approved-record checks before it
        can launch anything.
        """
        normalized_research_workspace_id = str(research_workspace_id or "").strip()
        normalized_run_id = str(run_id or "").strip()
        if not normalized_research_workspace_id or not normalized_run_id:
            return None
        _, workspaces = await self.workspace_service.list_workspaces(
            user_id,
            skip=0,
            limit=1000,
            workspace_type="trading",
        )
        for workspace in workspaces:
            units = await self.workspace_service.list_units(workspace.id, user_id)
            for raw_unit in units or []:
                unit = _coerce_strategy_unit_response(raw_unit)
                if unit is None or str(unit.trading_mode or "").strip().casefold() != "live":
                    continue
                settings = dict(unit.unit_settings or {})
                anchor = settings.get(AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_FIELD)
                source_signature = (
                    str(anchor.get("source_run_signature") or "").strip()
                    if isinstance(anchor, dict)
                    else ""
                )
                if not (
                    isinstance(anchor, dict)
                    and source_signature
                    and str(anchor.get("research_workspace_id") or "").strip()
                    == normalized_research_workspace_id
                    and str(anchor.get("run_id") or "").strip() == normalized_run_id
                    and verify_ai_research_live_handoff_unit_anchor(
                        anchor,
                        user_id=user_id,
                        research_workspace_id=normalized_research_workspace_id,
                        live_workspace_id=workspace.id,
                        live_unit_id=unit.id,
                        run_id=normalized_run_id,
                        source_run_signature=source_signature,
                        unit=unit,
                    )
                ):
                    continue
                return workspace, unit
        return None

    async def _historic_live_handoff_stop_source(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None,
    ) -> tuple[
        WorkspaceResponse,
        AIStrategyResearchRunRecord,
        tuple[WorkspaceResponse, StrategyUnitResponse],
    ] | None:
        """Recover a historic signed source solely to stop a sealed live unit.

        ``last_run`` intentionally has stronger rules than history: it is the
        one canonical revision allowed to launch a continuation or a live
        handoff.  A later normal research run can replace that pointer while
        an earlier sealed live process remains active.  This recovery helper
        is deliberately more limited.  It first proves the target's live-unit
        anchor, then accepts only an HMAC-valid raw historical record from
        the same research workspace so the stop-pending revocation can be
        persisted.  No caller may use this result to activate, prepare, or
        otherwise revive execution.
        """
        normalized_run_id = str(run_id or "").strip()
        normalized_workspace_id = str(research_workspace_id or "").strip()
        if not normalized_run_id:
            return None

        if normalized_workspace_id:
            workspace = await self.workspace_service.get_workspace(
                normalized_workspace_id,
                user_id,
            )
            if workspace is None:
                raise ValueError("Research workspace not found")
            research_workspaces = [workspace]
        else:
            _, research_workspaces = await self.workspace_service.list_workspaces(
                user_id,
                skip=0,
                limit=1000,
                workspace_type="research",
            )

        recovered: list[
            tuple[
                WorkspaceResponse,
                AIStrategyResearchRunRecord,
                tuple[WorkspaceResponse, StrategyUnitResponse],
            ]
        ] = []
        for workspace in research_workspaces:
            sealed_target = await self._sealed_live_handoff_target_for_stop(
                user_id,
                research_workspace_id=workspace.id,
                run_id=normalized_run_id,
            )
            if sealed_target is None:
                continue
            _, unit = sealed_target
            anchor = (
                dict(unit.unit_settings or {}).get(AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_FIELD)
            )
            source_signature = (
                str(anchor.get("source_run_signature") or "").strip()
                if isinstance(anchor, dict)
                else ""
            )
            record = _trusted_historic_run_record_for_stop(
                workspace,
                user_id=user_id,
                run_id=normalized_run_id,
                source_signature=source_signature,
            )
            if record is not None:
                recovered.append((workspace, record, sealed_target))

        # The stop boundary must not guess across two separately sealed
        # targets with the same caller-supplied run id.  A human can retry
        # with the exact research workspace id, while all generic public
        # stop/start paths remain denied.
        return recovered[0] if len(recovered) == 1 else None

    async def _persist_live_trading_handoff(
        self,
        user_id: str,
        workspace: WorkspaceResponse,
        handoff: dict[str, Any],
    ) -> WorkspaceResponse:
        settings = dict(workspace.settings or {})
        ai_handoff = dict(settings.get("ai_research_live_handoff") or {})
        handoff_payload = dict(handoff)

        existing: list[dict[str, Any]] = []
        raw_handoffs = ai_handoff.get("handoffs")
        if isinstance(raw_handoffs, list):
            existing = [dict(item) for item in raw_handoffs if isinstance(item, dict)]
        ai_handoff["last_handoff"] = handoff_payload
        ai_handoff["handoffs"] = [
            handoff_payload,
            *[
                item
                for item in existing
                if str(item.get("run_id") or "") != str(handoff_payload.get("run_id") or "")
            ],
        ][:20]

        updated = await self.workspace_service.update_workspace(
            workspace.id,
            user_id,
            WorkspaceUpdate(settings={"ai_research_live_handoff": ai_handoff}),
        )
        if updated is not None:
            return updated

        settings["ai_research_live_handoff"] = ai_handoff
        return workspace.model_copy(update={"settings": settings})

    async def _ensure_research_workspace(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
    ) -> WorkspaceResponse:
        if request.research_workspace_id:
            workspace = await self.workspace_service.get_workspace(
                request.research_workspace_id, user_id
            )
            if workspace is None:
                raise ValueError("Research workspace not found")
            return workspace
        name = _research_workspace_name(request)
        return await self.workspace_service.create_workspace(
            user_id,
            WorkspaceCreate(
                name=name,
                description="AI generated strategy research loop",
                workspace_type="research",
            ),
        )

    async def _prepare_initial_draft(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
    ) -> tuple[AIStrategyResearchRunRequest, AIStrategyDraft | None]:
        seed_strategy_id = request.seed_strategy_id
        seed_record: AIStrategyResearchRunRecord | None = None
        seed_iteration_payload: dict[str, Any] | None = None
        update: dict[str, Any] = {}
        explicit_fields = _request_explicit_fields(request)
        if request.continuation_context:
            update["continuation_context"] = _enriched_continuation_context(
                request.continuation_context,
                request,
            )
        if request.continue_from_run_id:
            record = await self._find_research_run_record(
                user_id,
                request.continue_from_run_id,
                research_workspace_id=request.research_workspace_id,
            )
            if record is None:
                raise ValueError("AI research run record not found")
            seed_record = record
            seed_iteration_payload = _best_iteration_payload(record)
            runtime_context = _record_runtime_context(record)
            backtest_environment = (
                dict(runtime_context.get("backtest_environment"))
                if isinstance(runtime_context.get("backtest_environment"), dict)
                else {}
            )
            if not seed_strategy_id:
                seed_strategy_id = record.best_strategy_id or _strategy_id_from_iteration_payload(
                    seed_iteration_payload or {}
                )
                if (
                    not seed_strategy_id
                    and seed_iteration_payload
                    and _iteration_payload_has_strategy_snapshot(seed_iteration_payload)
                ):
                    seed_strategy_id = _fallback_snapshot_strategy_id(record)
            if not seed_strategy_id:
                raise ValueError("AI research run record has no best strategy to continue")
            if not request.research_workspace_id:
                update["research_workspace_id"] = record.research_workspace_id
            if not request.symbol_name and record.symbol_name:
                update["symbol_name"] = record.symbol_name
            if not request.knowledge_base_id and record.knowledge_base_id:
                update["knowledge_base_id"] = record.knowledge_base_id
            if "start_date" not in explicit_fields and record.start_date:
                update["start_date"] = record.start_date
            if "end_date" not in explicit_fields and record.end_date:
                update["end_date"] = record.end_date
            if "initial_cash" not in explicit_fields:
                update["initial_cash"] = _runtime_float(
                    backtest_environment.get("initial_cash"),
                    record.initial_cash,
                )
            if "commission" not in explicit_fields:
                update["commission"] = _runtime_float(
                    backtest_environment.get("commission"),
                    record.commission,
                )
            if "annual_days" not in explicit_fields:
                update["annual_days"] = _runtime_int(
                    backtest_environment.get("annual_days"),
                    record.annual_days,
                )
            if "calc_method" not in explicit_fields and record.calc_method:
                update["calc_method"] = _runtime_text(
                    backtest_environment.get("calc_method"),
                    record.calc_method,
                )
            if "weight_mode" not in explicit_fields and record.weight_mode:
                update["weight_mode"] = _runtime_text(
                    backtest_environment.get("weight_mode"),
                    record.weight_mode,
                )
            if "backtest_timeout_seconds" not in explicit_fields:
                update["backtest_timeout_seconds"] = record.backtest_timeout_seconds
            if "poll_interval_seconds" not in explicit_fields:
                update["poll_interval_seconds"] = record.poll_interval_seconds
            if record.thinking_mode and "thinking_mode" not in explicit_fields:
                update["thinking_mode"] = record.thinking_mode
            update.update(_continuation_runtime_updates(record, request, explicit_fields))
            continuation_context = _continuation_context_from_record(record)
            if continuation_context:
                update["continuation_context"] = _enriched_continuation_context(
                    {
                        **dict(request.continuation_context or {}),
                        **continuation_context,
                    },
                    request,
                )

        if seed_strategy_id:
            update["seed_strategy_id"] = seed_strategy_id
            effective_request = request.model_copy(update=update) if update else request
            strategy = await self.strategy_service.get_strategy(seed_strategy_id, user_id)
            if strategy is None and seed_record is not None and seed_iteration_payload is not None:
                strategy = _strategy_from_iteration_snapshot(
                    seed_record,
                    seed_iteration_payload,
                    user_id=user_id,
                )
            if strategy is None:
                raise ValueError("Seed strategy not found and run record has no strategy snapshot")
            return effective_request, _draft_from_strategy(strategy, effective_request)

        effective_request = request.model_copy(update=update) if update else request
        return effective_request, None

    async def _find_research_run_record(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
        require_trusted: bool = True,
        freshen: bool = True,
    ) -> AIStrategyResearchRunRecord | None:
        found = await self._find_research_run_record_with_workspace(
            user_id,
            run_id,
            research_workspace_id=research_workspace_id,
            require_trusted=require_trusted,
            freshen=freshen,
        )
        return found[1] if found is not None else None

    async def _find_research_run_record_with_workspace(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
        require_trusted: bool = True,
        freshen: bool = True,
    ) -> tuple[WorkspaceResponse, AIStrategyResearchRunRecord] | None:
        run_id = str(run_id or "").strip()
        if not run_id:
            return None

        if research_workspace_id:
            workspace = await self.workspace_service.get_workspace(research_workspace_id, user_id)
            if workspace is None:
                raise ValueError("Research workspace not found")
            record = (
                _find_trusted_run_record_in_workspace(
                    workspace,
                    user_id=user_id,
                    run_id=run_id,
                )
                if require_trusted
                else _find_run_record_in_workspace(workspace, run_id, user_id=user_id)
            )
            if record is None:
                return None
            if not freshen:
                return workspace, record
            if require_trusted:
                return await self._freshen_found_run_record(user_id, workspace, record)
            # The ordinary history/detail reader may display unsigned legacy
            # rows, but it must not let them trigger a paper inspection or
            # persistence side effect.  If this ID also has an authenticated
            # raw source, freshen that exact source; otherwise return the
            # display record unchanged.
            trusted_record = _find_trusted_run_record_in_workspace(
                workspace,
                user_id=user_id,
                run_id=run_id,
            )
            if trusted_record is None:
                return workspace, record
            return await self._freshen_found_run_record(user_id, workspace, trusted_record)

        _, workspaces = await self.workspace_service.list_workspaces(
            user_id,
            skip=0,
            limit=1000,
            workspace_type="research",
        )
        for workspace in workspaces:
            record = (
                _find_trusted_run_record_in_workspace(
                    workspace,
                    user_id=user_id,
                    run_id=run_id,
                )
                if require_trusted
                else _find_run_record_in_workspace(workspace, run_id, user_id=user_id)
            )
            if record is None:
                continue
            if not freshen:
                return workspace, record
            if require_trusted:
                return await self._freshen_found_run_record(user_id, workspace, record)
            trusted_record = _find_trusted_run_record_in_workspace(
                workspace,
                user_id=user_id,
                run_id=run_id,
            )
            if trusted_record is None:
                return workspace, record
            return await self._freshen_found_run_record(user_id, workspace, trusted_record)
        return None

    async def _freshen_found_run_record(
        self,
        user_id: str,
        workspace: WorkspaceResponse,
        record: AIStrategyResearchRunRecord,
    ) -> tuple[WorkspaceResponse, AIStrategyResearchRunRecord]:
        # ``record`` was authenticated as its raw stored payload.  Only after
        # that check may time-dependent freshness add an expiry transition or
        # normalize old pipeline presentation fields; the persistence boundary
        # below signs the changed server state again.
        original_record = record
        record = _research_run_record_with_pipeline(record)
        updated = await self._freshen_run_record_with_paper_state(user_id, record)
        if updated == original_record:
            return workspace, original_record
        # Keep the authenticated raw signature on ``updated`` while the
        # persistence helper selects the exact stored mapping to replace.
        # Signing first would replace that source identity with the new
        # signature, making a legitimate expiry refresh look like an
        # untrusted same-run duplicate and leaving the old record on disk.
        refreshed_workspace = await self._persist_freshened_run_records(
            user_id,
            workspace,
            [updated],
            changed_run_ids={updated.run_id},
        )
        # ``_persist_freshened_run_records`` signs the replacement before it
        # writes it. Reproduce that deterministic server signature for the
        # caller so the returned record has the same provenance as storage.
        refreshed = sign_ai_research_run_record(
            updated,
            user_id=user_id,
            workspace_id=str(workspace.id),
        )
        return refreshed_workspace or workspace, refreshed

    async def _paper_trading_target_missing(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
    ) -> tuple[bool, WorkspaceResponse | None]:
        workspace = None
        if record.paper_workspace_id:
            workspace = await self.workspace_service.get_workspace(
                record.paper_workspace_id,
                user_id,
            )
        if workspace is None:
            return True, None
        if not record.paper_unit_id:
            return True, workspace
        unit = _coerce_strategy_unit_response(
            await self.workspace_service.get_unit(workspace.id, record.paper_unit_id, user_id)
        )
        return unit is None, workspace

    def _build_backtest_request(
        self,
        draft: AIStrategyDraft,
        request: AIStrategyResearchRunRequest,
        *,
        user_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        group_name_suffix: str = "",
    ) -> StrategyCopilotBacktestRequest:
        asset_specs = _resolve_research_asset_specs(request)
        effective_start_date = start_date if start_date is not None else request.start_date
        effective_end_date = end_date if end_date is not None else request.end_date
        data_config = {
            **request.data_config,
            "symbol": request.symbol,
            "symbol_name": request.symbol_name or request.symbol,
            "timeframe": request.timeframe,
            "timeframe_n": request.timeframe_n,
        }
        if effective_start_date:
            data_config["start_date"] = effective_start_date
        if effective_end_date:
            data_config["end_date"] = effective_end_date

        unit_settings = {
            "initial_cash": request.initial_cash,
            "commission": request.commission,
            "annual_days": request.annual_days,
            "calc_method": request.calc_method,
            "weight_mode": request.weight_mode,
            **request.unit_settings,
        }
        _apply_backtest_environment_defaults(unit_settings, request, asset_specs)
        if asset_specs:
            _merge_contract_metadata(data_config, asset_specs)
            _merge_contract_metadata(unit_settings, asset_specs)
            _apply_primary_asset_spec_settings(
                unit_settings,
                asset_specs,
                override_commission=not _request_has_explicit_commission(request),
            )

        backtest_request = StrategyCopilotBacktestRequest(
            strategy_draft=draft,
            symbol=request.symbol,
            symbol_name=request.symbol_name or request.symbol,
            timeframe=request.timeframe,
            timeframe_n=request.timeframe_n,
            group_name=_bounded_name(
                f"{request.group_name or draft.execution_plan.group_name or draft.name}{group_name_suffix}",
                200,
            ),
            data_config=data_config,
            unit_settings=unit_settings,
            optimization_config=request.optimization_config,
            parallel=False,
            report_config=None,
        )
        binding_attacher = self._market_data_binding_attacher(user_id=user_id, request=request)
        if binding_attacher is not None:
            backtest_request._market_data_binding_attacher = binding_attacher
        return backtest_request

    @staticmethod
    def _market_data_binding_attacher(
        *,
        user_id: str,
        request: AIStrategyResearchRunRequest,
    ) -> Callable[[str, str], Awaitable[None]] | None:
        """Return the private attachment capability for a sealed request.

        The values originate from the API/task binder and are revalidated by
        the market-data service.  They never become a public workspace API
        parameter; the returned closure is stored only on the in-process
        copilot backtest request.
        """
        config = dict(request.data_config or {})
        if config.get("market_data_binding_required") is not True:
            return None
        binding_id = str(config.get("market_data_binding_id") or "")
        binding_hash = str(config.get("market_data_binding_hash") or "")
        signature = str(config.get("market_data_binding_signature") or "")
        intent_id = str(config.get("market_data_binding_intent_id") or "")

        async def attach(workspace_id: str, unit_id: str) -> None:
            from app.db.database import async_session_maker
            from app.services.market_data.research_binding import (
                build_market_data_research_binding_service,
            )

            async with async_session_maker() as db:
                service = build_market_data_research_binding_service(db)
                await service.attach_runtime_binding_consumer(
                    user_id=user_id,
                    binding_id=binding_id,
                    binding_hash=binding_hash,
                    signature=signature,
                    intent_id=intent_id,
                    workspace_id=workspace_id,
                    unit_id=unit_id,
                )

        return attach

    async def _wait_for_unit_status(
        self,
        workspace_id: str,
        user_id: str,
        unit_id: str,
        *,
        initial_status: UnitStatusResponse | None,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> tuple[UnitStatusResponse | None, str | None]:
        status = _coerce_unit_status(initial_status)
        if status is not None and status.run_status in _TERMINAL_UNIT_STATUSES:
            return status, None if status.run_status == "completed" else status.run_status

        deadline = time.monotonic() + timeout_seconds
        last_status = status
        while time.monotonic() < deadline:
            statuses = await self.workspace_service.get_units_status(workspace_id, user_id)
            matched = _find_unit_status(statuses or [], unit_id)
            if matched is not None:
                last_status = matched
                if matched.run_status in _TERMINAL_UNIT_STATUSES:
                    return (
                        matched,
                        None if matched.run_status == "completed" else matched.run_status,
                    )
            await self.sleep(poll_interval_seconds)

        task_id = last_status.last_task_id if last_status else None
        cancel_requested = False
        if task_id:
            cancel_requested = await self._cancel_backtest_task(task_id, user_id)

        trading_snapshot = dict(last_status.trading_snapshot if last_status else {})
        if task_id:
            trading_snapshot["backtest_timeout_task_id"] = task_id
            trading_snapshot["backtest_timeout_cancel_requested"] = cancel_requested

        timeout_status = UnitStatusResponse(
            id=unit_id,
            run_status="timeout",
            last_task_id=task_id,
            metrics_snapshot=dict(last_status.metrics_snapshot if last_status else {}),
            run_count=last_status.run_count if last_status else 0,
            last_run_time=last_status.last_run_time if last_status else None,
            bar_count=last_status.bar_count if last_status else None,
            trading_instance_id=last_status.trading_instance_id if last_status else None,
            trading_snapshot=trading_snapshot,
            trading_mode=last_status.trading_mode if last_status else "paper",
            lock_trading=last_status.lock_trading if last_status else False,
            lock_running=last_status.lock_running if last_status else False,
        )
        return timeout_status, "Backtest timed out"

    async def _cancel_backtest_task(self, task_id: str, user_id: str) -> bool:
        try:
            service = self.backtest_service
            if service is None:
                from app.services.backtest.service import BacktestService

                service = BacktestService()
            return bool(await service.cancel_task(task_id, user_id))
        except Exception:
            logger.opt(exception=True).warning(
                "Unable to cancel AI research backtest task {}", task_id
            )
            return False

    async def _persist_research_draft_strategy(
        self,
        user_id: str,
        draft: AIStrategyDraft,
        request: AIStrategyResearchRunRequest,
        *,
        run_id: str,
        reason: str = "回测提交失败",
    ) -> StrategyResponse | None:
        try:
            normalized = _normalize_research_draft(draft, request)
            _validate_strategy_code_draft(normalized.code)
            return await self.strategy_service.create_strategy(
                user_id,
                StrategyCreate(
                    name=_bounded_name(f"{normalized.name} - 待回测", 100),
                    description=(
                        f"{normalized.description or ''}\n\n"
                        f"AI投研运行 {run_id} 的{reason}，保存该草案用于继续投研。"
                    ).strip(),
                    code=normalized.code,
                    params=normalized.params,
                    category=normalized.category,
                ),
            )
        except Exception:
            logger.opt(exception=True).warning(
                "Unable to persist AI research draft strategy for run {}", run_id
            )
            return None

    async def _persist_strategy_snapshot_for_promotion(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        strategy: StrategyResponse,
    ) -> StrategyResponse:
        try:
            _validate_strategy_code_draft(strategy.code)
            saved = await self.strategy_service.create_strategy(
                user_id,
                StrategyCreate(
                    name=_bounded_name(f"{strategy.name} - 投研快照", 100),
                    description=(
                        f"{strategy.description or ''}\n\n"
                        f"AI投研运行 {record.run_id} 的历史最佳策略快照，"
                        "已物化保存用于模拟/实盘晋级。"
                    ).strip(),
                    code=strategy.code,
                    params=strategy.params,
                    category=strategy.category,
                ),
                server_owned_ai_research_snapshot_run_id=record.run_id,
            )
        except Exception as exc:
            raise ValueError("Failed to persist strategy snapshot for promotion") from exc
        if saved is None:
            raise ValueError("Failed to persist strategy snapshot for promotion")
        return saved

    async def _persist_cancelled_research_run(
        self,
        *,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        research_workspace: WorkspaceResponse,
        run_id: str,
        started_at: str,
        iterations: list[AIStrategyResearchIteration],
        best_iteration: AIStrategyResearchIteration | None,
        selected_iteration: AIStrategyResearchIteration | None,
        run_failures: list[str],
        draft: AIStrategyDraft | None = None,
    ) -> AIStrategyResearchRunRecord | None:
        if not iterations:
            fallback_strategy = None
            if draft is not None:
                fallback_strategy = await self._persist_research_draft_strategy(
                    user_id,
                    draft,
                    request,
                    run_id=run_id,
                    reason="任务取消时尚未产生回测迭代",
                )
            completed_at = _utc_iso_now()
            failures = [str(item).strip() for item in run_failures if str(item or "").strip()]
            diagnostics = _cancelled_draft_diagnostics(
                failures,
                strategy_saved=fallback_strategy is not None,
            )
            next_actions = [
                "AI投研任务已取消，已保存当前待回测策略草案。"
                if fallback_strategy is not None
                else "AI投研任务已取消，但当前策略草案未能保存。",
                "可从该记录继续投研，重新提交首轮回测并沿用已解析的资产/费用环境。",
            ]
            if failures:
                next_actions.append("取消前最近状态：" + failures[-1])
            pipeline = _pipeline_summary(
                status="cancelled",
                achieved=False,
                iteration_count=0,
                max_iterations=request.max_iterations,
                out_of_sample_validation=request.out_of_sample_validation,
                validation_status=None,
                robustness_validation=request.robustness_validation,
                robustness_status=None,
                paper_trading_started=False,
                paper_trading_error=None,
                paper_review_status=None,
                paper_review_ready_for_live=False,
                workflow_mode=request.workflow_mode,
                workflow_steps=request.workflow_steps,
            )
            response = AIStrategyResearchRunResponse(
                run_id=run_id,
                status="cancelled",
                achieved=False,
                target_sharpe=request.target_sharpe,
                started_at=started_at,
                completed_at=completed_at,
                best_iteration=None,
                best_quality_score=0.0,
                best_quality_gate_evaluations=[],
                best_diagnostics=diagnostics,
                best_metrics={},
                research_workspace=research_workspace,
                mandate_id=request.mandate_id,
                iterations=[],
                best_strategy=fallback_strategy,
                paper_trading=None,
                paper_monitoring_plan=[],
                pipeline=pipeline,
                promotion_audit=[],
                next_actions=next_actions,
                message="AI research task cancelled before any backtest iteration completed",
            )
            await self._record_pipeline_event(
                user_id=user_id,
                run_id=run_id,
                request=request,
                workspace_id=research_workspace.id,
                stage="cancelled",
                status="cancelled",
                summary="AI投研任务在首轮回测前取消。",
                output_payload={"next_actions": next_actions},
                error=failures[-1] if failures else None,
            )
            run_record = _build_research_run_record(
                run_id=run_id,
                request=request,
                response=response,
                started_at=started_at,
                completed_at=completed_at,
            )
            run_record = sign_ai_research_run_record(
                run_record,
                user_id=user_id,
                workspace_id=str(research_workspace.id),
            )
            await self._persist_research_run_record(user_id, research_workspace, run_record)
            return run_record

        result_iteration = selected_iteration or best_iteration or iterations[-1]
        best_metrics = dict(result_iteration.metrics)
        completed_at = _utc_iso_now()
        next_actions = [
            "AI投研任务已取消，已保存取消前完成的回测迭代。",
            "可从该记录继续投研，沿用当前最佳策略和已解析的资产/费用环境。",
        ]
        failures = [str(item).strip() for item in run_failures if str(item or "").strip()]
        if failures:
            next_actions.append("取消前最近一次失败：" + failures[-1])
        pipeline = _pipeline_summary(
            status="cancelled",
            achieved=False,
            iteration_count=len(iterations),
            max_iterations=request.max_iterations,
            out_of_sample_validation=request.out_of_sample_validation,
            validation_status=result_iteration.validation_status,
            robustness_validation=request.robustness_validation,
            robustness_status=result_iteration.robustness_status,
            paper_trading_started=False,
            paper_trading_error=None,
            paper_review_status=None,
            paper_review_ready_for_live=False,
            workflow_mode=request.workflow_mode,
            workflow_steps=request.workflow_steps,
        )
        response = AIStrategyResearchRunResponse(
            run_id=run_id,
            status="cancelled",
            achieved=False,
            target_sharpe=request.target_sharpe,
            started_at=started_at,
            completed_at=completed_at,
            best_iteration=result_iteration.iteration,
            best_quality_score=_promotion_quality_score(result_iteration),
            best_quality_gate_evaluations=_promotion_gate_evaluations(result_iteration),
            best_diagnostics=result_iteration.diagnostics,
            best_metrics=best_metrics,
            research_workspace=research_workspace,
            mandate_id=request.mandate_id,
            iterations=iterations,
            best_strategy=result_iteration.strategy,
            paper_trading=None,
            paper_monitoring_plan=[],
            pipeline=pipeline,
            promotion_audit=[],
            next_actions=next_actions,
            message="AI research task cancelled after saving completed iterations",
        )
        await self._record_pipeline_event(
            user_id=user_id,
            run_id=run_id,
            request=request,
            workspace_id=research_workspace.id,
            stage="cancelled",
            status="cancelled",
            summary="AI投研任务取消，已保存已完成迭代。",
            output_payload={"next_actions": next_actions},
            metrics=best_metrics,
            error=failures[-1] if failures else None,
        )
        run_record = _build_research_run_record(
            run_id=run_id,
            request=request,
            response=response,
            started_at=started_at,
            completed_at=completed_at,
        )
        run_record = sign_ai_research_run_record(
            run_record,
            user_id=user_id,
            workspace_id=str(research_workspace.id),
        )
        await self._persist_research_run_record(user_id, research_workspace, run_record)
        return run_record

    async def _ensure_valid_draft_before_backtest(
        self,
        draft: AIStrategyDraft,
        *,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        iteration: int,
        iteration_count: int,
        pending_improvement_notes: list[str],
        pending_generation_metadata: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
    ) -> tuple[AIStrategyDraft, list[str], dict[str, Any]]:
        notes = list(pending_improvement_notes)
        generation_metadata = dict(pending_generation_metadata or {})
        current_draft = draft
        last_error = ""

        for attempt in range(_MAX_CODE_REPAIR_ATTEMPTS + 1):
            try:
                _validate_strategy_code_draft(current_draft.code)
                return current_draft, notes, generation_metadata
            except ValueError as exc:
                last_error = str(exc)
                if attempt >= _MAX_CODE_REPAIR_ATTEMPTS:
                    fallback = _normalize_research_draft(
                        build_ai_strategy_draft(request.prompt),
                        request,
                    )
                    _validate_strategy_code_draft(fallback.code)
                    return (
                        fallback,
                        [
                            *notes,
                            f"策略代码连续校验失败，已使用本地可运行草案继续投研：{last_error}",
                        ],
                        {
                            "source": "local_code_repair_fallback",
                            "provider": "local",
                            "fallback_reason": last_error,
                        },
                    )

                failure = f"Strategy code validation failed before backtest: {last_error}"
                await _emit_research_progress(
                    progress_callback,
                    {
                        "current_stage": "repairing_code",
                        "progress": min(
                            _research_loop_progress(iteration - 1, request.max_iterations) + 2.0,
                            80.0,
                        ),
                        "current_iteration": iteration,
                        "iteration_count": iteration_count,
                        "max_iterations": request.max_iterations,
                        "message": (
                            f"Repairing generated strategy code before iteration {iteration}"
                        ),
                    },
                )
                improvement = await self._improve_draft(
                    current_draft,
                    iteration=iteration - 1,
                    metrics={
                        "code_validation_failed": True,
                        "repair_attempt": attempt + 1,
                    },
                    target_sharpe=request.target_sharpe,
                    quality_gate_failures=[failure],
                    user_id=user_id,
                    request=request,
                )
                current_draft = _normalize_research_draft(improvement.draft, request)
                notes = [
                    *notes,
                    f"第 {iteration} 轮回测前策略代码校验失败，已自动修复：{last_error}",
                    *improvement.notes,
                ]
                generation_metadata = _strategy_generation_metadata(
                    improvement.metadata,
                    phase="code_repair",
                    iteration=iteration,
                )

        raise ValueError(
            f"Generated strategy code validation failed before iteration {iteration}: {last_error}"
        )

    async def _improve_draft(
        self,
        draft: AIStrategyDraft,
        *,
        iteration: int,
        metrics: dict[str, Any],
        target_sharpe: float,
        quality_gate_failures: list[str] | None,
        user_id: str,
        request: AIStrategyResearchRunRequest,
    ) -> StrategyImprovement:
        try:
            return await self.improver.improve(
                draft,
                iteration=iteration,
                metrics=metrics,
                target_sharpe=target_sharpe,
                quality_gate_failures=quality_gate_failures,
                user_id=user_id,
                request=request,
            )
        except Exception as exc:
            fallback = await LocalStrategyImprover().improve(
                draft,
                iteration=iteration,
                metrics=metrics,
                target_sharpe=target_sharpe,
                quality_gate_failures=quality_gate_failures,
                user_id=user_id,
                request=request,
            )
            return StrategyImprovement(
                draft=fallback.draft,
                notes=[
                    f"AI投研改稿失败，已使用本地规则回退：{exc}",
                    *fallback.notes,
                ],
                metadata={
                    **dict(fallback.metadata or {}),
                    "source": "local_fallback",
                    "fallback_reason": str(exc),
                },
            )

    async def _start_paper_trading(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        best_iteration: AIStrategyResearchIteration,
        *,
        run_id: str,
        research_workspace_id: str,
    ) -> AIStrategyPaperTradingStart:
        workspace = None
        if request.trading_workspace_id:
            workspace = await self.workspace_service.get_workspace(
                request.trading_workspace_id, user_id
            )
            if workspace is None:
                raise ValueError("Trading workspace not found")
        if workspace is None:
            workspace = await self.workspace_service.create_workspace(
                user_id,
                WorkspaceCreate(
                    name=request.paper_workspace_name
                    or _paper_workspace_name(request, best_iteration),
                    description="AI research loop paper trading workspace",
                    workspace_type="trading",
                ),
            )

        handoff = _build_paper_trading_handoff(
            run_id=run_id,
            research_workspace_id=research_workspace_id,
            request=request,
            best_iteration=best_iteration,
            promoted_at=_utc_iso_now(),
        )
        handoff["paper_workspace_name"] = workspace.name
        handoff_asset_specs = {
            str(symbol): dict(spec)
            for symbol, spec in dict(handoff.get("asset_specs") or {}).items()
            if isinstance(spec, dict) and spec
        }
        unit_data_config = {
            **best_iteration.unit.data_config,
            **dict(request.data_config or {}),
            "ai_research_run_id": run_id,
            "ai_research_workspace_id": research_workspace_id,
        }
        unit_settings = {
            **best_iteration.unit.unit_settings,
            **dict(request.unit_settings or {}),
            "ai_research_handoff": handoff,
        }
        unit_params = {
            **dict(best_iteration.unit.params or {}),
            "ai_research_run_id": run_id,
            "ai_research_workspace_id": research_workspace_id,
        }
        if handoff_asset_specs:
            _merge_contract_metadata(unit_data_config, handoff_asset_specs)
            _merge_contract_metadata(unit_settings, handoff_asset_specs)
            _merge_contract_metadata(unit_params, handoff_asset_specs)
        unit_payload = StrategyUnitCreate(
            group_name=request.group_name
            or best_iteration.unit.group_name
            or best_iteration.strategy.name,
            strategy_id=best_iteration.strategy.id,
            strategy_name=best_iteration.strategy.name,
            symbol=request.symbol,
            symbol_name=request.symbol_name or request.symbol,
            timeframe=request.timeframe,
            timeframe_n=request.timeframe_n,
            category=best_iteration.strategy.category,
            data_config=unit_data_config,
            unit_settings=unit_settings,
            params=unit_params,
            optimization_config=best_iteration.unit.optimization_config,
            trading_mode="paper",
            gateway_config=request.gateway_config or best_iteration.unit.gateway_config,
            lock_trading=False,
            lock_running=False,
        )
        created_unit = await self.workspace_service.create_unit(
            workspace.id,
            user_id,
            unit_payload,
            allow_server_owned_ai_research_state=True,
        )
        if created_unit is None:
            raise ValueError("Failed to create paper trading unit")
        unit = StrategyUnitResponse.model_validate(created_unit)

        # Seal the paper target before starting its runtime.  The public unit
        # API cannot later strip this marker and substitute another strategy,
        # gateway, instance ID, or fabricated snapshot for paper review.
        handoff = {
            **handoff,
            "paper_workspace_id": workspace.id,
            "paper_workspace_name": workspace.name,
            "paper_unit_id": unit.id,
            "paper_task_id": None,
            "paper_run_status": None,
            "paper_started_at": None,
        }
        runtime_anchor = issue_ai_research_paper_runtime_anchor(
            user_id=user_id,
            research_workspace_id=research_workspace_id,
            paper_workspace_id=workspace.id,
            paper_unit_id=unit.id,
            run_id=run_id,
            unit=unit,
            workspace_settings=workspace.settings,
            # The isolated unit directory is created by the following start
            # flow. It receives a materialized-file digest only after the
            # server verifies the completed runtime copy.
            include_runtime_snapshot=False,
        )
        if runtime_anchor is None:
            raise ValueError("AI research paper runtime provenance signing is unavailable")
        unit = unit.model_copy(
            update={
                "data_config": {
                    **unit.data_config,
                    "ai_research_run_id": run_id,
                    "ai_research_workspace_id": research_workspace_id,
                },
                "unit_settings": {
                    **unit.unit_settings,
                    "ai_research_handoff": handoff,
                    "ai_research_paper_runtime_anchor": runtime_anchor,
                },
                "params": {
                    **dict(unit.params or {}),
                    "ai_research_run_id": run_id,
                    "ai_research_workspace_id": research_workspace_id,
                },
            }
        )
        persisted_unit = await self.workspace_service.update_unit(
            workspace.id,
            unit.id,
            user_id,
            StrategyUnitUpdate(
                data_config=unit.data_config,
                unit_settings=unit.unit_settings,
                params=unit.params,
            ),
            allow_server_owned_ai_research_state=True,
        )
        if persisted_unit is not None:
            unit = StrategyUnitResponse.model_validate(persisted_unit)

        run_result = None
        run_results = await self.workspace_service.run_units(
            workspace.id, user_id, [unit.id], parallel=False
        )
        if run_results:
            run_result = StrategyCopilotRunResult.model_validate(run_results[0])

        # ``run_units`` materializes the isolated paper runtime in a separate
        # service session and replaces the initial expected-only anchor with a
        # signed snapshot digest. Reload before persisting the handoff task
        # metadata below; writing the stale response object here would erase
        # that digest and turn an otherwise valid paper runtime into an
        # untrusted legacy source on its next review or direct start.
        started_unit = await self.workspace_service.get_unit(workspace.id, unit.id, user_id)
        if started_unit is not None:
            unit = StrategyUnitResponse.model_validate(started_unit)

        handoff = {
            **handoff,
            "paper_workspace_id": workspace.id,
            "paper_workspace_name": workspace.name,
            "paper_unit_id": unit.id,
            "paper_task_id": run_result.task_id if run_result else None,
            "paper_run_status": run_result.status if run_result else None,
            "paper_started_at": _utc_iso_now() if _paper_trading_run_started(run_result) else None,
        }
        unit = unit.model_copy(
            update={
                "data_config": {
                    **unit.data_config,
                    "ai_research_run_id": run_id,
                    "ai_research_workspace_id": research_workspace_id,
                },
                "unit_settings": {
                    **unit.unit_settings,
                    "ai_research_handoff": handoff,
                },
                "params": {
                    **dict(unit.params or {}),
                    "ai_research_run_id": run_id,
                    "ai_research_workspace_id": research_workspace_id,
                    "ai_research_paper_task_id": run_result.task_id if run_result else None,
                    "ai_research_paper_run_status": run_result.status if run_result else None,
                },
            }
        )
        persisted_unit = await self.workspace_service.update_unit(
            workspace.id,
            unit.id,
            user_id,
            StrategyUnitUpdate(
                data_config=unit.data_config,
                unit_settings=unit.unit_settings,
                params=unit.params,
            ),
            allow_server_owned_ai_research_state=True,
            # This write records server-only handoff/task bookkeeping after
            # the process has begun. It must not rematerialize the isolated
            # runtime directory between the signed snapshot and later review.
            sync_runtime=False,
        )
        if persisted_unit is not None:
            unit = StrategyUnitResponse.model_validate(persisted_unit)
        workspace = await self._persist_paper_trading_handoff(user_id, workspace, handoff)

        return AIStrategyPaperTradingStart(
            workspace=workspace,
            unit=unit,
            run_result=run_result,
            started=_paper_trading_run_started(run_result),
            handoff=handoff,
        )

    async def _persist_paper_trading_handoff(
        self,
        user_id: str,
        workspace: WorkspaceResponse,
        handoff: dict[str, Any],
    ) -> WorkspaceResponse:
        settings = dict(workspace.settings or {})
        ai_handoff = dict(settings.get("ai_research_handoff") or {})
        handoff_payload = dict(handoff)

        existing: list[dict[str, Any]] = []
        raw_handoffs = ai_handoff.get("handoffs")
        if isinstance(raw_handoffs, list):
            existing = [dict(item) for item in raw_handoffs if isinstance(item, dict)]
        ai_handoff["last_handoff"] = handoff_payload
        ai_handoff["handoffs"] = [
            handoff_payload,
            *[
                item
                for item in existing
                if str(item.get("run_id") or "") != str(handoff_payload.get("run_id") or "")
            ],
        ][:20]

        updated = await self.workspace_service.update_workspace(
            workspace.id,
            user_id,
            WorkspaceUpdate(settings={"ai_research_handoff": ai_handoff}),
        )
        if updated is not None:
            return updated

        settings["ai_research_handoff"] = ai_handoff
        return workspace.model_copy(update={"settings": settings})

    async def _persist_research_run_record(
        self,
        user_id: str,
        research_workspace: WorkspaceResponse,
        run_record: AIStrategyResearchRunRecord,
    ) -> WorkspaceResponse:
        run_record = _research_run_record_with_pipeline(run_record)
        run_record = sign_ai_research_run_record(
            run_record,
            user_id=user_id,
            workspace_id=str(research_workspace.id),
        )
        settings = dict(research_workspace.settings or {})
        ai_research = dict(settings.get("ai_research") or {})
        record_payload = run_record.model_dump(mode="json")

        existing_runs: list[dict[str, Any]] = []
        raw_runs = ai_research.get("runs")
        if isinstance(raw_runs, list):
            existing_runs = [dict(item) for item in raw_runs if isinstance(item, dict)]
        runs = [
            record_payload,
            *[item for item in existing_runs if str(item.get("run_id") or "") != run_record.run_id],
        ][:20]
        ai_research["last_run"] = record_payload
        ai_research["runs"] = runs

        updated_workspace = await self.workspace_service.update_workspace(
            research_workspace.id,
            user_id,
            WorkspaceUpdate(settings={"ai_research": ai_research}),
        )
        if updated_workspace is not None:
            return updated_workspace

        settings["ai_research"] = ai_research
        return research_workspace.model_copy(update={"settings": settings})

    async def _persist_historic_live_handoff_stop_record(
        self,
        user_id: str,
        research_workspace: WorkspaceResponse,
        run_record: AIStrategyResearchRunRecord,
        *,
        source_signature: str,
    ) -> tuple[WorkspaceResponse, AIStrategyResearchRunRecord]:
        """Replace one verified history row without changing another ``last_run``.

        This writer is intentionally private to controlled emergency stop.
        It is the only case where a signed historical record may transition
        state after a later run became canonical.  Replacement binds the raw
        source signature and re-verifies that raw mapping before writing, so
        a caller cannot turn a same-id forged history entry into a signed
        record.  ``last_run`` is left byte-for-byte intact for the later run.
        """
        expected_signature = str(source_signature or "").strip()
        workspace_id = str(research_workspace.id or "").strip()
        if not expected_signature or not workspace_id:
            raise ValueError("AI_RESEARCH_LIVE_HANDOFF_PROVENANCE_INVALID")
        signed_record = sign_ai_research_run_record(
            _research_run_record_with_pipeline(run_record),
            user_id=user_id,
            workspace_id=workspace_id,
        )
        replacement_signature = str(signed_record.server_provenance_signature or "").strip()
        if not replacement_signature or not verify_ai_research_run_record(
            signed_record,
            user_id=user_id,
            workspace_id=workspace_id,
        ):
            raise ValueError("AI_RESEARCH_LIVE_HANDOFF_PROVENANCE_INVALID")

        settings = dict(research_workspace.settings or {})
        ai_research = dict(settings.get("ai_research") or {})
        raw_runs = ai_research.get("runs")
        if not isinstance(raw_runs, list):
            raise ValueError("AI_RESEARCH_LIVE_HANDOFF_PROVENANCE_INVALID")
        replacement = signed_record.model_dump(mode="json")
        replaced = False
        next_runs: list[Any] = []
        for raw in raw_runs:
            if not isinstance(raw, dict):
                next_runs.append(raw)
                continue
            raw_signature = str(raw.get("server_provenance_signature") or "").strip()
            same_source = (
                str(raw.get("run_id") or "").strip() == str(run_record.run_id or "").strip()
                and raw_signature == expected_signature
                and verify_ai_research_run_record(
                    raw,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
            )
            if same_source:
                next_runs.append(replacement)
                replaced = True
            else:
                next_runs.append(raw)
        if not replaced:
            raise ValueError("AI_RESEARCH_LIVE_HANDOFF_PROVENANCE_INVALID")

        ai_research["runs"] = next_runs[:20]
        # Do not touch ``last_run``. It belongs to the newer B revision that
        # displaced this historic A handoff and remains its own canonical
        # continuation/approval source.
        settings["ai_research"] = ai_research
        updated_workspace = await self.workspace_service.update_workspace(
            research_workspace.id,
            user_id,
            WorkspaceUpdate(settings={"ai_research": ai_research}),
        )
        if updated_workspace is not None:
            return updated_workspace, signed_record
        return research_workspace.model_copy(update={"settings": settings}), signed_record

    async def _persist_freshened_run_records(
        self,
        user_id: str,
        workspace: WorkspaceResponse,
        records: list[AIStrategyResearchRunRecord],
        *,
        changed_run_ids: set[str] | None = None,
    ) -> WorkspaceResponse | None:
        changed_run_ids = set(changed_run_ids or set())
        trusted_run_signatures = _trusted_run_record_signatures_from_workspace(
            workspace,
            user_id=user_id,
        )
        replacements: dict[tuple[str, str], dict[str, Any]] = {}
        for record in records:
            run_id = str(record.run_id or "").strip()
            source_signature = str(record.server_provenance_signature or "").strip()
            if (
                not run_id
                or source_signature not in trusted_run_signatures.get(run_id, set())
                or not (
                    run_id in changed_run_ids or _freshened_run_record_needs_persist(record)
                )
            ):
                continue
            replacements[(run_id, source_signature)] = sign_ai_research_run_record(
                record,
                user_id=user_id,
                workspace_id=str(workspace.id),
            ).model_dump(mode="json")
        if not replacements:
            return None

        settings = dict(workspace.settings or {})
        ai_research = dict(settings.get("ai_research") or {})
        changed = False

        raw_runs = ai_research.get("runs")
        if isinstance(raw_runs, list):
            next_runs: list[Any] = []
            for item in raw_runs:
                if isinstance(item, dict):
                    run_id = str(item.get("run_id") or "")
                    source_signature = str(item.get("server_provenance_signature") or "").strip()
                    replacement = replacements.get((run_id, source_signature))
                    if (
                        replacement is not None
                        and verify_ai_research_run_record(
                            item,
                            user_id=user_id,
                            workspace_id=str(workspace.id),
                        )
                        and _raw_run_record_needs_freshness_persist(
                        item,
                        force=run_id in changed_run_ids,
                        )
                    ):
                        next_runs.append(dict(replacement))
                        changed = True
                        continue
                next_runs.append(item)
            if changed:
                ai_research["runs"] = next_runs

        last_run = ai_research.get("last_run")
        if isinstance(last_run, dict):
            run_id = str(last_run.get("run_id") or "")
            source_signature = str(last_run.get("server_provenance_signature") or "").strip()
            replacement = replacements.get((run_id, source_signature))
            if (
                replacement is not None
                and verify_ai_research_run_record(
                    last_run,
                    user_id=user_id,
                    workspace_id=str(workspace.id),
                )
                and _raw_run_record_needs_freshness_persist(
                    last_run,
                    force=run_id in changed_run_ids,
                )
            ):
                ai_research["last_run"] = dict(replacement)
                changed = True

        if not changed:
            return None

        updated_workspace = await self.workspace_service.update_workspace(
            workspace.id,
            user_id,
            WorkspaceUpdate(settings={"ai_research": ai_research}),
        )
        if updated_workspace is not None:
            return updated_workspace

        settings["ai_research"] = ai_research
        return workspace.model_copy(update={"settings": settings})

    async def _mark_run_record_paper_started(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        paper_trading: AIStrategyPaperTradingStart,
    ) -> AIStrategyResearchRunRecord | None:
        workspace = await self.workspace_service.get_workspace(
            record.research_workspace_id, user_id
        )
        if workspace is None:
            return None
        updated_record = record.model_copy(
            update={
                "paper_workspace_id": paper_trading.workspace.id,
                "paper_workspace_name": paper_trading.workspace.name,
                "paper_unit_id": paper_trading.unit.id,
                "paper_trading_started": paper_trading.started,
                "paper_monitoring_plan": _paper_monitoring_plan_from_handoff(paper_trading.handoff),
                "paper_handoff": _research_record_handoff_payload(paper_trading.handoff),
                "live_readiness_checklist": [],
                "live_readiness_expires_at": None,
                "live_handoff": None,
                "live_handoff_approval": None,
                "live_workspace_id": None,
                "live_workspace_name": None,
                "live_unit_id": None,
                "live_trading_prepared": False,
                "live_trading_prepared_at": None,
                "next_actions": [
                    "已从历史投研结果启动模拟交易，下一步跟踪模拟账户成交、持仓和风控指标。",
                    "保留研究工作区记录，用于后续继续投研或样本外验证。",
                ],
            }
        )
        updated_record = _apply_initial_paper_review_to_run_record(
            updated_record,
            paper_trading=paper_trading,
            user_id=user_id,
        )
        updated_record = _apply_initial_live_handoff_to_run_record(updated_record)
        await self._persist_research_run_record(user_id, workspace, updated_record)
        return updated_record

    async def _mark_run_record_paper_start_failed(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        error: str,
        *,
        paper_trading: AIStrategyPaperTradingStart | None = None,
    ) -> AIStrategyResearchRunRecord | None:
        workspace = await self.workspace_service.get_workspace(
            record.research_workspace_id, user_id
        )
        if workspace is None:
            return None
        paper_trading_error = str(error or "Paper trading start failed").strip()
        updated_record = _research_run_record_with_promotion_audit(
            record.model_copy(
                update={
                    "paper_trading_started": False,
                    "paper_review_status": None,
                    "paper_review_ready_for_live": False,
                    "paper_reviewed_at": None,
                    "paper_review_evaluations": [],
                    "paper_review_next_actions": [],
                    "live_readiness_checklist": [],
                    "live_readiness_expires_at": None,
                    "live_handoff": None,
                    "live_handoff_approval": None,
                    "live_workspace_id": None,
                    "live_workspace_name": None,
                    "live_unit_id": None,
                    "live_trading_prepared": False,
                    "live_trading_prepared_at": None,
                    "paper_workspace_id": paper_trading.workspace.id if paper_trading else None,
                    "paper_workspace_name": paper_trading.workspace.name if paper_trading else None,
                    "paper_unit_id": paper_trading.unit.id if paper_trading else None,
                    "paper_monitoring_plan": _paper_monitoring_plan_from_handoff(
                        paper_trading.handoff if paper_trading else None
                    ),
                    "paper_handoff": _research_record_handoff_payload(
                        paper_trading.handoff if paper_trading else None
                    ),
                    "pipeline": _pipeline_summary(
                        status=record.status,
                        achieved=record.achieved,
                        iteration_count=record.iteration_count,
                        max_iterations=record.max_iterations,
                        out_of_sample_validation=bool(
                            (record.quality_gates or {}).get("out_of_sample_validation", False)
                        ),
                        validation_status=_record_best_validation_status(record),
                        robustness_validation=bool(
                            (record.quality_gates or {}).get("robustness_validation", False)
                        ),
                        robustness_status=_record_best_robustness_status(record),
                        paper_trading_started=False,
                        paper_trading_error=paper_trading_error,
                        paper_review_status=None,
                        paper_review_ready_for_live=False,
                        workflow_mode=record.workflow_mode,
                        workflow_steps=record.workflow_steps,
                    ),
                    "next_actions": [
                        f"模拟交易启动错误：{paper_trading_error}",
                        "检查交易工作区、网关配置、策略脚本依赖和资产参数后可重试模拟。",
                        "如果启动问题来自策略脚本或交易环境假设，可从该记录继续投研。",
                    ],
                }
            )
        )
        await self._persist_research_run_record(user_id, workspace, updated_record)
        return updated_record

    async def _mark_run_record_paper_reviewed(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        review: AIStrategyPaperTradingReview,
    ) -> AIStrategyResearchRunRecord | None:
        workspace = await self.workspace_service.get_workspace(
            record.research_workspace_id, user_id
        )
        if workspace is None:
            return None
        review_pipeline = dict(review.pipeline or {})
        review_observation = _dict_payload(review_pipeline.get("paper_runtime_observation"))
        runtime_observation = _paper_runtime_observation_payload(
            str(review_observation.get("instance_id") or ""),
            str(review_observation.get("started_at") or ""),
            str(review_observation.get("launch_id") or ""),
        )
        observation_unchanged = (
            _paper_runtime_observation_from_handoff(record.paper_handoff) == runtime_observation
        )
        paper_handoff = _research_record_handoff_payload(
            _paper_handoff_with_review_lock(
                _paper_handoff_with_live_readiness(
                    _paper_handoff_with_runtime_observation(
                        record.paper_handoff,
                        runtime_observation,
                    ),
                    review.live_readiness_checklist,
                    expires_at=review.live_readiness_expires_at,
                ),
                _paper_review_lock_from_pipeline(review.pipeline),
            )
        )
        updated_record = _research_run_record_with_promotion_audit(
            record.model_copy(
                update={
                    "paper_review_status": review.status,
                    "paper_review_ready_for_live": review.ready_for_live,
                    "paper_reviewed_at": review.reviewed_at,
                    "paper_review_evaluations": [
                        item.model_dump(mode="json") for item in review.evaluations
                    ],
                    "paper_review_next_actions": review.next_actions,
                    "live_readiness_checklist": review.live_readiness_checklist,
                    "live_readiness_expires_at": review.live_readiness_expires_at,
                    "paper_handoff": paper_handoff,
                    "pipeline": review.pipeline,
                    "next_actions": review.next_actions,
                    "live_handoff": (
                        record.live_handoff
                        if review.ready_for_live and observation_unchanged
                        else None
                    ),
                    "live_handoff_approval": (
                        record.live_handoff_approval
                        if review.ready_for_live and observation_unchanged
                        else None
                    ),
                }
            )
        )
        if review.ready_for_live and review.status == "ready_for_live_candidate":
            package = _build_live_handoff_package(updated_record)
            updated_record = _run_record_with_live_handoff(updated_record, package)
        await self._persist_research_run_record(user_id, workspace, updated_record)
        return updated_record

    async def _mark_run_record_live_handoff_built(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        package: AIStrategyLiveHandoffPackage,
    ) -> WorkspaceResponse | None:
        workspace = await self.workspace_service.get_workspace(
            record.research_workspace_id, user_id
        )
        if workspace is None:
            return None
        updated_record = _run_record_with_live_handoff(record, package)
        return await self._persist_research_run_record(user_id, workspace, updated_record)

    async def _mark_run_record_live_handoff_approval(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        package: AIStrategyLiveHandoffPackage,
        approval: AIStrategyLiveHandoffApprovalRecord,
    ) -> WorkspaceResponse | None:
        workspace = await self.workspace_service.get_workspace(
            record.research_workspace_id, user_id
        )
        if workspace is None:
            return None
        updated_record = _run_record_with_live_handoff_approval(
            _run_record_with_live_handoff(record, package),
            approval,
        )
        return await self._persist_research_run_record(user_id, workspace, updated_record)

    async def _mark_run_record_live_trading_prepared(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        package: AIStrategyLiveHandoffPackage,
        *,
        workspace: WorkspaceResponse,
        unit: StrategyUnitResponse,
        handoff: dict[str, Any],
    ) -> WorkspaceResponse | None:
        research_workspace = await self.workspace_service.get_workspace(
            record.research_workspace_id,
            user_id,
        )
        if research_workspace is None:
            return None
        prepared_at = str(handoff.get("live_trading_prepared_at") or _utc_iso_now())
        pipeline = _pipeline_with_live_trading_prepared(
            package.pipeline or record.pipeline,
            workspace=workspace,
            unit=unit,
            prepared_at=prepared_at,
        )
        next_actions = _live_trading_prepare_next_actions(unit)
        package_handoff = dict(package.handoff or {})
        package_handoff["live_trading_prepare"] = dict(handoff)
        prepared_package = package.model_copy(
            update={
                "handoff": _redact_sensitive_handoff(package_handoff),
                "pipeline": pipeline,
                "next_actions": next_actions,
            }
        )
        updated_record = _research_run_record_with_promotion_audit(
            record.model_copy(
                update={
                    "live_handoff": prepared_package,
                    "live_workspace_id": workspace.id,
                    "live_workspace_name": workspace.name,
                    "live_unit_id": unit.id,
                    "live_trading_prepared": True,
                    "live_trading_prepared_at": prepared_at,
                    "pipeline": pipeline,
                    "next_actions": next_actions,
                }
            )
        )
        return await self._persist_research_run_record(user_id, research_workspace, updated_record)


for _helper_name in _research_helpers.__all__:
    globals()[_helper_name] = getattr(_research_helpers, _helper_name)
del _helper_name
