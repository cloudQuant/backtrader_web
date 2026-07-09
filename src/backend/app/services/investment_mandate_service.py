"""Investment mandate parsing and persistence for AI research."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research import InvestmentMandate
from app.schemas.ai_strategy_research import (
    AIStrategyResearchRunRequest,
    InvestmentMandateCreate,
    InvestmentMandateResponse,
)


class InvestmentMandateService:
    """Parse natural-language investment demand into a confirmed mandate."""

    async def create_mandate(
        self,
        user_id: str,
        data: InvestmentMandateCreate,
    ) -> InvestmentMandateResponse:
        parsed = self.parse_mandate(data)
        model = InvestmentMandate(
            user_id=user_id,
            raw_prompt=data.raw_prompt.strip(),
            structured_goal=parsed["structured_goal"],
            asset_scope=parsed["asset_scope"],
            timeframe=parsed.get("timeframe"),
            objective=parsed.get("objective"),
            risk_constraints=parsed["risk_constraints"],
            trading_constraints=parsed["trading_constraints"],
            quality_gates=parsed["quality_gates"],
            status="confirmed",
            source="rule",
        )
        async with async_session_maker() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
        return self._to_response(model)

    async def ensure_for_request(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
    ) -> InvestmentMandateResponse:
        if request.mandate_id:
            mandate = await self.get_mandate(user_id, request.mandate_id)
            if mandate is None:
                raise ValueError("Investment mandate not found")
            return mandate

        return await self.create_mandate(
            user_id,
            InvestmentMandateCreate(
                raw_prompt=request.prompt,
                symbol=request.symbol,
                symbol_name=request.symbol_name,
                timeframe=request.timeframe,
                risk_constraints=self._risk_constraints_from_request(request),
                trading_constraints={
                    "annual_days": request.annual_days,
                    "calc_method": request.calc_method,
                    "weight_mode": request.weight_mode,
                    "start_paper_trading": request.start_paper_trading,
                },
                quality_gates=self._quality_gates_from_request(request),
            ),
        )

    async def get_mandate(
        self,
        user_id: str,
        mandate_id: str,
    ) -> InvestmentMandateResponse | None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(InvestmentMandate).where(
                    InvestmentMandate.id == mandate_id,
                    InvestmentMandate.user_id == user_id,
                )
            )
            model = result.scalar_one_or_none()
        return self._to_response(model) if model else None

    def parse_mandate(self, data: InvestmentMandateCreate) -> dict[str, Any]:
        prompt = data.raw_prompt.strip()
        symbol = (data.symbol or self._symbol_from_prompt(prompt) or "").strip()
        asset_class = self._asset_class(symbol, prompt)
        timeframe = (data.timeframe or self._timeframe_from_prompt(prompt) or "").strip() or None
        objective = (data.objective or self._objective_from_prompt(prompt)).strip()
        risk_constraints = {
            **self._risk_constraints_from_prompt(prompt),
            **dict(data.risk_constraints or {}),
        }
        trading_constraints = {
            **self._trading_constraints_from_prompt(prompt, asset_class),
            **dict(data.trading_constraints or {}),
        }
        quality_gates = dict(data.quality_gates or {})
        structured_goal = {
            "asset_class": asset_class,
            "symbol": symbol,
            "symbol_name": (data.symbol_name or "").strip(),
            "timeframe": timeframe,
            "objective": objective,
            "risk_focus": sorted(risk_constraints),
            "quality_gates": quality_gates,
        }
        return {
            "structured_goal": structured_goal,
            "asset_scope": {
                "asset_class": asset_class,
                "symbol": symbol,
                "symbol_name": (data.symbol_name or "").strip(),
            },
            "timeframe": timeframe,
            "objective": objective,
            "risk_constraints": risk_constraints,
            "trading_constraints": trading_constraints,
            "quality_gates": quality_gates,
        }

    def _quality_gates_from_request(self, request: AIStrategyResearchRunRequest) -> dict[str, Any]:
        return {
            "target_sharpe": request.target_sharpe,
            "min_total_trades": request.min_total_trades,
            "max_drawdown_limit": request.max_drawdown_limit,
            "min_total_return": request.min_total_return,
            "min_annual_return": request.min_annual_return,
            "min_win_rate": request.min_win_rate,
            "out_of_sample_validation": request.out_of_sample_validation,
            "require_out_of_sample_validation": request.require_out_of_sample_validation,
            "out_of_sample_ratio": request.out_of_sample_ratio,
            "min_out_of_sample_sharpe": request.min_out_of_sample_sharpe,
            "min_out_of_sample_trades": request.min_out_of_sample_trades,
        }

    def _risk_constraints_from_request(
        self,
        request: AIStrategyResearchRunRequest,
    ) -> dict[str, Any]:
        constraints: dict[str, Any] = {}
        if request.max_drawdown_limit is not None:
            constraints["max_drawdown_limit"] = request.max_drawdown_limit
        if request.min_win_rate is not None:
            constraints["min_win_rate"] = request.min_win_rate
        if request.out_of_sample_validation:
            constraints["out_of_sample_validation"] = {
                "ratio": request.out_of_sample_ratio,
                "required": request.require_out_of_sample_validation,
            }
        return constraints

    def _symbol_from_prompt(self, prompt: str) -> str:
        match = re.search(r"\b[A-Z]{1,4}\d{0,4}(?:\.(?:SZ|SH|BJ|SHFE|DCE|CZCE|INE|CFFEX))?\b", prompt)
        return match.group(0) if match else ""

    def _timeframe_from_prompt(self, prompt: str) -> str:
        normalized = prompt.lower()
        patterns = (
            (r"(\d+)\s*h|(\d+)\s*小时", "h"),
            (r"(\d+)\s*d|(\d+)\s*日", "d"),
            (r"(\d+)\s*min|(\d+)\s*分钟", "m"),
        )
        for pattern, suffix in patterns:
            match = re.search(pattern, normalized)
            if not match:
                continue
            number = next(group for group in match.groups() if group)
            return f"{number}{suffix}"
        if "日线" in prompt or "daily" in normalized:
            return "1d"
        if "小时" in prompt or "hour" in normalized:
            return "1h"
        return ""

    def _asset_class(self, symbol: str, prompt: str) -> str:
        text = f"{symbol} {prompt}".upper()
        if any(token in prompt for token in ("期货", "合约", "纯碱", "螺纹", "原油", "国债期货")):
            return "futures"
        if any(token in prompt for token in ("股票", "个股", "A股")) or text.endswith((".SZ", ".SH", ".BJ")):
            return "equity"
        if any(token in prompt for token in ("债券", "国债", "利率债")):
            return "bond"
        if any(token in prompt for token in ("基金", "ETF")):
            return "fund"
        if any(token in prompt for token in ("期权", "波动率曲面")):
            return "option"
        if any(token in prompt for token in ("外汇", "汇率")):
            return "fx"
        if any(token in text for token in ("USDT", "BTC", "ETH", "PERP", "SWAP")):
            return "crypto"
        return "multi_asset"

    def _objective_from_prompt(self, prompt: str) -> str:
        if any(token in prompt for token in ("保值", "稳健", "低回撤", "回撤")):
            return "稳健增值并控制回撤"
        if any(token in prompt for token in ("套利", "价差", "跨期")):
            return "捕捉相对价值或期限价差机会"
        if any(token in prompt for token in ("趋势", "突破")):
            return "捕捉趋势收益并控制反转风险"
        return prompt[:300]

    def _risk_constraints_from_prompt(self, prompt: str) -> dict[str, Any]:
        constraints: dict[str, Any] = {}
        if "回撤" in prompt:
            constraints["drawdown_control"] = True
        if any(token in prompt for token in ("止损", "风险")):
            constraints["stop_loss_required"] = True
        if any(token in prompt for token in ("样本外", "过拟合")):
            constraints["out_of_sample_required"] = True
        return constraints

    def _trading_constraints_from_prompt(self, prompt: str, asset_class: str) -> dict[str, Any]:
        constraints: dict[str, Any] = {"asset_class": asset_class}
        if asset_class == "futures":
            constraints["requires_contract_specs"] = True
            constraints["requires_margin_sizing"] = True
        if any(token in prompt for token in ("手续费", "滑点")):
            constraints["requires_cost_model"] = True
        return constraints

    def _to_response(self, model: InvestmentMandate) -> InvestmentMandateResponse:
        return InvestmentMandateResponse(
            id=model.id,
            raw_prompt=model.raw_prompt,
            structured_goal=dict(model.structured_goal or {}),
            asset_scope=dict(model.asset_scope or {}),
            timeframe=model.timeframe,
            objective=model.objective,
            risk_constraints=dict(model.risk_constraints or {}),
            trading_constraints=dict(model.trading_constraints or {}),
            quality_gates=dict(model.quality_gates or {}),
            status=model.status,
            source=model.source,
            created_at=_iso(model.created_at),
            updated_at=_iso(model.updated_at),
        )


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""
