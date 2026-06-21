from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.services.data_topic_hub import get_shared_data_topic_hub


class OptionsChainService:
    def __init__(self) -> None:
        self._hub = get_shared_data_topic_hub()

    async def build_chain(self, symbol: str, expiry: str, provider: str) -> dict[str, Any]:
        resolved_provider = self._normalize_provider(provider)
        if resolved_provider == "empty" or symbol == "UNKNOWN":
            return self._degraded(symbol, expiry, resolved_provider, "insufficient_data")

        if resolved_provider in {"data_governance", "auto"}:
            real_payload = await self._hub.peek(
                self._chain_topic("data_governance", symbol, expiry)
            )
            if real_payload is not None:
                payload = await self._build_real_chain(symbol, expiry, real_payload)
                if payload is not None:
                    return payload
            if resolved_provider == "data_governance":
                return self._degraded(
                    symbol,
                    expiry,
                    resolved_provider,
                    "insufficient_real_chain_data",
                )

        if resolved_provider not in {"auto", "mock"}:
            return self._degraded(symbol, expiry, resolved_provider, "unsupported_provider")

        spot = await self._hub.peek(f"market:quote:{symbol}")
        spot_price = float((spot or {}).get("price") or self._base_price(symbol))
        return await self._build_synthetic_chain(symbol, expiry, "mock", spot_price)

    async def _build_real_chain(
        self,
        symbol: str,
        expiry: str,
        raw_payload: Any,
    ) -> dict[str, Any] | None:
        raw_rows = self._extract_rows(raw_payload)
        spot_price = self._extract_spot(raw_payload)
        if spot_price is None:
            spot = await self._hub.peek(f"market:quote:{symbol}")
            spot_price = self._to_optional_float((spot or {}).get("price"))
        if spot_price is None:
            spot_price = self._derive_spot_from_rows(raw_rows)
        rows = self._normalize_rows(raw_rows, spot_price)
        if not rows:
            return None

        payload_meta = raw_payload if isinstance(raw_payload, dict) else {}
        payload = self._build_payload_from_rows(
            symbol=symbol,
            expiry=expiry,
            provider="data_governance",
            spot_price=spot_price,
            rows=rows,
            timestamp=str(
                payload_meta.get("timestamp")
                or payload_meta.get("source_timestamp")
                or datetime.now(timezone.utc).isoformat()
            ),
        )
        return await self._publish_payload(payload)

    async def _build_synthetic_chain(
        self,
        symbol: str,
        expiry: str,
        provider: str,
        spot_price: float,
    ) -> dict[str, Any]:
        strike_step = self._strike_step(spot_price)
        strikes = self._build_strikes(spot_price, strike_step)
        rows = []
        for index, strike in enumerate(strikes, start=1):
            distance = abs(index - 5)
            iv = round(0.16 + index * 0.0075, 4)
            call_oi = 720 - distance * 85
            put_oi = 680 - distance * 80
            call_volume = 60 - distance * 5
            put_volume = 55 - distance * 4
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
        payload = self._build_payload_from_rows(
            symbol=symbol,
            expiry=expiry,
            provider=provider,
            spot_price=spot_price,
            rows=rows,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return await self._publish_payload(payload)

    def _build_payload_from_rows(
        self,
        *,
        symbol: str,
        expiry: str,
        provider: str,
        spot_price: float,
        rows: list[dict[str, Any]],
        timestamp: str,
    ) -> dict[str, Any]:
        total_call_oi = sum(float((row.get("call") or {}).get("oi") or 0.0) for row in rows)
        total_put_oi = sum(float((row.get("put") or {}).get("oi") or 0.0) for row in rows)
        max_pain = self.calculate_max_pain(rows)
        atm_row = min(rows, key=lambda row: abs(row["strike"] - spot_price))
        atm_strike = atm_row["strike"]
        atm_iv = self._to_optional_float((atm_row.get("call") or {}).get("iv"))
        if atm_iv is None:
            atm_iv = self._to_optional_float((atm_row.get("put") or {}).get("iv"))
        return {
            "status": "ok",
            "underlying": symbol,
            "symbol": symbol,
            "expiry": expiry,
            "provider": provider,
            "source": provider,
            "spot": spot_price,
            "rows": rows,
            "pcr": round(total_put_oi / total_call_oi, 4) if total_call_oi else 0.0,
            "max_pain": max_pain,
            "atm_strike": atm_strike,
            "atm_iv": atm_iv,
            "strike_count": len(rows),
            "strike_step": self._calculate_strike_step(rows) or self._strike_step(spot_price),
            "timestamp": timestamp,
        }

    async def _publish_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider = str(payload["provider"])
        symbol = str(payload["symbol"])
        expiry = str(payload["expiry"])
        await self._hub.push(f"option:atm_iv:{provider}:{symbol}", payload["atm_iv"])
        await self._hub.push(f"fno:pcr:{provider}:{symbol}", payload["pcr"])
        await self._hub.push(f"fno:max_pain:{provider}:{symbol}", payload["max_pain"])
        await self._hub.push(self._chain_topic(provider, symbol, expiry), payload)
        return payload

    def _normalize_rows(self, raw_rows: list[Any], spot_price: float) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            strike = self._to_optional_float(raw_row.get("strike"))
            if strike is None:
                continue
            rows.append(
                {
                    "strike": strike,
                    "call": self._normalize_leg(raw_row, "call", spot_price, strike),
                    "put": self._normalize_leg(raw_row, "put", spot_price, strike),
                }
            )
        return sorted(rows, key=lambda row: row["strike"])

    def _normalize_leg(
        self,
        raw_row: dict[str, Any],
        side: str,
        spot_price: float,
        strike: float,
    ) -> dict[str, Any]:
        raw_leg = raw_row.get(side)
        leg_payload = raw_leg if isinstance(raw_leg, dict) else {}
        iv = self._to_float(self._first_present(leg_payload.get("iv"), raw_row.get(f"{side}_iv")))
        leg = {
            "oi": self._normalize_quantity(
                self._first_present(leg_payload.get("oi"), raw_row.get(f"{side}_oi"))
            ),
            "volume": self._normalize_quantity(
                self._first_present(leg_payload.get("volume"), raw_row.get(f"{side}_volume"))
            ),
            "iv": iv,
        }
        greeks = leg_payload.get("greeks")
        leg["greeks"] = (
            greeks
            if isinstance(greeks, dict)
            else self.calculate_greeks(spot_price, strike, iv, side == "call")
        )
        return leg

    @staticmethod
    def _extract_rows(raw_payload: Any) -> list[Any]:
        if isinstance(raw_payload, list):
            return raw_payload
        if not isinstance(raw_payload, dict):
            return []
        for key in ("rows", "data", "items", "chain"):
            rows = raw_payload.get(key)
            if isinstance(rows, list):
                return rows
        return []

    def _extract_spot(self, raw_payload: Any) -> float | None:
        if not isinstance(raw_payload, dict):
            return None
        for key in ("spot", "underlying_price", "last_price", "last", "price"):
            spot = self._to_optional_float(raw_payload.get(key))
            if spot is not None:
                return spot
        return None

    def _derive_spot_from_rows(self, raw_rows: list[Any]) -> float:
        strikes = sorted(
            strike
            for row in raw_rows
            if isinstance(row, dict)
            for strike in [self._to_optional_float(row.get("strike"))]
            if strike is not None
        )
        if not strikes:
            return 0.0
        return strikes[len(strikes) // 2]

    @staticmethod
    def _calculate_strike_step(rows: list[dict[str, Any]]) -> float | None:
        strikes = sorted({float(row["strike"]) for row in rows})
        steps = [
            round(strikes[index] - strikes[index - 1], 4)
            for index in range(1, len(strikes))
            if strikes[index] > strikes[index - 1]
        ]
        return min(steps) if steps else None

    @staticmethod
    def _normalize_quantity(value: Any) -> int | float:
        number = OptionsChainService._to_float(value)
        return int(number) if number.is_integer() else round(number, 4)

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_optional_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _first_present(*values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        return (provider or "data_governance").strip() or "data_governance"

    @staticmethod
    def _chain_topic(provider: str, symbol: str, expiry: str) -> str:
        return f"option:chain:{provider}:{symbol}:{expiry}"

    @staticmethod
    def _degraded(symbol: str, expiry: str, provider: str, reason: str) -> dict[str, Any]:
        return {
            "status": "degraded",
            "reason": reason,
            "underlying": symbol,
            "symbol": symbol,
            "expiry": expiry,
            "provider": provider,
            "source": provider,
            "spot": None,
            "rows": [],
            "pcr": None,
            "max_pain": None,
            "atm_strike": None,
            "atm_iv": None,
            "strike_count": 0,
            "strike_step": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

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
