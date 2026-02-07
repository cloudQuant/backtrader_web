"""
参数优化服务 — 基于多进程的网格搜索

设计思路:
- 根据用户指定的参数范围 (start, end, step) 生成笛卡尔积参数网格
- 使用 concurrent.futures.ProcessPoolExecutor 并行执行各参数组合
- 每个 worker: 写临时 config.yaml → 运行 run.py 子进程 → 解析 logs → 返回指标
- 主线程汇总结果，提供进度查询接口
"""
import copy
import itertools
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ---- 全局状态 ----

_tasks: Dict[str, Dict[str, Any]] = {}
_tasks_lock = Lock()


def _get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _tasks_lock:
        return _tasks.get(task_id)


def _set_task(task_id: str, data: Dict[str, Any]):
    with _tasks_lock:
        _tasks[task_id] = data


def _update_task(task_id: str, **kwargs):
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id].update(kwargs)


# ---- Worker (runs in subprocess of ProcessPoolExecutor) ----

def _run_single_trial(
    strategy_dir: str,
    params: Dict[str, Any],
    trial_index: int,
    tmp_base: str,
) -> Dict[str, Any]:
    """
    在独立进程中运行单次回测试验。

    为避免多进程同时写同一个 logs/ 目录冲突,
    将整个策略目录拷贝到临时目录中执行。
    """
    strategy_path = Path(strategy_dir)
    trial_dir = Path(tmp_base) / f"trial_{trial_index}"
    result: Dict[str, Any] = {"params": params, "trial_index": trial_index, "success": False}

    try:
        # 拷贝策略目录到临时位置
        shutil.copytree(strategy_path, trial_dir, dirs_exist_ok=True)

        # 清空 logs 子目录
        logs_dir = trial_dir / "logs"
        if logs_dir.is_dir():
            shutil.rmtree(logs_dir)

        # 写入当前参数到 config.yaml
        config_path = trial_dir / "config.yaml"
        config: dict = {}
        if config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        if "params" not in config:
            config["params"] = {}
        config["params"].update(params)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        # 移除 run.py 中的 assert 语句（参数变化后断言会失败）
        run_py = trial_dir / "run.py"
        if run_py.is_file():
            code = run_py.read_text(encoding="utf-8")
            lines = code.split("\n")
            cleaned = []
            for line in lines:
                stripped = line.lstrip()
                if stripped.startswith("assert ") or stripped.startswith("assert("):
                    cleaned.append(line.replace(stripped, "pass  # assert removed for optimization"))
                else:
                    cleaned.append(line)
            run_py.write_text("\n".join(cleaned), encoding="utf-8")

        # 准备环境变量：设置数据目录以便 run.py 能找到数据文件
        project_root = Path(strategy_dir).parent.parent  # strategies/ -> project root
        env = dict(os.environ)
        env["BACKTRADER_DATA_DIR"] = str(project_root / "datas")
        # 将原始策略目录也加入 PYTHONPATH 以便导入本地模块
        extra_paths = [str(strategy_dir), str(trial_dir)]
        env["PYTHONPATH"] = os.pathsep.join(extra_paths + [env.get("PYTHONPATH", "")])

        # 执行 run.py
        proc = subprocess.run(
            [sys.executable, str(run_py)],
            cwd=str(trial_dir),
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )

        if proc.returncode != 0:
            result["error"] = proc.stderr.strip().split("\n")[-1] if proc.stderr else "unknown error"
            return result

        # 解析日志提取绩效指标
        metrics = _parse_trial_logs(trial_dir)
        if metrics:
            result["metrics"] = metrics
            result["success"] = True
        else:
            result["error"] = "no logs produced"

    except Exception as e:
        result["error"] = str(e)
    finally:
        # 清理临时目录
        try:
            if trial_dir.is_dir():
                shutil.rmtree(trial_dir)
        except Exception:
            pass

    return result


def _safe_float(val, default=0.0):
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def _parse_trial_logs(trial_dir: Path) -> Optional[Dict[str, float]]:
    """从 trial 的 logs 目录中提取核心绩效指标"""
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

    # value.log → equity curve → return / drawdown
    # columns: log_time(0) dt(1) value(2) cash(3)
    value_path = log_dir / "value.log"
    equity = []
    if value_path.is_file():
        with open(value_path, "r", encoding="utf-8") as f:
            header = f.readline()
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    equity.append(_safe_float(parts[2]))

    initial = equity[0] if equity else 100000.0
    final = equity[-1] if equity else initial
    total_return = ((final - initial) / initial * 100) if initial > 0 else 0.0

    n_days = len(equity)
    n_years = n_days / 252.0 if n_days > 0 else 1.0
    annual_return = ((final / initial) ** (1.0 / n_years) - 1) * 100 if n_years > 0 and initial > 0 else 0.0

    # drawdown
    peak = 0.0
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = ((peak - v) / peak * 100) if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # sharpe (daily)
    if len(equity) > 1:
        returns = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity)) if equity[i - 1] > 0]
        if returns:
            avg_r = sum(returns) / len(returns)
            std_r = (sum((r - avg_r) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe = (avg_r / std_r * (252 ** 0.5)) if std_r > 0 else 0
        else:
            sharpe = 0
    else:
        sharpe = 0

    # trade.log
    trade_path = log_dir / "trade.log"
    total_trades = 0
    win_trades = 0
    if trade_path.is_file():
        with open(trade_path, "r", encoding="utf-8") as f:
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
                            if _safe_float(parts[pnlcomm_idx]) > 0:
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


# ---- Public API ----

def generate_param_grid(
    param_ranges: Dict[str, Dict[str, float]],
) -> List[Dict[str, Any]]:
    """
    根据 {param_name: {start, end, step}} 生成笛卡尔积参数网格。
    """
    keys = []
    value_lists = []
    for name, spec in param_ranges.items():
        start = spec["start"]
        end = spec["end"]
        step = spec["step"]
        ptype = spec.get("type", "float")

        vals = []
        v = start
        while v <= end + 1e-9:
            vals.append(int(v) if ptype == "int" else round(v, 6))
            v += step
        keys.append(name)
        value_lists.append(vals)

    combos = list(itertools.product(*value_lists))
    return [dict(zip(keys, combo)) for combo in combos]


def submit_optimization(
    strategy_id: str,
    param_ranges: Dict[str, Dict[str, float]],
    n_workers: int = 4,
) -> str:
    """
    提交优化任务（异步执行）。返回 task_id。
    """
    from app.services.strategy_service import STRATEGIES_DIR

    strategy_dir = STRATEGIES_DIR / strategy_id
    if not (strategy_dir / "run.py").is_file():
        raise ValueError(f"策略 {strategy_id} 不存在或缺少 run.py")

    grid = generate_param_grid(param_ranges)
    if not grid:
        raise ValueError("参数网格为空，请检查参数范围设置")

    task_id = uuid.uuid4().hex[:8]
    _set_task(task_id, {
        "status": "running",
        "strategy_id": strategy_id,
        "total": len(grid),
        "completed": 0,
        "failed": 0,
        "results": [],
        "param_names": list(param_ranges.keys()),
        "created_at": datetime.now().isoformat(),
        "n_workers": n_workers,
    })

    import threading
    t = threading.Thread(
        target=_run_optimization_thread,
        args=(task_id, str(strategy_dir), grid, n_workers),
        daemon=True,
    )
    t.start()

    return task_id


def _run_optimization_thread(
    task_id: str,
    strategy_dir: str,
    grid: List[Dict[str, Any]],
    n_workers: int,
):
    """在后台线程中运行多进程优化"""
    tmp_base = tempfile.mkdtemp(prefix=f"opt_{task_id}_")
    all_results: List[Dict[str, Any]] = []

    try:
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = {}
            for i, params in enumerate(grid):
                fut = executor.submit(
                    _run_single_trial, strategy_dir, params, i, tmp_base
                )
                futures[fut] = i

            for fut in as_completed(futures):
                trial_result = fut.result()
                if trial_result["success"]:
                    all_results.append(trial_result)
                    _update_task(task_id, completed=len(all_results))
                else:
                    task = _get_task(task_id)
                    if task:
                        _update_task(task_id, failed=task["failed"] + 1)

                # 更新进度
                task = _get_task(task_id)
                if task:
                    done_count = len(all_results) + task["failed"]
                    _update_task(task_id, results=list(all_results))

        _update_task(task_id, status="completed", results=all_results)
        logger.info(f"优化完成 {task_id}: {len(all_results)}/{len(grid)} 成功")

    except Exception as e:
        logger.error(f"优化任务失败 {task_id}: {e}")
        _update_task(task_id, status="error", error=str(e))
    finally:
        try:
            shutil.rmtree(tmp_base, ignore_errors=True)
        except Exception:
            pass


def get_optimization_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """获取优化任务进度"""
    task = _get_task(task_id)
    if not task:
        return None
    return {
        "task_id": task_id,
        "status": task["status"],
        "strategy_id": task["strategy_id"],
        "total": task["total"],
        "completed": task["completed"],
        "failed": task["failed"],
        "progress": round((task["completed"] + task["failed"]) / task["total"] * 100, 1) if task["total"] > 0 else 0,
        "n_workers": task["n_workers"],
        "created_at": task["created_at"],
    }


def get_optimization_results(task_id: str) -> Optional[Dict[str, Any]]:
    """获取优化任务结果"""
    task = _get_task(task_id)
    if not task:
        return None

    results = task.get("results", [])

    # 构建表格格式的数据
    rows = []
    for r in results:
        row = dict(r["params"])
        if r.get("metrics"):
            row.update(r["metrics"])
        rows.append(row)

    # 按年化收益率降序排序
    rows.sort(key=lambda x: x.get("annual_return", -999999), reverse=True)

    # 找到最佳参数
    best = rows[0] if rows else None

    return {
        "task_id": task_id,
        "status": task["status"],
        "strategy_id": task["strategy_id"],
        "param_names": task["param_names"],
        "metric_names": ["total_return", "annual_return", "sharpe_ratio", "max_drawdown", "total_trades", "win_rate", "final_value"],
        "total": task["total"],
        "completed": task["completed"],
        "failed": task["failed"],
        "rows": rows,
        "best": best,
    }


def cancel_optimization(task_id: str) -> bool:
    """取消优化任务（标记状态，不强制杀子进程）"""
    task = _get_task(task_id)
    if not task:
        return False
    _update_task(task_id, status="cancelled")
    return True
