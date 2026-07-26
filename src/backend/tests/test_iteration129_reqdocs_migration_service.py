"""Tests for ReqDocs structured data migration service."""

import pytest


class TestReqDocsMigrationService:
    """MySQL structured data migration tests."""

    @pytest.mark.asyncio
    async def test_migrate_structured_entities_preserves_links(self):
        from sqlalchemy import select

        from app.db.database import async_session_maker
        from app.models.knowledge_base import (
            ChatConversation,
            ChatMessage,
            KBDocument,
            KnowledgeBase,
        )
        from app.services.reqdocs_migration_service import ReqDocsMigrationService

        service = ReqDocsMigrationService()
        payload = {
            "projects": [
                {
                    "id": 2,
                    "name": "用户手册",
                    "description": "大类资产投研平台的用户手册",
                    "created_at": None,
                    "updated_at": None,
                    "current_version": "2.0.0",
                }
            ],
            "documents": [
                {
                    "id": 302,
                    "project_id": 2,
                    "title": "迭代6_信用债测试用例样板",
                    "status": "draft",
                    "is_folder": 0,
                    "parent_id": None,
                    "sort_order": 0,
                    "path": "/docs/迭代6_信用债测试用例.md",
                    "current_version": "1.0.1",
                    "type": "requirement",
                    "created_at": None,
                    "updated_at": None,
                }
            ],
            "kb_conversations": [
                {
                    "id": 1,
                    "knowledge_base_id": 2,
                    "title": "现在用户手册中的主要内容都有什么",
                    "created_by": 1,
                    "created_at": None,
                    "updated_at": None,
                }
            ],
            "kb_chat_messages": [
                {
                    "id": 1,
                    "conversation_id": 1,
                    "role": "user",
                    "content": "现在用户手册中的主要内容都有什么",
                    "model": "deepseek-chat",
                    "created_at": None,
                },
                {
                    "id": 2,
                    "conversation_id": 1,
                    "role": "assistant",
                    "content": "当前用户手册主要包含若干章节。",
                    "model": "deepseek-chat",
                    "created_at": None,
                },
            ],
        }

        result = await service.migrate_from_structured_data("owner-1", payload)

        assert result["knowledge_bases"] == 1
        assert result["documents"] == 1
        assert result["conversations"] == 1
        assert result["messages"] == 2

        async with async_session_maker() as session:
            kb = (await session.execute(select(KnowledgeBase))).scalar_one()
            doc = (await session.execute(select(KBDocument))).scalar_one()
            conv = (await session.execute(select(ChatConversation))).scalar_one()
            messages = (
                (await session.execute(select(ChatMessage).order_by(ChatMessage.created_at.asc())))
                .scalars()
                .all()
            )

            assert kb.name == "用户手册"
            assert kb.is_public is True
            assert doc.knowledge_base_id == kb.id
            assert conv.knowledge_base_id == kb.id
            assert len(messages) == 2
            assert messages[0].conversation_id == conv.id
            assert messages[1].conversation_id == conv.id

    @pytest.mark.asyncio
    async def test_migrate_prefers_markdown_contents_and_persists_source_file(
        self, tmp_path, monkeypatch
    ):
        from sqlalchemy import select

        from app.db.database import async_session_maker
        from app.models.knowledge_base import KBDocument
        from app.services.reqdocs_migration_service import ReqDocsMigrationService

        monkeypatch.setattr(ReqDocsMigrationService, "SOURCE_FILE_DIR", tmp_path)
        service = ReqDocsMigrationService()
        payload = {
            "projects": [
                {
                    "id": 9,
                    "name": "迁移正文测试库",
                    "description": "用于验证正文迁移",
                    "created_at": None,
                    "updated_at": None,
                    "current_version": "1.0.0",
                }
            ],
            "documents": [
                {
                    "id": 9001,
                    "project_id": 9,
                    "title": "只在Mongo里有正文的文档",
                    "status": "draft",
                    "is_folder": 0,
                    "parent_id": None,
                    "sort_order": 0,
                    "path": "/docs/mongo-content.md",
                    "current_version": "1.0.0",
                    "type": "requirement",
                    "created_at": None,
                    "updated_at": None,
                    "content": None,
                }
            ],
            "kb_conversations": [],
            "kb_chat_messages": [],
            "document_contents": {9001: "# 占位标题\n\n这是占位正文。"},
            "markdown_contents": {9001: "# 正文标题\n\n这是来自 Markdown 提取结果的完整正文。"},
            "source_files": {
                9001: {
                    "filename": "mongo-content.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 7,
                    "storage_type": "collection",
                    "data": b"PDFDATA",
                }
            },
        }

        result = await service.migrate_from_structured_data("owner-2", payload)
        assert result["documents"] == 1

        async with async_session_maker() as session:
            doc = (
                await session.execute(
                    select(KBDocument).where(KBDocument.title == "只在Mongo里有正文的文档")
                )
            ).scalar_one()
            assert doc.content == "# 正文标题\n\n这是来自 Markdown 提取结果的完整正文。"
            assert doc.metadata_json["reqdocs_source_filename"] == "mongo-content.pdf"
            assert doc.metadata_json["reqdocs_source_mime_type"] == "application/pdf"
            source_path = doc.metadata_json["reqdocs_source_file_path"]
            assert source_path is not None
            assert tmp_path.joinpath("9001_mongo-content.pdf").read_bytes() == b"PDFDATA"

    @pytest.mark.asyncio
    async def test_migrate_reuses_existing_source_file_without_loading_blob(
        self, tmp_path, monkeypatch
    ):
        from sqlalchemy import select

        from app.db.database import async_session_maker
        from app.models.knowledge_base import KBDocument
        from app.services.reqdocs_migration_service import ReqDocsMigrationService

        monkeypatch.setattr(ReqDocsMigrationService, "SOURCE_FILE_DIR", tmp_path)
        existing_file = tmp_path / "9101_existing.pdf"
        existing_file.write_bytes(b"EXISTING")
        service = ReqDocsMigrationService()
        payload = {
            "projects": [
                {
                    "id": 91,
                    "name": "本地源文件复用库",
                    "description": None,
                    "created_at": None,
                    "updated_at": None,
                    "current_version": "1.0.0",
                }
            ],
            "documents": [
                {
                    "id": 9101,
                    "project_id": 91,
                    "title": "已有本地源文件",
                    "status": "draft",
                    "is_folder": 0,
                    "parent_id": None,
                    "sort_order": 0,
                    "path": "/docs/existing.md",
                    "current_version": "1.0.0",
                    "type": "requirement",
                    "created_at": None,
                    "updated_at": None,
                    "content": "正文",
                }
            ],
            "kb_conversations": [],
            "kb_chat_messages": [],
            "source_files": {
                9101: {
                    "filename": "existing.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 8,
                    "storage_type": "gridfs",
                }
            },
        }

        await service.migrate_from_structured_data("owner-existing-file", payload)

        async with async_session_maker() as session:
            doc = (
                await session.execute(
                    select(KBDocument).where(KBDocument.title == "已有本地源文件")
                )
            ).scalar_one()
            assert doc.metadata_json["reqdocs_source_file_path"] == str(existing_file)
            assert existing_file.read_bytes() == b"EXISTING"

    @pytest.mark.asyncio
    async def test_migration_is_idempotent_by_reqdocs_source_ids(self):
        from sqlalchemy import func, select

        from app.db.database import async_session_maker
        from app.models.knowledge_base import (
            ChatConversation,
            ChatMessage,
            KBDocument,
            KnowledgeBase,
        )
        from app.services.reqdocs_migration_service import ReqDocsMigrationService

        service = ReqDocsMigrationService()
        payload = {
            "projects": [
                {
                    "id": 20,
                    "name": "幂等测试库",
                    "description": "用于验证重复迁移不重复插入",
                    "created_at": None,
                    "updated_at": None,
                    "current_version": "1.0.0",
                }
            ],
            "documents": [
                {
                    "id": 20001,
                    "project_id": 20,
                    "title": "文档A",
                    "status": "draft",
                    "is_folder": 0,
                    "parent_id": None,
                    "sort_order": 0,
                    "path": "/docs/a.md",
                    "current_version": "1.0.0",
                    "type": "requirement",
                    "created_at": None,
                    "updated_at": None,
                    "content": None,
                }
            ],
            "kb_conversations": [
                {
                    "id": 30001,
                    "knowledge_base_id": 20,
                    "title": "问答A",
                    "created_by": 1,
                    "created_at": None,
                    "updated_at": None,
                }
            ],
            "kb_chat_messages": [
                {
                    "id": 40001,
                    "conversation_id": 30001,
                    "role": "user",
                    "content": "问题A",
                    "model": "deepseek-chat",
                    "created_at": None,
                }
            ],
            "document_contents": {20001: "正文A"},
        }

        await service.migrate_from_structured_data("owner-3", payload)
        await service.migrate_from_structured_data("owner-3", payload)

        async with async_session_maker() as session:
            kb_count = (
                await session.execute(
                    select(func.count())
                    .select_from(KnowledgeBase)
                    .where(KnowledgeBase.name == "幂等测试库")
                )
            ).scalar_one()
            doc_count = (
                await session.execute(
                    select(func.count()).select_from(KBDocument).where(KBDocument.title == "文档A")
                )
            ).scalar_one()
            conv_count = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatConversation)
                    .where(ChatConversation.title == "问答A")
                )
            ).scalar_one()
            msg_count = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.content == "问题A")
                )
            ).scalar_one()

            assert kb_count == 1
            assert doc_count == 1
            assert conv_count == 1
            assert msg_count == 1
