"""Provider boundary for approved multi-asset data collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.schemas.asset_research import InstrumentIdentity, RawAssetSnapshot


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    """Server-owned external request controls for one source provider."""

    allowed_hosts: tuple[str, ...]
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 15.0
    total_timeout_seconds: float = 30.0
    max_response_bytes: int = 10_000_000
    max_retries: int = 2

    def validate(self) -> None:
        if not self.allowed_hosts:
            raise ValueError("PROVIDER_ALLOWED_HOSTS_EMPTY")
        if self.max_retries < 0 or self.max_retries > 5:
            raise ValueError("PROVIDER_RETRY_LIMIT_INVALID")
        if self.max_response_bytes <= 0:
            raise ValueError("PROVIDER_RESPONSE_SIZE_INVALID")
        if not (
            0 < self.connect_timeout_seconds < self.read_timeout_seconds <= self.total_timeout_seconds
        ):
            raise ValueError("PROVIDER_TIMEOUT_ORDER_INVALID")


class AssetDataProvider(Protocol):
    """One approved source adapter used by the research orchestrator."""

    source_id: str
    declared_source_ids: tuple[str, ...]
    network_policy: NetworkPolicy

    async def collect(
        self,
        identity: InstrumentIdentity,
        *,
        cutoff_at: datetime,
    ) -> RawAssetSnapshot: ...

