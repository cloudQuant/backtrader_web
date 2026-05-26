"""Estimated AI model cost calculation helpers."""

from __future__ import annotations

MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3.5-sonnet": (3.0, 15.0),
    "ollama-local": (0.0, 0.0),
}


def calculate_estimated_cost_usd(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate provider cost from token counts using USD per 1M token pricing."""
    pricing = MODEL_PRICING.get(str(model_name or "").lower())
    if pricing is None:
        return 0.0
    input_usd_per_million, output_usd_per_million = pricing
    prompt_cost = max(prompt_tokens, 0) / 1_000_000 * input_usd_per_million
    completion_cost = max(completion_tokens, 0) / 1_000_000 * output_usd_per_million
    return round(prompt_cost + completion_cost, 8)
