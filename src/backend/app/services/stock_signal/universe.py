"""Point-in-time universe resolution for the SSE 50 nightly signal batch."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any


def _exchange_symbol(code: str) -> str:
    exchange = "SH" if code.startswith(("5", "6", "9")) else "SZ"
    return f"{code}.{exchange}"


class Sse50UniverseProvider:
    """Resolve and normalize the current SSE 50 constituents from AkShare."""

    index_symbol = "000016"
    expected_member_count = 50

    def __init__(self, fetcher: Callable[..., Any] | None = None) -> None:
        self._fetcher = fetcher or self._fetch_members

    @staticmethod
    def _fetch_members(*, symbol: str) -> Any:
        import akshare as ak

        return ak.index_stock_cons_csindex(symbol=symbol)

    async def members(self) -> list[dict[str, str]]:
        frame = await asyncio.to_thread(self._fetcher, symbol=self.index_symbol)
        try:
            rows = frame.to_dict(orient="records")
        except (AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError("sse50_universe_unavailable") from exc
        members: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_code = str(
                row.get("成分券代码")
                or row.get("股票代码")
                or row.get("代码")
                or row.get("symbol")
                or ""
            ).strip()
            code = raw_code.split(".", 1)[0]
            if not re.fullmatch(r"\d{6}", code) or code in seen:
                continue
            seen.add(code)
            members.append(
                {
                    "symbol": _exchange_symbol(code),
                    "name": str(
                        row.get("成分券名称") or row.get("名称") or row.get("name") or code
                    ),
                }
            )
        if len(members) != self.expected_member_count:
            raise RuntimeError(f"sse50_universe_unexpected_count:{len(members)}")
        return members
