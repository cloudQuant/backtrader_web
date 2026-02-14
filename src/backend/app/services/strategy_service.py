"""策略服务 - 策略CRUD和配置加载"""
import glob
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

import yaml

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

logger = logging.getLogger(__name__)

# 策略目录（项目根目录/strategies）
STRATEGIES_DIR = Path(__file__).resolve().parents[4] / "strategies"


def _infer_category(name: str, description: str) -> str:
    """根据策略名称和描述推断分类"""
    text = (name + description).lower()
    if any(k in text for k in ["均线", "ma", "trend", "supertrend", "turtle", "海龟", "突破", "动量", "momentum"]):
        return "trend"
    if any(k in text for k in ["rsi", "均值回归", "反转", "reverser", "oscillat", "超买", "超卖", "kdj", "stochastic"]):
        return "mean_reversion"
    if any(k in text for k in ["boll", "波动", "atr", "volatil", "vix", "chandelier"]):
        return "volatility"
    if any(k in text for k in ["套利", "arbitrage", "对冲", "hedge", "long_short"]):
        return "arbitrage"
    if any(k in text for k in ["macd", "ema", "信号", "signal"]):
        return "indicator"
    return "custom"


def _scan_strategies_folder() -> List[StrategyTemplate]:
    """扫描 strategies/ 目录，自动构建策略模板列表"""
    templates: List[StrategyTemplate] = []
    if not STRATEGIES_DIR.is_dir():
        logger.warning(f"策略目录不存在: {STRATEGIES_DIR}")
        return templates

    for config_path in sorted(STRATEGIES_DIR.glob("*/config.yaml")):
        strategy_dir = config_path.parent
        dir_name = strategy_dir.name  # e.g. "029_macd_kdj"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            strat_info = config.get("strategy", {})
            name = strat_info.get("name", dir_name)
            description = strat_info.get("description", "")
            author = strat_info.get("author", "")

            # 读取策略代码文件
            code_files = list(strategy_dir.glob("strategy_*.py"))
            if not code_files:
                continue
            code = code_files[0].read_text(encoding="utf-8")

            # 解析参数
            raw_params = config.get("params") or {}
            params: Dict[str, ParamSpec] = {}
            for k, v in raw_params.items():
                ptype = "float" if isinstance(v, float) else "int"
                params[k] = ParamSpec(
                    type=ptype, default=v, description=k,
                )

            category = _infer_category(name, description)

            # 读取回测配置作为额外元数据
            bt_config = config.get("backtest", {})
            data_config = config.get("data", {})

            # description 追加作者和标的信息
            meta_parts = []
            if author:
                meta_parts.append(f"作者: {author}")
            if data_config.get("symbol"):
                meta_parts.append(f"默认标的: {data_config['symbol']}")
            full_desc = description
            if meta_parts:
                full_desc += " | " + " | ".join(meta_parts)

            templates.append(StrategyTemplate(
                id=dir_name,
                name=name,
                description=full_desc,
                category=category,
                code=code,
                params=params,
            ))
        except Exception as e:
            logger.warning(f"扫描策略 {dir_name} 失败: {e}")
            continue

    logger.info(f"从 {STRATEGIES_DIR} 加载了 {len(templates)} 个策略模板")
    return templates


# 启动时扫描一次
STRATEGY_TEMPLATES: List[StrategyTemplate] = _scan_strategies_folder()

# 构建ID -> 模板的快速查找字典
_TEMPLATE_MAP: Dict[str, StrategyTemplate] = {t.id: t for t in STRATEGY_TEMPLATES}


def get_template_by_id(template_id: str) -> Optional[StrategyTemplate]:
    """根据ID获取策略模板"""
    return _TEMPLATE_MAP.get(template_id)


def get_strategy_readme(template_id: str) -> Optional[str]:
    """读取策略的README.md内容"""
    readme_path = STRATEGIES_DIR / template_id / "README.md"
    if readme_path.is_file():
        return readme_path.read_text(encoding="utf-8")
    return None


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
            update_data["updated_at"] = datetime.now(timezone.utc)
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
