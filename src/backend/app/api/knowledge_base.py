"""Knowledge base API routes for iteration 129."""

import typing
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.schemas.auth import TokenPayload
from app.schemas.knowledge_base import (
    KBDocumentCreate,
    KBDocumentListResponse,
    KBDocumentResponse,
    KBDocumentSummaryResponse,
    KBDocumentUpdate,
    KnowledgeBaseCreate,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    ReqDocsImportRequest,
    ReqDocsImportResponse,
)
from app.services.knowledge_base_service import KnowledgeBaseService
from app.utils.backend_data_paths import get_backend_data_path

router = APIRouter()


@lru_cache
def get_knowledge_base_service() -> KnowledgeBaseService:
    return KnowledgeBaseService()


def _get_source_file_path(entity: typing.Any) -> tuple[Path, str] | None:
    metadata = getattr(entity, "metadata_json", None)
    if not isinstance(metadata, dict):
        return None
    source_path = metadata.get("reqdocs_source_file_path")
    source_mime_type = metadata.get("reqdocs_source_mime_type")
    if not isinstance(source_path, str) or not source_path:
        return None
    path = Path(source_path).resolve()
    allowed_root = get_backend_data_path("reqdocs_source_files").resolve()
    try:
        path.relative_to(allowed_root)
    except ValueError:
        return None
    return path, source_mime_type if isinstance(
        source_mime_type, str
    ) and source_mime_type else "application/octet-stream"


@router.get("/", response_model=KnowledgeBaseListResponse, summary="List knowledge bases")
async def list_knowledge_bases(
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
) -> typing.Any:
    total, items = await service.list_knowledge_bases(
        current_user.sub, skip=skip, limit=limit, search=search
    )
    return KnowledgeBaseListResponse(
        total=total,
        items=[KnowledgeBaseResponse.model_validate(item) for item in items],
        skip=skip,
        limit=limit,
    )


@router.post(
    "/",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create knowledge base",
)
async def create_knowledge_base(
    data: KnowledgeBaseCreate,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    return await service.create_knowledge_base(current_user.sub, data)


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse, summary="Get knowledge base")
async def get_knowledge_base(
    kb_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    entity = await service.get_knowledge_base(kb_id, current_user.sub)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
        )
    return entity


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse, summary="Update knowledge base")
async def update_knowledge_base(
    kb_id: str,
    data: KnowledgeBaseUpdate,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    entity = await service.update_knowledge_base(kb_id, current_user.sub, data)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
        )
    return entity


@router.delete("/{kb_id}", summary="Delete knowledge base", response_model=None)
async def delete_knowledge_base(
    kb_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    success = await service.delete_knowledge_base(kb_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
        )
    return {"message": "Knowledge base deleted"}


@router.get("/{kb_id}/documents/", response_model=KBDocumentListResponse, summary="List documents")
async def list_documents(
    kb_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    items = await service.list_documents(kb_id, current_user.sub)
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
        )
    return KBDocumentListResponse(
        total=len(items),
        items=[KBDocumentSummaryResponse.model_validate(item) for item in items],
    )


@router.post(
    "/{kb_id}/documents/",
    response_model=KBDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create document",
)
async def create_document(
    kb_id: str,
    data: KBDocumentCreate,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    try:
        entity = await service.create_document(kb_id, current_user.sub, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
        )
    return entity


@router.get(
    "/{kb_id}/documents/{doc_id}", response_model=KBDocumentResponse, summary="Get document"
)
async def get_document(
    kb_id: str,
    doc_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    entity = await service.get_document(kb_id, doc_id, current_user.sub)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return entity


@router.get(
    "/{kb_id}/documents/{doc_id}/source-file",
    summary="Get document source file",
    response_model=None,
)
async def get_document_source_file(
    kb_id: str,
    doc_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    entity = await service.get_document(kb_id, doc_id, current_user.sub)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    source_info = _get_source_file_path(entity)
    if source_info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found")
    path, media_type = source_info
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found")
    return FileResponse(path=path, filename=path.name, media_type=media_type)


@router.put(
    "/{kb_id}/documents/{doc_id}", response_model=KBDocumentResponse, summary="Update document"
)
async def update_document(
    kb_id: str,
    doc_id: str,
    data: KBDocumentUpdate,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    try:
        entity = await service.update_document(kb_id, doc_id, current_user.sub, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return entity


@router.delete("/{kb_id}/documents/{doc_id}", summary="Delete document", response_model=None)
async def delete_document(
    kb_id: str,
    doc_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    success = await service.delete_document(kb_id, doc_id, current_user.sub)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"message": "Document deleted"}


@router.post(
    "/import/reqdocs",
    response_model=ReqDocsImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import ReqDocs payload",
)
async def import_reqdocs_payload(
    data: ReqDocsImportRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
) -> typing.Any:
    kb, imported = await service.import_reqdocs_payload(current_user.sub, data)
    return ReqDocsImportResponse(
        knowledge_base=KnowledgeBaseResponse.model_validate(kb),
        imported_documents=imported,
    )
