"""ORM models.

Importing this package registers all ORM models with ``Base.metadata`` so
schema creation helpers and tests can safely call ``create_all()``.
"""

from app.models.alerts import Alert, AlertNotification, AlertRule
from app.models.backtest import BacktestResultModel, BacktestTask
from app.models.comparison import Comparison, ComparisonShare
from app.models.optimization import OptimizationTask
from app.models.paper_trading import Account, Order, PaperTrade, Position
from app.models.permission import Permission, Role, user_roles
from app.models.strategy import Strategy
from app.models.strategy_version import (
    StrategyVersion,
    VersionBranch,
    VersionComparison,
    VersionRollback,
)
from app.models.user import RefreshToken, User
from app.models.workspace import StrategyUnit, Workspace

__all__ = [
    "Account",
    "Alert",
    "OptimizationTask",
    "AlertNotification",
    "AlertRule",
    "BacktestResultModel",
    "BacktestTask",
    "Comparison",
    "ComparisonShare",
    "Order",
    "PaperTrade",
    "Permission",
    "Position",
    "RefreshToken",
    "Role",
    "Strategy",
    "StrategyVersion",
    "User",
    "VersionBranch",
    "VersionComparison",
    "VersionRollback",
    "user_roles",
    "Workspace",
    "StrategyUnit",
]
