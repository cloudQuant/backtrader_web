"""
Live trading service (Backtrader architecture).

Uses the standard Backtrader architecture: Cerebro + Store + Broker.
"""

from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Dynamically import backtrader project
BACKTRADER_PATH = Path.home() / "Documents" / "backtrader"
if BACKTRADER_PATH.exists():
    sys.path.insert(0, str(BACKTRADER_PATH))

try:
    import backtrader as bt

    BACKTRADER_AVAILABLE = True
except Exception as e:
    BACKTRADER_AVAILABLE = False
    logging.warning(f"backtrader not available: {e}")

logger = logging.getLogger(__name__)


class LiveTradingService:
    """Service for managing live trading strategies using Backtrader architecture.

    This service provides functionality to submit, manage, and monitor live trading
    strategies using the standard Backtrader architecture:

    - Cerebro.run() for executing live trading
    - Store for managing exchange connections
    - Broker for managing order execution
    - Observer for subscribing to events

    Attributes:
        tasks: Dictionary mapping task IDs to task information.
        cerebro_instances: Dictionary mapping task IDs to Cerebro instances.
    """

    def __init__(self):
        """Initialize the LiveTradingService.

        Creates empty dictionaries for tracking tasks and Cerebro instances.
        """
        self.tasks: dict[str, dict[str, Any]] = {}
        self.cerebro_instances: dict[str, bt.Cerebro] = {}

    async def submit_live_strategy(
        self,
        user_id: str,
        strategy_code: str,
        exchange: str,
        symbols: list[str],
        api_key: str,
        secret: str,
        initial_cash: float = 100000.0,
        strategy_params: dict[str, Any] | None = None,
        sandbox: bool = False,
        timeframe: str = "1d",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> str:
        """Submit a live trading strategy for execution.

        Args:
            user_id: The user ID submitting the strategy.
            strategy_code: The Python code containing the strategy implementation.
            exchange: The exchange to connect to (e.g., 'binance', 'okex', 'huobi').
            symbols: List of trading pairs to trade (e.g., ['BTC/USDT']).
            api_key: API key for exchange authentication.
            secret: Secret key for exchange authentication.
            initial_cash: Initial cash amount for the strategy. Defaults to 100000.0.
            strategy_params: Optional parameters to pass to the strategy.
            sandbox: Whether to use the exchange's sandbox/test environment.
            timeframe: The timeframe for data feeds (e.g., '1d', '1h', '5m').
            start_date: Optional start date for historical data.
            end_date: Optional end date for historical data.

        Returns:
            str: The unique task ID assigned to this live trading strategy.

        Raises:
            ImportError: If backtrader is not available.
        """
        if not BACKTRADER_AVAILABLE:
            raise ImportError("backtrader not available")
        try:
            from backtrader.feeds.ccxtdata import CCXTData
            from backtrader.observers.broker import Broker as BrokerObserver
            from backtrader.stores.ccxtstore import CCXTStore  # noqa: F811
        except ImportError as e:
            raise ImportError("CCXT live trading components are not available") from e

        # Generate unique task ID
        task_id = f"live-{user_id}-{datetime.now(timezone.utc).timestamp()}"

        # Run live trading in a background thread
        def _run_live_trading():
            try:
                logger.info(f"Starting live trading task: {task_id}")

                # Create Cerebro instance
                cerebro = bt.Cerebro()

                # Create data feeds for each symbol
                for symbol in symbols:
                    data_feed = CCXTData(
                        dataname=symbol,
                        name=exchange,
                        timeframe=timeframe,
                        fromdate=start_date,
                        todate=end_date,
                    )
                    cerebro.adddata(data_feed)

                # Create and add strategy
                strategy = self._load_strategy_from_code(strategy_code, strategy_params or {})
                cerebro.addstrategy(strategy)

                # Create Store and Broker
                store = CCXTStore(
                    exchange=exchange,
                    api_key=api_key,
                    secret=secret,
                    sandbox=sandbox,
                    config={"enableRateLimit": True},
                )

                broker = store.getbroker()
                cerebro.setbroker(broker)

                # Set initial cash
                cerebro.broker.setcash(initial_cash)

                # Add observer for event notifications
                cerebro.addobserver(BrokerObserver)

                # Store Cerebro instance for control
                self.cerebro_instances[task_id] = cerebro

                # Run live trading
                logger.info(f"Running live trading with Cerebro: {task_id}")
                cerebro.run()

            except Exception as e:
                logger.error(f"Live trading task error ({task_id}): {e}")
                self.tasks[task_id]["status"] = "failed"
                self.tasks[task_id]["error"] = str(e)

        # Start background thread
        thread = threading.Thread(target=_run_live_trading, daemon=True)
        thread.start()

        # Update task status
        self.tasks[task_id] = {
            "user_id": user_id,
            "status": "running",
            "config": {
                "exchange": exchange,
                "symbols": symbols,
                "initial_cash": initial_cash,
                "sandbox": sandbox,
            },
            "created_at": datetime.now(timezone.utc),
        }

        return task_id

    def _load_strategy_from_code(self, code: str, params: dict[str, Any]):
        """Load a Backtrader strategy class from executable Python code.

        Args:
            code: A string containing Python code with a Strategy class definition.
            params: Dictionary of parameters to set on the strategy.

        Returns:
            The loaded Backtrader Strategy class.

        Raises:
            ValueError: If no valid Strategy class is found in the code.
        """
        # Create temporary module
        import types

        module = types.ModuleType(f"strategy_{id(code)}")
        exec(code, module.__dict__)

        # Find strategy class
        for _name, obj in module.__dict__.items():
            if isinstance(obj, type) and issubclass(obj, bt.Strategy):
                # Set parameters
                if hasattr(obj, "params"):
                    for key, value in params.items():
                        obj.params._get(key).default = value
                return obj

        raise ValueError("No valid Strategy class found in the provided code")

    async def stop_live_strategy(
        self,
        user_id: str,
        task_id: str,
    ) -> bool:
        """Stop a running live trading strategy.

        Args:
            user_id: The user ID who owns the strategy.
            task_id: The unique task ID of the strategy to stop.

        Returns:
            bool: True if the strategy was stopped successfully, False otherwise.
        """
        if task_id not in self.cerebro_instances:
            return False

        # Get Cerebro instance
        cerebro = self.cerebro_instances[task_id]

        # Stop Cerebro
        cerebro.stop()

        # Cleanup
        del self.cerebro_instances[task_id]

        # Update task status
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "stopped"
            self.tasks[task_id]["stopped_at"] = datetime.now(timezone.utc)

        logger.info(f"Stopped live trading task: {task_id}")

        return True

    async def get_task_status(
        self,
        user_id: str,
        task_id: str,
    ) -> dict[str, Any] | None:
        """Get the current status of a live trading task.

        Args:
            user_id: The user ID who owns the strategy.
            task_id: The unique task ID to query.

        Returns:
            A dictionary containing task status including cash, value,
            positions, and orders. Returns None if the task doesn't exist.
        """
        if task_id not in self.tasks:
            return None

        task = self.tasks[task_id]

        # Get real-time status if Cerebro instance exists
        if task_id in self.cerebro_instances:
            cerebro = self.cerebro_instances[task_id]

            # Get account information
            cash = cerebro.broker.getcash()
            value = cerebro.broker.getvalue()

            # Get positions
            positions = []
            for data in cerebro.datas:
                position = cerebro.broker.getposition(data)
                if position:
                    positions.append(
                        {
                            "symbol": data._name,
                            "size": position.size,
                            "price": position.price,
                            "pnl": position.pnl,
                            "pnlcomm": position.pnlcomm,
                        }
                    )

            # Get orders
            orders = []
            for order in cerebro.broker.orders:
                orders.append(
                    {
                        "order_id": str(order.ref),
                        "symbol": order.data._name,
                        "ordtype": order.ordtypename(),
                        "side": order.ordtypename(),
                        "status": order.getstatusname(),
                        "size": order.size,
                        "price": order.created.price,
                    }
                )

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
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all live trading tasks for a user.

        Args:
            user_id: The user ID to list tasks for.
            status: Optional status filter (e.g., 'running', 'stopped', 'failed').

        Returns:
            A list of dictionaries containing task information including
            real-time status for active tasks.
        """
        tasks = []
        for task_id, task_info in self.tasks.items():
            if task_info["user_id"] != user_id:
                continue

            if status and task_info["status"] != status:
                continue

            # Get real-time status
            full_status = await self.get_task_status(user_id, task_id)
            if full_status:
                tasks.append(full_status)

        return tasks
