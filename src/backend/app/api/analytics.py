"""
回测分析API路由
"""
from functools import lru_cache
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import Optional
import json
import io
import csv
from datetime import datetime, timedelta

from pathlib import Path

from app.schemas.analytics import (
    BacktestDetailResponse,
    KlineWithSignalsResponse,
    MonthlyReturnsResponse,
    PerformanceMetrics,
)
from app.services.analytics_service import AnalyticsService
from app.services.backtest_service import BacktestService
from app.services.log_parser_service import parse_data_log, parse_value_log, find_latest_log_dir
from app.services.strategy_service import STRATEGIES_DIR
from app.db.sql_repository import SQLRepository
from app.models.backtest import BacktestTask
from app.api.deps import get_current_user

router = APIRouter()


@lru_cache
def get_analytics_service():
    return AnalyticsService()


@lru_cache
def get_backtest_service():
    return BacktestService()


async def _resolve_log_dir(task_id: str, strategy_id: str) -> Path:
    """[B009] 解析任务专属日志目录，优先使用 DB 中记录的 log_dir，回退到 latest"""
    try:
        task_repo = SQLRepository(BacktestTask)
        task = await task_repo.get_by_id(task_id)
        if task and getattr(task, 'log_dir', None):
            p = Path(task.log_dir)
            if p.is_dir():
                return p
    except Exception:
        pass
    # 回退: 兼容旧任务
    strategy_dir = STRATEGIES_DIR / strategy_id
    return find_latest_log_dir(strategy_dir)


async def get_backtest_data(task_id: str, backtest_service: BacktestService):
    """从数据库获取真实回测结果"""
    result = await backtest_service.get_result(task_id)
    
    if not result:
        return None
    
    # 转换资金曲线格式
    equity_curve = []
    drawdown_curve = []
    
    equity_values = result.equity_curve or []
    equity_dates = result.equity_dates or []
    drawdown_values = result.drawdown_curve or []
    
    # [B009] 使用任务专属日志目录获取真实现金数据
    real_cash_map: dict = {}
    task_log_dir = await _resolve_log_dir(task_id, result.strategy_id)
    try:
        if task_log_dir:
            value_data = parse_value_log(task_log_dir)
            for d, c in zip(value_data.get('dates', []), value_data.get('cash_curve', [])):
                real_cash_map[d] = c
    except Exception:
        pass
    
    peak = equity_values[0] if equity_values else 0
    
    for i, (date, value) in enumerate(zip(equity_dates, equity_values)):
        if value > peak:
            peak = value
        dd = (value - peak) / peak if peak > 0 else 0
        
        date_str = date if isinstance(date, str) else str(date)
        cash = real_cash_map.get(date_str, value * 0.3)
        position = value - cash
        
        equity_curve.append({
            'date': date_str,
            'total_assets': round(value, 2),
            'cash': round(cash, 2),
            'position_value': round(position, 2),
        })
        
        drawdown_curve.append({
            'date': date_str,
            'drawdown': round(dd, 6),
            'peak': round(peak, 2),
            'trough': round(value, 2),
        })
    
    # [B009] 从任务专属日志目录获取真实K线数据（提前解析，供信号价格查找使用）
    klines = []
    log_indicators: dict = {}
    kline_close_map: dict = {}  # date -> close price
    try:
        if task_log_dir:
            kline_data = parse_data_log(task_log_dir)
            kline_dates = kline_data.get('dates', [])
            kline_ohlc = kline_data.get('ohlc', [])
            kline_volumes = kline_data.get('volumes', [])
            log_indicators = kline_data.get('indicators', {})
            for j in range(len(kline_dates)):
                ohlc = kline_ohlc[j] if j < len(kline_ohlc) else [0, 0, 0, 0]
                klines.append({
                    'date': kline_dates[j],
                    'open': round(ohlc[0], 4),
                    'high': round(ohlc[3], 4),
                    'low': round(ohlc[2], 4),
                    'close': round(ohlc[1], 4),
                    'volume': kline_volumes[j] if j < len(kline_volumes) else 0,
                })
                kline_close_map[kline_dates[j]] = round(ohlc[1], 4)
    except Exception:
        pass

    # 转换交易记录
    trades = []
    signals = []
    raw_trades = result.trades or []
    
    for i, t in enumerate(raw_trades):
        # t 可能是 TradeRecord pydantic 对象或 dict
        td = t.model_dump() if hasattr(t, 'model_dump') else (t if isinstance(t, dict) else {})
        trade = {
            'id': i + 1,
            'datetime': td.get('datetime', ''),
            'symbol': result.symbol,
            'direction': td.get('direction', 'buy'),
            'price': td.get('price', 0),
            'size': td.get('size', 0),
            'value': td.get('value', 0),
            'commission': td.get('commission', 0),
            'pnl': td.get('pnl') or td.get('pnlcomm'),
            'barlen': td.get('barlen'),
        }
        trades.append(trade)
        
        # 每笔已关闭的交易生成开仓和平仓两个信号
        # 优先使用K线收盘价作为信号价格，回退到交易均价
        is_long = trade['direction'] == 'buy'
        dtopen = td.get('dtopen', '')
        dtclose = td.get('dtclose', '') or trade['datetime']
        if dtopen:
            open_date = dtopen[:10]
            signals.append({
                'date': open_date,
                'type': 'buy' if is_long else 'sell',
                'price': kline_close_map.get(open_date, trade['price']),
                'size': trade['size'],
            })
        if dtclose:
            close_date = dtclose[:10]
            signals.append({
                'date': close_date,
                'type': 'sell' if is_long else 'buy',
                'price': kline_close_map.get(close_date, trade['price']),
                'size': trade['size'],
            })
    
    # 如果无法从日志获取，回退使用资金曲线反推
    if not klines:
        base_price = 10.0
        for i, date in enumerate(equity_dates):
            if i > 0 and equity_values[i-1] > 0:
                change = (equity_values[i] - equity_values[i-1]) / equity_values[i-1]
                base_price = base_price * (1 + change * 0.5)
            klines.append({
                'date': date if isinstance(date, str) else str(date),
                'open': round(base_price * 0.998, 2),
                'high': round(base_price * 1.01, 2),
                'low': round(base_price * 0.99, 2),
                'close': round(base_price, 2),
                'volume': 500000,
            })
    
    # 计算月度收益
    monthly_returns = {}
    if equity_dates and equity_values:
        month_start_value = equity_values[0]
        current_month = None
        
        for date, value in zip(equity_dates, equity_values):
            try:
                dt = datetime.strptime(date, '%Y-%m-%d') if isinstance(date, str) else date
                month_key = (dt.year, dt.month)
                
                if current_month != month_key:
                    if current_month and month_start_value > 0:
                        ret = (value - month_start_value) / month_start_value
                        monthly_returns[current_month] = round(ret, 6)
                    month_start_value = value
                    current_month = month_key
            except Exception:
                pass
        
        # 最后一个月
        if current_month and month_start_value > 0:
            ret = (equity_values[-1] - month_start_value) / month_start_value
            monthly_returns[current_month] = round(ret, 6)
    
    return {
        'task_id': task_id,
        'strategy_name': result.strategy_id or 'Unknown',
        'symbol': result.symbol or 'Unknown',
        'start_date': str(result.start_date)[:10] if result.start_date else '',
        'end_date': str(result.end_date)[:10] if result.end_date else '',
        'equity_curve': equity_curve,
        'drawdown_curve': drawdown_curve,
        'trades': trades,
        'signals': signals,
        'klines': klines,
        'log_indicators': log_indicators,
        'monthly_returns': monthly_returns,
        'created_at': str(result.created_at) if result.created_at else '',
    }


@router.get("/{task_id}/detail", response_model=BacktestDetailResponse)
async def get_backtest_detail(
    task_id: str,
    current_user=Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
):
    """
    获取回测详细结果
    
    包含绩效指标、资金曲线、回撤曲线、交易记录等
    """
    # 从数据库获取真实回测结果
    result = await get_backtest_data(task_id, backtest_service)
    
    if not result:
        raise HTTPException(status_code=404, detail="回测结果不存在")
    
    # 计算绩效指标
    metrics = service.calculate_metrics(result)
    
    # 处理数据
    equity_curve = service.process_equity_curve(result['equity_curve'])
    drawdown_curve = service.process_drawdown_curve(result['drawdown_curve'])
    trades = service.process_trades(result['trades'])
    
    return BacktestDetailResponse(
        task_id=task_id,
        strategy_name=result['strategy_name'],
        symbol=result['symbol'],
        start_date=result['start_date'],
        end_date=result['end_date'],
        metrics=metrics,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        trades=trades,
        created_at=result['created_at'],
    )


@router.get("/{task_id}/kline", response_model=KlineWithSignalsResponse)
async def get_kline_with_signals(
    task_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user=Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
):
    """
    获取K线数据及交易信号
    
    用于绘制带买卖点标记的K线图
    """
    result = await get_backtest_data(task_id, backtest_service)
    
    if not result:
        raise HTTPException(status_code=404, detail="回测结果不存在")
    
    klines = result['klines']
    signals = result['signals']
    
    # 日期筛选
    if start_date:
        klines = [k for k in klines if k['date'] >= start_date]
        signals = [s for s in signals if s['date'] >= start_date]
    if end_date:
        klines = [k for k in klines if k['date'] <= end_date]
        signals = [s for s in signals if s['date'] <= end_date]
    
    # 优先使用日志中的真实指标，没有则计算均线
    log_indicators = result.get('log_indicators', {})
    if log_indicators:
        indicators = log_indicators
    else:
        indicators = service.calculate_indicators(klines)
    
    return KlineWithSignalsResponse(
        symbol=result['symbol'],
        klines=[
            {
                'date': k['date'],
                'open': k['open'],
                'high': k['high'],
                'low': k['low'],
                'close': k['close'],
                'volume': k['volume'],
            }
            for k in klines
        ],
        signals=service.process_signals(signals),
        indicators=indicators,
    )


@router.get("/{task_id}/monthly-returns", response_model=MonthlyReturnsResponse)
async def get_monthly_returns(
    task_id: str,
    current_user=Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
):
    """
    获取月度收益数据
    
    用于绘制收益热力图
    """
    result = await get_backtest_data(task_id, backtest_service)
    
    if not result:
        raise HTTPException(status_code=404, detail="回测结果不存在")
    
    return service.process_monthly_returns(result['monthly_returns'])


@router.get("/{task_id}/optimization")
async def get_optimization_results(
    task_id: str,
    current_user=Depends(get_current_user),
):
    """
    获取参数优化结果

    该回测任务未关联优化结果。请使用 /api/v1/optimization/ 模块进行参数优化。
    """
    raise HTTPException(
        status_code=404,
        detail="该回测任务没有关联的优化结果。请通过「参数优化」功能执行优化。",
    )


@router.get("/{task_id}/export")
async def export_backtest_results(
    task_id: str,
    format: str = "csv",
    current_user=Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
):
    """
    导出回测结果
    """
    result = await get_backtest_data(task_id, backtest_service)
    
    if not result:
        raise HTTPException(status_code=404, detail="回测结果不存在")
    
    trades = result['trades']
    
    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=trades[0].keys() if trades else [])
        writer.writeheader()
        writer.writerows(trades)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=backtest_{task_id}.csv"
            }
        )
    
    elif format == "json":
        return StreamingResponse(
            iter([json.dumps(result, ensure_ascii=False, indent=2)]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=backtest_{task_id}.json"
            }
        )
    
    raise HTTPException(status_code=400, detail="不支持的导出格式")
