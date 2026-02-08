"""
回测服务 - 封装Backtrader回测逻辑
"""
import os
import uuid
import asyncio
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
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
from app.websocket_manager import manager as ws_manager, MessageType

logger = logging.getLogger(__name__)

# ---- 进程级单例状态（B001 fix）----
_running_tasks: Dict[str, asyncio.Task] = {}
_running_processes: Dict[str, subprocess.Popen] = {}


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
        
        # 创建异步任务并保存引用（用于取消）
        async_task = asyncio.create_task(self._execute_backtest(task.id, user_id, request))
        _running_tasks[task.id] = async_task
        
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
        执行回测任务 - 调用策略目录中的 run.py
        """
        task_work_dir = None
        tmp_base = None
        try:
            # 更新状态为运行中
            await self.task_repo.update(task_id, {"status": TaskStatus.RUNNING})
            await ws_manager.send_to_task(task_id, {
                "type": MessageType.PROGRESS, "task_id": task_id,
                "progress": 10, "message": "任务开始执行",
            })

            # 查找策略目录
            from app.services.strategy_service import STRATEGIES_DIR
            strategy_dir = STRATEGIES_DIR / request.strategy_id
            run_py = strategy_dir / "run.py"

            if not run_py.is_file():
                raise ValueError(f"策略 {request.strategy_id} 的 run.py 不存在")

            # [B003/O001] 将策略目录复制到独立临时目录，避免并发冲突
            # 创建 tmp_base/strategies/<strategy_id>/ 结构，使 BASE_DIR.parent.parent 能正确定位
            tmp_base = Path(tempfile.mkdtemp(prefix=f"bt_{task_id}_"))
            task_work_dir = tmp_base / "strategies" / request.strategy_id
            task_work_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(strategy_dir, task_work_dir, dirs_exist_ok=True)

            # 创建 datas 符号链接，使 resolve_data_path 能找到数据文件
            project_root = STRATEGIES_DIR.parent
            datas_src = project_root / "datas"
            datas_link = tmp_base / "datas"
            if datas_src.is_dir() and not datas_link.exists():
                os.symlink(str(datas_src), str(datas_link))

            # 清空临时目录的 logs
            tmp_logs = task_work_dir / "logs"
            if tmp_logs.is_dir():
                shutil.rmtree(tmp_logs)

            await ws_manager.send_to_task(task_id, {
                "type": MessageType.PROGRESS, "task_id": task_id,
                "progress": 20, "message": "正在写入配置参数...",
            })

            # 如果前端传入了自定义参数，写入临时目录的 config.yaml
            config_path = task_work_dir / "config.yaml"
            if self._has_custom_params(request):
                original_text = config_path.read_text(encoding="utf-8") if config_path.is_file() else None
                self._write_temp_config(config_path, request, original_text)

            # [B005] 移除 run.py 中的 assert 语句
            tmp_run_py = task_work_dir / "run.py"
            self._strip_asserts(tmp_run_py)

            await ws_manager.send_to_task(task_id, {
                "type": MessageType.PROGRESS, "task_id": task_id,
                "progress": 30, "message": "正在运行回测...",
            })

            # 调用 run.py（在临时目录中运行）
            result = await self._run_strategy_subprocess(task_work_dir, str(strategy_dir), task_id)

            await ws_manager.send_to_task(task_id, {
                "type": MessageType.PROGRESS, "task_id": task_id,
                "progress": 80, "message": "正在解析日志...",
            })

            # 解析临时目录中的 logs
            from app.services.log_parser_service import parse_all_logs
            log_result = parse_all_logs(task_work_dir)
            if not log_result:
                raise ValueError("回测完成但未找到日志文件")

            # 保存结果
            result_model = BacktestResultModel(
                task_id=task_id,
                total_return=log_result.get("total_return", 0),
                annual_return=log_result.get("annual_return", 0),
                sharpe_ratio=log_result.get("sharpe_ratio", 0),
                max_drawdown=log_result.get("max_drawdown", 0),
                win_rate=log_result.get("win_rate", 0),
                total_trades=log_result.get("total_trades", 0),
                profitable_trades=log_result.get("profitable_trades", 0),
                losing_trades=log_result.get("losing_trades", 0),
                equity_curve=log_result.get("equity_curve", []),
                equity_dates=log_result.get("equity_dates", []),
                drawdown_curve=log_result.get("drawdown_curve", []),
                trades=log_result.get("trades", []),
            )
            await self.result_repo.create(result_model)

            # [B009] 将日志目录路径保存到任务中，供后续分析使用
            # 把临时logs复制回原策略目录（以 task_id 命名），确保持久化
            persist_log_dir = strategy_dir / "logs" / f"task_{task_id}"
            tmp_log_dir = log_result.get("log_dir")
            if tmp_log_dir and Path(tmp_log_dir).is_dir():
                shutil.copytree(tmp_log_dir, persist_log_dir, dirs_exist_ok=True)

            # 更新任务状态
            await self.task_repo.update(task_id, {
                "status": TaskStatus.COMPLETED,
                "log_dir": str(persist_log_dir),
            })

            await ws_manager.send_to_task(task_id, {
                "type": MessageType.COMPLETED, "task_id": task_id,
                "progress": 100, "message": "回测完成",
                "data": {"total_return": log_result.get("total_return", 0)},
            })

            logger.info(f"回测完成: {task_id}, 收益率: {log_result.get('total_return', 0)}%")

        except asyncio.CancelledError:
            logger.info(f"回测已取消: {task_id}")
            await self.task_repo.update(task_id, {
                "status": TaskStatus.CANCELLED,
                "error_message": "用户取消任务",
            })
            await ws_manager.send_to_task(task_id, {
                "type": MessageType.CANCELLED, "task_id": task_id,
                "message": "任务已取消",
            })
        except Exception as e:
            logger.error(f"回测失败: {task_id}, {e}")
            await self.task_repo.update(task_id, {
                "status": TaskStatus.FAILED,
                "error_message": str(e),
            })
            await ws_manager.send_to_task(task_id, {
                "type": MessageType.FAILED, "task_id": task_id,
                "message": str(e),
            })
        finally:
            _running_tasks.pop(task_id, None)
            _running_processes.pop(task_id, None)
            # 清理临时工作目录（清理整个 tmp_base）
            cleanup_dir = tmp_base or task_work_dir
            if cleanup_dir and cleanup_dir.is_dir():
                try:
                    shutil.rmtree(cleanup_dir, ignore_errors=True)
                except Exception:
                    pass

    def _has_custom_params(self, request: BacktestRequest) -> bool:
        """检查是否有自定义参数需要覆盖 config.yaml"""
        return bool(request.params) or request.initial_cash != 100000 or request.commission != 0.001

    def _write_temp_config(self, config_path, request: BacktestRequest, original_text: str):
        """将前端传入的自定义参数临时写入 config.yaml"""
        import yaml
        config = {}
        if original_text:
            config = yaml.safe_load(original_text) or {}

        # 覆盖策略参数
        if request.params:
            if "params" not in config:
                config["params"] = {}
            config["params"].update(request.params)

        # 覆盖回测配置
        if "backtest" not in config:
            config["backtest"] = {}
        config["backtest"]["initial_cash"] = request.initial_cash
        config["backtest"]["commission"] = request.commission

        # 覆盖数据配置
        if request.symbol:
            if "data" not in config:
                config["data"] = {}
            config["data"]["symbol"] = request.symbol

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    @staticmethod
    def _strip_asserts(run_py: Path):
        """[B005] 移除 run.py 中的 assert 语句，避免参数变化后断言失败"""
        if not run_py.is_file():
            return
        code = run_py.read_text(encoding="utf-8")
        lines = code.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("assert ") or stripped.startswith("assert("):
                cleaned.append(line.replace(stripped, "pass  # assert removed for web backtest"))
            else:
                cleaned.append(line)
        run_py.write_text("\n".join(cleaned), encoding="utf-8")

    async def _run_strategy_subprocess(self, work_dir, original_strategy_dir: str = None, task_id: str = None) -> dict:
        """通过子进程运行策略的 run.py，支持 PID 跟踪用于取消"""
        python_exec = sys.executable
        run_py = work_dir / "run.py"

        # 准备环境变量
        from app.services.strategy_service import STRATEGIES_DIR
        project_root = STRATEGIES_DIR.parent
        env = dict(os.environ)
        env["BACKTRADER_DATA_DIR"] = str(project_root / "datas")
        orig_dir = original_strategy_dir or str(work_dir)
        env["PYTHONPATH"] = os.pathsep.join([orig_dir, str(work_dir), env.get("PYTHONPATH", "")])

        def _run():
            proc = subprocess.Popen(
                [python_exec, str(run_py)],
                cwd=str(work_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            # 记录 PID 用于取消
            if task_id:
                _running_processes[task_id] = proc
            stdout, stderr = proc.communicate(timeout=300)
            return proc.returncode, stdout, stderr

        returncode, stdout, stderr = await asyncio.get_event_loop().run_in_executor(None, _run)

        if returncode != 0:
            err_msg = stderr.strip().split("\n")[-1] if stderr else "未知错误"
            raise RuntimeError(f"run.py 执行失败: {err_msg}")

        return {"stdout": stdout, "stderr": stderr}
    
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
        支持: 1) strategies/目录模板（受信任，直接执行）
              2) 数据库中用户自定义策略（沙箱执行）
        """
        from app.services.strategy_service import get_template_by_id
        from app.utils.sandbox import execute_strategy_safely

        # 1) 先从文件系统策略模板查找（受信任代码，直接执行）
        template = get_template_by_id(strategy_id)
        if template:
            try:
                return self._load_strategy_from_code(template.code, params or {}, strategy_id)
            except Exception as e:
                logger.error(f"加载内置策略失败: {strategy_id}, {e}")
                raise ValueError(f"加载内置策略失败: {e}")

        # 2) 尝试从数据库查找用户策略（沙箱执行）
        code = None
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    strategy = pool.submit(
                        asyncio.run,
                        self.strategy_repo.get_by_id(strategy_id)
                    ).result(timeout=5)
            else:
                strategy = asyncio.run(self.strategy_repo.get_by_id(strategy_id))
            if strategy and strategy.code:
                code = strategy.code
        except Exception as e:
            logger.warning(f"从数据库查找策略失败: {strategy_id}, {e}")

        if not code:
            raise ValueError(f"未找到策略: {strategy_id}")

        try:
            strategy_class = execute_strategy_safely(code, params)
            return strategy_class
        except (ValueError, SyntaxError, NameError, AttributeError, ImportError, RuntimeError) as e:
            logger.error(f"策略代码执行失败: {e}")
            raise ValueError(f"策略代码执行失败: {e}")

    def _load_strategy_from_code(self, code: str, params: Dict[str, Any], strategy_id: str = None):
        """
        从受信任的代码加载策略类（内置模板专用，不经过沙箱）
        注入 __file__ 以便策略代码中 Path(__file__) / load_config() 正常工作
        """
        import sys
        import builtins
        import types as _types
        import backtrader as bt
        from app.services.strategy_service import STRATEGIES_DIR

        module_name = f"strategy_{strategy_id or id(code)}"
        module = _types.ModuleType(module_name)
        module.__dict__['__builtins__'] = builtins

        # 注册到 sys.modules，backtrader 元类需要通过 sys.modules[cls.__module__] 查找
        sys.modules[module_name] = module

        # 如果是文件系统策略，注入 __file__ 指向实际的 .py 文件
        if strategy_id:
            strategy_dir = STRATEGIES_DIR / strategy_id
            code_files = list(strategy_dir.glob("strategy_*.py"))
            if code_files:
                real_file = str(code_files[0])
                module.__dict__['__file__'] = real_file
                # 把策略目录加入 sys.path 以便相对导入
                str_dir = str(strategy_dir)
                if str_dir not in sys.path:
                    sys.path.insert(0, str_dir)

        exec(compile(code, module.__dict__.get('__file__', '<strategy>'), 'exec'), module.__dict__)

        # 查找 bt.Strategy 子类
        for name, obj in module.__dict__.items():
            if isinstance(obj, type) and issubclass(obj, bt.Strategy) and obj is not bt.Strategy:
                return obj

        raise ValueError("策略代码中未找到有效的 Strategy 类")
    
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
        
        # 获取资金曲线（使用 TimeReturn 分析器）
        equity_curve = []
        equity_dates = []
        drawdown_curve = []
        
        try:
            timereturn = strat.analyzers.timereturn.get_analysis()
            current_value = initial_cash
            peak = initial_cash
            
            for dt, ret in sorted(timereturn.items()):
                current_value = current_value * (1 + (ret or 0))
                date_str = dt.strftime("%Y-%m-%d") if isinstance(dt, datetime) else str(dt)
                equity_curve.append(round(current_value, 2))
                equity_dates.append(date_str)
                
                if current_value > peak:
                    peak = current_value
                dd = ((peak - current_value) / peak) * 100 if peak > 0 else 0
                drawdown_curve.append(round(dd, 2))
            
            logger.info(f"资金曲线: {len(equity_curve)} 个数据点")
        except Exception as e:
            logger.warning(f"解析资金曲线失败: {e}")
            equity_curve = [initial_cash, final_value]
            equity_dates = [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")]
            drawdown_curve = [0, max_drawdown]
        
        # 提取交易记录
        import backtrader as bt
        trade_records = []
        try:
            for data_trades in strat._trades.values():
                for tid, t_list in data_trades.items():
                    for t in t_list:
                        if t.isclosed:
                            dt_close = ""
                            try:
                                dt_close = bt.num2date(t.dtclose).strftime("%Y-%m-%d %H:%M:%S")
                            except Exception:
                                pass
                            trade_records.append({
                                "datetime": dt_close,
                                "direction": "buy" if t.long else "sell",
                                "price": round(t.price, 4),
                                "size": abs(t.size),
                                "value": round(abs(t.value), 2) if t.value else 0,
                                "commission": round(t.commission, 4),
                                "pnl": round(t.pnl, 2),
                                "pnlcomm": round(t.pnlcomm, 2),
                                "barlen": t.barlen or 0,
                            })
        except Exception as e:
            logger.warning(f"解析交易记录失败: {e}")
        
        logger.info(f"交易记录: {len(trade_records)} 条")
        
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
            "trades": trade_records,
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
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='timereturn')
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
    
    async def get_result(self, task_id: str, user_id: str = None) -> Optional[BacktestResult]:
        """获取回测结果（B002: 可选 user_id 鉴权）"""
        # 先查缓存
        cache_key = f"backtest:result:{task_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return BacktestResult(**cached)
        
        # 查询任务
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            return None
        
        # B002: 校验用户归属
        if user_id and task.user_id != user_id:
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
            trades=result_model.trades if result_model else [],
            created_at=task.created_at,
            error_message=task.error_message,
        )
        
        # 缓存结果
        if task.status == TaskStatus.COMPLETED:
            await self.cache.set(cache_key, result.model_dump(mode="json"), ttl=3600)
        
        return result
    
    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        """取消运行中的回测任务（B001: 使用进程级单例 + PID 终止子进程）"""
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.user_id != user_id:
            return False
        
        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        
        # 终止子进程（B001 fix）
        proc = _running_processes.pop(task_id, None)
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

        # 取消 asyncio 任务
        running = _running_tasks.pop(task_id, None)
        if running and not running.done():
            running.cancel()
        
        await self.task_repo.update(task_id, {
            "status": TaskStatus.CANCELLED,
            "error_message": "用户取消任务",
        })
        return True
    
    async def get_task_status(self, task_id: str, user_id: str = None) -> Optional[TaskStatus]:
        """获取任务状态（B002: 可选 user_id 鉴权）"""
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            return None
        if user_id and task.user_id != user_id:
            return None
        return TaskStatus(task.status)
    
    async def list_results(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> BacktestListResponse:
        """列出回测结果，支持排序"""
        tasks = await self.task_repo.list(
            filters={"user_id": user_id},
            skip=offset,
            limit=limit,
            order_by=sort_by,
            order_desc=sort_desc,
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
