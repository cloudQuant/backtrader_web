"""Unit tests for app/api/knowledge_base.py.

Tests cover all knowledge base CRUD endpoints with mocked service layer:
- List, create, get, update, delete knowledge bases
- List, create, get, update, delete documents
- Source file download
- ReqDocs import
- Error cases (404, 400)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

_USER = SimpleNamespace(sub="u1")


def _make_kb(kb_id="kb-1", name="Test KB"):
    """Create a mock knowledge base entity that passes Pydantic validation."""
    from datetime import datetime, timezone

    return SimpleNamespace(
        id=kb_id,
        owner_id="u1",
        name=name,
        description="A test knowledge base",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        document_count=2,
        is_public=False,
        settings=SimpleNamespace(
            retrieval_profile="quant_research",
            search_mode="hybrid",
            top_k=10,
            min_similarity=0.3,
            context_chunk_budget=8000,
            prompt_suffix=None,
        ),
        retrieval_settings=None,
        metadata_json=None,
    )


def _make_doc(doc_id="doc-1", kb_id="kb-1"):
    """Create a mock document entity that passes Pydantic validation."""
    from datetime import datetime, timezone

    return SimpleNamespace(
        id=doc_id,
        knowledge_base_id=kb_id,
        title="Test Document",
        content="Some content here",
        content_type="text",
        file_path=None,
        is_folder=False,
        parent_id=None,
        sort_order=0,
        status="published",
        index_status="indexed",
        indexed_at=None,
        metadata_json=None,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


class _MockService:
    """Mock KnowledgeBaseService."""

    def __init__(self):
        self.list_knowledge_bases = AsyncMock(return_value=(1, [_make_kb()]))
        self.create_knowledge_base = AsyncMock(return_value=_make_kb())
        self.get_knowledge_base = AsyncMock(return_value=_make_kb())
        self.update_knowledge_base = AsyncMock(return_value=_make_kb())
        self.delete_knowledge_base = AsyncMock(return_value=True)
        self.list_documents = AsyncMock(return_value=[_make_doc()])
        self.create_document = AsyncMock(return_value=_make_doc())
        self.get_document = AsyncMock(return_value=_make_doc())
        self.update_document = AsyncMock(return_value=_make_doc())
        self.delete_document = AsyncMock(return_value=True)
        self.import_reqdocs_payload = AsyncMock(return_value=(_make_kb(), 3))


# ══════════════════════════════════════════════════════════════════════════════
# Knowledge Base CRUD
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_knowledge_bases():
    """List knowledge bases returns paginated results."""
    from app.api.knowledge_base import list_knowledge_bases

    svc = _MockService()
    result = await list_knowledge_bases(
        current_user=_USER, service=svc, skip=0, limit=20, search=None
    )
    assert result.total == 1
    assert len(result.items) == 1
    svc.list_knowledge_bases.assert_called_once_with("u1", skip=0, limit=20, search=None)


@pytest.mark.asyncio
async def test_list_knowledge_bases_with_search():
    """List knowledge bases with search filter."""
    from app.api.knowledge_base import list_knowledge_bases

    svc = _MockService()
    svc.list_knowledge_bases = AsyncMock(return_value=(0, []))
    result = await list_knowledge_bases(
        current_user=_USER, service=svc, skip=0, limit=20, search="test"
    )
    assert result.total == 0
    svc.list_knowledge_bases.assert_called_once_with("u1", skip=0, limit=20, search="test")


@pytest.mark.asyncio
async def test_create_knowledge_base():
    """Create knowledge base returns created entity."""
    from app.api.knowledge_base import create_knowledge_base

    svc = _MockService()
    data = SimpleNamespace(name="New KB", description="desc")
    result = await create_knowledge_base(data=data, current_user=_USER, service=svc)
    assert result.name == "Test KB"
    svc.create_knowledge_base.assert_called_once_with("u1", data)


@pytest.mark.asyncio
async def test_get_knowledge_base_success():
    """Get knowledge base returns entity."""
    from app.api.knowledge_base import get_knowledge_base

    svc = _MockService()
    result = await get_knowledge_base(kb_id="kb-1", current_user=_USER, service=svc)
    assert result.id == "kb-1"


@pytest.mark.asyncio
async def test_get_knowledge_base_not_found():
    """Get knowledge base raises 404 when not found."""
    from app.api.knowledge_base import get_knowledge_base

    svc = _MockService()
    svc.get_knowledge_base = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_knowledge_base(kb_id="missing", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_knowledge_base_success():
    """Update knowledge base returns updated entity."""
    from app.api.knowledge_base import update_knowledge_base

    svc = _MockService()
    data = SimpleNamespace(name="Updated")
    result = await update_knowledge_base(kb_id="kb-1", data=data, current_user=_USER, service=svc)
    assert result.id == "kb-1"


@pytest.mark.asyncio
async def test_update_knowledge_base_not_found():
    """Update knowledge base raises 404 when not found."""
    from app.api.knowledge_base import update_knowledge_base

    svc = _MockService()
    svc.update_knowledge_base = AsyncMock(return_value=None)
    data = SimpleNamespace(name="Updated")
    with pytest.raises(HTTPException) as exc_info:
        await update_knowledge_base(kb_id="missing", data=data, current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_knowledge_base_success():
    """Delete knowledge base returns success message."""
    from app.api.knowledge_base import delete_knowledge_base

    svc = _MockService()
    result = await delete_knowledge_base(kb_id="kb-1", current_user=_USER, service=svc)
    assert result["message"] == "Knowledge base deleted"


@pytest.mark.asyncio
async def test_delete_knowledge_base_not_found():
    """Delete knowledge base raises 404 when not found."""
    from app.api.knowledge_base import delete_knowledge_base

    svc = _MockService()
    svc.delete_knowledge_base = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc_info:
        await delete_knowledge_base(kb_id="missing", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# Document CRUD
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_documents_success():
    """List documents returns items."""
    from app.api.knowledge_base import list_documents

    svc = _MockService()
    result = await list_documents(kb_id="kb-1", current_user=_USER, service=svc)
    assert result.total == 1


@pytest.mark.asyncio
async def test_list_documents_kb_not_found():
    """List documents raises 404 when KB not found."""
    from app.api.knowledge_base import list_documents

    svc = _MockService()
    svc.list_documents = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await list_documents(kb_id="missing", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_document_success():
    """Create document returns created entity."""
    from app.api.knowledge_base import create_document

    svc = _MockService()
    data = SimpleNamespace(title="New Doc", content="content", doc_type="text")
    result = await create_document(kb_id="kb-1", data=data, current_user=_USER, service=svc)
    assert result.id == "doc-1"


@pytest.mark.asyncio
async def test_create_document_kb_not_found():
    """Create document raises 404 when KB not found."""
    from app.api.knowledge_base import create_document

    svc = _MockService()
    svc.create_document = AsyncMock(return_value=None)
    data = SimpleNamespace(title="New Doc", content="content", doc_type="text")
    with pytest.raises(HTTPException) as exc_info:
        await create_document(kb_id="missing", data=data, current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_document_value_error():
    """Create document raises 400 on ValueError."""
    from app.api.knowledge_base import create_document

    svc = _MockService()
    svc.create_document = AsyncMock(side_effect=ValueError("invalid content"))
    data = SimpleNamespace(title="Bad Doc", content="", doc_type="text")
    with pytest.raises(HTTPException) as exc_info:
        await create_document(kb_id="kb-1", data=data, current_user=_USER, service=svc)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_document_success():
    """Get document returns entity."""
    from app.api.knowledge_base import get_document

    svc = _MockService()
    result = await get_document(kb_id="kb-1", doc_id="doc-1", current_user=_USER, service=svc)
    assert result.id == "doc-1"


@pytest.mark.asyncio
async def test_get_document_not_found():
    """Get document raises 404 when not found."""
    from app.api.knowledge_base import get_document

    svc = _MockService()
    svc.get_document = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_document(kb_id="kb-1", doc_id="missing", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_document_success():
    """Update document returns updated entity."""
    from app.api.knowledge_base import update_document

    svc = _MockService()
    data = SimpleNamespace(title="Updated Doc")
    result = await update_document(
        kb_id="kb-1", doc_id="doc-1", data=data, current_user=_USER, service=svc
    )
    assert result.id == "doc-1"


@pytest.mark.asyncio
async def test_update_document_not_found():
    """Update document raises 404 when not found."""
    from app.api.knowledge_base import update_document

    svc = _MockService()
    svc.update_document = AsyncMock(return_value=None)
    data = SimpleNamespace(title="Updated")
    with pytest.raises(HTTPException) as exc_info:
        await update_document(
            kb_id="kb-1", doc_id="missing", data=data, current_user=_USER, service=svc
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_document_value_error():
    """Update document raises 400 on ValueError."""
    from app.api.knowledge_base import update_document

    svc = _MockService()
    svc.update_document = AsyncMock(side_effect=ValueError("bad data"))
    data = SimpleNamespace(title="Bad")
    with pytest.raises(HTTPException) as exc_info:
        await update_document(
            kb_id="kb-1", doc_id="doc-1", data=data, current_user=_USER, service=svc
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_document_success():
    """Delete document returns success message."""
    from app.api.knowledge_base import delete_document

    svc = _MockService()
    result = await delete_document(kb_id="kb-1", doc_id="doc-1", current_user=_USER, service=svc)
    assert result["message"] == "Document deleted"


@pytest.mark.asyncio
async def test_delete_document_not_found():
    """Delete document raises 404 when not found."""
    from app.api.knowledge_base import delete_document

    svc = _MockService()
    svc.delete_document = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc_info:
        await delete_document(kb_id="kb-1", doc_id="missing", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# Source File Download
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_document_source_file_doc_not_found():
    """Source file download raises 404 when document not found."""
    from app.api.knowledge_base import get_document_source_file

    svc = _MockService()
    svc.get_document = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_document_source_file(
            kb_id="kb-1", doc_id="missing", current_user=_USER, service=svc
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_document_source_file_no_metadata():
    """Source file download raises 404 when no source metadata."""
    from app.api.knowledge_base import get_document_source_file

    svc = _MockService()
    doc = _make_doc()
    doc.metadata_json = None
    svc.get_document = AsyncMock(return_value=doc)
    with pytest.raises(HTTPException) as exc_info:
        await get_document_source_file(
            kb_id="kb-1", doc_id="doc-1", current_user=_USER, service=svc
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_document_source_file_path_traversal():
    """Source file download rejects path traversal attempts."""
    from app.api.knowledge_base import get_document_source_file

    svc = _MockService()
    doc = _make_doc()
    doc.metadata_json = {
        "reqdocs_source_file_path": "/etc/passwd",
        "reqdocs_source_mime_type": "text/plain",
    }
    svc.get_document = AsyncMock(return_value=doc)
    with pytest.raises(HTTPException) as exc_info:
        await get_document_source_file(
            kb_id="kb-1", doc_id="doc-1", current_user=_USER, service=svc
        )
    assert exc_info.value.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# ReqDocs Import
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_import_reqdocs_payload():
    """Import reqdocs returns KB and document count."""
    from app.api.knowledge_base import import_reqdocs_payload

    svc = _MockService()
    data = SimpleNamespace(
        knowledge_base_name="Imported KB",
        documents=[],
    )
    result = await import_reqdocs_payload(data=data, current_user=_USER, service=svc)
    assert result.imported_documents == 3


# ══════════════════════════════════════════════════════════════════════════════
# _get_source_file_path helper
# ══════════════════════════════════════════════════════════════════════════════


def test_get_source_file_path_none_metadata():
    """Returns None when metadata_json is None."""
    from app.api.knowledge_base import _get_source_file_path

    entity = SimpleNamespace(metadata_json=None)
    assert _get_source_file_path(entity) is None


def test_get_source_file_path_empty_source():
    """Returns None when source path is empty."""
    from app.api.knowledge_base import _get_source_file_path

    entity = SimpleNamespace(metadata_json={"reqdocs_source_file_path": ""})
    assert _get_source_file_path(entity) is None


def test_get_source_file_path_not_dict():
    """Returns None when metadata_json is not a dict."""
    from app.api.knowledge_base import _get_source_file_path

    entity = SimpleNamespace(metadata_json="not a dict")
    assert _get_source_file_path(entity) is None
