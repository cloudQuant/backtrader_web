from __future__ import annotations

from typing import Any

from app.services.factor_lib.registry import FactorRegistry
from app.services.instruments import InstrumentService


class EquityResearchService:
    def __init__(self) -> None:
        self.instrument_service = InstrumentService.with_seed_data()
        self.factor_registry = FactorRegistry.with_builtin_factors()

    def search(self, keyword: str) -> dict[str, Any]:
        items = [
            {
                "symbol": item.canonical_symbol,
                "name": item.name,
                "asset_type": item.asset_type,
                "exchange": item.exchange,
            }
            for item in self.instrument_service.search(keyword)
        ]
        return {"items": items, "total": len(items)}

    def get_quote(self, symbol: str) -> dict[str, Any]:
        instrument = self.instrument_service.resolve(canonical_symbol=symbol)
        price = self._base_price(symbol)
        previous_close = round(price * 0.986, 2)
        return {
            "symbol": symbol,
            "name": instrument.name if instrument else symbol,
            "price": price,
            "previous_close": previous_close,
            "change_pct": round((price - previous_close) / previous_close, 4),
            "currency": (
                "CNY"
                if symbol.endswith((".SZ", ".SH")) or symbol.startswith(("RB", "IF"))
                else "USD"
            ),
            "provider": "data_governance",
        }

    def info(self, symbol: str) -> dict[str, Any]:
        instrument = self.instrument_service.resolve(canonical_symbol=symbol)
        if symbol == "000001.SZ":
            return {
                "symbol": symbol,
                "name": instrument.name if instrument else symbol,
                "asset_type": instrument.asset_type if instrument else "equity",
                "exchange": instrument.exchange if instrument else "SZSE",
                "sector": "Financials",
                "industry": "Banks",
                "country": "CN",
                "listing_currency": "CNY",
                "description": "区域性零售与公司金融业务并重的银行股示例资料。",
                "provider": "data_governance",
            }
        return {
            "symbol": symbol,
            "name": instrument.name if instrument else symbol,
            "asset_type": instrument.asset_type if instrument else "futures",
            "exchange": instrument.exchange if instrument else "SHFE",
            "sector": "Industrials",
            "industry": "Metals & Futures",
            "country": "CN",
            "listing_currency": "CNY",
            "description": "面向商品与指数研究的统一合约画像。",
            "provider": "data_governance",
        }

    def history(self, symbol: str) -> dict[str, Any]:
        base_price = self._base_price(symbol)
        closes = [
            round(base_price - 4 + index * 0.8 + (index % 2) * 0.35, 2) for index in range(10)
        ]
        rows = [
            {
                "date": f"2026-05-{index + 10:02d}",
                "open": round(close - 0.9, 2),
                "high": round(close + 1.1, 2),
                "low": round(close - 1.4, 2),
                "close": close,
                "volume": 1000 + index * 120,
            }
            for index, close in enumerate(closes, start=1)
        ]
        return {"symbol": symbol, "rows": rows}

    def financials(self, symbol: str) -> dict[str, Any]:
        base_revenue = 168_000 if symbol == "000001.SZ" else 82_000
        annual = [
            {
                "period": str(year),
                "revenue": base_revenue + index * 4_200,
                "net_income": round((base_revenue + index * 4_200) * 0.13, 2),
                "eps": round(1.1 + index * 0.08, 2),
                "roe": round(10.5 + index * 0.4, 2),
            }
            for index, year in enumerate([2023, 2024, 2025])
        ]
        quarterly = [
            {
                "period": period,
                "revenue": round(base_revenue / 4 + index * 350, 2),
                "net_income": round((base_revenue / 4 + index * 350) * 0.125, 2),
                "eps": round(0.26 + index * 0.01, 2),
            }
            for index, period in enumerate(["2025Q2", "2025Q3", "2025Q4", "2026Q1"])
        ]
        return {
            "symbol": symbol,
            "annual": annual,
            "quarterly": quarterly,
            "provider": "data_governance",
        }

    def peers(self, symbol: str) -> dict[str, Any]:
        if symbol == "000001.SZ":
            items = [
                {"symbol": "600036.SH", "name": "招商银行", "reason": "同属大型银行"},
                {"symbol": "601166.SH", "name": "兴业银行", "reason": "零售与对公结构相近"},
                {"symbol": "601328.SH", "name": "交通银行", "reason": "资产负债结构可比"},
            ]
        else:
            items = [
                {"symbol": "HC2510", "name": "热卷主力", "reason": "黑色系产业链联动"},
                {"symbol": "I2510", "name": "铁矿石主力", "reason": "原材料成本联动"},
                {"symbol": "IF2510", "name": "沪深300股指", "reason": "宏观风险偏好参照"},
            ]
        return {"symbol": symbol, "items": items, "total": len(items)}

    def technicals(self, symbol: str) -> dict[str, Any]:
        history = self.history(symbol)["rows"]
        factor_values = {
            factor_id: self.factor_registry.calculate(factor_id, history)
            for factor_id in ["momentum_5", "volatility_5", "reversal_1"]
        }
        return {"symbol": symbol, "factors": factor_values}

    @staticmethod
    def _base_price(symbol: str) -> float:
        if symbol == "RB2510":
            return 3524.0
        if symbol == "IF2510":
            return 4125.0
        if symbol == "000001.SZ":
            return 12.36
        return 100.0


_equity_research_service = EquityResearchService()


def get_equity_research_service() -> EquityResearchService:
    return _equity_research_service
