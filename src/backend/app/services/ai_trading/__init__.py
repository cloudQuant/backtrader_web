"""AI trading helpers split out of ``app.services.ai_trading_service``.

Iteration 174 (C9) carved off the message-formatting helpers and the
conditional-order manager into focused submodules so the orchestrator class
can stay readable. The public entry points
(:class:`AITradingService`, :class:`ConditionalOrderManager`,
``get_conditional_order_manager``, ``MissingGatewayContextError``) continue to
live on / re-export from :mod:`app.services.ai_trading_service`.
"""

__all__: list[str] = []
