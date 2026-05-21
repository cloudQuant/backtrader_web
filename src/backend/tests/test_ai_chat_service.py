"""Tests for AIChatService - AI chat provider integration."""

import json
from unittest.mock import MagicMock, patch

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
        history = [
            {"role": "user", "content": f"msg{i}"} for i in range(10)
        ]
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
        body = {
            "choices": [{"message": {"content": "Hello world"}}]
        }
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
        body = {
            "choices": [
                {"message": {"content": [{"text": "part1"}, {"text": "part2"}]}}
            ]
        }
        result = AIChatService._extract_content(body)
        assert "part1" in result
        assert "part2" in result

    def test_content_with_whitespace(self):
        body = {
            "choices": [{"message": {"content": "  trimmed  "}}]
        }
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
