from __future__ import annotations

import pytest

from app.services.research.tool_broker import ToolBroker, ToolDefinition


@pytest.mark.asyncio
async def test_tool_broker_allows_only_typed_allowlisted_operation_in_owned_scope() -> None:
    calls = []

    async def handler(arguments: dict[str, object]) -> dict[str, object]:
        calls.append(arguments)
        return {"artifact_id": arguments["artifact_id"], "status": "ok"}

    broker = ToolBroker(
        {
            "read_artifact_manifest": ToolDefinition(
                required_arguments=frozenset({"artifact_id"}),
                allowed_arguments=frozenset({"artifact_id"}),
                required_scope=frozenset({"user_id", "artifact_id"}),
                handler=handler,
            )
        }
    )

    result = await broker.invoke(
        operation="read_artifact_manifest",
        scope={"user_id": "user-1", "artifact_id": "artifact-1"},
        arguments={"artifact_id": "artifact-1"},
    )

    assert result == {"artifact_id": "artifact-1", "status": "ok"}
    assert calls == [{"artifact_id": "artifact-1"}]


@pytest.mark.asyncio
async def test_tool_broker_rejects_prompt_injected_operations_and_scope_escape() -> None:
    async def handler(arguments: dict[str, object]) -> dict[str, object]:
        return arguments

    broker = ToolBroker(
        {
            "read_artifact_manifest": ToolDefinition(
                required_arguments=frozenset({"artifact_id"}),
                allowed_arguments=frozenset({"artifact_id"}),
                required_scope=frozenset({"user_id", "artifact_id"}),
                handler=handler,
            )
        }
    )

    with pytest.raises(ValueError, match="TOOL_OPERATION_NOT_ALLOWED"):
        await broker.invoke(
            operation="shell_execute",
            scope={"user_id": "user-1"},
            arguments={"command": "curl https://evil.example"},
        )
    with pytest.raises(ValueError, match="TOOL_SCOPE_ARGUMENT_MISMATCH"):
        await broker.invoke(
            operation="read_artifact_manifest",
            scope={"user_id": "user-1", "artifact_id": "artifact-1"},
            arguments={"artifact_id": "artifact-2"},
        )
    with pytest.raises(ValueError, match="TOOL_ARGUMENT_NOT_ALLOWED"):
        await broker.invoke(
            operation="read_artifact_manifest",
            scope={"user_id": "user-1", "artifact_id": "artifact-1"},
            arguments={"artifact_id": "artifact-1", "authorization": "Bearer secret"},
        )
