"""HTML report renderer — assembles body sections + ECharts JavaScript.

Uses:
- ``compute.compute_sections`` for statistics
- ``format.*`` for CSS / HTML helpers
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

import numpy as np

from fincore.report.compute import compute_sections
from fincore.report.format import (
    HTML_CSS,
    css_cls,
    date_list,
    fmt,
    html_cards,
    html_df,
    html_table,
    safe_list,
)

__all__ = ["generate_html"]


def _histogram_data(values, bins, decimals=2):
    """Compute histogram bin centers and counts."""
    h, edges = np.histogram(values, bins=bins)
    centers = [round(float((edges[i] + edges[i + 1]) / 2), decimals) for i in range(len(h))]
    counts = [int(v) for v in h]
    return centers, counts


def _prepare_chart_data_core(s):
    """Prepare core chart data (returns, rolling, heatmap, histogram)."""
    cd = {}
    dates = date_list(s["cum_returns"].index)
    cd["dates"] = dates
    cd["cumRet"] = safe_list(s["cum_returns"])
    cd["dd"] = safe_list(s["drawdown"], decimals=4, pct=True)
    cd["dailyRet"] = safe_list(s["returns"], decimals=4, pct=True)

    rs = s["rolling_sharpe"].dropna()
    cd["rsDates"], cd["rsVals"] = date_list(rs.index), safe_list(rs, decimals=4)
    rv = s["rolling_volatility"].dropna()
    cd["rvDates"], cd["rvVals"] = date_list(rv.index), safe_list(rv, decimals=4, pct=True)

    if "benchmark_cum" in s:
        cd["benchCum"] = safe_list(s["benchmark_cum"])
    if "rolling_beta" in s:
        rb = s["rolling_beta"].dropna()
        cd["rbDates"], cd["rbVals"] = date_list(rb.index), safe_list(rb, decimals=4)

    monthly_tbl = s["monthly_returns"].unstack()
    hm_months = [f"{int(c):02d}" for c in monthly_tbl.columns]
    hm_years = [str(y) for y in monthly_tbl.index]
    hm_data = []
    for yi, y in enumerate(monthly_tbl.index):
        for mi, m in enumerate(monthly_tbl.columns):
            val = monthly_tbl.loc[y, m]
            if not (isinstance(val, (float, np.floating)) and np.isnan(val)):
                hm_data.append([mi, yi, round(float(val) * 100, 2)])
    cd["hmMonths"], cd["hmYears"], cd["hmData"] = hm_months, hm_years, hm_data

    ys = s["yearly_stats"]
    cd["yrLabels"] = [str(y) for y in ys.index]
    cd["yrRets"] = [round(float(v) * 100, 2) for v in ys["Annual Return"].values]

    ret_vals = s["returns"].values
    cd["histBins"], cd["histCnts"] = _histogram_data(
        ret_vals * 100, bins=min(60, max(10, len(ret_vals) // 5)), decimals=3
    )

    q = s["return_quantiles"]
    cd["quantLabels"] = [str(p) for p in q.index]
    cd["quantVals"] = [round(float(v) * 100, 4) for v in q.values]

    monthly_vals = s["monthly_returns"].dropna().values
    if len(monthly_vals) > 2:
        cd["mDistBins"], cd["mDistCnts"] = _histogram_data(
            monthly_vals * 100, bins=min(30, max(5, len(monthly_vals) // 2))
        )

    pr = s["period_returns"]
    cd["prLabels"] = list(pr.keys())
    cd["prVals"] = [
        round(float(v) * 100, 2) if not (isinstance(v, float) and np.isnan(v)) else None for v in pr.values()
    ]
    if "benchmark_period_returns" in s:
        bpr = s["benchmark_period_returns"]
        cd["bprVals"] = [
            round(float(bpr.get(k, np.nan)) * 100, 2) if not np.isnan(bpr.get(k, np.nan)) else None for k in pr
        ]

    return cd, monthly_tbl, hm_months


def _prepare_chart_data_positions(s, cd):
    """Prepare position-related chart data."""
    if "has_positions" not in s:
        return
    cd["posDates"] = date_list(s["pos_long"].index)
    cd["posLong"] = safe_list(s["pos_long"], decimals=2)
    cd["posShort"] = safe_list(s["pos_short"], decimals=2)
    gl = s["gross_leverage"].dropna()
    cd["glDates"], cd["glVals"] = date_list(gl.index), safe_list(gl, decimals=4)
    if "pos_max_concentration" in s:
        mc = s["pos_max_concentration"]
        cd["mcDates"] = date_list(mc.index)
        cd["mcMax"] = safe_list(mc, decimals=4, pct=True)
        cd["mcMed"] = safe_list(s["pos_median_concentration"], decimals=4, pct=True)
    if "pos_alloc" in s and len(s["pos_alloc"].columns) <= 20:
        pa = s["pos_alloc"]
        cd["paDates"] = date_list(pa.index)
        cd["paNames"] = list(pa.columns)
        cd["paData"] = {str(c): safe_list(pa[c], decimals=4) for c in pa.columns}


def _prepare_chart_data_transactions(s, cd):
    """Prepare transaction-related chart data."""
    if "has_transactions" not in s:
        return
    dv = s["daily_txn_value"]
    cd["txnDates"], cd["txnVol"] = date_list(dv.index), safe_list(dv, decimals=2)
    dc = s["daily_txn_count"]
    cd["txnCntDates"], cd["txnCnts"] = date_list(dc.index), [int(v) for v in dc.values]
    if "turnover" in s:
        to = s["turnover"].dropna()
        cd["toDates"], cd["toVals"] = date_list(to.index), safe_list(to, decimals=4)
    if "txn_hours" in s:
        cd["txnHrLabels"], cd["txnHrCnts"] = _histogram_data(s["txn_hours"], bins=range(25), decimals=0)
        cd["txnHrLabels"] = [f"{int(v):02d}" for v in cd["txnHrLabels"]]


def _prepare_chart_data_trades(s, cd):
    """Prepare trade-related chart data."""
    if "trade_pnl" not in s:
        return
    pnl = s["trade_pnl"]
    cd["pnlBins"], cd["pnlCnts"] = _histogram_data(pnl, bins=max(10, min(40, len(pnl) // 3)))
    if "trade_pnl_long" in s and len(s["trade_pnl_long"]) > 0:
        pl = s["trade_pnl_long"]
        cd["pnlLBins"], cd["pnlLCnts"] = _histogram_data(pl, bins=max(5, min(30, len(pl) // 3)))
    if "trade_pnl_short" in s and len(s["trade_pnl_short"]) > 0:
        ps = s["trade_pnl_short"]
        cd["pnlSBins"], cd["pnlSCnts"] = _histogram_data(ps, bins=max(5, min(30, len(ps) // 3)))
    if "trade_barlen" in s:
        bl = s["trade_barlen"]
        cd["blBins"], cd["blCnts"] = _histogram_data(bl, bins=max(10, min(50, len(bl) // 3)), decimals=1)


def _build_sidebar(s):
    """Build the sidebar navigation HTML."""
    nav = [
        ("overview", "Overview"),
        ("period", "Period Returns"),
        ("performance", "Performance"),
        ("returns", "Returns"),
        ("rolling", "Rolling Metrics"),
        ("drawdown", "Drawdown"),
    ]
    if "benchmark_stats" in s:
        nav.append(("benchmark", "Benchmark"))
    if "has_positions" in s:
        nav.append(("positions", "Positions"))
    if "has_transactions" in s:
        nav.append(("transactions", "Transactions"))
    if "trade_stats" in s:
        nav.append(("trades", "Trades"))
    sidebar = '<nav class="sidebar"><h2>Report</h2>'
    for aid, label in nav:
        sidebar += f'<a href="#{aid}">{label}</a>'
    sidebar += "</nav>"
    return sidebar


def _dedup_date_arrays(cd):
    """Deduplicate date arrays to reduce JSON size."""
    aliases = []
    base_dates = cd.get("dates")
    for dk in ("posDates", "glDates", "mcDates"):
        if dk in cd and cd[dk] == base_dates:
            del cd[dk]
            aliases.append(f"D.{dk}=D.dates;")
    if "rvDates" in cd and "rsDates" in cd and cd["rvDates"] == cd["rsDates"]:
        del cd["rvDates"]
        aliases.append("D.rvDates=D.rsDates;")
    return "\n".join(aliases)


def generate_html(
    returns,
    benchmark_rets,
    positions,
    transactions,
    trades,
    title,
    output,
    rolling_window,
):
    """Generate an interactive HTML report (ECharts + sidebar navigation)."""
    s = compute_sections(returns, benchmark_rets, positions, transactions, trades, rolling_window)

    # ---- chart data ----
    cd, monthly_tbl, hm_months = _prepare_chart_data_core(s)
    _prepare_chart_data_positions(s, cd)
    _prepare_chart_data_transactions(s, cd)
    _prepare_chart_data_trades(s, cd)

    # ---- sidebar ----
    sidebar = _build_sidebar(s)

    # ---- body sections ----
    pct_perf = {
        "Annual Return",
        "Cumulative Returns",
        "Annual Volatility",
        "Max Drawdown",
        "Downside Risk",
        "Daily Value at Risk",
        "Daily Mean Return",
        "Daily Std Return",
        "Best Day",
        "Worst Day",
        "Avg Daily Turnover",
    }
    b = _build_body_sections(s, pct_perf, monthly_tbl, hm_months, rolling_window)

    # ---- ECharts JavaScript ----
    js = "\n".join(_build_echart_js(s, rolling_window))

    # ---- assemble HTML ----
    _alias_js = _dedup_date_arrays(cd)
    chart_json = json.dumps(cd, ensure_ascii=False)
    body_html = "\n".join(b)
    html = (
        f"<!DOCTYPE html>\n<html lang='zh'><head><meta charset='utf-8'>\n"
        f"<title>{title}</title>\n"
        f"{HTML_CSS}\n</head>\n<body>\n"
        f"{sidebar}\n<main class='content'>\n{body_html}\n</main>\n"
        f'<script src="https://cdn.bootcdn.net/ajax/libs/echarts/5.5.0/echarts.min.js"></script>\n'
        f"<script>window.echarts||document.write('<script src=\"https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js\"><\\/script>')</script>\n"
        f"<script>window.echarts||document.write('<script src=\"https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js\"><\\/script>')</script>\n"
        f"<script>\nvar D={chart_json};\n{_alias_js}\n"
        f"var _charts=[];\n"
        f"function C(id,o){{\n"
        f"  var e=document.getElementById(id);if(!e)return;\n"
        f"  var c=echarts.init(e);c.setOption(o);_charts.push(c);\n"
        f"}}\n"
        f"window.addEventListener('resize',function(){{_charts.forEach(function(c){{c.resize()}})}});\n"
        f"var B='#3182ce',G='#38a169',R='#e53e3e',O='#dd6b20',P='#805ad5',GY='#a0aec0';\n"
        f"{js}\n</script>\n</body></html>"
    )

    Path(output).write_text(html, encoding="utf-8")
    return output


# =========================================================================
# Body sections builder
# =========================================================================


def _build_period_returns_table(s):
    """Build the period returns comparison HTML table."""
    _pr = s["period_returns"]
    _wr = s["period_win_rates"]
    _phdr = "<tr><th>Metric</th>" + "".join(f"<th>{k}</th>" for k in _pr) + "</tr>"
    _prow1 = '<tr><td style="text-align:left;font-weight:600">Strategy</td>'
    for _k, _v in _pr.items():
        _prow1 += f'<td class="{css_cls(_v)}">{fmt(_v, pct=True)}</td>'
    _prow1 += "</tr>"
    _prows = _phdr + _prow1
    if "benchmark_period_returns" in s:
        _bpr = s["benchmark_period_returns"]
        _prow2 = '<tr><td style="text-align:left;font-weight:600">Benchmark</td>'
        for _k in _pr:
            _bv = _bpr.get(_k, np.nan)
            _prow2 += f'<td class="{css_cls(_bv)}">{fmt(_bv, pct=True)}</td>'
        _prow2 += "</tr>"
        _prow3 = '<tr><td style="text-align:left;font-weight:600">Excess</td>'
        for _k in _pr:
            _sv = _pr.get(_k, np.nan)
            _bv2 = _bpr.get(_k, np.nan)
            _exc = (_sv - _bv2) if not (np.isnan(_sv) or np.isnan(_bv2)) else np.nan
            _prow3 += f'<td class="{css_cls(_exc)}">{fmt(_exc, pct=True)}</td>'
        _prow3 += "</tr>"
        _prows += _prow2 + _prow3
    _prow_wr = '<tr><td style="text-align:left;font-weight:600">Daily Win Rate</td>'
    for _k in _pr:
        _wv = _wr.get(_k, np.nan)
        _prow_wr += f"<td>{fmt(_wv, pct=True)}</td>"
    _prow_wr += "</tr>"
    _prows += _prow_wr
    return f'<table class="ptbl">{_prows}</table>'


def _build_body_benchmark(b, s):
    """Build the benchmark body section."""
    if "benchmark_stats" not in s:
        return
    b.append('<div class="sec" id="benchmark"><div class="sec-title">Benchmark</div>')
    b.append(
        html_cards(
            s["benchmark_stats"],
            [
                "Alpha",
                "Beta",
                "Information Ratio",
                "Tracking Error",
                "Up Capture",
                "Down Capture",
                "Capture Ratio",
                "Correlation",
            ],
        )
    )
    b.append(html_table(s["benchmark_stats"]))
    if "rolling_beta" in s:
        b.append('<div class="chart-sm" id="c-rb"></div>')
    b.append("</div>")


def _build_body_positions(b, s):
    """Build the positions body section."""
    if "has_positions" not in s:
        return
    b.append('<div class="sec" id="positions"><div class="sec-title">Positions</div>')
    b.append(html_cards(s["position_summary"], list(s["position_summary"].keys())))
    b.append(html_table(s["position_summary"]))
    b.append('<div class="chart-box" id="c-expo"></div>')
    b.append('<div class="grid-2">')
    b.append('<div class="chart-sm" id="c-lev"></div>')
    b.append('<div class="chart-sm" id="c-conc"></div>')
    b.append("</div>")
    if "pos_alloc" in s and len(s["pos_alloc"].columns) <= 20:
        b.append('<div class="chart-box" id="c-alloc"></div>')
    b.append("</div>")


def _build_body_transactions(b, s):
    """Build the transactions body section."""
    if "has_transactions" not in s:
        return
    b.append('<div class="sec" id="transactions"><div class="sec-title">Transactions</div>')
    b.append(html_cards(s["txn_summary"], list(s["txn_summary"].keys())))
    b.append(html_table(s["txn_summary"]))
    b.append('<div class="grid-2">')
    b.append('<div class="chart-sm" id="c-txn"></div>')
    b.append('<div class="chart-sm" id="c-txn-cnt"></div>')
    b.append("</div>")
    if "turnover" in s:
        b.append('<div class="chart-sm" id="c-turnover"></div>')
    if "txn_hours" in s:
        b.append('<div class="chart-sm" id="c-txn-hours"></div>')
    b.append("</div>")


def _build_body_trades(b, s):
    """Build the trades body section."""
    if "trade_stats" not in s:
        return
    ts = s["trade_stats"]
    pct_t = {"Win Rate", "Long Win Rate", "Short Win Rate"}
    b.append('<div class="sec" id="trades"><div class="sec-title">Trades</div>')
    b.append(
        html_cards(
            ts,
            ["Total Trades", "Win Rate", "Profit/Loss Ratio", "Total PnL", "Expectancy", "Avg PnL per Trade"],
            pct_keys=pct_t,
        )
    )
    b.append(html_table(ts, pct_keys=pct_t))
    if "trade_pnl" in s:
        b.append('<div class="chart-sm" id="c-pnl"></div>')
        if "trade_pnl_long" in s or "trade_pnl_short" in s:
            b.append('<div class="grid-2">')
            b.append('<div class="chart-sm" id="c-pnl-long"></div>')
            b.append('<div class="chart-sm" id="c-pnl-short"></div>')
            b.append("</div>")
    if "trade_barlen" in s:
        b.append('<div class="chart-sm" id="c-barlen"></div>')
    b.append("</div>")


def _build_body_sections(s, pct_perf, monthly_tbl, hm_months, rolling_window):
    """Build the HTML body section list."""
    b = []

    title = s.get("_title", "Strategy Report")
    b.append(f"<h1>{title}</h1>")
    b.append(
        f'<div class="meta">{s["date_range"][0]} → {s["date_range"][1]}'
        f" | {s['n_days']} trading days | ~{s['n_months']} months</div>"
    )

    # -- Summary --
    b.append(f'<div class="summary-box">{s["summary_text"]}</div>')

    # -- Overview --
    b.append('<div class="sec" id="overview"><div class="sec-title">Overview</div>')
    b.append(
        html_cards(
            s["perf_stats"],
            [
                "Sharpe Ratio",
                "Annual Return",
                "Max Drawdown",
                "Annual Volatility",
                "Sortino Ratio",
                "Calmar Ratio",
                "Omega Ratio",
                "Stability",
            ],
            pct_keys={"Annual Return", "Max Drawdown", "Annual Volatility"},
        )
    )
    b.append('<div class="chart-box" id="c-cum"></div>')
    b.append('<div class="chart-sm" id="c-cum-log"></div>')
    b.append('<div class="chart-sm" id="c-dd"></div>')
    b.append("</div>")

    # -- Period Returns --
    b.append('<div class="sec" id="period"><div class="sec-title">Period Returns</div>')
    b.append('<div class="chart-sm" id="c-period"></div>')
    b.append(_build_period_returns_table(s))
    b.append("</div>")

    # -- Performance --
    b.append('<div class="sec" id="performance"><div class="sec-title">Performance</div>')
    b.append('<div class="grid-2"><div>')
    b.append('<h3 class="sub">Core Metrics</h3>')
    b.append(html_table(s["perf_stats"], pct_keys=pct_perf))
    b.append("</div><div>")
    b.append('<h3 class="sub">Extended Risk Metrics</h3>')
    b.append(html_table(s["extended_stats"]))
    b.append("</div></div></div>")

    # -- Returns --
    b.append('<div class="sec" id="returns"><div class="sec-title">Returns</div>')
    b.append('<div class="grid-2">')
    b.append('<div class="chart-sm" id="c-daily"></div>')
    b.append('<div class="chart-sm" id="c-dist"></div>')
    b.append("</div>")
    b.append('<div class="grid-2">')
    b.append('<div class="chart-sm" id="c-quant"></div>')
    b.append('<div class="chart-sm" id="c-mdist"></div>')
    b.append("</div>")
    b.append('<div class="chart-box" id="c-hm" style="height:280px"></div>')
    b.append('<h3 class="sub">Monthly Returns (%)</h3>')
    mt = monthly_tbl.copy()
    mt.columns = hm_months
    b.append(html_df(mt * 100, float_format=".2f"))
    b.append('<div class="chart-sm" id="c-yr"></div>')
    b.append('<h3 class="sub">Yearly Statistics</h3>')
    b.append(html_df(s["yearly_stats"], left_align=True))
    extremes = OrderedDict()
    extremes["Best Month"] = s["best_month"]
    extremes["Worst Month"] = s["worst_month"]
    extremes["Avg Month"] = s["avg_month"]
    extremes["Best Year"] = s["best_year"]
    extremes["Worst Year"] = s["worst_year"]
    b.append('<h3 class="sub">Monthly/Yearly Extremes</h3>')
    b.append(html_table(extremes, pct_keys=set(extremes.keys())))
    b.append("</div>")

    # -- Rolling --
    b.append(f'<div class="sec" id="rolling"><div class="sec-title">Rolling Metrics ({rolling_window}d)</div>')
    b.append('<div class="chart-box" id="c-rs"></div>')
    b.append('<div class="chart-sm" id="c-rv"></div>')
    b.append("</div>")

    # -- Drawdown --
    b.append('<div class="sec" id="drawdown"><div class="sec-title">Drawdown</div>')
    b.append('<h3 class="sub">Top Drawdowns</h3>')
    b.append(html_df(s["dd_table"], float_format=".2f"))
    b.append("</div>")

    _build_body_benchmark(b, s)
    _build_body_positions(b, s)
    _build_body_transactions(b, s)
    _build_body_trades(b, s)

    b.append("<footer>Generated by <strong>fincore</strong> | create_strategy_report()</footer>")
    return b


# =========================================================================
# ECharts JS builder (unchanged logic from original report.py)
# =========================================================================


def _build_echart_js(s, rw):
    """Build ECharts initialization JavaScript statements."""
    js = []
    _grid = "grid:{left:60,right:30,bottom:30,top:50}"
    _grid_s = "grid:{left:55,right:15,bottom:25,top:45}"
    _zoom = "dataZoom:[{type:'inside'},{type:'slider',height:18,bottom:4}]"
    _zoom_s = "dataZoom:[{type:'inside'}]"

    # Period returns comparison
    bench_period = ""
    if "benchmark_period_returns" in s:
        bench_period = ",{name:'Benchmark',type:'bar',data:D.bprVals,barWidth:'30%',itemStyle:{color:GY}}"
    js.append(
        f"C('c-period',{{"
        f"title:{{text:'Period Returns Comparison (%)',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis',valueFormatter:function(v){{return v==null?'N/A':v.toFixed(2)+'%'}}}},"
        f"legend:{{top:4,right:10}},{_grid_s},"
        f"xAxis:{{type:'category',data:D.prLabels,axisLabel:{{fontSize:10}}}},"
        f"yAxis:{{type:'value'}},"
        f"series:[{{name:'Strategy',type:'bar',data:D.prVals,barWidth:'30%',"
        f"itemStyle:{{color:B}}}}"
        f"{bench_period}]"
        f"}});"
    )

    # Cumulative returns
    bench_series = ""
    if "benchmark_cum" in s:
        bench_series = (
            ",{name:'Benchmark',type:'line',data:D.benchCum,showSymbol:false,"
            "lineStyle:{width:1,color:GY,type:'dashed'}}"
        )
    js.append(
        f"C('c-cum',{{"
        f"title:{{text:'Cumulative Returns',textStyle:{{fontSize:13}}}},"
        f"tooltip:{{trigger:'axis'}},legend:{{top:4,right:10}},{_grid},"
        f"xAxis:{{type:'category',data:D.dates,axisLabel:{{fontSize:10}}}},"
        f"yAxis:{{type:'value',axisLabel:{{fontSize:10}}}},"
        f"{_zoom},"
        f"series:[{{name:'Strategy',type:'line',data:D.cumRet,showSymbol:false,"
        f"lineStyle:{{width:1.5,color:B}},"
        f"areaStyle:{{color:{{type:'linear',x:0,y:0,x2:0,y2:1,"
        f"colorStops:[{{offset:0,color:'rgba(49,130,206,0.15)'}},"
        f"{{offset:1,color:'rgba(49,130,206,0.01)'}}]}}}}}}"
        f"{bench_series}]"
        f"}});"
    )

    # Cumulative returns (log scale)
    bench_series_log = ""
    if "benchmark_cum" in s:
        bench_series_log = (
            ",{name:'Benchmark',type:'line',data:D.benchCum,showSymbol:false,"
            "lineStyle:{width:1,color:GY,type:'dashed'}}"
        )
    js.append(
        f"C('c-cum-log',{{"
        f"title:{{text:'Cumulative Returns (Log Scale)',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis'}},legend:{{top:4,right:10}},{_grid_s},"
        f"xAxis:{{type:'category',data:D.dates,axisLabel:{{fontSize:10}}}},"
        f"yAxis:{{type:'log',axisLabel:{{fontSize:10}}}},"
        f"{_zoom_s},"
        f"series:[{{name:'Strategy',type:'line',data:D.cumRet,showSymbol:false,"
        f"lineStyle:{{width:1.2,color:B}}}}"
        f"{bench_series_log}]"
        f"}});"
    )

    # Drawdown
    js.append(
        f"C('c-dd',{{"
        f"title:{{text:'Drawdown (%)',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis',valueFormatter:function(v){{return v.toFixed(2)+'%'}}}},"
        f"{_grid_s},"
        f"xAxis:{{type:'category',data:D.dates,axisLabel:{{fontSize:10}}}},"
        f"yAxis:{{type:'value',axisLabel:{{fontSize:10}}}},"
        f"{_zoom_s},"
        f"series:[{{type:'line',data:D.dd,showSymbol:false,"
        f"lineStyle:{{width:1,color:R}},areaStyle:{{color:'rgba(229,62,62,0.2)'}}}}]"
        f"}});"
    )

    # Daily returns
    js.append(
        f"C('c-daily',{{"
        f"title:{{text:'Daily Returns (%)',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis',valueFormatter:function(v){{return v.toFixed(3)+'%'}}}},"
        f"{_grid_s},"
        f"xAxis:{{type:'category',data:D.dates,axisLabel:{{show:false}}}},"
        f"yAxis:{{type:'value',axisLabel:{{fontSize:10}}}},"
        f"series:[{{type:'bar',data:D.dailyRet,barWidth:'60%',"
        f"itemStyle:{{color:function(p){{return p.value>=0?G:R}}}}}}]"
        f"}});"
    )

    # Return distribution
    js.append(
        f"C('c-dist',{{"
        f"title:{{text:'Return Distribution (%)',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis'}},"
        f"{_grid_s},"
        f"xAxis:{{type:'category',data:D.histBins,axisLabel:{{fontSize:9}}}},"
        f"yAxis:{{type:'value',axisLabel:{{fontSize:10}}}},"
        f"series:[{{type:'bar',data:D.histCnts,barWidth:'80%',"
        f"itemStyle:{{color:B,borderRadius:[2,2,0,0]}}}}]"
        f"}});"
    )

    # Return quantiles horizontal bar
    js.append(
        "C('c-quant',{"
        "title:{text:'Return Quantiles (%)',textStyle:{fontSize:12}},"
        "tooltip:{trigger:'axis',valueFormatter:function(v){return v.toFixed(4)+'%'}},"
        "grid:{left:80,right:20,bottom:25,top:45},"
        "yAxis:{type:'category',data:D.quantLabels,axisLabel:{fontSize:9}},"
        "xAxis:{type:'value'},"
        "series:[{type:'bar',data:D.quantVals,barWidth:'60%',"
        "itemStyle:{color:function(p){return p.value>=0?G:R}}}]"
        "});"
    )

    # Monthly returns distribution
    monthly_vals = s["monthly_returns"].dropna().values
    if len(monthly_vals) > 2:
        js.append(
            f"C('c-mdist',{{"
            f"title:{{text:'Monthly Return Distribution (%)',textStyle:{{fontSize:12}}}},"
            f"tooltip:{{trigger:'axis'}},"
            f"{_grid_s},"
            f"xAxis:{{type:'category',data:D.mDistBins,axisLabel:{{fontSize:9}}}},"
            f"yAxis:{{type:'value'}},"
            f"series:[{{type:'bar',data:D.mDistCnts,barWidth:'80%',"
            f"itemStyle:{{color:B,borderRadius:[2,2,0,0]}}}}]"
            f"}});"
        )

    # Monthly heatmap
    js.append(
        "C('c-hm',{"
        "title:{text:'Monthly Returns Heatmap (%)',textStyle:{fontSize:12}},"
        "tooltip:{formatter:function(p){return D.hmYears[p.value[1]]+'-'+D.hmMonths[p.value[0]]+': '+p.value[2]+'%'}},"
        "grid:{left:60,right:80,bottom:20,top:35},"
        "xAxis:{type:'category',data:D.hmMonths,splitArea:{show:true}},"
        "yAxis:{type:'category',data:D.hmYears,splitArea:{show:true}},"
        "visualMap:{min:-10,max:10,calculable:true,orient:'vertical',right:5,top:'center',"
        "inRange:{color:['#c53030','#fc8181','#fff5f5','#f0fff4','#68d391','#276749']},"
        "textStyle:{fontSize:10}},"
        "series:[{type:'heatmap',data:D.hmData,label:{show:true,fontSize:9,"
        "formatter:function(p){return p.value[2].toFixed(1)}}}]"
        "});"
    )

    # Yearly returns
    js.append(
        f"C('c-yr',{{"
        f"title:{{text:'Annual Returns (%)',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis',valueFormatter:function(v){{return v.toFixed(2)+'%'}}}},"
        f"{_grid_s},"
        f"xAxis:{{type:'category',data:D.yrLabels}},"
        f"yAxis:{{type:'value'}},"
        f"series:[{{type:'bar',data:D.yrRets,barWidth:'50%',"
        f"itemStyle:{{color:function(p){{return p.value>=0?G:R}}}}}}]"
        f"}});"
    )

    # Rolling Sharpe
    js.append(
        f"C('c-rs',{{"
        f"title:{{text:'Rolling Sharpe ({rw}d)',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis'}},{_grid},{_zoom_s},"
        f"xAxis:{{type:'category',data:D.rsDates,axisLabel:{{fontSize:10}}}},"
        f"yAxis:{{type:'value'}},"
        f"series:[{{type:'line',data:D.rsVals,showSymbol:false,"
        f"lineStyle:{{width:1.2,color:B}},"
        f"areaStyle:{{color:{{type:'linear',x:0,y:0,x2:0,y2:1,"
        f"colorStops:[{{offset:0,color:'rgba(49,130,206,0.12)'}},"
        f"{{offset:1,color:'rgba(49,130,206,0.01)'}}]}}}},"
        f"markLine:{{data:[{{yAxis:0,lineStyle:{{color:GY,type:'dashed'}}}}]}}}}]"
        f"}});"
    )

    # Rolling Volatility
    js.append(
        f"C('c-rv',{{"
        f"title:{{text:'Rolling Volatility ({rw}d, %)',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis',valueFormatter:function(v){{return v.toFixed(2)+'%'}}}},"
        f"{_grid_s},{_zoom_s},"
        f"xAxis:{{type:'category',data:D.rvDates,axisLabel:{{fontSize:10}}}},"
        f"yAxis:{{type:'value'}},"
        f"series:[{{type:'line',data:D.rvVals,showSymbol:false,"
        f"lineStyle:{{width:1.2,color:O}},areaStyle:{{color:'rgba(221,107,32,0.12)'}}}}]"
        f"}});"
    )

    # Rolling Beta
    if "rolling_beta" in s:
        js.append(
            f"C('c-rb',{{"
            f"title:{{text:'Rolling Beta ({rw}d)',textStyle:{{fontSize:12}}}},"
            f"tooltip:{{trigger:'axis'}},{_grid_s},{_zoom_s},"
            f"xAxis:{{type:'category',data:D.rbDates,axisLabel:{{fontSize:10}}}},"
            f"yAxis:{{type:'value'}},"
            f"series:[{{type:'line',data:D.rbVals,showSymbol:false,"
            f"lineStyle:{{width:1.2,color:P}},"
            f"markLine:{{data:[{{yAxis:1.0,lineStyle:{{color:GY,type:'dashed'}}}}]}}}}]"
            f"}});"
        )

    _build_echart_positions(js, s, _grid, _grid_s, _zoom_s)
    _build_echart_transactions(js, s, _grid_s, _zoom_s)
    _build_echart_trades(js, s, _grid_s)

    return js


def _build_echart_positions(js, s, _grid, _grid_s, _zoom_s):
    """Build ECharts JS for position-related charts."""
    if "has_positions" not in s:
        return
    js.append(
        f"C('c-expo',{{"
        f"title:{{text:'Long/Short Exposure',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis'}},legend:{{top:4,right:10}},{_grid},{_zoom_s},"
        f"xAxis:{{type:'category',data:D.posDates,axisLabel:{{fontSize:10}}}},"
        f"yAxis:{{type:'value'}},"
        f"series:["
        f"{{name:'Long',type:'line',data:D.posLong,showSymbol:false,"
        f"lineStyle:{{width:1,color:G}},areaStyle:{{color:'rgba(56,161,105,0.2)'}}}},"
        f"{{name:'Short',type:'line',data:D.posShort,showSymbol:false,"
        f"lineStyle:{{width:1,color:R}},areaStyle:{{color:'rgba(229,62,62,0.2)'}}}}]"
        f"}});"
    )
    js.append(
        f"C('c-lev',{{"
        f"title:{{text:'Gross Leverage',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis'}},{_grid_s},{_zoom_s},"
        f"xAxis:{{type:'category',data:D.glDates,axisLabel:{{fontSize:10}}}},"
        f"yAxis:{{type:'value'}},"
        f"series:[{{type:'line',data:D.glVals,showSymbol:false,"
        f"lineStyle:{{width:1.2,color:'#2b6cb0'}},"
        f"areaStyle:{{color:'rgba(43,108,176,0.1)'}}}}]"
        f"}});"
    )
    if "pos_max_concentration" in s:
        js.append(
            f"C('c-conc',{{"
            f"title:{{text:'Position Concentration (%)',textStyle:{{fontSize:12}}}},"
            f"tooltip:{{trigger:'axis',valueFormatter:function(v){{return v.toFixed(2)+'%'}}}},"
            f"legend:{{top:4,right:10}},{_grid_s},{_zoom_s},"
            f"xAxis:{{type:'category',data:D.mcDates,axisLabel:{{fontSize:10}}}},"
            f"yAxis:{{type:'value'}},"
            f"series:["
            f"{{name:'Max',type:'line',data:D.mcMax,showSymbol:false,"
            f"lineStyle:{{width:1,color:'#c53030'}},areaStyle:{{color:'rgba(197,48,48,0.1)'}}}},"
            f"{{name:'Median',type:'line',data:D.mcMed,showSymbol:false,"
            f"lineStyle:{{width:1,color:O}},areaStyle:{{color:'rgba(221,107,32,0.08)'}}}}]"
            f"}});"
        )
    if "pos_alloc" in s and len(s["pos_alloc"].columns) <= 20:
        _pa_colors = "['#3182ce','#38a169','#e53e3e','#dd6b20','#805ad5','#d69e2e','#319795','#b83280','#2b6cb0','#276749','#c53030','#9c4221','#6b46c1','#975a16','#2c7a7b','#97266d','#2a4365','#22543d','#742a2a','#7b341e']"
        _pa_series = ",".join(
            f"{{name:D.paNames[{i}],type:'line',stack:'alloc',data:D.paData[D.paNames[{i}]],"
            f"showSymbol:false,areaStyle:{{}},lineStyle:{{width:0.5}}}}"
            for i in range(len(s["pos_alloc"].columns))
        )
        js.append(
            f"C('c-alloc',{{"
            f"title:{{text:'Holdings Allocation',textStyle:{{fontSize:12}}}},"
            f"tooltip:{{trigger:'axis'}},legend:{{top:4,right:10,textStyle:{{fontSize:9}}}},"
            f"color:{_pa_colors},"
            f"{_grid},{_zoom_s},"
            f"xAxis:{{type:'category',data:D.paDates,axisLabel:{{fontSize:10}}}},"
            f"yAxis:{{type:'value'}},"
            f"series:[{_pa_series}]"
            f"}});"
        )


def _build_echart_transactions(js, s, _grid_s, _zoom_s):
    """Build ECharts JS for transaction-related charts."""
    if "has_transactions" not in s:
        return
    js.append(
        f"C('c-txn',{{"
        f"title:{{text:'Daily Trading Value',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis'}},{_grid_s},"
        f"xAxis:{{type:'category',data:D.txnDates,axisLabel:{{fontSize:10}}}},"
        f"yAxis:{{type:'value'}},"
        f"series:[{{type:'bar',data:D.txnVol,barWidth:'60%',itemStyle:{{color:B}}}}]"
        f"}});"
    )
    js.append(
        f"C('c-txn-cnt',{{"
        f"title:{{text:'Daily Trade Count',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis'}},{_grid_s},"
        f"xAxis:{{type:'category',data:D.txnCntDates,axisLabel:{{fontSize:10}}}},"
        f"yAxis:{{type:'value'}},"
        f"series:[{{type:'bar',data:D.txnCnts,barWidth:'60%',itemStyle:{{color:O}}}}]"
        f"}});"
    )
    if "turnover" in s:
        js.append(
            f"C('c-turnover',{{"
            f"title:{{text:'Daily Turnover',textStyle:{{fontSize:12}}}},"
            f"tooltip:{{trigger:'axis'}},{_grid_s},{_zoom_s},"
            f"xAxis:{{type:'category',data:D.toDates,axisLabel:{{fontSize:10}}}},"
            f"yAxis:{{type:'value'}},"
            f"series:[{{type:'line',data:D.toVals,showSymbol:false,"
            f"lineStyle:{{width:1.2,color:P}},areaStyle:{{color:'rgba(128,90,213,0.1)'}}}}]"
            f"}});"
        )
    if "txn_hours" in s:
        js.append(
            f"C('c-txn-hours',{{"
            f"title:{{text:'Trading Hour Distribution',textStyle:{{fontSize:12}}}},"
            f"tooltip:{{trigger:'axis'}},{_grid_s},"
            f"xAxis:{{type:'category',data:D.txnHrLabels}},"
            f"yAxis:{{type:'value'}},"
            f"series:[{{type:'bar',data:D.txnHrCnts,barWidth:'60%',"
            f"itemStyle:{{color:'#319795',borderRadius:[2,2,0,0]}}}}]"
            f"}});"
        )


def _build_echart_trades(js, s, _grid_s):
    """Build ECharts JS for trade-related charts."""
    if "trade_pnl" not in s:
        return
    js.append(
        f"C('c-pnl',{{"
        f"title:{{text:'PnL Distribution',textStyle:{{fontSize:12}}}},"
        f"tooltip:{{trigger:'axis'}},{_grid_s},"
        f"xAxis:{{type:'category',data:D.pnlBins,axisLabel:{{fontSize:9}}}},"
        f"yAxis:{{type:'value'}},"
        f"series:[{{type:'bar',data:D.pnlCnts,barWidth:'80%',"
        f"itemStyle:{{color:function(p){{return D.pnlBins[p.dataIndex]>=0?G:R}}}}}}]"
        f"}});"
    )
    if "trade_pnl_long" in s and len(s["trade_pnl_long"]) > 0:
        js.append(
            f"C('c-pnl-long',{{"
            f"title:{{text:'Long PnL',textStyle:{{fontSize:12}}}},"
            f"tooltip:{{trigger:'axis'}},{_grid_s},"
            f"xAxis:{{type:'category',data:D.pnlLBins,axisLabel:{{fontSize:9}}}},"
            f"yAxis:{{type:'value'}},"
            f"series:[{{type:'bar',data:D.pnlLCnts,barWidth:'80%',"
            f"itemStyle:{{color:function(p){{return D.pnlLBins[p.dataIndex]>=0?G:R}}}}}}]"
            f"}});"
        )
    if "trade_pnl_short" in s and len(s["trade_pnl_short"]) > 0:
        js.append(
            f"C('c-pnl-short',{{"
            f"title:{{text:'Short PnL',textStyle:{{fontSize:12}}}},"
            f"tooltip:{{trigger:'axis'}},{_grid_s},"
            f"xAxis:{{type:'category',data:D.pnlSBins,axisLabel:{{fontSize:9}}}},"
            f"yAxis:{{type:'value'}},"
            f"series:[{{type:'bar',data:D.pnlSCnts,barWidth:'80%',"
            f"itemStyle:{{color:function(p){{return D.pnlSBins[p.dataIndex]>=0?G:R}}}}}}]"
            f"}});"
        )
    if "trade_barlen" in s:
        js.append(
            f"C('c-barlen',{{"
            f"title:{{text:'Holding Time Distribution',textStyle:{{fontSize:12}}}},"
            f"tooltip:{{trigger:'axis'}},{_grid_s},"
            f"xAxis:{{type:'category',data:D.blBins,axisLabel:{{fontSize:9}}}},"
            f"yAxis:{{type:'value'}},"
            f"series:[{{type:'bar',data:D.blCnts,barWidth:'80%',"
            f"itemStyle:{{color:'#319795',borderRadius:[2,2,0,0]}}}}]"
            f"}});"
        )
