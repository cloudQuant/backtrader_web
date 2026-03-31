"""Strategy service (CRUD + template/config loading)."""

import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import yaml

from app.db.sql_repository import SQLRepository
from app.models.strategy import Strategy
from app.schemas.strategy import (
    ParamSpec,
    StrategyCreate,
    StrategyListResponse,
    StrategyResponse,
    StrategyTemplate,
    StrategyType,
    StrategyUpdate,
)

logger = logging.getLogger(__name__)

STRATEGIES_DIR = Path(__file__).resolve().parents[4] / "strategies"


def get_strategy_dir(strategy_id: str) -> Path:
    """Resolve strategy directory path with path traversal protection.

    strategy_id must be in format \"type/name\" (e.g. simulate/cu_macd_atr) or
    \"name\" for backtest-style ids. The resolved path is constrained to
    STRATEGIES_DIR to prevent directory traversal.

    Args:
        strategy_id: Strategy identifier (e.g. backtest/002_dual_ma).

    Returns:
        Path to the strategy directory.

    Raises:
        ValueError: If strategy_id contains path traversal or invalid chars.
    """
    if ".." in strategy_id or strategy_id.startswith("/") or "\\" in strategy_id:
        raise ValueError(f"Invalid strategy_id: {strategy_id}")
    path = (STRATEGIES_DIR / strategy_id).resolve()
    try:
        path.relative_to(STRATEGIES_DIR.resolve())
    except ValueError:
        raise ValueError(f"Strategy path escapes base directory: {strategy_id}") from None
    return path


def _infer_category(name: str, description: str) -> str:
    """Infer strategy category from name and description.

    Args:
        name: Strategy name.
        description: Strategy description.

    Returns:
        Inferred category string (trend, mean_reversion, volatility, etc.).
    """
    text = (name + description).lower()
    if any(
        k in text
        for k in ["ma", "trend", "supertrend", "turtle", "breakout", "momentum", "crossover"]
    ):
        return "trend"
    if any(
        k in text
        for k in [
            "rsi",
            "mean_reversion",
            "reversal",
            "oscillator",
            "overbought",
            "oversold",
            "kdj",
            "stochastic",
        ]
    ):
        return "mean_reversion"
    if any(k in text for k in ["boll", "bollinger", "atr", "volatility", "vix", "chandelier"]):
        return "volatility"
    if any(k in text for k in ["arbitrage", "hedge", "long_short", "pair"]):
        return "arbitrage"
    if any(k in text for k in ["macd", "ema", "signal", "indicator"]):
        return "indicator"
    return "custom"


def _scan_strategies_folder(strategy_type: StrategyType) -> list[StrategyTemplate]:
    """Scan strategies/ directory and auto-build strategy template list.

    Args:
        strategy_type: Type of strategy (backtest/simulate/live).

    Returns:
        List of StrategyTemplate objects parsed from strategy directories.
    """
    templates: list[StrategyTemplate] = []

    target_dir = STRATEGIES_DIR / strategy_type.value
    if not target_dir.is_dir():
        logger.warning(f"Strategy directory does not exist: {target_dir}")
        return templates

    for config_path in sorted(target_dir.glob("*/config.yaml")):
        strategy_dir = config_path.parent
        dir_name = strategy_dir.name
        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            strat_info = config.get("strategy", {})
            name = strat_info.get("name", dir_name)
            description = strat_info.get("description", "")
            author = strat_info.get("author", "")

            code_files = list(strategy_dir.glob("strategy_*.py"))
            if not code_files:
                continue
            code = code_files[0].read_text(encoding="utf-8")

            raw_params = config.get("params") or {}
            params: dict[str, ParamSpec] = {}
            for k, v in raw_params.items():
                if isinstance(v, bool):
                    ptype = "bool"
                elif isinstance(v, int):
                    ptype = "int"
                elif isinstance(v, float):
                    ptype = "float"
                else:
                    ptype = "string"
                params[k] = ParamSpec(
                    type=ptype,
                    default=v,
                    min=None,
                    max=None,
                    options=None,
                    description=k,
                )

            category = _infer_category(name, description)

            _bt_config = config.get("backtest", {})
            data_config = config.get("data", {})

            meta_parts = []
            if author:
                meta_parts.append(f"Author: {author}")
            if data_config.get("symbol"):
                meta_parts.append(f"Default Symbol: {data_config['symbol']}")
            full_desc = description
            if meta_parts:
                full_desc += " | " + " | ".join(meta_parts)

            templates.append(
                StrategyTemplate(
                    id=f"{strategy_type.value}/{dir_name}",
                    name=name,
                    description=full_desc,
                    category=category,
                    code=code,
                    params=params,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to scan strategy {dir_name}: {e}")
            continue

    logger.info(f"Loaded {len(templates)} strategy templates from {target_dir}")
    return templates


@lru_cache(maxsize=3)
def _get_templates_for_type(
    strategy_type: StrategyType,
) -> tuple[tuple[StrategyTemplate, ...], dict[str, StrategyTemplate]]:
    """Lazily load and cache strategy templates by type.

    Returns:
        Tuple of (templates list, id->template map).
    """
    templates = _scan_strategies_folder(strategy_type)
    template_map = {t.id: t for t in templates}
    return (tuple(templates), template_map)


def _get_template_map(strategy_type: StrategyType) -> dict[str, StrategyTemplate]:
    """Get cached template map for a strategy type."""
    return _get_templates_for_type(strategy_type)[1]


def get_all_strategy_templates() -> list[StrategyTemplate]:
    """Get all strategy templates (backtest + simulate + live). Lazy-loaded."""
    return (
        list(_get_templates_for_type(StrategyType.backtest)[0])
        + list(_get_templates_for_type(StrategyType.simulate)[0])
        + list(_get_templates_for_type(StrategyType.live)[0])
    )


def get_template_by_id(
    template_id: str, strategy_type: StrategyType | None = None
) -> StrategyTemplate | None:
    """Get strategy template by ID.


    Args:
        template_id: The strategy template identifier.
        strategy_type: Optional strategy type filter.

    Returns:
        StrategyTemplate if found, None otherwise.
    """
    if strategy_type:
        return _get_template_map(strategy_type).get(template_id)

    for st in (StrategyType.backtest, StrategyType.simulate, StrategyType.live):
        tpl = _get_template_map(st).get(template_id)
        if tpl:
            return tpl
    return None


def get_strategy_readme(template_id: str, strategy_type: StrategyType | None = None) -> str | None:
    """Read the strategy's README.md content.

    Args:
        template_id: The strategy template identifier.
        strategy_type: Optional strategy type filter.

    Returns:
        README content as string if found, None otherwise.
    """
    try:
        parts = template_id.split("/", 1)
        if len(parts) == 2:
            readme_path = get_strategy_dir(template_id) / "README.md"
        elif strategy_type:
            readme_path = get_strategy_dir(f"{strategy_type.value}/{template_id}") / "README.md"
        else:
            return None
    except ValueError:
        return None

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
        self, user_id: str, strategy_create: StrategyCreate
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

        update_data = {}
        if strategy_update.name is not None:
            update_data["name"] = strategy_update.name
        if strategy_update.description is not None:
            update_data["description"] = strategy_update.description
        if strategy_update.code is not None:
            update_data["code"] = strategy_update.code
        if strategy_update.params is not None:
            update_data["params"] = {k: v.model_dump() for k, v in strategy_update.params.items()}
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
        strategy = await self._get_owned_strategy(strategy_id, user_id)
        if strategy is None:
            return False

        return await self.strategy_repo.delete(strategy_id)

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
