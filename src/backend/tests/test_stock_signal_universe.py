"""SSE 50 constituent-resolution contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.stock_signal.universe import Sse50UniverseProvider


def _frame(rows: list[dict[str, str]]) -> SimpleNamespace:
    return SimpleNamespace(to_dict=lambda orient: rows)


@pytest.mark.asyncio
async def test_universe_normalizes_and_requires_exactly_fifty_members() -> None:
    rows = [
        {"成分券代码": f"{600000 + index:06d}", "成分券名称": f"测试{index}"}
        for index in range(50)
    ]
    provider = Sse50UniverseProvider(fetcher=lambda **_kwargs: _frame(rows))

    members = await provider.members()

    assert len(members) == 50
    assert members[0] == {"symbol": "600000.SH", "name": "测试0"}


@pytest.mark.asyncio
async def test_universe_refuses_partial_constituent_lists() -> None:
    rows = [{"成分券代码": f"{600000 + index:06d}"} for index in range(49)]
    provider = Sse50UniverseProvider(fetcher=lambda **_kwargs: _frame(rows))

    with pytest.raises(RuntimeError, match="sse50_universe_unexpected_count:49"):
        await provider.members()
