"""
Data provider factory.

Selects the appropriate data provider class based on the DataScript.source field.
Supports registration of new providers for extensibility.
"""

from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)

_PROVIDER_REGISTRY: dict[str, type] = {}


def register_provider(source: str, provider_class: type) -> None:
    """Register a data provider class for a given source.

    Args:
        source: Data source identifier (e.g. 'akshare', 'tushare').
        provider_class: The provider class to instantiate.
    """
    _PROVIDER_REGISTRY[source] = provider_class
    logger.info(f"Registered data provider: {source} -> {provider_class.__name__}")


def get_data_provider(source: str, db_config: dict[str, Any] | None = None) -> Any:
    """Get a data provider instance for the given source.

    Args:
        source: Data source identifier.
        db_config: Optional database configuration override.

    Returns:
        An instance of the registered provider class.

    Raises:
        ValueError: If the source is not registered.
    """
    provider_class = _PROVIDER_REGISTRY.get(source)
    if provider_class is None:
        raise ValueError(
            f"Unknown data source: '{source}'. "
            f"Registered sources: {list(_PROVIDER_REGISTRY.keys())}"
        )
    if db_config:
        return provider_class(db_config)
    return provider_class()


def list_providers() -> list[str]:
    """List all registered data source identifiers."""
    return list(_PROVIDER_REGISTRY.keys())


# Auto-register the built-in akshare provider
def _auto_register() -> None:
    """Register built-in providers on module import."""
    try:
        from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

        register_provider("akshare", AkshareToMySql)
    except ImportError:
        logger.debug("AkshareToMySql not available, skipping auto-registration")


_auto_register()
