"""Knowledge-base retrieval and grounded answer generation."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, or_, select

from app.db.database import async_session_maker
from app.models.knowledge_base import DocumentChunk, KBDocument, KnowledgeBase
from app.services.ai_chat_service import AIChatService
from app.services.chunk_service import chunk_service
from app.services.semantic_retrieval_service import SemanticChunk, SemanticRetrievalService
from app.services.strategy_service import build_ai_strategy_draft, render_ai_strategy_draft_answer
from app.utils.knowledge_base_settings import merge_knowledge_base_settings

logger = logging.getLogger(__name__)


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _extract_query_terms(query: str) -> list[str]:
    normalized = re.sub(r"[？?！!,，。；：:()（）\[\]{}<>/\\\s]+", " ", query.lower()).strip()
    tokens = [token for token in normalized.split() if token]
    if len(tokens) == 1 and any("\u4e00" <= ch <= "\u9fff" for ch in tokens[0]):
        text = tokens[0]
        ngrams = [text[i : i + 2] for i in range(len(text) - 1) if text[i : i + 2].strip()]
        if ngrams:
            return list(dict.fromkeys(ngrams))
    return tokens


def _keyword_similarity(query: str, content: str) -> float:
    query_terms = _extract_query_terms(query)
    haystack = (content or "").lower()
    if not query_terms:
        return 0.0
    hits = sum(1 for term in query_terms if term in haystack)
    return hits / len(query_terms)


def _char_ngrams(text: str, size: int = 2) -> set[str]:
    compact = re.sub(r"\s+", "", str(text or "").lower())
    if not compact:
        return set()
    if len(compact) <= size:
        return {compact}
    return {compact[idx : idx + size] for idx in range(len(compact) - size + 1)}


def _char_jaccard(left: str, right: str) -> float:
    left_set = _char_ngrams(left)
    right_set = _char_ngrams(right)
    if not left_set or not right_set:
        return 0.0
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def _history_message_to_dict(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        return message
    return {
        "role": getattr(message, "role", None),
        "content": getattr(message, "content", None),
        "citations": getattr(message, "citations", None),
    }


def _looks_like_follow_up(question: str) -> bool:
    normalized = _normalize_text(question).lower()
    if not normalized:
        return False
    follow_up_prefixes = (
        "那",
        "这个",
        "这个策略",
        "这套",
        "继续",
        "再",
        "然后",
        "展开",
        "细说",
        "如何",
        "为什么",
        "那风控",
        "那回测",
        "那参数",
        "its ",
        "that ",
        "those ",
        "how about",
        "what about",
        "continue",
    )
    if normalized.startswith(follow_up_prefixes):
        return True
    if len(normalized) <= 24:
        return True
    return any(token in normalized for token in ("上面", "刚才", "前面", "上述", "这个问题"))


def _is_knowledge_base_overview_question(question: str) -> bool:
    """Return whether a question asks for the contents of the whole knowledge base."""
    normalized = _normalize_text(question).lower()
    compact = re.sub(r"[\s？?！!,，。；：:()（）\[\]{}<>/\\]+", "", normalized)
    document_recommendation = any(
        phrase in compact
        for phrase in (
            "重点阅读",
            "优先阅读",
            "推荐阅读",
            "值得阅读",
            "哪些文档值得",
            "哪些资料值得",
        )
    )
    if document_recommendation:
        # The active knowledge base already supplies the scope in chat, so
        # users commonly omit an explicit "知识库" qualifier here.
        return True

    chinese_scope = any(marker in compact for marker in ("知识库", "这个库", "资料库"))
    chinese_intent = any(
        phrase in compact
        for phrase in (
            "包含哪些内容",
            "包含什么",
            "主要内容",
            "主要包含",
            "有什么内容",
            "有哪些文档",
            "有哪些资料",
        )
    )
    if chinese_scope and chinese_intent:
        return True

    english_scope = "knowledge base" in normalized or "document collection" in normalized
    english_intent = any(
        phrase in normalized
        for phrase in ("what does", "what is in", "what documents", "what content", "contain")
    )
    return english_scope and english_intent


def _safe_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class RAGService:
    """Index, search, and grounded answer generation."""

    def __init__(self, *, semantic_retriever: SemanticRetrievalService | None = None) -> None:
        self.ai_chat_service = AIChatService()
        self.semantic_retriever = semantic_retriever or SemanticRetrievalService()

    @staticmethod
    def _to_semantic_chunks(rows: list[tuple[DocumentChunk, KBDocument]]) -> list[SemanticChunk]:
        """Create one compact semantic representation per document.

        Embedding every chunk makes a first index of large collections take
        far too long.  Sampling the beginning, middle, and end of each
        document keeps document discovery semantic and bounded; the selected
        document's original chunks are still used as grounded answer context.
        """
        by_document: dict[str, tuple[KBDocument, list[DocumentChunk]]] = {}
        for chunk, document in rows:
            if not str(chunk.content or "").strip():
                continue
            document_id = str(chunk.document_id)
            if document_id not in by_document:
                by_document[document_id] = (document, [])
            by_document[document_id][1].append(chunk)

        semantic_documents: list[SemanticChunk] = []
        for document_id, (document, chunks) in by_document.items():
            ordered_chunks = sorted(chunks, key=lambda item: int(item.chunk_index))
            sample_positions = sorted({0, len(ordered_chunks) // 2, len(ordered_chunks) - 1})
            samples = [
                _normalize_text(str(ordered_chunks[position].content or ""))[:1400]
                for position in sample_positions
                if ordered_chunks[position].content
            ]
            content = "\n\n".join(sample for sample in samples if sample)
            if not content:
                continue
            semantic_documents.append(
                SemanticChunk(
                    # The vector record represents a document, not an
                    # individual chunk.  The document id is stable across
                    # chunk re-indexing and supports idempotent upserts.
                    chunk_id=document_id,
                    knowledge_base_id=str(getattr(document, "knowledge_base_id", "") or ""),
                    document_id=document_id,
                    document_title=str(getattr(document, "title", "") or "未命名文档"),
                    chunk_index=0,
                    content=content,
                )
            )
        return semantic_documents

    async def _sync_vector_document(
        self,
        session,
        knowledge_base_id: str,
        document_id: str,
    ) -> None:
        """Mirror one committed document into the local vector index."""
        if not self.semantic_retriever.enabled:
            return
        rows = list(
            (
                await session.execute(
                    select(DocumentChunk, KBDocument)
                    .join(KBDocument, KBDocument.id == DocumentChunk.document_id)
                    .where(
                        DocumentChunk.knowledge_base_id == knowledge_base_id,
                        DocumentChunk.document_id == document_id,
                    )
                )
            ).all()
        )
        await self.semantic_retriever.delete_document(knowledge_base_id, document_id)
        if rows:
            await self.semantic_retriever.upsert_chunks(self._to_semantic_chunks(rows))

    async def _list_indexable_documents(self, session, knowledge_base_id: str) -> list[KBDocument]:
        return list(
            (
                await session.execute(
                    select(KBDocument).where(
                        KBDocument.knowledge_base_id == knowledge_base_id,
                        KBDocument.is_folder.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )

    async def _knowledge_base_overview_citations(
        self,
        knowledge_base_id: str,
        owner_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Build document-level citations for a whole-library overview question."""
        async with async_session_maker() as session:
            documents = list(
                (
                    await session.execute(
                        select(KBDocument)
                        .join(KnowledgeBase, KnowledgeBase.id == KBDocument.knowledge_base_id)
                        .where(
                            KBDocument.knowledge_base_id == knowledge_base_id,
                            KBDocument.is_folder.is_(False),
                            or_(
                                KnowledgeBase.owner_id == owner_id,
                                KnowledgeBase.is_public.is_(True),
                            ),
                        )
                        .order_by(KBDocument.sort_order.asc(), KBDocument.created_at.asc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )

        citations: list[dict[str, Any]] = []
        for document in documents:
            title = _normalize_text(str(getattr(document, "title", "") or "")) or "未命名文档"
            preview = _normalize_text(str(getattr(document, "content", "") or ""))
            citations.append(
                {
                    "chunk_id": None,
                    "document_id": str(document.id),
                    "document_title": title,
                    "chunk_index": None,
                    "content": preview[:240],
                    "similarity": 1.0,
                    "score_breakdown": {"overview": 1.0},
                }
            )
        return citations

    async def _knowledge_base_overview_response(
        self,
        knowledge_base_id: str,
        owner_id: str,
        *,
        limit: int,
        diagnostics: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Return a deterministic library overview without requiring lexical overlap."""
        citations = await self._knowledge_base_overview_citations(
            knowledge_base_id,
            owner_id,
            limit=limit,
        )
        if not citations:
            return {
                "answer": "这个知识库当前还没有可供概览的文档。请先上传或新建文档并完成索引。",
                "citations": [],
                "context_chunks_used": 0,
                "tokens_used": 0,
                "model_id": None,
                "strategy_draft": None,
                "reasoning": None,
                "reason_code": "knowledge_base_overview",
                "diagnostic_message": "当前知识库没有可供概览的文档。",
                "diagnostics": diagnostics,
            }

        lines = ["这个知识库当前主要包含以下文档："]
        for index, citation in enumerate(citations, start=1):
            title = str(citation["document_title"])
            preview = str(citation["content"] or "")
            lines.append(f"{index}. 《{title}》" + (f"：{preview}" if preview else ""))

        return {
            "answer": "\n".join(lines),
            "citations": citations,
            "context_chunks_used": len(citations),
            "tokens_used": 0,
            "model_id": None,
            "strategy_draft": None,
            "reasoning": None,
            "reason_code": "knowledge_base_overview",
            "diagnostic_message": "已按当前知识库的文档目录生成概览。",
            "diagnostics": diagnostics,
        }

    async def _auto_index_documents(
        self,
        session,
        knowledge_base_id: str,
        documents: list[KBDocument] | None = None,
    ) -> int:
        """Create keyword chunks for documents that have not been indexed yet."""
        docs = documents or await self._list_indexable_documents(session, knowledge_base_id)
        if not docs:
            return 0

        existing_chunks_by_document: dict[str, list[str]] = {}
        existing_chunks = (
            await session.execute(
                select(DocumentChunk.document_id, DocumentChunk.content).where(
                    DocumentChunk.knowledge_base_id == knowledge_base_id
                )
            )
        ).all()
        for document_id, chunk_content in existing_chunks:
            existing_chunks_by_document.setdefault(str(document_id), []).append(
                str(chunk_content or "")
            )

        stored = 0
        changed = False
        vector_sync_document_ids: set[str] = set()
        for document in docs:
            content = str(getattr(document, "content", "") or "").strip()
            existing_chunks = existing_chunks_by_document.get(str(document.id), [])
            has_chunks = bool(existing_chunks)
            is_indexed = getattr(document, "index_status", None) == "indexed"
            has_legacy_title_only_chunk = chunk_service.has_legacy_title_only_chunk(
                existing_chunks,
                str(getattr(document, "title", "") or ""),
            )
            if not content:
                if is_indexed:
                    document.index_status = "not_indexed"
                    document.indexed_at = None
                    changed = True
                    vector_sync_document_ids.add(str(document.id))
                continue
            if (
                has_chunks
                and is_indexed
                and (self.semantic_retriever.enabled or not has_legacy_title_only_chunk)
            ):
                continue

            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
            )
            changed = True
            chunks = chunk_service.split_text(content)
            for index, chunk in enumerate(chunks):
                session.add(
                    DocumentChunk(
                        document_id=document.id,
                        knowledge_base_id=knowledge_base_id,
                        chunk_index=index,
                        content=chunk,
                        token_count=chunk_service.token_count(chunk),
                    )
                )
                stored += 1

            document.index_status = "indexed" if chunks else "not_indexed"
            document.indexed_at = datetime.utcnow() if chunks else None
            vector_sync_document_ids.add(str(document.id))

        if changed:
            await session.commit()
            for document_id in vector_sync_document_ids:
                await self._sync_vector_document(session, knowledge_base_id, document_id)
        return stored

    async def index_document(
        self, knowledge_base_id: str, document_id: str, owner_id: str, chunks: list[str]
    ) -> int | None:
        async with async_session_maker() as session:
            document = (
                await session.execute(
                    select(KBDocument)
                    .join(KnowledgeBase, KnowledgeBase.id == KBDocument.knowledge_base_id)
                    .where(
                        KBDocument.id == document_id,
                        KBDocument.knowledge_base_id == knowledge_base_id,
                        KnowledgeBase.owner_id == owner_id,
                    )
                )
            ).scalar_one_or_none()
            if document is None:
                return None

            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )

            stored = 0
            for index, chunk in enumerate(chunks):
                session.add(
                    DocumentChunk(
                        document_id=document_id,
                        knowledge_base_id=knowledge_base_id,
                        chunk_index=index,
                        content=chunk,
                        token_count=chunk_service.token_count(chunk),
                    )
                )
                stored += 1

            document.index_status = "indexed" if stored > 0 else "not_indexed"
            document.indexed_at = datetime.utcnow() if stored > 0 else None
            await session.commit()
            await self._sync_vector_document(session, knowledge_base_id, document_id)
            return stored

    async def index_document_by_id(
        self,
        knowledge_base_id: str,
        document_id: str,
        owner_id: str,
    ) -> int | None:
        """Index a stored document by id, splitting its content into chunks.

        Performs the ownership lookup once, splits the document content via
        :class:`ChunkService`, and persists chunks.

        Returns:
            Number of chunks stored, or ``None`` if the document is not found
            or the caller is not its owner.
        """
        async with async_session_maker() as session:
            document = (
                await session.execute(
                    select(KBDocument)
                    .join(KnowledgeBase, KnowledgeBase.id == KBDocument.knowledge_base_id)
                    .where(
                        KBDocument.id == document_id,
                        KBDocument.knowledge_base_id == knowledge_base_id,
                        KnowledgeBase.owner_id == owner_id,
                    )
                )
            ).scalar_one_or_none()
            if document is None:
                return None

            chunks = chunk_service.split_text(str(getattr(document, "content", "") or ""))

            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )

            stored = 0
            for index, chunk in enumerate(chunks):
                session.add(
                    DocumentChunk(
                        document_id=document_id,
                        knowledge_base_id=knowledge_base_id,
                        chunk_index=index,
                        content=chunk,
                        token_count=chunk_service.token_count(chunk),
                    )
                )
                stored += 1

            document.index_status = "indexed" if stored > 0 else "not_indexed"
            document.indexed_at = datetime.utcnow() if stored > 0 else None
            await session.commit()
            await self._sync_vector_document(session, knowledge_base_id, document_id)
            return stored

    def _build_retrieval_query(
        self,
        question: str,
        conversation_history: list[dict[str, Any]] | None,
        settings: dict[str, Any],
    ) -> tuple[str, int]:
        normalized_question = _normalize_text(question)
        if not normalized_question:
            return "", 0
        if not settings.get("use_conversation_memory", True):
            return normalized_question, 0

        history = [_history_message_to_dict(item) for item in (conversation_history or [])]
        lookback = int(settings.get("conversation_lookback_messages") or 0)
        if lookback <= 0 or not history:
            return normalized_question, 0

        recent_history = history[-lookback:]
        should_rewrite = _looks_like_follow_up(normalized_question)
        prior_user_prompts = [
            _normalize_text(item.get("content") or "")
            for item in recent_history
            if item.get("role") == "user"
        ]
        citation_titles: list[str] = []
        for item in recent_history:
            if item.get("role") != "assistant":
                continue
            for citation in item.get("citations") or []:
                if not isinstance(citation, dict):
                    continue
                title = _normalize_text(str(citation.get("document_title") or ""))
                if title and title not in citation_titles:
                    citation_titles.append(title)

        if not should_rewrite and not citation_titles:
            return normalized_question, 0

        query_parts = [normalized_question]
        if prior_user_prompts:
            query_parts.append(f"历史问题：{'；'.join(prior_user_prompts[-2:])}")
        if citation_titles:
            query_parts.append(f"相关文档：{'、'.join(citation_titles[:3])}")
        return " | ".join(query_parts), len(recent_history)

    @staticmethod
    def _metadata_text(document: KBDocument) -> str:
        metadata = getattr(document, "metadata_json", None)
        if not isinstance(metadata, dict):
            return _normalize_text(getattr(document, "file_path", "") or "")

        parts = [str(getattr(document, "file_path", "") or "")]
        for key in (
            "tags",
            "category",
            "symbol",
            "symbol_name",
            "timeframe",
            "source",
            "asset_class",
        ):
            value = metadata.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(item) for item in value[:5] if item)
        return _normalize_text(" ".join(parts))

    def _score_chunk(
        self,
        *,
        question: str,
        retrieval_query: str,
        chunk: DocumentChunk,
        document: KBDocument,
        settings: dict[str, Any],
        search_mode: str,
    ) -> tuple[float, dict[str, float]]:
        title_text = _normalize_text(getattr(document, "title", "") or "")
        content_text = _normalize_text(getattr(chunk, "content", "") or "")
        if chunk_service.has_legacy_title_only_chunk([content_text], title_text):
            return 0.0, {
                "title": 0.0,
                "keyword": 0.0,
                "phrase": 0.0,
                "recency": 0.0,
                "exact_match_boost": 0.0,
            }
        metadata_text = self._metadata_text(document)
        combined_header = _normalize_text(
            " ".join(part for part in (title_text, metadata_text) if part)
        )

        title_score = _keyword_similarity(retrieval_query, combined_header)
        keyword_score = _keyword_similarity(retrieval_query, content_text)
        phrase_score = max(
            _char_jaccard(question, content_text),
            _char_jaccard(question, title_text),
        )
        normalized_question = question.lower()
        content_lower = content_text.lower()
        title_lower = title_text.lower()
        if search_mode == "keyword":
            phrase_score = (
                1.0
                if normalized_question
                and (normalized_question in content_lower or normalized_question in title_lower)
                else 0.0
            )

        updated_at = _safe_datetime(getattr(document, "updated_at", None))
        recency_score = 0.0
        if settings.get("prefer_recent_documents", True) and updated_at is not None:
            age_days = max(
                0.0,
                (datetime.now(timezone.utc) - updated_at).total_seconds() / 86400.0,
            )
            if age_days <= 7:
                recency_score = 1.0
            elif age_days <= 30:
                recency_score = 0.7
            elif age_days <= 180:
                recency_score = 0.4
            else:
                recency_score = 0.1

        if settings.get("prioritize_title_matches", True) and title_score > 0:
            title_score = min(1.0, title_score * 1.15)

        if max(title_score, keyword_score, phrase_score) <= 0:
            return 0.0, {
                "title": round(title_score, 4),
                "keyword": round(keyword_score, 4),
                "phrase": round(phrase_score, 4),
                "recency": round(recency_score, 4),
                "exact_match_boost": 0.0,
            }

        exact_match_boost = 0.0
        if normalized_question and normalized_question in content_lower:
            exact_match_boost = 0.15
        if normalized_question and normalized_question in title_lower:
            exact_match_boost = max(exact_match_boost, 0.2)

        title_weight = float(settings.get("title_weight") or 0.0)
        keyword_weight = float(settings.get("keyword_weight") or 0.0)
        phrase_weight = float(settings.get("phrase_weight") or 0.0)
        recency_weight = float(settings.get("recency_weight") or 0.0)
        if search_mode == "keyword":
            phrase_weight = max(0.05, phrase_weight * 0.25)

        weight_sum = title_weight + keyword_weight + phrase_weight + recency_weight
        if weight_sum <= 0:
            return 0.0, {
                "title": 0.0,
                "keyword": 0.0,
                "phrase": 0.0,
                "recency": 0.0,
                "exact_match_boost": 0.0,
            }

        weighted_score = (
            title_score * title_weight
            + keyword_score * keyword_weight
            + phrase_score * phrase_weight
            + recency_score * recency_weight
        ) / weight_sum
        final_score = min(1.0, weighted_score + exact_match_boost)
        return final_score, {
            "title": round(title_score, 4),
            "keyword": round(keyword_score, 4),
            "phrase": round(phrase_score, 4),
            "recency": round(recency_score, 4),
            "exact_match_boost": round(exact_match_boost, 4),
        }

    @staticmethod
    def _diversify_results(results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        by_document: dict[str, list[dict[str, Any]]] = {}
        for item in results:
            by_document.setdefault(str(item["document_id"]), []).append(item)

        diversified: list[dict[str, Any]] = []
        round_index = 0
        while len(diversified) < limit:
            progressed = False
            for document_id in list(by_document.keys()):
                candidates = by_document[document_id]
                if round_index >= len(candidates):
                    continue
                diversified.append(candidates[round_index])
                progressed = True
                if len(diversified) >= limit:
                    break
            if not progressed:
                break
            round_index += 1
        return diversified

    async def search_with_diagnostics(
        self,
        knowledge_base_id: str,
        owner_id: str,
        query: str,
        top_k: int | None = None,
        min_similarity: float | None = None,
        *,
        search_mode: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        async with async_session_maker() as session:
            kb = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == knowledge_base_id,
                        or_(
                            KnowledgeBase.owner_id == owner_id,
                            KnowledgeBase.is_public.is_(True),
                        ),
                    )
                )
            ).scalar_one_or_none()
            if kb is None:
                return {"results": [], "diagnostics": None, "settings": None}

            settings = merge_knowledge_base_settings(getattr(kb, "settings", None))
            effective_top_k = int(top_k or settings.get("default_top_k") or 8)
            effective_min_similarity = float(
                min_similarity
                if min_similarity is not None
                else settings.get("min_similarity") or 0.0
            )
            effective_search_mode = str(search_mode or settings.get("search_mode") or "hybrid")

            documents = await self._list_indexable_documents(session, knowledge_base_id)
            await self._auto_index_documents(session, knowledge_base_id, documents)

            retrieval_query, history_messages_used = self._build_retrieval_query(
                query,
                conversation_history,
                settings,
            )

            semantic_matches: dict[str, float] = {}
            semantic_status = "disabled"
            semantic_candidate_limit = max(24, min(48, effective_top_k * 4))
            rows: list[tuple[DocumentChunk, KBDocument]] = []
            if effective_search_mode != "keyword" and self.semantic_retriever.enabled:
                semantic_status = "ready"
                expected_semantic_documents = sum(
                    1 for document in documents if document.index_status == "indexed"
                )
                indexed_document_count = await self.semantic_retriever.count_knowledge_base(
                    knowledge_base_id
                )
                if indexed_document_count != expected_semantic_documents:
                    # Only an incomplete or stale vector index requires a
                    # full chunk read.  A completed large knowledge base
                    # should never scan every chunk on each chat request.
                    rows = list(
                        (
                            await session.execute(
                                select(DocumentChunk, KBDocument)
                                .join(KBDocument, KBDocument.id == DocumentChunk.document_id)
                                .where(DocumentChunk.knowledge_base_id == knowledge_base_id)
                            )
                        ).all()
                    )
                    semantic_documents = self._to_semantic_chunks(rows)
                    if self.semantic_retriever.last_error is None:
                        await self.semantic_retriever.upsert_chunks(semantic_documents)
                if self.semantic_retriever.last_error is not None:
                    semantic_status = "degraded"
                else:
                    semantic_matches = {
                        match.chunk_id: match.similarity
                        for match in await self.semantic_retriever.query(
                            knowledge_base_id,
                            retrieval_query or query,
                            limit=semantic_candidate_limit,
                        )
                    }
                    if self.semantic_retriever.last_error is not None:
                        semantic_status = "degraded"
                    elif semantic_matches:
                        rows = list(
                            (
                                await session.execute(
                                    select(DocumentChunk, KBDocument)
                                    .join(KBDocument, KBDocument.id == DocumentChunk.document_id)
                                    .where(
                                        DocumentChunk.knowledge_base_id == knowledge_base_id,
                                        DocumentChunk.document_id.in_(list(semantic_matches)),
                                    )
                                )
                            ).all()
                        )

            if not rows and (effective_search_mode == "keyword" or semantic_status != "ready"):
                rows = list(
                    (
                        await session.execute(
                            select(DocumentChunk, KBDocument)
                            .join(KBDocument, KBDocument.id == DocumentChunk.document_id)
                            .where(DocumentChunk.knowledge_base_id == knowledge_base_id)
                        )
                    ).all()
                )

            ranked: list[dict[str, Any]] = []
            for chunk, document in rows:
                lexical_score, score_breakdown = self._score_chunk(
                    question=query,
                    retrieval_query=retrieval_query,
                    chunk=chunk,
                    document=document,
                    settings=settings,
                    search_mode=effective_search_mode,
                )
                semantic_score = semantic_matches.get(str(chunk.document_id), 0.0)
                if effective_search_mode == "keyword":
                    score = lexical_score
                elif semantic_status == "ready":
                    if effective_search_mode == "semantic":
                        score = semantic_score
                    elif semantic_score > 0:
                        # Semantic recall supplies broad meaning while lexical
                        # overlap preserves exact terms such as symbol codes.
                        score = (semantic_score * 0.75) + (lexical_score * 0.25)
                    else:
                        score = lexical_score * 0.4
                else:
                    # Keep every deployment usable while a local model is
                    # unavailable or still being installed.
                    score = lexical_score
                if score < effective_min_similarity:
                    continue
                score_breakdown["semantic"] = round(semantic_score, 4)
                ranked.append(
                    {
                        "chunk_id": chunk.id,
                        "document_id": chunk.document_id,
                        "document_title": str(getattr(document, "title", "") or "未命名文档"),
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "similarity": round(score, 4),
                        "score_breakdown": score_breakdown,
                    }
                )

            ranked.sort(
                key=lambda item: (
                    item["similarity"],
                    item["score_breakdown"]["title"],
                    item["score_breakdown"]["keyword"],
                ),
                reverse=True,
            )
            diversified = self._diversify_results(ranked, effective_top_k)

            total_indexable_documents = len(documents)
            indexed_documents = sum(
                1 for document in documents if document.index_status == "indexed"
            )
            diagnostics = {
                "retrieval_profile": str(settings.get("retrieval_profile") or "quant_research"),
                "search_mode": effective_search_mode,
                "search_query": retrieval_query or _normalize_text(query),
                "query_rewritten": _normalize_text(retrieval_query) != _normalize_text(query),
                "applied_top_k": effective_top_k,
                "applied_min_similarity": round(effective_min_similarity, 4),
                "history_messages_used": history_messages_used,
                "total_indexable_documents": total_indexable_documents,
                "indexed_documents": indexed_documents,
                "coverage_ratio": round(indexed_documents / total_indexable_documents, 4)
                if total_indexable_documents
                else 0.0,
                "semantic_retrieval_status": semantic_status,
                "semantic_candidates": len(semantic_matches),
                "llm_reranked": False,
            }
            return {
                "results": diversified,
                "diagnostics": diagnostics,
                "settings": settings,
            }

    async def search(
        self,
        knowledge_base_id: str,
        owner_id: str,
        query: str,
        top_k: int | None,
        min_similarity: float | None,
        *,
        search_mode: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> list[dict]:
        payload = await self.search_with_diagnostics(
            knowledge_base_id,
            owner_id,
            query,
            top_k,
            min_similarity,
            search_mode=search_mode,
            conversation_history=conversation_history,
        )
        return payload["results"]

    @staticmethod
    def _build_llm_document_recommendation_response(
        results: list[dict[str, Any]],
        diagnostics: dict[str, Any] | None,
        *,
        llm_selected: bool,
    ) -> dict[str, Any]:
        """Render a concise list after model or semantic document selection."""
        selected: list[dict[str, Any]] = []
        seen_document_ids: set[str] = set()
        for item in results:
            document_id = str(item.get("document_id") or "")
            if not document_id or document_id in seen_document_ids:
                continue
            selected.append(item)
            seen_document_ids.add(document_id)
            if len(selected) >= 6:
                break

        candidate_count = int((diagnostics or {}).get("semantic_candidates") or 0)
        lines = [
            (
                "已由模型根据你的问题，从语义召回的候选文档中筛选出以下重点阅读项："
                if llm_selected
                else "模型重排暂时不可用，以下为语义检索到的重点阅读候选："
            )
        ]
        for index, item in enumerate(selected, start=1):
            title = _normalize_text(str(item.get("document_title") or "未命名文档"))
            preview = _normalize_text(str(item.get("content") or ""))[:220]
            lines.append(f"{index}. 《{title}》" + (f"：{preview}" if preview else ""))
        if candidate_count:
            lines.append(f"\n已先从 {candidate_count} 个语义候选中召回，再由模型重排。")
        return {
            "answer": "\n".join(lines),
            "citations": selected,
            "context_chunks_used": len(selected),
            "tokens_used": 0,
            "model_id": None,
            "strategy_draft": None,
            "reasoning": None,
            "reason_code": (
                "llm_document_recommendation"
                if llm_selected
                else "semantic_document_recommendation"
            ),
            "diagnostic_message": (
                "已完成语义召回与大模型重排。"
                if llm_selected
                else "语义召回已完成；大模型重排暂时不可用。"
            ),
            "diagnostics": diagnostics,
        }

    async def ask(
        self,
        knowledge_base_id: str,
        owner_id: str,
        question: str,
        top_k: int | None,
        min_similarity: float | None,
        assistant_mode: str = "knowledge_qa",
        thinking_mode: bool = False,
        conversation_history: list[dict[str, Any]] | None = None,
        model_id: str | None = None,
    ) -> dict:
        search_payload = await self.search_with_diagnostics(
            knowledge_base_id,
            owner_id,
            question,
            top_k,
            min_similarity,
            conversation_history=conversation_history,
        )
        results = search_payload["results"]
        diagnostics = search_payload["diagnostics"]
        settings = search_payload["settings"] or {}
        if not results:
            if _is_knowledge_base_overview_question(question):
                # A deterministic directory view is only a last-resort
                # fallback.  Normal overview/recommendation questions pass
                # through semantic retrieval and model reranking above.
                overview = await self._knowledge_base_overview_response(
                    knowledge_base_id,
                    owner_id,
                    limit=max(1, min(int(settings.get("default_top_k") or 8), 12)),
                    diagnostics=diagnostics,
                )
                if overview is not None:
                    return overview
            message = "未找到相关内容，请先确认知识库已建立索引且问题与文档内容相关。"
            return {
                "answer": message,
                "citations": [],
                "context_chunks_used": 0,
                "tokens_used": 0,
                "model_id": None,
                "strategy_draft": None,
                "reasoning": None,
                "reason_code": "no_context_found",
                "diagnostic_message": message,
                "diagnostics": diagnostics,
            }

        max_context_chunks = int(settings.get("max_context_chunks") or len(results))
        reranked_results, llm_reranked = await self.ai_chat_service.rerank_citations(
            question=question,
            citations=results,
            user_id=owner_id,
            model_id=model_id,
            max_candidates=max(max_context_chunks * 3, 12),
        )
        if isinstance(diagnostics, dict):
            diagnostics["llm_reranked"] = llm_reranked
        context_results = reranked_results[:max_context_chunks]
        citations = context_results[:3]
        if _is_knowledge_base_overview_question(question):
            return self._build_llm_document_recommendation_response(
                context_results,
                diagnostics,
                llm_selected=llm_reranked,
            )

        ai_enabled = await self.ai_chat_service.can_generate(user_id=owner_id, model_id=model_id)
        generated = await self.ai_chat_service.generate_answer(
            question=question,
            citations=context_results,
            assistant_mode=assistant_mode,
            thinking_mode=thinking_mode,
            conversation_history=conversation_history,
            retrieval_diagnostics=diagnostics,
            knowledge_base_settings=settings,
            user_id=owner_id,
            model_id=model_id,
        )
        if generated is not None:
            strategy_draft = generated.get("strategy_draft")
            if assistant_mode == "backtrader_strategy" and strategy_draft is None:
                local_draft = build_ai_strategy_draft(
                    question,
                    [str(item.get("document_title") or "") for item in citations],
                )
                strategy_draft = local_draft.model_dump()
                if not generated.get("answer"):
                    generated["answer"] = render_ai_strategy_draft_answer(local_draft)
            return {
                "answer": generated["answer"],
                "citations": citations,
                "context_chunks_used": len(context_results),
                "tokens_used": int(generated["tokens_used"]),
                "model_id": generated["model_id"],
                "strategy_draft": strategy_draft,
                "reasoning": generated["reasoning"],
                "reason_code": None,
                "diagnostic_message": None,
                "diagnostics": diagnostics,
            }

        best = context_results[0]
        fallback_reason_code = "ai_provider_failed" if ai_enabled else "ai_not_configured"
        fallback_diagnostic_message = (
            "AI 模型调用失败，已降级返回最相关的知识库片段。"
            if ai_enabled
            else "当前系统未配置生成式 AI 模型，已降级返回最相关的知识库片段。"
        )
        if assistant_mode == "backtrader_strategy":
            draft = build_ai_strategy_draft(
                question,
                [str(item.get("document_title") or "") for item in citations],
            )
            return {
                "answer": render_ai_strategy_draft_answer(draft),
                "citations": citations,
                "context_chunks_used": len(context_results),
                "tokens_used": int(chunk_service.token_count(best["content"])),
                "model_id": None,
                "strategy_draft": draft.model_dump(),
                "reasoning": None,
                "reason_code": fallback_reason_code,
                "diagnostic_message": fallback_diagnostic_message,
                "diagnostics": diagnostics,
            }
        return {
            "answer": self._build_retrieval_fallback_answer(
                question,
                context_results,
                assistant_mode,
                ai_enabled=ai_enabled,
            ),
            "citations": citations,
            "context_chunks_used": len(context_results),
            "tokens_used": int(chunk_service.token_count(best["content"])),
            "model_id": None,
            "strategy_draft": None,
            "reasoning": None,
            "reason_code": fallback_reason_code,
            "diagnostic_message": fallback_diagnostic_message,
            "diagnostics": diagnostics,
        }

    @staticmethod
    def _build_retrieval_fallback_answer(
        question: str,
        results: list[dict[str, Any]],
        assistant_mode: str,
        ai_enabled: bool = False,
    ) -> str:
        best = results[0]
        title = str(best.get("document_title") or "未命名文档")
        content = str(best.get("content") or "").strip()
        unavailable_reason = (
            "AI 模型调用失败，因此先返回最相关的知识库片段。"
            if ai_enabled
            else "当前系统未配置生成式 AI 模型，因此返回的是最相关原文片段而非综合生成答案。"
        )
        if assistant_mode == "backtrader_strategy":
            if ai_enabled:
                return (
                    "AI 模型调用失败，因此无法直接生成完整的 Backtrader 策略代码。\n\n"
                    f"已为你的请求找到最相关的知识库片段，来源《{title}》：\n\n"
                    f"{content}\n\n"
                    "建议：检查 AI_CHAT_* 环境变量、模型服务地址和网络连通性后重试。"
                )
            return (
                "当前系统尚未配置生成式 AI 模型，因此无法直接生成完整的 Backtrader 策略代码。\n\n"
                f"已为你的请求找到最相关的知识库片段，来源《{title}》：\n\n"
                f"{content}\n\n"
                "建议：先配置 AI_CHAT_* 环境变量，再使用“Backtrader策略生成”模式提交一句话策略需求。"
            )
        if assistant_mode == "strategy_idea":
            if ai_enabled:
                return (
                    "AI 模型调用失败，因此先返回最相关的研究资料片段，供你继续构思策略。\n\n"
                    f"来源《{title}》：\n\n{content}"
                )
            return (
                "当前系统尚未配置生成式 AI 模型，因此先返回最相关的研究资料片段，供你继续构思策略。\n\n"
                f"来源《{title}》：\n\n{content}"
            )
        if assistant_mode == "strategy_review":
            if ai_enabled:
                return (
                    "AI 模型调用失败，因此无法自动完成结构化策略审查。\n\n"
                    f"不过系统已找到与你问题最相关的资料《{title}》：\n\n{content}"
                )
            return (
                "当前系统尚未配置生成式 AI 模型，因此无法自动完成结构化策略审查。\n\n"
                f"不过系统已找到与你问题最相关的资料《{title}》：\n\n{content}"
            )
        return (
            f"根据知识库中与“{question}”最相关的片段，来源《{title}》：\n\n"
            f"{content}\n\n"
            f"{unavailable_reason}"
        )


rag_service = RAGService()
