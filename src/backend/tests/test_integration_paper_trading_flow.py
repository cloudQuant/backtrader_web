"""Integration tests for the complete paper-trading round-trip.

Exercises the real service + persistence layer (no service mocks) against the
DB configured for the test session — on CI this is the Postgres service
container, locally it is the sqlite/Postgres test DB from conftest.

Round-trip covered:
    create account -> submit market buy (fills asynchronously) -> poll until
    filled -> position opened -> trade recorded -> account cash decreased ->
    submit market sell (closes) -> account deleted.

Backlog: REFACTORING_BACKLOG.md P2#9 (integration coverage for paper/live flow).
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_BASE = "/api/v1/paper-trading"
_SYMBOL = "000001.SZ"  # _get_simulated_price returns a deterministic 10.5 for 000001


async def _poll_order_status(
    client: AsyncClient, account_id: str, order_id: str, headers: dict, target: str
) -> dict:
    """Poll the order list until the order reaches *target* status (or times out).

    Paper orders fill via a fire-and-forget ``asyncio.create_task`` in the
    service, so the POST returns ``pending`` and the fill lands shortly after.
    """
    last: dict = {}
    for _ in range(50):  # ~5s budget
        resp = await client.get(
            f"{_BASE}/orders", params={"account_id": account_id}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        for order in resp.json()["items"]:
            if order["id"] == order_id:
                last = order
                if order["status"] == target:
                    return order
        await asyncio.sleep(0.1)
    return last


class TestPaperTradingRoundTrip:
    """End-to-end paper-trading lifecycle against the real service layer."""

    async def test_full_paper_trading_lifecycle(self, client: AsyncClient, auth_headers: dict):
        # Step 1: create a paper-trading account
        create_resp = await client.post(
            f"{_BASE}/accounts",
            json={
                "name": "Integration Account",
                "initial_cash": 100000.0,
                "commission_rate": 0.001,
                "slippage_rate": 0.001,
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 200, create_resp.text
        account = create_resp.json()
        account_id = account["id"]
        assert account["current_cash"] == pytest.approx(100000.0)
        assert account["initial_cash"] == pytest.approx(100000.0)

        # Step 2: submit a market BUY order (fills asynchronously)
        buy_resp = await client.post(
            f"{_BASE}/orders",
            json={
                "account_id": account_id,
                "symbol": _SYMBOL,
                "order_type": "market",
                "side": "buy",
                "size": 1000,
            },
            headers=auth_headers,
        )
        assert buy_resp.status_code == 200, buy_resp.text
        buy_order = buy_resp.json()
        assert buy_order["status"] in ("pending", "filled")

        # Step 3: poll until the buy order is filled
        filled = await _poll_order_status(
            client, account_id, buy_order["id"], auth_headers, "filled"
        )
        assert filled.get("status") == "filled", f"order did not fill: {filled}"
        assert filled["filled_size"] == 1000
        assert filled["avg_fill_price"] > 0

        # Step 4: a position was opened for the symbol
        positions_resp = await client.get(
            f"{_BASE}/positions",
            params={"account_id": account_id},
            headers=auth_headers,
        )
        assert positions_resp.status_code == 200, positions_resp.text
        positions = positions_resp.json()["items"]
        position = next((p for p in positions if p["symbol"] == _SYMBOL), None)
        assert position is not None, f"no position opened for {_SYMBOL}: {positions}"
        assert position["size"] == 1000

        # Step 5: a trade was recorded
        trades_resp = await client.get(
            f"{_BASE}/trades",
            params={"account_id": account_id},
            headers=auth_headers,
        )
        assert trades_resp.status_code == 200, trades_resp.text
        trades = trades_resp.json()["items"]
        assert len(trades) >= 1

        # Step 6: account cash decreased by ~ (fill_price * size + commission)
        acct_resp = await client.get(
            f"{_BASE}/accounts/{account_id}",
            headers=auth_headers,
        )
        assert acct_resp.status_code == 200, acct_resp.text
        acct_after_buy = acct_resp.json()
        assert acct_after_buy["current_cash"] < 100000.0

        # Step 7: close the position with a market SELL
        sell_resp = await client.post(
            f"{_BASE}/orders",
            json={
                "account_id": account_id,
                "symbol": _SYMBOL,
                "order_type": "market",
                "side": "sell",
                "size": 1000,
            },
            headers=auth_headers,
        )
        assert sell_resp.status_code == 200, sell_resp.text
        sell_filled = await _poll_order_status(
            client, account_id, sell_resp.json()["id"], auth_headers, "filled"
        )
        assert sell_filled.get("status") == "filled", f"sell did not fill: {sell_filled}"

        # Step 8: clean up — delete the account
        del_resp = await client.delete(
            f"{_BASE}/accounts/{account_id}",
            headers=auth_headers,
        )
        assert del_resp.status_code in (200, 204), del_resp.text

    async def test_order_rejected_for_insufficient_cash(
        self, client: AsyncClient, auth_headers: dict
    ):
        """A buy far exceeding cash must not result in a filled position."""
        create_resp = await client.post(
            f"{_BASE}/accounts",
            json={"name": "Tiny Account", "initial_cash": 100.0},
            headers=auth_headers,
        )
        assert create_resp.status_code == 200, create_resp.text
        account_id = create_resp.json()["id"]

        # 100000 shares @ ~10.5 = far more than 100 cash
        resp = await client.post(
            f"{_BASE}/orders",
            json={
                "account_id": account_id,
                "symbol": _SYMBOL,
                "order_type": "market",
                "side": "buy",
                "size": 100000,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        order_id = resp.json()["id"]

        # The async fill path must reject (insufficient funds), never fill.
        final = await _poll_order_status(client, account_id, order_id, auth_headers, "rejected")
        assert final.get("status") == "rejected", f"expected rejection, got {final}"

        # Account cash must be untouched.
        acct = await client.get(f"{_BASE}/accounts/{account_id}", headers=auth_headers)
        assert acct.json()["current_cash"] == pytest.approx(100.0)

        await client.delete(f"{_BASE}/accounts/{account_id}", headers=auth_headers)
