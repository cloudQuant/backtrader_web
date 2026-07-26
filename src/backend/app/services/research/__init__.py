"""Compatibility exports for the decomposed AI strategy research workflow."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from . import (
    continuation,
    generation,
    paper_handoff,
    pipeline_audit,
    robustness,
    run_records,
)

_WORKFLOW_MODULES: tuple[ModuleType, ...] = (
    run_records,
    robustness,
    pipeline_audit,
    continuation,
    paper_handoff,
    generation,
)


def _workflow_helpers(module: ModuleType) -> dict[str, Any]:
    return {
        name: value
        for name, value in vars(module).items()
        if callable(value) and getattr(value, "__module__", None) == module.__name__
    }


_HELPERS: dict[str, Any] = {}
for _module in _WORKFLOW_MODULES:
    _HELPERS.update(_workflow_helpers(_module))

# Existing functions freely called one another while they were in a single file.
# Populate every workflow module after all definitions are loaded so that moving a
# helper does not alter those runtime name lookups.
for _module in _WORKFLOW_MODULES:
    for _name, _value in _HELPERS.items():
        _module.__dict__.setdefault(_name, _value)

globals().update(_HELPERS)
__all__ = tuple(_HELPERS)

del _module, _name, _value
