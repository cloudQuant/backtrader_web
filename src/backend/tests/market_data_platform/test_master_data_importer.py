"""Offline contracts for the operator-only Iteration 197 master-data importer."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

import pytest
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.asset_research import AssetInstrument
from app.models.market_data_platform import MdInstrumentLookupKey
from app.services.market_data.master_data_importer import (
    MASTER_DATA_MANIFEST_VERSION,
    MarketDataMasterDataImporter,
    MarketDataMasterDataImportError,
    MarketDataMasterDataManifest,
)


def _identity(asset_type: str, *, suffix: str = "v1", venue: str | None = "TEST-VENUE") -> dict:
    """Return one valid frozen identity DTO for each currently supported asset family."""
    common = {
        "canonical_id": f"instrument:{asset_type}:test:{suffix}",
        "display_symbol": f"{asset_type[:3].upper()}-{suffix}",
        "name": f"Test {asset_type} {suffix}",
        "venue": venue,
        "currency": "USD",
        "timezone": "UTC",
        "identifier_type": "TEST_IDENTIFIER",
        "identifier_value": f"{asset_type[:3].upper()}-{suffix}",
        "product_type": "TEST_PRODUCT",
        "metadata_version": "v1",
    }
    if asset_type == "stock":
        return {
            "asset_type": "stock",
            "identity_level": "ASSET",
            **common,
            "details": {"kind": "STOCK", "exchange_symbol": "TST"},
        }
    if asset_type == "bond":
        return {
            "asset_type": "bond",
            "identity_level": "PRODUCT",
            **common,
            "details": {
                "kind": "BOND",
                "bond_identity_kind": "LISTING",
                "issuer_id": "issuer-test",
            },
        }
    if asset_type == "fund":
        return {
            "asset_type": "fund",
            "identity_level": "PRODUCT",
            **common,
            "details": {
                "kind": "FUND",
                "fund_identity_kind": "LISTING",
                "fund_id": "fund-test",
                "share_class_id": "class-test",
            },
        }
    if asset_type == "futures":
        return {
            "asset_type": "futures",
            "identity_level": "PRODUCT",
            **common,
            "details": {
                "kind": "FUTURES",
                "product_code": "TST",
                "trading_calendar_id": "TEST-CALENDAR",
            },
        }
    if asset_type == "option":
        symbol = f"OPT-{suffix}"
        option_common = {**common, "display_symbol": symbol, "identifier_value": symbol}
        return {
            "asset_type": "option",
            "identity_level": "CONTRACT",
            **option_common,
            "details": {
                "kind": "OPTION",
                "option_contract_id": symbol,
                "exchange": venue,
                "underlying_instrument_id": "instrument:stock:test:underlying",
                "underlying_contract_id": "contract:test:underlying",
                "expiry_at": "2027-01-15T08:00:00Z",
                "last_trade_at": "2027-01-14T08:00:00Z",
                "strike": "3.5",
                "option_right": "CALL",
                "exercise_style": "EUROPEAN",
                "contract_multiplier": "100",
                "settlement_type": "CASH",
                "deliverable": "USD",
                "quote_unit": "USD",
                "tick_size": "0.01",
                "trading_calendar_id": "TEST-CALENDAR",
                "automatic_exercise_rule": "TEST-RULE",
                "position_limit_rule": "TEST-RULE",
                "margin_rule_version": "v1",
            },
        }
    if asset_type == "fx":
        return {
            "asset_type": "fx",
            "identity_level": "PRODUCT",
            **common,
            "details": {
                "kind": "FX",
                "base_currency": "EUR",
                "quote_currency": "USD",
                "settlement_type": "SPOT",
                "settlement_currency": "USD",
                "calendar_id": "TEST-CALENDAR",
                "price_convention": "EURUSD",
            },
        }
    if asset_type == "crypto":
        return {
            "asset_type": "crypto",
            "identity_level": "PRODUCT",
            **common,
            "details": {
                "kind": "CRYPTO_PRODUCT",
                "base_asset_id": "caip19:btc",
                "quote_asset_id": "caip19:usd",
                "market_type": "SPOT",
                "linear_or_inverse": "NOT_APPLICABLE",
            },
        }
    raise AssertionError(f"unsupported test asset type {asset_type!r}")


def _manifest(identities: Iterable[dict]) -> MarketDataMasterDataManifest:
    return MarketDataMasterDataManifest.model_validate(
        {
            "manifest_version": MASTER_DATA_MANIFEST_VERSION,
            "identities": list(identities),
        }
    )


def _digest(manifest: MarketDataMasterDataManifest) -> str:
    return hashlib.sha256(
        json.dumps(manifest.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    ).hexdigest()


@pytest.mark.asyncio
async def test_importer_validates_and_materializes_all_seven_asset_identity_dtos() -> None:
    """The strict manifest exercises every current asset family through the operator writer."""
    asset_types = ("stock", "futures", "bond", "fund", "option", "fx", "crypto")
    manifest = _manifest(_identity(asset_type) for asset_type in asset_types)

    async with async_session_maker() as session:
        result = await MarketDataMasterDataImporter(session).import_manifest(
            manifest,
            manifest_sha256=_digest(manifest),
        )
        await session.commit()
        key_count = await session.scalar(select(func.count()).select_from(MdInstrumentLookupKey))

    assert result.identity_count == 7
    assert result.created_count == 7
    assert result.reused_count == 0
    assert result.lookup_key_count == 7
    assert result.canonical_only_count == 0
    assert result.asset_type_counts == dict.fromkeys(sorted(asset_types), 1)
    assert key_count == 7


@pytest.mark.asyncio
async def test_importer_is_idempotent_only_for_an_exact_existing_identity_version() -> None:
    """A repeated reviewed manifest reuses its version and cannot create another identity row."""
    manifest = _manifest([_identity("stock")])

    async with async_session_maker() as session:
        importer = MarketDataMasterDataImporter(session)
        first = await importer.import_manifest(manifest, manifest_sha256=_digest(manifest))
        await session.commit()
        second = await importer.import_manifest(manifest, manifest_sha256=_digest(manifest))
        await session.commit()
        instruments = await session.scalar(select(func.count()).select_from(AssetInstrument))
        keys = await session.scalar(select(func.count()).select_from(MdInstrumentLookupKey))

    assert first.created_count == 1
    assert second.created_count == 0
    assert second.reused_count == 1
    assert instruments == 1
    assert keys == 1


@pytest.mark.asyncio
async def test_incremental_import_publishes_mixed_reused_and_pending_receipts_then_clears_them() -> (
    None
):
    """A long-lived importer can add a new identity after an idempotent re-import."""
    first_manifest = _manifest([_identity("stock", suffix="first")])
    second_manifest = _manifest(
        [_identity("stock", suffix="first"), _identity("futures", suffix="second")]
    )

    async with async_session_maker() as session:
        importer = MarketDataMasterDataImporter(session)
        await importer.import_manifest(first_manifest, manifest_sha256=_digest(first_manifest))
        await session.commit()
        await importer.publish_staged()
        assert importer.staged_publication_ids == ()

        result = await importer.import_manifest(
            second_manifest, manifest_sha256=_digest(second_manifest)
        )
        await session.commit()
        await importer.publish_staged()

        assert importer.staged_publication_ids == ()

    assert result.created_count == 1
    assert result.reused_count == 1


@pytest.mark.asyncio
async def test_importer_rejects_a_different_payload_reusing_an_existing_canonical_version() -> None:
    """A canonical/version tuple cannot be silently repointed by a later manifest."""
    initial = _manifest([_identity("stock")])
    replacement = _identity("stock")
    replacement["name"] = "Changed but same version"
    changed = _manifest([replacement])

    async with async_session_maker() as session:
        importer = MarketDataMasterDataImporter(session)
        await importer.import_manifest(initial, manifest_sha256=_digest(initial))
        await session.commit()
        with pytest.raises(MarketDataMasterDataImportError) as rejected:
            await importer.import_manifest(changed, manifest_sha256=_digest(changed))
        instruments = await session.scalar(select(func.count()).select_from(AssetInstrument))

    assert rejected.value.code == "MASTER_DATA_IMPORT_EXISTING_VERSION_CONFLICT"
    assert instruments == 1


@pytest.mark.asyncio
async def test_dry_run_executes_the_same_path_then_rolls_back_every_identity_and_key() -> None:
    """Dry-run materializes within the transaction but leaves no reusable state behind."""
    manifest = _manifest([_identity("stock"), _identity("futures")])

    async with async_session_maker() as session:
        result = await MarketDataMasterDataImporter(session).import_manifest(
            manifest,
            manifest_sha256=_digest(manifest),
        )
        pending_instruments = await session.scalar(
            select(func.count()).select_from(AssetInstrument)
        )
        pending_keys = await session.scalar(select(func.count()).select_from(MdInstrumentLookupKey))
        await session.rollback()
        persisted_instruments = await session.scalar(
            select(func.count()).select_from(AssetInstrument)
        )
        persisted_keys = await session.scalar(
            select(func.count()).select_from(MdInstrumentLookupKey)
        )

    assert result.created_count == 2
    assert pending_instruments == 2
    assert pending_keys == 2
    assert persisted_instruments == 0
    assert persisted_keys == 0


@pytest.mark.asyncio
async def test_importer_rolls_back_the_entire_batch_when_a_later_identity_conflicts() -> None:
    """An exact lookup-key collision cannot leave the preceding manifest entry committed."""
    first = _identity("stock", suffix="first")
    second = _identity("stock", suffix="second")
    second["display_symbol"] = first["display_symbol"]
    second["identifier_value"] = first["identifier_value"]
    manifest = _manifest([first, second])

    async with async_session_maker() as session:
        with pytest.raises(MarketDataMasterDataImportError) as rejected:
            await MarketDataMasterDataImporter(session).import_manifest(
                manifest,
                manifest_sha256=_digest(manifest),
            )
        instruments = await session.scalar(select(func.count()).select_from(AssetInstrument))
        keys = await session.scalar(select(func.count()).select_from(MdInstrumentLookupKey))

    assert rejected.value.code == "LOOKUP_KEY_ACTIVE_CONFLICT"
    assert instruments == 0
    assert keys == 0


@pytest.mark.asyncio
async def test_importer_allows_a_venue_less_identity_only_as_canonical_identity_without_key() -> (
    None
):
    """A no-venue identity remains canonical-ID-only and is never guessed into a triple key."""
    raw = _identity("fx", venue=None)
    raw["identity_level"] = "ASSET"
    raw["details"].pop("settlement_currency")
    manifest = _manifest([raw])

    async with async_session_maker() as session:
        result = await MarketDataMasterDataImporter(session).import_manifest(
            manifest,
            manifest_sha256=_digest(manifest),
        )
        await session.commit()
        keys = await session.scalar(select(func.count()).select_from(MdInstrumentLookupKey))

    assert result.lookup_key_count == 0
    assert result.canonical_only_count == 1
    assert keys == 0
    assert "instrument:fx:test:v1" not in json.dumps(result.as_dict())


@pytest.mark.asyncio
async def test_importer_rejects_duplicate_canonical_id_and_metadata_version_in_one_manifest() -> (
    None
):
    """The input cannot rely on intra-batch ordering to reinterpret a frozen version."""
    raw = _identity("stock")
    manifest = _manifest([raw, dict(raw)])

    async with async_session_maker() as session:
        with pytest.raises(MarketDataMasterDataImportError) as rejected:
            await MarketDataMasterDataImporter(session).import_manifest(
                manifest,
                manifest_sha256=_digest(manifest),
            )
        instruments = await session.scalar(select(func.count()).select_from(AssetInstrument))

    assert rejected.value.code == "MASTER_DATA_IMPORT_DUPLICATE_MANIFEST_VERSION"
    assert instruments == 0
