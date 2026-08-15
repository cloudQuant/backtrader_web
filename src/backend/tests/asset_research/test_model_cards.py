"""Versioned model-card audit contracts."""

from datetime import datetime, timezone

from app.services.asset_research.model_cards import ModelCard


def test_model_card_content_hash_is_stable() -> None:
    card = ModelCard(
        model_name="futures-shadow-v1",
        head_spec_hash="a" * 64,
        owner="quant-research",
        target_definition="20-day executable futures return",
        labels=("LONG", "SHORT", "NEUTRAL"),
        training_cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        embargo="1D",
        baseline_code="futures.neutral_baseline",
        evaluation_manifest_hash="b" * 64,
        limitations=("研究观察", "不构成投资建议"),
        failure_modes=("来源失效", "深度不足", "价格边缺失"),
        model_version="v1",
    )

    assert card.content_hash() == card.content_hash()
    assert card.public_payload()["content_hash"] == card.content_hash()
