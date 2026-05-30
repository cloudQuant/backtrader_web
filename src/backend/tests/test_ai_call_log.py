"""Tests for AI call log model and schemas."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect

from app.db.database import Base


def test_ai_call_log_model_registers_privacy_preserving_columns() -> None:
    from app.models.ai_call_log import AICallLog

    table = AICallLog.__table__
    assert table.name == "ai_call_logs"
    assert table.name in Base.metadata.tables

    columns = {column.name for column in table.columns}
    assert {
        "id",
        "user_id",
        "request_id",
        "service_name",
        "mode",
        "model_name",
        "provider",
        "prompt_template_id",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_cost_usd",
        "latency_ms",
        "status",
        "error_code",
        "error_message",
        "created_at",
        "response_chars",
        "prompt_hash",
    }.issubset(columns)
    assert "prompt" not in columns
    assert "response" not in columns

    assert table.c.prompt_hash.type.length == 64
    assert table.c.service_name.nullable is False
    assert table.c.status.nullable is False
    assert table.c.prompt_tokens.default.arg == 0
    assert table.c.completion_tokens.default.arg == 0
    assert table.c.total_tokens.default.arg == 0
    assert table.c.response_chars.default.arg == 0


def test_ai_call_log_model_indexes_common_observability_queries() -> None:
    from app.models.ai_call_log import AICallLog

    indexes = {
        index.name: {column.name for column in index.columns}
        for index in AICallLog.__table__.indexes
    }
    assert indexes["ix_ai_call_logs_created_at"] == {"created_at"}
    assert indexes["ix_ai_call_logs_user_created_at"] == {"user_id", "created_at"}
    assert indexes["ix_ai_call_logs_service_created_at"] == {"service_name", "created_at"}
    assert indexes["ix_ai_call_logs_status_created_at"] == {"status", "created_at"}


def test_ai_call_log_schema_validates_status_and_non_negative_metrics() -> None:
    from app.schemas.ai_observability import AICallLogCreate, AICallStatus

    payload = AICallLogCreate(
        user_id="user-1",
        request_id="req-1",
        service_name="ai_chat",
        mode="knowledge_qa",
        model_name="gpt-4o-mini",
        provider="openai",
        prompt_template_id="kb-chat:v1",
        prompt_tokens=100,
        completion_tokens=40,
        total_tokens=140,
        estimated_cost_usd=0.00021,
        latency_ms=250,
        status=AICallStatus.SUCCESS,
        error_code=None,
        error_message=None,
        response_chars=128,
        prompt_hash="a" * 64,
    )
    assert payload.status == AICallStatus.SUCCESS
    assert payload.prompt_hash == "a" * 64

    with pytest.raises(ValidationError):
        AICallLogCreate(
            service_name="ai_chat",
            mode="knowledge_qa",
            model_name="gpt-4o-mini",
            provider="openai",
            prompt_tokens=-1,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=10,
            status=AICallStatus.SUCCESS,
            response_chars=0,
            prompt_hash="a" * 64,
        )

    with pytest.raises(ValidationError):
        AICallLogCreate(
            service_name="ai_chat",
            mode="knowledge_qa",
            model_name="gpt-4o-mini",
            provider="openai",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=10,
            status="unknown",
            response_chars=0,
            prompt_hash="a" * 64,
        )


def test_ai_call_log_read_schema_serializes_orm_model() -> None:
    from app.models.ai_call_log import AICallLog
    from app.schemas.ai_observability import AICallLogRead, AICallStatus

    record = AICallLog(
        id="log-1",
        user_id="user-1",
        request_id="req-1",
        service_name="strategy_explainer",
        mode="strategy_review",
        model_name="gpt-4o",
        provider="openai",
        prompt_tokens=12,
        completion_tokens=8,
        total_tokens=20,
        estimated_cost_usd=0.001,
        latency_ms=321,
        status=AICallStatus.SUCCESS.value,
        response_chars=256,
        prompt_hash="b" * 64,
        created_at=datetime.now(timezone.utc),
    )
    payload = AICallLogRead.model_validate(record)
    assert payload.id == "log-1"
    assert payload.status == AICallStatus.SUCCESS
    assert payload.total_tokens == 20


def test_ai_call_log_migration_declares_expected_table() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0006_add_ai_call_logs.py"
    )
    assert migration_path.exists()
    content = migration_path.read_text(encoding="utf-8")
    assert 'revision = "0006_add_ai_call_logs"' in content
    assert 'down_revision = "0005_add_ai_trading_logs"' in content
    assert 'op.create_table(\n        "ai_call_logs"' in content
    for column_name in [
        "service_name",
        "mode",
        "model_name",
        "provider",
        "total_tokens",
        "estimated_cost_usd",
        "latency_ms",
        "prompt_hash",
    ]:
        assert f'"{column_name}"' in content


@pytest.mark.asyncio
async def test_ai_call_logs_table_can_be_created_in_test_database() -> None:
    from app.db.database import engine
    from app.models.ai_call_log import AICallLog

    async with engine.begin() as conn:
        await conn.run_sync(AICallLog.__table__.create, checkfirst=True)
        table_names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    assert AICallLog.__tablename__ in table_names
