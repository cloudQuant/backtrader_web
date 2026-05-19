from __future__ import annotations

from pathlib import Path


def _write(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8")


def test_log_parser_parses_and_hits_edge_branches(tmp_path):
    from app.services import log_parser_service as lps

    log_dir = tmp_path / "logs" / "2023"
    log_dir.mkdir(parents=True)

    # value.log: includes an empty line to hit _parse_tsv skip, and dt with time to hit split.
    _write(
        log_dir / "value.log",
        "dt\tvalue\tcash\n\n2023-01-01 00:00:00\t100\t100\n2023-01-02\t0\t0\n",
    )

    # trade.log: includes an open trade to hit isclosed != 1 continue.
    _write(
        log_dir / "trade.log",
        "isclosed\tref\tdtopen\tdtclose\tdata_name\tlong\tsize\tprice\tvalue\tcommission\tpnl\tpnlcomm\tbarlen\n"
        "0\t1\t2023-01-01\t2023-01-02\tX\t1\t1\t1\t1\t0\t0\t0\t1\n"
        "1\t2\t2023-01-01 00:00:00\t2023-01-02 00:00:00\tX\t1\t1\t1\t1\t0\t0\t1\t1\n",
    )

    # data.log: dt with time to hit split.
    _write(
        log_dir / "data.log",
        "dt\topen\thigh\tlow\tclose\tvolume\n2023-01-01 00:00:00\t1\t1\t1\t1\t1\n",
    )

    v = lps.parse_value_log(log_dir)
    assert v["dates"][0] == "2023-01-01"

    trades = lps.parse_trade_log(log_dir)
    assert len(trades) == 1

    k = lps.parse_data_log(log_dir)
    assert k["dates"][0] == "2023-01-01"


def test_parse_all_logs_sharpe_ratio_empty_and_single_point(tmp_path):
    from app.services import log_parser_service as lps

    strategy_dir = tmp_path / "strategy"
    log_dir = strategy_dir / "logs" / "z"
    log_dir.mkdir(parents=True)

    # returns empty -> sharpe_ratio = 0.0 branch
    _write(log_dir / "value.log", "dt\tvalue\tcash\n2023-01-01\t0\t0\n2023-01-02\t0\t0\n")
    _write(log_dir / "trade.log", "isclosed\n")
    _write(log_dir / "order.log", "status\n")
    _write(log_dir / "data.log", "dt\n")
    _write(log_dir / "run_info.json", "{}\n")

    res = lps.parse_all_logs(strategy_dir)
    assert res is not None
    assert res["sharpe_ratio"] == 0.0

    # single point -> else branch sharpe_ratio = 0.0
    _write(log_dir / "value.log", "dt\tvalue\tcash\n2023-01-01\t100\t100\n")
    res2 = lps.parse_all_logs(strategy_dir)
    assert res2 is not None
    assert res2["sharpe_ratio"] == 0.0
