# Iteration 175 §1.5 (Mypy strict scope) — known residual Any sources:
# any-source: backtrader-runtime - third-party `backtrader.*` returns are Any
# any-source: dict-tasks - in-memory task dict still typed `dict[str, Any]`; bounded by submission contract
# any-source: callback-injection - `Callable[..., Any]` knobs for run_async / get_task to keep the API testable
# (Caps per Requirement 1.5: ≤5 categories per subpackage; mirrored in
# docs/iterations/迭代175-质量加固与可观测性纵深/PROGRESS.md §1 "已知尾巴")

__all__ = []
