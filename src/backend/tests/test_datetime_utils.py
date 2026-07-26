"""Regression tests for PostgreSQL timestamp compatibility."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.ai_call_log import AICallLog
from app.models.backtest import BacktestResultModel, BacktestTask
from app.models.knowledge_base import ChatConversation, ChatMessage, KBDocument, KnowledgeBase
from app.models.strategy import Strategy
from app.models.user import RefreshToken, User
from app.utils.datetime_utils import utc_now_naive


def test_utc_now_naive_returns_current_utc_without_timezone() -> None:
    """``DateTime(timezone=False)`` values must be compatible with asyncpg."""

    value = utc_now_naive()

    assert value.tzinfo is None
    assert (
        abs((datetime.now(timezone.utc) - value.replace(tzinfo=timezone.utc)).total_seconds()) < 2
    )


@pytest.mark.parametrize(
    ("model", "column_name"),
    [
        (User, "created_at"),
        (User, "updated_at"),
        (RefreshToken, "created_at"),
        (Strategy, "created_at"),
        (Strategy, "updated_at"),
        (BacktestTask, "created_at"),
        (BacktestTask, "updated_at"),
        (BacktestResultModel, "created_at"),
        (KnowledgeBase, "created_at"),
        (KnowledgeBase, "updated_at"),
        (KBDocument, "created_at"),
        (KBDocument, "updated_at"),
        (ChatConversation, "created_at"),
        (ChatConversation, "updated_at"),
        (ChatMessage, "created_at"),
        (AICallLog, "created_at"),
    ],
)
def test_postgres_timestamp_defaults_are_timezone_naive(
    model: type[object],
    column_name: str,
) -> None:
    """Model defaults match the existing PostgreSQL ``timestamp`` schema."""

    column = model.__table__.c[column_name]  # type: ignore[attr-defined]
    default = column.default

    assert default is not None
    assert getattr(default.arg, "__wrapped__", None) is utc_now_naive
