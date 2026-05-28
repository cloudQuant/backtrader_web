"""Log parsing helpers for backtest / simulate / live runs.

The original :mod:`app.services.log_parser_service` was a 956-line single file
containing four format-specific readers, several normalisation helpers, the
equity-curve synthesiser and a dozen format-specific ``parse_*`` entry points.

Iteration 174 (C7) split that surface into focused sub-modules:

- :mod:`log_parser.readers` — file format readers (TSV / JSON-Lines / pipe).
- :mod:`log_parser.normalize` — small pure helpers (``_safe_float``,
  date/time / truthy / indicator extraction).
- :mod:`log_parser.computations` — strategy config loading, initial-cash
  resolution, equity-curve synthesis.

The legacy ``app.services.log_parser_service`` module remains as a thin
re-export facade so callers continue to use ``parse_value_log`` /
``parse_trade_log`` / etc. without changes.
"""

__all__: list[str] = []
