"""RAG API routes for iteration 129.

Routes only handle request parsing, schema mapping, and HTTP error coding.
All DB access lives in :class:`app.services.rag_service.RAGService`.
"""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
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
    stored = await service.index_document_by_id(
        knowledge_base_id=data.knowledge_base_id,
        document_id=data.document_id,
        owner_id=current_user.sub,
    )
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
    payload = await service.search_with_diagnostics(
        data.knowledge_base_id,
        current_user.sub,
        data.query,
        data.top_k,
        data.min_similarity,
        search_mode=data.search_mode,
    )
    results = payload["results"]
    return RAGSearchResponse(
        total=len(results),
        results=[RAGSearchResult.model_validate(item) for item in results],
        diagnostics=payload.get("diagnostics"),
    )


@router.post("/ask", response_model=RAGAskResponse, summary="Ask knowledge base")
async def ask_knowledge_base(
    data: RAGAskRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: RAGService = Depends(get_rag_service),
):
    result = await service.ask(
        data.knowledge_base_id,
        current_user.sub,
        data.question,
        data.top_k,
        data.min_similarity,
        thinking_mode=data.thinking_mode,
    )
    return RAGAskResponse(**result)
