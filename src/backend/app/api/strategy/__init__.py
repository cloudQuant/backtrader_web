from fastapi import APIRouter

from app.api.strategy.base import (
    add_strategy_copilot_draft_to_workspace,
    backtest_strategy_copilot_draft,
    create_strategy,
    delete_strategy,
    generate_strategy_copilot_draft,
    get_ai_strategy_research_service,
    get_strategy,
    get_strategy_service,
    get_template_config,
    get_template_detail,
    get_template_readme,
    get_templates,
    list_strategies,
    run_ai_strategy_research_loop,
    update_strategy,
)
from app.api.strategy.base import (
    router as base_router,
)
from app.api.strategy.explainer import router as explainer_router
from app.api.strategy.score import router as score_router

router = APIRouter()
router.include_router(base_router)
router.include_router(score_router)
router.include_router(explainer_router)

__all__ = [
    "add_strategy_copilot_draft_to_workspace",
    "create_strategy",
    "delete_strategy",
    "backtest_strategy_copilot_draft",
    "generate_strategy_copilot_draft",
    "get_ai_strategy_research_service",
    "get_strategy",
    "get_strategy_service",
    "get_template_config",
    "get_template_detail",
    "get_template_readme",
    "get_templates",
    "list_strategies",
    "router",
    "run_ai_strategy_research_loop",
    "update_strategy",
]
