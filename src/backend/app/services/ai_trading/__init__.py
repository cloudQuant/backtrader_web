"""AI trading helpers split out of ``app.services.ai_trading_service``.

Iteration 174 (C9) carved off the message-formatting helpers and the
conditional-order manager into focused submodules so the orchestrator class
can stay readable. The public entry points
(:class:`AITradingService`, :class:`ConditionalOrderManager`,
``get_conditional_order_manager``, ``MissingGatewayContextError``) continue to
live on / re-export from :mod:`app.services.ai_trading_service`.
"""

# Iteration 175 §1.5 (Mypy strict scope) — known residual Any sources:
# any-source: llm-payloads - litellm response shape varies by provider, treated as Any
# any-source: order-context - heterogeneous gateway ack payloads use dict[str, Any]
# (Caps per Requirement 1.5: ≤5 categories per subpackage; mirrored in
# docs/iterations/迭代175-质量加固与可观测性纵深/PROGRESS.md §1 "已知尾巴")

__all__: list[str] = []
