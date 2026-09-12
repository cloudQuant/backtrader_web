from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.strategy import research as research_api
from app.config import get_settings
from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchRun
from app.models.user import User
from app.services.research.canonical import content_hash
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from tests.conftest import app, register_and_login


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the opt-in v2 API only after enabling its write flag."""

    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


@pytest.fixture
def dataset_object_resolver() -> InMemoryDatasetObjectResolver:
    """Inject only a server-owned fixture resolver through the deployment seam."""

    resolver = InMemoryDatasetObjectResolver()
    app.dependency_overrides[research_api.get_dataset_object_resolver] = lambda: resolver
    try:
        yield resolver
    finally:
        app.dependency_overrides.pop(research_api.get_dataset_object_resolver, None)


def _payload() -> dict[str, object]:
    return {
        "research_question": "成本与滑点后，趋势信号是否仍有可检验优势？",
        "economic_mechanism": "趋势持续由信息扩散与风险补偿共同驱动。",
        "asset_scope": {"symbols": ["RB0"], "asset_class": "futures"},
        "frequency": "1d",
        "time_window": {"start": "2022-01-01", "end": "2025-12-31"},
        "information_cutoff": "2025-12-31T00:00:00Z",
        "cost_model": {"commission_bps": 2.0, "slippage_bps": 1.0},
        "execution_model": {"fill": "next_bar_open"},
        "primary_metric": "deflated_sharpe",
        "secondary_metrics": ["max_drawdown", "turnover"],
        "capacity_assumptions": {"max_participation_rate": 0.1},
        "falsification_criteria": {"max_drawdown": 0.2},
        "search_space": {"lookback": [10, 20]},
        "max_budget": {"max_trials": 20},
        "dataset_policy_version": "dataset-policy-v1",
    }


def _dataset_payload(object_receipt_id: str) -> dict[str, object]:
    """Return the browser-safe snapshot metadata and an opaque server receipt."""

    return {
        "dataset_policy_version": "dataset-policy-v1",
        "partition_kind": "DISCOVERY",
        "instrument_manifest": {
            "symbols": ["RB0"],
            "asset_class": "futures",
            "identity_scheme": "exchange_symbol",
        },
        "split_manifest": {
            "start": "2022-01-01",
            "end": "2023-12-31",
            "walk_forward": True,
            "purge_bars": 5,
            "embargo_bars": 5,
            "folds": [
                {
                    "train_start": "2022-01-01",
                    "train_end": "2022-12-31",
                    "validation_start": "2023-01-01",
                    "validation_end": "2023-12-31",
                }
            ],
        },
        "source_manifest": {
            "provider": "fixture",
            "frequency": "1d",
            "timezone": "UTC",
            "adjustment_rule": "none",
            "event_time_basis": "bar_close",
            "ingested_at": "2024-01-01T00:00:00Z",
            "as_of_at": "2024-01-01T00:00:00Z",
            "vintage": "fixture-v1",
        },
        "execution_policy": {
            "fill": "next_bar_open",
            "commission_bps": 2.0,
            "slippage_bps": 1.0,
            "volume_limit": 0.1,
            "suspension": "BLOCKED",
            "price_limit": "BLOCKED",
            "market_impact": "UNKNOWN",
        },
        "point_in_time_cutoff": "2024-01-01T00:00:00Z",
        "object_receipt_id": object_receipt_id,
        "license_tags": ["fixture-permitted"],
    }


async def _user_id(username: str) -> str:
    async with async_session_maker() as session:
        return str(
            (await session.execute(select(User.id).where(User.username == username))).scalar_one()
        )


def _register_dataset_receipt(
    resolver: InMemoryDatasetObjectResolver,
    *,
    user_id: str,
    receipt_id: str,
) -> None:
    """Seed controlled object facts without exposing them to the API caller."""

    resolver.register(
        DatasetObjectAttestation(
            receipt_id=receipt_id,
            user_id=user_id,
            logical_object_id="fixture-discovery-object",
            object_version="fixture-v1",
            object_digest="d" * 64,
            object_size_bytes=1024,
            storage_uri="controlled://research-fixtures/discovery.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )


@pytest.mark.asyncio
async def test_v2_hypothesis_api_requires_server_side_confirmation(client, auth_headers) -> None:
    created = await client.post(
        "/api/v1/strategy/ai-research/v2/hypotheses",
        headers=auth_headers,
        json={"payload": _payload()},
    )

    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "DRAFT"
    assert draft["confirmed_by"] is None

    confirmed = await client.post(
        f"/api/v1/strategy/ai-research/v2/hypotheses/{draft['id']}/confirm",
        headers=auth_headers,
        json={"request_hash": draft["content_hash"]},
    )

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"
    assert confirmed.json()["confirmed_by"]


@pytest.mark.asyncio
async def test_v2_epoch_derives_family_hash_server_side_and_rejects_client_selected_hash(
    client,
    auth_headers,
) -> None:
    payload = _payload()
    created = await client.post(
        "/api/v1/strategy/ai-research/v2/hypotheses",
        headers=auth_headers,
        json={"payload": payload},
    )
    assert created.status_code == 201, created.text
    hypothesis = created.json()
    confirmed = await client.post(
        f"/api/v1/strategy/ai-research/v2/hypotheses/{hypothesis['id']}/confirm",
        headers=auth_headers,
        json={"request_hash": hypothesis["content_hash"]},
    )
    assert confirmed.status_code == 200, confirmed.text

    epoch_payload = {
        "hypothesis_version_id": hypothesis["id"],
        "search_budget": {"max_trials": 3},
        "dataset_policy_version": "dataset-policy-v1",
    }
    created_epoch = await client.post(
        "/api/v1/strategy/ai-research/v2/epochs",
        headers=auth_headers,
        json=epoch_payload,
    )

    assert created_epoch.status_code == 201, created_epoch.text
    expected_family_payload = {
        key: payload[key]
        for key in (
            "research_question",
            "asset_scope",
            "frequency",
            "time_window",
            "primary_metric",
            "search_space",
        )
    }
    assert created_epoch.json()["family_hash"] == content_hash(expected_family_payload)

    client_selected = await client.post(
        "/api/v1/strategy/ai-research/v2/epochs",
        headers=auth_headers,
        json={**epoch_payload, "family_hash": "0" * 64},
    )
    assert client_selected.status_code == 422


@pytest.mark.asyncio
async def test_v2_hypothesis_api_hides_foreign_versions(client, auth_headers) -> None:
    created = await client.post(
        "/api/v1/strategy/ai-research/v2/hypotheses",
        headers=auth_headers,
        json={"payload": _payload()},
    )
    assert created.status_code == 201, created.text
    _, other_headers = await register_and_login(client, username="ai-research-v2-api-other")

    foreign = await client.get(
        f"/api/v1/strategy/ai-research/v2/hypotheses/{created.json()['id']}",
        headers=other_headers,
    )

    assert foreign.status_code == 404


@pytest.mark.asyncio
async def test_v2_write_routes_are_blocked_when_feature_flag_is_off(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", False)

    created = await client.post(
        "/api/v1/strategy/ai-research/v2/hypotheses",
        headers=auth_headers,
        json={"payload": _payload()},
    )

    assert created.status_code == 409
    assert created.json()["message"] == "AI_RESEARCH_PROTOCOL_V2_DISABLED"


@pytest.mark.asyncio
async def test_cross_module_dataset_helper_installs_dependency_override(auth_user) -> None:
    """Model the helper reuse that originally leaked a resolver into later tests."""

    from tests.test_ai_research_holdout_request import _request_context

    await _request_context(auth_user, "dataset-resolver-override-polluter")

    assert research_api.get_dataset_object_resolver in app.dependency_overrides


@pytest.mark.asyncio
async def test_dependency_override_is_restored_after_cross_module_helper(
    client,
    auth_headers,
) -> None:
    """Every test must start from the dependency overrides it inherited at setup."""

    assert research_api.get_dataset_object_resolver not in app.dependency_overrides

    response = await client.post(
        "/api/v1/strategy/ai-research/v2/datasets",
        headers=auth_headers,
        json=_dataset_payload("fixture-receipt-discovery-v1"),
    )

    assert response.status_code == 409
    assert response.json()["message"] == "DATASET_OBJECT_RESOLVER_REQUIRED"


@pytest.mark.asyncio
async def test_v2_dataset_api_rejects_browser_storage_uris_and_fails_closed_without_resolver(
    client,
    auth_headers,
) -> None:
    """The public endpoint accepts an opaque receipt, never a storage location."""

    assert research_api.get_dataset_object_resolver not in app.dependency_overrides, repr(
        app.dependency_overrides
    )
    assert research_api.get_dataset_object_resolver() is None

    uri_as_receipt = await client.post(
        "/api/v1/strategy/ai-research/v2/datasets",
        headers=auth_headers,
        json=_dataset_payload("controlled://research-fixtures/discovery.parquet"),
    )
    assert uri_as_receipt.status_code == 422

    scheme_without_slashes = await client.post(
        "/api/v1/strategy/ai-research/v2/datasets",
        headers=auth_headers,
        json=_dataset_payload("s3:research-fixtures-discovery.parquet"),
    )
    assert scheme_without_slashes.status_code == 422

    explicit_uri = await client.post(
        "/api/v1/strategy/ai-research/v2/datasets",
        headers=auth_headers,
        json={
            **_dataset_payload("fixture-receipt-discovery-v1"),
            "storage_reference": "controlled://research-fixtures/discovery.parquet",
        },
    )
    assert explicit_uri.status_code == 422

    no_resolver = await client.post(
        "/api/v1/strategy/ai-research/v2/datasets",
        headers=auth_headers,
        json=_dataset_payload("fixture-receipt-discovery-v1"),
    )
    assert no_resolver.status_code == 409
    assert no_resolver.json()["message"] == "DATASET_OBJECT_RESOLVER_REQUIRED"


@pytest.mark.asyncio
async def test_v2_dataset_api_hides_invalid_filesystem_resolver_configuration(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deployment fault is stable and never reflects an operator-controlled root."""

    settings = get_settings()
    private_root = "/operator-only/dataset-root"
    monkeypatch.setattr(
        settings,
        "AI_RESEARCH_PROTOCOL_V2_DATASET_OBJECT_RESOLVER_TYPE",
        "filesystem",
    )
    monkeypatch.setattr(settings, "AI_RESEARCH_PROTOCOL_V2_DATASET_FILESYSTEM_ROOT", private_root)
    monkeypatch.setattr(
        settings,
        "AI_RESEARCH_PROTOCOL_V2_DATASET_RECEIPT_STORE",
        "/operator-only/receipt-store",
    )
    monkeypatch.setattr(settings, "AI_RESEARCH_PROTOCOL_V2_DATASET_MAX_BYTES", 1024)

    assert research_api.get_dataset_object_resolver not in app.dependency_overrides, repr(
        app.dependency_overrides
    )
    with pytest.raises(HTTPException) as direct_error:
        research_api.get_dataset_object_resolver()
    assert getattr(direct_error.value, "status_code", None) == 409
    assert getattr(direct_error.value, "detail", None) == (
        "DATASET_OBJECT_RESOLVER_CONFIGURATION_INVALID"
    )

    response = await client.post(
        "/api/v1/strategy/ai-research/v2/datasets",
        headers=auth_headers,
        json=_dataset_payload("fixture-receipt-discovery-v1"),
    )

    assert response.status_code == 409
    assert response.json()["message"] == "DATASET_OBJECT_RESOLVER_CONFIGURATION_INVALID"
    assert private_root not in response.text


@pytest.mark.asyncio
async def test_v2_config_profiles_are_owner_scoped_and_reject_direct_secrets(
    client, auth_user
) -> None:
    _user, headers = auth_user
    created = await client.post(
        "/api/v1/strategy/ai-research/v2/config-profiles",
        headers=headers,
        json={
            "name": "RB profile",
            "config": {
                "symbol": "RB0",
                "credential_ref": "vault://research/provider",
            },
        },
    )

    assert created.status_code == 201, created.text
    profile = created.json()
    assert profile["config"] == {"symbol": "RB0"}
    assert profile["credential_refs"] == {"config.credential_ref": "vault://research/provider"}
    listed = await client.get("/api/v1/strategy/ai-research/v2/config-profiles", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [profile["id"]]
    _other, other_headers = await register_and_login(client, username="v2-profile-owner-other")
    foreign = await client.get(
        f"/api/v1/strategy/ai-research/v2/config-profiles/{profile['id']}",
        headers=other_headers,
    )
    assert foreign.status_code == 404

    unsafe = await client.post(
        "/api/v1/strategy/ai-research/v2/config-profiles",
        headers=headers,
        json={"name": "unsafe", "config": {"api_key": "should-not-persist"}},
    )
    assert unsafe.status_code == 422
    assert unsafe.json()["message"] == "RESEARCH_CONFIG_PROFILE_SECRET_FIELD_DENIED"


@pytest.mark.asyncio
async def test_v2_api_submits_idempotent_run_and_exposes_only_safe_workbench_read_model(
    client,
    auth_user,
    dataset_object_resolver: InMemoryDatasetObjectResolver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The server setting freezes the graph even when a browser submits a conflicting value."""

    monkeypatch.setattr(
        get_settings(),
        "AI_RESEARCH_PROTOCOL_V2_WORKFLOW_VERSION",
        "discovery-v1",
        raising=False,
    )
    profile = CapabilityProfile(
        profile_id="dev-single-process",
        version="v1",
        service_identities={"explorer": "shared", "evaluator": "shared"},
        queue_isolation=False,
        storage_isolation=False,
        network_isolation=False,
        sandbox_runner=False,
        approval_mode="single_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await CapabilityRegistry().register(profile)
    user, headers = auth_user
    user_id = await _user_id(user["username"])
    _register_dataset_receipt(
        dataset_object_resolver,
        user_id=user_id,
        receipt_id="fixture-receipt-discovery-v1",
    )
    created = await client.post(
        "/api/v1/strategy/ai-research/v2/hypotheses",
        headers=headers,
        json={"payload": _payload()},
    )
    assert created.status_code == 201
    hypothesis = created.json()
    confirmed = await client.post(
        f"/api/v1/strategy/ai-research/v2/hypotheses/{hypothesis['id']}/confirm",
        headers=headers,
        json={"request_hash": hypothesis["content_hash"]},
    )
    assert confirmed.status_code == 200
    dataset = await client.post(
        "/api/v1/strategy/ai-research/v2/datasets",
        headers=headers,
        json=_dataset_payload("fixture-receipt-discovery-v1"),
    )
    assert dataset.status_code == 201, dataset.text
    assert "storage_uri" not in dataset.json()
    epoch = await client.post(
        "/api/v1/strategy/ai-research/v2/epochs",
        headers=headers,
        json={
            "hypothesis_version_id": hypothesis["id"],
            "search_budget": {"max_trials": 3},
            "dataset_policy_version": "dataset-policy-v1",
        },
    )
    assert epoch.status_code == 201, epoch.text
    launch_binding = {
        "hypothesis_version_id": hypothesis["id"],
        "dataset_snapshot_id": dataset.json()["id"],
        "experiment_epoch_id": epoch.json()["id"],
        "profile_id": "dev-single-process",
        "profile_version": "v1",
        "promotion_policy_version": "promotion-v1",
        "request_json": {
            "hypothesis_content_hash": hypothesis["content_hash"],
            "dataset_snapshot_id": dataset.json()["id"],
            "experiment_epoch_id": epoch.json()["id"],
        },
    }
    precheck = await client.post(
        "/api/v1/strategy/ai-research/v2/data-prechecks",
        headers=headers,
        json=launch_binding,
    )
    assert precheck.status_code == 201, precheck.text
    assert precheck.json()["status"] == "PASS", precheck.json()
    run_payload = {
        **launch_binding,
        "precheck_id": precheck.json()["id"],
        # This unknown request field must not select the persisted worker graph.
        "workflow_version": "generation-v1",
    }
    submitted = await client.post(
        "/api/v1/strategy/ai-research/v2/runs",
        headers={**headers, "Idempotency-Key": "v2-api-submit"},
        json=run_payload,
    )
    repeated = await client.post(
        "/api/v1/strategy/ai-research/v2/runs",
        headers={**headers, "Idempotency-Key": "v2-api-submit"},
        json=run_payload,
    )

    assert submitted.status_code == 201, submitted.text
    assert repeated.status_code == 201, repeated.text
    assert submitted.json()["task"]["id"] == repeated.json()["task"]["id"]
    assert submitted.json()["run"]["data_precheck_id"] == precheck.json()["id"]
    assert submitted.json()["run"]["workflow_version"] == "discovery-v1"
    assert repeated.json()["run"]["workflow_version"] == "discovery-v1"
    workbench = await client.get(
        f"/api/v1/strategy/ai-research/v2/runs/{submitted.json()['run']['id']}",
        headers=headers,
    )
    assert workbench.status_code == 200, workbench.text
    assert workbench.json()["run"]["workflow_version"] == "discovery-v1"
    assert "controlled://research-fixtures/discovery.parquet" not in str(dataset.json())
    assert "controlled://research-fixtures/discovery.parquet" not in str(workbench.json())
    assert workbench.json()["evidence_class"] == "PROTOCOL_V2_PENDING"
    assert workbench.json()["model_invocations"] == []
    assert workbench.json()["evidence_packages"] == []
    _other, other_headers = await register_and_login(client, username="v2-workbench-other")
    foreign = await client.get(
        f"/api/v1/strategy/ai-research/v2/runs/{submitted.json()['run']['id']}",
        headers=other_headers,
    )
    assert foreign.status_code == 404


@pytest.mark.asyncio
async def test_v2_governance_api_records_only_server_allowed_deviation_and_can_revoke(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A governance record remains a visible BLOCKED limitation rather than a gate bypass."""

    monkeypatch.setattr(
        get_settings(),
        "AI_RESEARCH_PROTOCOL_V2_WAIVABLE_TARGETS",
        "NFR-PERF-001",
        raising=False,
    )
    user, headers = auth_user
    async with async_session_maker() as session:
        user_id = str(
            (
                await session.execute(select(User.id).where(User.username == user["username"]))
            ).scalar_one()
        )
        run = ResearchRun(
            user_id=user_id,
            hypothesis_version_id="governance-api-hypothesis",
            promotion_policy_version="promotion-v1",
            request_hash="a" * 64,
            capability_profile_id="governance-api-profile",
            capability_profile_version="v1",
            capability_evidence_hash="b" * 64,
            trace_id="trace-governance-api",
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

    created = await client.post(
        "/api/v1/strategy/ai-research/v2/governance-deviations",
        headers={**headers, "Idempotency-Key": "governance-api-1"},
        json={
            "target_requirement_or_gate": "NFR-PERF-001",
            "original_status": "BLOCKED",
            "reason": "authorization=Bearer internal-governance-token",
            "risk": "The target-deployment latency budget is not proven.",
            "compensating_controls": ["token=internal-control-token"],
            "scope": {"run_id": run.id},
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )

    assert created.status_code == 201, created.text
    decision = created.json()
    assert decision["original_status"] == "BLOCKED"
    assert "actor_id" not in decision
    assert "scope" not in decision
    assert decision["reason"] == "[REDACTED]"
    assert decision["compensating_controls"] == ["[REDACTED]"]
    workbench = await client.get(
        f"/api/v1/strategy/ai-research/v2/runs/{run.id}",
        headers=headers,
    )
    assert workbench.status_code == 200, workbench.text
    assert workbench.json()["evidence_class"] == "PROTOCOL_V2_PENDING"
    assert workbench.json()["governance_decisions"][0]["id"] == decision["id"]

    revoked = await client.post(
        f"/api/v1/strategy/ai-research/v2/governance-deviations/{decision['id']}/revoke",
        headers=headers,
    )

    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["original_status"] == "BLOCKED"
    assert revoked.json()["revoked_at"] is not None
