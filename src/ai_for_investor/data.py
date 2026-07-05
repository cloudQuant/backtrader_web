"""
Data acquisition utilities for downloading stock data using akshare.

This module provides functions to fetch Chinese stock market data
and convert it to backtrader-compatible data feeds.
"""
import backtrader as bt
from datetime import datetime
from typing import Optional


def get_stock_data(
    symbol: str,
    start_date: str,
    end_date: str,
    adjust: str = "qfq"
) -> bt.feeds.PandasData:
    """
    Fetch A-share stock data using akshare and convert to backtrader data feed.

    Args:
        symbol: Stock code, e.g., '000001' or '000001.SZ'.
        start_date: Start date in 'YYYY-MM-DD' format.
        end_date: End date in 'YYYY-MM-DD' format.
        adjust: Adjustment method - 'qfq' for forward, 'hfq' for backward, '' for none.

    Returns:
        bt.feeds.PandasData: Backtrader data feed.

    Raises:
        ValueError: If no data is retrieved for the symbol.

    Example:
        >>> data = get_stock_data('000001', '2023-01-01', '2024-01-01')
        >>> cerebro.adddata(data)
    """
    import akshare as ak
    import pandas as pd

    # Parse stock code
    code = symbol.split('.')[0]

    # Format dates for akshare
    start_str = start_date.replace('-', '')
    end_str = end_date.replace('-', '')

    # Download data
    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=start_str,
        end_date=end_str,
        adjust=adjust
    )

    if df.empty:
        raise ValueError(f"No data retrieved for stock {symbol}")

    # Rename columns to English
    df = df.rename(columns={
        '日期': 'date',
        '开盘': 'open',
        '最高': 'high',
        '最低': 'low',
        '收盘': 'close',
        '成交量': 'volume',
    })

    # Set date as index
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    df = df[['open', 'high', 'low', 'close', 'volume']]

    # Create backtrader data feed
    data = bt.feeds.PandasData(
        dataname=df,
        name=symbol,
    )

    return data


def get_index_data(
    symbol: str,
    start_date: str,
    end_date: str,
) -> bt.feeds.PandasData:
    """
    Fetch index data for Chinese stock market indices.

    Args:
        symbol: Index code, e.g., '000001' (Shanghai Composite), '399001' (Shenzhen Component).
        start_date: Start date in 'YYYY-MM-DD' format.
        end_date: End date in 'YYYY-MM-DD' format.

    Returns:
        bt.feeds.PandasData: Backtrader data feed.

    Example:
        >>> data = get_index_data('000001', '2023-01-01', '2024-01-01')
        >>> cerebro.adddata(data)
    """
    import akshare as ak
    import pandas as pd

    start_str = start_date.replace('-', '')
    end_str = end_date.replace('-', '')

    # Fetch index data with appropriate prefix
    df = ak.stock_zh_index_daily(symbol=f"sh{symbol}" if symbol.startswith('0') else f"sz{symbol}")

    # Filter by date range
    df['date'] = pd.to_datetime(df['date'])
    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
    df = df.set_index('date')

    data = bt.feeds.PandasData(
        dataname=df,
        name=symbol,
    )

    return data
