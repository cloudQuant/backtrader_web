"""Public API contracts for multi-asset identity and task resources."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app.api.asset_research as asset_research_api
from app.api.asset_research import (
    get_asset_research_artifacts,
    get_asset_research_orchestrator,
    get_instrument_resolver,
)
from app.api.data.deps import require_data_admin_user
from app.db.database import async_session_maker
from app.main import app
from app.models.asset_research import AssetAnalysisTask, AssetDataSourceRegistry, AssetInstrument
from app.models.stock_signal import StockSignalPrediction
from app.schemas.asset_research import FuturesIdentityDetails, InstrumentIdentity
from app.services.asset_research.data import DEFAULT_ASSET_RESEARCH_SOURCE_ID
from tests.conftest import register_and_login


class _Resolver:
    async def resolve(self, _request: object) -> InstrumentIdentity:
        return InstrumentIdentity(
            asset_type="futures",
            identity_level="CONTRACT",
            canonical_id="futures:CFFEX:IF2609:CNY",
            display_symbol="IF2609",
            name="沪深300期货2609",
            venue="CFFEX",
            currency="CNY",
            timezone="Asia/Shanghai",
            identifier_type="CONTRACT_CODE",
            identifier_value="IF2609",
            product_type="FUTURE",
            metadata_version="fixture-v1",
            details=FuturesIdentityDetails(
                product_code="IF",
                contract_month="2609",
                expiry_at="2026-09-18T07:15:00+00:00",
                contract_multiplier="300",
                trading_calendar_id="CFFEX",
            ),
        )


async def _register_approved_instrument() -> InstrumentIdentity:
    """Insert one operator-approved identity for the real catalog API path."""
    identity = await _Resolver().resolve(None)
    async with async_session_maker() as db:
        db.add(
            AssetInstrument(
                canonical_id=identity.canonical_id,
                asset_type=identity.asset_type,
                identity_level=identity.identity_level,
                venue=identity.venue,
                currency=identity.currency,
                product_type=identity.product_type,
                identity_json=identity.model_dump(mode="json"),
                metadata_version=identity.metadata_version,
                lifecycle_status="ACTIVE",
                valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
        )
        await db.commit()
    return identity


async def _register_approved_source(*, asset_type: str, source_id: str) -> None:
    """Create the minimum server-owned capability needed by one API test."""
    async with async_session_maker() as db:
        db.add(
            AssetDataSourceRegistry(
                source_id=source_id,
                asset_types=[asset_type],
                jurisdictions=["GLOBAL"],
                license_status="RESEARCH_APPROVED",
                allowed_uses=["RESEARCH_ONLY"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy="research-v1",
                effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                freshness_sla={"max_age_seconds": 86400},
                enabled=True,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_capabilities_only_enable_asset_types_with_an_active_approved_source(
    client, auth_headers
) -> None:
    initial = await client.get("/api/v1/asset-research/capabilities", headers=auth_headers)
    assert initial.status_code == 200, initial.text
    initial_by_asset = {item["asset_type"]: item for item in initial.json()["asset_types"]}
    assert all(item["research_enabled"] is False for item in initial_by_asset.values())

    await _register_approved_source(
        asset_type="futures", source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID
    )

    approved = await client.get("/api/v1/asset-research/capabilities", headers=auth_headers)
    assert approved.status_code == 200, approved.text
    approved_by_asset = {item["asset_type"]: item for item in approved.json()["asset_types"]}
    assert approved_by_asset["futures"]["source_capability_enabled"] is True
    assert approved_by_asset["futures"]["instrument_catalog_ready"] is False
    assert approved_by_asset["futures"]["research_enabled"] is False
    assert approved_by_asset["futures"]["availability_reason"] == "INSTRUMENT_CATALOG_UNAVAILABLE"
    assert approved_by_asset["bond"]["research_enabled"] is False

    await _register_approved_instrument()
    catalog_ready = await client.get("/api/v1/asset-research/capabilities", headers=auth_headers)
    assert catalog_ready.status_code == 200, catalog_ready.text
    catalog_ready_by_asset = {
        item["asset_type"]: item for item in catalog_ready.json()["asset_types"]
    }
    assert catalog_ready_by_asset["futures"]["research_enabled"] is True


@pytest.mark.asyncio
async def test_capabilities_do_not_advertise_an_unbound_approved_source(
    client, auth_headers
) -> None:
    """A registry row is insufficient when no installed adapter owns that source."""
    await _register_approved_source(asset_type="futures", source_id="other-approved-source")
    await _register_approved_instrument()

    response = await client.get("/api/v1/asset-research/capabilities", headers=auth_headers)

    assert response.status_code == 200, response.text
    futures = next(
        item for item in response.json()["asset_types"] if item["asset_type"] == "futures"
    )
    assert futures["source_capability_enabled"] is False
    assert futures["instrument_catalog_ready"] is True
    assert futures["research_enabled"] is False
    assert futures["availability_reason"] == "SOURCE_CAPABILITY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_admin_stock_compat_reconcile_reads_legacy_system_rows(
    client, auth_headers
) -> None:
    """The compatibility audit endpoint is admin-only and reports structured rows."""
    async with async_session_maker() as db:
        db.add(
            StockSignalPrediction(
                prediction_key="reconcile-api-key",
                owner_scope="system",
                source="nightly_sse50",
                universe_code="SSE50",
                symbol="600000.SH",
                symbol_name="浦发银行",
                market_type="A股",
                as_of_date=datetime(2026, 7, 30, tzinfo=timezone.utc).date(),
                as_of_at=datetime(2026, 7, 30, 15, 0, tzinfo=timezone.utc),
                available_at=datetime(2026, 7, 30, 19, 0, tzinfo=timezone.utc),
                next_trading_date=datetime(2026, 7, 31, tzinfo=timezone.utc).date(),
                signal_action="WATCH",
                confidence_score=0.5,
                risk_score=0.2,
                eligibility_status="eligible",
                quality_reasons_json=[],
                data_freshness_json={},
                feature_version="ohlcv-v1",
                decision_policy_version="baseline-v1",
                model_version="deterministic-shadow-v1",
                feature_snapshot_json={},
                policy_snapshot_json={},
                source_snapshot_hash="a" * 64,
                outcome_status="pending",
            )
        )
        await db.commit()

    denied = await client.get(
        "/api/v1/asset-research/admin/stock-compat/reconcile",
        headers=auth_headers,
    )
    assert denied.status_code == 403

    app.dependency_overrides[require_data_admin_user] = lambda: SimpleNamespace(id="admin-fixture")
    try:
        response = await client.get(
            "/api/v1/asset-research/admin/stock-compat/reconcile",
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(require_data_admin_user, None)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["defect_count"] == 0
    assert payload["rows"][0]["classification"] == "EXPECTED_MAPPING"


@pytest.mark.asyncio
async def test_resolve_endpoint_persists_and_returns_a_canonical_identity(
    client, auth_headers
) -> None:
    app.dependency_overrides[get_instrument_resolver] = lambda: _Resolver()
    try:
        response = await client.post(
            "/api/v1/asset-research/instruments/resolve",
            headers=auth_headers,
            json={"asset_type": "futures", "query": "IF2609", "venue": "CFFEX"},
        )
    finally:
        app.dependency_overrides.pop(get_instrument_resolver, None)

    assert response.status_code == 200, response.text
    assert response.json()["canonical_id"] == "futures:CFFEX:IF2609:CNY"
    assert response.json()["identity_level"] == "CONTRACT"


@pytest.mark.asyncio
async def test_catalog_backed_search_and_resolve_do_not_fall_back_to_display_symbols(
    client, auth_headers
) -> None:
    """The public endpoint exposes only operator-approved database master data."""
    empty = await client.get(
        "/api/v1/asset-research/instruments/search",
        headers=auth_headers,
        params={"asset_type": "futures", "query": "IF2609"},
    )
    assert empty.status_code == 200, empty.text
    assert empty.json()["items"] == []

    identity = await _register_approved_instrument()
    found = await client.get(
        "/api/v1/asset-research/instruments/search",
        headers=auth_headers,
        params={"asset_type": "futures", "query": "IF2609", "identity_level": "CONTRACT"},
    )
    wrong_level = await client.get(
        "/api/v1/asset-research/instruments/search",
        headers=auth_headers,
        params={"asset_type": "futures", "query": "IF2609", "identity_level": "PRODUCT"},
    )
    resolved = await client.post(
        "/api/v1/asset-research/instruments/resolve",
        headers=auth_headers,
        json={
            "asset_type": "futures",
            "query": "IF2609",
            "venue": "CFFEX",
            "canonical_id": identity.canonical_id,
            "identity_level": "CONTRACT",
        },
    )

    assert found.status_code == 200, found.text
    assert found.json()["items"][0]["canonical_id"] == identity.canonical_id
    assert found.json()["items"][0]["identity_level"] == "CONTRACT"
    assert wrong_level.status_code == 200, wrong_level.text
    assert wrong_level.json()["items"] == []
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["metadata_version"] == identity.metadata_version


@pytest.mark.asyncio
async def test_evidence_endpoint_returns_only_the_public_whitelisted_manifest(
    client, auth_headers
) -> None:
    class _EvidenceService:
        async def get_signal_evidence(self, *, user_id: str, prediction_id: str) -> dict[str, object]:
            assert user_id
            assert prediction_id == "prediction-1"
            return {
                "prediction_id": prediction_id,
                "canonical_id": "futures:CFFEX:IF2609:CNY",
                "asset_type": "futures",
                "source": {
                    "source_id": "fixture-source",
                    "license_status": "RESEARCH_APPROVED",
                    "capabilities": ["price", "contract_calendar"],
                    "allowed_uses": ["RESEARCH_ONLY"],
                },
                "source_snapshot_hash": "a" * 64,
                "license_tags": ["research-only"],
                "versions": {
                    "feature_version": "fixture-feature-v1",
                    "model_version": "fixture-model-v1",
                },
                "reason_codes": ["COMMON.MODEL_NOT_PROMOTED"],
            }

    app.dependency_overrides[get_asset_research_orchestrator] = _EvidenceService
    try:
        response = await client.get(
            "/api/v1/asset-research/signals/prediction-1/evidence",
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_asset_research_orchestrator, None)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"]["source_id"] == "fixture-source"
    assert payload["versions"]["model_version"] == "fixture-model-v1"
    assert "raw_fields" not in payload
    assert "candidate_decision" not in payload


@pytest.mark.asyncio
async def test_report_export_post_is_the_explicit_creation_route(client, auth_headers) -> None:
    """Only the POST route may request an export and commit its audit record."""

    class _Db:
        commit_calls = 0

        async def commit(self) -> None:
            self.commit_calls += 1

    class _Artifacts:
        def __init__(self) -> None:
            self.db = _Db()
            self.request_calls = 0
            self.export = SimpleNamespace(
                id="export-1",
                report_id="report-1",
                format="MARKDOWN",
                status="SUCCEEDED",
                content_hash="a" * 64,
                error_code=None,
                created_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
                completed_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
            )

        async def request_export(self, **_: object) -> SimpleNamespace:
            self.request_calls += 1
            return self.export

    artifacts = _Artifacts()
    app.dependency_overrides[get_asset_research_artifacts] = lambda: artifacts
    try:
        response = await client.post(
            "/api/v1/asset-research/reports/report-1/exports",
            headers={**auth_headers, "Idempotency-Key": "export-api-1"},
            json={"format": "MARKDOWN"},
        )
    finally:
        app.dependency_overrides.pop(get_asset_research_artifacts, None)

    assert response.status_code == 201, response.text
    assert response.json()["download_url"].endswith("/exports/export-1/download")
    assert artifacts.request_calls == 1
    assert artifacts.db.commit_calls == 1


@pytest.mark.asyncio
async def test_report_export_get_routes_do_not_create_or_commit(client, auth_headers) -> None:
    """Status and download reads must not recreate an export or write its audit state."""

    class _Db:
        commit_calls = 0

        async def commit(self) -> None:
            self.commit_calls += 1

    class _Artifacts:
        def __init__(self) -> None:
            self.db = _Db()
            self.get_calls = 0
            self.read_calls = 0
            self.request_calls = 0
            self.export = SimpleNamespace(
                id="export-1",
                report_id="report-1",
                format="MARKDOWN",
                status="SUCCEEDED",
                content_hash="a" * 64,
                error_code=None,
                created_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
                completed_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
            )

        async def request_export(self, **_: object) -> SimpleNamespace:
            self.request_calls += 1
            return self.export

        async def get_export(self, **_: object) -> SimpleNamespace:
            self.get_calls += 1
            return self.export

        async def read_export(self, **_: object) -> tuple[SimpleNamespace, bytes]:
            self.read_calls += 1
            return self.export, b"# public report\n"

    artifacts = _Artifacts()
    app.dependency_overrides[get_asset_research_artifacts] = lambda: artifacts
    try:
        status_response = await client.get(
            "/api/v1/asset-research/exports/export-1", headers=auth_headers
        )
        download_response = await client.get(
            "/api/v1/asset-research/exports/export-1/download", headers=auth_headers
        )
    finally:
        app.dependency_overrides.pop(get_asset_research_artifacts, None)

    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["download_url"].endswith("/exports/export-1/download")
    assert download_response.status_code == 200, download_response.text
    assert download_response.content == b"# public report\n"
    assert artifacts.get_calls == 1
    assert artifacts.read_calls == 1
    assert artifacts.request_calls == 0
    assert artifacts.db.commit_calls == 0


@pytest.mark.asyncio
async def test_stock_compatibility_route_is_read_only_and_uses_legacy_visibility_scope(
    client, auth_headers
) -> None:
    async with async_session_maker() as db:
        from app.models.stock_signal import StockSignalPrediction

        db.add(
            StockSignalPrediction(
                prediction_key="compat-system-buy",
                owner_scope="system",
                source="nightly_sse50",
                universe_code="SSE50",
                symbol="600000.SH",
                symbol_name="浦发银行",
                market_type="A股",
                as_of_date=datetime(2026, 7, 30, tzinfo=timezone.utc).date(),
                as_of_at=datetime(2026, 7, 30, 15, tzinfo=timezone.utc),
                available_at=datetime(2026, 7, 30, 19, tzinfo=timezone.utc),
                signal_action="BUY",
                confidence_score=0.75,
                risk_score=0.3,
                eligibility_status="eligible",
                quality_reasons_json=[],
                data_freshness_json={},
                feature_version="ohlcv-v1",
                decision_policy_version="baseline-v1",
                model_version="deterministic-shadow-v1",
                feature_snapshot_json={},
                policy_snapshot_json={},
                source_snapshot_hash="a" * 64,
                outcome_status="pending",
            )
        )
        await db.commit()

    response = await client.get(
        "/api/v1/asset-research/stock-compat/signals",
        headers=auth_headers,
        params={"symbol": "600000.SH"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["compatibility_version"] == "stock-signal-v1-to-asset-research-v1"
    assert payload["items"][0]["decision"]["recommendation"] == "BUY"
    assert payload["items"][0]["decision"]["execution_disabled"] is True
    assert payload["items"][0]["legacy_identity"]["identity_status"] == "LEGACY_UNRESOLVED"


@pytest.mark.asyncio
async def test_task_endpoint_queues_a_resolved_asset_without_running_it_in_the_request(
    client, auth_headers, monkeypatch
) -> None:
    class _Runner:
        def __init__(self) -> None:
            self.wake_calls = 0

        def wake(self) -> bool:
            self.wake_calls += 1
            return True

    runner = _Runner()
    monkeypatch.setattr(asset_research_api, "get_asset_research_task_runner", lambda: runner)
    await _register_approved_source(
        asset_type="futures", source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID
    )
    app.dependency_overrides[get_instrument_resolver] = lambda: _Resolver()
    try:
        resolved = await client.post(
            "/api/v1/asset-research/instruments/resolve",
            headers=auth_headers,
            json={"asset_type": "futures", "query": "IF2609", "venue": "CFFEX"},
        )
        assert resolved.status_code == 200, resolved.text
        response = await client.post(
            "/api/v1/asset-research/tasks",
            headers=auth_headers,
            json={"asset_type": "futures", "canonical_id": "futures:CFFEX:IF2609:CNY"},
        )
    finally:
        app.dependency_overrides.pop(get_instrument_resolver, None)

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "QUEUED"
    assert response.json()["progress"] == 0
    assert runner.wake_calls == 1


@pytest.mark.asyncio
async def test_task_endpoint_rejects_an_asset_without_an_approved_source_capability(
    client, auth_headers, monkeypatch
) -> None:
    class _Runner:
        def wake(self) -> bool:
            raise AssertionError("a closed capability must not wake background research")

    monkeypatch.setattr(asset_research_api, "get_asset_research_task_runner", _Runner)
    app.dependency_overrides[get_instrument_resolver] = lambda: _Resolver()
    try:
        resolved = await client.post(
            "/api/v1/asset-research/instruments/resolve",
            headers=auth_headers,
            json={"asset_type": "futures", "query": "IF2609", "venue": "CFFEX"},
        )
        assert resolved.status_code == 200, resolved.text
        response = await client.post(
            "/api/v1/asset-research/tasks",
            headers=auth_headers,
            json={"asset_type": "futures", "canonical_id": "futures:CFFEX:IF2609:CNY"},
        )
    finally:
        app.dependency_overrides.pop(get_instrument_resolver, None)

    assert response.status_code == 422, response.text
    assert response.json()["details"]["error_code"] == "SOURCE_CAPABILITY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_schedule_endpoint_rejects_an_asset_without_an_approved_source_capability(
    client, auth_headers
) -> None:
    app.dependency_overrides[get_instrument_resolver] = lambda: _Resolver()
    try:
        resolved = await client.post(
            "/api/v1/asset-research/instruments/resolve",
            headers=auth_headers,
            json={"asset_type": "futures", "query": "IF2609", "venue": "CFFEX"},
        )
        assert resolved.status_code == 200, resolved.text
        response = await client.post(
            "/api/v1/asset-research/schedules",
            headers=auth_headers,
            json={
                "asset_type": "futures",
                "canonical_id": "futures:CFFEX:IF2609:CNY",
                "cron_expression": "10 19 * * 1-5",
                "timezone": "Asia/Shanghai",
                "cutoff_policy": "futures-complete-session-v1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_instrument_resolver, None)

    assert response.status_code == 422, response.text
    assert response.json()["details"]["error_code"] == "SOURCE_CAPABILITY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_retry_endpoint_rechecks_source_capability_before_creating_a_new_task(
    client, auth_headers, monkeypatch
) -> None:
    class _Runner:
        def __init__(self) -> None:
            self.wake_calls = 0

        def wake(self) -> bool:
            self.wake_calls += 1
            return True

    runner = _Runner()
    monkeypatch.setattr(asset_research_api, "get_asset_research_task_runner", lambda: runner)
    await _register_approved_source(
        asset_type="futures", source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID
    )
    app.dependency_overrides[get_instrument_resolver] = lambda: _Resolver()
    try:
        resolved = await client.post(
            "/api/v1/asset-research/instruments/resolve",
            headers=auth_headers,
            json={"asset_type": "futures", "query": "IF2609", "venue": "CFFEX"},
        )
        assert resolved.status_code == 200, resolved.text
        created = await client.post(
            "/api/v1/asset-research/tasks",
            headers=auth_headers,
            json={"asset_type": "futures", "canonical_id": "futures:CFFEX:IF2609:CNY"},
        )
        assert created.status_code == 202, created.text
        async with async_session_maker() as db:
            task = await db.get(AssetAnalysisTask, created.json()["task_id"])
            source = await db.get(AssetDataSourceRegistry, DEFAULT_ASSET_RESEARCH_SOURCE_ID)
            assert task is not None
            assert source is not None
            task.status = "FAILED"
            await db.delete(source)
            await db.commit()
        response = await client.post(
            f"/api/v1/asset-research/tasks/{created.json()['task_id']}/retry",
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_instrument_resolver, None)

    assert response.status_code == 422, response.text
    assert response.json()["details"]["error_code"] == "SOURCE_CAPABILITY_UNAVAILABLE"
    assert runner.wake_calls == 1


@pytest.mark.asyncio
async def test_retry_endpoint_queues_a_new_task_and_wakes_the_durable_runner(
    client, auth_headers, monkeypatch
) -> None:
    class _Runner:
        def __init__(self) -> None:
            self.wake_calls = 0

        def wake(self) -> bool:
            self.wake_calls += 1
            return True

    runner = _Runner()
    monkeypatch.setattr(asset_research_api, "get_asset_research_task_runner", lambda: runner)
    await _register_approved_source(
        asset_type="futures", source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID
    )
    app.dependency_overrides[get_instrument_resolver] = lambda: _Resolver()
    try:
        resolved = await client.post(
            "/api/v1/asset-research/instruments/resolve",
            headers=auth_headers,
            json={"asset_type": "futures", "query": "IF2609", "venue": "CFFEX"},
        )
        assert resolved.status_code == 200, resolved.text
        created = await client.post(
            "/api/v1/asset-research/tasks",
            headers=auth_headers,
            json={"asset_type": "futures", "canonical_id": "futures:CFFEX:IF2609:CNY"},
        )
        assert created.status_code == 202, created.text
        async with async_session_maker() as db:
            task = await db.get(AssetAnalysisTask, created.json()["task_id"])
            assert task is not None
            task.status = "FAILED"
            task.progress = 100
            await db.commit()
        retried = await client.post(
            f"/api/v1/asset-research/tasks/{created.json()['task_id']}/retry",
            headers=auth_headers,
        )
        async with async_session_maker() as db:
            original = await db.get(AssetAnalysisTask, created.json()["task_id"])
            retried_task = await db.get(AssetAnalysisTask, retried.json()["task_id"])
            assert original is not None
            assert retried_task is not None
            assert original.status == "FAILED"
            assert retried_task.retry_of_task_id == original.id
    finally:
        app.dependency_overrides.pop(get_instrument_resolver, None)

    assert retried.status_code == 202, retried.text
    assert retried.json()["status"] == "QUEUED"
    assert retried.json()["task_id"] != created.json()["task_id"]
    assert runner.wake_calls == 2


@pytest.mark.asyncio
async def test_position_context_endpoints_are_owner_scoped_and_idempotent(
    client, auth_headers
) -> None:
    app.dependency_overrides[get_instrument_resolver] = lambda: _Resolver()
    try:
        resolved = await client.post(
            "/api/v1/asset-research/instruments/resolve",
            headers=auth_headers,
            json={"asset_type": "futures", "query": "IF2609", "venue": "CFFEX"},
        )
        assert resolved.status_code == 200, resolved.text
        request = {
            "canonical_id": "futures:CFFEX:IF2609:CNY",
            "position_context": "LONG",
            "long_quantity": "2",
            "as_of_at": "2026-08-01T00:00:00Z",
        }
        headers = {**auth_headers, "Idempotency-Key": "position-context-api-1"}
        created = await client.post(
            "/api/v1/asset-research/position-contexts", headers=headers, json=request
        )
        repeated = await client.post(
            "/api/v1/asset-research/position-contexts", headers=headers, json=request
        )
        _, other_headers = await register_and_login(client, username="asset_context_other")
        other_user_read = await client.get(
            f"/api/v1/asset-research/position-contexts/{created.json()['snapshot_id']}",
            headers=other_headers,
        )
    finally:
        app.dependency_overrides.pop(get_instrument_resolver, None)

    assert created.status_code == 201, created.text
    assert repeated.status_code == 201, repeated.text
    assert created.json()["snapshot_id"] == repeated.json()["snapshot_id"]
    assert created.json()["source_type"] == "USER_DECLARED"
    assert created.json()["account_connected"] is False
    assert other_user_read.status_code == 404


@pytest.mark.asyncio
async def test_schedule_endpoints_create_list_and_version_future_configuration(
    client, auth_headers
) -> None:
    await _register_approved_source(
        asset_type="futures", source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID
    )
    app.dependency_overrides[get_instrument_resolver] = lambda: _Resolver()
    try:
        resolved = await client.post(
            "/api/v1/asset-research/instruments/resolve",
            headers=auth_headers,
            json={"asset_type": "futures", "query": "IF2609", "venue": "CFFEX"},
        )
        assert resolved.status_code == 200, resolved.text
        created = await client.post(
            "/api/v1/asset-research/schedules",
            headers={**auth_headers, "Idempotency-Key": "asset-schedule-api-1"},
            json={
                "asset_type": "futures",
                "canonical_id": "futures:CFFEX:IF2609:CNY",
                "cron_expression": "10 19 * * 1-5",
                "timezone": "Asia/Shanghai",
                "cutoff_policy": "futures-complete-session-v1",
            },
        )
        schedule_id = created.json().get("schedule_id")
        listed = await client.get("/api/v1/asset-research/schedules", headers=auth_headers)
        updated = await client.patch(
            f"/api/v1/asset-research/schedules/{schedule_id}",
            headers=auth_headers,
            json={"enabled": False},
        )
    finally:
        app.dependency_overrides.pop(get_instrument_resolver, None)

    assert created.status_code == 201, created.text
    assert created.json()["position_context"] == "UNKNOWN"
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["schedule_id"] == schedule_id
    assert updated.status_code == 200, updated.text
    assert updated.json()["enabled"] is False
    assert updated.json()["schedule_version"] == 2


@pytest.mark.asyncio
async def test_admin_manifest_control_plane_is_authorized_idempotent_and_retires_schedules(
    client, auth_headers
) -> None:
    """Only an admin can expand a static manifest; it cannot become a runtime selector."""
    request = {
        "manifest_key": "api-futures-shadow",
        "manifest_version": "v1",
        "owner_scope": "PUBLIC_SHADOW",
        "approval_reference": "TEST-ONLY",
        "evidence_uri": "evidence://test/api-futures-shadow",
        "evidence_content_hash": "a" * 64,
        "entries": [
            {
                "entry_key": "if2609",
                "schedule": {
                    "asset_type": "futures",
                    "canonical_id": "futures:CFFEX:IF2609:CNY",
                    "cron_expression": "10 19 * * 1-5",
                    "timezone": "Asia/Shanghai",
                    "cutoff_policy": "futures-complete-session-v1",
                },
            }
        ],
    }
    denied = await client.post(
        "/api/v1/asset-research/admin/schedule-manifests",
        headers=auth_headers,
        json=request,
    )
    assert denied.status_code == 403

    await _register_approved_source(
        asset_type="futures", source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID
    )
    app.dependency_overrides[get_instrument_resolver] = lambda: _Resolver()
    app.dependency_overrides[require_data_admin_user] = lambda: SimpleNamespace(id="admin-fixture")
    try:
        resolved = await client.post(
            "/api/v1/asset-research/instruments/resolve",
            headers=auth_headers,
            json={"asset_type": "futures", "query": "IF2609", "venue": "CFFEX"},
        )
        assert resolved.status_code == 200, resolved.text
        headers = {**auth_headers, "Idempotency-Key": "manifest-api-1"}
        created = await client.post(
            "/api/v1/asset-research/admin/schedule-manifests",
            headers=headers,
            json=request,
        )
        repeated = await client.post(
            "/api/v1/asset-research/admin/schedule-manifests",
            headers=headers,
            json=request,
        )
        listed = await client.get(
            "/api/v1/asset-research/admin/schedule-manifests",
            headers=auth_headers,
        )
        retired = await client.post(
            f"/api/v1/asset-research/admin/schedule-manifests/{created.json()['manifest_id']}/retire",
            headers=auth_headers,
            json={"reason_codes": ["SCHEDULE.MANIFEST_REPLACED"]},
        )
    finally:
        app.dependency_overrides.pop(get_instrument_resolver, None)
        app.dependency_overrides.pop(require_data_admin_user, None)

    assert created.status_code == 201, created.text
    assert repeated.status_code == 201, repeated.text
    assert created.json()["manifest_id"] == repeated.json()["manifest_id"]
    assert created.json()["schedules"][0]["canonical_id"] == "futures:CFFEX:IF2609:CNY"
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["manifest_id"] == created.json()["manifest_id"]
    assert retired.status_code == 200, retired.text
    assert retired.json()["status"] == "RETIRED"
    assert retired.json()["schedules"][0]["enabled"] is False
