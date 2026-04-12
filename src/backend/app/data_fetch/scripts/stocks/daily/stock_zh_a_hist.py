"""
Minimal akshare stock history script for data management migration.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

SCRIPT_NAME = "A股日线行情"
DESCRIPTION = "获取 A 股复权日线行情并返回标准化 DataFrame"
TARGET_TABLE = "stock_daily"
ENTRYPOINT = "main"


def _default_dates() -> tuple[str, str]:
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=180)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")


def fetch_data(
    symbol: str = "000001",
    period: str = "daily",
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """Fetch A-share history and normalize columns."""
    normalized_start, normalized_end = _default_dates()
    dataframe = ak.stock_zh_a_hist(
        symbol=symbol,
        period=period,
        start_date=(start_date or normalized_start).replace("-", ""),
        end_date=(end_date or normalized_end).replace("-", ""),
        adjust=adjust,
        timeout=10,
    )
    if dataframe.empty:
        return dataframe
    dataframe = dataframe.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "turnover",
            "涨跌幅": "change_pct",
            "涨跌额": "change_amount",
            "换手率": "turnover_rate",
        }
    )
    dataframe["symbol"] = symbol
    dataframe["period"] = period
    return dataframe


def main(**kwargs) -> pd.DataFrame:
    """Default script entrypoint."""
    return fetch_data(**kwargs)
