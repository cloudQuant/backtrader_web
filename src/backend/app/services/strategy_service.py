"""
策略服务 - 策略CRUD和配置加载
"""
from typing import Optional, List
from datetime import datetime

from app.models.strategy import Strategy
from app.schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    StrategyListResponse,
    StrategyTemplate,
    ParamSpec,
)
from app.db.sql_repository import SQLRepository


# 内置策略模板
STRATEGY_TEMPLATES = [
    StrategyTemplate(
        id="ma_cross",
        name="双均线交叉策略",
        description="基于快慢均线交叉的趋势跟踪策略，金叉买入，死叉卖出",
        category="trend",
        code='''import backtrader as bt

class MaCrossStrategy(bt.Strategy):
    """双均线交叉策略"""
    params = (
        ('fast_period', 5),
        ('slow_period', 20),
    )
    
    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=self.params.fast_period)
        self.slow_ma = bt.indicators.SMA(period=self.params.slow_period)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
    
    def next(self):
        if not self.position:
            if self.crossover > 0:
                self.buy()
        elif self.crossover < 0:
            self.sell()
''',
        params={
            "fast_period": ParamSpec(type="int", default=5, min=2, max=50, description="快线周期"),
            "slow_period": ParamSpec(type="int", default=20, min=10, max=200, description="慢线周期"),
        }
    ),
    StrategyTemplate(
        id="rsi",
        name="RSI超买超卖策略",
        description="基于RSI指标的均值回归策略，超卖买入，超买卖出",
        category="mean_reversion",
        code='''import backtrader as bt

class RSIStrategy(bt.Strategy):
    """RSI超买超卖策略"""
    params = (
        ('period', 14),
        ('overbought', 70),
        ('oversold', 30),
    )
    
    def __init__(self):
        self.rsi = bt.indicators.RSI(period=self.params.period)
    
    def next(self):
        if not self.position:
            if self.rsi < self.params.oversold:
                self.buy()
        elif self.rsi > self.params.overbought:
            self.sell()
''',
        params={
            "period": ParamSpec(type="int", default=14, min=5, max=50, description="RSI周期"),
            "overbought": ParamSpec(type="int", default=70, min=60, max=90, description="超买阈值"),
            "oversold": ParamSpec(type="int", default=30, min=10, max=40, description="超卖阈值"),
        }
    ),
    StrategyTemplate(
        id="bollinger",
        name="布林带策略",
        description="基于布林带的突破策略，价格触及下轨买入，触及上轨卖出",
        category="volatility",
        code='''import backtrader as bt

class BollingerStrategy(bt.Strategy):
    """布林带策略"""
    params = (
        ('period', 20),
        ('devfactor', 2.0),
    )
    
    def __init__(self):
        self.boll = bt.indicators.BollingerBands(
            period=self.params.period,
            devfactor=self.params.devfactor
        )
    
    def next(self):
        if not self.position:
            if self.data.close[0] < self.boll.lines.bot[0]:
                self.buy()
        elif self.data.close[0] > self.boll.lines.top[0]:
            self.sell()
''',
        params={
            "period": ParamSpec(type="int", default=20, min=10, max=50, description="布林带周期"),
            "devfactor": ParamSpec(type="float", default=2.0, min=1.0, max=3.0, description="标准差倍数"),
        }
    ),
]


class StrategyService:
    """策略服务"""
    
    def __init__(self):
        self.strategy_repo = SQLRepository(Strategy)
    
    async def create_strategy(
        self,
        user_id: str,
        strategy_create: StrategyCreate
    ) -> StrategyResponse:
        """创建策略"""
        strategy = Strategy(
            user_id=user_id,
            name=strategy_create.name,
            description=strategy_create.description,
            code=strategy_create.code,
            params={k: v.model_dump() for k, v in strategy_create.params.items()},
            category=strategy_create.category,
        )
        
        strategy = await self.strategy_repo.create(strategy)
        
        return self._to_response(strategy)
    
    async def get_strategy(self, strategy_id: str) -> Optional[StrategyResponse]:
        """获取策略详情"""
        strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy:
            return None
        return self._to_response(strategy)
    
    async def update_strategy(
        self,
        strategy_id: str,
        user_id: str,
        strategy_update: StrategyUpdate
    ) -> Optional[StrategyResponse]:
        """更新策略"""
        strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy or strategy.user_id != user_id:
            return None
        
        update_data = {}
        if strategy_update.name is not None:
            update_data["name"] = strategy_update.name
        if strategy_update.description is not None:
            update_data["description"] = strategy_update.description
        if strategy_update.code is not None:
            update_data["code"] = strategy_update.code
        if strategy_update.params is not None:
            update_data["params"] = {k: v.model_dump() for k, v in strategy_update.params.items()}
        if strategy_update.category is not None:
            update_data["category"] = strategy_update.category
        
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            strategy = await self.strategy_repo.update(strategy_id, update_data)
        
        return self._to_response(strategy)
    
    async def delete_strategy(self, strategy_id: str, user_id: str) -> bool:
        """删除策略"""
        strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy or strategy.user_id != user_id:
            return False
        
        return await self.strategy_repo.delete(strategy_id)
    
    async def list_strategies(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        category: str = None
    ) -> StrategyListResponse:
        """列出用户策略"""
        filters = {"user_id": user_id}
        if category:
            filters["category"] = category
        
        strategies = await self.strategy_repo.list(
            filters=filters,
            skip=offset,
            limit=limit
        )
        total = await self.strategy_repo.count(filters=filters)
        
        items = [self._to_response(s) for s in strategies]
        
        return StrategyListResponse(total=total, items=items)
    
    async def get_templates(self) -> List[StrategyTemplate]:
        """获取策略模板"""
        return STRATEGY_TEMPLATES
    
    def _to_response(self, strategy: Strategy) -> StrategyResponse:
        """转换为响应模型"""
        params = {}
        if strategy.params:
            for k, v in strategy.params.items():
                if isinstance(v, dict):
                    params[k] = ParamSpec(**v)
                else:
                    params[k] = v
        
        return StrategyResponse(
            id=strategy.id,
            user_id=strategy.user_id,
            name=strategy.name,
            description=strategy.description,
            code=strategy.code,
            params=params,
            category=strategy.category,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
        )
