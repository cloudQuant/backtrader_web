"""ORM models.

Importing this package registers all ORM models with ``Base.metadata`` so
schema creation helpers and tests can safely call ``create_all()``.
"""

from app.models.ai_call_log import AICallLog
from app.models.akshare_mgmt import (
    DataInterface,
    DataScript,
    DataTable,
    InterfaceCategory,
    InterfaceParameter,
    ScheduledTask,
    TaskExecution,
)
from app.models.alerts import Alert, AlertNotification, AlertRule
from app.models.audit_record import AuditRecord
from app.models.backtest import BacktestResultModel, BacktestTask
from app.models.comparison import Comparison, ComparisonShare
from app.models.knowledge_base import (
    ChatConversation,
    ChatMessage,
    DocumentChunk,
    KBDocument,
    KnowledgeBase,
    ModelConfig,
    ModelUsageLog,
)
from app.models.optimization import OptimizationTask
from app.models.overfitting_result import OverfittingResultModel
from app.models.paper_trading import Account, Order, PaperTrade, Position
from app.models.permission import Permission, Role, user_roles
from app.models.prompt_template import PromptTemplate
from app.models.strategy import Strategy
from app.models.strategy_explanation import StrategyExplanationModel
from app.models.strategy_score import StrategyScoreModel
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
    "AICallLog",
    "Alert",
    "AlertNotification",
    "AlertRule",
    "AuditRecord",
    "BacktestResultModel",
    "BacktestTask",
    "Comparison",
    "ComparisonShare",
    "DataInterface",
    "DataScript",
    "DataTable",
    "InterfaceCategory",
    "InterfaceParameter",
    "KnowledgeBase",
    "KBDocument",
    "DocumentChunk",
    "ChatConversation",
    "ChatMessage",
    "ModelConfig",
    "ModelUsageLog",
    "Order",
    "OptimizationTask",
    "OverfittingResultModel",
    "PaperTrade",
    "Permission",
    "Position",
    "RefreshToken",
    "Role",
    "PromptTemplate",
    "ScheduledTask",
    "Strategy",
    "StrategyExplanationModel",
    "StrategyScoreModel",
    "StrategyVersion",
    "TaskExecution",
    "User",
    "VersionBranch",
    "VersionComparison",
    "VersionRollback",
    "user_roles",
    "Workspace",
    "StrategyUnit",
]
