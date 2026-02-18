"""
Market data API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime
import logging

from app.api.deps import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/kline", summary="Query K-line data")
async def get_kline_data(
    symbol: str = Query(..., description="Stock code, e.g., 000001.SZ"),
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    period: str = Query("daily", description="Period: daily/weekly/monthly"),
    current_user=Depends(get_current_user),
):
    """Fetch A-share kline OHLCV data via AkShare.

    Args:
        symbol: Stock code (e.g., 000001.SZ).
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        period: Data period (daily/weekly/monthly).

    Returns:
        A payload containing `kline` arrays and a flat `records` list for UI display.
    """
    import akshare as ak
    import pandas as pd

    code = symbol.split('.')[0]
    start_str = start_date.replace('-', '')
    end_str = end_date.replace('-', '')

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
            raise HTTPException(status_code=404, detail=f"No data retrieved for {symbol}")

        # akshare returns Chinese column names, rename to English
        df = df.rename(columns={
            '日期': 'date',      # Date
            '开盘': 'open',      # Open
            '最高': 'high',      # High
            '最低': 'low',       # Low
            '收盘': 'close',     # Close
            '成交量': 'volume',  # Volume
            '涨跌幅': 'change_pct',  # Change percentage
        })

        records = []
        dates = []
        ohlc = []
        volumes = []

        for _, row in df.iterrows():
            d = str(row['date'])
            dates.append(d)
            o = round(float(row['open']), 2)
            h = round(float(row['high']), 2)
            l = round(float(row['low']), 2)
            c = round(float(row['close']), 2)
            v = int(row['volume'])
            change = round(float(row.get('change_pct', 0)), 2)

            ohlc.append([o, c, l, h])
            volumes.append(v)
            records.append({
                'date': d, 'open': o, 'high': h, 'low': l,
                'close': c, 'volume': v, 'change': change,
            })

        return {
            "symbol": symbol,
            "count": len(records),
            "kline": {"dates": dates, "ohlc": ohlc, "volumes": volumes},
            "records": records,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch market data: {symbol}, {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
