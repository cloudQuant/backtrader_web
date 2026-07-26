"""Shared imports, constants, and dependencies for research workflow helpers."""

# ruff: noqa: F401

from __future__ import annotations

import ast
import asyncio
import io
import json
import re
import time
import tokenize
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings, production_security_mode
from app.schemas.ai_strategy_research import (
    AI_STRATEGY_RESEARCH_DEFAULT_WORKFLOW_STEPS,
    AI_STRATEGY_RESEARCH_WORKFLOW_STEP_LABELS,
    AIStrategyLiveHandoffApprovalRecord,
    AIStrategyLiveHandoffApprovalRequest,
    AIStrategyLiveHandoffPackage,
    AIStrategyLiveTradingPrepare,
    AIStrategyLiveTradingPrepareRequest,
    AIStrategyPaperTradingReview,
    AIStrategyPaperTradingRuleEvaluation,
    AIStrategyPaperTradingStart,
    AIStrategyPaperTradingStartRequest,
    AIStrategyResearchIteration,
    AIStrategyResearchRunListResponse,
    AIStrategyResearchRunRecord,
    AIStrategyResearchRunRequest,
    AIStrategyResearchRunResponse,
    AIStrategyResearchTaskResponse,
)
from app.schemas.market_data_trust import RobustnessValidationRequest
from app.schemas.strategy import (
    AIStrategyBacktestSpec,
    AIStrategyDataSourceSpec,
    AIStrategyDraft,
    AIStrategyExecutionPlan,
    ParamSpec,
    StrategyCopilotBacktestRequest,
    StrategyCopilotDraftRequest,
    StrategyCopilotRunResult,
    StrategyCreate,
    StrategyResponse,
)
from app.schemas.workspace import (
    StrategyUnitCreate,
    StrategyUnitResponse,
    StrategyUnitUpdate,
    UnitStatusResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services.ai_router.preferences import (
    AIModelPreferenceService,
    ResolvedAIModelPreference,
)
from app.services.ai_router.router import AIChatRouter, get_ai_chat_router
from app.services.ai_strategy_research_version_service import AIStrategyResearchVersionService
from app.services.asset_info.gateway_specs import resolve_asset_specs
from app.services.investment_mandate_service import InvestmentMandateService
from app.services.research_pipeline_event_service import ResearchPipelineEventService
from app.services.risk_gate_service import RiskGateService
from app.services.robustness_validation_service import get_robustness_validation_service
from app.services.strategy.ai_draft import build_ai_strategy_draft
from app.services.strategy.core import StrategyService
from app.services.strategy.inference import render_param_default
from app.services.workspace_service import WorkspaceService
from app.utils.sandbox import SandboxPreflightError, StrategySandbox

from .types import OutOfSampleWindow, StrategyImprovement

_TERMINAL_UNIT_STATUSES = {"completed", "failed", "cancelled", "timeout"}
_MAX_CODE_REPAIR_ATTEMPTS = 2
_PAPER_TRADING_STARTED_STATUSES = {"running", "submitted", "queued", "pending", "completed"}
_LIVE_READINESS_VALID_DAYS = 7
_SENSITIVE_HANDOFF_KEYS = (
    "api_key",
    "apikey",
    "access_key",
    "password",
    "passphrase",
    "auth_code",
    "credential",
    "secret",
    "secret_key",
    "token",
    "authorization",
)
_SENSITIVE_OMITTED = object()

__all__ = tuple(name for name in globals() if not name.startswith("__"))
