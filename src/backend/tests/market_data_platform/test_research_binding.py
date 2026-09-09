"""Focused contracts for sealed local-first research data bindings."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import func, select, update
from sqlalchemy.dialects import mysql, postgresql, sqlite

from app.db.database import async_session_maker
from app.models.market_data_platform import ImmutableMarketDataRecordError, MdResearchDataBinding
from app.models.permission import Role, user_roles
from app.models.user import User
from app.schemas.ai_strategy_research import AIStrategyResearchRunRequest
from app.schemas.asset_research import InstrumentIdentity
from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.access import MarketDataAccessAuthorizer, MarketDataQueryAccess
from app.services.market_data.catalog import DatasetStorageResolution
from app.services.market_data.coverage import (
    CoveragePlan,
    CoverageStatus,
    EventKey,
    ObservationQuality,
    QueryIdentity,
)
from app.services.market_data.identity import ResolvedMarketDataIdentity
from app.services.market_data.publication import MarketDataVisibilityAnchor
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.query_service import MarketDataQueryExecution
from app.services.market_data.research_binding import (
    MarketDataResearchBindingError,
    MarketDataResearchBindingService,
)
from app.services.market_data.store import LocalObservationRevision

UTC = timezone.utc
NOW = datetime(2026, 2, 3, 12, tzinfo=UTC)
START = datetime(2026, 1, 5, tzinfo=UTC)
END = datetime(2026, 1, 7, tzinfo=UTC)
CANONICAL_ID = "instrument:stock:CN-SSE:600000"
SIGNING_KEY = "research-binding-test-key-material-at-least-thirty-two-bytes"


class _ContractResolver:
    def __init__(self) -> None:
        self.calls: list[dict[str, str | None]] = []

    async def resolve(
        self,
        *,
        asset_type: str,
        symbol: str,
        period: str,
        family_id: str | None = None,
    ) -> dict[str, Any] | None:
        self.calls.append(
            {
                "asset_type": asset_type,
                "symbol": symbol,
                "period": period,
                "family_id": family_id,
            }
        )
        return {
            "version": "market-data-v2",
            "request": {
                "identity": {"canonical_id": CANONICAL_ID},
                "dataset_code": "market.bars",
                "data_kind": "bars",
                "frequency": "1d",
                "required_fields": ["close"],
                "adjustment": "qfq",
                "price_basis": "close",
                "currency": "CNY",
                "unit": "share",
                "source_policy_id": "market-default-v1",
                "mode": "local_first",
                "family_id": "stock.realtime",
                "family_contract_version": "market-data-family-v1",
            },
        }


class _LocalOnlyQueryService:
    def __init__(self, *, missing_ohlc: bool = False) -> None:
        self.requests: list[MarketDataQueryRequest] = []
        self.accesses: list[MarketDataQueryAccess | None] = []
        self.missing_ohlc = missing_ohlc
        self.online_fetch_attempts = 0

    async def execute(
        self,
        request: MarketDataQueryRequest,
        *,
        access: MarketDataQueryAccess | None = None,
    ) -> MarketDataQueryExecution:
        self.requests.append(request)
        self.accesses.append(access)
        return _execution_for(request, missing_ohlc=self.missing_ohlc)


async def _user(*, username: str) -> User:
    async with async_session_maker() as db:
        user = User(
            username=username,
            email=f"{username}@example.test",
            hashed_password="unused",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        await db.execute(user_roles.insert().values(user_id=user.id, role=Role.USER.value))
        await db.commit()
        return user


def _request(data_config: dict[str, object] | None = None) -> AIStrategyResearchRunRequest:
    return AIStrategyResearchRunRequest(
        symbol="600000",
        timeframe="1d",
        timeframe_n=1,
        start_date="2026-01-05",
        end_date="2026-01-06",
        data_config=data_config or {"market_data_asset_type": "stock"},
        start_paper_trading=False,
    )


def _load_research_binding_migration() -> Any:
    """Load the owned revision without depending on Alembic's module cache."""
    backend_root = Path(__file__).resolve().parents[2]
    path = backend_root / "alembic" / "versions" / "20260909_market_data_research_bindings.py"
    spec = importlib.util.spec_from_file_location("research_binding_migration", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity.model_validate(
        {
            "asset_type": "stock",
            "identity_level": "ASSET",
            "canonical_id": CANONICAL_ID,
            "display_symbol": "600000",
            "name": "测试股票",
            "venue": "CN-SSE",
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "identifier_type": "EXCHANGE_SYMBOL",
            "identifier_value": "600000.SH",
            "product_type": "EQUITY",
            "metadata_version": "stock-v1",
            "details": {"kind": "STOCK", "exchange_symbol": "600000.SH"},
        }
    )


def _execution_for(
    request: MarketDataQueryRequest,
    *,
    missing_ohlc: bool,
) -> MarketDataQueryExecution:
    resolved_query = ResolvedMarketDataQuery.from_request(
        request,
        canonical_id=CANONICAL_ID,
        dataset_code="market.bars",
        instrument_metadata_version="stock-v1",
    )
    identity = ResolvedMarketDataIdentity(
        instrument_id="11111111-1111-1111-1111-111111111111",
        canonical_id=CANONICAL_ID,
        asset_type="stock",
        metadata_version="stock-v1",
        venue="CN-SSE",
        identity=_identity(),
        valid_from=START - timedelta(days=10),
        valid_to=None,
        known_at=START - timedelta(days=10),
        visibility_sequence=3,
    )
    coverage_identity = QueryIdentity(
        dataset_code="market.bars",
        canonical_id=CANONICAL_ID,
        asset_type="stock",
        instrument_metadata_version="stock-v1",
        data_kind="bars",
        market="CN-SSE",
        frequency="1d",
        source_policy_id="market-default-v1",
        adjustment="qfq",
        price_basis="close",
        currency="CNY",
        unit="share",
    )
    context = ResolvedMarketDataQueryContext(
        query=resolved_query,
        identity=identity,
        storage=DatasetStorageResolution(
            dataset_id="dataset-market-bars",
            dataset_code="market.bars",
            storage_id="canonical-market-data",
            engine="sqlite",
            database_name="test",
            physical_table="md_observation_revisions",
            write_mode="canonical_read_write",
        ),
        coverage_identity=coverage_identity,
    )
    event_times = (request.start, request.start + timedelta(days=1))
    observations: list[LocalObservationRevision] = []
    for index, event_at in enumerate(event_times, start=1):
        fields: dict[str, object] = {
            "open": "10.00",
            "high": "11.00",
            "low": "9.50",
            "close": 10.5,
            "volume": "1000",
            "open_interest": "12",
        }
        if missing_ohlc:
            fields.pop("high")
        observations.append(
            LocalObservationRevision(
                revision_id=f"00000000-0000-0000-0000-{index:012d}",
                source_snapshot_id=f"10000000-0000-0000-0000-{index:012d}",
                event_at=event_at,
                available_at=event_at + timedelta(hours=1),
                committed_at=NOW,
                visible_at=NOW,
                visibility_sequence=index,
                revision_number=1,
                quality=ObservationQuality.PASS,
                fields=fields,
            )
        )
    expected_keys = tuple(EventKey(event_at) for event_at in event_times)
    anchor = MarketDataVisibilityAnchor(visible_at=request.knowledge_cutoff or NOW, max_visibility_sequence=3)
    return MarketDataQueryExecution(
        context=context,
        knowledge_cutoff=request.knowledge_cutoff or NOW,
        identity_knowledge_cutoff=request.knowledge_cutoff or NOW,
        visibility_anchor=anchor,
        identity_visibility_anchor=anchor,
        coverage=CoveragePlan(
            status=CoverageStatus.COMPLETE,
            expected_event_keys=expected_keys,
            accepted_event_keys=expected_keys,
            missing_event_keys=(),
            gaps=(),
            rejection_counts={},
        ),
        observations=tuple(observations),
        next_cursor=None,
        fetches=(),
        warnings=(),
    )


@pytest.mark.asyncio
async def test_bind_request_forces_strict_local_only_and_persists_deterministic_csv(
    tmp_path: Path,
) -> None:
    """A bound request carries only a signed opaque receipt, never a client path."""
    user = await _user(username="binding-owner")
    contracts = _ContractResolver()
    query_service = _LocalOnlyQueryService()
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            query_service,
            contracts,
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        bound = await service.bind_request(
            user_id=user.id,
            request=_request(),
            intent_id="ai-research-task-001",
        )
        repeated = await service.bind_request(
            user_id=user.id,
            request=_request(),
            intent_id="ai-research-task-001",
        )
        count = await db.scalar(select(func.count()).select_from(MdResearchDataBinding))

    assert contracts.calls == [
        {
            "asset_type": "stock",
            "symbol": "600000",
            "period": "1d",
            "family_id": "stock.realtime",
        },
        {
            "asset_type": "stock",
            "symbol": "600000",
            "period": "1d",
            "family_id": "stock.realtime",
        },
    ]
    assert len(query_service.requests) == 2
    assert query_service.online_fetch_attempts == 0
    assert all(isinstance(access, MarketDataQueryAccess) for access in query_service.accesses)
    for query in query_service.requests:
        assert query.mode == "local_only"
        assert query.purpose == "backtest"
        assert query.consistency == "strict"
        assert query.knowledge_cutoff == END
        assert query.cursor is None
    assert count == 1
    assert bound.data_config == repeated.data_config
    assert set(bound.data_config) == {
        "market_data_asset_type",
        "market_data_binding_id",
        "market_data_binding_hash",
        "market_data_binding_signature",
        "market_data_binding_required",
    }
    assert bound.data_config["market_data_asset_type"] == "stock"
    binding_hash = str(bound.data_config["market_data_binding_hash"])
    artifact = tmp_path / "bindings" / binding_hash / "data.csv"
    assert artifact.read_text(encoding="utf-8") == (
        "datetime,open,high,low,close,volume,openinterest\n"
        "2026-01-05T00:00:00.000000Z,10,11,9.5,10.5,1000,12\n"
        "2026-01-06T00:00:00.000000Z,10,11,9.5,10.5,1000,12\n"
    )


@pytest.mark.asyncio
async def test_bind_request_rejects_client_path_injection_and_missing_ohlc(tmp_path: Path) -> None:
    """A caller cannot provide artifact selectors and cannot synthesize OHLC bars."""
    user = await _user(username="binding-input-reject")
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            _LocalOnlyQueryService(),
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        with pytest.raises(MarketDataResearchBindingError) as injected:
            await service.bind_request(
                user_id=user.id,
                request=_request(
                    {
                        "market_data_asset_type": "stock",
                        "directory_path": "/tmp/attacker-controlled.csv",
                    }
                ),
                intent_id="ai-research-task-002",
            )
        assert injected.value.code == "MARKET_DATA_BINDING_CLIENT_DATA_CONFIG_FORBIDDEN"

        missing_ohlc_service = MarketDataResearchBindingService(
            db,
            _LocalOnlyQueryService(missing_ohlc=True),
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        with pytest.raises(MarketDataResearchBindingError) as missing_ohlc:
            await missing_ohlc_service.bind_request(
                user_id=user.id,
                request=_request(),
                intent_id="ai-research-task-003",
            )
    assert missing_ohlc.value.code == "MARKET_DATA_BINDING_OHLC_REQUIRED"


@pytest.mark.asyncio
async def test_runtime_binding_rechecks_owner_signature_subset_and_artifact_digest(
    tmp_path: Path,
) -> None:
    """Runtime can consume a sealed subset but cannot cross owners or tamper bytes."""
    owner = await _user(username="binding-runtime-owner")
    other = await _user(username="binding-runtime-other")
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            _LocalOnlyQueryService(),
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        bound = await service.bind_request(
            user_id=owner.id,
            request=_request(),
            intent_id="ai-research-task-004",
        )
        config = bound.data_config
        runtime = await service.resolve_runtime_binding(
            user_id=owner.id,
            binding_id=str(config["market_data_binding_id"]),
            binding_hash=str(config["market_data_binding_hash"]),
            signature=str(config["market_data_binding_signature"]),
            symbol="600000",
            timeframe="1d",
            timeframe_n=1,
            start="2026-01-06",
            end="2026-01-06",
        )
        assert runtime.artifact_path.is_file()
        assert runtime.query_semantics["full_window_start"] == "2026-01-05T00:00:00.000000Z"
        assert runtime.query_semantics["full_window_end"] == "2026-01-07T00:00:00.000000Z"

        with pytest.raises(MarketDataResearchBindingError) as cross_owner:
            await service.resolve_runtime_binding(
                user_id=other.id,
                binding_id=str(config["market_data_binding_id"]),
                binding_hash=str(config["market_data_binding_hash"]),
                signature=str(config["market_data_binding_signature"]),
            )
        assert cross_owner.value.code == "MARKET_DATA_BINDING_OWNER_DENIED"

        with pytest.raises(MarketDataResearchBindingError) as expanded_window:
            await service.resolve_runtime_binding(
                user_id=owner.id,
                binding_id=str(config["market_data_binding_id"]),
                binding_hash=str(config["market_data_binding_hash"]),
                signature=str(config["market_data_binding_signature"]),
                symbol="600000",
                timeframe="1d",
                timeframe_n=1,
                start="2026-01-04T00:00:00Z",
                end="2026-01-07T00:00:00Z",
            )
        assert expanded_window.value.code == "MARKET_DATA_BINDING_RUNTIME_WINDOW_INVALID"

        runtime.artifact_path.chmod(0o640)
        runtime.artifact_path.write_text("tampered", encoding="utf-8")
        with pytest.raises(MarketDataResearchBindingError) as tampered:
            await service.resolve_runtime_binding(
                user_id=owner.id,
                binding_id=str(config["market_data_binding_id"]),
                binding_hash=str(config["market_data_binding_hash"]),
                signature=str(config["market_data_binding_signature"]),
            )
    assert tampered.value.code == "MARKET_DATA_BINDING_ARTIFACT_SIZE_MISMATCH"


@pytest.mark.asyncio
async def test_binding_without_a_signing_key_fails_before_any_local_query(tmp_path: Path) -> None:
    """A disabled/missing HMAC key cannot mint a runtime-usable artifact."""
    user = await _user(username="binding-no-key")
    query_service = _LocalOnlyQueryService()
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            query_service,
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=None,
            clock=lambda: NOW,
        )
        with pytest.raises(MarketDataResearchBindingError) as missing_key:
            await service.bind_request(
                user_id=user.id,
                request=_request(),
                intent_id="ai-research-task-005",
            )
    assert missing_key.value.code == "MARKET_DATA_BINDING_SIGNING_KEY_REQUIRED"
    assert query_service.requests == []


@pytest.mark.asyncio
async def test_binding_model_is_append_only_and_runtime_rejects_direct_model_tamper(
    tmp_path: Path,
) -> None:
    """ORM writes and bulk SQL cannot alter a sealed binding's runtime facts."""
    user = await _user(username="binding-immutable")
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            _LocalOnlyQueryService(),
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        bound = await service.bind_request(
            user_id=user.id,
            request=_request(),
            intent_id="ai-research-task-006",
        )
        binding_id = str(bound.data_config["market_data_binding_id"])
        binding_hash = str(bound.data_config["market_data_binding_hash"])
        signature = str(bound.data_config["market_data_binding_signature"])
        binding = await db.get(MdResearchDataBinding, binding_id)
        assert binding is not None
        binding.status = "INVALID"
        with pytest.raises(ImmutableMarketDataRecordError):
            await db.commit()
        await db.rollback()

        await db.execute(
            update(MdResearchDataBinding)
            .where(MdResearchDataBinding.id == binding_id)
            .values(canonical_id=f"{CANONICAL_ID}:tampered")
        )
        await db.commit()

    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            _LocalOnlyQueryService(),
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        with pytest.raises(MarketDataResearchBindingError) as tampered_record:
            await service.resolve_runtime_binding(
                user_id=user.id,
                binding_id=binding_id,
                binding_hash=binding_hash,
                signature=signature,
            )
    assert tampered_record.value.code == "MARKET_DATA_BINDING_MANIFEST_INVALID"


def test_research_binding_migration_preserves_exact_identifier_collation() -> None:
    """Fresh MySQL/PostgreSQL/SQLite binding DDL keeps canonical IDs bytewise."""
    migration = _load_research_binding_migration()
    assert migration.down_revision == "20260909_ai_research_market_data_merge"
    for dialect, expected_collation in (
        (mysql.dialect(), "COLLATE utf8mb4_bin"),
        (postgresql.dialect(), 'COLLATE "C"'),
        (sqlite.dialect(), 'COLLATE "BINARY"'),
    ):
        table = sa.Table(
            "research_binding_identity_probe",
            sa.MetaData(),
            sa.Column("canonical_id", migration._exact_identifier_type(512), nullable=False),
        )
        ddl = str(sa.schema.CreateTable(table).compile(dialect=dialect))
        assert expected_collation in ddl
