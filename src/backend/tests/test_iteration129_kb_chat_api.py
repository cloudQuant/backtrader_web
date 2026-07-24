"""Iteration 129 KB chat API tests."""

import uuid

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient) -> dict:
    username = f"user_{uuid.uuid4().hex[:8]}"
    password = "Test12345678"
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": password,
        },
    )
    assert reg.status_code == 200, reg.text
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "username": username,
            "password": password,
        },
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


class TestIteration129KBChatAPI:
    """Conversation management tests."""

    async def test_create_and_list_conversations(self, client: AsyncClient, auth_headers: dict):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "会话测试库", "description": "用于会话测试", "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        create_resp = await client.post(
            "/api/v1/kb-chat/conversations",
            headers=auth_headers,
            json={"knowledge_base_id": kb_id, "title": "新对话", "model_id": None},
        )
        assert create_resp.status_code == 201, create_resp.text
        conversation = create_resp.json()
        assert conversation["knowledge_base_id"] == kb_id
        assert conversation["title"] == "新对话"

        list_resp = await client.get(
            "/api/v1/kb-chat/conversations",
            headers=auth_headers,
            params={"knowledge_base_id": kb_id},
        )
        assert list_resp.status_code == 200, list_resp.text
        payload = list_resp.json()
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == conversation["id"]

    async def test_create_conversation_rejects_blank_title(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "空标题会话库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text

        create_resp = await client.post(
            "/api/v1/kb-chat/conversations",
            headers=auth_headers,
            json={"knowledge_base_id": kb_resp.json()["id"], "title": "   ", "model_id": None},
        )
        assert create_resp.status_code == 422, create_resp.text

    async def test_public_knowledge_base_is_available_for_other_user_chat(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "共享量化知识库", "description": None, "is_public": True},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "共享风控规则",
                "content": "共享知识库中的 ATR 止损可用于控制单笔风险。",
                "content_type": "markdown",
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text
        index_resp = await client.post(
            "/api/v1/rag/index",
            headers=auth_headers,
            json={"knowledge_base_id": kb_id, "document_id": doc_resp.json()["id"]},
        )
        assert index_resp.status_code == 200, index_resp.text

        other_headers = await _register_and_login(client)
        list_resp = await client.get("/api/v1/knowledge-base/?limit=100", headers=other_headers)
        assert list_resp.status_code == 200, list_resp.text
        assert any(item["id"] == kb_id for item in list_resp.json()["items"])

        send_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=other_headers,
            json={"knowledge_base_id": kb_id, "question": "ATR 止损有什么作用？"},
        )
        assert send_resp.status_code == 200, send_resp.text
        assert send_resp.json()["citations"][0]["document_id"] == doc_resp.json()["id"]

    async def test_send_history_and_delete_conversation(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "发送测试库", "description": "用于发送消息", "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "双均线策略",
                "content": "双均线策略在短期均线上穿长期均线时开仓。",
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

        send_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={"knowledge_base_id": kb_id, "question": "开仓条件是什么？"},
        )
        assert send_resp.status_code == 200, send_resp.text
        send_body = send_resp.json()
        assert send_body["conversation_id"]
        assert "开仓" in send_body["answer"]

        history_resp = await client.get(
            f"/api/v1/kb-chat/history/{send_body['conversation_id']}",
            headers=auth_headers,
        )
        assert history_resp.status_code == 200, history_resp.text
        history_body = history_resp.json()
        assert history_body["conversation_id"] == send_body["conversation_id"]
        assert len(history_body["messages"]) == 2
        assert history_body["messages"][0]["role"] == "user"
        assert history_body["messages"][1]["role"] == "assistant"

        delete_resp = await client.delete(
            f"/api/v1/kb-chat/conversations/{send_body['conversation_id']}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == 200, delete_resp.text

    async def test_send_auto_indexes_unindexed_documents(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "自动索引测试库", "description": "用于直接问答", "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "ATR 风控",
                "content": "ATR 止损通常使用最近波动幅度控制单笔交易风险。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text
        assert doc_resp.json()["index_status"] == "not_indexed"

        send_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={"knowledge_base_id": kb_id, "question": "ATR 止损有什么作用？"},
        )
        assert send_resp.status_code == 200, send_resp.text
        send_body = send_resp.json()
        assert send_body["context_chunks_used"] >= 1
        assert send_body["citations"][0]["document_id"] == doc_resp.json()["id"]
        assert "ATR" in send_body["answer"]
        assert send_body["reason_code"] == "ai_not_configured"
        assert "未配置" in send_body["diagnostic_message"]

    async def test_send_knowledge_base_overview_lists_documents_without_keyword_match(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "比赛资料库", "description": "用于赛前准备", "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "双均线策略说明",
                "content": "短期均线上穿长期均线时开仓，并通过 ATR 控制风险。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text

        send_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "这个知识库主要包含哪些内容？",
            },
        )

        assert send_resp.status_code == 200, send_resp.text
        payload = send_resp.json()
        assert "双均线策略说明" in payload["answer"]
        assert payload["context_chunks_used"] >= 1
        assert payload["citations"][0]["document_id"] == doc_resp.json()["id"]
        assert payload["reason_code"] == "knowledge_base_overview"
        assert "未找到相关内容" not in payload["answer"]

    async def test_send_document_recommendation_lists_documents_without_keyword_match(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "阅读推荐资料库", "description": "用于阅读推荐", "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "双均线策略说明",
                "content": "短期均线上穿长期均线时开仓，并通过 ATR 控制风险。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text

        send_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "有哪些值得重点阅读的文档？",
            },
        )

        assert send_resp.status_code == 200, send_resp.text
        payload = send_resp.json()
        assert "双均线策略说明" in payload["answer"]
        assert payload["context_chunks_used"] >= 1
        assert payload["citations"][0]["document_id"] == doc_resp.json()["id"]
        assert payload["reason_code"] == "knowledge_base_overview"
        assert "未找到相关内容" not in payload["answer"]

    async def test_send_empty_knowledge_base_overview_explains_how_to_populate_it(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "空资料库", "description": "尚未上传资料", "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text

        send_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_resp.json()["id"],
                "question": "这个知识库主要包含哪些内容？",
            },
        )

        assert send_resp.status_code == 200, send_resp.text
        payload = send_resp.json()
        assert payload["reason_code"] == "knowledge_base_overview"
        assert "还没有可供概览的文档" in payload["answer"]

    async def test_send_backtrader_strategy_returns_structured_draft(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "策略生成测试库", "description": "用于 AI 生成策略", "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "趋势策略模板",
                "content": "趋势策略通常结合均线、ATR 止损和突破确认。",
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

        send_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "请生成一个双均线突破并结合 ATR 止损的 Backtrader 策略",
                "assistant_mode": "backtrader_strategy",
            },
        )
        assert send_resp.status_code == 200, send_resp.text
        payload = send_resp.json()
        assert payload["assistant_mode"] == "backtrader_strategy"
        assert payload["strategy_draft"] is not None
        assert payload["strategy_draft"]["name"]
        assert "class" in payload["strategy_draft"]["code"]
        assert payload["strategy_draft"]["params"]

    async def test_send_backtrader_strategy_does_not_require_knowledge_base(
        self, client: AsyncClient, auth_headers: dict
    ):
        send_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={
                "question": "请生成一个双均线突破并结合 ATR 止损的 Backtrader 策略",
                "assistant_mode": "backtrader_strategy",
            },
        )
        assert send_resp.status_code == 200, send_resp.text
        payload = send_resp.json()
        assert payload["assistant_mode"] == "backtrader_strategy"
        assert payload["context_chunks_used"] == 0
        assert payload["citations"] == []
        assert payload["strategy_draft"] is not None
        assert "class" in payload["strategy_draft"]["code"]

        history_resp = await client.get(
            f"/api/v1/kb-chat/history/{payload['conversation_id']}",
            headers=auth_headers,
        )
        assert history_resp.status_code == 200, history_resp.text
        history_body = history_resp.json()
        assert len(history_body["messages"]) == 2
        assistant_message = history_body["messages"][1]
        assert assistant_message["assistant_mode"] == "backtrader_strategy"
        assert assistant_message["strategy_draft"] is not None
        assert "class" in assistant_message["strategy_draft"]["code"]

        list_resp = await client.get("/api/v1/kb-chat/conversations", headers=auth_headers)
        assert list_resp.status_code == 200, list_resp.text
        list_body = list_resp.json()
        assert any(item["id"] == payload["conversation_id"] for item in list_body["items"])

    async def test_send_rejects_conversation_from_different_knowledge_base(
        self, client: AsyncClient, auth_headers: dict
    ):
        first = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "会话所属库", "description": None, "is_public": False},
        )
        assert first.status_code == 201, first.text
        second = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "错误请求库", "description": None, "is_public": False},
        )
        assert second.status_code == 201, second.text
        first_id = first.json()["id"]
        second_id = second.json()["id"]

        conversation_resp = await client.post(
            "/api/v1/kb-chat/conversations",
            headers=auth_headers,
            json={"knowledge_base_id": first_id, "title": "固定会话", "model_id": None},
        )
        assert conversation_resp.status_code == 201, conversation_resp.text

        send_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={
                "knowledge_base_id": second_id,
                "conversation_id": conversation_resp.json()["id"],
                "question": "这条消息不能写入另一个知识库的会话",
            },
        )
        assert send_resp.status_code == 404

    async def test_send_rejects_invalid_question_payload(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "问题校验库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        blank_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={"knowledge_base_id": kb_id, "question": "   "},
        )
        assert blank_resp.status_code == 422, blank_resp.text

        too_long_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={"knowledge_base_id": kb_id, "question": "x" * 2001},
        )
        assert too_long_resp.status_code == 422, too_long_resp.text

    async def test_other_user_cannot_read_conversation_history(
        self, client: AsyncClient, auth_headers: dict
    ):
        other_headers = await _register_and_login(client)
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "私有会话库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        conversation_resp = await client.post(
            "/api/v1/kb-chat/conversations",
            headers=auth_headers,
            json={"knowledge_base_id": kb_resp.json()["id"], "title": "私有会话", "model_id": None},
        )
        assert conversation_resp.status_code == 201, conversation_resp.text

        history_resp = await client.get(
            f"/api/v1/kb-chat/history/{conversation_resp.json()['id']}",
            headers=other_headers,
        )
        assert history_resp.status_code == 404

    async def test_follow_up_question_uses_conversation_aware_query_rewrite(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "会话改写库", "description": None, "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "双均线风控说明",
                "content": "双均线策略通常结合 ATR 止损、单笔风险限制和样本外验证。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text

        first_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "请总结双均线策略的核心思路",
            },
        )
        assert first_resp.status_code == 200, first_resp.text
        conversation_id = first_resp.json()["conversation_id"]

        follow_up_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "conversation_id": conversation_id,
                "question": "那风控呢？",
            },
        )
        assert follow_up_resp.status_code == 200, follow_up_resp.text
        payload = follow_up_resp.json()
        assert payload["citations"][0]["document_id"] == doc_resp.json()["id"]
        assert payload["diagnostics"]["query_rewritten"] is True
        assert "历史问题" in payload["diagnostics"]["search_query"]
