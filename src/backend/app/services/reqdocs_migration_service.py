"""One-time structured data migration from ReqDocs into AI for Investor."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymysql
from pymongo import MongoClient
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.knowledge_base import ChatConversation, ChatMessage, KBDocument, KnowledgeBase
from app.utils.backend_data_paths import get_backend_data_path

logger = logging.getLogger(__name__)


@dataclass
class ReqDocsConnectionSettings:
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    mongodb_url: str


class ReqDocsMigrationService:
    """Migrate structured ReqDocs data into local knowledge base tables."""

    SOURCE_FILE_DIR = get_backend_data_path("reqdocs_source_files")
    _DOCUMENT_COLUMNS = (
        "id, title, type, status, project_id, parent_id, path, is_folder, sort_order, "
        "current_version, created_at, updated_at"
    )

    @staticmethod
    def _message_key(conversation_id: Any, role: Any, content: Any, created_at: Any) -> tuple:
        if created_at is None:
            return (conversation_id, role, content)
        if hasattr(created_at, "isoformat"):
            return (conversation_id, role, content, created_at.isoformat())
        return (conversation_id, role, content, str(created_at))

    @classmethod
    def _message_keys(
        cls, conversation_id: Any, role: Any, content: Any, created_at: Any
    ) -> set[tuple]:
        keys = {cls._message_key(conversation_id, role, content, created_at)}
        if created_at is not None:
            keys.add((conversation_id, role, content))
        return keys

    @staticmethod
    def _normalize_content_map(raw: Any) -> dict[int, str]:
        if not isinstance(raw, dict):
            return {}
        result: dict[int, str] = {}
        for key, value in raw.items():
            try:
                doc_id = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(value, str):
                result[doc_id] = value
        return result

    @staticmethod
    def _normalize_source_file_map(raw: Any) -> dict[int, dict[str, Any]]:
        if not isinstance(raw, dict):
            return {}
        result: dict[int, dict[str, Any]] = {}
        for key, value in raw.items():
            try:
                doc_id = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict):
                result[doc_id] = value
        return result

    @classmethod
    def _build_existing_source_file_map(cls) -> dict[int, str]:
        if not cls.SOURCE_FILE_DIR.is_dir():
            return {}
        result: dict[int, str] = {}
        for path in cls.SOURCE_FILE_DIR.iterdir():
            if not path.is_file():
                continue
            raw_id = path.name.split("_", 1)[0]
            try:
                document_id = int(raw_id)
            except ValueError:
                continue
            result.setdefault(document_id, str(path))
        return result

    @staticmethod
    def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
        return [items[index : index + size] for index in range(0, len(items), size)]

    @staticmethod
    def _document_id_query_values(document_ids: list[int]) -> list[int | str]:
        return [*document_ids, *(str(document_id) for document_id in document_ids)]

    @classmethod
    def _fetch_latest_mongo_content_map(
        cls,
        db: Any,
        collection_name: str,
        document_ids: list[int],
        sort_fields: list[tuple[str, int]],
    ) -> dict[int, str]:
        if not document_ids:
            return {}

        result: dict[int, str] = {}
        query = {"document_id": {"$in": cls._document_id_query_values(document_ids)}}
        cursor = db[collection_name].find(query, {"document_id": 1, "content": 1}).sort(sort_fields)
        for item in cursor:
            try:
                document_id = int(item.get("document_id"))
            except (TypeError, ValueError):
                continue
            if document_id in result:
                continue
            content = item.get("content")
            if isinstance(content, str):
                result[document_id] = content
        return result

    @classmethod
    def _fetch_source_file_metadata_map(
        cls, db: Any, document_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        if not document_ids:
            return {}

        result: dict[int, dict[str, Any]] = {}
        query = {"document_id": {"$in": cls._document_id_query_values(document_ids)}}
        cursor = db.source_files.find(
            query,
            {
                "document_id": 1,
                "filename": 1,
                "mime_type": 1,
                "file_size": 1,
                "storage_type": 1,
                "gridfs_id": 1,
            },
        )
        for item in cursor:
            try:
                document_id = int(item.get("document_id"))
            except (TypeError, ValueError):
                continue
            if document_id in result:
                continue
            result[document_id] = {
                "filename": item.get("filename"),
                "mime_type": item.get("mime_type"),
                "file_size": item.get("file_size"),
                "storage_type": item.get("storage_type"),
            }
        return result

    @classmethod
    def _persist_source_file(
        cls,
        document_id: int,
        source_info: dict[str, Any] | None,
        existing_source_paths: dict[int, str] | None = None,
    ) -> str | None:
        if not source_info:
            return None
        file_data = source_info.get("data")
        filename = source_info.get("filename")
        if existing_source_paths is not None and document_id in existing_source_paths:
            return existing_source_paths[document_id]
        if (
            not isinstance(file_data, (bytes, bytearray))
            or not isinstance(filename, str)
            or not filename
        ):
            return None
        cls.SOURCE_FILE_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename).name
        target = cls.SOURCE_FILE_DIR / f"{document_id}_{safe_name}"
        target.write_bytes(bytes(file_data))
        if existing_source_paths is not None:
            existing_source_paths[document_id] = str(target)
        return str(target)

    @staticmethod
    def _parse_reqdocs_env() -> ReqDocsConnectionSettings:
        env_path = Path(
            os.environ.get(
                "REQDOCS_ENV_PATH",
                str(Path(__file__).resolve().parents[5] / "ReqDocs" / "backend" / ".env"),
            )
        )
        values: dict[str, str] = {}
        for line in env_path.read_text().splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, value = text.split("=", 1)
            values[key] = value

        database_url = values.get("DATABASE_URL", "")
        # mysql+pymysql://user:pass@127.0.0.1:3306/db
        prefix = "mysql+pymysql://"
        if not database_url.startswith(prefix):
            raise ValueError("Unsupported ReqDocs DATABASE_URL")
        rest = database_url[len(prefix) :]
        creds, host_part = rest.split("@", 1)
        user, password = creds.split(":", 1)
        host_port, database = host_part.split("/", 1)
        host, port = host_port.split(":", 1)
        return ReqDocsConnectionSettings(
            mysql_host=host,
            mysql_port=int(port),
            mysql_user=user,
            mysql_password=password,
            mysql_database=database,
            mongodb_url=values.get("MONGODB_URL", "mongodb://localhost:27017/document_management"),
        )

    async def migrate_from_structured_data(
        self, owner_id: str, payload: dict[str, Any]
    ) -> dict[str, int]:
        project_id_map: dict[int, str] = {}
        document_id_map: dict[int, str] = {}
        conversation_id_map: dict[int, str] = {}
        content_map = self._normalize_content_map(payload.get("document_contents", {}))
        markdown_map = self._normalize_content_map(payload.get("markdown_contents", {}))
        source_file_map = self._normalize_source_file_map(payload.get("source_files", {}))
        existing_source_paths = self._build_existing_source_file_map()

        async with async_session_maker() as session:
            existing_kbs = (
                (
                    await session.execute(
                        select(KnowledgeBase).where(KnowledgeBase.owner_id == owner_id)
                    )
                )
                .scalars()
                .all()
            )
            kb_by_reqdocs_id = {
                int((kb.settings or {}).get("reqdocs_project_id")): kb
                for kb in existing_kbs
                if isinstance(kb.settings, dict)
                and (kb.settings or {}).get("reqdocs_project_id") is not None
            }

            existing_docs = (await session.execute(select(KBDocument))).scalars().all()
            doc_by_reqdocs_id = {
                int((doc.metadata_json or {}).get("reqdocs_document_id")): doc
                for doc in existing_docs
                if isinstance(doc.metadata_json, dict)
                and (doc.metadata_json or {}).get("reqdocs_document_id") is not None
            }

            existing_conversations = (
                (await session.execute(select(ChatConversation))).scalars().all()
            )
            conv_by_reqdocs_id = {
                int((conv.settings or {}).get("reqdocs_conversation_id")): conv
                for conv in existing_conversations
                if isinstance(conv.settings, dict)
                and (conv.settings or {}).get("reqdocs_conversation_id") is not None
            }

            existing_messages = (await session.execute(select(ChatMessage))).scalars().all()
            existing_message_keys = {
                key
                for msg in existing_messages
                for key in self._message_keys(
                    msg.conversation_id, msg.role, msg.content, msg.created_at
                )
            }

            for project in payload.get("projects", []):
                kb = kb_by_reqdocs_id.get(project["id"])
                if kb is None:
                    kb = KnowledgeBase(
                        owner_id=owner_id,
                        name=project["name"],
                        description=project.get("description"),
                        is_public=True,
                        document_count=0,
                        settings={
                            "reqdocs_project_id": project["id"],
                            "reqdocs_current_version": project.get("current_version"),
                        },
                    )
                    if project.get("created_at"):
                        kb.created_at = project["created_at"]
                    session.add(kb)
                    await session.flush()
                    kb_by_reqdocs_id[project["id"]] = kb
                kb.name = project["name"]
                kb.description = project.get("description")
                kb.is_public = True
                kb.settings = {
                    "reqdocs_project_id": project["id"],
                    "reqdocs_current_version": project.get("current_version"),
                }
                if project.get("updated_at"):
                    kb.updated_at = project["updated_at"]
                project_id_map[project["id"]] = kb.id

            docs_by_project: dict[int, list[dict[str, Any]]] = {}
            for document in payload.get("documents", []):
                docs_by_project.setdefault(document["project_id"], []).append(document)

            for project_id, docs in docs_by_project.items():
                kb_id = project_id_map.get(project_id)
                if not kb_id:
                    continue
                for order, document in enumerate(docs):
                    entity = doc_by_reqdocs_id.get(document["id"])
                    source_info = source_file_map.get(document["id"])
                    source_file_path = self._persist_source_file(
                        document["id"], source_info, existing_source_paths
                    )
                    content = markdown_map.get(
                        document["id"],
                        content_map.get(document["id"], document.get("content")),
                    )
                    metadata_json = {
                        "reqdocs_document_id": document["id"],
                        "reqdocs_type": document.get("type"),
                        "reqdocs_current_version": document.get("current_version"),
                        "reqdocs_original_path": document.get("path"),
                    }
                    if source_info:
                        metadata_json.update(
                            {
                                "reqdocs_source_filename": source_info.get("filename"),
                                "reqdocs_source_mime_type": source_info.get("mime_type"),
                                "reqdocs_source_file_size": source_info.get("file_size"),
                                "reqdocs_source_storage_type": source_info.get("storage_type"),
                                "reqdocs_source_file_path": source_file_path,
                            }
                        )
                    if entity is None:
                        entity = KBDocument(
                            knowledge_base_id=kb_id,
                            title=document["title"],
                            content=content,
                            content_type="markdown",
                            file_path=document.get("path"),
                            is_folder=bool(document.get("is_folder", 0)),
                            sort_order=int(document.get("sort_order", order) or order),
                            status=document.get("status", "draft"),
                            index_status="not_indexed",
                            metadata_json=metadata_json,
                        )
                        if document.get("created_at"):
                            entity.created_at = document["created_at"]
                        session.add(entity)
                        await session.flush()
                        doc_by_reqdocs_id[document["id"]] = entity
                    entity.knowledge_base_id = kb_id
                    entity.title = document["title"]
                    entity.content = content
                    entity.content_type = "markdown"
                    entity.file_path = document.get("path")
                    entity.is_folder = bool(document.get("is_folder", 0))
                    entity.sort_order = int(document.get("sort_order", order) or order)
                    entity.status = document.get("status", "draft")
                    entity.metadata_json = metadata_json
                    if document.get("updated_at"):
                        entity.updated_at = document["updated_at"]
                    document_id_map[document["id"]] = entity.id

                # patch parent ids in second pass
                for document in docs:
                    old_parent = document.get("parent_id")
                    if not old_parent:
                        continue
                    new_doc_id = document_id_map[document["id"]]
                    new_parent_id = document_id_map.get(old_parent)
                    if new_parent_id:
                        target = (
                            await session.execute(
                                select(KBDocument).where(KBDocument.id == new_doc_id)
                            )
                        ).scalar_one()
                        target.parent_id = new_parent_id

                kb = (
                    await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
                ).scalar_one()
                kb.document_count = len(docs)

            for conversation in payload.get("kb_conversations", []):
                kb_id = project_id_map.get(conversation["knowledge_base_id"])
                if not kb_id:
                    continue
                conv = conv_by_reqdocs_id.get(conversation["id"])
                if conv is None:
                    conv = ChatConversation(
                        knowledge_base_id=kb_id,
                        user_id=owner_id,
                        title=conversation.get("title") or "新对话",
                        model_id=None,
                        settings={"reqdocs_conversation_id": conversation["id"]},
                    )
                    if conversation.get("created_at"):
                        conv.created_at = conversation["created_at"]
                    session.add(conv)
                    await session.flush()
                    conv_by_reqdocs_id[conversation["id"]] = conv
                conv.knowledge_base_id = kb_id
                conv.user_id = owner_id
                conv.title = conversation.get("title") or "新对话"
                conv.settings = {"reqdocs_conversation_id": conversation["id"]}
                if conversation.get("updated_at"):
                    conv.updated_at = conversation["updated_at"]
                conversation_id_map[conversation["id"]] = conv.id

            for message in payload.get("kb_chat_messages", []):
                conv_id = conversation_id_map.get(message["conversation_id"])
                if not conv_id:
                    continue
                key = self._message_key(
                    conv_id,
                    message["role"],
                    message["content"],
                    message.get("created_at"),
                )
                if key in existing_message_keys:
                    continue
                entity = ChatMessage(
                    conversation_id=conv_id,
                    role=message["role"],
                    content=message["content"],
                    model_id=message.get("model"),
                    citations=None,
                    tokens_used=None,
                    reasoning=None,
                )
                if message.get("created_at"):
                    entity.created_at = message["created_at"]
                session.add(entity)
                existing_message_keys.update(
                    self._message_keys(
                        conv_id, message["role"], message["content"], message.get("created_at")
                    )
                )

            await session.commit()

        return {
            "knowledge_bases": len(project_id_map),
            "documents": len(document_id_map),
            "conversations": len(conversation_id_map),
            "messages": sum(
                1
                for msg in payload.get("kb_chat_messages", [])
                if msg.get("conversation_id") in conversation_id_map
            ),
        }

    def read_reqdocs_structured_data(self) -> dict[str, Any]:
        settings = self._parse_reqdocs_env()
        conn = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, description, created_at, updated_at, current_version FROM projects"
                )
                projects = list(cur.fetchall())
                cur.execute(
                    "SELECT id, title, type, status, project_id, parent_id, path, is_folder, sort_order, current_version, created_at, updated_at FROM documents"
                )
                documents = list(cur.fetchall())
                cur.execute(
                    "SELECT id, knowledge_base_id, title, created_by, created_at, updated_at FROM kb_conversations"
                )
                conversations = list(cur.fetchall())
                cur.execute(
                    "SELECT id, conversation_id, role, content, model, created_at FROM kb_chat_messages"
                )
                messages = list(cur.fetchall())
        finally:
            conn.close()

        content_map: dict[int, str] = {}
        markdown_map: dict[int, str] = {}
        source_file_map: dict[int, dict[str, Any]] = {}
        client: MongoClient[Any] | None = None
        try:
            client = MongoClient(settings.mongodb_url)
            db = client.get_default_database()
            cursor = db.document_contents.find({}, {"document_id": 1, "content": 1}).sort("_id", -1)
            for item in cursor:
                try:
                    doc_id = int(item.get("document_id"))
                except (TypeError, ValueError):
                    continue
                if doc_id not in content_map and isinstance(item.get("content"), str):
                    content_map[doc_id] = item["content"]

            markdown_cursor = db.markdown_contents.find(
                {}, {"document_id": 1, "content": 1, "generated_at": 1}
            ).sort("generated_at", -1)
            for item in markdown_cursor:
                try:
                    doc_id = int(item.get("document_id"))
                except (TypeError, ValueError):
                    continue
                if doc_id not in markdown_map and isinstance(item.get("content"), str):
                    markdown_map[doc_id] = item["content"]

            source_files = db.source_files.find(
                {},
                {
                    "document_id": 1,
                    "filename": 1,
                    "mime_type": 1,
                    "file_size": 1,
                    "storage_type": 1,
                    "gridfs_id": 1,
                },
            )
            for item in source_files:
                try:
                    doc_id = int(item.get("document_id"))
                except (TypeError, ValueError):
                    continue
                if doc_id in source_file_map:
                    continue
                source_file_map[doc_id] = {
                    "filename": item.get("filename"),
                    "mime_type": item.get("mime_type"),
                    "file_size": item.get("file_size"),
                    "storage_type": item.get("storage_type"),
                }
        finally:
            try:
                if client is not None:
                    client.close()
            except Exception:
                logger.debug("Failed to close MongoDB client (best-effort)", exc_info=True)

        return {
            "projects": projects,
            "documents": documents,
            "kb_conversations": conversations,
            "kb_chat_messages": messages,
            "document_contents": content_map,
            "markdown_contents": markdown_map,
            "source_files": source_file_map,
        }

    async def _load_existing_reqdocs_maps(
        self, owner_id: str
    ) -> tuple[dict[int, str], dict[int, str], dict[int, str], set[tuple]]:
        async with async_session_maker() as session:
            existing_kbs = (
                await session.execute(
                    select(KnowledgeBase.id, KnowledgeBase.settings).where(
                        KnowledgeBase.owner_id == owner_id
                    )
                )
            ).all()
            kb_by_reqdocs_id = {
                int((settings or {}).get("reqdocs_project_id")): str(kb_id)
                for kb_id, settings in existing_kbs
                if isinstance(settings, dict) and settings.get("reqdocs_project_id") is not None
            }

            existing_docs = (
                await session.execute(select(KBDocument.id, KBDocument.metadata_json))
            ).all()
            doc_by_reqdocs_id = {
                int((metadata_json or {}).get("reqdocs_document_id")): str(doc_id)
                for doc_id, metadata_json in existing_docs
                if isinstance(metadata_json, dict)
                and metadata_json.get("reqdocs_document_id") is not None
            }

            existing_conversations = (
                await session.execute(select(ChatConversation.id, ChatConversation.settings))
            ).all()
            conv_by_reqdocs_id = {
                int((settings or {}).get("reqdocs_conversation_id")): str(conv_id)
                for conv_id, settings in existing_conversations
                if isinstance(settings, dict) and settings.get("reqdocs_conversation_id") is not None
            }

            existing_messages = (
                await session.execute(
                    select(
                        ChatMessage.conversation_id,
                        ChatMessage.role,
                        ChatMessage.content,
                        ChatMessage.created_at,
                    )
                )
            ).all()
            existing_message_keys = {
                key
                for conversation_id, role, content, created_at in existing_messages
                for key in self._message_keys(conversation_id, role, content, created_at)
            }

        return kb_by_reqdocs_id, doc_by_reqdocs_id, conv_by_reqdocs_id, existing_message_keys

    async def migrate_from_live_reqdocs_batched(
        self,
        owner_id: str,
        document_batch_size: int = 10,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, int]:
        """Migrate ReqDocs data in small committed document batches.

        This path avoids loading all MongoDB document contents or source files
        into memory. It is idempotent by ReqDocs source IDs and can be safely
        rerun after interruption.
        """
        if document_batch_size < 1:
            raise ValueError("document_batch_size must be >= 1")

        settings = self._parse_reqdocs_env()
        existing_source_paths = self._build_existing_source_file_map()
        kb_by_reqdocs_id, doc_by_reqdocs_id, conv_by_reqdocs_id, existing_message_keys = (
            await self._load_existing_reqdocs_maps(owner_id)
        )
        project_id_map = dict(kb_by_reqdocs_id)
        document_id_map = dict(doc_by_reqdocs_id)
        conversation_id_map = dict(conv_by_reqdocs_id)
        result = {
            "knowledge_bases": 0,
            "documents": 0,
            "conversations": 0,
            "messages": 0,
        }

        conn = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        mongo_client: MongoClient[Any] | None = None
        try:
            mongo_client = MongoClient(settings.mongodb_url)
            mongo_db = mongo_client.get_default_database()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, description, created_at, updated_at, current_version "
                    "FROM projects ORDER BY id ASC"
                )
                projects = list(cur.fetchall())

            for project_index, project in enumerate(projects, start=1):
                project_id = int(project["id"])
                async with async_session_maker() as session:
                    kb_id = kb_by_reqdocs_id.get(project_id)
                    kb = await session.get(KnowledgeBase, kb_id) if kb_id else None
                    if kb is None:
                        kb = KnowledgeBase(
                            owner_id=owner_id,
                            name=project["name"],
                            description=project.get("description"),
                            is_public=True,
                            document_count=0,
                            settings={
                                "reqdocs_project_id": project_id,
                                "reqdocs_current_version": project.get("current_version"),
                            },
                        )
                        if project.get("created_at"):
                            kb.created_at = project["created_at"]
                        session.add(kb)
                        await session.flush()
                        kb_by_reqdocs_id[project_id] = kb.id
                    kb.name = project["name"]
                    kb.description = project.get("description")
                    kb.is_public = True
                    kb.settings = {
                        "reqdocs_project_id": project_id,
                        "reqdocs_current_version": project.get("current_version"),
                    }
                    if project.get("updated_at"):
                        kb.updated_at = project["updated_at"]
                    await session.commit()
                    project_id_map[project_id] = kb.id

                result["knowledge_bases"] += 1

                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT {self._DOCUMENT_COLUMNS} FROM documents "
                        "WHERE project_id = %s ORDER BY sort_order ASC, id ASC",
                        (project_id,),
                    )
                    documents = list(cur.fetchall())

                if progress_callback:
                    progress_callback(
                        {
                            "event": "project",
                            "project_index": project_index,
                            "project_total": len(projects),
                            "project_id": project_id,
                            "project_name": project["name"],
                            "documents": len(documents),
                        }
                    )

                kb_id = project_id_map[project_id]
                for batch_index, batch in enumerate(
                    self._chunked(documents, document_batch_size), start=1
                ):
                    document_ids = [int(document["id"]) for document in batch]
                    content_map = self._fetch_latest_mongo_content_map(
                        mongo_db, "document_contents", document_ids, [("_id", -1)]
                    )
                    markdown_map = self._fetch_latest_mongo_content_map(
                        mongo_db,
                        "markdown_contents",
                        document_ids,
                        [("generated_at", -1), ("_id", -1)],
                    )
                    source_file_map = self._fetch_source_file_metadata_map(mongo_db, document_ids)

                    async with async_session_maker() as session:
                        for document in batch:
                            document_id = int(document["id"])
                            entity_id = doc_by_reqdocs_id.get(document_id)
                            entity = await session.get(KBDocument, entity_id) if entity_id else None
                            source_info = source_file_map.get(document_id)
                            source_file_path = self._persist_source_file(
                                document_id, source_info, existing_source_paths
                            )
                            content = markdown_map.get(
                                document_id,
                                content_map.get(document_id, document.get("content")),
                            )
                            metadata_json = {
                                "reqdocs_document_id": document_id,
                                "reqdocs_type": document.get("type"),
                                "reqdocs_current_version": document.get("current_version"),
                                "reqdocs_original_path": document.get("path"),
                            }
                            if source_info:
                                metadata_json.update(
                                    {
                                        "reqdocs_source_filename": source_info.get("filename"),
                                        "reqdocs_source_mime_type": source_info.get("mime_type"),
                                        "reqdocs_source_file_size": source_info.get("file_size"),
                                        "reqdocs_source_storage_type": source_info.get(
                                            "storage_type"
                                        ),
                                        "reqdocs_source_file_path": source_file_path,
                                    }
                                )
                            if entity is None:
                                entity = KBDocument(
                                    knowledge_base_id=kb_id,
                                    title=document["title"],
                                    content=content,
                                    content_type="markdown",
                                    file_path=document.get("path"),
                                    is_folder=bool(document.get("is_folder", 0)),
                                    sort_order=int(
                                        document.get("sort_order", result["documents"]) or 0
                                    ),
                                    status=document.get("status", "draft"),
                                    index_status="not_indexed",
                                    metadata_json=metadata_json,
                                )
                                if document.get("created_at"):
                                    entity.created_at = document["created_at"]
                                session.add(entity)
                                await session.flush()
                                doc_by_reqdocs_id[document_id] = entity.id
                            entity.knowledge_base_id = kb_id
                            entity.title = document["title"]
                            entity.content = content
                            entity.content_type = "markdown"
                            entity.file_path = document.get("path")
                            entity.is_folder = bool(document.get("is_folder", 0))
                            entity.sort_order = int(
                                document.get("sort_order", result["documents"]) or 0
                            )
                            entity.status = document.get("status", "draft")
                            entity.metadata_json = metadata_json
                            if document.get("updated_at"):
                                entity.updated_at = document["updated_at"]
                            document_id_map[document_id] = entity.id

                        await session.commit()

                    result["documents"] += len(batch)
                    if progress_callback:
                        progress_callback(
                            {
                                "event": "document_batch",
                                "project_id": project_id,
                                "project_name": project["name"],
                                "batch_index": batch_index,
                                "batch_size": len(batch),
                                "project_done": min(
                                    batch_index * document_batch_size, len(documents)
                                ),
                                "project_total": len(documents),
                                "total_documents": result["documents"],
                            }
                        )

                for parent_batch in self._chunked(documents, document_batch_size):
                    async with async_session_maker() as session:
                        for document in parent_batch:
                            old_parent = document.get("parent_id")
                            if not old_parent:
                                continue
                            new_doc_id = document_id_map.get(int(document["id"]))
                            new_parent_id = document_id_map.get(int(old_parent))
                            if new_doc_id and new_parent_id:
                                target = await session.get(KBDocument, new_doc_id)
                                if target is not None:
                                    target.parent_id = new_parent_id
                        await session.commit()

                async with async_session_maker() as session:
                    kb = await session.get(KnowledgeBase, kb_id)
                    if kb is not None:
                        kb.document_count = len(documents)
                    await session.commit()

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, knowledge_base_id, title, created_by, created_at, updated_at "
                    "FROM kb_conversations ORDER BY id ASC"
                )
                conversations = list(cur.fetchall())
                cur.execute(
                    "SELECT id, conversation_id, role, content, model, created_at "
                    "FROM kb_chat_messages ORDER BY id ASC"
                )
                messages = list(cur.fetchall())

            async with async_session_maker() as session:
                for conversation in conversations:
                    old_kb_id = int(conversation["knowledge_base_id"])
                    kb_id = project_id_map.get(old_kb_id)
                    if not kb_id:
                        continue
                    conversation_id = int(conversation["id"])
                    conv_id = conv_by_reqdocs_id.get(conversation_id)
                    conv = await session.get(ChatConversation, conv_id) if conv_id else None
                    if conv is None:
                        conv = ChatConversation(
                            knowledge_base_id=kb_id,
                            user_id=owner_id,
                            title=conversation.get("title") or "新对话",
                            model_id=None,
                            settings={"reqdocs_conversation_id": conversation_id},
                        )
                        if conversation.get("created_at"):
                            conv.created_at = conversation["created_at"]
                        session.add(conv)
                        await session.flush()
                        conv_by_reqdocs_id[conversation_id] = conv.id
                    conv.knowledge_base_id = kb_id
                    conv.user_id = owner_id
                    conv.title = conversation.get("title") or "新对话"
                    conv.settings = {"reqdocs_conversation_id": conversation_id}
                    if conversation.get("updated_at"):
                        conv.updated_at = conversation["updated_at"]
                    conversation_id_map[conversation_id] = conv.id
                    result["conversations"] += 1

                await session.commit()

            async with async_session_maker() as session:
                for message in messages:
                    conv_id = conversation_id_map.get(int(message["conversation_id"]))
                    if not conv_id:
                        continue
                    key = self._message_key(
                        conv_id,
                        message["role"],
                        message["content"],
                        message.get("created_at"),
                    )
                    if key in existing_message_keys:
                        continue
                    entity = ChatMessage(
                        conversation_id=conv_id,
                        role=message["role"],
                        content=message["content"],
                        model_id=message.get("model"),
                        citations=None,
                        tokens_used=None,
                        reasoning=None,
                    )
                    if message.get("created_at"):
                        entity.created_at = message["created_at"]
                    session.add(entity)
                    existing_message_keys.update(
                        self._message_keys(
                            conv_id,
                            message["role"],
                            message["content"],
                            message.get("created_at"),
                        )
                    )
                    result["messages"] += 1
                await session.commit()

            if progress_callback:
                progress_callback({"event": "complete", **result})

            return result
        finally:
            conn.close()
            try:
                if mongo_client is not None:
                    mongo_client.close()
            except Exception:
                logger.debug("Failed to close MongoDB client (best-effort)", exc_info=True)

    async def migrate_from_live_reqdocs(self, owner_id: str) -> dict[str, int]:
        return await self.migrate_from_live_reqdocs_batched(owner_id, document_batch_size=10)


reqdocs_migration_service = ReqDocsMigrationService()
