"""
Pytest 配置和 Fixtures

为所有测试提供共享的 fixtures 和配置
"""
import asyncio
import os
import tempfile
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

from app.main_updated import app
from app.models.user import User
from app.models.permission import Role, Permission, ROLE_PERMISSIONS
from app.models.backtest import BacktestTask, BacktestResultModel
from app.models.strategy import Strategy
from app.db.database import Base, get_async_session


# ==================== 数据库 Fixtures ====================

@pytest.fixture(scope="session")
def db_engine():
    """创建测试数据库引擎（session 级）"""
    # 使用 SQLite 内存数据库
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """创建测试数据库会话（function 级）"""
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
async def async_db_session() -> AsyncGenerator[Session, None]:
    """创建异步数据库会话"""
    async with get_async_session() as session:
        yield session


# ==================== 用户 Fixtures ====================

@pytest.fixture
def mock_user():
    """创建模拟用户"""
    return User(
        id="test-user-1",
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password_here",
    )


@pytest.fixture
def mock_user_with_roles():
    """创建带角色的模拟用户"""
    user = User(
        id="test-user-2",
        username="testuser",
        email="test2@example.com",
        hashed_password="hashed_password_here",
    )
    user.roles = [Role.USER]
    return user


@pytest.fixture
def mock_guest_user():
    """创建 Guest 角色"""
    user = User(
        id="test-user-3",
        username="guestuser",
        email="guest@example.com",
        hashed_password="hashed_password_here",
    )
    user.roles = [Role.GUEST]
    return user


@pytest.fixture
def mock_premium_user():
    """创建 Premium 角色"""
    user = User(
        id="test-user-4",
        username="premiumuser",
        email="premium@example.com",
        hashed_password="hashed_password_here",
    )
    user.roles = [Role.PREMIUM]
    return user


@pytest.fixture
def mock_admin_user():
    """创建 Admin 角色"""
    user = User(
        id="test-user-5",
        username="adminuser",
        email="admin@example.com",
        hashed_password="hashed_password_here",
    )
    user.roles = [Role.ADMIN]
    return user


# ==================== 策略 Fixtures ====================

@pytest.fixture
def mock_strategy():
    """创建模拟策略"""
    return Strategy(
        id="test-strategy-1",
        user_id="test-user-1",
        name="双均线策略",
        description="基于快慢均线交叉的趋势跟踪策略",
        code='''
import backtrader as bt

class MaCrossStrategy(bt.Strategy):
    params = (
        ('fast_period', 5),
        ('slow_period', 20),
    )
    
    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=self.p.fast_period)
        self.slow_ma = bt.indicators.SMA(period=self.p.slow_period)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
    
    def next(self):
        if not self.position:
            if self.crossover > 0:
                self.buy()
        elif self.crossover < 0:
            self.sell()
''',
        params={
            "fast_period": {"type": "int", "default": 5, "min": 2, "max": 50},
            "slow_period": {"type": "int", "default": 20, "min": 10, "max": 200},
        },
        category="trend",
    )


# ==================== 回测 Fixtures ====================

@pytest.fixture
def mock_backtest_task():
    """创建模拟回测任务"""
    return BacktestTask(
        id="test-task-1",
        user_id="test-user-1",
        strategy_id="ma_cross",
        symbol="000001.SZ",
        status="pending",
        request_data={
            "strategy_id": "ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_cash": 100000,
            "commission": 0.001,
            "params": {"fast_period": 5, "slow_period": 20},
        },
    )


@pytest.fixture
def mock_backtest_result():
    """创建模拟回测结果"""
    return BacktestResultModel(
        id="test-result-1",
        task_id="test-task-1",
        total_return=15.5,
        annual_return=15.5,
        sharpe_ratio=1.8,
        max_drawdown=12.5,
        win_rate=60.0,
        total_trades=20,
        profitable_trades=12,
        losing_trades=8,
        equity_curve=[100000, 101550, 103100, 104650],
        equity_dates=["2023-01-01", "2023-06-30", "2023-09-30", "2023-12-31"],
        drawdown_curve=[0, -2.0, -5.0, -10.0],
        trades=[],
    )


# ==================== API 客户端 Fixture ====================

@pytest.fixture
def client():
    """创建 FastAPI 测试客户端"""
    return TestClient(app)


@pytest.fixture
async def auth_headers(mock_user):
    """创建认证头（JWT Token）"""
    # 模拟登录并获取 Token
    # 实际实现应该从认证服务获取
    return {"Authorization": "Bearer mock_token_here"}


# ==================== Mock Services ====================

@pytest.fixture
def mock_backtest_service():
    """Mock BacktestService"""
    from app.services.backtest_service import BacktestService

    service = AsyncMock(spec=BacktestService)
    return service


@pytest.fixture
def mock_report_service():
    """Mock ReportService"""
    from app.services.report_service import ReportService

    service = AsyncMock(spec=ReportService)
    return service


@pytest.fixture
def mock_optimization_service():
    """Mock OptimizationService"""
    from app.services.optimization_service import OptimizationService

    service = AsyncMock(spec=OptimizationService)
    return service


# ==================== 测试配置 ====================

def pytest_configure(config):
    """Pytest 配置"""
    config.addinivalue(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
        "integration: marks tests as integration tests",
        "unit: marks tests as unit tests",
    )
