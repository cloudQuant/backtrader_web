import logging
import math
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from app.services.log_parser_service import parse_log_dir
from app.services.strategy_runtime_support import has_log_artifacts, latest_meaningful_log_subdir

log = logging.getLogger(__name__)


def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def _aggregate_period_returns(
    daily_returns: list[float], period_size: int
) -> list[float]:
    """Group daily returns into period returns (weekly=5, monthly=21)."""
    result = []
    for i in range(0, len(daily_returns), period_size):
        chunk = daily_returns[i : i + period_size]
        period_ret = 1.0
        for r in chunk:
            period_ret *= 1 + r
        result.append((period_ret - 1) * 100)
    return result


def _period_stats(returns_pct: list[float]) -> tuple[float, float, float]:
    """Return (avg, min, max) for a list of returns in percent."""
    if not returns_pct:
        return 0.0, 0.0, 0.0
    avg = sum(returns_pct) / len(returns_pct)
    return avg, min(returns_pct), max(returns_pct)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _persist_trial_artifacts(
    trial_dir: Path,
    artifact_root: str | None,
    trial_index: int,
    result: dict[str, Any],
    stdout_text: str = "",
    stderr_text: str = "",
) -> str | None:
    if not artifact_root:
        return None

    trial_artifact_dir = Path(artifact_root) / f"trial_{trial_index + 1:04d}"
    if trial_artifact_dir.exists():
        shutil.rmtree(trial_artifact_dir)
    trial_artifact_dir.mkdir(parents=True, exist_ok=True)

    config_path = trial_dir / "config.yaml"
    logs_path = trial_dir / "logs"

    if config_path.is_file():
        shutil.copy2(config_path, trial_artifact_dir / "config.yaml")
    if logs_path.is_dir():
        shutil.copytree(logs_path, trial_artifact_dir / "logs", dirs_exist_ok=True)

    params = dict(result.get("params", {}) or {})
    metrics = dict(result.get("metrics", {}) or {})
    trial_status = "success" if result.get("success") else "failed"
    trial_summary = {
        "trial_index": trial_index,
        "trial_name": f"trial_{trial_index + 1:04d}",
        "status": trial_status,
        "success": bool(result.get("success")),
        "params": params,
        "metrics": metrics,
        "error": result.get("error"),
        "exit_code": result.get("exit_code"),
        "artifact_path": str(trial_artifact_dir),
    }

    _write_json(trial_artifact_dir / "params.json", params)
    if metrics:
        _write_json(trial_artifact_dir / "metrics.json", metrics)
    _write_json(trial_artifact_dir / "result.json", {**result, "artifact_path": str(trial_artifact_dir)})
    _write_json(trial_artifact_dir / "summary.json", trial_summary)
    if stdout_text:
        _write_text(trial_artifact_dir / "stdout.txt", stdout_text)
    if stderr_text:
        _write_text(trial_artifact_dir / "stderr.txt", stderr_text)
    return str(trial_artifact_dir)


def parse_trial_logs(
    trial_dir: Path,
    *,
    safe_float_fn: Callable[..., float] = safe_float,
) -> dict[str, float] | None:
    logs_dir = trial_dir / "logs"
    if not logs_dir.is_dir():
        return None

    log_dir = latest_meaningful_log_subdir(logs_dir)
    if log_dir is None:
        if has_log_artifacts(logs_dir):
            log_dir = logs_dir
        else:
            return None

    parsed = parse_log_dir(log_dir, strategy_dir=trial_dir)
    if not parsed:
        return None

    equity = [safe_float_fn(value, 0.0) for value in (parsed.get("equity_curve") or [])]
    trades = list(parsed.get("trades") or [])

    initial = safe_float_fn(
        parsed.get("initial_cash", equity[0] if equity else 100000.0),
        100000.0,
    )
    final = safe_float_fn(
        parsed.get("final_value", equity[-1] if equity else initial),
        initial,
    )
    net_profit = final - initial
    total_return = safe_float_fn(
        parsed.get("total_return", ((net_profit) / initial * 100) if initial > 0 else 0.0),
        0.0,
    )
    net_value = final / initial if initial > 0 else 1.0

    n_days = len(equity)
    annual_return = safe_float_fn(
        parsed.get("annual_return", 0.0),
        0.0,
    )

    # Max drawdown
    peak = 0.0
    max_dd = safe_float_fn(parsed.get("max_drawdown", 0.0), 0.0)
    max_dd_value = 0.0
    max_market_value = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if v > max_market_value:
            max_market_value = v
        dd_abs = peak - v
        dd_pct = (dd_abs / peak * 100) if peak > 0 else 0
        if dd_pct > max_dd:
            max_dd = dd_pct
            max_dd_value = dd_abs

    # Daily returns
    daily_returns: list[float] = []
    if len(equity) > 1:
        daily_returns = [
            (equity[i] - equity[i - 1]) / equity[i - 1]
            for i in range(1, len(equity))
            if equity[i - 1] > 0
        ]

    # Sharpe ratio
    sharpe = safe_float_fn(parsed.get("sharpe_ratio", 0.0), 0.0)

    # Daily return stats (in percent)
    daily_pct = [r * 100 for r in daily_returns]
    daily_avg, daily_min, daily_max = _period_stats(daily_pct)

    # Weekly return stats (5 trading days)
    weekly_pct = _aggregate_period_returns(daily_returns, 5)
    weekly_avg, weekly_min, weekly_max = _period_stats(weekly_pct)

    # Monthly return stats (21 trading days)
    monthly_pct = _aggregate_period_returns(daily_returns, 21)
    monthly_avg, monthly_min, monthly_max = _period_stats(monthly_pct)

    # Return-risk ratio (annual_return / max_drawdown)
    adjusted_return_risk = (
        annual_return / max_dd if max_dd > 0 else 0.0
    )

    # ---- Parse trade log ----
    total_trades = len(trades)
    trade_pnls = [safe_float_fn(trade.get("pnlcomm", 0.0), 0.0) for trade in trades]
    win_trades = len([pnl for pnl in trade_pnls if pnl > 0])
    total_win_amount = sum(pnl for pnl in trade_pnls if pnl > 0)
    total_loss_amount = sum(abs(pnl) for pnl in trade_pnls if pnl <= 0)
    trading_cost = sum(safe_float_fn(trade.get("commission", 0.0), 0.0) for trade in trades)

    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
    loss_trades = total_trades - win_trades
    avg_win = total_win_amount / win_trades if win_trades > 0 else 0
    avg_loss = total_loss_amount / loss_trades if loss_trades > 0 else 0
    avg_profit = sum(trade_pnls) / total_trades if total_trades > 0 else 0
    avg_profit_rate = (avg_profit / initial * 100) if initial > 0 else 0

    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
    profit_factor = total_win_amount / total_loss_amount if total_loss_amount > 0 else 0
    profit_rate_factor = (
        (avg_win / avg_loss) * (win_trades / loss_trades)
        if avg_loss > 0 and loss_trades > 0
        else 0
    )
    profit_loss_rate_ratio = profit_loss_ratio
    odds = (win_rate / 100 * profit_loss_ratio) if profit_loss_ratio > 0 else 0

    return {
        "initial_cash": round(initial, 2),
        "net_value": round(net_value, 4),
        "net_profit": round(net_profit, 2),
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "max_drawdown_value": round(max_dd_value, 2),
        "max_market_value": round(max_market_value, 2),
        "max_leverage": 0,
        "adjusted_return_risk": round(adjusted_return_risk, 4),
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "avg_profit": round(avg_profit, 2),
        "avg_profit_rate": round(avg_profit_rate, 4),
        "total_win_amount": round(total_win_amount, 2),
        "total_loss_amount": round(total_loss_amount, 2),
        "profit_loss_ratio": round(profit_loss_ratio, 4),
        "profit_factor": round(profit_factor, 4),
        "profit_rate_factor": round(profit_rate_factor, 4),
        "profit_loss_rate_ratio": round(profit_loss_rate_ratio, 4),
        "odds": round(odds, 4),
        "daily_avg_return": round(daily_avg, 4),
        "daily_max_loss": round(daily_min, 4),
        "daily_max_profit": round(daily_max, 4),
        "weekly_avg_return": round(weekly_avg, 4),
        "weekly_max_loss": round(weekly_min, 4),
        "weekly_max_profit": round(weekly_max, 4),
        "monthly_avg_return": round(monthly_avg, 4),
        "monthly_max_loss": round(monthly_min, 4),
        "monthly_max_profit": round(monthly_max, 4),
        "trading_days": n_days,
        "trading_cost": round(trading_cost, 2),
        "final_value": round(final, 2),
    }


def run_single_trial(
    strategy_dir: str,
    params: dict[str, Any],
    trial_index: int,
    tmp_base: str,
    artifact_root: str | None = None,
    *,
    parse_trial_logs_fn: Callable[[Path], dict[str, float] | None] = parse_trial_logs,
    subprocess_module: Any = subprocess,
) -> dict[str, Any]:
    strategy_path = Path(strategy_dir)
    trial_dir = Path(tmp_base) / f"trial_{trial_index}"
    result: dict[str, Any] = {"params": params, "trial_index": trial_index, "success": False}
    stdout_text = ""
    stderr_text = ""

    try:
        shutil.copytree(strategy_path, trial_dir, dirs_exist_ok=True)

        logs_dir = trial_dir / "logs"
        if logs_dir.is_dir():
            shutil.rmtree(logs_dir)

        config_path = trial_dir / "config.yaml"
        config: dict[str, Any] = {}
        if config_path.is_file():
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        if "params" not in config:
            config["params"] = {}
        config["params"].update(params)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        run_py = trial_dir / "run.py"

        project_root = Path(strategy_dir).parent.parent
        env = dict(os.environ)
        env["BACKTRADER_DATA_DIR"] = str(project_root / "datas")
        extra_paths = [str(strategy_dir), str(trial_dir)]
        env["PYTHONPATH"] = os.pathsep.join(extra_paths + [env.get("PYTHONPATH", "")])

        proc = subprocess_module.run(
            [sys.executable, "-O", str(run_py)],
            cwd=str(trial_dir),
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        stdout_text = getattr(proc, "stdout", "") or ""
        stderr_text = getattr(proc, "stderr", "") or ""
        return_code = int(getattr(proc, "returncode", 0) or 0)

        if return_code != 0:
            result["exit_code"] = return_code
            result["error"] = (
                stderr_text.strip().split("\n")[-1] if stderr_text else "unknown error"
            )
            return result

        metrics = parse_trial_logs_fn(trial_dir)
        if metrics:
            result["metrics"] = metrics
            result["success"] = True
        else:
            result["error"] = "no logs produced"

    except Exception as e:
        result["error"] = str(e)
    finally:
        try:
            artifact_path = _persist_trial_artifacts(
                trial_dir,
                artifact_root,
                trial_index,
                result,
                stdout_text=stdout_text,
                stderr_text=stderr_text,
            )
            if artifact_path:
                result["artifact_path"] = artifact_path
        except Exception as e:
            log = logging.getLogger(__name__)
            log.debug("Trial artifact persistence failed: %s", e)
        try:
            if trial_dir.is_dir():
                shutil.rmtree(trial_dir)
        except Exception as e:
            log = logging.getLogger(__name__)
            log.debug("Trial dir cleanup failed: %s", e)

    return result
