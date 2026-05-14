"""RAG API routes for iteration 129."""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import get_current_user
from app.db.database import async_session_maker
from app.models.knowledge_base import KBDocument, KnowledgeBase
from app.schemas.auth import TokenPayload
from app.schemas.rag import (
    RAGAskRequest,
    RAGAskResponse,
    RAGIndexRequest,
    RAGIndexResponse,
    RAGSearchRequest,
    RAGSearchResponse,
    RAGSearchResult,
)
from app.services.chunk_service import chunk_service
from app.services.rag_service import RAGService

router = APIRouter()


@lru_cache
def get_rag_service() -> RAGService:
    return RAGService()


@router.post("/index", response_model=RAGIndexResponse, summary="Index document")
async def index_document(
    data: RAGIndexRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: RAGService = Depends(get_rag_service),
):
    chunks = chunk_service.split_text("")
    # content is resolved from the stored document itself after ownership validation
    async with async_session_maker() as session:
        document = (
            await session.execute(
                select(KBDocument)
                .join(KnowledgeBase, KnowledgeBase.id == KBDocument.knowledge_base_id)
                .where(
                    KBDocument.id == data.document_id,
                    KBDocument.knowledge_base_id == data.knowledge_base_id,
                    KnowledgeBase.owner_id == current_user.sub,
                )
            )
        ).scalar_one_or_none()
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        chunks = chunk_service.split_text(str(getattr(document, "content", "") or ""))

    stored = await service.index_document(data.knowledge_base_id, data.document_id, current_user.sub, chunks)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return RAGIndexResponse(
        document_id=data.document_id,
        knowledge_base_id=data.knowledge_base_id,
        status="indexed" if stored > 0 else "not_indexed",
        chunks_count=stored,
    )


@router.post("/search", response_model=RAGSearchResponse, summary="Search chunks")
async def search_chunks(
    data: RAGSearchRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: RAGService = Depends(get_rag_service),
):
    results = await service.search(
        data.knowledge_base_id, current_user.sub, data.query, data.top_k, data.min_similarity
    )
    return RAGSearchResponse(
        total=len(results),
        results=[RAGSearchResult.model_validate(item) for item in results],
    )


@router.post("/ask", response_model=RAGAskResponse, summary="Ask knowledge base")
async def ask_knowledge_base(
    data: RAGAskRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: RAGService = Depends(get_rag_service),
):
    result = await service.ask(
        data.knowledge_base_id, current_user.sub, data.question, data.top_k, data.min_similarity
    )
    return RAGAskResponse(**result)
