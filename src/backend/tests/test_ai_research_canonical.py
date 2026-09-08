from __future__ import annotations

from datetime import datetime, timezone

from app.services.research.canonical import canonical_json, content_hash
from app.services.research.redaction import redact_sensitive_payload


def test_canonical_json_is_stable_for_equivalent_research_payloads() -> None:
    first = {
        "dataset": {"end_at": "2026-01-02T00:00:00Z", "symbols": ["RB0", "SA0"]},
        "cost": {"slippage_bps": 1.5, "commission_bps": 2},
        "optional": None,
    }
    second = {
        "optional": None,
        "cost": {"commission_bps": 2.0, "slippage_bps": 1.50},
        "dataset": {
            "symbols": ["RB0", "SA0"],
            "end_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        },
    }

    assert canonical_json(first) == canonical_json(second)
    assert content_hash(first) == content_hash(second)


def test_content_hash_changes_when_a_controlled_research_field_changes() -> None:
    baseline = {
        "research_question": "趋势跟随是否在成本后成立？",
        "primary_metric": "deflated_sharpe",
        "search_space": {"lookback": [10, 20]},
    }
    changed = {
        **baseline,
        "search_space": {"lookback": [10, 30]},
    }

    assert content_hash(baseline) != content_hash(changed)


def test_redaction_removes_nested_secrets_and_url_credentials() -> None:
    payload = {
        "gateway": {
            "api_key": "sk-live-secret-value",
            "nested": [{"password": "dont-leak"}],
        },
        "callback_url": "https://user:password@example.test/hook?token=super-token&safe=yes",
        "safe": "visible",
    }

    redacted = redact_sensitive_payload(payload)
    rendered = canonical_json(redacted)

    assert redacted["safe"] == "visible"
    assert "sk-live-secret-value" not in rendered
    assert "dont-leak" not in rendered
    assert "super-token" not in rendered
    assert "password@example.test" not in rendered
    assert "[REDACTED]" in rendered
