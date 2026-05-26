"""Safe custom factor expression evaluation."""

import ast
import math
import operator
from typing import Any

from app.schemas.factor_lib import CustomFactorResult

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ALLOWED_NAMES = {"open", "high", "low", "close", "volume"}


class CustomFactorService:
    """Calculate custom factors from a restricted arithmetic expression."""

    def calculate(self, *, expression: str, records: list[dict[str, Any]]) -> CustomFactorResult:
        """Evaluate expression for each OHLCV record."""
        try:
            parsed = ast.parse(expression, mode="eval")
            _validate_node(parsed)
        except (SyntaxError, ValueError):
            return CustomFactorResult(status="degraded", reason="unsafe_expression")

        values: list[float | None] = []
        for record in records:
            try:
                value = _eval_node(parsed.body, record)
            except (ArithmeticError, KeyError, TypeError, ValueError):
                values.append(None)
                continue
            values.append(round(float(value), 6) if math.isfinite(float(value)) else None)
        return CustomFactorResult(status="ok", values=values, observation_count=len(values))


def _validate_node(node: ast.AST) -> None:
    if isinstance(node, ast.Expression):
        _validate_node(node.body)
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _ALLOWED_BINOPS:
            raise ValueError("unsupported operator")
        _validate_node(node.left)
        _validate_node(node.right)
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _ALLOWED_UNARYOPS:
            raise ValueError("unsupported unary operator")
        _validate_node(node.operand)
        return
    if isinstance(node, ast.Name):
        if node.id not in _ALLOWED_NAMES:
            raise ValueError("unsupported name")
        return
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return
    raise ValueError("unsupported expression")


def _eval_node(node: ast.AST, record: dict[str, Any]) -> float:
    if isinstance(node, ast.BinOp):
        return _ALLOWED_BINOPS[type(node.op)](_eval_node(node.left, record), _eval_node(node.right, record))
    if isinstance(node, ast.UnaryOp):
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand, record))
    if isinstance(node, ast.Name):
        value = record[node.id]
        if value is None:
            raise ValueError("missing value")
        return float(value)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    raise ValueError("unsupported expression")
