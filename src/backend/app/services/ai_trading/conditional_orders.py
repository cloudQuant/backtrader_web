"""Conditional ("trigger") order manager.

Conditional orders are stored in a process-local dict and periodically checked
against market conditions. When the condition is met, the order is executed.

Example conditions:
- "如果BTC跌到60000就买入0.1个"
- "螺纹钢涨到4000就卖出"
- "如果持仓亏损超过5%就平仓"
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# In-memory store for conditional orders (production should use DB).
# This dict is intentionally module-level so legacy callers can do
# ``from app.services.ai_trading_service import _conditional_orders`` and
# ``_conditional_orders.clear()`` between tests.
_conditional_orders: dict[str, dict[str, Any]] = {}


class ConditionalOrderManager:
    """Manages conditional (trigger) orders."""

    def create_conditional_order(
        self,
        user_id: str,
        condition: str,
        action_message: str,
        gateway_id: str | None = None,
        dry_run: bool = True,
        expiry_hours: float = 24.0,
    ) -> dict[str, Any]:
        """Create a new conditional order."""
        order_id = str(uuid.uuid4())[:12]
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expiry_hours)

        order_data = {
            "id": order_id,
            "user_id": user_id,
            "condition": condition,
            "action_message": action_message,
            "gateway_id": gateway_id,
            "dry_run": dry_run,
            "status": "active",
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "triggered_at": None,
        }

        _conditional_orders[order_id] = order_data
        logger.info(
            "Created conditional order %s: %s → %s",
            order_id,
            condition,
            action_message,
        )

        return order_data

    def list_conditional_orders(self, user_id: str) -> list[dict[str, Any]]:
        """List all conditional orders for a user."""
        self._expire_old_orders()
        return [
            order
            for order in _conditional_orders.values()
            if order["user_id"] == user_id
        ]

    def cancel_conditional_order(self, order_id: str, user_id: str) -> bool:
        """Cancel a conditional order owned by ``user_id``."""
        order = _conditional_orders.get(order_id)
        if not order or order["user_id"] != user_id:
            return False
        order["status"] = "cancelled"
        return True

    def _expire_old_orders(self) -> None:
        """Mark expired orders as ``status='expired'``."""
        now = datetime.now(timezone.utc)
        for order in _conditional_orders.values():
            if order["status"] == "active":
                expires_at = datetime.fromisoformat(order["expires_at"])
                if now > expires_at:
                    order["status"] = "expired"


# Global singleton (lazy)
_conditional_order_manager: ConditionalOrderManager | None = None


def get_conditional_order_manager() -> ConditionalOrderManager:
    """Get or create the conditional order manager singleton."""
    global _conditional_order_manager
    if _conditional_order_manager is None:
        _conditional_order_manager = ConditionalOrderManager()
    return _conditional_order_manager
