"""Local vector retrieval for knowledge-base chunks.

The relational ``document_chunks`` table remains the source of truth.  This
module keeps one representative vector per document in local Chroma, which
makes first-time indexing predictable even for very large source documents.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.utils.backend_data_paths import get_backend_data_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SemanticChunk:
    """The minimal chunk data required by the vector store."""

    chunk_id: str
    knowledge_base_id: str
    document_id: str
    document_title: str
    chunk_index: int
    content: str


@dataclass(frozen=True)
class SemanticSearchMatch:
    """A vector result expressed in the application's score convention."""

    chunk_id: str
    similarity: float


class SemanticRetrievalService:
    """Manage local embeddings and retrieve semantically related chunks.

    Imports for Chroma and Sentence Transformers are deliberately lazy.  This
    lets a lightweight or test deployment retain the existing lexical fallback
    instead of failing application startup when optional RAG dependencies are
    absent.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        persistence_path: Path | None = None,
        model_name: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self.enabled = bool(
            getattr(settings, "RAG_VECTOR_ENABLED", True) if enabled is None else enabled
        )
        self.persistence_path = persistence_path or get_backend_data_path("chroma")
        self.model_name = model_name or str(
            getattr(settings, "RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
        )
        self.collection_name = collection_name or str(
            getattr(settings, "RAG_VECTOR_COLLECTION", "knowledge_base_documents_v3")
        )
        self.upsert_batch_size = int(getattr(settings, "RAG_VECTOR_UPSERT_BATCH_SIZE", 128))
        self._collection: Any | None = None
        self._model: Any | None = None
        self._last_error: str | None = None
        self._initialization_lock = threading.Lock()

    @property
    def last_error(self) -> str | None:
        """Return a safe status token for diagnostics, never a raw exception."""
        return self._last_error

    async def warm_up(self) -> bool:
        """Load the local model once during application startup."""
        if not self.enabled:
            return False
        try:
            await asyncio.to_thread(self._ensure_ready)
        except Exception:
            self._mark_unavailable()
            return False
        self._last_error = None
        return True

    async def has_knowledge_base(self, knowledge_base_id: str) -> bool:
        """Return whether this knowledge base already has vectors."""
        if not self.enabled:
            return False
        try:
            return await asyncio.to_thread(self._has_knowledge_base, knowledge_base_id)
        except Exception:
            self._mark_unavailable()
            return False

    async def count_knowledge_base(self, knowledge_base_id: str) -> int:
        """Count indexed documents for one knowledge base.

        This protects against an interrupted first build being mistakenly
        treated as a complete semantic index.
        """
        if not self.enabled:
            return 0
        try:
            count = await asyncio.to_thread(self._count_knowledge_base, knowledge_base_id)
        except Exception:
            self._mark_unavailable()
            return 0
        self._last_error = None
        return count

    async def upsert_chunks(self, chunks: list[SemanticChunk]) -> bool:
        """Embed and persist chunks.  An unavailable index remains non-fatal."""
        if not self.enabled or not chunks:
            return False
        try:
            await asyncio.to_thread(self._upsert_chunks, chunks)
        except Exception:
            self._mark_unavailable()
            return False
        self._last_error = None
        return True

    async def delete_document(self, knowledge_base_id: str, document_id: str) -> bool:
        """Remove stale vectors for a re-indexed or emptied document."""
        if not self.enabled:
            return False
        try:
            await asyncio.to_thread(self._delete_document, knowledge_base_id, document_id)
        except Exception:
            self._mark_unavailable()
            return False
        self._last_error = None
        return True

    async def query(
        self,
        knowledge_base_id: str,
        query: str,
        *,
        limit: int,
    ) -> list[SemanticSearchMatch]:
        """Return the nearest chunks for a question, scoped to one knowledge base."""
        if not self.enabled or not query.strip() or limit <= 0:
            return []
        try:
            matches = await asyncio.to_thread(
                self._query,
                knowledge_base_id,
                query,
                limit,
            )
        except Exception:
            self._mark_unavailable()
            return []
        self._last_error = None
        return matches

    def _ensure_ready(self) -> None:
        if self._collection is not None and self._model is not None:
            return
        with self._initialization_lock:
            if self._collection is not None and self._model is not None:
                return

            # Some desktop Python distributions ship Keras 3 alongside
            # transformers.  Sentence Transformers does not need TensorFlow
            # for inference, and opting out prevents an unrelated Keras
            # import error.
            os.environ.setdefault("USE_TF", "0")
            import chromadb
            from sentence_transformers import SentenceTransformer

            self.persistence_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.persistence_path))
            collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            # Assign only after loading succeeds so a second caller never
            # mistakes a partially initialized model for a usable service.
            model = SentenceTransformer(self.model_name)
            self._collection = collection
            self._model = model

    def _has_knowledge_base(self, knowledge_base_id: str) -> bool:
        self._ensure_ready()
        assert self._collection is not None
        result = self._collection.get(
            where={"knowledge_base_id": knowledge_base_id},
            limit=1,
            include=[],
        )
        return bool(result.get("ids"))

    def _count_knowledge_base(self, knowledge_base_id: str) -> int:
        self._ensure_ready()
        assert self._collection is not None
        result = self._collection.get(
            where={"knowledge_base_id": knowledge_base_id},
            include=[],
        )
        return len(result.get("ids") or [])

    def _upsert_chunks(self, chunks: list[SemanticChunk]) -> None:
        self._ensure_ready()
        assert self._collection is not None
        assert self._model is not None
        for offset in range(0, len(chunks), self.upsert_batch_size):
            batch = chunks[offset : offset + self.upsert_batch_size]
            documents = [
                f"文档标题：{chunk.document_title}\n内容：{chunk.content}".strip()
                for chunk in batch
            ]
            embeddings = self._model.encode(
                documents,
                batch_size=32,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            self._collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                documents=documents,
                embeddings=embeddings.tolist(),
                metadatas=[
                    {
                        "knowledge_base_id": chunk.knowledge_base_id,
                        "document_id": chunk.document_id,
                        "chunk_index": chunk.chunk_index,
                    }
                    for chunk in batch
                ],
            )

    def _delete_document(self, knowledge_base_id: str, document_id: str) -> None:
        self._ensure_ready()
        assert self._collection is not None
        self._collection.delete(
            where={
                "$and": [
                    {"knowledge_base_id": knowledge_base_id},
                    {"document_id": document_id},
                ]
            }
        )

    def _query(
        self,
        knowledge_base_id: str,
        query: str,
        limit: int,
    ) -> list[SemanticSearchMatch]:
        self._ensure_ready()
        assert self._collection is not None
        assert self._model is not None
        query_embedding = self._model.encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()
        result = self._collection.query(
            query_embeddings=query_embedding,
            n_results=limit,
            where={"knowledge_base_id": knowledge_base_id},
            include=["distances"],
        )
        ids = list((result.get("ids") or [[]])[0] or [])
        distances = list((result.get("distances") or [[]])[0] or [])
        return [
            SemanticSearchMatch(
                chunk_id=str(chunk_id),
                similarity=self._distance_to_similarity(distance),
            )
            for chunk_id, distance in zip(ids, distances, strict=False)
        ]

    @staticmethod
    def _distance_to_similarity(distance: float | int | None) -> float:
        """Convert Chroma cosine distance to the existing zero-to-one score."""
        normalized_distance = float(distance or 0.0)
        return round(max(0.0, min(1.0, 1.0 - normalized_distance)), 4)

    def _mark_unavailable(self) -> None:
        # Do not expose dependency paths, provider details, or raw database
        # exceptions to the caller.  The service will retry lazily next time.
        self._last_error = "semantic_index_unavailable"
        logger.warning("Semantic retrieval is unavailable; using lexical fallback", exc_info=True)
