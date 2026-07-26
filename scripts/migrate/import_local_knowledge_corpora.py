#!/usr/bin/env python3
"""Import local quantitative HTML and systematic-trading PDF corpora.

The importer has no document-count limit. It is idempotent: source paths and
SHA-256 hashes identify unchanged documents, while title matching upgrades
documents imported by older scripts that did not store source metadata.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

from sqlalchemy import delete, func, select


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.database import async_session_maker  # noqa: E402
from app.models.knowledge_base import DocumentChunk, KBDocument, KnowledgeBase  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.chunk_service import chunk_service  # noqa: E402
from app.utils.knowledge_base_settings import default_knowledge_base_settings  # noqa: E402


DEFAULT_QUANT_DIR = Path("/home/yun/Documents/论文/论文")
DEFAULT_SYSTEM_DIR = Path("/home/yun/Documents/system_trade_pdf")
DEFAULT_QUANT_KB = "云子量化文章库"
DEFAULT_SYSTEM_KB = "系统交易者知识库"
_BLOCK_TAGS = {"article", "blockquote", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "p", "pre", "section", "tr"}
_IGNORED_TAGS = {"footer", "nav", "noscript", "script", "style", "svg"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


@dataclass(frozen=True)
class Corpus:
    key: str
    directory: Path
    suffix: str
    knowledge_base_name: str
    description: str


@dataclass(frozen=True)
class ExtractedDocument:
    path: Path
    title: str
    content: str
    source_hash: str
    source_format: str
    source_url: str | None = None


class ArticleHTMLParser(HTMLParser):
    """Extract the saved article body without styles, scripts, or images."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.content_parts: list[str] = []
        self._stack: list[str] = []
        self._content_depth: int | None = None
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        attributes = dict(attrs)
        if normalized not in _VOID_TAGS:
            self._stack.append(normalized)
        if normalized in _IGNORED_TAGS:
            self._ignored_depth += 1
        classes = set(str(attributes.get("class") or "").split())
        if self._content_depth is None and "content" in classes:
            self._content_depth = len(self._stack)
        if normalized == "title":
            self._in_title = True
        if self._content_depth is not None and normalized in _BLOCK_TAGS:
            self.content_parts.append("\n\n")
        if self._content_depth is not None and normalized == "li":
            self.content_parts.append("- ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized == "title":
            self._in_title = False
        if normalized in _IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1
        if self._stack:
            self._stack.pop()
        if self._content_depth is not None and len(self._stack) < self._content_depth:
            self._content_depth = None

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        if self._content_depth is not None and not self._ignored_depth:
            self.content_parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def content(self) -> str:
        return normalize_content("".join(self.content_parts))


def normalize_content(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.replace("\r", "").split("\n")]
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs).strip()


def normalize_title(value: str) -> str:
    return " ".join(value.split()).strip().casefold()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_html(path: Path) -> ExtractedDocument:
    raw = path.read_text(encoding="utf-8", errors="replace")
    parser = ArticleHTMLParser()
    parser.feed(raw)
    title = parser.title or re.sub(r"^\d+_", "", path.stem)
    source_match = re.search(r"原文链接\s*:.*?href=[\"']([^\"']+)", raw, flags=re.DOTALL)
    body = parser.content
    if not body:
        raise ValueError("article body is empty")
    source_url = source_match.group(1).strip() if source_match else None
    front_matter = [f"# {title}", f"来源文件：{path.name}"]
    if source_url:
        front_matter.append(f"原文链接：{source_url}")
    content = "\n\n".join([*front_matter, body])
    return ExtractedDocument(path, title, content, file_sha256(path), "html", source_url)


def extract_pdf(path: Path) -> ExtractedDocument:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    page_text = [str(page.extract_text() or "").strip() for page in reader.pages]
    body = normalize_content("\n\n".join(text for text in page_text if text))
    if not body:
        raise ValueError("PDF contains no extractable text")
    title = re.sub(r"\.en$", "", path.stem, flags=re.IGNORECASE).strip()
    content = f"# {title}\n\n来源文件：{path.name}\n\n{body}"
    return ExtractedDocument(path, title, content, file_sha256(path), "pdf")


def iter_source_files(corpus: Corpus) -> list[Path]:
    if not corpus.directory.is_dir():
        raise FileNotFoundError(f"source directory does not exist: {corpus.directory}")
    return sorted(
        (path for path in corpus.directory.rglob(f"*{corpus.suffix}") if path.is_file()),
        key=lambda path: str(path).casefold(),
    )


def extract_document(path: Path, source_format: str) -> ExtractedDocument:
    if source_format == "html":
        return extract_html(path)
    if source_format == "pdf":
        return extract_pdf(path)
    raise ValueError(f"unsupported source format: {source_format}")


async def resolve_owner_id(explicit_owner_id: str | None, quant_kb_name: str) -> str:
    async with async_session_maker() as session:
        if explicit_owner_id:
            owner = await session.get(User, explicit_owner_id)
            if owner is None:
                raise ValueError(f"owner does not exist: {explicit_owner_id}")
            return str(owner.id)

        existing_owner = (
            await session.execute(
                select(KnowledgeBase.owner_id)
                .where(KnowledgeBase.name == quant_kb_name)
                .order_by(KnowledgeBase.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing_owner:
            return str(existing_owner)

        first_active_user = (
            await session.execute(
                select(User.id).where(User.is_active.is_(True)).order_by(User.created_at.asc()).limit(1)
            )
        ).scalar_one_or_none()
        if not first_active_user:
            raise ValueError("no active user is available to own the knowledge bases")
        return str(first_active_user)


async def ensure_knowledge_base(session, owner_id: str, corpus: Corpus) -> KnowledgeBase:
    knowledge_base = (
        await session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.owner_id == owner_id,
                KnowledgeBase.name == corpus.knowledge_base_name,
            )
        )
    ).scalar_one_or_none()
    if knowledge_base is not None:
        return knowledge_base

    settings = default_knowledge_base_settings()
    settings.update(
        {
            "retrieval_profile": "quant_research",
            "search_mode": "hybrid",
            "default_top_k": 8,
            "quant_focus": "strategy_research",
        }
    )
    knowledge_base = KnowledgeBase(
        owner_id=owner_id,
        name=corpus.knowledge_base_name,
        description=corpus.description,
        is_public=True,
        document_count=0,
        settings=settings,
    )
    session.add(knowledge_base)
    await session.flush()
    return knowledge_base


async def load_existing_documents(session, knowledge_base_id: str) -> tuple[dict[str, KBDocument], dict[str, KBDocument]]:
    documents = list(
        (
            await session.execute(
                select(KBDocument).where(KBDocument.knowledge_base_id == knowledge_base_id)
            )
        ).scalars()
    )
    by_path: dict[str, KBDocument] = {}
    by_title: dict[str, KBDocument] = {}
    for document in documents:
        metadata = document.metadata_json if isinstance(document.metadata_json, dict) else {}
        source_path = str(metadata.get("source_path") or "")
        if source_path:
            by_path[source_path] = document
        by_title.setdefault(normalize_title(str(document.title or "")), document)
    return by_path, by_title


async def store_document(
    session,
    knowledge_base_id: str,
    corpus: Corpus,
    extracted: ExtractedDocument,
    by_path: dict[str, KBDocument],
    by_title: dict[str, KBDocument],
) -> str:
    source_path = str(extracted.path.resolve())
    document = by_path.get(source_path) or by_title.get(normalize_title(extracted.title))
    metadata = document.metadata_json if document is not None and isinstance(document.metadata_json, dict) else {}
    if (
        document is not None
        and metadata.get("source_sha256") == extracted.source_hash
        and document.index_status == "indexed"
    ):
        return "skipped"

    if document is None:
        document = KBDocument(
            knowledge_base_id=knowledge_base_id,
            title=extracted.title,
            content=extracted.content,
            content_type="markdown",
            file_path=source_path,
            status="published",
            index_status="not_indexed",
        )
        session.add(document)
        await session.flush()
        action = "created"
    else:
        document.title = extracted.title
        document.content = extracted.content
        document.content_type = "markdown"
        document.file_path = source_path
        document.status = "published"
        action = "updated"

    document.metadata_json = {
        **metadata,
        "corpus": corpus.key,
        "source_path": source_path,
        "source_sha256": extracted.source_hash,
        "source_format": extracted.source_format,
        "source_url": extracted.source_url,
    }
    await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    chunks = chunk_service.split_text(extracted.content)
    for chunk_index, chunk in enumerate(chunks):
        session.add(
            DocumentChunk(
                document_id=document.id,
                knowledge_base_id=knowledge_base_id,
                chunk_index=chunk_index,
                content=chunk,
                token_count=chunk_service.token_count(chunk),
                source_type=extracted.source_format,
            )
        )
    document.index_status = "indexed" if chunks else "not_indexed"
    document.indexed_at = datetime.now(timezone.utc) if chunks else None
    by_path[source_path] = document
    by_title[normalize_title(extracted.title)] = document
    return action


async def import_corpus(owner_id: str, corpus: Corpus, batch_size: int, dry_run: bool) -> dict[str, int]:
    paths = iter_source_files(corpus)
    totals = {"discovered": len(paths), "created": 0, "updated": 0, "skipped": 0, "failed": 0}
    if dry_run:
        print(f"{corpus.key}: discovered {len(paths)} {corpus.suffix} files")
        return totals

    async with async_session_maker() as session:
        knowledge_base = await ensure_knowledge_base(session, owner_id, corpus)
        knowledge_base_id = str(knowledge_base.id)
        by_path, by_title = await load_existing_documents(session, knowledge_base_id)
        for index, path in enumerate(paths, start=1):
            try:
                extracted = extract_document(path, corpus.suffix.lstrip("."))
                action = await store_document(
                    session,
                    knowledge_base_id,
                    corpus,
                    extracted,
                    by_path,
                    by_title,
                )
                totals[action] += 1
            except Exception as exc:
                totals["failed"] += 1
                print(f"{corpus.key}: failed {path.name}: {exc}", file=sys.stderr)
            if index % batch_size == 0:
                await session.commit()
                print(f"{corpus.key}: processed {index}/{len(paths)}")

        document_count = (
            await session.execute(
                select(func.count()).select_from(KBDocument).where(
                    KBDocument.knowledge_base_id == knowledge_base_id
                )
            )
        ).scalar_one()
        knowledge_base.document_count = int(document_count)
        await session.commit()
        print(f"{corpus.key}: knowledge_base={knowledge_base_id} documents={document_count} stats={totals}")
    return totals


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quant-dir", type=Path, default=DEFAULT_QUANT_DIR)
    parser.add_argument("--system-dir", type=Path, default=DEFAULT_SYSTEM_DIR)
    parser.add_argument("--quant-kb-name", default=DEFAULT_QUANT_KB)
    parser.add_argument("--system-kb-name", default=DEFAULT_SYSTEM_KB)
    parser.add_argument("--owner-id", default=None)
    parser.add_argument("--only", choices=("all", "quant", "system"), default="all")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> int:
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1")
    owner_id = await resolve_owner_id(args.owner_id, args.quant_kb_name)
    corpora: Iterable[Corpus] = (
        Corpus(
            "quant",
            args.quant_dir.resolve(),
            ".html",
            args.quant_kb_name,
            "本地量化研究、策略设计、资产配置与风险管理文章全文库。",
        ),
        Corpus(
            "system",
            args.system_dir.resolve(),
            ".pdf",
            args.system_kb_name,
            "Better System Trader 系统交易访谈与方法论全文库。",
        ),
    )
    selected = [corpus for corpus in corpora if args.only == "all" or args.only == corpus.key]
    failed = 0
    for corpus in selected:
        totals = await import_corpus(owner_id, corpus, args.batch_size, args.dry_run)
        failed += totals["failed"]
    return 1 if failed else 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(async_main(args))
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
