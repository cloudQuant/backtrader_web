"""Iteration 129 RAG API tests."""

from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.knowledge_base import DocumentChunk
from app.services.ai_chat_service import AIChatService


class TestIteration129RAGAPI:
    """Minimal RAG flow tests."""

    async def test_index_search_and_ask_flow(self, client: AsyncClient, auth_headers: dict):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "RAG测试库", "description": "用于RAG接口测试", "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "双均线策略",
                "content": "双均线策略在短期均线上穿长期均线时开仓，在下穿时平仓。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text
        doc_id = doc_resp.json()["id"]

        index_resp = await client.post(
            "/api/v1/rag/index",
            headers=auth_headers,
            json={"knowledge_base_id": kb_id, "document_id": doc_id, "force_reindex": False},
        )
        assert index_resp.status_code == 200, index_resp.text
        assert index_resp.json()["status"] == "indexed"
        assert index_resp.json()["chunks_count"] >= 1

        search_resp = await client.post(
            "/api/v1/rag/search",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "query": "开仓条件",
                "top_k": 5,
                "min_similarity": 0.0,
                "search_mode": "keyword",
            },
        )
        assert search_resp.status_code == 200, search_resp.text
        search_payload = search_resp.json()
        assert search_payload["total"] >= 1
        assert search_payload["results"][0]["document_id"] == doc_id

        ask_resp = await client.post(
            "/api/v1/rag/ask",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "双均线策略的开仓条件是什么？",
                "top_k": 5,
                "min_similarity": 0.0,
                "include_citations": True,
            },
        )
        assert ask_resp.status_code == 200, ask_resp.text
        ask_payload = ask_resp.json()
        assert "开仓" in ask_payload["answer"]
        assert ask_payload["context_chunks_used"] >= 1
        assert len(ask_payload["citations"]) >= 1

    async def test_ask_empty_knowledge_base_returns_empty_answer(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "空知识库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text

        ask_resp = await client.post(
            "/api/v1/rag/ask",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_resp.json()["id"],
                "question": "这里有什么内容？",
                "top_k": 5,
                "min_similarity": 0.1,
                "include_citations": True,
            },
        )

        assert ask_resp.status_code == 200, ask_resp.text
        payload = ask_resp.json()
        assert payload["context_chunks_used"] == 0
        assert payload["citations"] == []
        assert payload["reason_code"] == "no_context_found"
        assert "未找到" in payload["diagnostic_message"]
        assert "未找到" in payload["answer"]

    async def test_search_and_ask_reject_blank_query_payloads(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "空白查询校验库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        search_resp = await client.post(
            "/api/v1/rag/search",
            headers=auth_headers,
            json={"knowledge_base_id": kb_id, "query": "   "},
        )
        assert search_resp.status_code == 422, search_resp.text

        ask_resp = await client.post(
            "/api/v1/rag/ask",
            headers=auth_headers,
            json={"knowledge_base_id": kb_id, "question": "   "},
        )
        assert ask_resp.status_code == 422, ask_resp.text

    async def test_index_empty_document_reports_not_indexed(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "空文档索引状态库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]
        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "空内容文档",
                "content": "   ",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text

        index_resp = await client.post(
            "/api/v1/rag/index",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "document_id": doc_resp.json()["id"],
                "force_reindex": False,
            },
        )

        assert index_resp.status_code == 200, index_resp.text
        payload = index_resp.json()
        assert payload["chunks_count"] == 0
        assert payload["status"] == "not_indexed"

    async def test_ai_provider_failure_uses_accurate_fallback_message(
        self, client: AsyncClient, auth_headers: dict, monkeypatch
    ):
        async def fake_generate_answer(self, **kwargs):
            return None

        async def fake_can_generate(self, **kwargs):
            return True

        monkeypatch.setattr(AIChatService, "is_enabled", lambda self: True)
        monkeypatch.setattr(AIChatService, "can_generate", fake_can_generate)
        monkeypatch.setattr(AIChatService, "generate_answer", fake_generate_answer)

        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "AI失败提示库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]
        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "模型失败资料",
                "content": "PROVIDER_FAIL_TOKEN 表示模型调用失败时仍应返回可用引用。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text

        ask_resp = await client.post(
            "/api/v1/rag/ask",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "PROVIDER_FAIL_TOKEN",
                "top_k": 5,
                "min_similarity": 0.1,
            },
        )

        assert ask_resp.status_code == 200, ask_resp.text
        payload = ask_resp.json()
        assert "AI 模型调用失败" in payload["answer"]
        assert payload["reason_code"] == "ai_provider_failed"
        assert "AI 模型调用失败" in payload["diagnostic_message"]
        assert "未配置生成式 AI 模型" not in payload["answer"]

    async def test_ai_not_configured_uses_diagnostic_reason_code(
        self, client: AsyncClient, auth_headers: dict, monkeypatch
    ):
        async def fake_generate_answer(self, **kwargs):
            return None

        monkeypatch.setattr(AIChatService, "is_enabled", lambda self: False)
        monkeypatch.setattr(AIChatService, "generate_answer", fake_generate_answer)

        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "AI未配置提示库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]
        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "模型未配置资料",
                "content": "AI_DISABLED_TOKEN 表示模型未配置时仍应返回知识库片段。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text

        ask_resp = await client.post(
            "/api/v1/rag/ask",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "AI_DISABLED_TOKEN",
                "top_k": 5,
                "min_similarity": 0.1,
            },
        )

        assert ask_resp.status_code == 200, ask_resp.text
        payload = ask_resp.json()
        assert payload["reason_code"] == "ai_not_configured"
        assert "未配置" in payload["diagnostic_message"]

    async def test_auto_index_skips_folders_and_empty_documents(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "文件夹跳过库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        folder_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "隐藏文件夹",
                "content": "FOLDER_ONLY_TOKEN",
                "content_type": "markdown",
                "is_folder": True,
            },
        )
        assert folder_resp.status_code == 201, folder_resp.text
        empty_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "空文档",
                "content": "",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert empty_resp.status_code == 201, empty_resp.text
        normal_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "有效文档",
                "content": "VALID_RAG_TOKEN 表示有效索引内容。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert normal_resp.status_code == 201, normal_resp.text

        folder_search = await client.post(
            "/api/v1/rag/search",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "query": "FOLDER_ONLY_TOKEN",
                "top_k": 5,
                "min_similarity": 0.1,
                "search_mode": "keyword",
            },
        )
        assert folder_search.status_code == 200, folder_search.text
        assert folder_search.json()["total"] == 0

        normal_search = await client.post(
            "/api/v1/rag/search",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "query": "VALID_RAG_TOKEN",
                "top_k": 5,
                "min_similarity": 0.1,
                "search_mode": "keyword",
            },
        )
        assert normal_search.status_code == 200, normal_search.text
        assert normal_search.json()["total"] == 1

    async def test_auto_index_does_not_duplicate_existing_chunks(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "重复索引库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]
        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "重复索引文档",
                "content": "DEDUP_RAG_TOKEN 用于验证自动索引不会重复创建 chunk。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text
        doc_id = doc_resp.json()["id"]

        for _ in range(2):
            ask_resp = await client.post(
                "/api/v1/rag/ask",
                headers=auth_headers,
                json={
                    "knowledge_base_id": kb_id,
                    "question": "DEDUP_RAG_TOKEN",
                    "top_k": 5,
                    "min_similarity": 0.1,
                    "include_citations": True,
                },
            )
            assert ask_resp.status_code == 200, ask_resp.text

        async with async_session_maker() as session:
            chunk_count = (
                await session.execute(
                    select(func.count())
                    .select_from(DocumentChunk)
                    .where(DocumentChunk.document_id == doc_id)
                )
            ).scalar_one()

        assert chunk_count == 1

    async def test_updated_document_removes_stale_chunks(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "旧 chunk 清理库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]
        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "可更新文档",
                "content": "OLD_RAG_TOKEN 是旧内容。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text
        doc_id = doc_resp.json()["id"]

        first_ask = await client.post(
            "/api/v1/rag/ask",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "OLD_RAG_TOKEN",
                "top_k": 5,
                "min_similarity": 0.1,
                "include_citations": True,
            },
        )
        assert first_ask.status_code == 200, first_ask.text
        assert first_ask.json()["context_chunks_used"] == 1

        update_resp = await client.put(
            f"/api/v1/knowledge-base/{kb_id}/documents/{doc_id}",
            headers=auth_headers,
            json={"content": "NEW_RAG_TOKEN 是新内容。"},
        )
        assert update_resp.status_code == 200, update_resp.text
        assert update_resp.json()["index_status"] == "not_indexed"

        new_ask = await client.post(
            "/api/v1/rag/ask",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "NEW_RAG_TOKEN",
                "top_k": 5,
                "min_similarity": 0.1,
                "include_citations": True,
            },
        )
        assert new_ask.status_code == 200, new_ask.text
        assert new_ask.json()["context_chunks_used"] == 1

        stale_search = await client.post(
            "/api/v1/rag/search",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "query": "OLD_RAG_TOKEN",
                "top_k": 5,
                "min_similarity": 0.1,
                "search_mode": "keyword",
            },
        )
        assert stale_search.status_code == 200, stale_search.text
        assert stale_search.json()["total"] == 0

    async def test_search_and_ask_return_retrieval_diagnostics(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={
                "name": "诊断检索库",
                "description": None,
                "is_public": False,
                "settings": {
                    "retrieval_profile": "precision",
                    "default_top_k": 4,
                    "min_similarity": 0.05,
                },
            },
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "风险控制模板",
                "content": "DIAGNOSTIC_RAG_TOKEN 用于验证检索诊断字段。ATR 止损用于控制波动风险。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text

        search_resp = await client.post(
            "/api/v1/rag/search",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "query": "DIAGNOSTIC_RAG_TOKEN",
                "top_k": 4,
                "min_similarity": 0.05,
                "search_mode": "hybrid",
            },
        )
        assert search_resp.status_code == 200, search_resp.text
        search_payload = search_resp.json()
        assert search_payload["diagnostics"]["retrieval_profile"] == "precision"
        assert search_payload["diagnostics"]["search_mode"] == "hybrid"
        assert search_payload["diagnostics"]["applied_top_k"] == 4
        assert search_payload["diagnostics"]["indexed_documents"] >= 1

        ask_resp = await client.post(
            "/api/v1/rag/ask",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "DIAGNOSTIC_RAG_TOKEN",
                "top_k": 4,
                "min_similarity": 0.05,
                "thinking_mode": True,
            },
        )
        assert ask_resp.status_code == 200, ask_resp.text
        ask_payload = ask_resp.json()
        assert ask_payload["diagnostics"]["search_query"] == "DIAGNOSTIC_RAG_TOKEN"
        assert ask_payload["diagnostics"]["query_rewritten"] is False
