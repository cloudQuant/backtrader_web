from unittest.mock import MagicMock, patch

import pytest

from app.db.database import async_session_maker
from app.models.ai_call_log import AICallLog
from app.models.prompt_template import PromptTemplate
from app.services.ai_chat_service import AIChatService
from app.services.ai_observability.logger import get_ai_call_log_sink


class TestAIChatServicePromptRegistry:
    def _make_service(self):
        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = "http://localhost:8000"
            settings.AI_CHAT_API_KEY = "sk-test-key"
            settings.AI_CHAT_MODEL = "gpt-4"
            settings.AI_CHAT_TIMEOUT = 30
            settings.AI_CHAT_TEMPERATURE = 0.2
            mock_settings.return_value = settings
            return AIChatService()

    @pytest.mark.asyncio
    async def test_build_messages_uses_active_prompt_template_for_mode(self):
        async with async_session_maker() as session:
            session.add(
                PromptTemplate(
                    name="knowledge_qa",
                    version="v2",
                    content="注册中心模板：{{question}}。上下文：{{context_text}}",
                    status="active",
                    variables=["question", "context_text"],
                    created_by="admin-user",
                )
            )
            await session.commit()

        service = self._make_service()
        (
            messages,
            prompt_template_id,
            prompt_template_version,
        ) = await service._build_messages_with_registry(
            question="什么是均线策略？",
            citations=[
                {
                    "document_title": "指南",
                    "chunk_index": 1,
                    "similarity": 0.9,
                    "content": "均线交叉",
                }
            ],
            assistant_mode="knowledge_qa",
            thinking_mode=False,
            conversation_history=None,
            retrieval_diagnostics=None,
            knowledge_base_settings=None,
        )

        assert prompt_template_id is not None
        assert prompt_template_version == "v2"
        assert "注册中心模板：什么是均线策略？" in messages[-1]["content"]
        assert "均线交叉" in messages[-1]["content"]
        assert "模式要求" not in messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_build_messages_falls_back_to_default_prompt_when_no_active_template(self):
        service = self._make_service()
        (
            messages,
            prompt_template_id,
            prompt_template_version,
        ) = await service._build_messages_with_registry(
            question="什么是均线策略？",
            citations=[],
            assistant_mode="knowledge_qa",
            thinking_mode=False,
            conversation_history=None,
            retrieval_diagnostics=None,
            knowledge_base_settings=None,
        )

        assert prompt_template_id is None
        assert prompt_template_version is None
        assert "模式要求" in messages[-1]["content"]
        assert "AI for Trader 的知识库助手" in messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_generate_answer_records_prompt_template_id_for_active_template(self):
        from sqlalchemy import select

        from app.services.ai_router.router import ChatCompletionResponse

        async with async_session_maker() as session:
            template = PromptTemplate(
                name="knowledge_qa",
                version="v3",
                content="日志模板：{{question}}",
                status="active",
                variables=["question"],
                created_by="admin-user",
            )
            session.add(template)
            await session.commit()
            await session.refresh(template)
            template_id = str(template.id)

        service = self._make_service()

        async def fake_chat_completion(**kwargs):
            return ChatCompletionResponse(
                content="模板回答",
                model="gpt-4",
                provider="openai_compatible",
                total_tokens=5,
            )

        service.ai_router.chat_completion = fake_chat_completion
        result = await service.generate_answer(
            question="什么是均线策略？",
            citations=[],
            assistant_mode="knowledge_qa",
            thinking_mode=False,
        )
        sink = get_ai_call_log_sink()
        try:
            await sink.flush()
        finally:
            await sink.shutdown()

        assert result["answer"] == "模板回答"
        async with async_session_maker() as session:
            rows = (await session.execute(select(AICallLog))).scalars().all()
        assert rows[0].prompt_template_id == template_id

    @pytest.mark.asyncio
    async def test_build_messages_uses_rollout_template_for_selected_user(self):
        async with async_session_maker() as session:
            session.add_all(
                [
                    PromptTemplate(
                        name="knowledge_qa",
                        version="stable",
                        content="稳定模板：{{question}}",
                        status="active",
                        variables=["question"],
                        rollout_percentage=0,
                    ),
                    PromptTemplate(
                        name="knowledge_qa",
                        version="canary",
                        content="灰度模板：{{question}}",
                        status="draft",
                        variables=["question"],
                        rollout_percentage=100,
                    ),
                ]
            )
            await session.commit()

        service = self._make_service()
        (
            messages,
            prompt_template_id,
            prompt_template_version,
        ) = await service._build_messages_with_registry(
            question="什么是均线策略？",
            citations=[],
            assistant_mode="knowledge_qa",
            thinking_mode=False,
            conversation_history=None,
            retrieval_diagnostics=None,
            knowledge_base_settings=None,
            user_id="user-canary",
        )

        assert prompt_template_id is not None
        assert prompt_template_version == "canary"
        assert "灰度模板：什么是均线策略？" in messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_build_messages_falls_back_to_active_template_when_rollout_misses(self):
        async with async_session_maker() as session:
            session.add_all(
                [
                    PromptTemplate(
                        name="knowledge_qa",
                        version="stable",
                        content="稳定模板：{{question}}",
                        status="active",
                        variables=["question"],
                        rollout_percentage=0,
                    ),
                    PromptTemplate(
                        name="knowledge_qa",
                        version="canary",
                        content="灰度模板：{{question}}",
                        status="draft",
                        variables=["question"],
                        rollout_percentage=0,
                    ),
                ]
            )
            await session.commit()

        service = self._make_service()
        (
            messages,
            prompt_template_id,
            prompt_template_version,
        ) = await service._build_messages_with_registry(
            question="什么是均线策略？",
            citations=[],
            assistant_mode="knowledge_qa",
            thinking_mode=False,
            conversation_history=None,
            retrieval_diagnostics=None,
            knowledge_base_settings=None,
            user_id="user-stable",
        )

        assert prompt_template_id is not None
        assert prompt_template_version == "stable"
        assert "稳定模板：什么是均线策略？" in messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_generate_answer_records_prompt_template_version(self):
        from sqlalchemy import select

        from app.services.ai_router.router import ChatCompletionResponse

        async with async_session_maker() as session:
            session.add(
                PromptTemplate(
                    name="knowledge_qa",
                    version="stable",
                    content="版本日志模板：{{question}}",
                    status="active",
                    variables=["question"],
                    rollout_percentage=0,
                )
            )
            await session.commit()

        service = self._make_service()

        async def fake_chat_completion(**kwargs):
            return ChatCompletionResponse(
                content="模板回答",
                model="gpt-4",
                provider="openai_compatible",
                total_tokens=5,
            )

        service.ai_router.chat_completion = fake_chat_completion
        result = await service.generate_answer(
            question="什么是均线策略？",
            citations=[],
            assistant_mode="knowledge_qa",
            thinking_mode=False,
            user_id="user-stable",
        )
        sink = get_ai_call_log_sink()
        try:
            await sink.flush()
        finally:
            await sink.shutdown()

        assert result["answer"] == "模板回答"
        async with async_session_maker() as session:
            rows = (await session.execute(select(AICallLog))).scalars().all()
        assert rows[0].prompt_template_version == "stable"
