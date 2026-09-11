# ruff: noqa: E402
"""Run an opt-in, disposable AkShare acceptance probe for Iteration 197.

The command is deliberately a narrow non-production harness.  It does not use
``DATABASE_URL``, does not alter application configuration or credentials, and
never talks to AkShare unless ``--live`` is supplied.  A live run creates a
fresh SQLite file, seeds only the synthetic control-plane prerequisites needed
for one exact reviewed B1 family (``--family stock-liquidity`` by default;
``fund-liquidity``, ``fund-nav`` and ``fx-range`` select the other reviewed
routes), exercises the real ``MarketDataQueryService`` and AkShare adapter,
commits that isolated receipt, then verifies an independent ``local_only``
re-read before deleting the file.

Run from ``src/backend`` with the repository-required Conda interpreter:

    /Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
        python scripts/accept_iteration197_akshare_stock_liquidity.py

The default output is a safe ``NOT_RUN`` result and makes no network or
database call.  A live confirmation is explicit:

    /Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
        python scripts/accept_iteration197_akshare_stock_liquidity.py --live \
        --family fund-liquidity --trading-date 2026-09-08

``--database-path`` is optional for operators that need to choose the temporary
file location.  It must name a non-existent ``.db``, ``.sqlite`` or
``.sqlite3`` file under an existing, non-symlink directory.  The harness owns
and deletes that file on every terminal path; it never accepts a database URL
or an existing application database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Permit direct ``python scripts/...`` execution without relying on a caller's
# PYTHONPATH.  This script intentionally does not import the process-global
# database session factory, so an application's configured database can never
# become this harness's target.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401  # Register all mapped tables before create_all.
from app.db.database import Base
from app.models.asset_research import AssetDataSourceRegistry
from app.models.market_data_platform import MdObservationRevision, MdSourceSnapshot
from app.models.permission import Role, user_roles
from app.models.user import User
from app.schemas.asset_research import InstrumentIdentity
from app.schemas.market_data_platform import MarketDataQueryRequest
from app.services.market_data.access import MarketDataAccessAuthorizer, MarketDataQueryAccess
from app.services.market_data.akshare_provider import AkShareMarketDataProvider
from app.services.market_data.bootstrap import (
    CanonicalStorageSpec,
    MarketDataBootstrapSpec,
    MarketDataPlatformBootstrapper,
)
from app.services.market_data.calendar_importer import MANIFEST_VERSION, MarketDataCalendarImporter
from app.services.market_data.catalog import DataCatalogResolver
from app.services.market_data.identity import MarketDataIdentityResolver
from app.services.market_data.master_data import MarketDataIdentityWriter
from app.services.market_data.providers import MarketDataProviderRequest, ProviderFetchResult
from app.services.market_data.query_resolution import MarketDataQueryResolver
from app.services.market_data.query_service import MarketDataQueryExecution, MarketDataQueryService
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
    MarketDataSourcePolicyRegistry,
)
from app.services.market_data.store import MarketDataStore

UTC = timezone.utc
FAMILY_CONTRACT_VERSION = "market-data-family-v1"
DEFAULT_TRADING_DATE = date(2024, 1, 2)
_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_SAFE_WARNING_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_DATABASE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})


@dataclass(frozen=True, slots=True)
class _FamilyProfile:
    """One reviewed B1 family probe: identity, request axes, and route mirror.

    Every field mirrors the production dataset contract and the AkShare route
    registry.  The harness never invents a second semantics for a family that
    production already pinned, so a probe exercises exactly the reviewed pair.
    """

    key: str
    family_id: str
    dataset_code: str
    data_kind: str
    required_fields: tuple[str, ...]
    route_id: str
    source_policy_id: str
    asset_type: str
    identity_level: str
    identity_currency: str
    canonical_id: str
    display_symbol: str
    venue: str
    identifier_type: str
    identifier_value: str
    product_type: str
    identity_details: tuple[tuple[str, str], ...]
    registry_asset_types: tuple[str, ...]
    route_asset_types: frozenset[str]
    route_markets: frozenset[str]
    route_adjustments: frozenset[str]
    route_price_bases: frozenset[str]
    route_currencies: frozenset[str | None]
    route_units: frozenset[str | None]
    route_product_types: frozenset[str] | None
    route_fund_identity_kinds: frozenset[str] | None
    request_adjustment: str
    request_price_basis: str
    # ``None`` omits the axis from the request exactly like the reviewed
    # public contract (fx.range declares no currency/unit axis).
    request_currency: str | None
    request_unit: str | None


_PROFILES: dict[str, _FamilyProfile] = {
    profile.key: profile
    for profile in (
        _FamilyProfile(
            key="stock-liquidity",
            family_id="stock.liquidity",
            dataset_code="market.liquidity",
            data_kind="reference_series",
            required_fields=("volume", "turnover", "turnover_rate"),
            route_id="akshare-stock-liquidity-primary-v1",
            source_policy_id="market-default-v1",
            asset_type="stock",
            identity_level="ASSET",
            identity_currency="CNY",
            canonical_id="instrument:stock:CN-SSE:600000",
            display_symbol="600000",
            venue="CN-SSE",
            identifier_type="EXCHANGE_SYMBOL",
            identifier_value="600000.SH",
            product_type="EQUITY",
            identity_details=(("kind", "STOCK"), ("exchange_symbol", "600000.SH")),
            registry_asset_types=("stock",),
            route_asset_types=frozenset({"stock"}),
            route_markets=frozenset({"CN-SSE"}),
            route_adjustments=frozenset({"unadjusted"}),
            route_price_bases=frozenset({"close"}),
            route_currencies=frozenset({"CNY"}),
            route_units=frozenset({"share"}),
            route_product_types=None,
            route_fund_identity_kinds=None,
            request_adjustment="unadjusted",
            request_price_basis="close",
            request_currency="CNY",
            request_unit="share",
        ),
        _FamilyProfile(
            key="fund-liquidity",
            family_id="fund.liquidity",
            dataset_code="market.liquidity",
            data_kind="reference_series",
            required_fields=("volume", "turnover"),
            route_id="akshare-fund-liquidity-primary-v1",
            source_policy_id="market-default-v1",
            asset_type="fund",
            identity_level="PRODUCT",
            identity_currency="CNY",
            canonical_id="instrument:fund:CN-SSE:510300",
            display_symbol="510300",
            venue="CN-SSE",
            identifier_type="EXCHANGE_SYMBOL",
            identifier_value="510300.SH",
            product_type="ETF",
            identity_details=(
                ("kind", "FUND"),
                ("fund_identity_kind", "LISTING"),
                ("fund_id", "iteration197-harness:etf:510300"),
                ("share_class_id", "iteration197-harness:etf:510300:listing"),
            ),
            registry_asset_types=("fund",),
            route_asset_types=frozenset({"fund"}),
            route_markets=frozenset({"CN-SSE", "CN-SZSE"}),
            route_adjustments=frozenset({"unadjusted"}),
            route_price_bases=frozenset({"close"}),
            route_currencies=frozenset({"CNY"}),
            route_units=frozenset({"share"}),
            route_product_types=None,
            route_fund_identity_kinds=None,
            request_adjustment="unadjusted",
            request_price_basis="close",
            request_currency="CNY",
            request_unit="share",
        ),
        _FamilyProfile(
            key="fund-nav",
            family_id="fund.nav",
            dataset_code="market.fund_nav",
            data_kind="reference_series",
            required_fields=("nav", "cumulative_nav", "daily_growth_rate"),
            route_id="akshare-fund-nav-primary-v1",
            source_policy_id="market-default-v1",
            asset_type="fund",
            identity_level="PRODUCT",
            identity_currency="CNY",
            canonical_id="instrument:fund:CN-SSE:510300",
            display_symbol="510300",
            venue="CN-SSE",
            identifier_type="EXCHANGE_SYMBOL",
            identifier_value="510300.SH",
            product_type="ETF",
            # The frozen identity must declare both reviewed markers before
            # the route authorizes any provider I/O; LOF/REIT/share-class
            # identities are rejected by the adapter itself.
            identity_details=(
                ("kind", "FUND"),
                ("fund_identity_kind", "LISTING"),
                ("fund_id", "iteration197-harness:etf:510300"),
                ("share_class_id", "iteration197-harness:etf:510300:listing"),
            ),
            registry_asset_types=("fund",),
            route_asset_types=frozenset({"fund"}),
            route_markets=frozenset({"CN-SSE", "CN-SZSE"}),
            route_adjustments=frozenset({"source_reported"}),
            route_price_bases=frozenset({"nav"}),
            route_currencies=frozenset({"CNY"}),
            route_units=frozenset({"fund_share"}),
            route_product_types=frozenset({"ETF"}),
            route_fund_identity_kinds=frozenset({"LISTING"}),
            request_adjustment="source_reported",
            request_price_basis="nav",
            request_currency="CNY",
            request_unit="fund_share",
        ),
        _FamilyProfile(
            key="fx-range",
            family_id="fx.range",
            dataset_code="market.bars",
            data_kind="bars",
            required_fields=("open", "high", "low", "close"),
            route_id="akshare-fx-range-primary-v1",
            source_policy_id="market-default-v1",
            asset_type="fx",
            identity_level="PRODUCT",
            identity_currency="CNH",
            canonical_id="instrument:fx:OTC:USDCNH",
            display_symbol="USDCNH",
            venue="OTC",
            identifier_type="PROVIDER_SYMBOL",
            identifier_value="USDCNH",
            product_type="FX_PAIR",
            identity_details=(
                ("kind", "FX"),
                ("base_currency", "USD"),
                ("quote_currency", "CNH"),
                ("settlement_type", "SPOT"),
                ("settlement_currency", "CNH"),
                ("calendar_id", "OTC"),
                ("price_convention", "USD_PER_CNH"),
            ),
            registry_asset_types=("fx",),
            route_asset_types=frozenset({"fx"}),
            route_markets=frozenset({"OTC", "CN-OTC"}),
            route_adjustments=frozenset({"unadjusted"}),
            route_price_bases=frozenset({"close"}),
            # fx.range declares no currency/unit axis; the route accepts the
            # undeclared (``None``) axis value exactly like the public contract.
            route_currencies=frozenset({None}),
            route_units=frozenset({None}),
            route_product_types=None,
            route_fund_identity_kinds=None,
            request_adjustment="unadjusted",
            request_price_basis="close",
            request_currency=None,
            request_unit=None,
        ),
    )
}


class _Provider(Protocol):
    """The small provider seam used for no-network harness tests."""

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        """Fetch an exact provider request."""


class HarnessError(RuntimeError):
    """Stable, non-sensitive harness failure."""

    def __init__(self, code: str, *, stage: str) -> None:
        self.code = code if _SAFE_CODE.fullmatch(code) else "AKSHARE_ACCEPTANCE_HARNESS_FAILED"
        self.stage = stage
        super().__init__(self.code)


@dataclass(slots=True)
class _DatabaseTarget:
    """A file owned by this invocation and safe to remove during cleanup."""

    path: Path
    kind: str
    _device: int
    _inode: int

    @classmethod
    def allocate(cls, requested_path: str | None) -> _DatabaseTarget:
        if requested_path is None:
            directory = Path(tempfile.mkdtemp(prefix="iteration197-akshare-"))
            path = directory / "market_data.sqlite3"
            kind = "temporary"
        else:
            path = _validate_requested_database_path(requested_path)
            kind = "caller_designated_temporary"
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise HarnessError("HARNESS_DATABASE_NOT_FRESH", stage="database_target") from exc
        except OSError as exc:
            raise HarnessError("HARNESS_DATABASE_TARGET_UNSAFE", stage="database_target") from exc
        else:
            os.close(descriptor)
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise HarnessError("HARNESS_DATABASE_TARGET_UNSAFE", stage="database_target") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise HarnessError("HARNESS_DATABASE_TARGET_UNSAFE", stage="database_target")
        return cls(path=path, kind=kind, _device=metadata.st_dev, _inode=metadata.st_ino)

    def cleanup(self) -> bool:
        """Delete only the exact file this invocation created, plus SQLite sidecars."""
        removed = True
        try:
            metadata = self.path.lstat()
            same_file = (
                stat.S_ISREG(metadata.st_mode)
                and metadata.st_dev == self._device
                and metadata.st_ino == self._inode
            )
            if not same_file:
                return False
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            removed = False

        # Sidecars can only be associated with the fresh path this process
        # created.  Do not follow or remove a non-regular replacement.
        for suffix in ("-journal", "-shm", "-wal"):
            sidecar = Path(f"{self.path}{suffix}")
            try:
                metadata = sidecar.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                removed = False
                continue
            if not stat.S_ISREG(metadata.st_mode):
                removed = False
                continue
            try:
                sidecar.unlink()
            except OSError:
                removed = False

        if self.kind == "temporary":
            try:
                self.path.parent.rmdir()
            except FileNotFoundError:
                pass
            except OSError:
                removed = False
        return removed


class _RecordingProvider:
    """Count provider attempts and safe result cardinalities without emitting source content."""

    def __init__(self, delegate: _Provider) -> None:
        self._delegate = delegate
        self.attempt_count = 0
        self._result_count = 0
        self._response_row_count = 0
        self._response_row_count_known = True
        self._normalized_observation_count = 0

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        self.attempt_count += 1
        result = await self._delegate.fetch(request)
        if isinstance(result, ProviderFetchResult):
            self._result_count += 1
            self._normalized_observation_count += len(result.observations)
            response_rows = result.raw_payload.get("response_rows")
            if isinstance(response_rows, list):
                self._response_row_count += len(response_rows)
            else:
                self._response_row_count_known = False
        return result

    def result_summary(self) -> dict[str, int | None]:
        """Return only aggregate counts needed to diagnose an empty receipt."""
        return {
            "result_count": self._result_count,
            "response_row_count": (
                self._response_row_count if self._response_row_count_known else None
            ),
            "normalized_observation_count": self._normalized_observation_count,
        }


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly permit one real AkShare request through the local-first service.",
    )
    parser.add_argument(
        "--family",
        dest="family",
        choices=sorted(_PROFILES),
        default="stock-liquidity",
        help=(
            "Which reviewed B1 family probe to run (default: stock-liquidity). "
            "Each probe uses its own exact route, identity, and calendar seed."
        ),
    )
    parser.add_argument(
        "--database-path",
        metavar="PATH",
        help=(
            "A new SQLite .db/.sqlite/.sqlite3 file to create and delete; existing files, "
            "URLs, symlink paths, and missing parents are rejected."
        ),
    )
    parser.add_argument(
        "--trading-date",
        metavar="YYYY-MM-DD",
        default=DEFAULT_TRADING_DATE.isoformat(),
        help=(
            "One Monday-Friday historical date for the exact single-day probe window "
            f"(default: {DEFAULT_TRADING_DATE.isoformat()})."
        ),
    )
    return parser.parse_args(argv)


def _validate_requested_database_path(value: str) -> Path:
    """Reject anything that might name an existing or indirect application database."""
    if not isinstance(value, str) or not value.strip() or "://" in value:
        raise HarnessError("HARNESS_DATABASE_TARGET_UNSAFE", stage="database_target")
    raw_path = Path(value).expanduser()
    if not raw_path.is_absolute():
        raw_path = Path.cwd() / raw_path
    if raw_path.name in {"", ".", ".."} or raw_path.suffix.lower() not in _DATABASE_SUFFIXES:
        raise HarnessError("HARNESS_DATABASE_TARGET_UNSAFE", stage="database_target")
    # Refuse every symlink component before resolving so a caller cannot use a
    # friendly path that resolves into an application data directory.
    current = Path(raw_path.anchor)
    for component in raw_path.parts[1:-1]:
        current = current / component
        if current.is_symlink():
            raise HarnessError("HARNESS_DATABASE_TARGET_UNSAFE", stage="database_target")
    if raw_path.is_symlink() or raw_path.exists():
        raise HarnessError("HARNESS_DATABASE_NOT_FRESH", stage="database_target")
    parent = raw_path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise HarnessError("HARNESS_DATABASE_TARGET_UNSAFE", stage="database_target")
    return raw_path


def _parse_trading_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise HarnessError("HARNESS_TRADING_DATE_INVALID", stage="arguments") from exc
    if parsed.weekday() >= 5:
        raise HarnessError("HARNESS_TRADING_DATE_NOT_WEEKDAY", stage="arguments")
    return parsed


def _database_url(path: Path) -> str:
    """Render an isolated SQLite URL without reading or printing environment URLs."""
    return str(URL.create(drivername="sqlite+aiosqlite", database=str(path)))


def _window_for(trading_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(trading_date, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _request_for(
    profile: _FamilyProfile, *, start: datetime, end: datetime, mode: str
) -> MarketDataQueryRequest:
    """Build the public B1 contract; no generic/unbound request is permitted."""
    payload: dict[str, object] = {
        "identity": {"canonical_id": profile.canonical_id},
        "family_id": profile.family_id,
        "family_contract_version": FAMILY_CONTRACT_VERSION,
        "dataset_code": profile.dataset_code,
        "data_kind": profile.data_kind,
        "frequency": "1d",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "required_fields": list(profile.required_fields),
        "adjustment": profile.request_adjustment,
        "price_basis": profile.request_price_basis,
        "source_policy_id": profile.source_policy_id,
        "mode": mode,
        "purpose": "display",
    }
    # The reviewed semantic binding requires every axis to be supplied
    # explicitly (``model_fields_set``), including an undeclared ``None`` for
    # fx.range, so both keys always enter the validated payload.
    payload["currency"] = profile.request_currency
    payload["unit"] = profile.request_unit
    return MarketDataQueryRequest.model_validate(payload)


def _source_policies(
    provider: _Provider, profile: _FamilyProfile
) -> MarketDataSourcePolicyRegistry:
    """Mirror only the reviewed production route for the selected family."""
    route = MarketDataProviderRoute(
        route_id=profile.route_id,
        request_provider="akshare",
        expected_result_provider_ids=frozenset({"akshare"}),
        asset_types=profile.route_asset_types,
        data_kinds=frozenset({profile.data_kind}),
        frequencies=frozenset({"1d"}),
        markets=profile.route_markets,
        adjustments=profile.route_adjustments,
        price_bases=profile.route_price_bases,
        currencies=profile.route_currencies,
        units=profile.route_units,
        family_id=profile.family_id,
        family_contract_version=FAMILY_CONTRACT_VERSION,
        product_types=profile.route_product_types,
        fund_identity_kinds=profile.route_fund_identity_kinds,
        adapter=provider,
    )
    return MarketDataSourcePolicyRegistry(
        (
            MarketDataSourcePolicy(
                policy_id=profile.source_policy_id,
                allowed_purposes=frozenset({"display"}),
                routes=(route,),
            ),
        )
    )


async def _seed_prerequisites(
    session: AsyncSession,
    *,
    database_url: str,
    profile: _FamilyProfile,
    start: datetime,
    end: datetime,
) -> str:
    """Seed synthetic, disposable approvals needed by exactly one public query."""
    spec = MarketDataBootstrapSpec(
        storage=CanonicalStorageSpec.from_database_url(database_url),
    )
    await MarketDataPlatformBootstrapper(session).bootstrap(spec)

    user = User(
        username="iteration197-akshare-harness",
        email="iteration197-akshare-harness@example.test",
        hashed_password="not-used-disposable-harness",
        is_active=True,
    )
    session.add(user)
    session.add(
        AssetDataSourceRegistry(
            source_id="akshare",
            asset_types=list(profile.registry_asset_types),
            jurisdictions=["CN"] if profile.asset_type != "fx" else ["GLOBAL"],
            license_status="APPROVED",
            allowed_uses=["DISPLAY"],
            redistribution_policy="NO_REDISTRIBUTION",
            derived_data_policy="ALLOWED",
            retention_policy="iteration197-harness-only",
            effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            enabled=True,
            updated_at=datetime.now(UTC),
        )
    )
    await session.flush()
    await session.execute(user_roles.insert().values(user_id=user.id, role=Role.USER.value))
    user_id = str(user.id)
    await session.commit()

    identity = InstrumentIdentity.model_validate(
        {
            "asset_type": profile.asset_type,
            "identity_level": profile.identity_level,
            "canonical_id": profile.canonical_id,
            "display_symbol": profile.display_symbol,
            "name": "Iteration 197 disposable acceptance instrument",
            "venue": profile.venue,
            "currency": profile.identity_currency,
            "timezone": "Asia/Shanghai" if profile.asset_type != "fx" else "UTC",
            "identifier_type": profile.identifier_type,
            "identifier_value": profile.identifier_value,
            "product_type": profile.product_type,
            "metadata_version": "iteration197-harness-v1",
            "details": dict(profile.identity_details),
        }
    )
    identity_writer = MarketDataIdentityWriter(session)
    await identity_writer.persist_identity(identity, valid_from=start - timedelta(days=365))
    await session.commit()
    await identity_writer.publish_staged()

    calendar_payload = {
        "manifest_version": MANIFEST_VERSION,
        "approval_reference": "ITER197-HARNESS-NONPRODUCTION",
        "evidence_uri": "file:///iteration197-harness/non-production-calendar.json",
        "evidence_content_hash": "0" * 64,
        "source_registry_id": "akshare",
        # The store resolves the calendar by the request's market value, so
        # the synthetic grid reuses the frozen venue of this probe identity.
        "calendar_code": profile.venue,
        "calendar_version": f"harness-{start.date().isoformat()}",
        "timezone_name": "Asia/Shanghai" if profile.asset_type != "fx" else "UTC",
        "coverage_start_at": start.isoformat(),
        "coverage_end_at": end.isoformat(),
        "events": [
            {
                "trading_date": start.date().isoformat(),
                "event_type": "session",
                "session_code": (
                    "reference-series-daily-close"
                    if profile.data_kind == "reference_series"
                    else "daily-bar-close"
                ),
                "is_trading_day": True,
                "event_start": start.isoformat(),
                # ``event_end`` stays strictly below the half-open coverage
                # endpoint while still representing the one daily event.
                "event_end": (end - timedelta(microseconds=1)).isoformat(),
                "coverage": {"data_kind": profile.data_kind, "frequency": "1d"},
                "event_payload": {"provider_observation_key": "daily-close"},
            }
        ],
    }
    await MarketDataCalendarImporter(session).import_payload(
        payload=calendar_payload, dry_run=False
    )
    await session.commit()
    return user_id


async def _access(session: AsyncSession, *, user_id: str) -> MarketDataQueryAccess:
    user = await session.get(User, user_id)
    if user is None:
        raise HarnessError("HARNESS_PREREQUISITES_UNAVAILABLE", stage="authorization")
    authorizer = MarketDataAccessAuthorizer(session)
    principal = await authorizer.principal_for_user(user)
    return MarketDataQueryAccess(principal=principal, authorizer=authorizer)


def _service(
    session: AsyncSession, provider: _Provider, profile: _FamilyProfile
) -> MarketDataQueryService:
    """Compose the production resolver/store/query service against only this DB."""
    return MarketDataQueryService(
        resolver=MarketDataQueryResolver(
            catalog=DataCatalogResolver(session),
            identities=MarketDataIdentityResolver(session),
        ),
        store=MarketDataStore(session),
        source_policies=_source_policies(provider, profile),
        allow_online_fetch=True,
        # No pagination is exercised, but an explicit local test key prevents
        # this harness from reading application configuration if a future
        # query path adds a cursor.
        cursor_signing_key="iteration197-disposable-local-cursor-key-0000000000000000000000000001",
    )


def _execution_summary(execution: MarketDataQueryExecution) -> dict[str, object]:
    """Keep useful proof counts/codes while excluding source rows and raw receipts."""
    return {
        "coverage_status": execution.coverage.status.value,
        "observation_count": len(execution.observations),
        "persisted_fetch_count": len(execution.fetches),
        "passing_observation_count": sum(
            fetch.passing_observation_count for fetch in execution.fetches
        ),
        "failed_observation_count": sum(
            fetch.failed_observation_count for fetch in execution.fetches
        ),
        "warning_codes": sorted(
            warning.code
            for warning in execution.warnings
            if _SAFE_WARNING_CODE.fullmatch(warning.code)
        ),
    }


def _failure_code(first: MarketDataQueryExecution, *, provider_attempts: int) -> str:
    """Derive one stable, payload-free failure code from a failed first read."""
    warning_codes = [
        warning.code for warning in first.warnings if _SAFE_WARNING_CODE.fullmatch(warning.code)
    ]
    if warning_codes:
        return sorted(warning_codes)[0]
    if provider_attempts == 0:
        return "AKSHARE_PROVIDER_NOT_ATTEMPTED"
    if not first.fetches:
        return "AKSHARE_RECEIPT_NOT_PERSISTED"
    if not any(fetch.observation_revision_ids for fetch in first.fetches):
        return "AKSHARE_ZERO_USABLE_OBSERVATIONS"
    return "AKSHARE_LOCAL_FIRST_INCOMPLETE"


def _live_provider_from_environment() -> _Provider:
    """Construct the same isolated AkShare runner adapter used by API requests."""
    return AkShareMarketDataProvider.from_environment()


async def _run_live(
    *,
    database_path: Path,
    trading_date: date,
    profile: _FamilyProfile,
    provider_factory: Callable[[], _Provider] | None = None,
) -> dict[str, object]:
    """Run the full durable live chain; tests pass a fake factory, CLI uses AkShare."""
    database_url = _database_url(database_path)
    engine: AsyncEngine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    start, end = _window_for(trading_date)
    factory = _live_provider_from_environment if provider_factory is None else provider_factory
    provider = _RecordingProvider(factory())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as seed_session:
            user_id = await _seed_prerequisites(
                seed_session,
                database_url=database_url,
                profile=profile,
                start=start,
                end=end,
            )

        request = _request_for(profile, start=start, end=end, mode="local_first")
        async with session_factory() as first_session:
            first = await _service(first_session, provider, profile).execute(
                request,
                access=await _access(first_session, user_id=user_id),
            )
            await first_session.commit()

        first_summary = _execution_summary(first)
        base_summary: dict[str, object] = {
            "family_id": profile.family_id,
            "route_id": profile.route_id,
            "data_kind": profile.data_kind,
            "frequency": "1d",
            "window_date": trading_date.isoformat(),
            "provider_fetch_attempt_count": provider.attempt_count,
            "provider_result": provider.result_summary(),
            "first_local_first": first_summary,
            "raw_payload_emitted": False,
            "credential_writes": False,
        }
        if (
            first.coverage.status.value != "complete"
            or len(first.fetches) != 1
            or len(first.observations) < 1
        ):
            return {
                "status": "failed",
                "code": _failure_code(first, provider_attempts=provider.attempt_count),
                "stage": "live_fetch_or_persistence",
                **base_summary,
            }

        local_only_request = _request_for(profile, start=start, end=end, mode="local_only")
        async with session_factory() as reread_session:
            reread_provider = _RecordingProvider(_UnexpectedProvider())
            reread = await _service(reread_session, reread_provider, profile).execute(
                local_only_request,
                access=await _access(reread_session, user_id=user_id),
            )
            snapshot_count = await reread_session.scalar(
                select(func.count()).select_from(MdSourceSnapshot)
            )
            revision_count = await reread_session.scalar(
                select(func.count()).select_from(MdObservationRevision)
            )

        reread_summary = _execution_summary(reread)
        reread_summary["provider_fetch_attempt_count"] = reread_provider.attempt_count
        base_summary.update(
            {
                "independent_local_only_reread": reread_summary,
                "persistence": {
                    "source_snapshot_count": int(snapshot_count or 0),
                    "observation_revision_count": int(revision_count or 0),
                },
            }
        )
        if (
            reread.coverage.status.value != "complete"
            or reread.fetches
            or reread_provider.attempt_count != 0
            or len(reread.observations) < 1
        ):
            return {
                "status": "failed",
                "code": "AKSHARE_LOCAL_ONLY_REREAD_FAILED",
                "stage": "independent_local_only_reread",
                **base_summary,
            }
        return {"status": "pass", "code": "AKSHARE_LOCAL_FIRST_CHAIN_PASSED", **base_summary}
    finally:
        await engine.dispose()


class _UnexpectedProvider:
    """Turn an accidental local-only network path into a stable test failure."""

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        del request
        raise HarnessError("AKSHARE_LOCAL_ONLY_PROVIDER_CALLED", stage="local_only_reread")


def _not_run_summary() -> dict[str, object]:
    """The default process performs no network, schema, or filesystem action."""
    return {
        "status": "not_run",
        "code": "LIVE_CONFIRMATION_REQUIRED",
        "network_called": False,
        "database_created": False,
        "credential_writes": False,
        "raw_payload_emitted": False,
    }


def _emit(payload: dict[str, object]) -> None:
    """Emit exactly one structured, non-sensitive record to stdout."""
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    """Run the operator boundary without leaking exceptions, URLs, or payloads."""
    try:
        args = _arguments(argv)
        if not args.live:
            _emit(_not_run_summary())
            return 0
        trading_date = _parse_trading_date(args.trading_date)
        target = _DatabaseTarget.allocate(args.database_path)
    except HarnessError as exc:
        _emit(
            {
                "status": "failed",
                "code": exc.code,
                "stage": exc.stage,
                "credential_writes": False,
                "raw_payload_emitted": False,
            }
        )
        return 2

    payload: dict[str, object]
    exit_code = 1
    cleanup_ok = False
    try:
        payload = asyncio.run(
            _run_live(
                database_path=target.path,
                trading_date=trading_date,
                profile=_PROFILES[args.family],
            )
        )
        exit_code = 0 if payload.get("status") == "pass" else 1
    except HarnessError as exc:
        payload = {"status": "failed", "code": exc.code, "stage": exc.stage}
    except Exception:
        # Driver errors and third-party client exceptions can include paths,
        # request text, or URLs.  Keep this terminal output intentionally
        # opaque; source-specific stable failures return through warnings.
        payload = {
            "status": "failed",
            "code": "AKSHARE_ACCEPTANCE_HARNESS_FAILED",
            "stage": "harness_execution",
        }
    finally:
        cleanup_ok = target.cleanup()

    payload.update(
        {
            "database": {"kind": target.kind, "removed": cleanup_ok},
            "credential_writes": False,
            "raw_payload_emitted": False,
        }
    )
    if not cleanup_ok:
        payload["status"] = "failed"
        payload["code"] = "HARNESS_DATABASE_CLEANUP_FAILED"
        payload["stage"] = "cleanup"
        exit_code = 1
    _emit(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
