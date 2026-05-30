"""Knowledge base service for iteration 129."""

from sqlalchemy import delete, func, select

from app.db.database import async_session_maker
from app.models.knowledge_base import (
    ChatConversation,
    ChatMessage,
    DocumentChunk,
    KBDocument,
    KnowledgeBase,
)
from app.schemas.knowledge_base import (
    KBDocumentCreate,
    KBDocumentUpdate,
    KnowledgeBaseCreate,
    KnowledgeBaseSettings,
    KnowledgeBaseUpdate,
    ReqDocsImportRequest,
)
from app.utils.knowledge_base_settings import (
    default_knowledge_base_settings,
    merge_knowledge_base_settings,
)


class KnowledgeBaseService:
    """CRUD service for knowledge bases and documents."""

    @staticmethod
    def _hydrate_settings(entity: KnowledgeBase | None) -> KnowledgeBase | None:
        if entity is None:
            return None
        entity.settings = merge_knowledge_base_settings(getattr(entity, "settings", None))
        return entity

    @staticmethod
    def _merge_settings(
        current_settings: dict | None,
        update_settings: dict | None,
    ) -> dict:
        merged = merge_knowledge_base_settings(current_settings)
        for key, value in (update_settings or {}).items():
            if value is None:
                continue
            merged[key] = value
        return KnowledgeBaseSettings.model_validate(merged).model_dump()

    async def _validate_parent(
        self,
        session,
        kb_id: str,
        parent_id: str | None,
        current_document_id: str | None = None,
    ) -> None:
        if parent_id is None:
            return
        if current_document_id is not None and parent_id == current_document_id:
            raise ValueError("Document cannot be its own parent")
        parent = (
            await session.execute(
                select(KBDocument).where(
                    KBDocument.id == parent_id,
                    KBDocument.knowledge_base_id == kb_id,
                )
            )
        ).scalar_one_or_none()
        if parent is None:
            raise ValueError("Parent document not found in this knowledge base")
        if not parent.is_folder:
            raise ValueError("Parent document must be a folder")
        if current_document_id is None:
            return
        rows = (
            await session.execute(
                select(KBDocument.id, KBDocument.parent_id).where(
                    KBDocument.knowledge_base_id == kb_id
                )
            )
        ).all()
        parent_by_id = {str(doc_id): str(pid) if pid is not None else None for doc_id, pid in rows}
        cursor = parent_id
        while cursor is not None:
            if cursor == current_document_id:
                raise ValueError("Document parent cycle is not allowed")
            cursor = parent_by_id.get(cursor)

    async def create_knowledge_base(
        self, owner_id: str, data: KnowledgeBaseCreate
    ) -> KnowledgeBase:
        async with async_session_maker() as session:
            entity = KnowledgeBase(
                owner_id=owner_id,
                name=data.name,
                description=data.description,
                is_public=data.is_public,
                settings=KnowledgeBaseSettings.model_validate(data.settings).model_dump(),
            )
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return self._hydrate_settings(entity)

    async def list_knowledge_bases(
        self, owner_id: str, skip: int = 0, limit: int = 20, search: str | None = None
    ) -> tuple[int, list[KnowledgeBase]]:
        async with async_session_maker() as session:
            filters = [KnowledgeBase.owner_id == owner_id]
            if search:
                filters.append(KnowledgeBase.name.ilike(f"%{search}%"))

            total = (
                await session.execute(
                    select(func.count()).select_from(KnowledgeBase).where(*filters)
                )
            ).scalar_one()
            items = (
                (
                    await session.execute(
                        select(KnowledgeBase)
                        .where(*filters)
                        .order_by(KnowledgeBase.created_at.desc())
                        .offset(skip)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return total, [self._hydrate_settings(item) for item in items]

    async def get_knowledge_base(self, kb_id: str, owner_id: str) -> KnowledgeBase | None:
        async with async_session_maker() as session:
            entity = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == kb_id,
                        KnowledgeBase.owner_id == owner_id,
                    )
                )
            ).scalar_one_or_none()
            return self._hydrate_settings(entity)

    async def update_knowledge_base(
        self, kb_id: str, owner_id: str, data: KnowledgeBaseUpdate
    ) -> KnowledgeBase | None:
        async with async_session_maker() as session:
            entity = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == kb_id,
                        KnowledgeBase.owner_id == owner_id,
                    )
                )
            ).scalar_one_or_none()
            if entity is None:
                return None
            payload = data.model_dump(exclude_unset=True)
            if "settings" in payload:
                payload["settings"] = self._merge_settings(
                    getattr(entity, "settings", None),
                    data.settings.model_dump(exclude_unset=True) if data.settings else None,
                )
            for key, value in payload.items():
                setattr(entity, key, value)
            await session.commit()
            await session.refresh(entity)
            return self._hydrate_settings(entity)

    async def delete_knowledge_base(self, kb_id: str, owner_id: str) -> bool:
        async with async_session_maker() as session:
            entity = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == kb_id,
                        KnowledgeBase.owner_id == owner_id,
                    )
                )
            ).scalar_one_or_none()
            if entity is None:
                return False
            conversation_ids = list(
                (
                    await session.execute(
                        select(ChatConversation.id).where(
                            ChatConversation.knowledge_base_id == kb_id
                        )
                    )
                ).scalars()
            )
            if conversation_ids:
                await session.execute(
                    delete(ChatMessage).where(ChatMessage.conversation_id.in_(conversation_ids))
                )
            await session.execute(
                delete(ChatConversation).where(ChatConversation.knowledge_base_id == kb_id)
            )
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.knowledge_base_id == kb_id)
            )
            await session.execute(delete(KBDocument).where(KBDocument.knowledge_base_id == kb_id))
            await session.delete(entity)
            await session.commit()
            return True

    async def list_documents(self, kb_id: str, owner_id: str) -> list[KBDocument] | None:
        async with async_session_maker() as session:
            kb = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id
                    )
                )
            ).scalar_one_or_none()
            if kb is None:
                return None
            self._hydrate_settings(kb)
            items = (
                (
                    await session.execute(
                        select(KBDocument)
                        .where(KBDocument.knowledge_base_id == kb_id)
                        .order_by(KBDocument.sort_order.asc(), KBDocument.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            return list(items)

    async def create_document(
        self, kb_id: str, owner_id: str, data: KBDocumentCreate
    ) -> KBDocument | None:
        async with async_session_maker() as session:
            kb = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id
                    )
                )
            ).scalar_one_or_none()
            if kb is None:
                return None
            await self._validate_parent(session, kb_id, data.parent_id)
            entity = KBDocument(
                knowledge_base_id=kb_id,
                title=data.title,
                content=data.content,
                content_type=data.content_type,
                parent_id=data.parent_id,
                is_folder=data.is_folder,
            )
            session.add(entity)
            current_count = int(getattr(kb, "document_count", 0) or 0)
            kb.document_count = current_count + 1
            await session.commit()
            await session.refresh(entity)
            return entity

    async def get_document(self, kb_id: str, doc_id: str, owner_id: str) -> KBDocument | None:
        async with async_session_maker() as session:
            return (
                await session.execute(
                    select(KBDocument)
                    .join(KnowledgeBase, KnowledgeBase.id == KBDocument.knowledge_base_id)
                    .where(
                        KBDocument.id == doc_id,
                        KBDocument.knowledge_base_id == kb_id,
                        KnowledgeBase.owner_id == owner_id,
                    )
                )
            ).scalar_one_or_none()

    async def update_document(
        self, kb_id: str, doc_id: str, owner_id: str, data: KBDocumentUpdate
    ) -> KBDocument | None:
        async with async_session_maker() as session:
            entity = (
                await session.execute(
                    select(KBDocument)
                    .join(KnowledgeBase, KnowledgeBase.id == KBDocument.knowledge_base_id)
                    .where(
                        KBDocument.id == doc_id,
                        KBDocument.knowledge_base_id == kb_id,
                        KnowledgeBase.owner_id == owner_id,
                    )
                )
            ).scalar_one_or_none()
            if entity is None:
                return None
            payload = data.model_dump(exclude_unset=True)
            if "parent_id" in payload:
                await self._validate_parent(session, kb_id, payload["parent_id"], doc_id)
            content_affecting_keys = {"content", "content_type", "title", "is_folder"}
            should_expire_index = (
                bool(content_affecting_keys.intersection(payload.keys()))
                and "index_status" not in payload
            )
            for key, value in payload.items():
                setattr(entity, key, value)
            if should_expire_index:
                entity.index_status = "not_indexed"
                entity.indexed_at = None
            await session.commit()
            await session.refresh(entity)
            return entity

    async def delete_document(self, kb_id: str, doc_id: str, owner_id: str) -> bool:
        async with async_session_maker() as session:
            kb = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id
                    )
                )
            ).scalar_one_or_none()
            if kb is None:
                return False
            entity = (
                await session.execute(
                    select(KBDocument).where(
                        KBDocument.id == doc_id, KBDocument.knowledge_base_id == kb_id
                    )
                )
            ).scalar_one_or_none()
            if entity is None:
                return False
            await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
            await session.delete(entity)
            current_count = int(getattr(kb, "document_count", 0) or 0)
            kb.document_count = max(0, current_count - 1)
            await session.commit()
            return True

    async def import_reqdocs_payload(
        self, owner_id: str, data: ReqDocsImportRequest
    ) -> tuple[KnowledgeBase, int]:
        async with async_session_maker() as session:
            kb = KnowledgeBase(
                owner_id=owner_id,
                name=data.name,
                description=data.description,
                is_public=False,
                document_count=len(data.documents),
                settings=default_knowledge_base_settings(),
            )
            session.add(kb)
            await session.flush()

            for index, doc in enumerate(data.documents):
                session.add(
                    KBDocument(
                        knowledge_base_id=kb.id,
                        title=doc.title,
                        content=doc.content,
                        content_type=doc.content_type,
                        is_folder=doc.is_folder,
                        parent_id=doc.parent_id,
                        sort_order=index,
                    )
                )

            await session.commit()
            await session.refresh(kb)
            return self._hydrate_settings(kb), len(data.documents)
