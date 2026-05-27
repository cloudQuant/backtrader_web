import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_call_log import AICallLog
from app.models.audit_record import AuditRecord
from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_quant_tools_schema_auth_rate_limit_and_audit(client: AsyncClient):
    _, headers = await register_and_login(client, username="tool_user")
    _, admin_headers = await register_and_login(client, username="admin")

    await client.post("/api/v1/data-governance/bootstrap", headers=admin_headers)

    listed = await client.get("/api/v1/quant-tools", headers=headers)
    quote = await client.post(
        "/api/v1/quant-tools/call",
        headers=headers,
        json={"tool_name": "markets.get_quote", "input": {"symbol": "RB2510"}},
    )
    invalid = await client.post(
        "/api/v1/quant-tools/call",
        headers=headers,
        json={"tool_name": "markets.get_quote", "input": {"symbol": 123}},
    )
    forbidden = await client.post(
        "/api/v1/quant-tools/call",
        headers=headers,
        json={"tool_name": "data_topics.peek", "input": {"topic": "market:quote:RB2510"}},
    )
    admin_allowed = await client.post(
        "/api/v1/quant-tools/call",
        headers=admin_headers,
        json={"tool_name": "data_topics.peek", "input": {"topic": "market:quote:RB2510"}},
    )
    var_cvar = await client.post(
        "/api/v1/quant-tools/call",
        headers=headers,
        json={
            "tool_name": "risk.var_cvar",
            "input": {"symbol": "RB2510", "returns": [-0.03, -0.01, 0.01, 0.02]},
        },
    )
    endpoint_preview = await client.post(
        "/api/v1/quant-tools/call",
        headers=admin_headers,
        json={
            "tool_name": "data_governance.endpoint_preview",
            "input": {"endpoint": "quote", "params": {"symbol": "RB2510"}},
        },
    )
    timed_out = await client.post(
        "/api/v1/quant-tools/call",
        headers=headers,
        json={"tool_name": "debug.sleep", "input": {"delay_ms": 10}},
    )

    for _ in range(30):
        await client.post(
            "/api/v1/quant-tools/call",
            headers=headers,
            json={"tool_name": "data_topics.list", "input": {}},
        )
    limited = await client.post(
        "/api/v1/quant-tools/call",
        headers=headers,
        json={"tool_name": "data_topics.list", "input": {}},
    )

    assert listed.status_code == 200
    quote_tool = next(
        item for item in listed.json()["tools"] if item["name"] == "markets.get_quote"
    )
    assert quote_tool["output_schema"]["type"] == "object"
    assert quote_tool["auth_level"] == "user"
    assert quote_tool["requires_confirmation"] is False
    assert quote_tool["timeout_ms"] == 5000
    assert quote_tool["rate_limit_per_user_per_min"] == 30
    assert quote.status_code == 200
    assert quote.json()["status"] == "ok"
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "invalid_tool_input"
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "insufficient_auth_level"
    assert admin_allowed.status_code == 200
    assert var_cvar.status_code == 200
    assert var_cvar.json()["result"]["sample_size"] == 4
    assert endpoint_preview.status_code == 200
    assert endpoint_preview.json()["result"]["preview"]["status"] == "ok"
    assert timed_out.status_code == 504
    assert timed_out.json()["detail"] == "tool_timeout"
    assert limited.status_code == 429

    async with async_session_maker() as session:
        ai_logs = (await session.execute(select(AICallLog))).scalars().all()
        audit_records = (await session.execute(select(AuditRecord))).scalars().all()

    assert any(log.service_name == "quant_tool" for log in ai_logs)
    assert any(record.event_type == "quant_tool.call" for record in audit_records)
    assert all(log.response_chars <= 4096 for log in ai_logs)
    assert any(
        record.event_target == "markets.get_quote" and len(record.event_data or "") <= 4096
        for record in audit_records
    )


@pytest.mark.asyncio
async def test_quant_tools_destructive_guard_requires_confirmation(client: AsyncClient):
    _, headers = await register_and_login(client, username="tool_guard")

    response = await client.post(
        "/api/v1/quant-tools/call",
        headers=headers,
        json={
            "tool_name": "portfolio_ledger.import_transactions",
            "input": {"idempotency_key": "abc"},
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "confirmation_required"


@pytest.mark.asyncio
async def test_quant_tools_chat_integration_supports_three_readonly_tools(client: AsyncClient):
    _, headers = await register_and_login(client, username="tool_chat")

    response = await client.post(
        "/api/v1/quant-tools/chat-simulate",
        headers=headers,
        json={"tool_calls": ["markets.get_quote", "data_topics.list", "news.latest"]},
    )

    assert response.status_code == 200
    assert response.json()["called_count"] == 3
    assert all(item["status"] == "ok" for item in response.json()["results"])
