"""Read-only approved master-data lookup for multi-asset research identity.

The general market discovery service deliberately remains outside this adapter:
its display symbols are not sufficient to infer contractual facts such as a
futures expiry or an option multiplier.  This catalog exposes only identity
records that an operator has already placed in ``asset_instruments`` and that
are valid at the lookup time.  It never creates, enriches, or guesses an
identity from a search string.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import AssetInstrument
from app.schemas.asset_research import InstrumentIdentity, PublicAssetType


def _utc_now() -> datetime:
    """Return the current UTC time through a replaceable dependency for tests."""
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive reads and MySQL's timezone-aware values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalized(value: str) -> str:
    """Normalize user-facing identifiers for non-authoritative search matching."""
    return re.sub(r"[\s._:/-]+", "", value).upper()


class ApprovedInstrumentCatalog:
    """Expose only currently valid, internally approved master identities.

    ``asset_instruments`` is versioned.  A canonical ID may have older rows
    retained for audit, but the catalog exposes only the latest valid row at a
    lookup time.  If two rows claim the same latest ``valid_from`` timestamp,
    their authority is ambiguous and neither becomes a search candidate.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = db
        self._now = now

    async def list_instruments(
        self,
        *,
        asset_type: PublicAssetType,
        search: str = "",
        limit: int = 80,
    ) -> dict[str, Any]:
        """Return display candidates backed by validated active master records.

        An invalid/mismatched persisted JSON payload is ignored rather than
        surfaced as a partially reconstructed identity.  Search is a UI
        convenience only; final confirmation remains the resolver's exact
        symbol/venue check.
        """
        effective_at = _as_utc(self._now())
        rows = list(
            (
                await self._db.execute(
                    select(AssetInstrument)
                    .where(
                        AssetInstrument.asset_type == asset_type,
                        AssetInstrument.lifecycle_status == "ACTIVE",
                        AssetInstrument.valid_from <= effective_at,
                        or_(
                            AssetInstrument.valid_to.is_(None),
                            AssetInstrument.valid_to >= effective_at,
                        ),
                    )
                    .order_by(
                        AssetInstrument.canonical_id,
                        AssetInstrument.valid_from.desc(),
                        AssetInstrument.created_at.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        query = _normalized(search)
        candidates: list[dict[str, Any]] = []
        for record in self._current_records(rows):
            item = self._candidate_item(record)
            if item is None or not self._matches_query(item, query):
                continue
            candidates.append(item)
            if len(candidates) >= limit:
                break
        return {"asset_type": asset_type, "items": candidates}

    async def active_asset_types(self) -> set[str]:
        """Return public asset types with at least one usable active master row.

        The capability endpoint uses this as a second, independent gate after
        data-source authorization.  A registry permission alone must not make
        a page look ready when no resolvable instrument identity exists.
        """
        effective_at = _as_utc(self._now())
        rows = list(
            (
                await self._db.execute(
                    select(AssetInstrument)
                    .where(
                        AssetInstrument.lifecycle_status == "ACTIVE",
                        AssetInstrument.valid_from <= effective_at,
                        or_(
                            AssetInstrument.valid_to.is_(None),
                            AssetInstrument.valid_to >= effective_at,
                        ),
                    )
                    .order_by(
                        AssetInstrument.canonical_id,
                        AssetInstrument.valid_from.desc(),
                        AssetInstrument.created_at.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            record.asset_type
            for record in self._current_records(rows)
            if record.asset_type in {"bond", "fund", "futures", "option", "fx", "crypto"}
            and self._candidate_item(record) is not None
        }

    @staticmethod
    def _current_records(rows: list[AssetInstrument]) -> list[AssetInstrument]:
        """Choose the newest valid row per canonical ID without guessing ties."""
        grouped: dict[str, list[AssetInstrument]] = defaultdict(list)
        for row in rows:
            grouped[row.canonical_id].append(row)

        current: list[AssetInstrument] = []
        for canonical_id in sorted(grouped):
            versions = grouped[canonical_id]
            newest = versions[0]
            newest_valid_from = _as_utc(newest.valid_from)
            if sum(_as_utc(row.valid_from) == newest_valid_from for row in versions) != 1:
                continue
            current.append(newest)
        return current

    @staticmethod
    def _candidate_item(record: AssetInstrument) -> dict[str, Any] | None:
        """Validate persisted columns and JSON before exposing a candidate."""
        try:
            identity = InstrumentIdentity.model_validate(record.identity_json)
        except ValidationError:
            return None

        if (
            identity.asset_type != record.asset_type
            or identity.canonical_id != record.canonical_id
            or identity.identity_level != record.identity_level
            or identity.metadata_version != record.metadata_version
            or identity.venue != record.venue
            or identity.currency != record.currency
            or identity.product_type != record.product_type
        ):
            return None
        return {
            "asset_type": identity.asset_type,
            "identity_level": identity.identity_level,
            "symbol": identity.display_symbol,
            "name": identity.name,
            "market": identity.venue or "",
            "canonical_id": identity.canonical_id,
            "metadata_version": identity.metadata_version,
            "source_table": "asset_instruments",
            "asset_research_identity": identity.model_dump(mode="json"),
        }

    @staticmethod
    def _matches_query(item: dict[str, Any], query: str) -> bool:
        """Match a catalog search without treating a partial match as resolution."""
        if not query:
            return True
        searchable = (
            str(item.get("symbol") or ""),
            str(item.get("name") or ""),
            str(item.get("canonical_id") or ""),
        )
        return any(query in _normalized(value) for value in searchable)
