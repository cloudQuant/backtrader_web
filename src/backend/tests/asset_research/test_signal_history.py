"""Public signal history exposes published facts and outcome maturity, never candidates."""

from datetime import datetime, timezone

import pytest

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.user import User
from app.schemas.asset_research import (
    AssetAnalysisCreateRequest,
    FuturesIdentityDetails,
    InstrumentIdentity,
    RawAssetSnapshot,
)
from app.services.asset_research.orchestrator import AssetResearchOrchestrator


class _Data:
    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version="fixture-v1",
            raw_fields={"snapshot": {"price": 101, "bid": 100.9, "ask": 101.1}},
            history_rows=[
                {"date": "2026-07-31", "close": 100},
                {"date": "2026-08-01", "close": 101},
            ],
            source_manifest={
                "provider": "signal-history-fixture",
                "capabilities": ["price", "contract_calendar"],
            },
            license_tags=[],
            content_hash="e" * 64,
        )


def _identity() -> InstrumentIdentity:
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


@pytest.mark.asyncio
async def test_history_summary_evidence_and_outcomes_are_owner_scoped_and_public_only() -> None:
    async with async_session_maker() as db:
        user = User(
            username="signal_history_user",
            email="signal-history@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="signal-history-fixture",
                asset_types=["futures"],
                jurisdictions=["GLOBAL"],
                license_status="APPROVED",
                allowed_uses=["RESEARCH_ONLY"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy="research-v1",
                effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                freshness_sla={},
                enabled=True,
            )
        )
        await db.flush()
        service = AssetResearchOrchestrator(db, data_adapter=_Data())
        await service.persist_identity(_identity())
        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures", canonical_id="futures:CFFEX:IF2609:CNY"
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        history = await service.get_signal_history(
            user_id=user.id,
            asset_type="futures",
            canonical_id="futures:CFFEX:IF2609:CNY",
        )
        summary = await service.get_signal_summary(
            user_id=user.id,
            asset_type="futures",
            canonical_id="futures:CFFEX:IF2609:CNY",
        )
        evidence = await service.get_signal_evidence(
            user_id=user.id, prediction_id=history.items[0].prediction_id
        )
        outcomes = await service.get_signal_outcomes(
            user_id=user.id, prediction_id=history.items[0].prediction_id
        )

    assert task.status == "SUCCEEDED"
    assert history.items[0].owner_scope == "USER"
    assert history.items[0].published_decision.actionability == "RESEARCH_ONLY"
    assert "candidate_decision" not in history.items[0].model_dump()
    assert summary.generated_count == 1
    assert summary.actioned_generated_count == 0
    assert evidence is not None
    assert "raw_fields" not in evidence
    assert outcomes[0].status == "PENDING"
