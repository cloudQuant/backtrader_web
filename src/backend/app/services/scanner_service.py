from __future__ import annotations

import ast
import uuid
from typing import Any

_ALLOWED_NAMES = {
    "price",
    "volume",
    "change_pct",
    "indicator",
    "factor",
    "news_sentiment",
    "portfolio_exposure",
    "lookback_days",
    "timeframe",
}
_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Eq,
    ast.NotEq,
)


class ScannerService:
    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}

    def run(
        self,
        universe: list[str],
        condition: str,
        *,
        lookback_days: int = 20,
        timeframe: str = "1d",
    ) -> dict[str, Any]:
        parsed = ast.parse(condition, mode="eval")
        for node in ast.walk(parsed):
            if not isinstance(node, _ALLOWED_NODES):
                raise ValueError("unsafe_expression")
            if isinstance(node, ast.Name) and node.id not in _ALLOWED_NAMES:
                raise ValueError("unsafe_expression")
        matches = []
        for symbol in universe:
            context = self._build_context(symbol, lookback_days=lookback_days, timeframe=timeframe)
            if bool(eval(compile(parsed, "<scanner>", "eval"), {"__builtins__": {}}, context)):
                matches.append({"symbol": symbol, **context})
        task_id = str(uuid.uuid4())
        payload = {
            "status": "completed",
            "task_id": task_id,
            "condition": condition,
            "timeframe": timeframe,
            "lookback_days": lookback_days,
            "matches": matches,
        }
        self._tasks[task_id] = payload
        return payload

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        payload = self._tasks.get(task_id)
        if payload is None:
            return None
        return dict(payload)

    @staticmethod
    def _build_context(symbol: str, *, lookback_days: int, timeframe: str) -> dict[str, Any]:
        if symbol == "RB2510":
            base = {
                "price": 3524.0,
                "volume": 4200,
                "change_pct": 0.018,
                "indicator": 0.77,
                "factor": 0.71,
                "news_sentiment": 0.65,
                "portfolio_exposure": 0.18,
            }
        else:
            base = {
                "price": 4125.0 if symbol == "IF2510" else 95.0,
                "volume": 2800 if symbol == "IF2510" else 800,
                "change_pct": 0.011,
                "indicator": 0.58,
                "factor": 0.54,
                "news_sentiment": 0.42,
                "portfolio_exposure": 0.09,
            }
        return {
            **base,
            "lookback_days": int(lookback_days),
            "timeframe": timeframe,
        }


_scanner_service = ScannerService()


def get_scanner_service() -> ScannerService:
    return _scanner_service
