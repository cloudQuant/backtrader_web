"""HTTP and persistence contracts for the restricted model-governance surface."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.api.data.deps import require_data_admin_user
from app.db.database import async_session_maker
from app.main import app
from app.models.asset_research import (
    AssetInstrument,
    AssetModelRegistry,
    AssetModelStatusEvent,
    AssetSignalPrediction,
    AssetSourceSnapshot,
)
from app.models.user import User
from app.schemas.asset_research import PromotionScope


def _promotion_metrics(head_spec_hash: str) -> dict[str, object]:
    """Return the smallest complete, internally consistent T2 evidence fixture."""
    return {
        "head_spec_hash": head_spec_hash,
        "sample_count": 200,
        "unique_evaluation_days": 60,
        "market_regime_count": 3,
        "walk_forward_train_before_test": True,
        "overlap_purged": True,
        "embargo_applied": True,
        "vintage_data_enforced": True,
        "block_length_covers_max_overlap": True,
        "brier_score": 0.20,
        "baseline_brier_score": 0.25,
        "brier_skill_score": 0.20,
        "expected_calibration_error": 0.02,
        "reliability_reviewed": True,
        "mean_net_utility": 0.001,
        "delta_net_utility_ci_lower": 0.0,
        "tail_risk_approved": True,
        "maximum_drawdown_approved": True,
        "coverage_approved": True,
        "data_failure_rate_approved": True,
        "multiple_comparisons_controlled": True,
        "forward_shadow_days": 60,
        "all_attempts_manifest_hash": "e" * 64,
        "evaluation_artifact_hash": "f" * 64,
        "model_card_hash": "8" * 64,
        "drift_report_hash": "9" * 64,
        "futures_contract_month_count": 3,
    }


def _model_scope(
    *, status: str, complete_metrics: bool = True, fixture_key: str = "model-governance-api"
) -> AssetModelRegistry:
    """Build one immutable registry projection ready for a controlled transition."""
    head_spec_hash = "a" * 64
    scope = PromotionScope(
        scope_type="INSTRUMENT_SPECIFIC",
        asset_type="futures",
        instrument_class="FUTURE",
        canonical_id="futures:CFFEX:IF2609:CNY",
        venue="CFFEX",
        product_type="FUTURE",
        quote_or_settlement_asset=None,
        signal_head="futures.contract_pnl",
        horizon_code="standard",
        scope_parameters={"fixture": fixture_key},
    )
    return AssetModelRegistry(
        promotion_scope_key=scope.scope_key(),
        promotion_scope_type=scope.scope_type,
        asset_type=scope.asset_type,
        instrument_class=scope.instrument_class,
        canonical_id_scope=scope.canonical_id,
        venue_scope=scope.venue,
        product_type_scope=scope.product_type,
        scope_parameters_json=scope.scope_parameters,
        signal_head=scope.signal_head,
        horizon_code=scope.horizon_code,
        head_spec_hash=head_spec_hash,
        target_spec_version="target-v2",
        scoreability_rule_version="scoreability-v2",
        baseline_version="baseline-v1",
        policy_version="asset-research-policy-v2",
        model_version="asset-research-shadow-v2",
        probability_artifact_hash="b" * 64,
        calibration_version="not-promoted-v2",
        calibration_artifact_hash="c" * 64,
        training_cutoff_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        status=status,
        metrics_json=_promotion_metrics(head_spec_hash)
        if complete_metrics
        else {"sample_count": 10},
        approval_set_json={
            "model_quality": True,
            "product": True,
            "compliance": True,
            "data_license": True,
            "security": True,
        },
        evidence_uri="evidence://fixtures/model-governance.json",
        evidence_content_hash="d" * 64,
        effective_from=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )


async def _registered_user(user_data: dict[str, str]) -> User:
    async with async_session_maker() as db:
        return (
            await db.execute(select(User).where(User.username == user_data["username"]))
        ).scalar_one()


async def _seed_system_prediction(
    *, owner_scope: str, user_id: str | None
) -> AssetSignalPrediction:
    """Persist a minimal system/private prediction solely for access-control coverage."""
    as_of_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    canonical_id = "futures:CFFEX:IF2609:CNY"
    candidate = {
        "asset_type": "futures",
        "market_view": "BULLISH",
        "normalized_direction": "LONG",
        "position_context": "UNKNOWN",
        "horizon_code": "standard",
        "quality_status": "ELIGIBLE",
        "recommendation": "BUY",
        "actionability": "RESEARCH_ONLY",
        "trade_intent": "NONE",
        "reason_codes": ["COMMON.MODEL_NOT_PROMOTED"],
        "execution_disabled": True,
    }
    published = {
        **candidate,
        "market_view": "INDETERMINATE",
        "normalized_direction": "INDETERMINATE",
        "recommendation": "HOLD",
    }
    async with async_session_maker() as db:
        instrument = AssetInstrument(
            canonical_id=canonical_id,
            asset_type="futures",
            identity_level="CONTRACT",
            venue="CFFEX",
            currency="CNY",
            product_type="FUTURE",
            identity_json={"fixture": "model-governance-api"},
            metadata_version=f"fixture-{owner_scope}-{user_id or 'system'}",
            lifecycle_status="ACTIVE",
            valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        db.add(instrument)
        await db.flush()
        snapshot = AssetSourceSnapshot(
            instrument_id=instrument.id,
            asset_type="futures",
            canonical_id=canonical_id,
            identity_version=instrument.metadata_version,
            cutoff_at=as_of_at,
            raw_schema_version="fixture-v1",
            raw_fields_json={},
            source_manifest_json={},
            content_hash=("1" if owner_scope == "PUBLIC_SHADOW" else "2") * 64,
            license_tags_json=[],
        )
        db.add(snapshot)
        await db.flush()
        prediction = AssetSignalPrediction(
            prediction_key=("3" if owner_scope == "PUBLIC_SHADOW" else "4") * 64,
            decision_input_hash=("5" if owner_scope == "PUBLIC_SHADOW" else "6") * 64,
            owner_scope=owner_scope,
            user_id=user_id,
            instrument_id=instrument.id,
            asset_type="futures",
            canonical_id=canonical_id,
            identity_version=instrument.metadata_version,
            as_of_at=as_of_at,
            horizon_code="standard",
            horizon_spec_json={},
            position_context="UNKNOWN",
            candidate_decision_json=candidate,
            published_decision_json=published,
            actionability="RESEARCH_ONLY",
            quality_status="ELIGIBLE",
            quality_json={},
            snapshot_id=snapshot.id,
            head_spec_set_hash="7" * 64,
            feature_version="asset-research-features-v2",
            policy_version="asset-research-policy-v2",
            model_version="asset-research-shadow-v2",
            calibration_version="not-promoted-v2",
            capability_version="asset-research-capabilities-v1",
            compliance_policy_version="asset-research-compliance-v1",
            cutoff_policy_version="asset-research-cutoff-v1",
            cost_snapshot_json={},
        )
        db.add(prediction)
        await db.commit()
        return prediction


@pytest.mark.asyncio
async def test_admin_model_scope_transitions_are_append_only_and_fail_closed(
    client, auth_user, auth_headers
) -> None:
    """Only an admin can transition a pre-evidenced scope, with one immutable event."""
    user_data, _ = auth_user
    admin_user = await _registered_user(user_data)
    good = _model_scope(status="DRAFT")
    incomplete = _model_scope(
        status="SHADOW",
        complete_metrics=False,
        fixture_key="model-governance-api-incomplete",
    )
    async with async_session_maker() as db:
        db.add_all([good, incomplete])
        await db.commit()

    denied = await client.get("/api/v1/asset-research/admin/model-scopes", headers=auth_headers)
    assert denied.status_code == 403

    app.dependency_overrides[require_data_admin_user] = lambda: admin_user
    try:
        listed = await client.get("/api/v1/asset-research/admin/model-scopes", headers=auth_headers)
        card = await client.get(
            f"/api/v1/asset-research/admin/model-cards/{good.id}",
            headers=auth_headers,
        )
        shadow = await client.post(
            f"/api/v1/asset-research/admin/model-scopes/{good.id}/transitions",
            headers=auth_headers,
            json={"to_status": "SHADOW", "reason_codes": ["COMMON.SHADOW_APPROVED"]},
        )
        duplicate = await client.post(
            f"/api/v1/asset-research/admin/model-scopes/{good.id}/transitions",
            headers=auth_headers,
            json={"to_status": "SHADOW", "reason_codes": ["COMMON.SHADOW_APPROVED"]},
        )
        missing_gate_reason = await client.post(
            f"/api/v1/asset-research/admin/model-scopes/{good.id}/transitions",
            headers=auth_headers,
            json={"to_status": "PROMOTED", "reason_codes": ["COMMON.EVIDENCE_REVIEWED"]},
        )
        promoted = await client.post(
            f"/api/v1/asset-research/admin/model-scopes/{good.id}/transitions",
            headers=auth_headers,
            json={"to_status": "PROMOTED", "reason_codes": ["COMMON.T2_GATE_PASSED"]},
        )
        blocked = await client.post(
            f"/api/v1/asset-research/admin/model-scopes/{incomplete.id}/transitions",
            headers=auth_headers,
            json={"to_status": "PROMOTED", "reason_codes": ["COMMON.T2_GATE_PASSED"]},
        )
    finally:
        app.dependency_overrides.pop(require_data_admin_user, None)

    assert listed.status_code == 200, listed.text
    assert {item["registry_id"] for item in listed.json()} == {good.id, incomplete.id}
    assert card.status_code == 200, card.text
    assert card.json()["model_card_hash"] == "8" * 64
    assert card.json()["evaluation_manifest_hash"] == "e" * 64
    assert shadow.status_code == 200, shadow.text
    assert shadow.json()["model_scope"]["status"] == "SHADOW"
    assert shadow.json()["event"]["from_status"] == "DRAFT"
    assert shadow.json()["event"]["to_status"] == "SHADOW"
    assert duplicate.status_code == 422
    assert duplicate.json()["details"]["error_code"] == "MODEL_STATUS_TRANSITION_INVALID"
    assert missing_gate_reason.status_code == 422
    assert missing_gate_reason.json()["details"]["error_code"] == "MODEL_PROMOTION_REASON_REQUIRED"
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["model_scope"]["status"] == "PROMOTED"
    assert promoted.json()["model_scope"]["approved_at"] is not None
    assert promoted.json()["event"]["metrics_snapshot"]["sample_count"] == 200
    assert blocked.status_code == 422
    assert blocked.json()["details"]["error_code"] == "MODEL_PROMOTION_EVIDENCE_INCOMPLETE"

    async with async_session_maker() as db:
        events = list(
            (
                await db.execute(
                    select(AssetModelStatusEvent)
                    .where(AssetModelStatusEvent.model_registry_id == good.id)
                    .order_by(AssetModelStatusEvent.created_at)
                )
            ).scalars()
        )
        blocked_scope = await db.get(AssetModelRegistry, incomplete.id)

    assert [(event.from_status, event.to_status) for event in events] == [
        ("DRAFT", "SHADOW"),
        ("SHADOW", "PROMOTED"),
    ]
    assert all(event.actor_id == admin_user.id for event in events)
    assert blocked_scope is not None
    assert blocked_scope.status == "SHADOW"


@pytest.mark.asyncio
async def test_admin_model_scope_state_machine_never_restores_a_suspension_directly(
    client, auth_user, auth_headers
) -> None:
    """Suspension requires a new shadow period, and retirement is terminal."""
    user_data, _ = auth_user
    admin_user = await _registered_user(user_data)
    pausable = _model_scope(status="PROMOTED", fixture_key="model-governance-api-pausable")
    retireable = _model_scope(status="PROMOTED", fixture_key="model-governance-api-retireable")
    async with async_session_maker() as db:
        db.add_all([pausable, retireable])
        await db.commit()

    app.dependency_overrides[require_data_admin_user] = lambda: admin_user
    try:
        suspended = await client.post(
            f"/api/v1/asset-research/admin/model-scopes/{pausable.id}/transitions",
            headers=auth_headers,
            json={"to_status": "SUSPENDED", "reason_codes": ["COMMON.DRIFT_DETECTED"]},
        )
        direct_restore = await client.post(
            f"/api/v1/asset-research/admin/model-scopes/{pausable.id}/transitions",
            headers=auth_headers,
            json={"to_status": "PROMOTED", "reason_codes": ["COMMON.T2_GATE_PASSED"]},
        )
        shadow = await client.post(
            f"/api/v1/asset-research/admin/model-scopes/{pausable.id}/transitions",
            headers=auth_headers,
            json={"to_status": "SHADOW", "reason_codes": ["COMMON.REVALIDATION_REQUIRED"]},
        )
        retired = await client.post(
            f"/api/v1/asset-research/admin/model-scopes/{retireable.id}/transitions",
            headers=auth_headers,
            json={"to_status": "RETIRED", "reason_codes": ["COMMON.MODEL_RETIRED"]},
        )
        after_retirement = await client.post(
            f"/api/v1/asset-research/admin/model-scopes/{retireable.id}/transitions",
            headers=auth_headers,
            json={"to_status": "SHADOW", "reason_codes": ["COMMON.REVALIDATION_REQUIRED"]},
        )
    finally:
        app.dependency_overrides.pop(require_data_admin_user, None)

    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["model_scope"]["status"] == "SUSPENDED"
    assert direct_restore.status_code == 422
    assert direct_restore.json()["details"]["error_code"] == "MODEL_STATUS_TRANSITION_INVALID"
    assert shadow.status_code == 200, shadow.text
    assert shadow.json()["model_scope"]["status"] == "SHADOW"
    assert retired.status_code == 200, retired.text
    assert retired.json()["model_scope"]["status"] == "RETIRED"
    assert after_retirement.status_code == 422
    assert after_retirement.json()["details"]["error_code"] == "MODEL_STATUS_TRANSITION_INVALID"


@pytest.mark.asyncio
async def test_admin_candidate_endpoint_exposes_only_system_shadow_candidates(
    client, auth_user, auth_headers
) -> None:
    """Candidate direction never leaks to a normal user or from a private prediction."""
    user_data, _ = auth_user
    admin_user = await _registered_user(user_data)
    system_prediction = await _seed_system_prediction(owner_scope="PUBLIC_SHADOW", user_id=None)
    private_prediction = await _seed_system_prediction(owner_scope="USER", user_id=admin_user.id)

    denied = await client.get(
        f"/api/v1/asset-research/admin/signals/{system_prediction.id}/candidate",
        headers=auth_headers,
    )
    assert denied.status_code == 403

    app.dependency_overrides[require_data_admin_user] = lambda: admin_user
    try:
        allowed = await client.get(
            f"/api/v1/asset-research/admin/signals/{system_prediction.id}/candidate",
            headers=auth_headers,
        )
        private = await client.get(
            f"/api/v1/asset-research/admin/signals/{private_prediction.id}/candidate",
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(require_data_admin_user, None)

    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["owner_scope"] == "PUBLIC_SHADOW"
    assert allowed.json()["candidate_decision"]["normalized_direction"] == "LONG"
    assert private.status_code == 404
    assert private.json()["details"]["error_code"] == "PREDICTION_CANDIDATE_NOT_FOUND"
