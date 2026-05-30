"""Simple chunking service for iteration 129."""


class ChunkService:
    """Split text into simple chunks."""

    @staticmethod
    def split_text(content: str) -> list[str]:
        text = (content or "").strip()
        if not text:
            return []
        paragraphs = [
            part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()
        ]
        if paragraphs:
            return paragraphs
        return [text]

    @staticmethod
    def token_count(content: str) -> int:
        return len((content or "").split())


chunk_service = ChunkService()
