"""
回测结果对比服务测试

测试：
- ComparisonService 类
- create_comparison 方法
- _generate_comparison_data 方法
- _compare_metrics 方法
- _find_best_metrics 方法
- _compare_equity 方法
- _compare_trades 方法
- _compare_drawdown 方法
- update_comparison 方法
- delete_comparison 方法
- get_comparison 方法
- list_comparisons 方法
- _to_response 方法
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime

from app.services.comparison_service import ComparisonService
from app.models.comparison import Comparison, ComparisonType


class TestComparisonServiceInitialization:
    """测试ComparisonService初始化"""

    def test_initialization(self):
        """测试服务初始化"""
        service = ComparisonService()

        assert service.comparison_repo is not None
        assert service.backtest_service is not None


@pytest.mark.asyncio
class TestCreateComparison:
    """测试创建对比"""

    async def test_create_comparison_basic(self):
        """测试基础创建"""
        service = ComparisonService()

        mock_result = Mock()
        mock_result.strategy_id = "SMACross"
        mock_result.symbol = "BTC/USDT"
        mock_result.total_return = 0.15
        mock_result.annual_return = 0.20
        mock_result.sharpe_ratio = 1.5
        mock_result.max_drawdown = -0.10
        mock_result.win_rate = 0.60
        mock_result.total_trades = 50
        mock_result.equity_curve = [100000, 105000, 103000, 110000]
        mock_result.equity_dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
        mock_result.drawdown_curve = [0, -0.02, -0.05, -0.03]
        mock_result.trades = []

        service.backtest_service = AsyncMock()
        service.backtest_service.get_result = AsyncMock(return_value=mock_result)

        mock_comparison = Mock()
        mock_comparison.id = "comp_123"
        mock_comparison.user_id = "user_123"
        mock_comparison.name = "测试对比"
        mock_comparison.description = None
        mock_comparison.type = ComparisonType.METRICS
        mock_comparison.backtest_task_ids = ["task1", "task2"]
        mock_comparison.comparison_data = {}
        mock_comparison.is_public = False
        mock_comparison.is_favorite = False
        mock_comparison.created_at = datetime.now()
        mock_comparison.updated_at = datetime.now()

        service.comparison_repo = AsyncMock()
        service.comparison_repo.create = AsyncMock(return_value=mock_comparison)

        result = await service.create_comparison(
            user_id="user_123",
            name="测试对比",
            backtest_task_ids=["task1", "task2"]
        )

        assert result is not None

    async def test_create_comparison_with_invalid_task(self):
        """测试包含无效任务ID"""
        service = ComparisonService()

        service.backtest_service = AsyncMock()
        service.backtest_service.get_result = AsyncMock(return_value=None)

        with pytest.raises(ValueError) as exc_info:
            await service.create_comparison(
                user_id="user_123",
                name="测试对比",
                backtest_task_ids=["invalid_task"]
            )

        assert "不存在" in str(exc_info.value)


@pytest.mark.asyncio
class TestGenerateComparisonData:
    """测试生成对比数据"""

    async def test_generate_metrics_comparison(self):
        """测试生成指标对比"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "strategy_id": "SMACross",
                "symbol": "BTC/USDT",
                "total_return": 0.15,
                "annual_return": 0.20,
                "sharpe_ratio": 1.5,
                "max_drawdown": -0.10,
                "win_rate": 0.60,
                "total_trades": 50,
                "equity_curve": [100000, 105000],
                "equity_dates": ["2024-01-01", "2024-01-02"],
                "drawdown_curve": [0, -0.02],
                "trades": [],
            },
            "task2": {
                "strategy_id": "EMACross",
                "symbol": "BTC/USDT",
                "total_return": 0.12,
                "annual_return": 0.18,
                "sharpe_ratio": 1.2,
                "max_drawdown": -0.08,
                "win_rate": 0.55,
                "total_trades": 40,
                "equity_curve": [100000, 102000],
                "equity_dates": ["2024-01-01", "2024-01-02"],
                "drawdown_curve": [0, -0.01],
                "trades": [],
            }
        }

        result = await service._generate_comparison_data(
            backtest_results, ComparisonType.METRICS
        )

        assert "metrics_comparison" in result
        assert "best_metrics" in result
        assert result["type"] == ComparisonType.METRICS

    async def test_generate_equity_comparison(self):
        """测试生成资金曲线对比"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "equity_curve": [100000, 105000],
                "equity_dates": ["2024-01-01", "2024-01-02"],
            }
        }

        result = await service._generate_comparison_data(
            backtest_results, ComparisonType.EQUITY
        )

        assert "equity_comparison" in result
        assert "dates" in result["equity_comparison"]
        assert "curves" in result["equity_comparison"]

    async def test_generate_trades_comparison(self):
        """测试生成交易对比"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "total_trades": 50,
                "profitable_trades": 30,
                "losing_trades": 20,
                "win_rate": 0.6,
            }
        }

        result = await service._generate_comparison_data(
            backtest_results, ComparisonType.TRADES
        )

        assert "trades_comparison" in result
        assert "trade_counts" in result["trades_comparison"]
        assert "win_rates" in result["trades_comparison"]

    async def test_generate_drawdown_comparison(self):
        """测试生成回撤对比"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "max_drawdown": -0.10,
                "drawdown_curve": [0, -0.05, -0.10],
            }
        }

        result = await service._generate_comparison_data(
            backtest_results, ComparisonType.DRAWDOWN
        )

        assert "drawdown_comparison" in result
        assert "max_drawdowns" in result["drawdown_comparison"]
        assert "drawdown_curves" in result["drawdown_comparison"]


class TestCompareMetrics:
    """测试指标对比"""

    def test_compare_metrics(self):
        """测试指标对比计算"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "total_return": 0.15,
                "annual_return": 0.20,
                "sharpe_ratio": 1.5,
                "max_drawdown": -0.10,
                "win_rate": 0.60,
            },
            "task2": {
                "total_return": 0.12,
                "annual_return": 0.18,
                "sharpe_ratio": 1.2,
                "max_drawdown": -0.08,
                "win_rate": 0.55,
            }
        }

        result = service._compare_metrics(backtest_results)

        assert "total_return" in result
        assert "annual_return" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown" in result
        assert "win_rate" in result
        assert result["total_return"]["task1"] == 0.15
        assert result["total_return"]["task2"] == 0.12


class TestFindBestMetrics:
    """测试查找最优指标"""

    def test_find_best_metrics(self):
        """测试查找最优指标"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "total_return": 0.15,
                "annual_return": 0.20,
                "sharpe_ratio": 1.5,
                "max_drawdown": -0.10,
                "win_rate": 0.60,
            },
            "task2": {
                "total_return": 0.18,
                "annual_return": 0.22,
                "sharpe_ratio": 1.3,
                "max_drawdown": -0.08,
                "win_rate": 0.65,
            }
        }

        result = service._find_best_metrics(backtest_results)

        assert result["total_return"]["task_id"] == "task2"  # 0.18 > 0.15
        # max_drawdown: 实现找最小的值（最负的），所以是task1(-0.10)
        assert result["max_drawdown"]["task_id"] == "task1"
        assert result["max_drawdown"]["value"] == -0.10
        assert result["win_rate"]["task_id"] == "task2"  # 0.65 > 0.60

    def test_find_best_metrics_single_task(self):
        """测试单个任务的最优指标"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "total_return": 0.15,
                "annual_return": 0.20,
                "sharpe_ratio": 1.5,
                "max_drawdown": -0.10,
                "win_rate": 0.60,
            }
        }

        result = service._find_best_metrics(backtest_results)

        assert result["total_return"]["task_id"] == "task1"
        assert result["total_return"]["value"] == 0.15


class TestCompareEquity:
    """测试资金曲线对比"""

    def test_compare_equity(self):
        """测试资金曲线对比"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "equity_curve": [100000, 105000, 103000],
                "equity_dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
            },
            "task2": {
                "equity_curve": [100000, 102000, 101000],
                "equity_dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
            }
        }

        result = service._compare_equity(backtest_results)

        assert "dates" in result
        assert "curves" in result
        assert len(result["dates"]) == 3
        assert "task1" in result["curves"]
        assert "task2" in result["curves"]

    def test_compare_equity_date_alignment(self):
        """测试日期对齐"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "equity_curve": [100000, 105000],
                "equity_dates": ["2024-01-01", "2024-01-03"],
            },
            "task2": {
                "equity_curve": [100000, 102000],
                "equity_dates": ["2024-01-01", "2024-01-02"],
            }
        }

        result = service._compare_equity(backtest_results)

        # 应该包含所有唯一日期
        assert "2024-01-01" in result["dates"]
        assert "2024-01-02" in result["dates"]
        assert "2024-01-03" in result["dates"]


class TestCompareTrades:
    """测试交易对比"""

    def test_compare_trades(self):
        """测试交易对比"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "total_trades": 50,
                "profitable_trades": 30,
                "losing_trades": 20,
                "win_rate": 0.6,
            },
            "task2": {
                "total_trades": 40,
                "profitable_trades": 22,
                "losing_trades": 18,
                "win_rate": 0.55,
            }
        }

        result = service._compare_trades(backtest_results)

        assert "trade_counts" in result
        assert "win_rates" in result
        assert result["trade_counts"]["task1"]["total"] == 50
        assert result["trade_counts"]["task1"]["profitable"] == 30
        assert result["trade_counts"]["task1"]["losing"] == 20
        assert result["win_rates"]["task1"] == 0.6


class TestCompareDrawdown:
    """测试回撤对比"""

    def test_compare_drawdown(self):
        """测试回撤对比"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "max_drawdown": -0.10,
                "drawdown_curve": [0, -0.05, -0.10, -0.08],
            },
            "task2": {
                "max_drawdown": -0.08,
                "drawdown_curve": [0, -0.03, -0.08, -0.05],
            }
        }

        result = service._compare_drawdown(backtest_results)

        assert "max_drawdowns" in result
        assert "drawdown_curves" in result
        assert result["max_drawdowns"]["task1"] == -0.10
        assert result["max_drawdowns"]["task2"] == -0.08


@pytest.mark.asyncio
class TestUpdateComparison:
    """测试更新对比"""

    async def test_update_comparison_name(self):
        """测试更新名称"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.id = "comp_123"
        mock_comparison.user_id = "user_123"
        mock_comparison.name = "旧名称"
        mock_comparison.description = None
        mock_comparison.is_public = False
        mock_comparison.is_favorite = False  # 添加布尔值
        mock_comparison.type = ComparisonType.METRICS
        mock_comparison.backtest_task_ids = ["task1"]
        mock_comparison.comparison_data = {}
        mock_comparison.created_at = datetime.now()
        mock_comparison.updated_at = datetime.now()

        # 模拟repo
        async def mock_get(rid):
            return mock_comparison

        async def mock_up(rid, data):
            # 更新mock对象
            for k, v in data.items():
                setattr(mock_comparison, k, v)
            return mock_comparison

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = mock_get
        service.comparison_repo.update = mock_up

        mock_update_data = Mock()
        mock_update_data.name = "新名称"
        mock_update_data.description = None
        mock_update_data.is_public = False  # 使用布尔值而不是None
        mock_update_data.backtest_task_ids = None
        mock_update_data.exclude_fields = []  # 添加exclude_fields属性

        result = await service.update_comparison("comp_123", "user_123", mock_update_data)

        assert result is not None

    async def test_update_comparison_not_owner(self):
        """测试非所有者更新"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.user_id = "other_user"

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=mock_comparison)

        mock_update_data = Mock()
        mock_update_data.name = "新名称"
        mock_update_data.description = None
        mock_update_data.is_public = None
        mock_update_data.backtest_task_ids = None

        result = await service.update_comparison("comp_123", "user_123", mock_update_data)

        assert result is None

    async def test_update_comparison_not_found(self):
        """测试更新不存在的对比"""
        service = ComparisonService()

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=None)

        mock_update_data = Mock()
        mock_update_data.name = "新名称"
        mock_update_data.description = None
        mock_update_data.is_public = None
        mock_update_data.backtest_task_ids = None

        result = await service.update_comparison("comp_123", "user_123", mock_update_data)

        assert result is None


@pytest.mark.asyncio
class TestDeleteComparison:
    """测试删除对比"""

    async def test_delete_comparison_success(self):
        """测试成功删除"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.user_id = "user_123"

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=mock_comparison)
        service.comparison_repo.delete = AsyncMock(return_value=True)

        result = await service.delete_comparison("comp_123", "user_123")

        assert result is True

    async def test_delete_comparison_not_owner(self):
        """测试非所有者删除"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.user_id = "other_user"

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=mock_comparison)

        result = await service.delete_comparison("comp_123", "user_123")

        assert result is False

    async def test_delete_comparison_not_found(self):
        """测试删除不存在的对比"""
        service = ComparisonService()

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.delete_comparison("comp_123", "user_123")

        assert result is False


@pytest.mark.asyncio
class TestGetComparison:
    """测试获取对比"""

    async def test_get_comparison_success(self):
        """测试成功获取"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.id = "comp_123"
        mock_comparison.user_id = "user_123"
        mock_comparison.name = "测试对比"
        mock_comparison.description = None
        mock_comparison.type = ComparisonType.METRICS
        mock_comparison.backtest_task_ids = []
        mock_comparison.comparison_data = {}
        mock_comparison.is_favorite = False
        mock_comparison.is_public = False
        mock_comparison.created_at = datetime.now()
        mock_comparison.updated_at = datetime.now()

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=mock_comparison)

        result = await service.get_comparison("comp_123", "user_123")

        assert result is not None

    async def test_get_comparison_not_found(self):
        """测试获取不存在的对比"""
        service = ComparisonService()

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.get_comparison("comp_123", "user_123")

        assert result is None

    async def test_get_comparison_private_not_owner(self):
        """测试获取私有对比但非所有者"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.user_id = "other_user"
        mock_comparison.is_public = False

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=mock_comparison)

        result = await service.get_comparison("comp_123", "user_123")

        assert result is None

    async def test_get_comparison_public_accessible(self):
        """测试公开对比可被其他用户访问"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.user_id = "other_user"
        mock_comparison.is_public = True
        mock_comparison.id = "comp_123"
        mock_comparison.name = "公开对比"
        mock_comparison.description = None
        mock_comparison.type = ComparisonType.METRICS
        mock_comparison.backtest_task_ids = []
        mock_comparison.comparison_data = {}
        mock_comparison.is_favorite = False
        mock_comparison.created_at = datetime.now()
        mock_comparison.updated_at = datetime.now()

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=mock_comparison)

        result = await service.get_comparison("comp_123", "user_123")

        assert result is not None


@pytest.mark.asyncio
class TestListComparisons:
    """测试列出对比"""

    async def test_list_comparisons_default(self):
        """测试默认列出用户对比"""
        service = ComparisonService()

        mock_comparisons = []
        service.comparison_repo = AsyncMock()
        service.comparison_repo.list = AsyncMock(return_value=mock_comparisons)
        service.comparison_repo.count = AsyncMock(return_value=0)

        comparisons, total = await service.list_comparisons("user_123")

        assert comparisons == []
        assert total == 0

    async def test_list_comparisons_public_only(self):
        """测试只列出公开对比"""
        service = ComparisonService()

        mock_comparisons = []
        service.comparison_repo = AsyncMock()
        service.comparison_repo.list = AsyncMock(return_value=mock_comparisons)
        service.comparison_repo.count = AsyncMock(return_value=0)

        comparisons, total = await service.list_comparisons("user_123", is_public=True)

        assert comparisons == []
        assert total == 0

    async def test_list_comparisons_private_only(self):
        """测试只列出私有对比"""
        service = ComparisonService()

        mock_comparisons = []
        service.comparison_repo = AsyncMock()
        service.comparison_repo.list = AsyncMock(return_value=mock_comparisons)
        service.comparison_repo.count = AsyncMock(return_value=0)

        comparisons, total = await service.list_comparisons("user_123", is_public=False)

        assert comparisons == []
        assert total == 0

    async def test_list_comparisons_with_pagination(self):
        """测试分页"""
        service = ComparisonService()

        mock_comparisons = []
        service.comparison_repo = AsyncMock()
        service.comparison_repo.list = AsyncMock(return_value=mock_comparisons)
        service.comparison_repo.count = AsyncMock(return_value=0)

        comparisons, total = await service.list_comparisons("user_123", limit=10, offset=20)

        assert comparisons == []
        assert total == 0


class TestToResponse:
    """测试转换为响应模型"""

    def test_to_response(self):
        """测试转换"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.id = "comp_123"
        mock_comparison.user_id = "user_123"
        mock_comparison.name = "测试对比"
        mock_comparison.description = "测试描述"
        mock_comparison.type = ComparisonType.METRICS
        mock_comparison.backtest_task_ids = ["task1", "task2"]
        mock_comparison.comparison_data = {"metrics": {}}
        mock_comparison.is_favorite = True
        mock_comparison.is_public = False
        mock_comparison.created_at = datetime.now()
        mock_comparison.updated_at = datetime.now()

        result = service._to_response(mock_comparison)

        assert result.id == "comp_123"
        assert result.user_id == "user_123"
        assert result.name == "测试对比"
        assert result.description == "测试描述"
        assert result.type == ComparisonType.METRICS
        assert result.backtest_task_ids == ["task1", "task2"]
        assert result.is_favorite is True
        assert result.is_public is False
