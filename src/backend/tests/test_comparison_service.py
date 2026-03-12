"""
Backtest result comparison service tests

Tests:
- ComparisonService class
- create_comparison method
- _generate_comparison_data method
- _compare_metrics method
- _find_best_metrics method
- _compare_equity method
- _compare_trades method
- _compare_drawdown method
- update_comparison method
- delete_comparison method
- get_comparison method
- list_comparisons method
- _to_response method
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.comparison import ComparisonType
from app.services.comparison_service import ComparisonService


class TestComparisonServiceInitialization:
    """Test ComparisonService initialization"""

    def test_initialization(self):
        """Test service initialization"""
        service = ComparisonService()

        assert service.comparison_repo is not None
        assert service.backtest_service is not None


@pytest.mark.asyncio
class TestCreateComparison:
    """Test creating comparison"""

    async def test_create_comparison_basic(self):
        """Test basic creation"""
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
        mock_comparison.name = "Test Comparison"
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
            user_id="user_123", name="Test Comparison", backtest_task_ids=["task1", "task2"]
        )

        assert result is not None

    async def test_create_comparison_with_invalid_task(self):
        """Test with invalid task ID"""
        service = ComparisonService()

        service.backtest_service = AsyncMock()
        service.backtest_service.get_result = AsyncMock(return_value=None)

        with pytest.raises(ValueError) as exc_info:
            await service.create_comparison(
                user_id="user_123", name="Test Comparison", backtest_task_ids=["invalid_task"]
            )

        assert "not found" in str(exc_info.value)


@pytest.mark.asyncio
class TestGenerateComparisonData:
    """Test generating comparison data"""

    async def test_generate_metrics_comparison(self):
        """Test generating metrics comparison"""
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
            },
        }

        result = await service._generate_comparison_data(backtest_results, ComparisonType.METRICS)

        assert "metrics_comparison" in result
        assert "best_metrics" in result
        assert result["type"] == ComparisonType.METRICS

    async def test_generate_equity_comparison(self):
        """Test generating equity curve comparison"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "equity_curve": [100000, 105000],
                "equity_dates": ["2024-01-01", "2024-01-02"],
            }
        }

        result = await service._generate_comparison_data(backtest_results, ComparisonType.EQUITY)

        assert "equity_comparison" in result
        assert "dates" in result["equity_comparison"]
        assert "curves" in result["equity_comparison"]

    async def test_generate_trades_comparison(self):
        """Test generating trades comparison"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "total_trades": 50,
                "profitable_trades": 30,
                "losing_trades": 20,
                "win_rate": 0.6,
            }
        }

        result = await service._generate_comparison_data(backtest_results, ComparisonType.TRADES)

        assert "trades_comparison" in result
        assert "trade_counts" in result["trades_comparison"]
        assert "win_rates" in result["trades_comparison"]

    async def test_generate_drawdown_comparison(self):
        """Test generating drawdown comparison"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "max_drawdown": -0.10,
                "drawdown_curve": [0, -0.05, -0.10],
            }
        }

        result = await service._generate_comparison_data(backtest_results, ComparisonType.DRAWDOWN)

        assert "drawdown_comparison" in result
        assert "max_drawdowns" in result["drawdown_comparison"]
        assert "drawdown_curves" in result["drawdown_comparison"]


class TestCompareMetrics:
    """Test metrics comparison"""

    def test_compare_metrics(self):
        """Test metrics comparison calculation"""
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
            },
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
    """Test finding best metrics"""

    def test_find_best_metrics(self):
        """Test finding best metrics"""
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
            },
        }

        result = service._find_best_metrics(backtest_results)

        assert result["total_return"]["task_id"] == "task2"  # 0.18 > 0.15
        # max_drawdown: look for smallest (most negative) value, so task1(-0.10)
        assert result["max_drawdown"]["task_id"] == "task1"
        assert result["max_drawdown"]["value"] == -0.10
        assert result["win_rate"]["task_id"] == "task2"  # 0.65 > 0.60

    def test_find_best_metrics_single_task(self):
        """Test finding best metrics for single task"""
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
    """Test equity curve comparison"""

    def test_compare_equity(self):
        """Test equity curve comparison"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "equity_curve": [100000, 105000, 103000],
                "equity_dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
            },
            "task2": {
                "equity_curve": [100000, 102000, 101000],
                "equity_dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
            },
        }

        result = service._compare_equity(backtest_results)

        assert "dates" in result
        assert "curves" in result
        assert len(result["dates"]) == 3
        assert "task1" in result["curves"]
        assert "task2" in result["curves"]

    def test_compare_equity_date_alignment(self):
        """Test date alignment"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "equity_curve": [100000, 105000],
                "equity_dates": ["2024-01-01", "2024-01-03"],
            },
            "task2": {
                "equity_curve": [100000, 102000],
                "equity_dates": ["2024-01-01", "2024-01-02"],
            },
        }

        result = service._compare_equity(backtest_results)

        # Should include all unique dates
        assert "2024-01-01" in result["dates"]
        assert "2024-01-02" in result["dates"]
        assert "2024-01-03" in result["dates"]


class TestCompareTrades:
    """Test trades comparison"""

    def test_compare_trades(self):
        """Test trades comparison"""
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
            },
        }

        result = service._compare_trades(backtest_results)

        assert "trade_counts" in result
        assert "win_rates" in result
        assert result["trade_counts"]["task1"]["total"] == 50
        assert result["trade_counts"]["task1"]["profitable"] == 30
        assert result["trade_counts"]["task1"]["losing"] == 20
        assert result["win_rates"]["task1"] == 0.6


class TestCompareDrawdown:
    """Test drawdown comparison"""

    def test_compare_drawdown(self):
        """Test drawdown comparison"""
        service = ComparisonService()

        backtest_results = {
            "task1": {
                "max_drawdown": -0.10,
                "drawdown_curve": [0, -0.05, -0.10, -0.08],
            },
            "task2": {
                "max_drawdown": -0.08,
                "drawdown_curve": [0, -0.03, -0.08, -0.05],
            },
        }

        result = service._compare_drawdown(backtest_results)

        assert "max_drawdowns" in result
        assert "drawdown_curves" in result
        assert result["max_drawdowns"]["task1"] == -0.10
        assert result["max_drawdowns"]["task2"] == -0.08


@pytest.mark.asyncio
class TestUpdateComparison:
    """Test updating comparison"""

    async def test_update_comparison_name(self):
        """Test updating name"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.id = "comp_123"
        mock_comparison.user_id = "user_123"
        mock_comparison.name = "Old Name"
        mock_comparison.description = None
        mock_comparison.is_public = False
        mock_comparison.is_favorite = False  # Add boolean value
        mock_comparison.type = ComparisonType.METRICS
        mock_comparison.backtest_task_ids = ["task1"]
        mock_comparison.comparison_data = {}
        mock_comparison.created_at = datetime.now()
        mock_comparison.updated_at = datetime.now()

        # Mock repo
        async def mock_get(rid):
            return mock_comparison

        async def mock_up(rid, data):
            # Update mock object
            for k, v in data.items():
                setattr(mock_comparison, k, v)
            return mock_comparison

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = mock_get
        service.comparison_repo.update = mock_up

        mock_update_data = Mock()
        mock_update_data.name = "New Name"
        mock_update_data.description = None
        mock_update_data.is_public = False  # Use boolean instead of None
        mock_update_data.backtest_task_ids = None
        mock_update_data.exclude_fields = []  # Add exclude_fields attribute

        result = await service.update_comparison("comp_123", "user_123", mock_update_data)

        assert result is not None

    async def test_update_comparison_not_owner(self):
        """Test updating by non-owner"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.user_id = "other_user"

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=mock_comparison)

        mock_update_data = Mock()
        mock_update_data.name = "New Name"
        mock_update_data.description = None
        mock_update_data.is_public = None
        mock_update_data.backtest_task_ids = None

        result = await service.update_comparison("comp_123", "user_123", mock_update_data)

        assert result is None

    async def test_update_comparison_not_found(self):
        """Test updating non-existent comparison"""
        service = ComparisonService()

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=None)

        mock_update_data = Mock()
        mock_update_data.name = "New Name"
        mock_update_data.description = None
        mock_update_data.is_public = None
        mock_update_data.backtest_task_ids = None

        result = await service.update_comparison("comp_123", "user_123", mock_update_data)

        assert result is None


@pytest.mark.asyncio
class TestDeleteComparison:
    """Test deleting comparison"""

    async def test_delete_comparison_success(self):
        """Test successful deletion"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.user_id = "user_123"

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=mock_comparison)
        service.comparison_repo.delete = AsyncMock(return_value=True)

        result = await service.delete_comparison("comp_123", "user_123")

        assert result is True

    async def test_delete_comparison_not_owner(self):
        """Test deletion by non-owner"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.user_id = "other_user"

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=mock_comparison)

        result = await service.delete_comparison("comp_123", "user_123")

        assert result is False

    async def test_delete_comparison_not_found(self):
        """Test deleting non-existent comparison"""
        service = ComparisonService()

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.delete_comparison("comp_123", "user_123")

        assert result is False


@pytest.mark.asyncio
class TestGetComparison:
    """Test getting comparison"""

    async def test_get_comparison_success(self):
        """Test successful retrieval"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.id = "comp_123"
        mock_comparison.user_id = "user_123"
        mock_comparison.name = "Test Comparison"
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
        """Test getting non-existent comparison"""
        service = ComparisonService()

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.get_comparison("comp_123", "user_123")

        assert result is None

    async def test_get_comparison_private_not_owner(self):
        """Test getting private comparison by non-owner"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.user_id = "other_user"
        mock_comparison.is_public = False

        service.comparison_repo = AsyncMock()
        service.comparison_repo.get_by_id = AsyncMock(return_value=mock_comparison)

        result = await service.get_comparison("comp_123", "user_123")

        assert result is None

    async def test_get_comparison_public_accessible(self):
        """Test public comparison accessible by other users"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.user_id = "other_user"
        mock_comparison.is_public = True
        mock_comparison.id = "comp_123"
        mock_comparison.name = "Public Comparison"
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
    """Test listing comparisons"""

    async def test_list_comparisons_default(self):
        """Test default user comparison listing"""
        service = ComparisonService()

        mock_comparisons = []
        service.comparison_repo = AsyncMock()
        service.comparison_repo.list = AsyncMock(return_value=mock_comparisons)
        service.comparison_repo.count = AsyncMock(return_value=0)

        comparisons, total = await service.list_comparisons("user_123")

        assert comparisons == []
        assert total == 0

    async def test_list_comparisons_public_only(self):
        """Test listing public comparisons only"""
        service = ComparisonService()

        mock_comparisons = []
        service.comparison_repo = AsyncMock()
        service.comparison_repo.list = AsyncMock(return_value=mock_comparisons)
        service.comparison_repo.count = AsyncMock(return_value=0)

        comparisons, total = await service.list_comparisons("user_123", is_public=True)

        assert comparisons == []
        assert total == 0

    async def test_list_comparisons_private_only(self):
        """Test listing private comparisons only"""
        service = ComparisonService()

        mock_comparisons = []
        service.comparison_repo = AsyncMock()
        service.comparison_repo.list = AsyncMock(return_value=mock_comparisons)
        service.comparison_repo.count = AsyncMock(return_value=0)

        comparisons, total = await service.list_comparisons("user_123", is_public=False)

        assert comparisons == []
        assert total == 0

    async def test_list_comparisons_with_pagination(self):
        """Test pagination"""
        service = ComparisonService()

        mock_comparisons = []
        service.comparison_repo = AsyncMock()
        service.comparison_repo.list = AsyncMock(return_value=mock_comparisons)
        service.comparison_repo.count = AsyncMock(return_value=0)

        comparisons, total = await service.list_comparisons("user_123", limit=10, offset=20)

        assert comparisons == []
        assert total == 0


class TestToResponse:
    """Test conversion to response model"""

    def test_to_response(self):
        """Test conversion"""
        service = ComparisonService()

        mock_comparison = Mock()
        mock_comparison.id = "comp_123"
        mock_comparison.user_id = "user_123"
        mock_comparison.name = "Test Comparison"
        mock_comparison.description = "Test Description"
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
        assert result.name == "Test Comparison"
        assert result.description == "Test Description"
        assert result.type == ComparisonType.METRICS
        assert result.backtest_task_ids == ["task1", "task2"]
        assert result.is_favorite is True
        assert result.is_public is False
