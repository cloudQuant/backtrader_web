"""Point-in-time market-data adapter used by every non-stock research plugin."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Any, Protocol

from app.schemas.asset_research import (
    InstrumentIdentity,
    PublicAssetType,
    RawAssetSnapshot,
    RawObservation,
)
from app.services.asset_research.redaction import redact_sensitive_data

# The default bridge is intentionally warehouse-only.  It must never turn an
# approved *type* capability into an unapproved live AkShare request.
DEFAULT_ASSET_RESEARCH_SOURCE_ID = "akshare_data"


class MarketDataLookup(Protocol):
    """Narrow market-data dependency, easy to replace in deterministic tests."""

    async def lookup(
        self,
        *,
        asset_type: PublicAssetType,
        symbol: str,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        period: str = "daily",
        market: str | None = None,
        refresh_online: bool = False,
    ) -> dict[str, Any]: ...


class AssetResearchDataError(ValueError):
    """Stable source/identity error which the orchestrator records on its task."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def canonical_json_hash(value: Any) -> str:
    """Return the deterministic content hash used by immutable snapshot records."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sanitize_raw_snapshot(snapshot: RawAssetSnapshot) -> RawAssetSnapshot:
    """Redact untrusted fields and refresh the immutable hash before persistence.

    The generic adapter applies this boundary to its own provider payload, but
    injected source-specific adapters can return a prebuilt ``RawAssetSnapshot``.
    Applying it once more after source authorization keeps the persistence
    contract independent of any individual adapter implementation.
    """
    raw_fields = redact_sensitive_data(snapshot.raw_fields)
    history_rows = redact_sensitive_data(snapshot.history_rows)
    source_manifest = redact_sensitive_data(snapshot.source_manifest)
    observations = {
        field_name: observation.model_copy(
            update={"value": redact_sensitive_data(observation.value)}
        )
        for field_name, observation in snapshot.observations.items()
    }
    content = {
        "identity": snapshot.identity.model_dump(mode="json"),
        "cutoff_at": snapshot.cutoff_at.isoformat(),
        "raw_fields": raw_fields,
        "history_rows": history_rows,
        "observations": {
            field_name: observation.model_dump(mode="json")
            for field_name, observation in observations.items()
        },
        "source_manifest": source_manifest,
    }
    return snapshot.model_copy(
        update={
            "raw_fields": raw_fields,
            "history_rows": history_rows,
            "observations": observations,
            "source_manifest": source_manifest,
            "content_hash": canonical_json_hash(content),
        }
    )


def _normalized_symbol(value: str | None) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _row_date(row: dict[str, Any]) -> date | None:
    value = row.get("date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _timestamp(value: object) -> datetime | None:
    """Parse a provider timestamp without turning an unknown time into ``now``."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if value is None or not str(value).strip():
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _scalar_fields(value: object, *, prefix: str = "") -> dict[str, object]:
    """Flatten structured provider facts to stable field IDs for provenance."""
    if isinstance(value, Mapping):
        flattened: dict[str, object] = {}
        for key, nested in value.items():
            nested_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_scalar_fields(nested, prefix=nested_prefix))
        return flattened
    if isinstance(value, (list, tuple, set)):
        return {}
    return {prefix: value} if prefix else {}


def _observation(
    *,
    value: object,
    field_name: str,
    metadata: Mapping[str, object],
    source_id: str,
    retrieved_at: datetime,
    default_observed_at: datetime | None,
) -> RawObservation:
    """Build one explicit provenance envelope, preserving missing PIT facts."""
    field_metadata = metadata.get(field_name)
    details = field_metadata if isinstance(field_metadata, Mapping) else {}
    observed_at = _timestamp(details.get("observed_at")) or default_observed_at
    published_at = _timestamp(details.get("published_at"))
    available_at = _timestamp(details.get("available_at"))
    missing_reason = details.get("missing_reason")
    if available_at is None and missing_reason is None:
        missing_reason = "COMMON.AVAILABLE_AT_MISSING"
    return RawObservation(
        value=value,
        source_id=str(details.get("source_id") or source_id) or None,
        observed_at=observed_at,
        published_at=published_at,
        available_at=available_at,
        retrieved_at=retrieved_at,
        license_tag=str(details.get("license_tag")) if details.get("license_tag") else None,
        missing_reason=str(missing_reason) if missing_reason else None,
    )


class StrictMarketDataAdapter:
    """Fetch data only after confirming that the provider returned the same identity.

    A non-empty provider response is deliberately not enough: legacy market
    adapters may return a recent bar for a different symbol after an exact
    query misses.  That response cannot be converted into a research snapshot.
    """

    def __init__(
        self,
        market_data: MarketDataLookup,
        *,
        declared_source_id: str | None = None,
    ) -> None:
        self._market_data = market_data
        self._declared_source_id = declared_source_id

    @property
    def declared_source_ids(self) -> tuple[str, ...]:
        """Return the server-configured source identity used before collection.

        Test adapters and future source-specific adapters may omit this value,
        but the production default always declares its warehouse source.  The
        orchestrator uses this to evaluate capability before it invokes an
        adapter that could otherwise reach an upstream provider.
        """
        return (self._declared_source_id,) if self._declared_source_id else ()

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        """Fetch one frozen raw snapshot, retaining valid missing data for quality gating."""
        if identity.asset_type == "stock":
            raise AssetResearchDataError("INSTRUMENT_UNSUPPORTED")
        payload = await self._market_data.lookup(
            asset_type=identity.asset_type,
            symbol=identity.display_symbol,
            end_date=cutoff_at.date(),
            period="daily",
            market=identity.venue,
            # The general market service can contact AkShare when this flag is
            # true.  Multi-asset research is not permitted to make that
            # request until a dedicated, source-specific adapter with its own
            # network controls has been approved and installed.
            refresh_online=False,
        )
        self._validate_identity(identity, payload)
        history = (payload.get("history") or {}).get("rows") or []
        rows = [row for row in history if isinstance(row, dict)]
        rows = [
            row
            for row in rows
            if (row_date := _row_date(row)) is None or row_date <= cutoff_at.date()
        ]
        retrieved_at = datetime.now(timezone.utc)
        source_id = str(
            payload.get("source_id")
            or (payload.get("history") or {}).get("provider")
            or payload.get("provider")
            or "market_instrument"
        )
        self._validate_declared_source(source_id, payload.get("observations"))
        snapshot_values = dict(payload.get("snapshot") or {})
        snapshot_observed_at = _timestamp(
            snapshot_values.get("observed_at")
            or snapshot_values.get("update_time")
            or payload.get("observed_at")
        )
        if snapshot_observed_at is not None and snapshot_observed_at > cutoff_at:
            # A current quote returned for an historical request is evidence of
            # a provider limitation, not a legal historical fact.  Keep the
            # history separately and let quality reject the absent snapshot.
            snapshot_values = {}
        domain_facts = payload.get(identity.asset_type)
        raw_fields = {
            "snapshot": snapshot_values,
            "indicators": dict(payload.get("indicators") or {}),
            "warnings": [str(value) for value in payload.get("warnings") or []],
            "provider_symbol": payload.get("symbol"),
            "provider_market": payload.get("market"),
        }
        # Keep only the domain envelope corresponding to the already-validated
        # public asset type.  This lets a separately approved adapter carry
        # terms, NAV, curve, chain, macro or on-chain facts into the matching
        # plugin without accepting arbitrary provider top-level fields.
        if isinstance(domain_facts, Mapping):
            raw_fields[identity.asset_type] = dict(domain_facts)
        # A source may accidentally return credentials in a data, warning or
        # metadata field.  Preserve the field shape for auditability but remove
        # the value before provenance, hashes and database persistence see it.
        raw_fields = redact_sensitive_data(raw_fields)
        rows = redact_sensitive_data(rows)
        metadata = payload.get("observations")
        observation_metadata = metadata if isinstance(metadata, Mapping) else {}
        observations: dict[str, RawObservation] = {}
        for section in ("snapshot", "indicators", identity.asset_type):
            if section not in raw_fields:
                continue
            defaults = snapshot_observed_at if section == "snapshot" else None
            for field_name, value in _scalar_fields(raw_fields[section], prefix=section).items():
                observations[field_name] = _observation(
                    value=value,
                    field_name=field_name,
                    metadata=observation_metadata,
                    source_id=source_id,
                    retrieved_at=retrieved_at,
                    default_observed_at=defaults,
                )
        for row in rows:
            row_date = _row_date(row)
            observed_at = (
                datetime.combine(row_date, datetime.min.time(), tzinfo=timezone.utc)
                if row_date is not None
                else None
            )
            row_prefix = f"history:{row_date.isoformat() if row_date is not None else 'unknown'}"
            for field_name, value in _scalar_fields(row, prefix=row_prefix).items():
                if field_name.rsplit(".", maxsplit=1)[-1] == "date":
                    continue
                observations[field_name] = _observation(
                    value=value,
                    field_name=field_name,
                    metadata=observation_metadata,
                    source_id=source_id,
                    retrieved_at=retrieved_at,
                    default_observed_at=observed_at,
                )
        cutoff = (
            cutoff_at if cutoff_at.tzinfo is not None else cutoff_at.replace(tzinfo=timezone.utc)
        )
        pit_violations = [
            field_name
            for field_name, observation in observations.items()
            if observation.available_at is None or observation.available_at > cutoff
        ]
        point_in_time_status = "VERIFIED" if observations and not pit_violations else "UNVERIFIED"
        source_manifest = {
            "provider": source_id,
            "source_id": source_id,
            "observed_at": max(
                (str(row.get("date")) for row in rows if row.get("date")), default=None
            ),
            "available_at": None,
            "retrieved_at": retrieved_at.isoformat(),
            "point_in_time_status": point_in_time_status,
            "pit_unverified_fields": pit_violations[:100],
            "license_status": "UNKNOWN",
            "allowed_use": "RESEARCH_ONLY",
        }
        content = {
            "identity": identity.model_dump(mode="json"),
            "cutoff_at": cutoff_at.isoformat(),
            "raw_fields": raw_fields,
            "history_rows": rows,
            "observations": {
                field_name: observation.model_dump(mode="json")
                for field_name, observation in observations.items()
            },
            "source_manifest": source_manifest,
        }
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=retrieved_at,
            raw_schema_version="market-instrument-v1",
            raw_fields=raw_fields,
            history_rows=rows,
            observations=observations,
            source_manifest=source_manifest,
            license_tags=["UNKNOWN"],
            content_hash=canonical_json_hash(content),
        )

    @staticmethod
    def _validate_identity(identity: InstrumentIdentity, payload: dict[str, Any]) -> None:
        provider_asset_type = str(payload.get("asset_type") or "").strip().lower()
        provider_symbol = str(payload.get("symbol") or "").strip()
        provider_market = str(payload.get("market") or "").strip()
        if provider_asset_type != identity.asset_type:
            raise AssetResearchDataError("INSTRUMENT_UNSUPPORTED")
        if _normalized_symbol(provider_symbol) != _normalized_symbol(identity.display_symbol):
            raise AssetResearchDataError("INSTRUMENT_UNSUPPORTED")
        if (
            identity.venue
            and provider_market
            and provider_market.casefold() != identity.venue.casefold()
        ):
            raise AssetResearchDataError("INSTRUMENT_UNSUPPORTED")

    def _validate_declared_source(self, source_id: str, observations: object) -> None:
        """Reject a response that switches provider after capability preflight.

        The source registry is an authorization boundary, not an attribution
        hint.  A default warehouse adapter therefore cannot return a payload
        or field that claims a different source.  Multi-source collection must
        instead be implemented as an explicit, separately approved adapter.
        """
        declared = self._declared_source_id
        if not declared:
            return
        if source_id != declared:
            raise AssetResearchDataError("SOURCE_UNAVAILABLE")
        if not isinstance(observations, Mapping):
            return
        for metadata in observations.values():
            if not isinstance(metadata, Mapping):
                continue
            observed_source = str(metadata.get("source_id") or "").strip()
            if observed_source and observed_source != declared:
                raise AssetResearchDataError("SOURCE_UNAVAILABLE")
