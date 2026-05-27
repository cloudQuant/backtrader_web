from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class InstrumentRecord:
    canonical_symbol: str
    name: str
    asset_type: str
    exchange: str
    broker_symbols: dict[str, str]


class InstrumentService:
    def __init__(self, instruments: list[InstrumentRecord]) -> None:
        self._items = instruments

    @classmethod
    def with_seed_data(cls) -> InstrumentService:
        return cls(
            [
                InstrumentRecord(
                    canonical_symbol="RB2510",
                    name="螺纹钢主力",
                    asset_type="futures",
                    exchange="SHFE",
                    broker_symbols={"ctp": "rb2510", "ib": "RBV26"},
                ),
                InstrumentRecord(
                    canonical_symbol="IF2510",
                    name="沪深300股指",
                    asset_type="futures",
                    exchange="CFFEX",
                    broker_symbols={"ctp": "IF2510", "ib": "IFV26"},
                ),
                InstrumentRecord(
                    canonical_symbol="000001.SZ",
                    name="平安银行",
                    asset_type="equity",
                    exchange="SZSE",
                    broker_symbols={"akshare": "000001", "yahoo": "000001.SZ"},
                ),
            ]
        )

    def resolve(
        self,
        *,
        canonical_symbol: str | None = None,
        broker_symbol: str | None = None,
        broker_id: str | None = None,
    ) -> InstrumentRecord | None:
        if canonical_symbol:
            for item in self._items:
                if item.canonical_symbol == canonical_symbol:
                    return item
        if broker_symbol and broker_id:
            for item in self._items:
                if item.broker_symbols.get(broker_id, "").lower() == broker_symbol.lower():
                    return item
        return None

    def search(self, keyword: str) -> list[InstrumentRecord]:
        query = keyword.lower().strip()
        return [
            item
            for item in self._items
            if query in item.canonical_symbol.lower() or query in item.name.lower()
        ]

    def to_broker_symbol(self, canonical_symbol: str, broker_id: str) -> str | None:
        item = self.resolve(canonical_symbol=canonical_symbol)
        return None if item is None else item.broker_symbols.get(broker_id)
