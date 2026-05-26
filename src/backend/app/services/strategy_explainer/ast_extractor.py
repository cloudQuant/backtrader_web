"""Static AST extraction for Backtrader strategy code."""

from __future__ import annotations

import ast
from typing import Any

from app.schemas.strategy_explanation import (
    StrategyIndicator,
    StrategyParamInfo,
    StrategyRiskControl,
    StrategySignal,
    StrategyStructure,
)


def extract_strategy_structure(source_code: str) -> StrategyStructure:
    """Extract common Backtrader strategy structure from Python source."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        return StrategyStructure(
            parsable=False,
            raw_code=source_code,
            parse_error=str(exc),
        )

    extractor = _StrategyAstExtractor(source_code)
    extractor.visit(tree)
    return StrategyStructure(
        parsable=True,
        indicators=extractor.indicators,
        entry_signals=extractor.entry_signals,
        exit_signals=extractor.exit_signals,
        risk_controls=extractor.risk_controls,
        params=extractor.params,
        data_sources=sorted(extractor.data_sources),
    )


class _StrategyAstExtractor(ast.NodeVisitor):
    def __init__(self, source_code: str) -> None:
        self.source_code = source_code
        self.indicators: list[StrategyIndicator] = []
        self.entry_signals: list[StrategySignal] = []
        self.exit_signals: list[StrategySignal] = []
        self.risk_controls: list[StrategyRiskControl] = []
        self.params: list[StrategyParamInfo] = []
        self.data_sources: set[str] = set()
        self._current_condition: str | None = None
        self._param_names: set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for statement in node.body:
            if isinstance(statement, ast.Assign):
                self._extract_params(statement)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            alias = _self_attribute_name(target)
            if alias and isinstance(node.value, ast.Call):
                indicator_name = _indicator_name(node.value.func)
                if indicator_name:
                    self.indicators.append(
                        StrategyIndicator(
                            name=indicator_name,
                            alias=alias,
                            params=_call_keyword_params(node.value),
                        )
                    )
            data_source = _data_source_name(target)
            if data_source:
                self.data_sources.add(data_source)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        previous_condition = self._current_condition
        self._current_condition = _source_segment(self.source_code, node.test)
        for statement in node.body:
            self.visit(statement)
        for statement in node.orelse:
            self.visit(statement)
        self._current_condition = previous_condition

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in {"buy", "sell", "close", "order_target_percent", "order_target_size"}:
            condition = self._current_condition or "direct call"
            if call_name in {"buy", "order_target_percent", "order_target_size"}:
                self.entry_signals.append(StrategySignal(condition=condition, side="buy"))
            else:
                self.exit_signals.append(StrategySignal(condition=condition, side=call_name))
        for keyword in node.keywords:
            if keyword.arg == "size":
                self.risk_controls.append(
                    StrategyRiskControl(
                        type="position_size",
                        value=_literal_or_source(self.source_code, keyword.value),
                        source=_source_segment(self.source_code, keyword.value),
                    )
                )
            if call_name == "order_target_percent" and keyword.arg in {"target", "percent"}:
                self.risk_controls.append(
                    StrategyRiskControl(
                        type="target_percent",
                        value=_literal_or_source(self.source_code, keyword.value),
                        source=_source_segment(self.source_code, keyword.value),
                    )
                )
            if call_name == "order_target_size" and keyword.arg in {"target", "size"}:
                self.risk_controls.append(
                    StrategyRiskControl(
                        type="target_size",
                        value=_literal_or_source(self.source_code, keyword.value),
                        source=_source_segment(self.source_code, keyword.value),
                    )
                )
        self.generic_visit(node)

    def _extract_params(self, node: ast.Assign) -> None:
        if not any(_target_name(target) == "params" for target in node.targets):
            return
        if isinstance(node.value, ast.Call) and _call_name(node.value.func) == "dict":
            self._extract_dict_params(node.value)
            return
        if not isinstance(node.value, (ast.Tuple, ast.List)):
            return
        for item in node.value.elts:
            if not isinstance(item, ast.Tuple) or len(item.elts) < 2:
                continue
            name = _literal_or_source(self.source_code, item.elts[0])
            if not isinstance(name, str):
                continue
            self._add_param(
                name,
                _literal_or_source(self.source_code, item.elts[1]),
            )

    def _extract_dict_params(self, call: ast.Call) -> None:
        for keyword in call.keywords:
            if not keyword.arg:
                continue
            self._add_param(
                keyword.arg,
                _literal_or_source(self.source_code, keyword.value),
            )

    def _add_param(self, name: str, default: Any) -> None:
        if name in self._param_names:
            return
        self._param_names.add(name)
        self.params.append(StrategyParamInfo(name=name, default=default))
        lower_name = name.lower()
        if any(token in lower_name for token in ("stop_loss", "stoploss", "trailing_stop")):
            self.risk_controls.append(
                StrategyRiskControl(
                    type="stop_loss_param",
                    value=default,
                    source=name,
                )
            )


def _target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _self_attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        return node.attr
    return None


def _data_source_name(node: ast.AST) -> str | None:
    alias = _self_attribute_name(node)
    if alias and alias in {"data", "close", "open", "high", "low", "volume"}:
        return alias
    return None


def _indicator_name(func: ast.AST) -> str | None:
    dotted = _dotted_name(func)
    if not dotted:
        return None
    if ".indicators." in dotted:
        return dotted.rsplit(".", maxsplit=1)[-1]
    if dotted.startswith("bt.ind.") or dotted.startswith("bt.talib."):
        return dotted.rsplit(".", maxsplit=1)[-1]
    return None


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _call_keyword_params(call: ast.Call) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for keyword in call.keywords:
        if keyword.arg:
            params[keyword.arg] = _literal_or_source("", keyword.value)
    return params


def _literal_or_source(source_code: str, node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return _source_segment(source_code, node) or ast.dump(node)


def _source_segment(source_code: str, node: ast.AST) -> str:
    if source_code:
        return ast.get_source_segment(source_code, node) or ast.dump(node)
    return ast.unparse(node) if hasattr(ast, "unparse") else ast.dump(node)
