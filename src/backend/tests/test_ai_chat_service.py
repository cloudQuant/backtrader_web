"""Tests for AIChatService - AI chat provider integration."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai_chat_service import AIChatService, _normalize_text


class TestNormalizeText:
    """Test text normalization helper."""

    def test_normal_text(self):
        assert _normalize_text("hello world") == "hello world"

    def test_extra_whitespace(self):
        assert _normalize_text("  hello   world  ") == "hello world"

    def test_newlines_and_tabs(self):
        assert _normalize_text("hello\n\tworld") == "hello world"

    def test_empty_string(self):
        assert _normalize_text("") == ""

    def test_none_value(self):
        assert _normalize_text(None) == ""


class TestAIChatServiceIsEnabled:
    """Test is_enabled() method."""

    def test_enabled_when_all_settings_present(self):
        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = "http://localhost:8000"
            settings.AI_CHAT_API_KEY = "sk-test-key"
            settings.AI_CHAT_MODEL = "gpt-4"
            mock_settings.return_value = settings
            service = AIChatService()
            assert service.is_enabled() is True

    def test_disabled_when_flag_false(self):
        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = False
            settings.AI_CHAT_BASE_URL = "http://localhost:8000"
            settings.AI_CHAT_API_KEY = "sk-test-key"
            settings.AI_CHAT_MODEL = "gpt-4"
            mock_settings.return_value = settings
            service = AIChatService()
            assert service.is_enabled() is False

    def test_disabled_when_base_url_empty(self):
        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = "  "
            settings.AI_CHAT_API_KEY = "sk-test-key"
            settings.AI_CHAT_MODEL = "gpt-4"
            mock_settings.return_value = settings
            service = AIChatService()
            assert service.is_enabled() is False

    def test_disabled_when_api_key_empty(self):
        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = "http://localhost:8000"
            settings.AI_CHAT_API_KEY = ""
            settings.AI_CHAT_MODEL = "gpt-4"
            mock_settings.return_value = settings
            service = AIChatService()
            assert service.is_enabled() is False

    def test_disabled_when_model_empty(self):
        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = "http://localhost:8000"
            settings.AI_CHAT_API_KEY = "sk-test-key"
            settings.AI_CHAT_MODEL = ""
            mock_settings.return_value = settings
            service = AIChatService()
            assert service.is_enabled() is False


class TestAIChatServiceCanGenerate:
    """Test model-aware AI generation availability."""

    @pytest.mark.asyncio
    async def test_can_generate_with_configured_session_model_when_fallback_empty(self):
        from app.services.ai_router.preferences import ResolvedAIModelPreference

        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = ""
            settings.AI_CHAT_API_KEY = ""
            settings.AI_CHAT_MODEL = ""
            mock_settings.return_value = settings
            service = AIChatService()
            service.model_preference_service.resolve_model_key = MagicMock(
                return_value=ResolvedAIModelPreference(
                    provider="openai_compatible",
                    model="deepseek-ai/DeepSeek-V4-Flash",
                    base_url="https://api.siliconflow.cn/v1",
                    api_key="sk-test",
                    configured=True,
                )
            )
            service.model_preference_service.resolve_for_user = AsyncMock()

            assert await service.can_generate(model_id="siliconflow::deepseek-ai/DeepSeek-V4-Flash")

        service.model_preference_service.resolve_for_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_can_generate_rejects_unconfigured_selected_model(self):
        from app.services.ai_router.preferences import ResolvedAIModelPreference

        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = "http://fallback.invalid"
            settings.AI_CHAT_API_KEY = "sk-fallback"
            settings.AI_CHAT_MODEL = "fallback-model"
            mock_settings.return_value = settings
            service = AIChatService()
            service.model_preference_service.resolve_model_key = MagicMock(
                return_value=ResolvedAIModelPreference(
                    provider="openai_compatible",
                    model="deepseek-ai/DeepSeek-V4-Flash",
                    base_url="https://api.siliconflow.cn/v1",
                    api_key=None,
                    configured=False,
                )
            )

            assert (
                await service.can_generate(model_id="siliconflow::deepseek-ai/DeepSeek-V4-Flash")
                is False
            )


class TestAIChatServiceBuildMessages:
    """Test message building logic."""

    def _make_service(self):
        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = "http://localhost:8000"
            settings.AI_CHAT_API_KEY = "sk-test-key"
            settings.AI_CHAT_MODEL = "gpt-4"
            mock_settings.return_value = settings
            return AIChatService()

    def test_build_messages_basic(self):
        service = self._make_service()
        messages = service._build_messages(
            question="什么是均线策略？",
            citations=[],
            assistant_mode="knowledge_qa",
            thinking_mode=False,
            conversation_history=None,
            retrieval_diagnostics=None,
            knowledge_base_settings=None,
        )
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert "均线策略" in messages[-1]["content"]

    def test_build_messages_with_citations(self):
        service = self._make_service()
        citations = [
            {
                "document_title": "策略指南",
                "chunk_index": 1,
                "similarity": 0.95,
                "content": "均线策略是一种趋势跟踪策略",
            }
        ]
        messages = service._build_messages(
            question="什么是均线策略？",
            citations=citations,
            assistant_mode="knowledge_qa",
            thinking_mode=False,
            conversation_history=None,
            retrieval_diagnostics=None,
            knowledge_base_settings=None,
        )
        user_content = messages[-1]["content"]
        assert "策略指南" in user_content
        assert "均线策略是一种趋势跟踪策略" in user_content

    def test_build_messages_with_conversation_history(self):
        service = self._make_service()
        history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
        ]
        messages = service._build_messages(
            question="继续",
            citations=[],
            assistant_mode="knowledge_qa",
            thinking_mode=False,
            conversation_history=history,
            retrieval_diagnostics=None,
            knowledge_base_settings=None,
        )
        # Should include history messages between system and user
        roles = [m["role"] for m in messages]
        assert "user" in roles[1:-1] or "assistant" in roles[1:-1]

    def test_build_messages_thinking_mode(self):
        service = self._make_service()
        messages = service._build_messages(
            question="分析一下",
            citations=[],
            assistant_mode="knowledge_qa",
            thinking_mode=True,
            conversation_history=None,
            retrieval_diagnostics=None,
            knowledge_base_settings=None,
        )
        user_content = messages[-1]["content"]
        assert "分析摘要" in user_content

    def test_build_messages_strategy_mode(self):
        service = self._make_service()
        messages = service._build_messages(
            question="写一个双均线策略",
            citations=[],
            assistant_mode="backtrader_strategy",
            thinking_mode=False,
            conversation_history=None,
            retrieval_diagnostics=None,
            knowledge_base_settings=None,
        )
        user_content = messages[-1]["content"]
        assert "backtrader_strategy" in user_content


class TestAIChatServiceContextBlocks:
    """Test context block building."""

    def test_empty_citations(self):
        result = AIChatService._build_context_blocks([])
        assert result == "无可用上下文"

    def test_single_citation(self):
        citations = [
            {
                "document_title": "Test Doc",
                "chunk_index": 0,
                "similarity": 0.9,
                "content": "Test content here",
            }
        ]
        result = AIChatService._build_context_blocks(citations)
        assert "Test Doc" in result
        assert "Test content here" in result
        assert "0.9" in result

    def test_citation_with_score_breakdown(self):
        citations = [
            {
                "document_title": "Doc",
                "chunk_index": 1,
                "similarity": 0.85,
                "content": "Content",
                "score_breakdown": {"semantic": 0.8, "keyword": 0.9},
            }
        ]
        result = AIChatService._build_context_blocks(citations)
        assert "打分明细" in result

    def test_max_8_citations(self):
        citations = [
            {"document_title": f"Doc{i}", "chunk_index": i, "similarity": 0.5, "content": f"c{i}"}
            for i in range(12)
        ]
        result = AIChatService._build_context_blocks(citations)
        # Should only include first 8
        assert "Doc7" in result
        assert "Doc8" not in result


class TestAIChatServiceDiagnostics:
    """Test diagnostics text building."""

    def test_none_diagnostics(self):
        result = AIChatService._build_diagnostics_text(None)
        assert result == "无诊断信息"

    def test_empty_diagnostics(self):
        result = AIChatService._build_diagnostics_text({})
        assert result == "无诊断信息"

    def test_valid_diagnostics(self):
        diag = {
            "retrieval_profile": "hybrid",
            "search_mode": "semantic",
            "search_query": "均线策略",
            "query_rewritten": True,
            "applied_top_k": 5,
            "applied_min_similarity": 0.7,
            "history_messages_used": 2,
            "indexed_documents": 10,
            "total_indexable_documents": 15,
            "coverage_ratio": 0.667,
        }
        result = AIChatService._build_diagnostics_text(diag)
        assert "hybrid" in result
        assert "semantic" in result
        assert "66.7%" in result


class TestAIChatServiceConversationMessages:
    """Test conversation history message building."""

    def test_empty_history(self):
        result = AIChatService._build_conversation_messages(None)
        assert result == []

    def test_history_trimmed_to_4(self):
        history = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = AIChatService._build_conversation_messages(history)
        assert len(result) <= 4

    def test_long_content_truncated(self):
        history = [
            {"role": "assistant", "content": "x" * 2000},
        ]
        result = AIChatService._build_conversation_messages(history)
        assert len(result[0]["content"]) <= 800

    def test_user_content_truncated(self):
        history = [
            {"role": "user", "content": "y" * 1000},
        ]
        result = AIChatService._build_conversation_messages(history)
        assert len(result[0]["content"]) <= 500

    def test_empty_content_skipped(self):
        history = [
            {"role": "user", "content": ""},
            {"role": "user", "content": "valid"},
        ]
        result = AIChatService._build_conversation_messages(history)
        assert len(result) == 1
        assert result[0]["content"] == "valid"


class TestAIChatServiceResolveEndpoint:
    """Test endpoint URL resolution."""

    def test_already_has_chat_completions(self):
        result = AIChatService._resolve_endpoint("http://api.example.com/v1/chat/completions")
        assert result == "http://api.example.com/v1/chat/completions"

    def test_appends_chat_completions(self):
        result = AIChatService._resolve_endpoint("http://api.example.com/v1")
        assert result == "http://api.example.com/v1/chat/completions"

    def test_strips_trailing_slash(self):
        result = AIChatService._resolve_endpoint("http://api.example.com/v1/")
        assert result == "http://api.example.com/v1/chat/completions"


class TestAIChatServiceExtractContent:
    """Test content extraction from API response."""

    def test_normal_response(self):
        body = {"choices": [{"message": {"content": "Hello world"}}]}
        result = AIChatService._extract_content(body)
        assert result == "Hello world"

    def test_empty_choices(self):
        body = {"choices": []}
        result = AIChatService._extract_content(body)
        assert result == ""

    def test_no_choices_key(self):
        body = {}
        result = AIChatService._extract_content(body)
        assert result == ""

    def test_content_is_list(self):
        body = {"choices": [{"message": {"content": [{"text": "part1"}, {"text": "part2"}]}}]}
        result = AIChatService._extract_content(body)
        assert "part1" in result
        assert "part2" in result

    def test_content_with_whitespace(self):
        body = {"choices": [{"message": {"content": "  trimmed  "}}]}
        result = AIChatService._extract_content(body)
        assert result == "trimmed"


class TestAIChatServiceExtractJsonObject:
    """Test JSON object extraction from content."""

    def test_plain_json(self):
        content = '{"key": "value"}'
        result = AIChatService._extract_json_object(content)
        assert result == '{"key": "value"}'

    def test_fenced_json(self):
        content = '```json\n{"key": "value"}\n```'
        result = AIChatService._extract_json_object(content)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_json_in_text(self):
        content = 'Some text before {"key": "value"} some text after'
        result = AIChatService._extract_json_object(content)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_no_json(self):
        content = "No JSON here at all"
        result = AIChatService._extract_json_object(content)
        assert result is None


class TestAIChatServiceGenerateAnswer:
    """Test the generate_answer method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self):
        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = False
            settings.AI_CHAT_BASE_URL = ""
            settings.AI_CHAT_API_KEY = ""
            settings.AI_CHAT_MODEL = ""
            mock_settings.return_value = settings
            service = AIChatService()
            result = await service.generate_answer(
                question="test",
                citations=[],
                assistant_mode="knowledge_qa",
                thinking_mode=False,
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_generate_answer_records_ai_call_log(self):
        from sqlalchemy import select

        from app.db.session_provider import unit_of_work
        from app.models.ai_call_log import AICallLog
        from app.services.ai_observability.logger import get_ai_call_log_sink

        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = "http://localhost:8000"
            settings.AI_CHAT_API_KEY = "sk-test-key"
            settings.AI_CHAT_MODEL = "gpt-4o-mini"
            mock_settings.return_value = settings
            service = AIChatService()
            service._call_provider = MagicMock(
                return_value={
                    "answer": "测试回答",
                    "tokens_used": 42,
                    "model_id": "gpt-4o-mini",
                    "strategy_draft": None,
                    "reasoning": None,
                }
            )

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

        assert result["answer"] == "测试回答"
        async with unit_of_work() as session:
            rows = (await session.execute(select(AICallLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].service_name == "ai_chat"
        assert rows[0].mode == "knowledge_qa"
        assert rows[0].model_name == "gpt-4o-mini"
        assert rows[0].total_tokens == 42
        assert rows[0].prompt_hash

    @pytest.mark.asyncio
    async def test_generate_answer_uses_ai_router_completion(self):
        from app.services.ai_router.router import ChatCompletionResponse

        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = "http://localhost:8000"
            settings.AI_CHAT_API_KEY = "sk-test-key"
            settings.AI_CHAT_MODEL = "gpt-4o-mini"
            settings.AI_CHAT_TIMEOUT = 30
            settings.AI_CHAT_TEMPERATURE = 0.2
            mock_settings.return_value = settings
            service = AIChatService()
            captured = {}

            async def fake_chat_completion(**kwargs):
                captured.update(kwargs)
                return ChatCompletionResponse(
                    content="路由层回答",
                    model="gpt-4o-mini",
                    provider="openai_compatible",
                    prompt_tokens=3,
                    completion_tokens=4,
                    total_tokens=7,
                )

            service.ai_router.chat_completion = fake_chat_completion

            result = await service.generate_answer(
                question="什么是均线策略？",
                citations=[],
                assistant_mode="knowledge_qa",
                thinking_mode=False,
            )

        assert result["answer"] == "路由层回答"
        assert result["tokens_used"] == 7
        assert result["model_id"] == "gpt-4o-mini"
        assert captured["model"] == "gpt-4o-mini"
        assert captured["provider"] == "openai_compatible"
        assert captured["base_url"] == "http://localhost:8000"
        assert captured["api_key"] == "sk-test-key"

    @pytest.mark.asyncio
    async def test_generate_answer_uses_saved_user_model_preference(self):
        from app.services.ai_router.preferences import ResolvedAIModelPreference
        from app.services.ai_router.router import ChatCompletionResponse

        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = ""
            settings.AI_CHAT_API_KEY = ""
            settings.AI_CHAT_MODEL = ""
            settings.AI_CHAT_TIMEOUT = 30
            settings.AI_CHAT_TEMPERATURE = 0.2
            mock_settings.return_value = settings
            service = AIChatService()
            service.budget_checker = AsyncMock()
            service._record_ai_call = AsyncMock()
            service.model_preference_service.resolve_model_key = MagicMock(return_value=None)
            service.model_preference_service.resolve_for_user = AsyncMock(
                return_value=ResolvedAIModelPreference(
                    provider="litellm",
                    model="ollama/qwen2.5-coder:7b",
                    base_url="http://localhost:11434",
                    api_key=None,
                )
            )
            captured = {}

            async def fake_chat_completion(**kwargs):
                captured.update(kwargs)
                return ChatCompletionResponse(
                    content="本地模型回答",
                    model="ollama/qwen2.5-coder:7b",
                    provider="litellm",
                    total_tokens=9,
                )

            service.ai_router.chat_completion = fake_chat_completion

            result = await service.generate_answer(
                question="什么是均线策略？",
                citations=[],
                assistant_mode="knowledge_qa",
                thinking_mode=False,
                user_id="user-1",
            )

        assert result["answer"] == "本地模型回答"
        assert captured["model"] == "ollama/qwen2.5-coder:7b"
        assert captured["provider"] == "litellm"
        assert captured["base_url"] == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_generate_answer_uses_session_model_override(self):
        from app.services.ai_router.router import ChatCompletionResponse

        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = ""
            settings.AI_CHAT_API_KEY = ""
            settings.AI_CHAT_MODEL = ""
            settings.AI_CHAT_TIMEOUT = 30
            settings.AI_CHAT_TEMPERATURE = 0.2
            mock_settings.return_value = settings
            service = AIChatService()
            service.budget_checker = AsyncMock()
            service._record_ai_call = AsyncMock()
            captured = {}

            async def fake_chat_completion(**kwargs):
                captured.update(kwargs)
                return ChatCompletionResponse(
                    content="会话模型回答",
                    model="ollama/llama3.1:8b",
                    provider="litellm",
                    total_tokens=8,
                )

            service.ai_router.chat_completion = fake_chat_completion

            result = await service.generate_answer(
                question="什么是均线策略？",
                citations=[],
                assistant_mode="knowledge_qa",
                thinking_mode=False,
                user_id="missing-user",
                model_id="ollama::ollama/llama3.1:8b",
            )

        assert result["answer"] == "会话模型回答"
        assert captured["model"] == "ollama/llama3.1:8b"
        assert captured["provider"] == "litellm"
        assert captured["base_url"] == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_generate_answer_blocks_provider_when_hard_budget_exceeded(self):
        from datetime import datetime, timezone

        from app.services.ai_observability.budget import AIBudgetExceededError

        with patch("app.services.ai_chat_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.AI_CHAT_ENABLED = True
            settings.AI_CHAT_BASE_URL = "http://localhost:8000"
            settings.AI_CHAT_API_KEY = "sk-test-key"
            settings.AI_CHAT_MODEL = "gpt-4o-mini"
            mock_settings.return_value = settings
            service = AIChatService()
            service._call_provider = MagicMock(return_value={"answer": "should not run"})

            async def deny_budget(*, user_id: str | None) -> None:
                assert user_id == "user-1"
                raise AIBudgetExceededError(
                    reason_code="budget_exceeded",
                    limit_usd=0.01,
                    used_usd=0.02,
                    reset_at=datetime.now(timezone.utc),
                )

            service.budget_checker = deny_budget

            with pytest.raises(AIBudgetExceededError):
                await service.generate_answer(
                    question="什么是均线策略？",
                    citations=[],
                    assistant_mode="knowledge_qa",
                    thinking_mode=False,
                    user_id="user-1",
                )

        service._call_provider.assert_not_called()
