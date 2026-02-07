"""
行情数据查询API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime
import logging

from app.api.deps import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/kline", summary="查询K线数据")
async def get_kline_data(
    symbol: str = Query(..., description="股票代码，如 000001.SZ"),
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    period: str = Query("daily", description="周期: daily/weekly/monthly"),
    current_user=Depends(get_current_user),
):
    """
    使用akshare查询真实A股K线数据

    返回OHLCV数据，可直接用于前端K线图和数据表格
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
        )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"未获取到 {symbol} 的数据")

        df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
            '涨跌幅': 'change_pct',
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
        logger.error(f"查询行情数据失败: {symbol}, {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")
