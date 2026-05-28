"""Filesystem helpers used to materialise the per-backtest run workspace.

Iteration 174 (C8) extracted these pure-IO helpers out of
:class:`app.services.backtest.service.BacktestService` so the service class
can focus on orchestration. They operate on ``Path`` objects and config
mappings only — no DB / cache / network dependencies.

The functions are re-exported from ``BacktestService`` as one-line
forwarders, so external code that imported them off the class continues to
work without changes.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

from app.schemas.backtest import BacktestRequest

logger = logging.getLogger(__name__)


def setup_workspace(
    task_id: str,
    strategy_id: str,
    strategy_dir: Path,
) -> tuple[Path, Path]:
    """Create an isolated temp workspace for a backtest run.

    Returns:
        ``(tmp_base, task_work_dir)`` — the root temp directory and the
        strategy-specific working directory inside it.
    """
    from app.services.strategy_service import STRATEGIES_DIR

    tmp_base = Path(tempfile.mkdtemp(prefix=f"bt_{task_id}_"))
    task_work_dir = tmp_base / "strategies" / strategy_id
    task_work_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(strategy_dir, task_work_dir, dirs_exist_ok=True)

    # Symlink shared data directory so each task does not duplicate market data.
    project_root = STRATEGIES_DIR.parent
    datas_src = project_root / "datas"
    datas_link = tmp_base / "strategies" / "datas"
    if datas_src.is_dir() and not datas_link.exists():
        datas_link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(str(datas_src), str(datas_link))
        except OSError as exc:
            logger.warning("Failed to symlink datas dir for backtest workspace: %s", exc)
            shutil.copytree(datas_src, datas_link, dirs_exist_ok=True)

    # Clear stale logs from the copied strategy directory.
    tmp_logs = task_work_dir / "logs"
    if tmp_logs.is_dir():
        shutil.rmtree(tmp_logs)

    return tmp_base, task_work_dir


def copy_log_artifacts(source_dir: Path, target_dir: Path) -> None:
    """Copy flat log artifacts into a task-specific directory safely."""
    if not source_dir.is_dir():
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    for child in source_dir.iterdir():
        if child == target_dir:
            continue
        if child.is_file():
            shutil.copy2(child, target_dir / child.name)


def has_custom_params(request: BacktestRequest) -> bool:
    """Return True when the request overrides the strategy's default config."""
    return bool(request.params) or request.initial_cash != 100000 or request.commission != 0.001


def write_temp_config(
    config_path: Path, request: BacktestRequest, original_text: str | None
) -> None:
    """Write custom parameters from the frontend to a temporary ``config.yaml``."""
    import yaml

    config: dict = {}
    if original_text:
        config = yaml.safe_load(original_text) or {}

    if request.params:
        if "params" not in config:
            config["params"] = {}
        config["params"].update(request.params)

    if "backtest" not in config:
        config["backtest"] = {}
    config["backtest"]["initial_cash"] = request.initial_cash
    config["backtest"]["commission"] = request.commission

    if "data" not in config:
        config["data"] = {}
    if request.symbol:
        config["data"]["symbol"] = request.symbol
    if request.timeframe:
        config["data"]["timeframe"] = request.timeframe
    if request.timeframe_n is not None:
        config["data"]["timeframe_n"] = request.timeframe_n
    if request.bar_count is not None:
        config["data"]["bar_count"] = request.bar_count

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def strip_asserts(run_py: Path) -> None:
    """Remove ``assert`` statements from ``run.py`` to prevent assertion failures.

    This is a defensive measure for legacy strategy templates that ``assert`` on
    parameter ranges; the web backtest framework lets the user override these
    parameters, which could otherwise blow up the run.
    """
    if not run_py.is_file():
        return
    code = run_py.read_text(encoding="utf-8")
    lines = code.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("assert ") or stripped.startswith("assert("):
            cleaned.append(line.replace(stripped, "pass  # assert removed for web backtest"))
        else:
            cleaned.append(line)
    run_py.write_text("\n".join(cleaned), encoding="utf-8")


def normalize_trade_logger_params(run_py: Path) -> None:
    """Rewrite legacy ``TradeLogger`` kwargs in ``run.py`` so the real observer works.

    Maps ``log_data`` → ``log_bars``, ``log_file_enabled`` → removed,
    ``file_format`` → ``log_format``. Only touches the text of the file; safe
    to call on files that already use the current param names (no-op).
    """
    if not run_py.is_file():
        return
    code = run_py.read_text(encoding="utf-8")
    original = code

    code = code.replace("log_data=", "log_bars=")
    code = code.replace("file_format='log'", "log_format='text'")
    code = code.replace('file_format="log"', 'log_format="text"')
    code = code.replace("file_format='csv'", "log_format='text'")
    code = code.replace('file_format="csv"', 'log_format="text"')
    code = code.replace("file_format='json'", "log_format='json'")
    code = code.replace('file_format="json"', 'log_format="json"')
    code = code.replace("file_format='text'", "log_format='text'")
    code = code.replace('file_format="text"', 'log_format="text"')

    lines = code.split("\n")
    cleaned = [ln for ln in lines if "log_file_enabled" not in ln]
    code = "\n".join(cleaned)
    if code != original:
        run_py.write_text(code, encoding="utf-8")
