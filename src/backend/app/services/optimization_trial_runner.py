import logging
import math
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def parse_trial_logs(
    trial_dir: Path,
    *,
    safe_float_fn: Callable[..., float] = safe_float,
) -> dict[str, float] | None:
    logs_dir = trial_dir / "logs"
    if not logs_dir.is_dir():
        return None

    subdirs = sorted(
        [d for d in logs_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    if not subdirs:
        return None

    log_dir = subdirs[0]

    value_path = log_dir / "value.log"
    equity = []
    if value_path.is_file():
        with open(value_path, encoding="utf-8") as f:
            _header = f.readline()
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    equity.append(safe_float_fn(parts[2]))

    initial = equity[0] if equity else 100000.0
    final = equity[-1] if equity else initial
    total_return = ((final - initial) / initial * 100) if initial > 0 else 0.0

    n_days = len(equity)
    n_years = n_days / 252.0 if n_days > 0 else 1.0
    annual_return = (
        ((final / initial) ** (1.0 / n_years) - 1) * 100 if n_years > 0 and initial > 0 else 0.0
    )

    peak = 0.0
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = ((peak - v) / peak * 100) if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    if len(equity) > 1:
        returns = [
            (equity[i] - equity[i - 1]) / equity[i - 1]
            for i in range(1, len(equity))
            if equity[i - 1] > 0
        ]
        if returns:
            avg_r = sum(returns) / len(returns)
            std_r = (sum((r - avg_r) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe = (avg_r / std_r * (252**0.5)) if std_r > 0 else 0
        else:
            sharpe = 0
    else:
        sharpe = 0

    trade_path = log_dir / "trade.log"
    total_trades = 0
    win_trades = 0
    if trade_path.is_file():
        with open(trade_path, encoding="utf-8") as f:
            header_line = f.readline().strip()
            headers = header_line.split("\t")
            isclosed_idx = headers.index("isclosed") if "isclosed" in headers else -1
            pnlcomm_idx = headers.index("pnlcomm") if "pnlcomm" in headers else -1
            for line in f:
                parts = line.strip().split("\t")
                if isclosed_idx >= 0 and isclosed_idx < len(parts):
                    if parts[isclosed_idx] == "1":
                        total_trades += 1
                        if pnlcomm_idx >= 0 and pnlcomm_idx < len(parts):
                            if safe_float_fn(parts[pnlcomm_idx]) > 0:
                                win_trades += 1

    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0

    return {
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "final_value": round(final, 2),
    }


def run_single_trial(
    strategy_dir: str,
    params: dict[str, Any],
    trial_index: int,
    tmp_base: str,
    *,
    parse_trial_logs_fn: Callable[[Path], dict[str, float] | None] = parse_trial_logs,
    subprocess_module: Any = subprocess,
) -> dict[str, Any]:
    strategy_path = Path(strategy_dir)
    trial_dir = Path(tmp_base) / f"trial_{trial_index}"
    result: dict[str, Any] = {"params": params, "trial_index": trial_index, "success": False}

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

        if proc.returncode != 0:
            result["error"] = (
                proc.stderr.strip().split("\n")[-1] if proc.stderr else "unknown error"
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
            if trial_dir.is_dir():
                shutil.rmtree(trial_dir)
        except Exception as e:
            log = logging.getLogger(__name__)
            log.debug("Trial dir cleanup failed: %s", e)

    return result
