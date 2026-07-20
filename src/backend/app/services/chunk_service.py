"""Document chunking helpers used by knowledge-base retrieval."""

import re

_MARKDOWN_HEADING_PATTERN = re.compile(r"^#{1,6}\s+\S")
_NUMBERED_HEADING_PATTERN = re.compile(r"^(?:\d+|[一二三四五六七八九十]+)[.、．]\s*\S")
_SHORT_HEADING_MAX_LENGTH = 80
_METADATA_LINE_PREFIXES = (
    "来源：",
    "来源:",
    "原文发布时间：",
    "原文发布时间:",
    "采集时间：",
    "采集时间:",
    "发布日期：",
    "发布日期:",
    "作者：",
    "作者:",
)


class ChunkService:
    """Split documents into retrieval-ready chunks.

    Markdown headings carry important context, but a heading on its own is not
    useful evidence for a grounded answer.  Keep it together with the first
    substantive paragraph that follows so a title match cannot surface an
    otherwise empty-looking citation.
    """

    @staticmethod
    def _is_standalone_heading(paragraph: str) -> bool:
        """Return whether a short paragraph is a structural heading."""
        normalized = paragraph.strip()
        if len(normalized) > _SHORT_HEADING_MAX_LENGTH:
            return False
        return bool(
            _MARKDOWN_HEADING_PATTERN.match(normalized)
            or _NUMBERED_HEADING_PATTERN.match(normalized)
            or normalized in {"导读", "结语", "总结", "参考资料", "附录"}
        )

    @staticmethod
    def _is_metadata_block(paragraph: str) -> bool:
        """Return whether a paragraph contains only source/front-matter metadata."""
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        return bool(lines) and all(line.startswith(_METADATA_LINE_PREFIXES) for line in lines)

    @staticmethod
    def split_text(content: str) -> list[str]:
        """Split text while retaining standalone headings with their content."""
        text = (content or "").strip()
        if not text:
            return []
        paragraphs = [
            part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()
        ]
        if not paragraphs:
            return [text]

        chunks: list[str] = []
        pending_headings: list[str] = []
        for paragraph in paragraphs:
            if (
                ChunkService._is_standalone_heading(paragraph)
                or ChunkService._is_metadata_block(paragraph)
            ):
                pending_headings.append(paragraph)
                continue

            if pending_headings:
                chunks.append("\n\n".join([*pending_headings, paragraph]))
                pending_headings.clear()
            else:
                chunks.append(paragraph)

        if pending_headings:
            # A document consisting only of headings is still searchable, but
            # do not leave a trailing heading separate from useful evidence.
            if chunks:
                chunks[-1] = "\n\n".join([chunks[-1], *pending_headings])
            else:
                chunks.append("\n\n".join(pending_headings))

        return chunks

    @staticmethod
    def has_legacy_title_only_chunk(chunks: list[str], title: str) -> bool:
        """Detect old indexes whose title chunk lacks any substantive body text."""
        normalized_title = re.sub(r"^#+\s*", "", (title or "").strip())
        if not normalized_title:
            return False
        for chunk in chunks:
            lines = [line.strip() for line in str(chunk or "").splitlines() if line.strip()]
            if not lines:
                continue
            normalized_chunk_title = re.sub(r"^#+\s*", "", lines[0])
            if normalized_chunk_title != normalized_title:
                continue
            if len(lines) == 1 or all(
                line.startswith(_METADATA_LINE_PREFIXES) for line in lines[1:]
            ):
                return True
        return False

    @staticmethod
    def token_count(content: str) -> int:
        return len((content or "").split())


chunk_service = ChunkService()
