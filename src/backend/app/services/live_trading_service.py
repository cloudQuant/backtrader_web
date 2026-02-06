"""
实盘交易服务（正确版本 - 基于 backtrader 的完整架构）

使用 Cerebro + Store + Broker 的标准 backtrader 架构
"""
import sys
import asyncio
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import logging
from datetime import datetime

# 动态导入 backtrader 项目
BACKTRADER_PATH = Path.home() / "Documents" / "backtrader"
if BACKTRADER_PATH.exists():
    sys.path.insert(0, str(BACKTRADER_PATH))

try:
    import backtrader as bt
    from backtrader.brokers.ccxtbroker import CCXTBroker, CCXTStore
    from backtrader.feeds.ccxtdata import CCXTData
    from backtrader.observers.broker import BrokerObserver
    from backtrader.stores.ccxtstore import CCXTStore
    BACKTRADER_AVAILABLE = True
except ImportError as e:
    BACKTRADER_AVAILABLE = False
    logging.warning(f"backtrader not available: {e}")

logger = logging.getLogger(__name__)


class LiveTradingService:
    """
    实盘交易服务（正确版本）

    使用 backtrader 的标准架构：
    - Cerebro.run() 进行实盘交易
    - Store 管理交易所连接
    - Broker 管理订单执行
    - Observer 订阅事件
    """

    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}  # {task_id: task_info}
        self.cerebro_instances: Dict[str, bt.Cerebro] = {}  # {task_id: cerebro}

    async def submit_live_strategy(
        self,
        user_id: str,
        strategy_code: str,
        exchange: str,
        symbols: List[str],
        api_key: str,
        secret: str,
        initial_cash: float = 100000.0,
        strategy_params: Optional[Dict[str, Any]] = None,
        sandbox: bool = False,
        timeframe: str = "1d",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> str:
        """
        提交实盘交易策略

        Args:
            user_id: 用户 ID
            strategy_code: 策略代码
            exchange: 交易所（binance, okex, huobi 等）
            symbols: 交易对列表
            api_key: API Key
            secret: Secret Key
            initial_cash: 初始资金
            strategy_params: 策略参数
            sandbox: 是否测试环境
            timeframe: 时间周期
            start_date: 开始时间
            end_date: 结束时间

        Returns:
            str: 任务 ID
        """
        if not BACKTRADER_AVAILABLE:
            raise ImportError("backtrader not available")

        # 生成任务 ID
        task_id = f"live-{user_id}-{datetime.utcnow().timestamp()}"

        # 在后台线程中运行实盘交易
        def _run_live_trading():
            try:
                logger.info(f"Starting live trading task: {task_id}")

                # 创建 Cerebro 实例
                cerebro = bt.Cerebro()

                # 创建数据源
                for symbol in symbols:
                    data_feed = CCXTData(
                        dataname=symbol,
                        name=exchange,
                        timeframe=timeframe,
                        fromdate=start_date,
                        todate=end_date,
                    )
                    cerebro.adddata(data_feed)

                # 创建策略
                strategy = self._load_strategy_from_code(strategy_code, strategy_params or {})
                cerebro.addstrategy(strategy)

                # 创建 Store 和 Broker
                store = CCXTStore(
                    exchange=exchange,
                    api_key=api_key,
                    secret=secret,
                    sandbox=sandbox,
                    config={"enableRateLimit": True}
                )

                broker = store.getbroker()
                cerebro.setbroker(broker)

                # 设置初始资金
                cerebro.broker.setcash(initial_cash)

                # 添加观察者（用于获取事件）
                cerebro.addobserver(BrokerObserver)

                # 保存 Cerebro 实例用于控制
                self.cerebro_instances[task_id] = cerebro

                # 运行实盘交易
                logger.info(f"Running live trading with Cerebro: {task_id}")
                cerebro.run()

            except Exception as e:
                logger.error(f"Live trading task error ({task_id}): {e}")
                self.tasks[task_id]["status"] = "failed"
                self.tasks[task_id]["error"] = str(e)

        # 启动后台线程
        thread = threading.Thread(target=_run_live_trading, daemon=True)
        thread.start()

        # 更新任务状态
        self.tasks[task_id] = {
            "user_id": user_id,
            "status": "running",
            "config": {
                "exchange": exchange,
                "symbols": symbols,
                "initial_cash": initial_cash,
                "sandbox": sandbox,
            },
            "created_at": datetime.utcnow(),
        }

        return task_id

    def _load_strategy_from_code(self, code: str, params: Dict[str, Any]):
        """
        从代码加载策略

        Args:
            code: 策略代码
            params: 策略参数

        Returns:
            策略类
        """
        # 创建临时模块
        import types
        module = types.ModuleType(f"strategy_{id(code)}")
        exec(code, module.__dict__)

        # 查找策略类
        for name, obj in module.__dict__.items():
            if isinstance(obj, type) and issubclass(obj, bt.Strategy):
                # 设置参数
                if hasattr(obj, 'params'):
                    for key, value in params.items():
                        obj.params._get(key).default = value
                return obj

        raise ValueError("策略代码中未找到有效的 Strategy 类")

    async def stop_live_strategy(
        self,
        user_id: str,
        task_id: str,
    ) -> bool:
        """
        停止实盘交易策略

        Args:
            user_id: 用户 ID
            task_id: 任务 ID

        Returns:
            bool: 是否停止成功
        """
        if task_id not in self.cerebro_instances:
            return False

        # 获取 Cerebro 实例
        cerebro = self.cerebro_instances[task_id]

        # 停止 Cerebro
        cerebro.stop()

        # 清理
        del self.cerebro_instances[task_id]

        # 更新任务状态
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "stopped"
            self.tasks[task_id]["stopped_at"] = datetime.utcnow()

        logger.info(f"Stopped live trading task: {task_id}")

        return True

    async def get_task_status(
        self,
        user_id: str,
        task_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        获取任务状态

        Args:
            user_id: 用户 ID
            task_id: 任务 ID

        Returns:
            Dict: 状态信息
        """
        if task_id not in self.tasks:
            return None

        task = self.tasks[task_id]

        # 如果有 Cerebro 实例，获取实时状态
        if task_id in self.cerebro_instances:
            cerebro = self.cerebro_instances[task_id]
            
            # 获取账户信息
            cash = cerebro.broker.getcash()
            value = cerebro.broker.getvalue()

            # 获取持仓
            positions = []
            for data in cerebro.datas:
                position = cerebro.broker.getposition(data)
                if position:
                    positions.append({
                        "symbol": data._name,
                        "size": position.size,
                        "price": position.price,
                        "pnl": position.pnl,
                        "pnlcomm": position.pnlcomm,
                    })

            # 获取订单
            orders = []
            for order in cerebro.broker.orders:
                orders.append({
                    "order_id": str(order.ref),
                    "symbol": order.data._name,
                    "ordtype": order.ordtypename(),
                    "side": order.ordtypename(),
                    "status": order.getstatusname(),
                    "size": order.size,
                    "price": order.created.price,
                })

            return {
                "task_id": task_id,
                "status": task["status"],
                "cash": cash,
                "value": value,
                "positions": positions,
                "orders": orders,
            }

        return task

    async def list_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        列出所有任务

        Args:
            user_id: 用户 ID
            status: 状态筛选

        Returns:
            List: 任务列表
        """
        tasks = []
        for task_id, task_info in self.tasks.items():
            if task_info["user_id"] != user_id:
                continue

            if status and task_info["status"] != status:
                continue

            # 获取实时状态
            full_status = await self.get_task_status(user_id, task_id)
            if full_status:
                tasks.append(full_status)

        return tasks
