"""Allowlisted, scope-bound tools for model-assisted research workflows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

ToolHandler = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Typed operation contract owned by the service, never by prompt text."""

    required_arguments: frozenset[str]
    allowed_arguments: frozenset[str]
    required_scope: frozenset[str]
    handler: ToolHandler


class ToolBroker:
    """Mediate every tool call using operation and resource ownership allowlists."""

    def __init__(self, definitions: Mapping[str, ToolDefinition]) -> None:
        self._definitions = dict(definitions)

    async def invoke(
        self,
        *,
        operation: str,
        scope: Mapping[str, object],
        arguments: Mapping[str, object],
    ) -> dict[str, object]:
        """Execute one typed tool only when it stays inside its supplied scope."""

        definition = self._definitions.get(operation)
        if definition is None:
            raise ValueError("TOOL_OPERATION_NOT_ALLOWED")
        scope_dict = dict(scope)
        arguments_dict = dict(arguments)
        if not definition.required_scope.issubset(scope_dict):
            raise ValueError("TOOL_SCOPE_REQUIRED")
        if not definition.required_arguments.issubset(arguments_dict):
            raise ValueError("TOOL_ARGUMENT_REQUIRED")
        if not set(arguments_dict).issubset(definition.allowed_arguments):
            raise ValueError("TOOL_ARGUMENT_NOT_ALLOWED")
        for key in set(scope_dict).intersection(arguments_dict):
            if scope_dict[key] != arguments_dict[key]:
                raise ValueError("TOOL_SCOPE_ARGUMENT_MISMATCH")
        if not all(_is_json_scalar(value) for value in arguments_dict.values()):
            raise ValueError("TOOL_ARGUMENT_TYPE_INVALID")
        return await definition.handler(arguments_dict)


def _is_json_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))
