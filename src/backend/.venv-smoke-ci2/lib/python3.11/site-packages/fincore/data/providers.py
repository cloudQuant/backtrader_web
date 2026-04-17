"""Financial data provider implementations.

Provides a unified interface for fetching financial data from various sources:
- Yahoo Finance (free, limited)
- Alpha Vantage (free with API key, rate limited)
- Tushare (Chinese A-share, requires token)
- AkShare (Chinese data, free)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from datetime import datetime

__all__ = [
    "AkShareProvider",
    "AlphaVantageProvider",
    "BatchFetchError",
    "DataProvider",
    "TushareProvider",
    "YahooFinanceProvider",
    "fetch_multiple_prices",
    "fetch_price_data",
    "get_provider",
]


# Module-level logger
logger = logging.getLogger(__name__)

# Default HTTP timeout (seconds) for requests; prevents indefinite hangs
HTTP_TIMEOUT = 30


class BatchFetchError(Exception):
    """Raised when strict batch fetch fails for one or more symbols."""

    def __init__(
        self,
        provider: str,
        errors: dict[str, Exception],
        partial_results: dict[str, pd.DataFrame],
    ) -> None:
        self.provider = provider
        self.errors = errors
        self.partial_results = partial_results
        symbols = ", ".join(sorted(errors.keys()))
        super().__init__(f"Failed to fetch {len(errors)} symbol(s) from {provider}: {symbols}")


class DataProvider(ABC):
    """Abstract base class for financial data providers.

    All data providers should implement this interface to ensure
    consistent behavior across different data sources.

    Examples
    --------
    >>> provider = YahooFinanceProvider()
    >>> data = provider.fetch("AAPL", start="2020-01-01", end="2020-12-31")
    >>> returns = data['Adj Close'].pct_change().dropna()
    """

    @abstractmethod
    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        adjust: bool = True,
    ) -> pd.DataFrame:
        """Fetch historical price data for a single symbol.

        Parameters
        ----------
        symbol : str
            Ticker symbol (e.g., 'AAPL', '600519.SS').
        start : str or datetime
            Start date ('YYYY-MM-DD' or datetime).
        end : str or datetime
            End date ('YYYY-MM-DD' or datetime).
        interval : str, default '1d'
            Data frequency. Options: '1m', '5m', '15m', '30m', '60m',
            '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'.
        adjust : bool, default True
            Whether to adjust prices for splits and dividends.

        Returns
        -------
        pd.DataFrame
            DataFrame with price data. Columns typically include:
            Open, High, Low, Close, Adj Close, Volume
        """
        ...

    @abstractmethod
    def fetch_multiple(
        self,
        symbols: list[str],
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        adjust: bool = True,
        strict: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Fetch historical data for multiple symbols.

        Parameters
        ----------
        symbols : list of str
            Ticker symbols.
        start : str or datetime
            Start date.
        end : str or datetime
            End date.
        interval : str, default '1d'
            Data frequency.
        adjust : bool, default True
            Whether to adjust prices.
        strict : bool, default False
            If True, raise :class:`BatchFetchError` when any symbol fails.
            If False, failed symbols are returned as empty DataFrames.

        Returns
        -------
        dict
            Dictionary mapping symbols to their DataFrames.
        """
        ...

    @abstractmethod
    def get_info(self, symbol: str) -> dict:
        """Get basic information about a symbol.

        Parameters
        ----------
        symbol : str
            Ticker symbol.

        Returns
        -------
        dict
            Dictionary with symbol information (name, exchange, etc.).
        """
        ...

    def to_returns(
        self,
        price_data: pd.DataFrame,
        column: str = "Adj Close",
    ) -> pd.Series:
        """Convert price data to returns.

        Parameters
        ----------
        price_data : pd.DataFrame
            Price data from fetch().
        column : str, default 'Adj Close'
            Column to use for return calculation.

        Returns
        -------
        pd.Series
            Simple returns.
        """
        if column not in price_data.columns:
            # Fallback to Close if Adj Close not available
            column = "Close"
        return price_data[column].pct_change().dropna()

    def validate_dates(
        self,
        start: str | datetime,
        end: str | datetime,
    ) -> tuple[pd.Timestamp, pd.Timestamp]:
        """Validate and convert date inputs.

        Parameters
        ----------
        start : str or datetime
            Start date.
        end : str or datetime
            End date.

        Returns
        -------
        tuple
            (start_dt, end_dt) as datetime objects.
        """
        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)

        if start_dt >= end_dt:
            raise ValueError("start date must be before end date")

        # Ensure we return Timestamp, not NaTType
        if pd.isna(start_dt) or pd.isna(end_dt):
            raise ValueError("Invalid date values")

        return pd.Timestamp(start_dt), pd.Timestamp(end_dt)


class YahooFinanceProvider(DataProvider):
    """Yahoo Finance data provider using yfinance.

    Free to use, no API key required. Rate limited but
    generally sufficient for personal use.

    Parameters
    ----------
    session : requests.Session, optional
        Custom session for advanced usage.

    Examples
    --------
    >>> provider = YahooFinanceProvider()
    >>> data = provider.fetch("AAPL", start="2020-01-01", end="2020-12-31")
    >>> data.head()
    """

    def __init__(self, session=None):
        try:
            import yfinance as yf

            self._yf = yf
            self._session = session
        except ImportError as e:
            raise ImportError(
                "yfinance is required for YahooFinanceProvider. Install with: pip install yfinance"
            ) from e

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        adjust: bool = True,
    ) -> pd.DataFrame:
        """Fetch historical price data from Yahoo Finance.

        Parameters
        ----------
        symbol : str
            Ticker symbol (e.g., 'AAPL', '^GSPC').
        start : str or datetime
            Start date.
        end : str or datetime
            End date.
        interval : str, default '1d'
            Data frequency.
        adjust : bool, default True
            Whether to use adjusted prices.

        Returns
        -------
        pd.DataFrame
            Historical price data.
        """
        start_dt, end_dt = self.validate_dates(start, end)

        ticker = self._yf.Ticker(symbol)

        kwargs = {
            "start": start_dt,
            "end": end_dt,
            "interval": interval,
            "progress": False,
        }

        if self._session:
            kwargs["session"] = self._session

        data = ticker.history(**kwargs)

        if data.empty:
            raise ValueError(f"No data found for symbol {symbol}")

        # Rename columns to standard format
        data.columns = [col.replace(" ", " ") for col in data.columns]

        return data

    def fetch_multiple(
        self,
        symbols: list[str],
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        adjust: bool = True,
        strict: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Fetch data for multiple symbols.

        Parameters
        ----------
        symbols : list of str
            Ticker symbols.
        start : str or datetime
            Start date.
        end : str or datetime
            End date.
        interval : str, default '1d'
            Data frequency.
        adjust : bool, default True
            Whether to use adjusted prices.
        strict : bool, default False
            If True, raise :class:`BatchFetchError` when any symbol fails.
            If False, failed symbols are returned as empty DataFrames.

        Returns
        -------
        dict
            Dictionary mapping symbols to DataFrames.
        """
        results = {}
        errors: dict[str, Exception] = {}
        for symbol in symbols:
            try:
                results[symbol] = self.fetch(symbol, start, end, interval, adjust)
            except (ConnectionError, TimeoutError, ValueError, KeyError, OSError, RuntimeError) as e:
                logger.warning(
                    "Failed to fetch %s from Yahoo Finance: %s",
                    symbol,
                    e,
                    extra={"provider": "YahooFinance", "symbol": symbol},
                )
                if strict:
                    errors[symbol] = e
                else:
                    results[symbol] = pd.DataFrame()
        if strict and errors:
            raise BatchFetchError("YahooFinance", errors=errors, partial_results=results)
        return results

    def get_info(self, symbol: str) -> dict:
        """Get information about a symbol.

        Parameters
        ----------
        symbol : str
            Ticker symbol.

        Returns
        -------
        dict
            Symbol information.
        """
        ticker = self._yf.Ticker(symbol)
        info = ticker.info

        return {
            "symbol": symbol,
            "name": info.get("longName", info.get("shortName", "N/A")),
            "exchange": info.get("exchange", "N/A"),
            "currency": info.get("currency", "N/A"),
            "industry": info.get("industry", "N/A"),
            "sector": info.get("sector", "N/A"),
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
        }


class AlphaVantageProvider(DataProvider):
    """Alpha Vantage data provider.

    Requires a free API key from https://www.alphavantage.co/
    Rate limited to 5 calls/minute for free tier.

    Parameters
    ----------
    api_key : str
        Alpha Vantage API key.
    outputsize : str, default 'full'
        'compact' (100 data points) or 'full' (20+ years).

    Examples
    --------
    >>> provider = AlphaVantageProvider(api_key="YOUR_KEY")
    >>> data = provider.fetch("AAPL", start="2020-01-01", end="2020-12-31")
    """

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str, outputsize: str = "full"):
        try:
            import requests

            self._requests = requests
        except ImportError as e:
            raise ImportError(
                "requests is required for AlphaVantageProvider. Install with: pip install requests"
            ) from e

        self.api_key = api_key
        self.outputsize = outputsize
        self._session = self._requests.Session()

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        adjust: bool = True,
    ) -> pd.DataFrame:
        """Fetch historical price data from Alpha Vantage."""
        start_dt, end_dt = self.validate_dates(start, end)

        # Map interval to Alpha Vantage function
        function_map = {
            "1d": "TIME_SERIES_DAILY",
            "1wk": "TIME_SERIES_WEEKLY",
            "1mo": "TIME_SERIES_MONTHLY",
        }

        function = function_map.get(interval, "TIME_SERIES_DAILY")

        params = {
            "function": function,
            "symbol": symbol,
            "outputsize": self.outputsize,
            "apikey": self.api_key,
        }

        response = self._session.get(self.BASE_URL, params=params, timeout=HTTP_TIMEOUT)
        data = response.json()

        # Parse response
        time_key = {
            "TIME_SERIES_DAILY": "Time Series (Daily)",
            "TIME_SERIES_WEEKLY": "Weekly Time Series",
            "TIME_SERIES_MONTHLY": "Monthly Time Series",
        }.get(function)

        if time_key not in data:
            error = data.get("Note", data.get("Error Message", "Unknown error"))
            raise ValueError(f"Alpha Vantage error: {error}")

        time_series = data[time_key]

        # Convert to DataFrame
        df = pd.DataFrame.from_dict(time_series, orient="index")
        df.index = pd.to_datetime(df.index)
        df = df.astype(float)
        df.columns = [col.split(". ")[1] for col in df.columns]
        df = df.sort_index()

        # Filter by date range
        df = df.loc[start_dt:end_dt]

        # Add Adj Close (same as Close for daily data)
        if adjust and "close" in df.columns:
            df["Adj Close"] = df["close"]

        return df

    def fetch_multiple(
        self,
        symbols: list[str],
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        adjust: bool = True,
        strict: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Fetch data for multiple symbols."""
        results = {}
        errors: dict[str, Exception] = {}
        for symbol in symbols:
            try:
                results[symbol] = self.fetch(symbol, start, end, interval, adjust)
            except (ConnectionError, TimeoutError, ValueError, KeyError, OSError, RuntimeError) as e:
                logger.warning(
                    "Failed to fetch %s from Alpha Vantage: %s",
                    symbol,
                    e,
                    extra={"provider": "AlphaVantage", "symbol": symbol},
                )
                if strict:
                    errors[symbol] = e
                else:
                    results[symbol] = pd.DataFrame()
        if strict and errors:
            raise BatchFetchError("AlphaVantage", errors=errors, partial_results=results)
        return results

    def get_info(self, symbol: str) -> dict:
        """Get information about a symbol."""
        params = {
            "function": "OVERVIEW",
            "symbol": symbol,
            "apikey": self.api_key,
        }

        response = self._session.get(self.BASE_URL, params=params, timeout=HTTP_TIMEOUT)
        info = response.json()

        return {
            "symbol": symbol,
            "name": info.get("Name", "N/A"),
            "exchange": info.get("Exchange", "N/A"),
            "currency": info.get("Currency", "N/A"),
            "industry": info.get("Industry", "N/A"),
            "sector": info.get("Sector", "N/A"),
            "market_cap": info.get("MarketCapitalization"),
            "shares_outstanding": info.get("SharesOutstanding"),
        }


class TushareProvider(DataProvider):
    """Tushare data provider for Chinese A-share market.

    Requires a free token from https://tushare.pro/
    Provides comprehensive Chinese market data.

    Parameters
    ----------
    token : str
        Tushare API token.

    Examples
    --------
    >>> provider = TushareProvider(token="YOUR_TOKEN")
    >>> data = provider.fetch("000001.SZ", start="2020-01-01", end="2020-12-31")
    """

    def __init__(self, token: str):
        try:
            import tushare as ts

            self._ts = ts
            self._token = token
            self._pro = None
        except ImportError as e:
            raise ImportError("tushare is required for TushareProvider. Install with: pip install tushare") from e

    def _get_pro(self):
        """Lazy initialization of Pro API."""
        if self._pro is None:
            self._pro = self._ts.pro_api(self._token)
        return self._pro

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        adjust: bool = True,
    ) -> pd.DataFrame:
        """Fetch historical data from Tushare.

        Parameters
        ----------
        symbol : str
            Stock code (e.g., '000001.SZ', '600519.SH').
        start : str or datetime
            Start date.
        end : str or datetime
            End date.
        interval : str, default '1d'
            Data frequency (only '1d' supported for now).
        adjust : bool, default True
            Whether to use adjusted prices ('qfq' for forward-adjusted).

        Returns
        -------
        pd.DataFrame
            Historical price data.
        """
        start_dt, end_dt = self.validate_dates(start, end)

        # Convert symbol format: 000001.SZ -> 000001.SZ
        # Tushare expects TS code format
        ts_code = symbol

        # Get daily data
        pro = self._get_pro()

        # Adjust parameter: '' (no adjustment), 'qfq' (forward), 'hfq' (backward)
        adj = "qfq" if adjust else ""

        data = pro.daily(
            ts_code=ts_code,
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=end_dt.strftime("%Y%m%d"),
            adj=adj,
        )

        if data.empty:
            raise ValueError(f"No data found for symbol {symbol}")

        # Format DataFrame
        data = data.sort_values("trade_date")
        data = data.set_index("trade_date")
        data.index = pd.to_datetime(data.index)

        # Rename columns to match Yahoo Finance format
        column_map = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "vol": "Volume",
            "amount": "Amount",
        }
        data = data.rename(columns=column_map)

        # Add Adj Close (same as Close for already adjusted data)
        if adjust:
            data["Adj Close"] = data["Close"]

        return data[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]

    def fetch_multiple(
        self,
        symbols: list[str],
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        adjust: bool = True,
        strict: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Fetch data for multiple symbols."""
        results = {}
        errors: dict[str, Exception] = {}
        for symbol in symbols:
            try:
                results[symbol] = self.fetch(symbol, start, end, interval, adjust)
            except (ConnectionError, TimeoutError, ValueError, KeyError, OSError, RuntimeError) as e:
                logger.warning(
                    "Failed to fetch %s from Tushare: %s",
                    symbol,
                    e,
                    extra={"provider": "Tushare", "symbol": symbol},
                )
                if strict:
                    errors[symbol] = e
                else:
                    results[symbol] = pd.DataFrame()
        if strict and errors:
            raise BatchFetchError("Tushare", errors=errors, partial_results=results)
        return results

    def get_info(self, symbol: str) -> dict:
        """Get information about a symbol."""
        pro = self._get_pro()

        info = pro.stock_basic(ts_code=symbol, fields="ts_code,name,industry,list_date")

        if info.empty:
            return {
                "symbol": symbol,
                "name": "N/A",
                "exchange": "N/A",
                "industry": "N/A",
            }

        row = info.iloc[0]

        return {
            "symbol": symbol,
            "name": row["name"],
            "exchange": row.get("exchange", "N/A"),
            "industry": row.get("industry", "N/A"),
            "list_date": row.get("list_date"),
        }


class AkShareProvider(DataProvider):
    """AkShare data provider for Chinese financial data.

    Free to use, no API key required. Provides comprehensive
    Chinese market and economic data.

    Examples
    --------
    >>> provider = AkShareProvider()
    >>> data = provider.fetch("000001", start="2020-01-01", end="2020-12-31")
    """

    def __init__(self):
        try:
            import akshare as ak

            self._ak = ak
        except ImportError as e:
            raise ImportError("akshare is required for AkShareProvider. Install with: pip install akshare") from e

    def fetch(  # type: ignore[override]
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """Fetch historical data from AkShare.

        Parameters
        ----------
        symbol : str
            Stock code (e.g., '000001' for Ping An Bank).
        start : str or datetime
            Start date.
        end : str or datetime
            End date.
        interval : str, default '1d'
            Data frequency.
        adjust : str, default 'qfq'
            Adjustment type: '' (none), 'qfq' (forward), 'hfq' (backward).

        Returns
        -------
        pd.DataFrame
            Historical price data.
        """
        start_dt, end_dt = self.validate_dates(start, end)

        # AkShare uses different API functions
        # For individual stocks: stock_zh_a_hist
        data = self._ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=end_dt.strftime("%Y%m%d"),
            adjust=adjust,
        )

        if data.empty:
            raise ValueError(f"No data found for symbol {symbol}")

        # Format columns - map Chinese column names to English
        # AkShare returns data with Chinese column names, so we translate them
        column_map = {
            "开盘": "Open",  # Opening price
            "最高": "High",  # Highest price
            "最低": "Low",  # Lowest price
            "收盘": "Close",  # Closing price
            "成交量": "Volume",  # Trading volume
            "成交额": "Amount",  # Trading amount
            "振幅": "Amplitude",  # Price amplitude
            "涨跌幅": "ChangePct",  # Percentage change
            "涨跌额": "Change",  # Absolute change
            "换手率": "Turnover",  # Turnover rate
        }

        data = data.rename(columns=column_map)
        # Set the Chinese date column as index
        data = data.set_index("日期")
        data.index = pd.to_datetime(data.index)
        data = data.sort_index()

        # Add Adj Close
        data["Adj Close"] = data["Close"]

        return data[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]

    def fetch_multiple(  # type: ignore[override]
        self,
        symbols: list[str],
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        adjust: str = "qfq",
        strict: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Fetch data for multiple symbols."""
        results = {}
        errors: dict[str, Exception] = {}
        for symbol in symbols:
            try:
                results[symbol] = self.fetch(symbol, start, end, interval, adjust)
            except (ConnectionError, TimeoutError, ValueError, KeyError, OSError, RuntimeError) as e:
                logger.warning(
                    "Failed to fetch %s from AkShare: %s",
                    symbol,
                    e,
                    extra={"provider": "AkShare", "symbol": symbol},
                )
                if strict:
                    errors[symbol] = e
                else:
                    results[symbol] = pd.DataFrame()
        if strict and errors:
            raise BatchFetchError("AkShare", errors=errors, partial_results=results)
        return results

    def get_info(self, symbol: str) -> dict:
        """Get information about a symbol."""
        try:
            info = self._ak.stock_individual_info_em(symbol=symbol)
        except (ConnectionError, TimeoutError, ValueError, KeyError, OSError, RuntimeError) as e:
            logger.warning(
                "Failed to get info for %s from AkShare: %s",
                symbol,
                e,
                extra={"provider": "AkShare", "symbol": symbol},
            )
            return {
                "symbol": symbol,
                "name": "N/A",
                "exchange": "N/A",
                "industry": "N/A",
            }

        return {
            "symbol": symbol,
            # AkShare returns Chinese keys - map them to English field names
            "name": info.get("item", {}).get("股票简称", "N/A"),  # Stock short name
            "exchange": info.get("item", {}).get("交易所", "N/A"),  # Exchange name
            "industry": info.get("item", {}).get("行业", "N/A"),  # Industry classification
        }


# =============================================================================
# Convenience Functions
# =============================================================================


def get_provider(
    name: str,
    **kwargs,
) -> DataProvider:
    """Get a data provider instance by name.

    Parameters
    ----------
    name : str
        Provider name. Options: 'yahoo', 'alphavantage', 'tushare', 'akshare'.
    **kwargs
        Provider-specific arguments (api_key, token, etc.).

    Returns
    -------
    DataProvider
        Initialized provider instance.

    Examples
    --------
    >>> yahoo = get_provider("yahoo")
    >>> av = get_provider("alphavantage", api_key="YOUR_KEY")
    """
    name = name.lower().strip()

    providers = {
        "yahoo": YahooFinanceProvider,
        "yfinance": YahooFinanceProvider,
        "alphavantage": AlphaVantageProvider,
        "alpha_vantage": AlphaVantageProvider,
        "av": AlphaVantageProvider,
        "tushare": TushareProvider,
        "ts": TushareProvider,
        "akshare": AkShareProvider,
        "ak": AkShareProvider,
    }

    if name not in providers:
        raise ValueError(f"Unknown provider {name!r}. Available: {sorted(set(providers.keys()))}")

    return providers[name](**kwargs)  # type: ignore[return-value]


def fetch_price_data(
    symbol: str,
    provider: str | DataProvider = "yahoo",
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    years: int = 5,
    interval: str = "1d",
    **kwargs,
) -> pd.DataFrame:
    """Fetch price data for a single symbol.

    Convenience function that automatically handles date defaults.

    Parameters
    ----------
    symbol : str
        Ticker symbol.
    provider : str or DataProvider, default 'yahoo'
        Data provider to use.
    start : str or datetime, optional
        Start date. Defaults to (end - years).
    end : str or datetime, optional
        End date. Defaults to today.
    years : int, default 5
        Number of years if start not specified.
    interval : str, default '1d'
        Data frequency.
    **kwargs
        Additional arguments for provider.

    Returns
    -------
    pd.DataFrame
        Price data.

    Examples
    --------
    >>> data = fetch_price_data("AAPL", years=3)
    >>> data = fetch_price_data("AAPL", start="2020-01-01", end="2020-12-31")
    >>> data = fetch_price_data("000001.SZ", provider="tushare", token="...")
    """
    if isinstance(provider, str):
        provider = get_provider(provider, **kwargs)

    if end is None:
        end = pd.Timestamp.today()
    elif isinstance(end, str):
        end = pd.to_datetime(end)

    if start is None:
        start = end - pd.DateOffset(years=years)
    elif isinstance(start, str):
        start = pd.to_datetime(start)

    assert start is not None and end is not None  # guaranteed by logic above
    return provider.fetch(symbol, start, end, interval)


def fetch_multiple_prices(
    symbols: list[str],
    provider: str | DataProvider = "yahoo",
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    years: int = 5,
    interval: str = "1d",
    strict: bool = False,
    **kwargs,
) -> dict[str, pd.DataFrame]:
    """Fetch price data for multiple symbols.

    Parameters
    ----------
    symbols : list of str
        Ticker symbols.
    provider : str or DataProvider, default 'yahoo'
        Data provider to use.
    start : str or datetime, optional
        Start date.
    end : str or datetime, optional
        End date.
    years : int, default 5
        Number of years if start not specified.
    interval : str, default '1d'
        Data frequency.
    strict : bool, default False
        If True, raise :class:`BatchFetchError` when any symbol fails.
        If False, failed symbols are returned as empty DataFrames.
    **kwargs
        Additional arguments for provider.

    Returns
    -------
    dict
        Dictionary mapping symbols to DataFrames.

    Examples
    --------
    >>> data = fetch_multiple_prices(["AAPL", "MSFT", "GOOGL"], years=3)
    >>> data = fetch_multiple_prices(
    ...     ["000001.SZ", "600519.SH"],
    ...     provider="tushare",
    ...     token="..."
    ... )
    """
    if isinstance(provider, str):
        provider = get_provider(provider, **kwargs)

    if end is None:
        end = pd.Timestamp.today()
    elif isinstance(end, str):
        end = pd.to_datetime(end)

    if start is None:
        start = end - pd.DateOffset(years=years)
    elif isinstance(start, str):
        start = pd.to_datetime(start)

    assert start is not None and end is not None  # guaranteed by logic above
    return provider.fetch_multiple(symbols, start, end, interval, strict=strict)
