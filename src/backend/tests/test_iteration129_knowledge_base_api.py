"""Iteration 129 knowledge base API tests."""

import uuid
from types import SimpleNamespace

from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.knowledge_base import ChatConversation, ChatMessage, DocumentChunk


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


class TestIteration129RouterRegistration:
    """Optional router registration tests for iteration 129."""

    def test_knowledge_base_optional_router_registered(self):
        from app.api.router import api_router

        routes = [
            route
            for route in api_router.routes
            if getattr(route, "path", "").startswith("/knowledge-base")
        ]
        http_routes = [route for route in routes if getattr(route, "methods", None)]

        assert routes
        assert http_routes
        assert all("Knowledge Base" in getattr(route, "tags", []) for route in http_routes)


class TestIteration129KnowledgeBaseAPI:
    """Knowledge base CRUD tests."""

    async def test_create_and_list_knowledge_bases(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={
                "name": "量化知识库",
                "description": "用于迭代129测试",
                "is_public": False,
            },
        )

        assert create_resp.status_code == 201, create_resp.text
        created = create_resp.json()
        assert created["id"]
        assert created["name"] == "量化知识库"
        assert created["document_count"] == 0

        list_resp = await client.get("/api/v1/knowledge-base/", headers=auth_headers)
        assert list_resp.status_code == 200, list_resp.text
        payload = list_resp.json()
        assert payload["total"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["id"] == created["id"]

    async def test_knowledge_base_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/knowledge-base/")
        assert resp.status_code == 401

    async def test_create_and_list_documents_under_knowledge_base(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "文档知识库", "description": "文档测试", "is_public": False},
        )
        assert kb_resp.status_code == 201, kb_resp.text
        kb_id = kb_resp.json()["id"]

        doc_resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "双均线策略",
                "content": "# 双均线策略\n\n策略说明",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc_resp.status_code == 201, doc_resp.text
        created_doc = doc_resp.json()
        assert created_doc["knowledge_base_id"] == kb_id
        assert created_doc["title"] == "双均线策略"
        assert created_doc["index_status"] == "not_indexed"

        list_resp = await client.get(
            f"/api/v1/knowledge-base/{kb_id}/documents/", headers=auth_headers
        )
        assert list_resp.status_code == 200, list_resp.text
        payload = list_resp.json()
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == created_doc["id"]
        assert "content" not in payload["items"][0]
        assert payload["items"][0]["has_content"] is False
        assert payload["items"][0]["content_length"] == 0

        detail_resp = await client.get(
            f"/api/v1/knowledge-base/{kb_id}/documents/{created_doc['id']}",
            headers=auth_headers,
        )
        assert detail_resp.status_code == 200, detail_resp.text
        assert detail_resp.json()["content"] == "# 双均线策略\n\n策略说明"

        kb_detail = await client.get(f"/api/v1/knowledge-base/{kb_id}", headers=auth_headers)
        assert kb_detail.status_code == 200, kb_detail.text
        assert kb_detail.json()["document_count"] == 1

    async def test_rejects_parent_from_another_knowledge_base(
        self, client: AsyncClient, auth_headers: dict
    ):
        first = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "父级库", "description": None, "is_public": False},
        )
        assert first.status_code == 201, first.text
        first_id = first.json()["id"]
        folder = await client.post(
            f"/api/v1/knowledge-base/{first_id}/documents/",
            headers=auth_headers,
            json={
                "title": "外部文件夹",
                "content": None,
                "content_type": "markdown",
                "is_folder": True,
            },
        )
        assert folder.status_code == 201, folder.text

        second = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "子级库", "description": None, "is_public": False},
        )
        assert second.status_code == 201, second.text

        resp = await client.post(
            f"/api/v1/knowledge-base/{second.json()['id']}/documents/",
            headers=auth_headers,
            json={
                "title": "错误子文档",
                "content": "content",
                "content_type": "markdown",
                "is_folder": False,
                "parent_id": folder.json()["id"],
            },
        )
        assert resp.status_code == 400

    async def test_rejects_child_under_non_folder_parent(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "父节点类型库", "description": None, "is_public": False},
        )
        assert kb.status_code == 201, kb.text
        kb_id = kb.json()["id"]
        parent = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "普通文档",
                "content": "content",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert parent.status_code == 201, parent.text

        resp = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "子文档",
                "content": "content",
                "content_type": "markdown",
                "is_folder": False,
                "parent_id": parent.json()["id"],
            },
        )
        assert resp.status_code == 400

    async def test_rejects_document_parent_cycle_on_update(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "循环检测库", "description": None, "is_public": False},
        )
        assert kb.status_code == 201, kb.text
        kb_id = kb.json()["id"]
        root = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "根文件夹",
                "content": None,
                "content_type": "markdown",
                "is_folder": True,
            },
        )
        assert root.status_code == 201, root.text
        child = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "子文件夹",
                "content": None,
                "content_type": "markdown",
                "is_folder": True,
                "parent_id": root.json()["id"],
            },
        )
        assert child.status_code == 201, child.text

        resp = await client.put(
            f"/api/v1/knowledge-base/{kb_id}/documents/{root.json()['id']}",
            headers=auth_headers,
            json={"parent_id": child.json()["id"]},
        )
        assert resp.status_code == 400

    async def test_non_owner_cannot_access_document(self, client: AsyncClient, auth_headers: dict):
        other_headers = await _register_and_login(client)
        kb = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "私有库", "description": None, "is_public": False},
        )
        assert kb.status_code == 201, kb.text
        kb_id = kb.json()["id"]
        doc = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "私有文档",
                "content": "secret",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc.status_code == 201, doc.text

        resp = await client.get(
            f"/api/v1/knowledge-base/{kb_id}/documents/{doc.json()['id']}",
            headers=other_headers,
        )
        assert resp.status_code == 404

    async def test_public_knowledge_base_is_readable_by_non_owner(
        self, client: AsyncClient, auth_headers: dict
    ):
        other_headers = await _register_and_login(client)
        kb = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "公开库", "description": None, "is_public": True},
        )
        assert kb.status_code == 201, kb.text
        kb_id = kb.json()["id"]
        doc = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "公开文档",
                "content": "public content",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc.status_code == 201, doc.text

        list_resp = await client.get("/api/v1/knowledge-base/", headers=other_headers)
        assert list_resp.status_code == 200, list_resp.text
        assert any(item["id"] == kb_id for item in list_resp.json()["items"])

        doc_resp = await client.get(
            f"/api/v1/knowledge-base/{kb_id}/documents/{doc.json()['id']}",
            headers=other_headers,
        )
        assert doc_resp.status_code == 200, doc_resp.text
        assert doc_resp.json()["title"] == "公开文档"

        update_resp = await client.put(
            f"/api/v1/knowledge-base/{kb_id}",
            headers=other_headers,
            json={"name": "非 owner 不可改"},
        )
        assert update_resp.status_code == 404

    async def test_delete_knowledge_base_cascades_chat_and_chunks(
        self, client: AsyncClient, auth_headers: dict
    ):
        kb = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "级联删除库", "description": None, "is_public": False},
        )
        assert kb.status_code == 201, kb.text
        kb_id = kb.json()["id"]
        doc = await client.post(
            f"/api/v1/knowledge-base/{kb_id}/documents/",
            headers=auth_headers,
            json={
                "title": "级联文档",
                "content": "级联删除测试 chunk 和会话都应该被清理。",
                "content_type": "markdown",
                "is_folder": False,
            },
        )
        assert doc.status_code == 201, doc.text

        index_resp = await client.post(
            "/api/v1/rag/index",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "document_id": doc.json()["id"],
                "force_reindex": False,
            },
        )
        assert index_resp.status_code == 200, index_resp.text
        chat_resp = await client.post(
            "/api/v1/kb-chat/send",
            headers=auth_headers,
            json={
                "knowledge_base_id": kb_id,
                "question": "级联删除测试是什么？",
                "assistant_mode": "knowledge_qa",
            },
        )
        assert chat_resp.status_code == 200, chat_resp.text
        conversation_id = chat_resp.json()["conversation_id"]

        delete_resp = await client.delete(f"/api/v1/knowledge-base/{kb_id}", headers=auth_headers)
        assert delete_resp.status_code == 200, delete_resp.text

        async with async_session_maker() as session:
            chunk_count = (
                await session.execute(
                    select(func.count())
                    .select_from(DocumentChunk)
                    .where(DocumentChunk.knowledge_base_id == kb_id)
                )
            ).scalar_one()
            conversation_count = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatConversation)
                    .where(ChatConversation.knowledge_base_id == kb_id)
                )
            ).scalar_one()
            message_count = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.conversation_id == conversation_id)
                )
            ).scalar_one()

        assert chunk_count == 0
        assert conversation_count == 0
        assert message_count == 0

    def test_source_file_path_uses_backend_data_root(self, monkeypatch, tmp_path):
        from app.api import knowledge_base as kb_api

        source_root = tmp_path / "reqdocs_source_files"
        source_root.mkdir()
        source_file = source_root / "sample.pdf"
        source_file.write_bytes(b"%PDF")
        monkeypatch.setattr(
            kb_api, "get_backend_data_path", lambda *parts: tmp_path.joinpath(*parts), raising=False
        )

        result = kb_api._get_source_file_path(
            SimpleNamespace(
                metadata_json={
                    "reqdocs_source_file_path": str(source_file),
                    "reqdocs_source_mime_type": "application/pdf",
                }
            )
        )

        assert result == (source_file.resolve(), "application/pdf")

    async def test_knowledge_base_returns_default_settings_and_accepts_partial_update(
        self, client: AsyncClient, auth_headers: dict
    ):
        create_resp = await client.post(
            "/api/v1/knowledge-base/",
            headers=auth_headers,
            json={"name": "检索配置库", "description": None, "is_public": False},
        )
        assert create_resp.status_code == 201, create_resp.text
        created = create_resp.json()
        assert created["settings"]["retrieval_profile"] == "quant_research"
        assert created["settings"]["search_mode"] == "hybrid"
        assert created["settings"]["default_top_k"] == 8
        assert created["settings"]["use_conversation_memory"] is True

        update_resp = await client.put(
            f"/api/v1/knowledge-base/{created['id']}",
            headers=auth_headers,
            json={
                "settings": {
                    "retrieval_profile": "precision",
                    "default_top_k": 5,
                    "use_conversation_memory": False,
                }
            },
        )
        assert update_resp.status_code == 200, update_resp.text
        updated = update_resp.json()
        assert updated["settings"]["retrieval_profile"] == "precision"
        assert updated["settings"]["default_top_k"] == 5
        assert updated["settings"]["use_conversation_memory"] is False
        assert updated["settings"]["search_mode"] == "hybrid"
