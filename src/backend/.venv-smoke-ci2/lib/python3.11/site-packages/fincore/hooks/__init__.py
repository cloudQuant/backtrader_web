"""Event hooks and execution framework for fincore plugin system."""

from __future__ import annotations

from fincore.hooks import events

# Re-export events module contents
_EVENT_HOOKS = events._EVENT_HOOKS
AnalysisContext = events.AnalysisContext
ComputeContext = events.ComputeContext
OptimizationContext = events.OptimizationContext
create_analysis_context = events.create_analysis_context
create_compute_context = events.create_compute_context
create_optimization_context = events.create_optimization_context
execute_hooks = events.execute_hooks
get_event_hooks = events.get_event_hooks
register_event_hook = events.register_event_hook
list_events = events.list_events
clear_hooks = events.clear_hooks

__all__ = [
    "_EVENT_HOOKS",
    # Events
    "AnalysisContext",
    "ComputeContext",
    "OptimizationContext",
    "clear_hooks",
    "create_analysis_context",
    "create_compute_context",
    "create_optimization_context",
    "execute_hooks",
    "get_event_hooks",
    "list_events",
    "register_event_hook",
]
