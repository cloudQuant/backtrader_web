"""
日志解析服务 - 解析策略 logs/ 目录中的回测日志文件

支持的日志文件:
- value.log: 每日资金曲线 (dt, value, cash)
- trade.log: 交易记录
- order.log: 订单记录
- data.log: OHLCV + 指标数据
- position.log: 持仓记录
- run_info.json: 运行元信息
- current_position.json: 最终持仓
"""
import json
import logging
import math
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def find_latest_log_dir(strategy_dir: Path) -> Optional[Path]:
    """找到策略目录下最新的日志目录"""
    logs_dir = strategy_dir / "logs"
    if not logs_dir.is_dir():
        return None

    subdirs = sorted(
        [d for d in logs_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    return subdirs[0] if subdirs else None


def _parse_tsv(filepath: Path) -> List[Dict[str, str]]:
    """解析 tab 分隔的日志文件，返回字典列表"""
    if not filepath.is_file():
        return []

    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        if not header_line:
            return []
        headers = header_line.split("\t")

        for line in f:
            line = line.strip()
            if not line:
                continue
            values = line.split("\t")
            row = {}
            for i, h in enumerate(headers):
                row[h] = values[i] if i < len(values) else ""
            rows.append(row)

    return rows


def _safe_float(val: str, default: float = 0.0) -> float:
    """安全转换浮点数"""
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def parse_value_log(log_dir: Path) -> Dict[str, Any]:
    """
    解析 value.log，返回资金曲线数据。

    Returns:
        {
            "dates": ["2017-07-24", ...],
            "equity_curve": [100000.0, ...],
            "cash_curve": [100000.0, ...],
            "drawdown_curve": [0.0, ...],
        }
    """
    rows = _parse_tsv(log_dir / "value.log")
    dates = []
    equity = []
    cash = []

    for row in rows:
        dt = row.get("dt", "")
        if " " in dt:
            dt = dt.split(" ")[0]
        dates.append(dt)
        equity.append(_safe_float(row.get("value", "0")))
        cash.append(_safe_float(row.get("cash", "0")))

    # 计算回撤曲线
    drawdown = []
    peak = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = ((peak - v) / peak * 100) if peak > 0 else 0.0
        drawdown.append(round(dd, 4))

    return {
        "dates": dates,
        "equity_curve": equity,
        "cash_curve": cash,
        "drawdown_curve": drawdown,
    }


def parse_trade_log(log_dir: Path) -> List[Dict[str, Any]]:
    """
    解析 trade.log，返回交易记录列表。
    只返回已关闭的交易 (isclosed=1)。
    """
    rows = _parse_tsv(log_dir / "trade.log")
    trades = []

    for row in rows:
        if row.get("isclosed") != "1":
            continue

        trades.append({
            "ref": int(_safe_float(row.get("ref", "0"))),
            "datetime": row.get("dtclose", "").split(" ")[0] if row.get("dtclose") else "",
            "dtopen": row.get("dtopen", "").split(" ")[0] if row.get("dtopen") else "",
            "dtclose": row.get("dtclose", "").split(" ")[0] if row.get("dtclose") else "",
            "data_name": row.get("data_name", ""),
            "direction": "buy" if row.get("long") == "1" else "sell",
            "size": abs(_safe_float(row.get("size", "0"))),
            "price": round(_safe_float(row.get("price", "0")), 4),
            "value": round(abs(_safe_float(row.get("value", "0"))), 2),
            "commission": round(_safe_float(row.get("commission", "0")), 4),
            "pnl": round(_safe_float(row.get("pnl", "0")), 2),
            "pnlcomm": round(_safe_float(row.get("pnlcomm", "0")), 2),
            "barlen": int(_safe_float(row.get("barlen", "0"))),
        })

    return trades


def parse_order_log(log_dir: Path) -> List[Dict[str, Any]]:
    """解析 order.log，返回已完成订单列表"""
    rows = _parse_tsv(log_dir / "order.log")
    orders = []

    for row in rows:
        if row.get("status") != "Completed":
            continue

        orders.append({
            "ref": int(_safe_float(row.get("ref", "0"))),
            "type": row.get("ordtype", ""),
            "size": _safe_float(row.get("size", "0")),
            "price": round(_safe_float(row.get("executed_price", "0")), 4),
            "commission": round(_safe_float(row.get("commission", "0")), 4),
            "dt": row.get("dt", "").split(" ")[0] if row.get("dt") else "",
            "data_name": row.get("data_name", ""),
        })

    return orders


def parse_data_log(log_dir: Path) -> Dict[str, Any]:
    """
    解析 data.log，返回 OHLCV + 指标数据。
    返回 kline 格式的数据用于前端图表。
    """
    rows = _parse_tsv(log_dir / "data.log")
    if not rows:
        return {"dates": [], "ohlc": [], "volumes": [], "indicators": {}}

    # 找出指标列（非标准列）
    standard_cols = {"log_time", "dt", "data_name", "open", "high", "low", "close", "volume", "openinterest"}
    all_cols = set(rows[0].keys()) if rows else set()
    indicator_cols = [c for c in all_cols - standard_cols if c]

    dates = []
    ohlc = []
    volumes = []
    indicators: Dict[str, List[float]] = {col: [] for col in indicator_cols}

    for row in rows:
        dt = row.get("dt", "")
        if " " in dt:
            dt = dt.split(" ")[0]
        dates.append(dt)

        o = _safe_float(row.get("open", "0"))
        h = _safe_float(row.get("high", "0"))
        l = _safe_float(row.get("low", "0"))
        c = _safe_float(row.get("close", "0"))
        ohlc.append([o, c, l, h])
        volumes.append(_safe_float(row.get("volume", "0")))

        for col in indicator_cols:
            indicators[col].append(_safe_float(row.get(col, "0")))

    return {
        "dates": dates,
        "ohlc": ohlc,
        "volumes": volumes,
        "indicators": indicators,
    }


def parse_position_log(log_dir: Path) -> List[Dict[str, Any]]:
    """
    解析 position.log，返回每日持仓快照列表。
    每条记录: {dt, data_name, size, price}
    """
    rows = _parse_tsv(log_dir / "position.log")
    positions = []
    for row in rows:
        size = _safe_float(row.get("size", "0"))
        price = _safe_float(row.get("price", "0"))
        dt = row.get("dt", "")
        if " " in dt:
            dt = dt.split(" ")[0]
        positions.append({
            "dt": dt,
            "data_name": row.get("data_name", ""),
            "size": size,
            "price": round(price, 4),
            "market_value": round(abs(size) * price, 2),
        })
    return positions


def parse_current_position(log_dir: Path) -> List[Dict[str, Any]]:
    """解析 current_position.json，返回最终持仓列表"""
    fp = log_dir / "current_position.json"
    if not fp.is_file():
        return []
    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = []
        for item in data:
            size = _safe_float(str(item.get("size", 0)))
            price = _safe_float(str(item.get("price", 0)))
            result.append({
                "data_name": item.get("data_name", ""),
                "size": size,
                "price": round(price, 4),
                "market_value": round(abs(size) * price, 2),
            })
        return result
    except Exception:
        return []


def parse_run_info(log_dir: Path) -> Dict[str, Any]:
    """解析 run_info.json"""
    info_path = log_dir / "run_info.json"
    if not info_path.is_file():
        return {}
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def parse_all_logs(strategy_dir: Path) -> Optional[Dict[str, Any]]:
    """
    解析策略目录下最新日志，返回完整回测结果。

    Returns:
        完整的回测结果字典，包含资金曲线、交易记录、订单、K线数据等。
        如果没有日志目录则返回 None。
    """
    log_dir = find_latest_log_dir(strategy_dir)
    if not log_dir:
        return None

    # 解析各个日志
    value_data = parse_value_log(log_dir)
    trades = parse_trade_log(log_dir)
    orders = parse_order_log(log_dir)
    kline_data = parse_data_log(log_dir)
    run_info = parse_run_info(log_dir)

    # 计算统计指标
    equity = value_data.get("equity_curve", [])
    initial_cash = equity[0] if equity else 100000.0
    final_value = equity[-1] if equity else initial_cash

    total_return = ((final_value - initial_cash) / initial_cash * 100) if initial_cash > 0 else 0.0

    # 年化收益率
    n_days = len(equity)
    n_years = n_days / 252.0 if n_days > 0 else 1.0
    annual_return = ((final_value / initial_cash) ** (1.0 / n_years) - 1) * 100 if n_years > 0 and initial_cash > 0 else 0.0

    # 最大回撤
    max_drawdown = max(value_data.get("drawdown_curve", [0.0])) if value_data.get("drawdown_curve") else 0.0

    # 夏普比率 (简化计算)
    if len(equity) > 1:
        returns = []
        for i in range(1, len(equity)):
            if equity[i - 1] > 0:
                returns.append((equity[i] - equity[i - 1]) / equity[i - 1])
        if returns:
            avg_ret = np.mean(returns)
            std_ret = np.std(returns)
            sharpe_ratio = (avg_ret / std_ret * (252 ** 0.5)) if std_ret > 0 else 0.0
        else:
            sharpe_ratio = 0.0
    else:
        sharpe_ratio = 0.0

    # 交易统计
    total_trades = len(trades)
    profitable_trades = len([t for t in trades if t.get("pnlcomm", 0) > 0])
    losing_trades = len([t for t in trades if t.get("pnlcomm", 0) <= 0])
    win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0.0

    return {
        "run_info": run_info,
        "log_dir": str(log_dir),
        # 指标
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "sharpe_ratio": round(sharpe_ratio, 4),
        "max_drawdown": round(max_drawdown, 4),
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "profitable_trades": profitable_trades,
        "losing_trades": losing_trades,
        "initial_cash": initial_cash,
        "final_value": round(final_value, 2),
        # 曲线数据
        "equity_curve": equity,
        "equity_dates": value_data.get("dates", []),
        "cash_curve": value_data.get("cash_curve", []),
        "drawdown_curve": value_data.get("drawdown_curve", []),
        # 交易和订单
        "trades": trades,
        "orders": orders,
        # K线数据
        "kline": kline_data,
    }
