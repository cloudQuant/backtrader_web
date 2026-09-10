"""Focused contracts for sealed local-first research data bindings."""

from __future__ import annotations

import importlib.util
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects import mysql, postgresql, sqlite

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.data_governance import DgProvider
from app.models.market_data_platform import (
    SOURCE_AUTHORIZATION_STATE_VERIFIED,
    ImmutableMarketDataRecordError,
    MdResearchDataBinding,
    MdResearchDataBindingConsumer,
    MdResearchDataBindingRevocation,
    MdResearchDataBindingScope,
    MdSourceSnapshot,
)
from app.models.permission import Role, user_roles
from app.models.user import User
from app.models.workspace import StrategyUnit, Workspace
from app.schemas.ai_strategy_research import AIStrategyResearchRunRequest
from app.schemas.asset_research import InstrumentIdentity
from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.access import (
    MarketDataAccessAuthorizer,
    MarketDataAuthorizationError,
    MarketDataQueryAccess,
)
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
    _strict_research_bars_family_id,
    build_market_data_research_binding_service,
)
from app.services.market_data.store import LocalObservationRevision

UTC = timezone.utc
NOW = datetime(2026, 2, 3, 12, tzinfo=UTC)
START = datetime(2026, 1, 5, tzinfo=UTC)
END = datetime(2026, 1, 7, tzinfo=UTC)
CANONICAL_ID = "instrument:stock:CN-SSE:600000"
SIGNING_KEY = "research-binding-test-key-material-at-least-thirty-two-bytes"
_SEALED_SOURCE_ID = "akshare"
_SEALED_PROVIDER_ID = "20000000-0000-0000-0000-000000000000"
_SEALED_SOURCE_SNAPSHOT_IDS = (
    "10000000-0000-0000-0000-000000000001",
    "10000000-0000-0000-0000-000000000002",
)
_SHA256_A = "a" * 64
_SHA256_B = "b" * 64
_SHA256_C = "c" * 64


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
    def __init__(
        self,
        *,
        missing_ohlc: bool = False,
        execution_error: Exception | None = None,
        close_adjustment: float = 0.0,
        on_execute: Callable[[MarketDataQueryRequest], Awaitable[None]] | None = None,
    ) -> None:
        self.requests: list[MarketDataQueryRequest] = []
        self.accesses: list[MarketDataQueryAccess | None] = []
        self.missing_ohlc = missing_ohlc
        self.execution_error = execution_error
        self.close_adjustment = close_adjustment
        self.on_execute = on_execute
        self.online_fetch_attempts = 0

    async def execute(
        self,
        request: MarketDataQueryRequest,
        *,
        access: MarketDataQueryAccess | None = None,
    ) -> MarketDataQueryExecution:
        self.requests.append(request)
        self.accesses.append(access)
        if self.on_execute is not None:
            await self.on_execute(request)
        if self.execution_error is not None:
            raise self.execution_error
        return _execution_for(
            request,
            missing_ohlc=self.missing_ohlc,
            close_adjustment=self.close_adjustment,
        )


async def _user(*, username: str) -> User:
    async with async_session_maker() as db:
        await _seed_sealed_source_evidence(db)
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


async def _seed_sealed_source_evidence(db: Any) -> None:
    """Persist the source-snapshot/registry chain used by the local fake."""
    provider = await db.get(DgProvider, _SEALED_PROVIDER_ID)
    if provider is None:
        db.add(
            DgProvider(
                id=_SEALED_PROVIDER_ID,
                provider_id=_SEALED_SOURCE_ID,
                name="Sealed test source",
                category="market",
                is_active=True,
            )
        )
    registry = await db.get(AssetDataSourceRegistry, _SEALED_SOURCE_ID)
    if registry is None:
        db.add(
            AssetDataSourceRegistry(
                source_id=_SEALED_SOURCE_ID,
                asset_types=["stock"],
                jurisdictions=["CN"],
                license_status="APPROVED",
                allowed_uses=["BACKTEST"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy="market-data-v1",
                effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                effective_to=None,
                retention_expires_at=None,
                enabled=True,
                updated_at=NOW,
            )
        )
    await db.flush()
    existing_snapshot_ids = set(
        (
            await db.scalars(
                select(MdSourceSnapshot.id).where(
                    MdSourceSnapshot.id.in_(_SEALED_SOURCE_SNAPSHOT_IDS)
                )
            )
        ).all()
    )
    for source_snapshot_id in _SEALED_SOURCE_SNAPSHOT_IDS:
        if source_snapshot_id in existing_snapshot_ids:
            continue
        db.add(
            MdSourceSnapshot(
                id=source_snapshot_id,
                provider_id=_SEALED_PROVIDER_ID,
                platform="akshare",
                source_id=_SEALED_SOURCE_ID,
                adapter_id="akshare-test",
                endpoint_version="test-v1",
                request_fingerprint_sha256=_SHA256_A,
                payload_sha256=_SHA256_B,
                request_json={},
                payload_manifest_json={},
                provenance_json={},
                source_authorization_state=SOURCE_AUTHORIZATION_STATE_VERIFIED,
                source_authorization_descriptor_sha256=_SHA256_C,
                retrieved_at=NOW,
            )
        )


async def _attach_research_unit(
    *,
    db: Any,
    service: MarketDataResearchBindingService,
    user: User,
    bound: AIStrategyResearchRunRequest,
    workspace_name: str = "binding research workspace",
) -> tuple[str, str]:
    """Create a trusted research unit and persist its binding consumer receipt."""
    workspace = Workspace(
        user_id=user.id,
        name=workspace_name,
        workspace_type="research",
    )
    db.add(workspace)
    await db.flush()
    unit = StrategyUnit(
        workspace_id=workspace.id,
        strategy_name="binding strategy",
        symbol="600000",
        timeframe="1d",
        timeframe_n=1,
        category="stock",
        data_config={
            **dict(bound.data_config),
            "range_type": "date",
            "start_date": "2026-01-05",
            "end_date": "2026-01-06",
            "use_end_date": True,
        },
    )
    db.add(unit)
    await db.commit()
    await service.attach_runtime_binding_consumer(
        user_id=user.id,
        binding_id=str(bound.data_config["market_data_binding_id"]),
        binding_hash=str(bound.data_config["market_data_binding_hash"]),
        signature=str(bound.data_config["market_data_binding_signature"]),
        intent_id=str(bound.data_config["market_data_binding_intent_id"]),
        workspace_id=workspace.id,
        unit_id=unit.id,
    )
    return workspace.id, unit.id


def _request(
    data_config: dict[str, object] | None = None,
    *,
    timeframe: str = "1d",
) -> AIStrategyResearchRunRequest:
    return AIStrategyResearchRunRequest(
        symbol="600000",
        timeframe=timeframe,
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


@pytest.mark.asyncio
async def test_production_binding_builder_rejects_settings_only_enablement_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh builder cannot turn an enabled environment flag into a grant."""
    import app.api.data.queries as data_queries

    artifact_root = tmp_path / "must-not-be-created"
    monkeypatch.setattr(
        data_queries,
        "get_settings",
        lambda: SimpleNamespace(
            MARKET_DATA_QUERY_V2_ENABLED=True,
            MARKET_DATA_ONLINE_FETCH_ENABLED=True,
            MARKET_DATA_RESEARCH_CACHE_FILL_ENABLED=True,
            MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_ENABLED=True,
            MARKET_DATA_OPENBB_ALLOWED_MARKETS="",
            MARKET_DATA_OPENBB_PROVIDER="yfinance",
            MARKET_DATA_RESEARCH_ARTIFACT_ROOT=str(artifact_root),
            MARKET_DATA_RESEARCH_ARTIFACT_SIGNING_KEY=SIGNING_KEY,
        ),
    )
    user = await _user(username="binding-builder-settings-only")

    async with async_session_maker() as db:
        with pytest.raises(MarketDataResearchBindingError) as failure:
            await build_market_data_research_binding_service(db, user_id=user.id)
        assert await db.scalar(select(func.count()).select_from(MdResearchDataBinding)) == 0

    assert failure.value.code == "MARKET_DATA_BRIDGE_DISABLED"
    assert not artifact_root.exists()


def _execution_for(
    request: MarketDataQueryRequest,
    *,
    missing_ohlc: bool,
    close_adjustment: float = 0.0,
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
            "close": 10.5 + close_adjustment,
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
    anchor = MarketDataVisibilityAnchor(
        visible_at=request.knowledge_cutoff or NOW, max_visibility_sequence=3
    )
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


@pytest.mark.parametrize(
    ("asset_type", "expected_family_id"),
    (
        ("stock", "stock.realtime"),
        ("futures", "futures.realtime"),
        ("bond", "bond.realtime"),
        ("fund", "fund.realtime"),
        ("option", "option.realtime"),
        ("fx", "fx.realtime"),
        ("crypto", "crypto.range"),
    ),
)
def test_strict_research_bars_family_selection_is_explicit(
    asset_type: str,
    expected_family_id: str,
) -> None:
    """A snapshot family can never become the strict-backtest bars fallback."""
    assert _strict_research_bars_family_id(asset_type) == expected_family_id


@pytest.mark.asyncio
@pytest.mark.parametrize("timeframe", ("1d", "1w", "1mo"))
async def test_bind_request_rejects_unconfigured_crypto_bars_before_contract_or_query(
    tmp_path: Path,
    timeframe: str,
) -> None:
    """Crypto range remains a fail-closed future bars route until explicitly enabled."""
    user = await _user(username=f"binding-crypto-{timeframe}")
    contracts = _ContractResolver()
    query_service = _LocalOnlyQueryService()
    artifact_root = tmp_path / "artifacts"
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            query_service,
            contracts,
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            artifact_root,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        with pytest.raises(MarketDataResearchBindingError) as failure:
            await service.bind_request(
                user_id=user.id,
                request=_request(
                    {"market_data_asset_type": "crypto"},
                    timeframe=timeframe,
                ),
                intent_id=f"ai-research-crypto-{timeframe}",
            )
        binding_count = await db.scalar(select(func.count()).select_from(MdResearchDataBinding))

    assert failure.value.code == "MARKET_DATA_BINDING_STRICT_BARS_FAMILY_UNCONFIGURED"
    assert contracts.calls == []
    assert query_service.requests == []
    assert query_service.online_fetch_attempts == 0
    assert binding_count == 0
    assert not (artifact_root / "bindings").exists()


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
        "market_data_binding_intent_id",
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
        workspace_id, unit_id = await _attach_research_unit(
            db=db,
            service=service,
            user=owner,
            bound=bound,
        )
        runtime = await service.resolve_runtime_binding(
            user_id=owner.id,
            binding_id=str(config["market_data_binding_id"]),
            binding_hash=str(config["market_data_binding_hash"]),
            signature=str(config["market_data_binding_signature"]),
            workspace_id=workspace_id,
            unit_id=unit_id,
            intent_id=str(config["market_data_binding_intent_id"]),
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
                workspace_id=workspace_id,
                unit_id=unit_id,
                intent_id=str(config["market_data_binding_intent_id"]),
            )
        assert cross_owner.value.code == "MARKET_DATA_BINDING_OWNER_DENIED"

        with pytest.raises(MarketDataResearchBindingError) as expanded_window:
            await service.resolve_runtime_binding(
                user_id=owner.id,
                binding_id=str(config["market_data_binding_id"]),
                binding_hash=str(config["market_data_binding_hash"]),
                signature=str(config["market_data_binding_signature"]),
                workspace_id=workspace_id,
                unit_id=unit_id,
                intent_id=str(config["market_data_binding_intent_id"]),
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
                workspace_id=workspace_id,
                unit_id=unit_id,
                intent_id=str(config["market_data_binding_intent_id"]),
            )
    assert tampered.value.code == "MARKET_DATA_BINDING_ARTIFACT_SIZE_MISMATCH"


@pytest.mark.asyncio
async def test_runtime_binding_rejects_a_copied_token_without_a_server_consumer(
    tmp_path: Path,
) -> None:
    """An owner cannot reuse a sealed token in a second browser-created unit."""
    owner = await _user(username="binding-copy-owner")
    query_service = _LocalOnlyQueryService()
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            query_service,
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        bound = await service.bind_request(
            user_id=owner.id,
            request=_request(),
            intent_id="ai-research-task-copy-001",
        )
        workspace_id, trusted_unit_id = await _attach_research_unit(
            db=db,
            service=service,
            user=owner,
            bound=bound,
        )
        copied_unit = StrategyUnit(
            workspace_id=workspace_id,
            strategy_name="copied binding strategy",
            symbol="600000",
            timeframe="1d",
            timeframe_n=1,
            category="stock",
            data_config={
                **dict(bound.data_config),
                "range_type": "date",
                "start_date": "2026-01-05",
                "end_date": "2026-01-06",
                "use_end_date": True,
            },
        )
        db.add(copied_unit)
        await db.commit()
        binding_id = str(bound.data_config["market_data_binding_id"])
        scope = await db.get(MdResearchDataBindingScope, binding_id)
        consumers = list(
            (
                await db.scalars(
                    select(MdResearchDataBindingConsumer).where(
                        MdResearchDataBindingConsumer.binding_id == binding_id
                    )
                )
            ).all()
        )

        assert scope is not None
        assert scope.workspace_id == workspace_id
        assert [consumer.unit_id for consumer in consumers] == [trusted_unit_id]

        with pytest.raises(MarketDataResearchBindingError) as copied:
            await service.resolve_runtime_binding(
                user_id=owner.id,
                binding_id=binding_id,
                binding_hash=str(bound.data_config["market_data_binding_hash"]),
                signature=str(bound.data_config["market_data_binding_signature"]),
                workspace_id=workspace_id,
                unit_id=copied_unit.id,
                intent_id=str(bound.data_config["market_data_binding_intent_id"]),
            )

        workspace = await db.get(Workspace, workspace_id)
        assert workspace is not None
        workspace.workspace_type = "trading"
        await db.commit()
        with pytest.raises(MarketDataResearchBindingError) as moved_to_trading:
            await service.resolve_runtime_binding(
                user_id=owner.id,
                binding_id=binding_id,
                binding_hash=str(bound.data_config["market_data_binding_hash"]),
                signature=str(bound.data_config["market_data_binding_signature"]),
                workspace_id=workspace_id,
                unit_id=trusted_unit_id,
                intent_id=str(bound.data_config["market_data_binding_intent_id"]),
            )

    assert copied.value.code == "MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED"
    assert moved_to_trading.value.code == "MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED"
    # Binding + trusted attachment query only; a copied unit is rejected before
    # the potentially expensive current-policy local replay.
    assert len(query_service.requests) == 2


@pytest.mark.asyncio
async def test_runtime_binding_rechecks_current_read_permission_and_source_policy(
    tmp_path: Path,
) -> None:
    """Revoked data entitlements and source access fail before the artifact is reused."""
    owner = await _user(username="binding-current-access-owner")
    query_service = _LocalOnlyQueryService()
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            query_service,
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        bound = await service.bind_request(
            user_id=owner.id,
            request=_request(),
            intent_id="ai-research-task-current-access-001",
        )
        workspace_id, unit_id = await _attach_research_unit(
            db=db,
            service=service,
            user=owner,
            bound=bound,
        )
        resolve_kwargs = {
            "user_id": owner.id,
            "binding_id": str(bound.data_config["market_data_binding_id"]),
            "binding_hash": str(bound.data_config["market_data_binding_hash"]),
            "signature": str(bound.data_config["market_data_binding_signature"]),
            "workspace_id": workspace_id,
            "unit_id": unit_id,
            "intent_id": str(bound.data_config["market_data_binding_intent_id"]),
        }

        await db.execute(
            delete(user_roles).where(
                user_roles.c.user_id == owner.id,
                user_roles.c.role == Role.USER.value,
            )
        )
        await db.commit()
        with pytest.raises(MarketDataResearchBindingError) as no_read_access:
            await service.resolve_runtime_binding(**resolve_kwargs)
        assert no_read_access.value.code == "MARKET_DATA_BINDING_RUNTIME_READ_ACCESS_DENIED"

        await db.execute(user_roles.insert().values(user_id=owner.id, role=Role.USER.value))
        await db.commit()
        query_service.execution_error = MarketDataAuthorizationError("SOURCE_LICENSE_DENIED")
        with pytest.raises(MarketDataResearchBindingError) as no_source_access:
            await service.resolve_runtime_binding(**resolve_kwargs)

    assert no_source_access.value.code == "MARKET_DATA_BINDING_RUNTIME_SOURCE_POLICY_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_runtime_binding_rejects_changed_current_source_evidence_and_revocation(
    tmp_path: Path,
) -> None:
    """A permitted substitute datum and an append-only revocation both fail closed."""
    owner = await _user(username="binding-evidence-owner")
    query_service = _LocalOnlyQueryService()
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            query_service,
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        bound = await service.bind_request(
            user_id=owner.id,
            request=_request(),
            intent_id="ai-research-task-evidence-001",
        )
        workspace_id, unit_id = await _attach_research_unit(
            db=db,
            service=service,
            user=owner,
            bound=bound,
        )
        resolve_kwargs = {
            "user_id": owner.id,
            "binding_id": str(bound.data_config["market_data_binding_id"]),
            "binding_hash": str(bound.data_config["market_data_binding_hash"]),
            "signature": str(bound.data_config["market_data_binding_signature"]),
            "workspace_id": workspace_id,
            "unit_id": unit_id,
            "intent_id": str(bound.data_config["market_data_binding_intent_id"]),
        }

        query_service.close_adjustment = 0.5
        with pytest.raises(MarketDataResearchBindingError) as changed_evidence:
            await service.resolve_runtime_binding(**resolve_kwargs)
        assert changed_evidence.value.code == "MARKET_DATA_BINDING_RUNTIME_SOURCE_EVIDENCE_MISMATCH"

        query_service.close_adjustment = 0.0
        await service.revoke_runtime_binding(
            binding_id=resolve_kwargs["binding_id"],
            reason_code="OPERATOR_EMERGENCY_REVOKE",
            actor_user_id=owner.id,
        )
        revocation = await db.scalar(
            select(MdResearchDataBindingRevocation).where(
                MdResearchDataBindingRevocation.binding_id == resolve_kwargs["binding_id"]
            )
        )
        assert revocation is not None
        assert revocation.status == "REVOKED"
        revocation.status = "INVALID"
        with pytest.raises(ImmutableMarketDataRecordError):
            await db.commit()
        await db.rollback()

        with pytest.raises(MarketDataResearchBindingError) as revoked:
            await service.resolve_runtime_binding(**resolve_kwargs)

    assert revoked.value.code == "MARKET_DATA_BINDING_REVOKED"


@pytest.mark.asyncio
async def test_runtime_binding_reloads_after_revocation_commits_during_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A revocation committed at the replay fence cannot reuse an old snapshot.

    The shared in-memory SQLite test engine cannot hold an independent writer
    transaction while the resolver owns its read snapshot. The execute hook
    therefore records the revocation request during the long replay, and the
    snapshot-end wrapper commits it through a separate session immediately
    after the old snapshot is discarded. This models the MySQL interleaving
    where the operator transaction commits before the fresh current read.
    """
    owner = await _user(username="binding-replay-revocation-owner")
    query_service = _LocalOnlyQueryService()
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            query_service,
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        bound = await service.bind_request(
            user_id=owner.id,
            request=_request(),
            intent_id="ai-research-task-replay-revocation-001",
        )
        workspace_id, unit_id = await _attach_research_unit(
            db=db,
            service=service,
            user=owner,
            bound=bound,
        )
        resolve_kwargs = {
            "user_id": owner.id,
            "binding_id": str(bound.data_config["market_data_binding_id"]),
            "binding_hash": str(bound.data_config["market_data_binding_hash"]),
            "signature": str(bound.data_config["market_data_binding_signature"]),
            "workspace_id": workspace_id,
            "unit_id": unit_id,
            "intent_id": str(bound.data_config["market_data_binding_intent_id"]),
        }
        replay_requested_revocation = False
        revocation_committed = False

        async def request_revocation(_request: MarketDataQueryRequest) -> None:
            nonlocal replay_requested_revocation
            replay_requested_revocation = True

        query_service.on_execute = request_revocation
        request_count_before_resolve = len(query_service.requests)
        original_end_snapshot = service._end_runtime_read_snapshot

        async def end_snapshot_then_commit_revocation() -> None:
            nonlocal revocation_committed
            await original_end_snapshot()
            if not replay_requested_revocation or revocation_committed:
                return
            async with async_session_maker() as revoker_db:
                revoker = MarketDataResearchBindingService(
                    revoker_db,
                    _LocalOnlyQueryService(),
                    _ContractResolver(),
                    MarketDataAccessAuthorizer(revoker_db, clock=lambda: NOW),
                    tmp_path,
                    binding_signing_key=SIGNING_KEY,
                    clock=lambda: NOW,
                )
                await revoker.revoke_runtime_binding(
                    binding_id=resolve_kwargs["binding_id"],
                    reason_code="OPERATOR_REVOKED_DURING_REPLAY",
                    actor_user_id=owner.id,
                )
            revocation_committed = True

        monkeypatch.setattr(
            service,
            "_end_runtime_read_snapshot",
            end_snapshot_then_commit_revocation,
        )
        with pytest.raises(MarketDataResearchBindingError) as revoked:
            await service.resolve_runtime_binding(**resolve_kwargs)

    assert replay_requested_revocation
    assert revocation_committed
    assert revoked.value.code == "MARKET_DATA_BINDING_REVOKED"
    # The refreshed consumer check rejects before a second strict replay can
    # expose the artifact. The first new request is the long replay hook.
    assert len(query_service.requests) == request_count_before_resolve + 1


@pytest.mark.asyncio
async def test_runtime_binding_final_fence_rechecks_sealed_source_registries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A registry disabled after fresh replay cannot authorize its sealed bytes."""
    owner = await _user(username="binding-final-source-fence-owner")
    query_service = _LocalOnlyQueryService()
    async with async_session_maker() as db:
        service = MarketDataResearchBindingService(
            db,
            query_service,
            _ContractResolver(),
            MarketDataAccessAuthorizer(db, clock=lambda: NOW),
            tmp_path,
            binding_signing_key=SIGNING_KEY,
            clock=lambda: NOW,
        )
        bound = await service.bind_request(
            user_id=owner.id,
            request=_request(),
            intent_id="ai-research-task-final-source-fence-001",
        )
        workspace_id, unit_id = await _attach_research_unit(
            db=db,
            service=service,
            user=owner,
            bound=bound,
        )
        resolve_kwargs = {
            "user_id": owner.id,
            "binding_id": str(bound.data_config["market_data_binding_id"]),
            "binding_hash": str(bound.data_config["market_data_binding_hash"]),
            "signature": str(bound.data_config["market_data_binding_signature"]),
            "workspace_id": workspace_id,
            "unit_id": unit_id,
            "intent_id": str(bound.data_config["market_data_binding_intent_id"]),
        }
        request_count_before_resolve = len(query_service.requests)
        original_end_snapshot = service._end_runtime_read_snapshot
        snapshot_restarts = 0
        registry_disabled = False

        async def end_fresh_replay_then_disable_registry() -> None:
            nonlocal registry_disabled, snapshot_restarts
            await original_end_snapshot()
            snapshot_restarts += 1
            if snapshot_restarts != 2:
                return
            async with async_session_maker() as registry_db:
                registry = await registry_db.get(AssetDataSourceRegistry, _SEALED_SOURCE_ID)
                assert registry is not None
                registry.enabled = False
                await registry_db.commit()
            registry_disabled = True

        monkeypatch.setattr(
            service,
            "_end_runtime_read_snapshot",
            end_fresh_replay_then_disable_registry,
        )
        runtime = None
        with pytest.raises(MarketDataResearchBindingError) as denied:
            runtime = await service.resolve_runtime_binding(**resolve_kwargs)

    assert snapshot_restarts == 2
    assert registry_disabled
    assert runtime is None
    assert denied.value.code == "MARKET_DATA_BINDING_RUNTIME_SOURCE_POLICY_ACCESS_DENIED"
    # The fresh replay completed; the final locking registry fence, rather
    # than stale source-policy evidence, denied the artifact materialization.
    assert len(query_service.requests) == request_count_before_resolve + 2


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
        intent_id = str(bound.data_config["market_data_binding_intent_id"])
        workspace_id, unit_id = await _attach_research_unit(
            db=db,
            service=service,
            user=user,
            bound=bound,
        )
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
                workspace_id=workspace_id,
                unit_id=unit_id,
                intent_id=intent_id,
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
