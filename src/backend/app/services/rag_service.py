"""Minimal RAG service for iteration 129."""

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app.db.database import async_session_maker
from app.models.knowledge_base import DocumentChunk, KBDocument, KnowledgeBase
from app.services.ai_chat_service import AIChatService
from app.services.chunk_service import chunk_service
from app.services.strategy_service import build_ai_strategy_draft, render_ai_strategy_draft_answer


def _extract_query_terms(query: str) -> list[str]:
    normalized = re.sub(r"[？?！!,，。；：:\s]+", " ", query.lower()).strip()
    tokens = [token for token in normalized.split() if token]
    if len(tokens) == 1 and any("\u4e00" <= ch <= "\u9fff" for ch in tokens[0]):
        text = tokens[0]
        ngrams = {text[i : i + 2] for i in range(len(text) - 1) if text[i : i + 2].strip()}
        if ngrams:
            return list(ngrams)
    return tokens


def _keyword_similarity(query: str, content: str) -> float:
    query_terms = _extract_query_terms(query)
    haystack = (content or "").lower()
    if not query_terms:
        return 0.0
    hits = sum(1 for term in query_terms if term in haystack)
    return hits / len(query_terms)


class RAGService:
    """Index, search, and simple answer generation."""

    def __init__(self) -> None:
        self.ai_chat_service = AIChatService()

    async def _auto_index_documents(self, session, knowledge_base_id: str) -> int:
        """Create keyword chunks for documents that have not been indexed yet."""
        documents = (
            await session.execute(
                select(KBDocument).where(
                    KBDocument.knowledge_base_id == knowledge_base_id,
                    KBDocument.is_folder.is_(False),
                )
            )
        ).scalars().all()
        if not documents:
            return 0

        existing_document_ids = set(
            (
                await session.execute(
                    select(DocumentChunk.document_id).where(
                        DocumentChunk.knowledge_base_id == knowledge_base_id
                    )
                )
            ).scalars().all()
        )

        stored = 0
        changed = False
        for document in documents:
            content = str(getattr(document, "content", "") or "").strip()
            has_chunks = document.id in existing_document_ids
            is_indexed = getattr(document, "index_status", None) == "indexed"
            if not content:
                if is_indexed:
                    document.index_status = "not_indexed"
                    document.indexed_at = None
                    changed = True
                continue
            if has_chunks and is_indexed:
                continue

            await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
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
            document.indexed_at = datetime.now(timezone.utc) if chunks else None

        if changed:
            await session.commit()
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

            await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))

            stored = 0
            for index, chunk in enumerate(chunks):
                session.add(
                    DocumentChunk(
                        document_id=document_id,
                        knowledge_base_id=knowledge_base_id,
                        chunk_index=index,
                        content=chunk,
                        token_count=len(chunk.split()),
                    )
                )
                stored += 1

            document.index_status = "indexed" if stored > 0 else "not_indexed"
            document.indexed_at = datetime.now(timezone.utc) if stored > 0 else None
            await session.commit()
            return stored

    async def search(
        self, knowledge_base_id: str, owner_id: str, query: str, top_k: int, min_similarity: float
    ) -> list[dict]:
        async with async_session_maker() as session:
            kb = (
                await session.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id, KnowledgeBase.owner_id == owner_id)
                )
            ).scalar_one_or_none()
            if kb is None:
                return []

            await self._auto_index_documents(session, knowledge_base_id)

            rows = (
                await session.execute(
                    select(DocumentChunk, KBDocument.title)
                    .join(KBDocument, KBDocument.id == DocumentChunk.document_id)
                    .where(DocumentChunk.knowledge_base_id == knowledge_base_id)
                )
            ).all()

            ranked: list[dict] = []
            for chunk, title in rows:
                similarity = _keyword_similarity(query, chunk.content)
                if query in chunk.content:
                    similarity = max(similarity, 1.0)
                if similarity < min_similarity:
                    continue
                ranked.append(
                    {
                        "chunk_id": chunk.id,
                        "document_id": chunk.document_id,
                        "document_title": title,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "similarity": similarity,
                    }
                )

            ranked.sort(key=lambda item: item["similarity"], reverse=True)
            return ranked[:top_k]

    async def ask(
        self,
        knowledge_base_id: str,
        owner_id: str,
        question: str,
        top_k: int,
        min_similarity: float,
        assistant_mode: str = "knowledge_qa",
        thinking_mode: bool = False,
    ) -> dict:
        results = await self.search(knowledge_base_id, owner_id, question, top_k, min_similarity)
        if not results:
            return {
                "answer": "未找到相关内容，请先确认知识库已建立索引且问题与文档内容相关。",
                "citations": [],
                "context_chunks_used": 0,
                "tokens_used": 0,
                "model_id": None,
                "strategy_draft": None,
                "reasoning": None,
                "reason_code": "no_context_found",
                "diagnostic_message": "未找到相关内容，请先确认知识库已建立索引且问题与文档内容相关。",
            }

        ai_enabled = self.ai_chat_service.is_enabled()
        generated = await self.ai_chat_service.generate_answer(
            question=question,
            citations=results,
            assistant_mode=assistant_mode,
            thinking_mode=thinking_mode,
        )
        if generated is not None:
            strategy_draft = generated.get("strategy_draft")
            if assistant_mode == "backtrader_strategy" and strategy_draft is None:
                local_draft = build_ai_strategy_draft(
                    question,
                    [str(item.get("document_title") or "") for item in results[:3]],
                )
                strategy_draft = local_draft.model_dump()
                if not generated.get("answer"):
                    generated["answer"] = render_ai_strategy_draft_answer(local_draft)
            return {
                "answer": generated["answer"],
                "citations": results[:3],
                "context_chunks_used": len(results),
                "tokens_used": generated["tokens_used"],
                "model_id": generated["model_id"],
                "strategy_draft": strategy_draft,
                "reasoning": generated["reasoning"],
                "reason_code": None,
                "diagnostic_message": None,
            }

        best = results[0]
        fallback_reason_code = "ai_provider_failed" if ai_enabled else "ai_not_configured"
        fallback_diagnostic_message = (
            "AI 模型调用失败，已降级返回最相关的知识库片段。"
            if ai_enabled
            else "当前系统未配置生成式 AI 模型，已降级返回最相关的知识库片段。"
        )
        if assistant_mode == "backtrader_strategy":
            draft = build_ai_strategy_draft(
                question,
                [str(item.get("document_title") or "") for item in results[:3]],
            )
            return {
                "answer": render_ai_strategy_draft_answer(draft),
                "citations": results[:3],
                "context_chunks_used": len(results),
                "tokens_used": len(best["content"].split()),
                "model_id": None,
                "strategy_draft": draft.model_dump(),
                "reasoning": None,
                "reason_code": fallback_reason_code,
                "diagnostic_message": fallback_diagnostic_message,
            }
        return {
            "answer": self._build_retrieval_fallback_answer(
                question, results, assistant_mode, ai_enabled=ai_enabled
            ),
            "citations": results[:3],
            "context_chunks_used": len(results),
            "tokens_used": len(best["content"].split()),
            "model_id": None,
            "strategy_draft": None,
            "reasoning": None,
            "reason_code": fallback_reason_code,
            "diagnostic_message": fallback_diagnostic_message,
        }

    @staticmethod
    def _build_retrieval_fallback_answer(
        question: str, results: list[dict[str, Any]], assistant_mode: str, ai_enabled: bool = False
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
