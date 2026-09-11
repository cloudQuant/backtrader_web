"""Compatibility exports for market-data provider contracts and OpenBB adapter.

Provider-neutral DTOs, raw runner transport, and OpenBB receipt validation live
in focused modules. Existing imports from ``market_data.providers`` remain
stable while the default OpenBB runtime stays opt-in and fail-closed.
"""

from app.services.market_data.openbb_runner import (
    OPENBB_RUNNER_PROTOCOL_SELF_CHECK_VERSION,
    OPENBB_RUNNER_PROTOCOL_VERSION,
    OPENBB_RUNNER_TRANSPORT_VERSION,
    OpenBBProviderError,
)
from app.services.market_data.openbb_subprocess_provider import (
    DEFAULT_OPENBB_MAX_CONCURRENT_RUNS,
    OpenBBSubprocessProvider,
    _openbb_runner_environment,  # noqa: F401
    _openbb_runner_workdir,  # noqa: F401
)
from app.services.market_data.provider_models import (
    MarketDataProvider,
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
    SharedSourcePayloadSegment,
)

__all__ = [
    "DEFAULT_OPENBB_MAX_CONCURRENT_RUNS",
    "MarketDataProvider",
    "MarketDataProviderRequest",
    "OPENBB_RUNNER_PROTOCOL_SELF_CHECK_VERSION",
    "OPENBB_RUNNER_PROTOCOL_VERSION",
    "OPENBB_RUNNER_TRANSPORT_VERSION",
    "OpenBBProviderError",
    "OpenBBSubprocessProvider",
    "ProviderFetchResult",
    "ProviderMarketObservation",
    "SharedSourcePayloadSegment",
]
