"""
Realtime market data service.

Supports tick subscription and streaming across brokers.
"""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class RealTimeDataService:
    """Service for managing real-time market data subscriptions and tick data.

    This service provides functionality for:
    1. Subscribing to and unsubscribing from real-time market data
    2. Retrieving the latest market quotes
    3. Fetching historical market data

    Attributes:
        _subscriptions: Dictionary mapping user IDs to their subscribed symbols
            per broker. Format: {user_id: {broker_id: [symbols]}}
        _tick_cache: Dictionary caching the latest tick data per broker and symbol.
            Format: {broker_id: {symbol: tick_data}}
    """

    def __init__(self):
        """Initialize the RealTimeDataService with empty subscriptions and cache."""
        # User-subscribed symbols {user_id: {broker_id: [symbols]}}
        self._subscriptions: dict[str, dict[str, list[str]]] = {}
        # Latest tick cache {broker_id: {symbol: tick_data}}
        self._tick_cache: dict[str, dict[str, dict[str, Any]]] = {}

    async def subscribe_ticks(
        self,
        user_id: str,
        broker_id: str | None,
        symbols: list[str],
    ) -> None:
        """Subscribe to real-time market data for the specified symbols.

        Args:
            user_id: The unique identifier of the user.
            broker_id: The broker identifier. Uses "default" if None.
            symbols: List of symbol codes to subscribe to.
        """
        if user_id not in self._subscriptions:
            self._subscriptions[user_id] = {}

        broker_key = broker_id or "default"
        if broker_key not in self._subscriptions[user_id]:
            self._subscriptions[user_id][broker_key] = []

        # Add new subscriptions
        for symbol in symbols:
            if symbol not in self._subscriptions[user_id][broker_key]:
                self._subscriptions[user_id][broker_key].append(symbol)

        logger.info(f"User {user_id} subscribed to {len(symbols)} symbols: {symbols}")

    async def unsubscribe_ticks(
        self,
        user_id: str,
        broker_id: str | None,
        symbols: list[str],
    ) -> None:
        """Unsubscribe from real-time market data for the specified symbols.

        Args:
            user_id: The unique identifier of the user.
            broker_id: The broker identifier. Uses "default" if None.
            symbols: List of symbol codes to unsubscribe from.
        """
        broker_key = broker_id or "default"

        if user_id in self._subscriptions and broker_key in self._subscriptions[user_id]:
            for symbol in symbols:
                if symbol in self._subscriptions[user_id][broker_key]:
                    self._subscriptions[user_id][broker_key].remove(symbol)

        logger.info(f"User {user_id} unsubscribed from {len(symbols)} symbols: {symbols}")

    async def get_subscribed_symbols(
        self,
        user_id: str,
        broker_id: str | None,
    ) -> list[str]:
        """Get the list of symbols subscribed by a user.

        Args:
            user_id: The unique identifier of the user.
            broker_id: The broker identifier. Uses "default" if None.

        Returns:
            List of symbol codes that the user is subscribed to.
        """
        broker_key = broker_id or "default"

        if user_id in self._subscriptions and broker_key in self._subscriptions[user_id]:
            return self._subscriptions[user_id][broker_key]

        return []

    async def get_tick(
        self,
        user_id: str,
        broker_id: str | None,
        symbol: str,
    ) -> dict[str, Any] | None:
        """Get the latest market data for a single symbol.

        Args:
            user_id: The unique identifier of the user.
            broker_id: The broker identifier. Uses "default" if None.
            symbol: The symbol code to retrieve data for.

        Returns:
            Dictionary containing tick data with fields:
                - symbol: The symbol code
                - timestamp: ISO format timestamp
                - open: Opening price
                - high: Highest price
                - low: Lowest price
                - close: Closing price
                - volume: Trading volume
                - bid: Bid price
                - ask: Ask price
                - bid_size: Bid size
                - ask_size: Ask size
            Returns mock data with zero values if symbol not found in cache.
        """
        broker_key = broker_id or "default"

        if broker_key in self._tick_cache and symbol in self._tick_cache[broker_key]:
            return self._tick_cache[broker_key][symbol]

        # Return mock data
        return {
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "open": 0.0,
            "high": 0.0,
            "low": 0.0,
            "close": 0.0,
            "volume": 0.0,
            "bid": None,
            "ask": None,
            "bid_size": None,
            "ask_size": None,
        }

    async def get_ticks(
        self,
        user_id: str,
        broker_id: str | None,
        symbols: list[str],
    ) -> dict[str, Any]:
        """Get the latest market data for multiple symbols in batch.

        Args:
            user_id: The unique identifier of the user.
            broker_id: The broker identifier. Uses "default" if None.
            symbols: List of symbol codes to retrieve data for.

        Returns:
            Dictionary mapping symbol codes to their tick data.
        """
        result = {}
        for symbol in symbols:
            result[symbol] = await self.get_tick(user_id, broker_id, symbol)
        return result

    async def get_historical_data(
        self,
        user_id: str,
        broker_id: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        frequency: str = "1d",
    ) -> list[dict[str, Any]]:
        """Get historical market data for a symbol.

        Fetches historical K-line data using akshare for A-share stocks.
        Supports daily, weekly, and monthly frequencies.

        Args:
            user_id: The unique identifier of the user.
            broker_id: The broker identifier.
            symbol: The symbol code to retrieve data for (e.g., 000001.SZ).
            start_date: Start date of the historical data range.
            end_date: End date of the historical data range.
            frequency: Data frequency (e.g., "1d" for daily, "1w" for weekly, "1M" for monthly).

        Returns:
            List of dictionaries containing OHLCV data with fields:
                - date: Trading date
                - open: Opening price
                - high: Highest price
                - low: Lowest price
                - close: Closing price
                - volume: Trading volume
                - change: Change percentage

        Raises:
            ValueError: If symbol format is invalid or data fetch fails.
        """
        try:
            import akshare as ak
        except ImportError:
            logger.error("akshare not installed, cannot fetch historical data")
            raise ValueError("akshare library is required for historical data")

        # Parse symbol (e.g., 000001.SZ -> 000001)
        code = symbol.split(".")[0] if "." in symbol else symbol
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        # Map frequency to akshare period
        period_map = {
            "1d": "daily",
            "daily": "daily",
            "1w": "weekly",
            "weekly": "weekly",
            "1M": "monthly",
            "monthly": "monthly",
        }
        period = period_map.get(frequency, "daily")

        logger.info(
            f"Fetching historical data: {symbol} ({code}) from {start_str} to {end_str}, period={period}"
        )

        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period=period,
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
                timeout=10,
            )

            if df.empty:
                logger.warning(f"No historical data found for {symbol}")
                return []

            # Rename Chinese column names to English
            df = df.rename(
                columns={
                    "日期": "date",
                    "开盘": "open",
                    "最高": "high",
                    "最低": "low",
                    "收盘": "close",
                    "成交量": "volume",
                    "涨跌幅": "change_pct",
                }
            )

            records = []
            for _, row in df.iterrows():
                records.append(
                    {
                        "date": str(row["date"]),
                        "open": round(float(row["open"]), 2),
                        "high": round(float(row["high"]), 2),
                        "low": round(float(row["low"]), 2),
                        "close": round(float(row["close"]), 2),
                        "volume": int(row["volume"]),
                        "change": round(float(row.get("change_pct", 0)), 2),
                    }
                )

            logger.info(f"Retrieved {len(records)} historical records for {symbol}")
            return records

        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol}: {e}")
            raise ValueError(f"Failed to fetch historical data: {e}")

    def update_tick(
        self,
        broker_id: str,
        symbol: str,
        tick_data: dict[str, Any],
    ) -> None:
        """Update the tick data cache (internal method for data sources).

        Args:
            broker_id: The broker identifier.
            symbol: The symbol code to update.
            tick_data: The tick data dictionary to cache.
        """
        if broker_id not in self._tick_cache:
            self._tick_cache[broker_id] = {}

        self._tick_cache[broker_id][symbol] = tick_data
