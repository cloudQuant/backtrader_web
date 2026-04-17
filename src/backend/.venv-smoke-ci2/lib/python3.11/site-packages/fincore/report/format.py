"""CSS styles and HTML formatting helpers for strategy reports.

Contains:
- ``HTML_CSS``: full ``<style>`` block
- ``fmt`` / ``css_cls``: value formatting & colouring
- ``html_table`` / ``html_df`` / ``html_cards``: table/card renderers
- ``safe_list`` / ``date_list``: JSON-safe data converters
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    import pandas as pd

__all__ = [
    "HTML_CSS",
    "css_cls",
    "date_list",
    "fmt",
    "html_cards",
    "html_df",
    "html_table",
    "safe_list",
]


# =========================================================================
# CSS
# =========================================================================

HTML_CSS = """\
<style>
:root {
  --primary: #1a365d; --primary-lt: #2b6cb0; --accent: #3182ce;
  --green: #38a169; --red: #e53e3e; --orange: #dd6b20;
  --g50: #f7fafc; --g100: #edf2f7; --g200: #e2e8f0; --g300: #cbd5e0;
  --g500: #718096; --g600: #4a5568; --g700: #2d3748; --sidebar-w: 200px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       color: var(--g700); line-height: 1.6; background: var(--g50); }
.sidebar { position: fixed; left: 0; top: 0; bottom: 0; width: var(--sidebar-w);
           background: linear-gradient(180deg, var(--primary), #0d2137); color: #fff;
           padding: 16px 0; overflow-y: auto; z-index: 100; }
.sidebar h2 { font-size: 0.95em; padding: 0 16px 12px;
              border-bottom: 1px solid rgba(255,255,255,.15); margin-bottom: 6px; }
.sidebar a { display: block; padding: 7px 16px; color: rgba(255,255,255,.75);
             text-decoration: none; font-size: 0.82em; transition: .2s; }
.sidebar a:hover { background: rgba(255,255,255,.1); color: #fff;
                   border-left: 3px solid var(--accent); }
.content { margin-left: var(--sidebar-w); padding: 20px 28px; max-width: 1180px; }
.content h1 { font-size: 1.4em; color: var(--primary);
              border-bottom: 3px solid var(--primary); padding-bottom: 6px; margin-bottom: 4px; }
.meta { color: var(--g500); font-size: 0.88em; margin-bottom: 18px; }
.sec { background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.07);
       padding: 18px 22px; margin-bottom: 18px; }
.sec-title { color: var(--primary); font-size: 1.1em; font-weight: 700; margin-bottom: 14px;
             padding-bottom: 6px; border-bottom: 2px solid var(--g200);
             display: flex; align-items: center; gap: 8px; }
.sec-title::before { content: ''; width: 4px; height: 18px; background: var(--accent);
                     border-radius: 2px; display: inline-block; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(145px, 1fr));
         gap: 10px; margin-bottom: 16px; }
.card { background: var(--g50); border: 1px solid var(--g200); border-radius: 8px;
        padding: 12px 14px; text-align: center; }
.card .val { font-size: 1.25em; font-weight: 700; margin-bottom: 2px; }
.card .lbl { font-size: 0.76em; color: var(--g500); }
.pos { color: var(--green); } .neg { color: var(--red); }
table { border-collapse: collapse; width: 100%; font-size: 0.85em; margin: 10px 0; }
th, td { border: 1px solid var(--g200); padding: 7px 10px; }
th { background: var(--g100); font-weight: 600; text-align: left; }
td { text-align: right; }
tr:nth-child(even) { background: var(--g50); }
tr:hover { background: #ebf8ff; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.chart-box { width: 100%; height: 340px; margin: 10px 0; }
.chart-sm { width: 100%; height: 260px; margin: 10px 0; }
h3.sub { margin: 12px 0 6px; color: var(--primary); font-size: 1em; }
footer { margin-top: 28px; padding: 14px 0; border-top: 1px solid var(--g200);
         font-size: 0.78em; color: var(--g500); text-align: center; }
@media (max-width: 860px) {
  .sidebar { display: none; } .content { margin-left: 0; }
  .grid-2 { grid-template-columns: 1fr; }
  .cards { grid-template-columns: repeat(2, 1fr); }
}
@media print {
  .sidebar { display: none !important; }
  .content { margin-left: 0 !important; max-width: 100% !important; padding: 8px 14px !important; }
  body { background: #fff !important; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  .sec-title { page-break-after: avoid; break-after: avoid; }
  .chart-box, .chart-sm { page-break-inside: avoid; break-inside: avoid; }
  .grid-2 { page-break-inside: avoid; break-inside: avoid; }
  table { page-break-inside: avoid; break-inside: avoid; }
  .cards { page-break-inside: avoid; break-inside: avoid; }
  .summary-box { page-break-inside: avoid; break-inside: avoid; }
  h1, .meta { page-break-after: avoid; break-after: avoid; }
  h3.sub { page-break-after: avoid; break-after: avoid; }
}
.summary-box { background: linear-gradient(135deg, #ebf8ff 0%, #f0fff4 100%);
               border-left: 4px solid var(--accent); border-radius: 6px;
               padding: 14px 18px; margin-bottom: 16px; font-size: 0.92em;
               line-height: 1.7; color: var(--g700); }
.ptbl { font-size: 0.83em; }
.ptbl th { background: var(--primary); color: #fff; text-align: center; padding: 8px 6px; }
.ptbl td { text-align: center; padding: 7px 6px; }
.ptbl tr:first-child td { font-weight: 700; }
.card-hl { border-top: 3px solid var(--accent); }
.card-hl.cg { border-top-color: var(--green); }
.card-hl.cr { border-top-color: var(--red); }
.card-hl.co { border-top-color: var(--orange); }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
@media (max-width: 860px) { .grid-3 { grid-template-columns: 1fr; } }
.tbl-left td { text-align: left; }
</style>
"""


# =========================================================================
# Value formatting helpers
# =========================================================================


def fmt(v: Any, pct: bool = False) -> str:
    """Format a scalar for display in HTML tables/cards."""
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}" if abs(int(v)) >= 10000 else str(v)
    if isinstance(v, (float, np.floating)):
        if np.isnan(v):
            return "N/A"
        vf = float(v)
        if pct:
            return f"{vf * 100:.2f}%"
        a = abs(vf)
        if a >= 1e6:
            return f"{vf:,.0f}"
        if a >= 100:
            return f"{vf:,.2f}"
        return f"{vf:.4f}"
    return str(v)


def css_cls(v: Any) -> str:
    """Return CSS class for positive/negative coloring."""
    if isinstance(v, (int, float, np.integer, np.floating)):
        # np.isnan can raise for edge-case numeric types; suppress and treat as non-NaN
        with contextlib.suppress(TypeError, ValueError):
            if np.isnan(v):
                return ""
        return "pos" if v > 0 else ("neg" if v < 0 else "")
    return ""


# =========================================================================
# HTML renderers
# =========================================================================


def html_table(
    d: Mapping[str, Any],
    pct_keys: Iterable[str] | None = None,
) -> str:
    """OrderedDict → HTML table."""
    pct_keys = set(pct_keys or [])
    rows = []
    for k, v in d.items():
        css = css_cls(v)
        rows.append(f'<tr><th>{k}</th><td class="{css}">{fmt(v, pct=k in pct_keys)}</td></tr>')
    return "<table>" + "".join(rows) + "</table>"


def html_df(
    df: pd.DataFrame,
    float_format: str = ".4f",
    table_class: str = "",
    left_align: bool = False,
) -> str:
    """DataFrame → HTML table."""
    cls_attr = f' class="{table_class}"' if table_class else ""
    _td_sty = ' style="text-align:left"' if left_align else ""
    hdr = "<tr><th></th>" + "".join(f"<th>{c}</th>" for c in df.columns) + "</tr>"
    rows = [hdr]
    for idx, row in df.iterrows():
        cells = f"<th>{idx}</th>"
        for v in row:
            if isinstance(v, (float, np.floating)):
                if np.isnan(v):
                    cells += f"<td{_td_sty}></td>"
                else:
                    cells += f'<td class="{css_cls(v)}"{_td_sty}>{v:{float_format}}</td>'
            else:
                cells += f"<td{_td_sty}>{v}</td>"
        rows.append(f"<tr>{cells}</tr>")
    return f"<table{cls_attr}>" + "".join(rows) + "</table>"


def html_cards(
    d: Mapping[str, Any],
    keys: Iterable[str],
    pct_keys: Iterable[str] | None = None,
) -> str:
    """Render metric cards."""
    pct_keys = set(pct_keys or [])
    cards = []
    for k in keys:
        v = d.get(k, np.nan)
        css = css_cls(v)
        cards.append(
            f'<div class="card"><div class="val {css}">{fmt(v, pct=k in pct_keys)}</div>'
            f'<div class="lbl">{k}</div></div>'
        )
    return '<div class="cards">' + "".join(cards) + "</div>"


# =========================================================================
# JSON-safe data converters
# =========================================================================


def safe_list(
    arr: np.ndarray | Iterable[float],
    decimals: int = 6,
    pct: bool = False,
) -> list[float | None]:
    """Convert numpy array to JSON-safe list."""
    factor = 100.0 if pct else 1.0
    out: list[float | None] = []
    for v in np.asanyarray(arr, dtype=float):
        if np.isnan(v) or np.isinf(v):
            out.append(None)
        else:
            out.append(round(float(v) * factor, decimals))
    return out


def date_list(index: pd.DatetimeIndex) -> list[str]:
    """Convert DatetimeIndex to list of 'YYYY-MM-DD' strings."""
    return [d.strftime("%Y-%m-%d") for d in index]
