"""Compatibility exports for decomposed trading asset information helpers."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from . import gateway_specs, normalization, positions

_MODULES: tuple[ModuleType, ...] = (positions, normalization, gateway_specs)


def _module_functions(module: ModuleType) -> dict[str, Any]:
    return {
        name: value
        for name, value in vars(module).items()
        if callable(value) and getattr(value, "__module__", None) == module.__name__
    }


_FUNCTIONS: dict[str, Any] = {}
for _module in _MODULES:
    _FUNCTIONS.update(_module_functions(_module))

# The original service was a single module, so helpers use direct global name
# lookups. Restore that runtime visibility after every submodule is loaded.
for _module in _MODULES:
    for _name, _value in _FUNCTIONS.items():
        if _value.__module__ != _module.__name__:
            _module.__dict__[_name] = _value

globals().update(_FUNCTIONS)
__all__ = tuple(_FUNCTIONS)

del _module, _name, _value
