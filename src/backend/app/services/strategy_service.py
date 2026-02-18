"""Strategy service (CRUD + template/config loading)."""
import glob
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

import yaml

from app.models.strategy import Strategy
from app.schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    StrategyListResponse,
    StrategyTemplate,
    ParamSpec,
)
from app.db.sql_repository import SQLRepository

logger = logging.getLogger(__name__)

# Strategy directory (project root/strategies)
STRATEGIES_DIR = Path(__file__).resolve().parents[4] / "strategies"


def _infer_category(name: str, description: str) -> str:
    """Infer strategy category from name and description.

    Args:
        name: Strategy name.
        description: Strategy description.

    Returns:
        Inferred category string (trend, mean_reversion, volatility, etc.).
    """
    text = (name + description).lower()
    if any(k in text for k in ["ma", "trend", "supertrend", "turtle",
                                "breakout", "momentum", "crossover"]):
        return "trend"
    if any(k in text for k in ["rsi", "mean_reversion", "reversal",
                                "oscillator", "overbought", "oversold",
                                "kdj", "stochastic"]):
        return "mean_reversion"
    if any(k in text for k in ["boll", "bollinger", "atr", "volatility",
                                "vix", "chandelier"]):
        return "volatility"
    if any(k in text for k in ["arbitrage", "hedge", "long_short", "pair"]):
        return "arbitrage"
    if any(k in text for k in ["macd", "ema", "signal", "indicator"]):
        return "indicator"
    return "custom"


def _scan_strategies_folder() -> List[StrategyTemplate]:
    """Scan strategies/ directory and auto-build strategy template list.

    Returns:
        List of StrategyTemplate objects parsed from strategy directories.
    """
    templates: List[StrategyTemplate] = []
    if not STRATEGIES_DIR.is_dir():
        logger.warning(f"Strategy directory does not exist: {STRATEGIES_DIR}")
        return templates

    for config_path in sorted(STRATEGIES_DIR.glob("*/config.yaml")):
        strategy_dir = config_path.parent
        dir_name = strategy_dir.name  # e.g. "029_macd_kdj"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            strat_info = config.get("strategy", {})
            name = strat_info.get("name", dir_name)
            description = strat_info.get("description", "")
            author = strat_info.get("author", "")

            # Read strategy code files
            code_files = list(strategy_dir.glob("strategy_*.py"))
            if not code_files:
                continue
            code = code_files[0].read_text(encoding="utf-8")

            # Parse parameters
            raw_params = config.get("params") or {}
            params: Dict[str, ParamSpec] = {}
            for k, v in raw_params.items():
                ptype = "float" if isinstance(v, float) else "int"
                params[k] = ParamSpec(
                    type=ptype, default=v, description=k,
                )

            category = _infer_category(name, description)

            # Read backtest config as additional metadata
            bt_config = config.get("backtest", {})
            data_config = config.get("data", {})

            # Append author and symbol info to description
            meta_parts = []
            if author:
                meta_parts.append(f"Author: {author}")
            if data_config.get("symbol"):
                meta_parts.append(f"Default Symbol: {data_config['symbol']}")
            full_desc = description
            if meta_parts:
                full_desc += " | " + " | ".join(meta_parts)

            templates.append(StrategyTemplate(
                id=dir_name,
                name=name,
                description=full_desc,
                category=category,
                code=code,
                params=params,
            ))
        except Exception as e:
            logger.warning(f"Failed to scan strategy {dir_name}: {e}")
            continue

    logger.info(f"Loaded {len(templates)} strategy templates from {STRATEGIES_DIR}")
    return templates


# Scan once at startup
STRATEGY_TEMPLATES: List[StrategyTemplate] = _scan_strategies_folder()

# Build fast lookup dictionary ID -> template
_TEMPLATE_MAP: Dict[str, StrategyTemplate] = {t.id: t for t in STRATEGY_TEMPLATES}


def get_template_by_id(template_id: str) -> Optional[StrategyTemplate]:
    """Get strategy template by ID.

    Args:
        template_id: The strategy template identifier.

    Returns:
        StrategyTemplate if found, None otherwise.
    """
    return _TEMPLATE_MAP.get(template_id)


def get_strategy_readme(template_id: str) -> Optional[str]:
    """Read the strategy's README.md content.

    Args:
        template_id: The strategy template identifier.

    Returns:
        README content as string if found, None otherwise.
    """
    readme_path = STRATEGIES_DIR / template_id / "README.md"
    if readme_path.is_file():
        return readme_path.read_text(encoding="utf-8")
    return None


class StrategyService:
    """Service for managing user-defined strategies."""

    def __init__(self) -> None:
        """Initialize the StrategyService.

        Attributes:
            strategy_repo: Repository for strategy CRUD operations.
        """
        self.strategy_repo = SQLRepository(Strategy)

    async def create_strategy(
        self,
        user_id: str,
        strategy_create: StrategyCreate
    ) -> StrategyResponse:
        """Create a new user strategy.

        Args:
            user_id: The ID of the user creating the strategy.
            strategy_create: Strategy creation data.

        Returns:
            StrategyResponse: The created strategy.
        """
        strategy = Strategy(
            user_id=user_id,
            name=strategy_create.name,
            description=strategy_create.description,
            code=strategy_create.code,
            params={k: v.model_dump() for k, v in strategy_create.params.items()},
            category=strategy_create.category,
        )

        strategy = await self.strategy_repo.create(strategy)

        return self._to_response(strategy)

    async def get_strategy(self, strategy_id: str) -> Optional[StrategyResponse]:
        """Get strategy details by ID.

        Args:
            strategy_id: The unique identifier for the strategy.

        Returns:
            StrategyResponse if found, None otherwise.
        """
        strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy:
            return None
        return self._to_response(strategy)

    async def update_strategy(
        self,
        strategy_id: str,
        user_id: str,
        strategy_update: StrategyUpdate
    ) -> Optional[StrategyResponse]:
        """Update an existing strategy.

        Args:
            strategy_id: The unique identifier for the strategy.
            user_id: The ID of the user requesting the update.
            strategy_update: Strategy update data.

        Returns:
            Updated StrategyResponse if successful, None if not found
            or unauthorized.
        """
        strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy or strategy.user_id != user_id:
            return None

        update_data = {}
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
            strategy = await self.strategy_repo.update(strategy_id, update_data)

        return self._to_response(strategy)

    async def delete_strategy(self, strategy_id: str, user_id: str) -> bool:
        """Delete a strategy.

        Args:
            strategy_id: The unique identifier for the strategy.
            user_id: The ID of the user requesting deletion.

        Returns:
            True if deletion succeeded, False if not found or unauthorized.
        """
        strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy or strategy.user_id != user_id:
            return False

        return await self.strategy_repo.delete(strategy_id)

    async def list_strategies(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        category: str = None
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

        strategies = await self.strategy_repo.list(
            filters=filters,
            skip=offset,
            limit=limit
        )
        total = await self.strategy_repo.count(filters=filters)

        items = [self._to_response(s) for s in strategies]

        return StrategyListResponse(total=total, items=items)

    async def get_templates(self) -> List[StrategyTemplate]:
        """Get all available strategy templates.

        Returns:
            List of all StrategyTemplate objects.
        """
        return STRATEGY_TEMPLATES

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
                    # Be tolerant: some rows may store plain defaults
                    # instead of full ParamSpec dicts.
                    if isinstance(v, bool):
                        ptype = "bool"
                    elif isinstance(v, int):
                        ptype = "int"
                    elif isinstance(v, float):
                        ptype = "float"
                    else:
                        ptype = "string"
                    params[k] = ParamSpec(type=ptype, default=v, description=k)

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
