"""Strategy template scanning and lookup helpers.

Templates are auto-discovered from the ``strategies/`` directory at the project
root. Each template is described by a ``config.yaml`` plus a ``strategy_*.py``
file under ``strategies/<type>/<name>/``.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

from app.schemas.strategy import ParamSpec, StrategyResponse, StrategyTemplate, StrategyType
from app.services.strategy.ai_draft import strategy_param_defaults
from app.services.strategy.inference import infer_category

logger = logging.getLogger(__name__)

STRATEGIES_DIR = Path(__file__).resolve().parents[4] / "strategies"


def get_strategy_dir(strategy_id: str) -> Path:
    """Resolve strategy directory path with path traversal protection.

    ``strategy_id`` must be in the form ``"type/name"`` (e.g. ``simulate/cu_macd_atr``)
    or ``"name"`` for backtest-style ids. The resolved path is constrained to
    ``STRATEGIES_DIR`` to prevent directory traversal.

    Args:
        strategy_id: Strategy identifier (e.g. ``backtest/002_dual_ma``).

    Returns:
        Path to the strategy directory.

    Raises:
        ValueError: If ``strategy_id`` contains path traversal or invalid chars.
    """
    if ".." in strategy_id or strategy_id.startswith("/") or "\\" in strategy_id:
        raise ValueError(f"Invalid strategy_id: {strategy_id}")
    path = (STRATEGIES_DIR / strategy_id).resolve()
    try:
        path.relative_to(STRATEGIES_DIR.resolve())
    except ValueError:
        raise ValueError(f"Strategy path escapes base directory: {strategy_id}") from None
    return path


def sync_user_strategy_runtime_files(strategy: StrategyResponse) -> None:
    """Persist a user strategy into runtime-consumable files under ``strategies/``."""
    strategy_dir = get_strategy_dir(strategy.id)
    strategy_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "strategy": {
            "name": strategy.name,
            "description": strategy.description or "",
        },
        "params": strategy_param_defaults(strategy.params),
        "data": {
            "data_type": strategy.category or "custom",
            "category": strategy.category or "custom",
            "symbol": "",
            "symbol_name": "",
            "timeframe": "1d",
            "timeframe_n": 1,
        },
        "backtest": {
            "initial_cash": 100000.0,
            "commission": 0.001,
        },
    }
    with (strategy_dir / "config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
    (strategy_dir / "strategy_generated.py").write_text(strategy.code, encoding="utf-8")


def scan_strategies_folder(strategy_type: StrategyType) -> list[StrategyTemplate]:
    """Scan ``strategies/`` directory and auto-build the strategy template list.

    Args:
        strategy_type: Type of strategy (backtest/simulate/live).

    Returns:
        List of ``StrategyTemplate`` objects parsed from strategy directories.
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

            category = infer_category(name, description)

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
    templates = scan_strategies_folder(strategy_type)
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
    """Get a strategy template by id.

    Args:
        template_id: The strategy template identifier.
        strategy_type: Optional strategy type filter.

    Returns:
        ``StrategyTemplate`` if found, ``None`` otherwise.
    """
    if strategy_type:
        return _get_template_map(strategy_type).get(template_id)

    for st in (StrategyType.backtest, StrategyType.simulate, StrategyType.live):
        tpl = _get_template_map(st).get(template_id)
        if tpl:
            return tpl
    return None


def get_strategy_readme(
    template_id: str, strategy_type: StrategyType | None = None
) -> str | None:
    """Read the strategy's ``README.md`` content.

    Args:
        template_id: The strategy template identifier.
        strategy_type: Optional strategy type filter.

    Returns:
        README content as string if found, ``None`` otherwise.
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
