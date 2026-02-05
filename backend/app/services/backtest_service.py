"""
回测服务 - 封装Backtrader回测逻辑
"""
import uuid
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

from app.models.backtest import BacktestTask, BacktestResultModel
from app.schemas.backtest import (
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
    BacktestListResponse,
    TaskStatus,
    TradeRecord,
)
from app.db.sql_repository import SQLRepository
from app.db.cache import get_cache

logger = logging.getLogger(__name__)


class BacktestService:
    """
    回测服务
    
    功能:
    1. 异步执行回测任务
    2. 回测结果存储
    3. 回测任务管理
    """
    
    def __init__(self):
        self.task_repo = SQLRepository(BacktestTask)
        self.result_repo = SQLRepository(BacktestResultModel)
        self.cache = get_cache()
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    async def run_backtest(
        self,
        user_id: str,
        request: BacktestRequest
    ) -> BacktestResponse:
        """
        运行回测（异步）
        
        Args:
            user_id: 用户ID
            request: 回测请求
            
        Returns:
            BacktestResponse: 包含task_id和状态
        """
        # 创建任务记录
        task = BacktestTask(
            user_id=user_id,
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            status=TaskStatus.PENDING,
            request_data=request.model_dump(mode="json"),
        )
        task = await self.task_repo.create(task)
        
        # 创建异步任务
        asyncio.create_task(self._execute_backtest(task.id, user_id, request))
        
        return BacktestResponse(
            task_id=task.id,
            status=TaskStatus.PENDING,
            message="回测任务已创建",
        )
    
    async def _execute_backtest(
        self,
        task_id: str,
        user_id: str,
        request: BacktestRequest
    ):
        """
        执行回测任务
        """
        try:
            # 更新状态为运行中
            await self.task_repo.update(task_id, {"status": TaskStatus.RUNNING})
            
            # 执行回测逻辑
            result = await self._run_backtrader(request)
            
            # 保存结果
            result_model = BacktestResultModel(
                task_id=task_id,
                total_return=result.get("total_return", 0),
                annual_return=result.get("annual_return", 0),
                sharpe_ratio=result.get("sharpe_ratio", 0),
                max_drawdown=result.get("max_drawdown", 0),
                win_rate=result.get("win_rate", 0),
                total_trades=result.get("total_trades", 0),
                profitable_trades=result.get("profitable_trades", 0),
                losing_trades=result.get("losing_trades", 0),
                equity_curve=result.get("equity_curve", []),
                equity_dates=result.get("equity_dates", []),
                drawdown_curve=result.get("drawdown_curve", []),
                trades=result.get("trades", []),
            )
            await self.result_repo.create(result_model)
            
            # 更新任务状态
            await self.task_repo.update(task_id, {"status": TaskStatus.COMPLETED})
            
            logger.info(f"回测完成: {task_id}")
            
        except Exception as e:
            logger.error(f"回测失败: {task_id}, {e}")
            await self.task_repo.update(task_id, {
                "status": TaskStatus.FAILED,
                "error_message": str(e),
            })
    
    def _get_stock_data(self, symbol: str, start_date: datetime, end_date: datetime):
        """
        使用akshare下载股票数据
        
        Args:
            symbol: 股票代码，如 000001.SZ 或 600000.SH
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            pandas.DataFrame: 包含OHLCV数据的DataFrame
        """
        import akshare as ak
        import pandas as pd
        
        # 解析股票代码，去掉后缀
        code = symbol.split('.')[0]
        
        # 格式化日期
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        try:
            # 使用akshare获取A股日线数据
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust="qfq"  # 前复权
            )
            
            if df.empty:
                raise ValueError(f"未获取到股票 {symbol} 的数据")
            
            # 重命名列以匹配backtrader格式
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume',
            })
            
            # 设置日期索引
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            
            # 只保留需要的列
            df = df[['open', 'high', 'low', 'close', 'volume']]
            
            logger.info(f"成功下载 {symbol} 数据，共 {len(df)} 条记录")
            return df
            
        except Exception as e:
            logger.error(f"下载股票数据失败: {symbol}, {e}")
            raise ValueError(f"下载股票数据失败: {e}")
    
    def _get_strategy_class(self, strategy_id: str, params: Dict[str, Any] = None):
        """
        根据策略ID获取策略类（安全版本）
        """
        from app.services.strategy_service import STRATEGY_TEMPLATES
        from app.utils.sandbox import execute_strategy_safely

        # 查找策略模板
        template = None
        for t in STRATEGY_TEMPLATES:
            if t.id == strategy_id:
                template = t
                break

        if not template:
            raise ValueError(f"未找到策略: {strategy_id}")

        # 使用安全沙箱执行策略代码
        try:
            strategy_class = execute_strategy_safely(template.code, params)
            return strategy_class
        except (ValueError, SyntaxError, NameError, AttributeError, ImportError, RuntimeError) as e:
            logger.error(f"策略代码执行失败: {e}")
            raise ValueError(f"策略代码执行失败: {e}")
    
    def _parse_backtest_results(
        self, 
        cerebro, 
        results, 
        initial_cash: float,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        解析backtrader回测结果
        """
        strat = results[0]
        
        # 获取最终资金
        final_value = cerebro.broker.getvalue()
        total_return = ((final_value - initial_cash) / initial_cash) * 100
        
        # 计算年化收益
        total_days = (end_date - start_date).days
        years = total_days / 365.0 if total_days > 0 else 1
        annual_return = (((final_value / initial_cash) ** (1 / years)) - 1) * 100 if years > 0 else 0
        
        # 解析分析器结果
        sharpe_ratio = 0.0
        try:
            sharpe_analysis = strat.analyzers.sharpe.get_analysis()
            sharpe_ratio = sharpe_analysis.get('sharperatio') or 0.0
            if sharpe_ratio is None:
                sharpe_ratio = 0.0
        except Exception:
            pass
        
        max_drawdown = 0.0
        try:
            drawdown_analysis = strat.analyzers.drawdown.get_analysis()
            max_drawdown = drawdown_analysis.get('max', {}).get('drawdown', 0.0) or 0.0
        except Exception:
            pass
        
        # 交易统计
        total_trades = 0
        profitable_trades = 0
        losing_trades = 0
        try:
            trade_analysis = strat.analyzers.trades.get_analysis()
            total_trades = trade_analysis.get('total', {}).get('total', 0) or 0
            profitable_trades = trade_analysis.get('won', {}).get('total', 0) or 0
            losing_trades = trade_analysis.get('lost', {}).get('total', 0) or 0
        except Exception:
            pass
        
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 获取资金曲线
        equity_curve = []
        equity_dates = []
        drawdown_curve = []
        
        try:
            # 从TimeReturn分析器获取每日收益
            returns_analysis = strat.analyzers.returns.get_analysis()
            
            # 计算资金曲线
            current_value = initial_cash
            peak = initial_cash
            
            for dt, ret in sorted(returns_analysis.items()):
                if isinstance(dt, datetime):
                    current_value = current_value * (1 + (ret or 0))
                    equity_curve.append(round(current_value, 2))
                    equity_dates.append(dt.strftime("%Y-%m-%d"))
                    
                    if current_value > peak:
                        peak = current_value
                    dd = ((peak - current_value) / peak) * 100 if peak > 0 else 0
                    drawdown_curve.append(round(dd, 2))
        except Exception as e:
            logger.warning(f"解析资金曲线失败: {e}")
            # 简化的资金曲线
            equity_curve = [initial_cash, final_value]
            equity_dates = [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")]
            drawdown_curve = [0, max_drawdown]
        
        return {
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "sharpe_ratio": round(sharpe_ratio, 2) if sharpe_ratio else 0.0,
            "max_drawdown": round(max_drawdown, 2),
            "win_rate": round(win_rate, 1),
            "total_trades": total_trades,
            "profitable_trades": profitable_trades,
            "losing_trades": losing_trades,
            "equity_curve": equity_curve,
            "equity_dates": equity_dates,
            "drawdown_curve": drawdown_curve,
            "trades": [],
        }

    async def _run_backtrader(self, request: BacktestRequest) -> Dict[str, Any]:
        """
        运行Backtrader回测（使用akshare真实数据）
        """
        import backtrader as bt
        import pandas as pd
        
        # 下载真实股票数据
        logger.info(f"开始下载股票数据: {request.symbol}, {request.start_date} - {request.end_date}")
        df = self._get_stock_data(request.symbol, request.start_date, request.end_date)
        
        # 创建Cerebro引擎
        cerebro = bt.Cerebro()
        
        # 添加数据
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        
        # 获取并添加策略
        strategy_class = self._get_strategy_class(request.strategy_id, request.params)
        
        # 设置策略参数
        if request.params:
            cerebro.addstrategy(strategy_class, **request.params)
        else:
            cerebro.addstrategy(strategy_class)
        
        # 设置初始资金和手续费
        cerebro.broker.setcash(request.initial_cash)
        cerebro.broker.setcommission(commission=request.commission)
        
        # 添加分析器
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.02)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # 运行回测
        logger.info(f"开始运行回测: {request.strategy_id}")
        results = cerebro.run()
        
        # 解析结果
        result = self._parse_backtest_results(
            cerebro, 
            results, 
            request.initial_cash,
            request.start_date,
            request.end_date
        )
        
        logger.info(f"回测完成，总收益率: {result['total_return']}%")
        return result
    
    async def get_result(self, task_id: str) -> Optional[BacktestResult]:
        """获取回测结果"""
        # 先查缓存
        cache_key = f"backtest:result:{task_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return BacktestResult(**cached)
        
        # 查询任务
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            return None
        
        # 查询结果
        results = await self.result_repo.list(filters={"task_id": task_id}, limit=1)
        result_model = results[0] if results else None
        
        result = BacktestResult(
            task_id=task.id,
            strategy_id=task.strategy_id,
            symbol=task.symbol,
            start_date=task.request_data.get("start_date") if task.request_data else datetime.now(),
            end_date=task.request_data.get("end_date") if task.request_data else datetime.now(),
            status=TaskStatus(task.status),
            total_return=result_model.total_return if result_model else 0,
            annual_return=result_model.annual_return if result_model else 0,
            sharpe_ratio=result_model.sharpe_ratio if result_model else 0,
            max_drawdown=result_model.max_drawdown if result_model else 0,
            win_rate=result_model.win_rate if result_model else 0,
            total_trades=result_model.total_trades if result_model else 0,
            profitable_trades=result_model.profitable_trades if result_model else 0,
            losing_trades=result_model.losing_trades if result_model else 0,
            equity_curve=result_model.equity_curve if result_model else [],
            equity_dates=result_model.equity_dates if result_model else [],
            drawdown_curve=result_model.drawdown_curve if result_model else [],
            trades=[],
            created_at=task.created_at,
            error_message=task.error_message,
        )
        
        # 缓存结果
        if task.status == TaskStatus.COMPLETED:
            await self.cache.set(cache_key, result.model_dump(mode="json"), ttl=3600)
        
        return result
    
    async def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            return None
        return TaskStatus(task.status)
    
    async def list_results(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> BacktestListResponse:
        """列出回测结果"""
        tasks = await self.task_repo.list(
            filters={"user_id": user_id},
            skip=offset,
            limit=limit
        )
        total = await self.task_repo.count(filters={"user_id": user_id})
        
        items = []
        for task in tasks:
            result = await self.get_result(task.id)
            if result:
                items.append(result)
        
        return BacktestListResponse(total=total, items=items)
    
    async def delete_result(self, task_id: str, user_id: str) -> bool:
        """删除回测结果"""
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.user_id != user_id:
            return False
        
        # 删除结果
        results = await self.result_repo.list(filters={"task_id": task_id}, limit=1)
        if results:
            await self.result_repo.delete(results[0].id)
        
        # 删除任务
        await self.task_repo.delete(task_id)
        
        # 清除缓存
        await self.cache.delete(f"backtest:result:{task_id}")
        
        return True
