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

# Iteration 175 §1.5 (Mypy strict scope) — known residual Any sources:
# any-source: pandas-frames - pandas.DataFrame.iterrows / row[col] resolves to Any
# any-source: heterogeneous-rows - parse_*_log returns list[dict[str, Any]] by contract
# (Caps per Requirement 1.5: ≤5 categories per subpackage; mirrored in
# docs/iterations/迭代175-质量加固与可观测性纵深/PROGRESS.md §1 "已知尾巴")

__all__: list[str] = []
