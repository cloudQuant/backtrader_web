"""Strategy validation, quality gates, and robustness promotion helpers."""

# Workflow helpers are injected after every stage is loaded; see research.__init__.
# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405
from .shared import *


def _validate_strategy_code_draft(code: str) -> None:
    text = str(code or "").strip()
    if not text:
        raise ValueError("strategy code is empty")
    try:
        StrategySandbox._check_code_safety(text)
        tree = ast.parse(text, filename="<ai_strategy_draft>")
    except SyntaxError as exc:
        raise ValueError(f"strategy code syntax error: {exc}") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"strategy code safety check failed: {exc}") from exc

    strategy_node = next(
        (node for node in ast.walk(tree) if _is_backtrader_strategy_class(node)),
        None,
    )
    if strategy_node is None:
        raise ValueError("strategy code must define a class inheriting from bt.Strategy")
    _validate_strategy_runtime_dependencies(tree)
    _validate_strategy_class_completeness(strategy_node, text)
    settings = get_settings()
    try:
        StrategySandbox.validate_strategy_code(
            text,
            timeout=3,
            use_docker=(
                production_security_mode(settings) and settings.AI_STRATEGY_SANDBOX_USE_DOCKER
            ),
            docker_image=settings.AI_STRATEGY_SANDBOX_DOCKER_IMAGE,
        )
    except SandboxPreflightError as exc:
        raise ValueError(f"strategy code preflight backtest failed: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"strategy code sandbox validation failed: {exc}") from exc


def _validate_strategy_runtime_dependencies(tree: ast.AST) -> None:
    forbidden_modules = {"pandas", "numpy"}
    forbidden_names = {"pd", "np", "pandas", "numpy"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = str(alias.name or "").split(".", maxsplit=1)[0]
                if module_name in forbidden_modules:
                    raise ValueError("strategy code must not depend on pandas/numpy at runtime")
        elif isinstance(node, ast.ImportFrom):
            module_name = str(node.module or "").split(".", maxsplit=1)[0]
            if module_name in forbidden_modules:
                raise ValueError("strategy code must not depend on pandas/numpy at runtime")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in forbidden_names:
                raise ValueError("strategy code must not depend on pandas/numpy at runtime")


def _validate_strategy_class_completeness(strategy_node: ast.ClassDef, code: str) -> None:
    methods = {
        item.name: item
        for item in strategy_node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if "__init__" not in methods:
        raise ValueError("strategy code must define __init__")
    if "next" not in methods:
        raise ValueError("strategy code must define next")
    for node in ast.walk(strategy_node):
        if isinstance(node, ast.Pass):
            raise ValueError("strategy code must not contain pass placeholders")
        if _is_ellipsis_expr(node):
            raise ValueError("strategy code must not contain ellipsis placeholders")
        if _is_not_implemented_placeholder(node):
            raise ValueError("strategy code must not contain NotImplemented placeholders")
    if _contains_placeholder_comment(code):
        raise ValueError("strategy code must not contain TODO or placeholder comments")
    if not any(_is_trade_action_call(node) for node in ast.walk(methods["next"])):
        raise ValueError("strategy code next method must place or close orders")


def _is_ellipsis_expr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and node.value.value is Ellipsis
    )


def _is_not_implemented_placeholder(node: ast.AST) -> bool:
    if isinstance(node, ast.Raise):
        exc = node.exc
        if isinstance(exc, ast.Name):
            return exc.id == "NotImplementedError"
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            return exc.func.id == "NotImplementedError"
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
        return node.value.value is NotImplemented
    return False


def _contains_placeholder_comment(code: str) -> bool:
    placeholders = ("TODO", "todo", "待实现", "省略", "伪代码")
    try:
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        return any(
            token.type == tokenize.COMMENT
            and any(marker in token.string for marker in placeholders)
            for token in tokens
        )
    except tokenize.TokenError:
        return True


def _is_trade_action_call(node: ast.AST) -> bool:
    trade_actions = {
        "buy",
        "sell",
        "close",
        "order_target_percent",
        "order_target_size",
        "order_target_value",
        "buy_bracket",
        "sell_bracket",
    }
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in trade_actions:
        return False
    return isinstance(node.func.value, ast.Name) and node.func.value.id == "self"


def _is_backtrader_strategy_class(node: ast.AST) -> bool:
    if not isinstance(node, ast.ClassDef):
        return False
    return any(_is_backtrader_strategy_base(base) for base in node.bases)


def _is_backtrader_strategy_base(base: ast.AST) -> bool:
    if isinstance(base, ast.Attribute) and base.attr == "Strategy":
        return _ast_name(base.value) in {"bt", "backtrader"}
    if isinstance(base, ast.Name):
        return base.id == "Strategy"
    return False


def _ast_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _ast_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _quality_gate_failures(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    sharpe = _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
    total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
    if sharpe is None:
        failures.append("Sharpe metric unavailable")
    elif sharpe < request.target_sharpe:
        failures.append(f"Sharpe {sharpe:.3f} below target {request.target_sharpe:.3f}")
    if total_trades < request.min_total_trades:
        failures.append(f"Only {total_trades} trades, below minimum {request.min_total_trades}")

    if request.max_drawdown_limit is not None:
        max_drawdown = _quality_metric(
            metrics,
            "max_drawdown",
            "maxDrawdown",
            "drawdown",
            "max_dd",
            "maxDD",
        )
        if max_drawdown is None:
            failures.append("Max drawdown metric unavailable")
        else:
            comparable = abs(_align_metric_scale(max_drawdown, request.max_drawdown_limit))
            if comparable > abs(request.max_drawdown_limit):
                failures.append(
                    f"Max drawdown {comparable:.3f} exceeds limit "
                    f"{abs(request.max_drawdown_limit):.3f}"
                )

    if request.min_total_return is not None:
        total_return = _quality_metric(metrics, "total_return", "totalReturn", "return")
        if total_return is None:
            failures.append("Total return metric unavailable")
        else:
            comparable = _align_metric_scale(total_return, request.min_total_return)
            if comparable < request.min_total_return:
                failures.append(
                    f"Total return {comparable:.3f} below minimum {request.min_total_return:.3f}"
                )

    if request.min_annual_return is not None:
        annual_return = _quality_metric(metrics, "annual_return", "annualReturn")
        if annual_return is None:
            failures.append("Annual return metric unavailable")
        else:
            comparable = _align_metric_scale(annual_return, request.min_annual_return)
            if comparable < request.min_annual_return:
                failures.append(
                    f"Annual return {comparable:.3f} below minimum {request.min_annual_return:.3f}"
                )

    if request.min_win_rate is not None:
        win_rate = _quality_metric(metrics, "win_rate", "winRate")
        if win_rate is None:
            failures.append("Win rate metric unavailable")
        else:
            comparable = _align_metric_scale(win_rate, request.min_win_rate)
            if comparable < request.min_win_rate:
                failures.append(
                    f"Win rate {comparable:.3f} below minimum {request.min_win_rate:.3f}"
                )

    return failures


def _research_completion_message(
    *,
    request: AIStrategyResearchRunRequest,
    achieved: bool,
    result_iteration: Any | None,
    run_failures: list[str],
) -> str:
    if achieved:
        return "Quality gates achieved"

    failures: list[str] = []
    if result_iteration is not None:
        failures = [
            str(item).strip()
            for item in getattr(result_iteration, "quality_gate_failures", []) or []
            if str(item or "").strip()
        ]

    if failures:
        shown = "; ".join(failures[:3])
        suffix = f"; +{len(failures) - 3} more" if len(failures) > 3 else ""
        return f"Quality gates not achieved: {shown}{suffix}"

    if run_failures:
        latest = str(run_failures[-1] or "").strip()
        if latest:
            return f"Backtest submission failed: {latest[:220]}"

    return f"Target Sharpe {request.target_sharpe:.3f} not achieved"


def _parse_iso_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _out_of_sample_window(request: AIStrategyResearchRunRequest) -> OutOfSampleWindow | None:
    if not request.out_of_sample_validation:
        return None
    start = _parse_iso_date(request.start_date)
    end = _parse_iso_date(request.end_date)
    if start is None or end is None or end <= start:
        return None
    total_days = (end - start).days + 1
    if total_days < 8:
        return None
    validation_days = max(int(total_days * request.out_of_sample_ratio), 1)
    validation_days = min(validation_days, total_days - 2)
    validation_start = end - timedelta(days=validation_days - 1)
    train_end = validation_start - timedelta(days=1)
    if train_end <= start or validation_start > end:
        return None
    return OutOfSampleWindow(
        train_start=start.isoformat(),
        train_end=train_end.isoformat(),
        validation_start=validation_start.isoformat(),
        validation_end=end.isoformat(),
    )


def _required_out_of_sample_validation_failure(
    request: AIStrategyResearchRunRequest,
) -> str | None:
    if not request.require_out_of_sample_validation:
        return None
    if not request.out_of_sample_validation:
        return "Required out-of-sample validation is enabled but out_of_sample_validation is false"
    if _out_of_sample_window(request) is not None:
        return None
    return (
        "Required out-of-sample validation needs valid start_date/end_date "
        "with at least 8 calendar days"
    )


def _required_research_configuration_failure(
    request: AIStrategyResearchRunRequest,
) -> str | None:
    out_of_sample_failure = _required_out_of_sample_validation_failure(request)
    if out_of_sample_failure:
        return out_of_sample_failure
    if request.require_robustness_validation and not request.robustness_validation:
        return "Required robustness validation is enabled but robustness_validation is false"
    if request.robustness_validation and not request.robustness_methods:
        return "Robustness validation requires at least one robustness method"
    return None


def _out_of_sample_min_sharpe(request: AIStrategyResearchRunRequest) -> float:
    if request.min_out_of_sample_sharpe is not None:
        return request.min_out_of_sample_sharpe
    return round(request.target_sharpe * 0.6, 6)


def _out_of_sample_min_trades(request: AIStrategyResearchRunRequest) -> int:
    if request.min_out_of_sample_trades is not None:
        return request.min_out_of_sample_trades
    if request.min_total_trades <= 0:
        return 0
    return max(1, int(round(request.min_total_trades * request.out_of_sample_ratio)))


def _out_of_sample_failures(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
    *,
    run_status: str | None,
) -> list[str]:
    failures: list[str] = []
    if run_status != "completed":
        failures.append(f"Out-of-sample backtest finished with status {run_status or 'unknown'}")
        return failures

    min_sharpe = _out_of_sample_min_sharpe(request)
    sharpe = _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
    if sharpe is None:
        failures.append("Out-of-sample Sharpe metric unavailable")
    elif sharpe < min_sharpe:
        failures.append(f"Out-of-sample Sharpe {sharpe:.3f} below minimum {min_sharpe:.3f}")

    min_trades = _out_of_sample_min_trades(request)
    total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
    if total_trades < min_trades:
        failures.append(f"Out-of-sample only {total_trades} trades, below minimum {min_trades}")

    if request.max_drawdown_limit is not None:
        max_drawdown = _quality_metric(
            metrics,
            "max_drawdown",
            "maxDrawdown",
            "drawdown",
            "max_dd",
            "maxDD",
        )
        if max_drawdown is None:
            failures.append("Out-of-sample max drawdown metric unavailable")
        else:
            comparable = abs(_align_metric_scale(max_drawdown, request.max_drawdown_limit))
            if comparable > abs(request.max_drawdown_limit):
                failures.append(
                    f"Out-of-sample max drawdown {comparable:.3f} exceeds limit "
                    f"{abs(request.max_drawdown_limit):.3f}"
                )

    return failures


def _out_of_sample_gate_evaluations(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
    *,
    run_status: str | None,
) -> list[dict[str, Any]]:
    if run_status != "completed":
        return []
    evaluations = [
        _minimum_gate_evaluation(
            "out_of_sample_sharpe",
            "Out-of-sample Sharpe",
            _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio"),
            _out_of_sample_min_sharpe(request),
        ),
        _minimum_gate_evaluation(
            "out_of_sample_total_trades",
            "Out-of-sample total trades",
            float(_metric_int(metrics, "total_trades", "totalTrades", "trades")),
            float(_out_of_sample_min_trades(request)),
        ),
    ]
    if request.max_drawdown_limit is not None:
        max_drawdown = _quality_metric(
            metrics,
            "max_drawdown",
            "maxDrawdown",
            "drawdown",
            "max_dd",
            "maxDD",
        )
        comparable = (
            abs(_align_metric_scale(max_drawdown, request.max_drawdown_limit))
            if max_drawdown is not None
            else None
        )
        evaluations.append(
            _maximum_gate_evaluation(
                "out_of_sample_max_drawdown",
                "Out-of-sample max drawdown",
                comparable,
                abs(request.max_drawdown_limit),
            )
        )
    return evaluations


def _robustness_validation_request(
    request: AIStrategyResearchRunRequest,
    *,
    run_id: str,
) -> RobustnessValidationRequest:
    return RobustnessValidationRequest(
        methods=list(request.robustness_methods or ["monte_carlo"]),
        min_robustness_score=request.min_robustness_score,
        require_no_high_risk=True,
        monte_carlo_iterations=request.robustness_monte_carlo_iterations,
        random_seed=request.robustness_random_seed,
        run_id=run_id,
    )


def _robustness_gate_payloads(result: dict[str, Any]) -> list[dict[str, Any]]:
    gates = result.get("gate_evaluations")
    if not isinstance(gates, list):
        return []
    return [dict(item) for item in gates if isinstance(item, dict)]


def _robustness_failures_from_result(
    result: dict[str, Any],
    *,
    require_robustness: bool,
) -> list[str]:
    if not require_robustness:
        return []
    failures: list[str] = []
    for gate in _robustness_gate_payloads(result):
        if gate.get("passed") is True:
            continue
        message = str(gate.get("message") or gate.get("label") or gate.get("key") or "").strip()
        failures.append(message or "Robustness validation gate failed")
    status = str(result.get("status") or "").strip()
    if status and status != "passed" and not failures:
        failures.append(str(result.get("error_message") or "Robustness validation failed"))
    return failures


def _robustness_gate_evaluations_for_promotion(
    iteration: AIStrategyResearchIteration,
) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for item in iteration.robustness_gate_evaluations:
        if not isinstance(item, dict):
            continue
        payload = dict(item)
        payload.setdefault("target", payload.get("threshold"))
        payload.setdefault("direction", _robustness_gate_direction(payload.get("operator")))
        payload.setdefault("passed", bool(payload.get("passed")))
        payload.setdefault("score", 1.0 if payload["passed"] else 0.0)
        payload.setdefault("status", "passed" if payload["passed"] else "failed")
        payload.setdefault("failure_reason", payload.get("message") or "")
        evaluations.append(payload)
    if (
        iteration.robustness_status == "failed"
        and not evaluations
        and iteration.robustness_failure_reason
    ):
        evaluations.append(
            {
                "key": "robustness_validation",
                "label": "稳健性验证",
                "actual": 0.0,
                "target": 1.0,
                "direction": "min",
                "passed": False,
                "score": 0.0,
                "status": "failed",
                "failure_reason": iteration.robustness_failure_reason,
            }
        )
    return evaluations


def _robustness_gate_direction(operator: Any) -> str:
    text = str(operator or "").strip()
    if text in {"<", "<=", "!="}:
        return "max"
    return "min"


def _improvement_metrics(
    metrics: dict[str, Any],
    validation_metrics: dict[str, Any],
    *,
    iteration_progress: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(metrics)
    feedback = _improvement_feedback_payload(diagnostics)
    if feedback:
        merged["research_feedback"] = feedback
        for key in (
            "failure_categories",
            "strengths",
            "weaknesses",
            "gate_gaps",
            "improvement_plan",
            "promotion_ready",
            "out_of_sample_validation",
            "robustness_validation",
        ):
            if key in feedback:
                merged[key] = feedback[key]
        if iteration_progress is None and isinstance(feedback.get("iteration_progress"), dict):
            iteration_progress = feedback["iteration_progress"]
    if iteration_progress:
        merged["iteration_progress"] = dict(iteration_progress)
    if not validation_metrics:
        return merged
    merged["out_of_sample"] = dict(validation_metrics)
    for source_key, target_key in (
        ("sharpe_ratio", "out_of_sample_sharpe"),
        ("total_trades", "out_of_sample_total_trades"),
        ("max_drawdown", "out_of_sample_max_drawdown"),
        ("total_return", "out_of_sample_total_return"),
    ):
        if source_key in validation_metrics:
            merged[target_key] = validation_metrics[source_key]
    return merged


def _improvement_feedback_payload(diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(diagnostics, dict) or not diagnostics:
        return {}
    payload: dict[str, Any] = {}
    for key in (
        "summary",
        "failure_categories",
        "strengths",
        "weaknesses",
        "gate_gaps",
        "iteration_progress",
        "improvement_plan",
        "promotion_ready",
        "out_of_sample_validation",
        "robustness_validation",
    ):
        value = diagnostics.get(key)
        if isinstance(value, dict):
            payload[key] = dict(value)
        elif isinstance(value, list):
            payload[key] = list(value)
        elif value is not None:
            payload[key] = value
    return payload


def _is_better_research_candidate(
    candidate: AIStrategyResearchIteration,
    current: AIStrategyResearchIteration,
) -> bool:
    candidate_key = (
        1 if candidate.passed else 0,
        _promotion_quality_score(candidate),
        candidate.sharpe_ratio,
        candidate.total_trades,
        -candidate.iteration,
    )
    current_key = (
        1 if current.passed else 0,
        _promotion_quality_score(current),
        current.sharpe_ratio,
        current.total_trades,
        -current.iteration,
    )
    return candidate_key > current_key


def _promotion_gate_evaluations(
    iteration: AIStrategyResearchIteration | None,
) -> list[dict[str, Any]]:
    if iteration is None:
        return []

    evaluations = [
        dict(item) for item in iteration.quality_gate_evaluations if isinstance(item, dict)
    ]
    seen = {str(item.get("key") or "") for item in evaluations}
    for item in iteration.validation_gate_evaluations:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if key and key in seen:
            continue
        evaluations.append(dict(item))
        if key:
            seen.add(key)

    for item in _robustness_gate_evaluations_for_promotion(iteration):
        key = str(item.get("key") or "").strip()
        if key and key in seen:
            continue
        evaluations.append(dict(item))
        if key:
            seen.add(key)

    if (
        iteration.validation_status == "failed"
        and not iteration.validation_gate_evaluations
        and "out_of_sample_validation" not in seen
    ):
        evaluations.append(
            {
                "key": "out_of_sample_validation",
                "label": "Out-of-sample validation",
                "actual": 0.0,
                "target": 1.0,
                "direction": "min",
                "passed": False,
                "score": 0.0,
                "failure_reason": iteration.validation_failure_reason
                or "; ".join(iteration.validation_failures),
            }
        )
    return evaluations


def _promotion_quality_score(iteration: AIStrategyResearchIteration | None) -> float:
    if iteration is None:
        return 0.0
    evaluations = _promotion_gate_evaluations(iteration)
    if not evaluations:
        return round(float(iteration.quality_score or 0.0), 3)
    return round(
        sum(float(item.get("score", 0.0) or 0.0) for item in evaluations) / len(evaluations) * 100,
        3,
    )


def _quality_score(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
    *,
    run_status: str | None,
) -> float:
    evaluations = _quality_gate_evaluations(request, metrics, run_status=run_status)
    if not evaluations:
        return 0.0
    return round(
        sum(float(item.get("score", 0.0) or 0.0) for item in evaluations) / len(evaluations) * 100,
        3,
    )


def _quality_gate_evaluations(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
    *,
    run_status: str | None,
) -> list[dict[str, Any]]:
    if run_status != "completed":
        return []

    evaluations: list[dict[str, Any]] = []
    sharpe = _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
    evaluations.append(_minimum_gate_evaluation("sharpe", "Sharpe", sharpe, request.target_sharpe))

    total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
    evaluations.append(
        _minimum_gate_evaluation(
            "total_trades",
            "Total trades",
            float(total_trades),
            float(request.min_total_trades),
        )
    )

    if request.max_drawdown_limit is not None:
        max_drawdown = _quality_metric(
            metrics,
            "max_drawdown",
            "maxDrawdown",
            "drawdown",
            "max_dd",
            "maxDD",
        )
        comparable = (
            abs(_align_metric_scale(max_drawdown, request.max_drawdown_limit))
            if max_drawdown is not None
            else None
        )
        evaluations.append(
            _maximum_gate_evaluation(
                "max_drawdown",
                "Max drawdown",
                comparable,
                abs(request.max_drawdown_limit),
            )
        )

    if request.min_total_return is not None:
        total_return = _quality_metric(metrics, "total_return", "totalReturn", "return")
        comparable = (
            _align_metric_scale(total_return, request.min_total_return)
            if total_return is not None
            else None
        )
        evaluations.append(
            _minimum_gate_evaluation(
                "total_return",
                "Total return",
                comparable,
                request.min_total_return,
            )
        )

    if request.min_annual_return is not None:
        annual_return = _quality_metric(metrics, "annual_return", "annualReturn")
        comparable = (
            _align_metric_scale(annual_return, request.min_annual_return)
            if annual_return is not None
            else None
        )
        evaluations.append(
            _minimum_gate_evaluation(
                "annual_return",
                "Annual return",
                comparable,
                request.min_annual_return,
            )
        )

    if request.min_win_rate is not None:
        win_rate = _quality_metric(metrics, "win_rate", "winRate")
        comparable = (
            _align_metric_scale(win_rate, request.min_win_rate) if win_rate is not None else None
        )
        evaluations.append(
            _minimum_gate_evaluation(
                "win_rate",
                "Win rate",
                comparable,
                request.min_win_rate,
            )
        )

    return evaluations


def _minimum_gate_evaluation(
    key: str,
    label: str,
    actual: float | None,
    target: float,
) -> dict[str, Any]:
    score = _minimum_gate_score(actual, target)
    passed = actual is not None and score >= 1.0
    distance = None if actual is None else max(float(target) - float(actual), 0.0)
    return {
        "key": key,
        "label": label,
        "actual": actual,
        "target": target,
        "direction": "min",
        "passed": passed,
        "score": score,
        "margin": _rounded_gate_delta(None if actual is None else float(actual) - float(target)),
        "gap": _rounded_gate_delta(distance),
        "gap_ratio": _gate_gap_ratio(distance, target),
        "distance_to_pass": _rounded_gate_delta(distance),
        "status": "passed" if passed else "unavailable" if actual is None else "failed",
    }


def _maximum_gate_evaluation(
    key: str,
    label: str,
    actual: float | None,
    target: float,
) -> dict[str, Any]:
    score = (
        0.0 if actual is None else 1.0 if actual <= target else max(min(target / actual, 1.0), 0.0)
    )
    passed = actual is not None and actual <= target
    distance = None if actual is None else max(float(actual) - float(target), 0.0)
    return {
        "key": key,
        "label": label,
        "actual": actual,
        "target": target,
        "direction": "max",
        "passed": passed,
        "score": score,
        "margin": _rounded_gate_delta(None if actual is None else float(target) - float(actual)),
        "gap": _rounded_gate_delta(distance),
        "gap_ratio": _gate_gap_ratio(distance, target),
        "distance_to_pass": _rounded_gate_delta(distance),
        "status": "passed" if passed else "unavailable" if actual is None else "failed",
    }


def _rounded_gate_delta(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _gate_gap_ratio(gap: float | None, target: float) -> float | None:
    if gap is None:
        return None
    denominator = abs(float(target))
    if denominator <= 1e-12:
        return None
    return round(float(gap) / denominator, 6)


def _gate_gap_summary(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for item in evaluations:
        if not isinstance(item, dict) or bool(item.get("passed")):
            continue
        gaps.append(
            {
                "key": item.get("key"),
                "label": item.get("label"),
                "direction": item.get("direction"),
                "actual": item.get("actual"),
                "target": item.get("target"),
                "gap": item.get("gap"),
                "gap_ratio": item.get("gap_ratio"),
                "distance_to_pass": item.get("distance_to_pass"),
                "score": item.get("score"),
                "status": item.get("status"),
            }
        )
    gaps.sort(
        key=lambda item: (
            float(item.get("gap_ratio") or -1.0),
            float(item.get("gap") or -1.0),
        ),
        reverse=True,
    )
    return gaps


def _minimum_gate_score(value: float | None, threshold: float) -> float:
    if value is None:
        return 0.0
    if threshold <= 0:
        return 1.0 if value >= threshold else 0.0
    return max(min(value / threshold, 1.0), 0.0)


def _quality_gates_payload(request: AIStrategyResearchRunRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "target_sharpe": request.target_sharpe,
        "min_total_trades": request.min_total_trades,
        "out_of_sample_validation": request.out_of_sample_validation,
        "require_out_of_sample_validation": request.require_out_of_sample_validation,
        "out_of_sample_ratio": request.out_of_sample_ratio,
        "min_paper_trading_days": request.min_paper_trading_days,
    }
    if request.out_of_sample_validation:
        payload["min_out_of_sample_sharpe"] = _out_of_sample_min_sharpe(request)
        payload["min_out_of_sample_trades"] = _out_of_sample_min_trades(request)
    if request.robustness_validation or request.require_robustness_validation:
        payload.update(
            {
                "robustness_validation": request.robustness_validation,
                "require_robustness_validation": request.require_robustness_validation,
                "robustness_methods": list(request.robustness_methods or []),
                "min_robustness_score": request.min_robustness_score,
                "robustness_monte_carlo_iterations": request.robustness_monte_carlo_iterations,
            }
        )
    for key in (
        "max_drawdown_limit",
        "min_total_return",
        "min_annual_return",
        "min_win_rate",
        "min_out_of_sample_sharpe",
        "min_out_of_sample_trades",
    ):
        value = getattr(request, key)
        if value is not None:
            payload[key] = value
    return payload
