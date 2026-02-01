"""
回测分析API路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import Optional
import json
import io
import csv
from datetime import datetime, timedelta

from app.schemas.analytics import (
    BacktestDetailResponse,
    KlineWithSignalsResponse,
    OptimizationResponse,
    MonthlyReturnsResponse,
    PerformanceMetrics,
)
from app.services.analytics_service import AnalyticsService
from app.services.backtest_service import BacktestService
from app.api.deps import get_current_user

router = APIRouter()


def get_analytics_service():
    return AnalyticsService()


def get_backtest_service():
    return BacktestService()


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
    
    peak = equity_values[0] if equity_values else 0
    
    for i, (date, value) in enumerate(zip(equity_dates, equity_values)):
        if value > peak:
            peak = value
        dd = (value - peak) / peak if peak > 0 else 0
        
        # 简单估算现金和持仓比例
        cash = value * 0.3
        position = value * 0.7
        
        equity_curve.append({
            'date': date if isinstance(date, str) else str(date),
            'total_assets': round(value, 2),
            'cash': round(cash, 2),
            'position_value': round(position, 2),
        })
        
        drawdown_curve.append({
            'date': date if isinstance(date, str) else str(date),
            'drawdown': round(dd, 6),
            'peak': round(peak, 2),
            'trough': round(value, 2),
        })
    
    # 转换交易记录
    trades = []
    signals = []
    raw_trades = result.trades or []
    
    for i, t in enumerate(raw_trades):
        trade = {
            'id': i + 1,
            'datetime': t.get('datetime', ''),
            'symbol': result.symbol,
            'direction': t.get('direction', 'buy'),
            'price': t.get('price', 0),
            'size': t.get('size', 0),
            'value': t.get('value', 0),
            'commission': t.get('commission', 0),
            'pnl': t.get('pnl'),
            'barlen': t.get('barlen'),
        }
        trades.append(trade)
        
        signals.append({
            'date': trade['datetime'][:10] if trade['datetime'] else '',
            'type': trade['direction'],
            'price': trade['price'],
            'size': trade['size'],
        })
    
    # 生成K线数据（从资金曲线反推价格变化）
    klines = []
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
            except:
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
    
    # 计算指标
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


@router.get("/{task_id}/optimization", response_model=OptimizationResponse)
async def get_optimization_results(
    task_id: str,
    sort_by: str = "sharpe_ratio",
    order: str = "desc",
    limit: int = 50,
    current_user=Depends(get_current_user),
):
    """
    获取参数优化结果
    
    支持按不同指标排序
    """
    # 生成模拟优化结果
    import random
    
    results = []
    for i in range(20):
        ma_short = random.choice([5, 10, 15, 20])
        ma_long = random.choice([30, 40, 50, 60])
        
        results.append({
            'params': {'ma_short': ma_short, 'ma_long': ma_long},
            'total_return': random.uniform(-0.1, 0.5),
            'max_drawdown': random.uniform(-0.3, -0.05),
            'sharpe_ratio': random.uniform(0.5, 2.5),
            'trade_count': random.randint(10, 50),
        })
    
    # 排序
    reverse = order == 'desc'
    results.sort(key=lambda x: x.get(sort_by, 0) or 0, reverse=reverse)
    
    # 添加排名
    for i, r in enumerate(results[:limit]):
        r['rank'] = i + 1
        r['is_best'] = i == 0
    
    return OptimizationResponse(
        task_id=task_id,
        parameters=['ma_short', 'ma_long'],
        results=[
            {
                'params': r['params'],
                'total_return': round(r['total_return'], 6),
                'max_drawdown': round(r['max_drawdown'], 6),
                'sharpe_ratio': round(r['sharpe_ratio'], 4) if r['sharpe_ratio'] else None,
                'trade_count': r['trade_count'],
                'rank': r['rank'],
                'is_best': r['is_best'],
            }
            for r in results[:limit]
        ],
        best=results[0] if results else None,
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
