from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.services.data_topic_hub import get_shared_data_topic_hub


class OptionsChainService:
    def __init__(self) -> None:
        self._hub = get_shared_data_topic_hub()

    async def build_chain(self, symbol: str, expiry: str, provider: str) -> dict[str, Any]:
        if provider == "empty" or symbol == "UNKNOWN":
            return {
                "status": "degraded",
                "reason": "insufficient_data",
                "underlying": symbol,
                "expiry": expiry,
                "source": provider,
                "rows": [],
                "atm_iv": None,
            }
        spot = await self._hub.peek(f"market:quote:{symbol}")
        resolved_provider = (
            provider if provider != "auto" else ("data_governance" if spot else "mock")
        )
        spot_price = float((spot or {}).get("price") or self._base_price(symbol))
        strike_step = self._strike_step(spot_price)
        strikes = self._build_strikes(spot_price, strike_step)
        rows = []
        total_put_oi = 0
        total_call_oi = 0
        for index, strike in enumerate(strikes, start=1):
            distance = abs(index - 5)
            iv = round(0.16 + index * 0.0075, 4)
            call_oi = 720 - distance * 85
            put_oi = 680 - distance * 80
            call_volume = 60 - distance * 5
            put_volume = 55 - distance * 4
            total_call_oi += call_oi
            total_put_oi += put_oi
            rows.append(
                {
                    "strike": strike,
                    "call": {
                        "oi": call_oi,
                        "volume": call_volume,
                        "iv": iv,
                        "greeks": self.calculate_greeks(spot_price, strike, iv, True),
                    },
                    "put": {
                        "oi": put_oi,
                        "volume": put_volume,
                        "iv": iv,
                        "greeks": self.calculate_greeks(spot_price, strike, iv, False),
                    },
                }
            )
        max_pain = self.calculate_max_pain(rows)
        atm_row = min(rows, key=lambda row: abs(row["strike"] - spot_price))
        atm_strike = atm_row["strike"]
        atm_iv = atm_row["call"]["iv"]
        payload = {
            "status": "ok",
            "underlying": symbol,
            "symbol": symbol,
            "expiry": expiry,
            "provider": resolved_provider,
            "source": resolved_provider,
            "spot": spot_price,
            "rows": rows,
            "pcr": round(total_put_oi / total_call_oi, 4) if total_call_oi else 0.0,
            "max_pain": max_pain,
            "atm_strike": atm_strike,
            "atm_iv": atm_iv,
            "strike_count": len(rows),
            "strike_step": strike_step,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self._hub.push(f"option:atm_iv:{resolved_provider}:{symbol}", atm_iv)
        await self._hub.push(f"fno:pcr:{resolved_provider}:{symbol}", payload["pcr"])
        await self._hub.push(f"fno:max_pain:{resolved_provider}:{symbol}", max_pain)
        await self._hub.push(f"option:chain:{resolved_provider}:{symbol}:{expiry}", payload)
        return payload

    @staticmethod
    def _build_strikes(spot_price: float, strike_step: float) -> list[float]:
        center = round(spot_price / strike_step) * strike_step
        return [round(center + (index - 4) * strike_step, 2) for index in range(9)]

    @staticmethod
    def _strike_step(spot_price: float) -> float:
        if spot_price >= 1000:
            return 50.0
        if spot_price >= 100:
            return 10.0
        return 1.0

    @staticmethod
    def _base_price(symbol: str) -> float:
        if symbol == "RB2510":
            return 3524.0
        if symbol == "IF2510":
            return 4125.0
        if symbol == "000001.SZ":
            return 12.36
        return 100.0

    @staticmethod
    def calculate_max_pain(rows: list[dict[str, Any]]) -> float:
        if not rows:
            return 0.0
        candidates = [float(row["strike"]) for row in rows]
        losses: dict[float, float] = {}
        for settlement in candidates:
            total_loss = 0.0
            for row in rows:
                strike = float(row["strike"])
                call_oi = float((row.get("call") or {}).get("oi") or 0.0)
                put_oi = float((row.get("put") or {}).get("oi") or 0.0)
                total_loss += max(settlement - strike, 0.0) * call_oi
                total_loss += max(strike - settlement, 0.0) * put_oi
            losses[settlement] = total_loss
        return min(losses, key=losses.get)

    @staticmethod
    def calculate_greeks(spot: float, strike: float, iv: float, is_call: bool) -> dict[str, float]:
        return OptionsChainService._greeks(spot, strike, iv, is_call)

    @staticmethod
    def _greeks(spot: float, strike: float, iv: float, is_call: bool) -> dict[str, float]:
        moneyness = (spot - strike) / max(strike, 1.0)
        delta = 0.5 + moneyness * 2
        if not is_call:
            delta -= 1
        gamma = max(0.01, 1 / max(spot, 1.0))
        theta = -iv * 0.1
        vega = math.sqrt(max(spot, 1.0)) * iv * 0.1
        return {
            "delta": round(delta, 4),
            "gamma": round(gamma, 4),
            "theta": round(theta, 4),
            "vega": round(vega, 4),
        }


_options_chain_service = OptionsChainService()


def get_options_chain_service() -> OptionsChainService:
    return _options_chain_service
