from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio_ledger import (
    PortfolioLedgerImportModel,
    PortfolioLedgerModel,
    PortfolioLedgerSnapshotModel,
    PortfolioLedgerTransactionModel,
)

_BASE_NAV = 1_000_000.0
_POSITION_TRADE_TYPES = {"buy", "sell"}


class PortfolioLedgerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_portfolio(
        self,
        user_id: str,
        name: str,
        base_currency: str,
        source_type: str,
        *,
        benchmark_symbol: str | None = None,
        tags: list[str] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        portfolio = PortfolioLedgerModel(
            owner_id=user_id,
            name=name,
            base_currency=base_currency,
            source_type=source_type,
            benchmark_symbol=str(benchmark_symbol or "").strip() or None,
            tags=self._normalize_tags(tags),
            notes=str(notes or "").strip() or None,
        )
        self.db.add(portfolio)
        await self.db.commit()
        await self.db.refresh(portfolio)
        return self._serialize_portfolio(portfolio, transaction_count=0)

    async def get_portfolio(self, user_id: str, portfolio_id: str) -> dict[str, Any] | None:
        portfolio = await self._get_portfolio(user_id, portfolio_id)
        if portfolio is None:
            return None
        return self._serialize_portfolio(
            portfolio,
            transaction_count=await self._transaction_count(portfolio_id),
        )

    async def list_transactions(self, user_id: str, portfolio_id: str) -> dict[str, Any] | None:
        portfolio = await self._get_portfolio(user_id, portfolio_id)
        if portfolio is None:
            return None
        transactions = await self._list_transaction_models(portfolio_id)
        return {
            "items": [self._serialize_transaction(item) for item in transactions],
            "total": len(transactions),
        }

    async def import_transactions(
        self,
        user_id: str,
        portfolio_id: str,
        *,
        idempotency_key: str,
        transactions: list[dict[str, Any]],
        import_format: str = "json",
    ) -> dict[str, Any] | None:
        portfolio = await self._get_portfolio(user_id, portfolio_id)
        if portfolio is None:
            return None
        existing_import = await self.db.execute(
            select(PortfolioLedgerImportModel).where(
                PortfolioLedgerImportModel.portfolio_id == portfolio_id,
                PortfolioLedgerImportModel.idempotency_key == idempotency_key,
            )
        )
        if existing_import.scalar_one_or_none() is not None:
            return {"duplicate": True, "imported_count": 0}
        imported_count = 0
        for item in transactions:
            quantity = float(item.get("quantity") or 0.0)
            price = float(item.get("price") or 0.0)
            amount_raw = item.get("amount")
            amount = float(amount_raw) if amount_raw is not None else round(quantity * price, 2)
            self.db.add(
                PortfolioLedgerTransactionModel(
                    portfolio_id=portfolio_id,
                    symbol=str(item.get("symbol") or "").strip(),
                    trade_type=str(item.get("trade_type") or "buy").strip().lower(),
                    quantity=quantity,
                    price=price,
                    amount=amount,
                    trade_date=str(item.get("trade_date") or str(date.today())),
                    benchmark_symbol=(
                        str(
                            item.get("benchmark_symbol") or portfolio.benchmark_symbol or ""
                        ).strip()
                        or None
                    ),
                    tags=self._normalize_tags(item.get("tags")),
                    notes=str(item.get("notes") or "").strip() or None,
                )
            )
            imported_count += 1
        self.db.add(
            PortfolioLedgerImportModel(
                portfolio_id=portfolio_id,
                import_format=import_format,
                idempotency_key=idempotency_key,
                imported_count=imported_count,
            )
        )
        await self.db.commit()
        return {"duplicate": False, "imported_count": imported_count}

    async def holdings(self, user_id: str, portfolio_id: str) -> dict[str, Any] | None:
        portfolio = await self._get_portfolio(user_id, portfolio_id)
        if portfolio is None:
            return None
        transactions = await self._list_transaction_models(portfolio_id)
        position_stats = self._build_position_stats(transactions)
        items = [
            {
                "symbol": symbol,
                "quantity": round(float(item["quantity"]), 6),
                "cost_basis": round(float(item["avg_cost"]), 6),
            }
            for symbol, item in position_stats.items()
            if abs(float(item["quantity"])) > 0
        ]
        return {"items": items, "total": len(items)}

    async def snapshots(self, user_id: str, portfolio_id: str) -> dict[str, Any] | None:
        portfolio = await self._get_portfolio(user_id, portfolio_id)
        if portfolio is None:
            return None
        transactions = await self._list_transaction_models(portfolio_id)
        derived_items = self._build_snapshot_items(transactions)
        snapshots = await self._list_snapshot_models(portfolio_id)
        items = [self._serialize_snapshot(item) for item in snapshots]
        if items != derived_items:
            await self._persist_snapshot_items(portfolio_id, derived_items)
            return {"items": derived_items, "total": len(derived_items)}
        return {"items": items, "total": len(items)}

    async def backfill_snapshots(
        self,
        user_id: str,
        portfolio_id: str,
    ) -> dict[str, Any] | None:
        portfolio = await self._get_portfolio(user_id, portfolio_id)
        if portfolio is None:
            return None
        transactions = await self._list_transaction_models(portfolio_id)
        items = self._build_snapshot_items(transactions)
        await self._persist_snapshot_items(portfolio_id, items)
        return {"items": items, "total": len(items)}

    async def export_portfolio(self, user_id: str, portfolio_id: str) -> dict[str, Any] | None:
        portfolio = await self._get_portfolio(user_id, portfolio_id)
        if portfolio is None:
            return None
        transactions = await self._list_transaction_models(portfolio_id)
        return {
            "schema_version": "portfolio-ledger.v1",
            "portfolio": self._serialize_portfolio(
                portfolio,
                transaction_count=len(transactions),
            ),
            "transactions": [self._serialize_transaction(item) for item in transactions],
        }

    async def analytics_context(self, user_id: str, portfolio_id: str) -> dict[str, Any] | None:
        portfolio = await self._get_portfolio(user_id, portfolio_id)
        if portfolio is None:
            return None
        transactions = await self._list_transaction_models(portfolio_id)
        snapshot_items = self._build_snapshot_items(transactions)
        position_stats = self._build_position_stats(transactions)
        return {
            "portfolio": self._serialize_portfolio(
                portfolio,
                transaction_count=len(transactions),
            ),
            "equity_curve": [float(item["nav"]) for item in snapshot_items],
            "equity_dates": [str(item["date"]) for item in snapshot_items],
            "position_stats": position_stats,
            "transaction_count": len(transactions),
        }

    async def _get_portfolio(
        self,
        user_id: str,
        portfolio_id: str,
    ) -> PortfolioLedgerModel | None:
        result = await self.db.execute(
            select(PortfolioLedgerModel).where(
                PortfolioLedgerModel.id == portfolio_id,
                PortfolioLedgerModel.owner_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _list_transaction_models(
        self,
        portfolio_id: str,
    ) -> list[PortfolioLedgerTransactionModel]:
        result = await self.db.execute(
            select(PortfolioLedgerTransactionModel)
            .where(PortfolioLedgerTransactionModel.portfolio_id == portfolio_id)
            .order_by(
                PortfolioLedgerTransactionModel.trade_date,
                PortfolioLedgerTransactionModel.created_at,
            )
        )
        return list(result.scalars().all())

    async def _persist_snapshot_items(
        self,
        portfolio_id: str,
        items: list[dict[str, Any]],
    ) -> None:
        await self.db.execute(
            delete(PortfolioLedgerSnapshotModel).where(
                PortfolioLedgerSnapshotModel.portfolio_id == portfolio_id
            )
        )
        for item in items:
            self.db.add(
                PortfolioLedgerSnapshotModel(
                    portfolio_id=portfolio_id,
                    snapshot_date=str(item["date"]),
                    snapshot_index=int(item["snapshot_index"]),
                    cash_flow=float(item["cash_flow"]),
                    nav=float(item["nav"]),
                )
            )
        await self.db.commit()

    def _build_position_stats(
        self,
        transactions: list[PortfolioLedgerTransactionModel],
    ) -> dict[str, dict[str, float]]:
        positions: dict[str, dict[str, float]] = {}
        for txn in transactions:
            if txn.trade_type not in _POSITION_TRADE_TYPES or not txn.symbol:
                continue
            state = positions.setdefault(
                txn.symbol,
                {
                    "quantity": 0.0,
                    "avg_cost": 0.0,
                    "last_price": 0.0,
                    "market_value": 0.0,
                    "return_ratio": 0.0,
                },
            )
            quantity = float(txn.quantity)
            price = float(txn.price)
            previous_quantity = float(state["quantity"])
            previous_avg_cost = float(state["avg_cost"])
            if txn.trade_type == "buy":
                new_quantity = previous_quantity + quantity
                total_cost = previous_quantity * previous_avg_cost + quantity * price
                state["quantity"] = new_quantity
                state["avg_cost"] = total_cost / new_quantity if abs(new_quantity) > 1e-12 else 0.0
            else:
                new_quantity = previous_quantity - quantity
                state["quantity"] = new_quantity
                if abs(new_quantity) <= 1e-12:
                    state["avg_cost"] = 0.0
                elif previous_quantity <= 0:
                    total_cost = abs(previous_quantity) * previous_avg_cost + quantity * price
                    state["avg_cost"] = total_cost / abs(new_quantity)
                elif previous_quantity > 0 and new_quantity < 0:
                    state["avg_cost"] = price
            state["last_price"] = price

        for state in positions.values():
            quantity = float(state["quantity"])
            last_price = float(state["last_price"])
            avg_cost = float(state["avg_cost"])
            state["market_value"] = quantity * last_price
            if avg_cost > 0 and last_price > 0 and abs(quantity) > 1e-12:
                direction = 1.0 if quantity >= 0 else -1.0
                state["return_ratio"] = ((last_price - avg_cost) / avg_cost) * direction
            else:
                state["return_ratio"] = 0.0
        return positions

    async def _transaction_count(self, portfolio_id: str) -> int:
        transactions = await self._list_transaction_models(portfolio_id)
        return len(transactions)

    async def _list_snapshot_models(
        self,
        portfolio_id: str,
    ) -> list[PortfolioLedgerSnapshotModel]:
        result = await self.db.execute(
            select(PortfolioLedgerSnapshotModel)
            .where(PortfolioLedgerSnapshotModel.portfolio_id == portfolio_id)
            .order_by(
                PortfolioLedgerSnapshotModel.snapshot_index,
                PortfolioLedgerSnapshotModel.snapshot_date,
            )
        )
        return list(result.scalars().all())

    def _build_snapshot_items(
        self,
        transactions: list[PortfolioLedgerTransactionModel],
    ) -> list[dict[str, Any]]:
        if not transactions:
            return [
                {
                    "date": str(date.today()),
                    "snapshot_index": 1,
                    "cash_flow": 0.0,
                    "nav": _BASE_NAV,
                }
            ]
        items: list[dict[str, Any]] = []
        cash_balance = _BASE_NAV
        positions: dict[str, dict[str, float]] = {}
        for index, txn in enumerate(transactions, start=1):
            signed_cash = self._signed_cash_flow(txn)
            cash_balance += signed_cash
            self._apply_transaction_to_positions(positions, txn)
            marked_value = sum(
                float(position["quantity"]) * float(position["last_price"])
                for position in positions.values()
            )
            items.append(
                {
                    "date": txn.trade_date,
                    "snapshot_index": index,
                    "cash_flow": round(signed_cash, 2),
                    "nav": round(cash_balance + marked_value, 2),
                }
            )
        return items

    def _apply_transaction_to_positions(
        self,
        positions: dict[str, dict[str, float]],
        transaction: PortfolioLedgerTransactionModel,
    ) -> None:
        if transaction.trade_type not in _POSITION_TRADE_TYPES or not transaction.symbol:
            return
        state = positions.setdefault(
            transaction.symbol,
            {"quantity": 0.0, "avg_cost": 0.0, "last_price": 0.0},
        )
        quantity = float(transaction.quantity)
        price = float(transaction.price)
        previous_quantity = float(state["quantity"])
        previous_avg_cost = float(state["avg_cost"])
        if transaction.trade_type == "buy":
            new_quantity = previous_quantity + quantity
            total_cost = previous_quantity * previous_avg_cost + quantity * price
            state["quantity"] = new_quantity
            state["avg_cost"] = total_cost / new_quantity if abs(new_quantity) > 1e-12 else 0.0
        else:
            new_quantity = previous_quantity - quantity
            state["quantity"] = new_quantity
            if abs(new_quantity) <= 1e-12:
                state["avg_cost"] = 0.0
            elif previous_quantity <= 0:
                total_cost = abs(previous_quantity) * previous_avg_cost + quantity * price
                state["avg_cost"] = total_cost / abs(new_quantity)
            elif previous_quantity > 0 and new_quantity < 0:
                state["avg_cost"] = price
        state["last_price"] = price

    def _signed_cash_flow(self, transaction: PortfolioLedgerTransactionModel) -> float:
        trade_type = str(transaction.trade_type or "").lower()
        if trade_type == "buy":
            return -abs(transaction.quantity * transaction.price)
        if trade_type == "sell":
            return abs(transaction.quantity * transaction.price)
        amount = float(transaction.amount or 0.0)
        if trade_type in {"dividend", "cash_deposit"}:
            return abs(amount)
        if trade_type in {"cash_withdrawal", "fee"}:
            return -abs(amount)
        return 0.0

    def _serialize_portfolio(
        self,
        portfolio: PortfolioLedgerModel,
        *,
        transaction_count: int,
    ) -> dict[str, Any]:
        return {
            "id": portfolio.id,
            "name": portfolio.name,
            "base_currency": portfolio.base_currency,
            "source_type": portfolio.source_type,
            "benchmark_symbol": portfolio.benchmark_symbol,
            "tags": list(portfolio.tags or []),
            "notes": portfolio.notes,
            "transaction_count": transaction_count,
        }

    def _serialize_transaction(
        self,
        transaction: PortfolioLedgerTransactionModel,
    ) -> dict[str, Any]:
        return {
            "id": transaction.id,
            "symbol": transaction.symbol,
            "trade_type": transaction.trade_type,
            "quantity": transaction.quantity,
            "price": transaction.price,
            "amount": transaction.amount,
            "trade_date": transaction.trade_date,
            "benchmark_symbol": transaction.benchmark_symbol,
            "tags": list(transaction.tags or []),
            "notes": transaction.notes,
        }

    def _serialize_snapshot(self, snapshot: PortfolioLedgerSnapshotModel) -> dict[str, Any]:
        return {
            "date": snapshot.snapshot_date,
            "snapshot_index": snapshot.snapshot_index,
            "cash_flow": snapshot.cash_flow,
            "nav": snapshot.nav,
        }

    def _normalize_tags(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]


def get_portfolio_ledger_service(db: AsyncSession) -> PortfolioLedgerService:
    return PortfolioLedgerService(db)
