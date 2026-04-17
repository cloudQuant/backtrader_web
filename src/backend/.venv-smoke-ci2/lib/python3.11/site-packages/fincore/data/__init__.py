"""Data provider integrations for fincore.

Provides unified access to financial data from multiple sources:
- Yahoo Finance (via yfinance)
- Alpha Vantage (via alpha-vantage)
- Tushare (Chinese A-share data)
- AkShare (Chinese financial data)
"""

from __future__ import annotations

from fincore.data.providers import (
    AkShareProvider,
    AlphaVantageProvider,
    DataProvider,
    TushareProvider,
    YahooFinanceProvider,
    fetch_multiple_prices,
    fetch_price_data,
    get_provider,
)

__all__ = [
    "AkShareProvider",
    "AlphaVantageProvider",
    "DataProvider",
    "TushareProvider",
    "YahooFinanceProvider",
    "fetch_multiple_prices",
    "fetch_price_data",
    "get_provider",
]
