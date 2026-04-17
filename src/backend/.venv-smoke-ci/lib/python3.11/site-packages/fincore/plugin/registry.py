"""Plugin registry for fincore framework.

Allows dynamic extension of fincore's capabilities through:
- Custom metric functions
- Custom visualization backends
- Event hooks (pre/post analysis, pre/post compute)
- Custom risk models
- Custom optimization objectives
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "clear_registry",
    "execute_hooks",
    "get_metric",
    "get_viz_backend",
    "list_hooks",
    "list_metrics",
    "list_viz_backends",
    "register_hook",
    "register_metric",
    "register_viz_backend",
]


# =============================================================================
# Registry Storage
# =============================================================================

_METRIC_REGISTRY: dict[str, Callable] = {}
_HOOK_REGISTRY: dict[str, list[tuple[int, Callable]]] = {}
_VIZ_BACKEND_REGISTRY: dict[str, type] = {}


# =============================================================================
# Decorators
# =============================================================================


def register_metric(
    name: str | None = None,
) -> Callable:
    """Decorator to register a custom metric function.

    The decorated function should:
    - Take returns (pd.Series or np.ndarray) as first argument
    - Return a single scalar value

    Example::
        @register_metric("custom_ratio")
        def custom_ratio(returns, period=252):
            mean = np.mean(returns)
            std = np.std(returns, ddof=1)
            return mean / std * np.sqrt(period)
    """

    def decorator(func: Callable) -> Callable:
        metric_name = name or func.__name__
        _METRIC_REGISTRY[metric_name] = func

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper.__name__ = metric_name
        return wrapper

    return decorator


def register_viz_backend(
    name: str,
) -> Callable[[type], type]:
    """Decorator to register a custom visualization backend.

    The decorated class should provide the following methods:
    - plot_returns(cum_returns, **kwargs) - Plot cumulative returns
    - plot_drawdown(drawdown, **kwargs) - Plot underwater chart
    - plot_rolling_sharpe(sharpe, **kwargs) - Plot rolling Sharpe ratio
    - plot_monthly_heatmap(returns, **kwargs) - Plot monthly heatmap

    The backend class should be initialized with theme parameter.

    Example::

        @register_viz_backend("my_backend")
        class MyBackend:
            def __init__(self, theme="light"):
                self.theme = theme

            def plot_returns(self, cum_returns, **kwargs):
                import matplotlib.pyplot as plt
                fig, ax = plt.subplots()
                ax.plot(cum_returns.index, cum_returns.values)
                return fig

    """

    def decorator(cls: type) -> type:
        backend_name = name or cls.__name__
        _VIZ_BACKEND_REGISTRY[backend_name] = cls
        return cls

    return decorator


def register_hook(
    event: str,
    priority: int = 100,
) -> Callable:
    """Decorator to register an event hook.

    Available events:
    - "pre_analysis": Before AnalysisContext computes metrics, validate data
    - "post_analysis": After metrics computed, add custom results
    - "pre_compute": Before solving optimization, validate constraints
    - "post_compute": After optimization, validate results

    Hooks receive (analysis_context, returns, weights, factor_data, etc) depending on event type.

    Example::

        @register_hook("pre_analysis", priority=50)
        def validate_returns(returns, **kwargs):
            # Remove outliers
            returns_clean = returns[returns < 3 * returns.std()]
            return returns_clean
    """

    def decorator(func: Callable) -> Callable:
        event_name = event or func.__name__

        if event_name not in _HOOK_REGISTRY:
            _HOOK_REGISTRY[event_name] = []
        _HOOK_REGISTRY[event_name].append((priority, func))
        _HOOK_REGISTRY[event_name].sort(key=lambda x: x[0])

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper.__name__ = event_name
        return wrapper

    return decorator


# =============================================================================
# Public API Functions
# =============================================================================


def list_metrics() -> dict[str, Callable]:
    """List all registered custom metrics."""
    return _METRIC_REGISTRY.copy()


def list_viz_backends() -> dict[str, type]:
    """List all registered visualization backends."""
    return _VIZ_BACKEND_REGISTRY.copy()


def list_hooks(event: str | None = None) -> dict[str, list[Callable]]:
    """List all registered hooks for an event.

    Returns hook functions in priority order (lowest priority number first).
    """
    if event is None:
        return {k: [fn for _, fn in v] for k, v in _HOOK_REGISTRY.items()}
    hooks = _HOOK_REGISTRY.get(event, [])
    return {event: [fn for _, fn in hooks]}


def get_metric(name: str) -> Callable | None:
    """Get a registered metric by name."""
    return _METRIC_REGISTRY.get(name)


def get_viz_backend(name: str) -> type | None:
    """Get a registered visualization backend by name."""
    return _VIZ_BACKEND_REGISTRY.get(name)


def execute_hooks(
    event: str,
    *args,
    **kwargs,
) -> None:
    """Execute all hooks registered for an event.

    Hooks are executed in priority order (lowest priority number first).
    """
    for _priority, hook_fn in _HOOK_REGISTRY.get(event, []):
        hook_fn(*args, **kwargs)


def clear_registry(registry_type: str | None = None) -> None:
    """Clear one or all registries.

    Parameters
    ----------
    registry_type : str, optional
        'metrics', 'hooks', 'viz_backends', or None to clear all.
    """
    if registry_type is None or registry_type == "metrics":
        _METRIC_REGISTRY.clear()
    if registry_type is None or registry_type == "hooks":
        _HOOK_REGISTRY.clear()
    if registry_type is None or registry_type == "viz_backends":
        _VIZ_BACKEND_REGISTRY.clear()
