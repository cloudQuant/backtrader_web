"""Knowledge base retrieval settings helpers."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

DEFAULT_KNOWLEDGE_BASE_SETTINGS: dict[str, Any] = {
    "retrieval_profile": "quant_research",
    "search_mode": "hybrid",
    "default_top_k": 8,
    "min_similarity": 0.08,
    "title_weight": 0.35,
    "keyword_weight": 0.35,
    "phrase_weight": 0.2,
    "recency_weight": 0.1,
    "max_context_chunks": 6,
    "use_conversation_memory": True,
    "conversation_lookback_messages": 6,
    "prioritize_title_matches": True,
    "prefer_recent_documents": True,
    "quant_focus": "strategy_research",
    "system_prompt_suffix": None,
}


def default_knowledge_base_settings() -> dict[str, Any]:
    """Return a deep-copied default knowledge base settings payload."""
    return deepcopy(DEFAULT_KNOWLEDGE_BASE_SETTINGS)


def merge_knowledge_base_settings(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge a raw settings payload on top of the default retrieval profile."""
    merged = default_knowledge_base_settings()
    if not isinstance(raw, Mapping):
        return merged

    for key, value in raw.items():
        if key not in merged:
            continue
        if value is None:
            continue
        merged[key] = value
    return merged
