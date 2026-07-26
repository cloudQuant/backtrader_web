"""ORM models.

Importing this package registers all ORM models with ``Base.metadata`` so
schema creation helpers and tests can safely call ``create_all()``.
"""

from app.models.ai_call_log import AICallLog
from app.models.ai_research import (
    AIStrategyResearchVersion,
    AIStrategyResearchVersionComparison,
    InvestmentMandate,
    ResearchPipelineEvent,
)
from app.models.ai_trading import AITradingLog
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
from app.models.broker_profile import BrokerConnectionProfile
from app.models.comparison import Comparison, ComparisonShare
from app.models.data_governance import (
    DgEndpoint,
    DgEndpointParam,
    DgIngestJob,
    DgProvider,
    DgQualityRule,
)
from app.models.knowledge_base import (
    ChatConversation,
    ChatMessage,
    DocumentChunk,
    KBDocument,
    KnowledgeBase,
    ModelConfig,
    ModelUsageLog,
)
from app.models.market_data_trust import (
    AssetSpecModel,
    MarketDataCoverageModel,
    MarketDataQualityReportModel,
    RobustnessTestResultModel,
)
from app.models.news_intelligence import NewsAnalysisModel, NewsArticleModel, NewsSourceModel
from app.models.optimization import OptimizationTask
from app.models.overfitting_result import OverfittingResultModel
from app.models.paper_runtime import (
    LiveHandoffReview,
    PaperEquitySnapshot,
    PaperReviewReport,
    RiskRule,
)
from app.models.paper_trading import Account, Order, PaperTrade, Position
from app.models.permission import Permission, Role, user_roles
from app.models.portfolio_ledger import (
    PortfolioLedgerImportModel,
    PortfolioLedgerModel,
    PortfolioLedgerSnapshotModel,
    PortfolioLedgerTransactionModel,
)
from app.models.prompt_template import PromptTemplate
from app.models.scanner_plan import ScannerPlanModel, ScannerPlanRunModel
from app.models.stock_analysis import (
    StockAnalysisExportModel,
    StockAnalysisReportModel,
    StockAnalysisTaskModel,
)
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
    "AITradingLog",
    "AIStrategyResearchVersion",
    "AIStrategyResearchVersionComparison",
    "Alert",
    "AlertNotification",
    "AlertRule",
    "AssetSpecModel",
    "AuditRecord",
    "BacktestResultModel",
    "BacktestTask",
    "BrokerConnectionProfile",
    "Comparison",
    "ComparisonShare",
    "DataInterface",
    "DgEndpoint",
    "DgEndpointParam",
    "DgIngestJob",
    "DgProvider",
    "DgQualityRule",
    "DataScript",
    "DataTable",
    "InterfaceCategory",
    "InterfaceParameter",
    "InvestmentMandate",
    "MarketDataCoverageModel",
    "MarketDataQualityReportModel",
    "KnowledgeBase",
    "KBDocument",
    "DocumentChunk",
    "ChatConversation",
    "ChatMessage",
    "ModelConfig",
    "ModelUsageLog",
    "NewsAnalysisModel",
    "NewsArticleModel",
    "NewsSourceModel",
    "Order",
    "LiveHandoffReview",
    "PaperEquitySnapshot",
    "PaperReviewReport",
    "OptimizationTask",
    "OverfittingResultModel",
    "PaperTrade",
    "Permission",
    "Position",
    "PortfolioLedgerImportModel",
    "PortfolioLedgerModel",
    "PortfolioLedgerSnapshotModel",
    "PortfolioLedgerTransactionModel",
    "RefreshToken",
    "ResearchPipelineEvent",
    "Role",
    "RiskRule",
    "RobustnessTestResultModel",
    "PromptTemplate",
    "ScannerPlanModel",
    "ScannerPlanRunModel",
    "ScheduledTask",
    "Strategy",
    "StrategyExplanationModel",
    "StrategyScoreModel",
    "StockAnalysisExportModel",
    "StockAnalysisReportModel",
    "StockAnalysisTaskModel",
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
