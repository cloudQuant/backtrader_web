"""
数据获取工具 - 使用akshare下载股票数据
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
    使用akshare获取A股数据并转换为backtrader数据源
    
    Args:
        symbol: 股票代码，如 '000001' 或 '000001.SZ'
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
        adjust: 复权方式，'qfq'前复权, 'hfq'后复权, ''不复权
        
    Returns:
        bt.feeds.PandasData: backtrader数据源
        
    Example:
        data = get_stock_data('000001', '2023-01-01', '2024-01-01')
        cerebro.adddata(data)
    """
    import akshare as ak
    import pandas as pd
    
    # 解析股票代码
    code = symbol.split('.')[0]
    
    # 格式化日期
    start_str = start_date.replace('-', '')
    end_str = end_date.replace('-', '')
    
    # 下载数据
    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=start_str,
        end_date=end_str,
        adjust=adjust
    )
    
    if df.empty:
        raise ValueError(f"未获取到股票 {symbol} 的数据")
    
    # 重命名列
    df = df.rename(columns={
        '日期': 'date',
        '开盘': 'open',
        '最高': 'high',
        '最低': 'low',
        '收盘': 'close',
        '成交量': 'volume',
    })
    
    # 设置索引
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    df = df[['open', 'high', 'low', 'close', 'volume']]
    
    # 创建backtrader数据源
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
    获取指数数据
    
    Args:
        symbol: 指数代码，如 '000001'(上证指数), '399001'(深证成指)
        start_date: 开始日期
        end_date: 结束日期
        
    Returns:
        bt.feeds.PandasData: backtrader数据源
    """
    import akshare as ak
    import pandas as pd
    
    start_str = start_date.replace('-', '')
    end_str = end_date.replace('-', '')
    
    df = ak.stock_zh_index_daily(symbol=f"sh{symbol}" if symbol.startswith('0') else f"sz{symbol}")
    
    # 筛选日期范围
    df['date'] = pd.to_datetime(df['date'])
    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
    df = df.set_index('date')
    
    data = bt.feeds.PandasData(
        dataname=df,
        name=symbol,
    )
    
    return data
