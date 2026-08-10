"""Immutable, user-declared position-context snapshots stay isolated and idempotent."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.user import User
from app.schemas.asset_research import (
    AssetAnalysisCreateRequest,
    FuturesIdentityDetails,
    InstrumentIdentity,
    OptionIdentityDetails,
    PositionContextCreateRequest,
)
from app.services.asset_research.data import DEFAULT_ASSET_RESEARCH_SOURCE_ID
from app.services.asset_research.orchestrator import (
    AssetResearchOrchestrationError,
    AssetResearchOrchestrator,
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


def _option_identity(expires_at: datetime) -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="option",
        identity_level="CONTRACT",
        canonical_id="option:XSHG:510050C2609M03000:CNY",
        display_symbol="510050C2609M03000",
        name="上证50ETF认购期权",
        venue="XSHG",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value="510050C2609M03000",
        product_type="OPTION",
        metadata_version="fixture-v1",
        details=OptionIdentityDetails(
            option_contract_id="510050C2609M03000",
            exchange="XSHG",
            underlying_instrument_id="fund:XSHG:510050:CNY",
            underlying_contract_id="fund:XSHG:510050:CNY",
            expiry_at=expires_at,
            last_trade_at=expires_at,
            strike=Decimal("3"),
            option_right="CALL",
            exercise_style="EUROPEAN",
            contract_multiplier=Decimal("10000"),
            settlement_type="CASH",
            deliverable="10000 ETF units",
            quote_unit="CNY_PER_UNIT",
            tick_size=Decimal("0.0001"),
            trading_calendar_id="XSHG",
            automatic_exercise_rule="EXERCISE_IF_ITM",
            position_limit_rule="XSHG_ETF_OPTION_V1",
            margin_rule_version="XSHG_ETF_OPTION_MARGIN_V1",
        ),
    )


def _approved_option_source() -> AssetDataSourceRegistry:
    """Permit the task-creation branch used by the option-context contract test."""
    return AssetDataSourceRegistry(
        source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID,
        asset_types=["option"],
        jurisdictions=["GLOBAL"],
        license_status="RESEARCH_APPROVED",
        allowed_uses=["RESEARCH_ONLY"],
        redistribution_policy="NO_REDISTRIBUTION",
        derived_data_policy="ALLOWED",
        retention_policy="research-v1",
        effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        freshness_sla={},
        enabled=True,
    )


@pytest.mark.asyncio
async def test_position_context_is_immutable_user_declared_and_idempotent() -> None:
    async with async_session_maker() as db:
        user = User(
            username="position_context_user",
            email="position-context@example.test",
            hashed_password="hash",
        )
        db.add(user)
        await db.flush()
        service = AssetResearchOrchestrator(db)
        await service.persist_identity(_identity())

        request = PositionContextCreateRequest(
            canonical_id="futures:CFFEX:IF2609:CNY",
            position_context="LONG",
            long_quantity=Decimal("2"),
            as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        first = await service.create_position_context(
            user_id=user.id,
            request=request,
            idempotency_key="position-context-1",
        )
        second = await service.create_position_context(
            user_id=user.id,
            request=request,
            idempotency_key="position-context-1",
        )

    assert first.id == second.id
    assert first.position_context == "LONG"
    assert first.source_type == "USER_DECLARED"
    assert first.source_manifest_json == {"account_connected": False, "source": "USER_DECLARED"}


@pytest.mark.asyncio
async def test_position_context_rejects_invalid_quantity_and_conflicting_idempotency_key() -> None:
    async with async_session_maker() as db:
        user = User(
            username="position_context_conflict",
            email="position-conflict@example.test",
            hashed_password="hash",
        )
        db.add(user)
        await db.flush()
        service = AssetResearchOrchestrator(db)
        await service.persist_identity(_identity())

        with pytest.raises(AssetResearchOrchestrationError, match="POSITION_CONTEXT_INVALID"):
            await service.create_position_context(
                user_id=user.id,
                request=PositionContextCreateRequest(
                    canonical_id="futures:CFFEX:IF2609:CNY",
                    position_context="LONG",
                    as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                ),
                idempotency_key="position-context-2",
            )

        await service.create_position_context(
            user_id=user.id,
            request=PositionContextCreateRequest(
                canonical_id="futures:CFFEX:IF2609:CNY",
                position_context="FLAT",
                as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            ),
            idempotency_key="position-context-2",
        )
        with pytest.raises(AssetResearchOrchestrationError, match="IDEMPOTENCY_CONFLICT"):
            await service.create_position_context(
                user_id=user.id,
                request=PositionContextCreateRequest(
                    canonical_id="futures:CFFEX:IF2609:CNY",
                    position_context="SHORT",
                    short_quantity=Decimal("1"),
                    as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                ),
                idempotency_key="position-context-2",
            )


@pytest.mark.asyncio
async def test_option_context_must_be_visible_and_unexpired_at_the_research_cutoff() -> None:
    """A close authorization cannot be inherited from an expired option context."""
    now = datetime.now(timezone.utc)
    cutoff_at = now + timedelta(hours=1)
    identity = _option_identity(now + timedelta(days=30))
    async with async_session_maker() as db:
        user = User(
            username="option_position_context_user",
            email="option-position-context@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(_approved_option_source())
        await db.flush()
        service = AssetResearchOrchestrator(db)
        instrument = await service.persist_identity(identity)
        expired_at_cutoff = await service.create_position_context(
            user_id=user.id,
            request=PositionContextCreateRequest(
                canonical_id=identity.canonical_id,
                position_context="LONG",
                long_quantity=Decimal("1"),
                as_of_at=now,
                expires_at=now + timedelta(minutes=10),
            ),
        )
        task = await service.create_pending(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="option",
                canonical_id=identity.canonical_id,
                position_context="LONG",
                position_context_snapshot_id=expired_at_cutoff.id,
            ),
        )
        close_authorized = await service._normalize_task_position_context_for_cutoff(
            task=task,
            instrument=instrument,
            identity=identity,
            cutoff_at=cutoff_at,
        )

        valid_at_cutoff = await service.create_position_context(
            user_id=user.id,
            request=PositionContextCreateRequest(
                canonical_id=identity.canonical_id,
                position_context="LONG",
                long_quantity=Decimal("1"),
                as_of_at=now,
                expires_at=now + timedelta(days=2),
            ),
        )
        valid_task = await service.create_pending(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="option",
                canonical_id=identity.canonical_id,
                position_context="LONG",
                position_context_snapshot_id=valid_at_cutoff.id,
            ),
        )
        valid_close_authorized = await service._normalize_task_position_context_for_cutoff(
            task=valid_task,
            instrument=instrument,
            identity=identity,
            cutoff_at=cutoff_at,
        )

    assert close_authorized is False
    assert task.position_context == "UNKNOWN"
    assert task.position_context_snapshot_id is None
    assert valid_close_authorized is True
    assert valid_task.position_context == "LONG"
    assert valid_task.position_context_snapshot_id == valid_at_cutoff.id
