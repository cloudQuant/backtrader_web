#
# Copyright 2016 Quantopian, Inc.
# Copyright 2025 CloudQuant Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Drawdown-related metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fincore.metrics.returns import cum_returns
from fincore.utils import nanmin

__all__ = [
    "gen_drawdown_table",
    "get_all_drawdowns",
    "get_all_drawdowns_detailed",
    "get_max_drawdown",
    "get_max_drawdown_period",
    "get_max_drawdown_underwater",
    "get_top_drawdowns",
    "max_drawdown",
    "max_drawdown_days",
    "max_drawdown_months",
    "max_drawdown_recovery_days",
    "max_drawdown_recovery_months",
    "max_drawdown_recovery_weeks",
    "max_drawdown_weeks",
    "second_max_drawdown",
    "second_max_drawdown_days",
    "second_max_drawdown_recovery_days",
    "third_max_drawdown",
    "third_max_drawdown_days",
    "third_max_drawdown_recovery_days",
]


def max_drawdown(
    returns: pd.Series | pd.DataFrame | np.ndarray,
    out: np.ndarray | None = None,
) -> float | np.ndarray | pd.Series:
    """Determine the maximum drawdown of a return series.

    Maximum drawdown is defined as the minimum (most negative) percentage
    drop from a running maximum of cumulative returns.

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative simple returns.
    out : np.ndarray, optional
        pre-allocated output array. If provided, the result is
        written in-place into this array.

    Returns
    -------
    float or np.ndarray or pd.Series
        Maximum drawdown. For 1D input a scalar is returned; for 2D input
        one value is returned per column.
    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:])

    returns_1d = returns.ndim == 1

    if len(returns) < 1:
        assert out is not None  # for type checking
        out[()] = np.nan  # type: ignore[index]
        if returns_1d:
            out = out.item()  # type: ignore[attr-defined]
        return out

    returns_array = np.asanyarray(returns)

    cumulative = np.empty(
        (returns.shape[0] + 1, *returns.shape[1:]),
        dtype="float64",
    )
    cumulative[0] = start = 100
    cum_returns(returns_array, starting_value=start, out=cumulative[1:])

    max_return = np.fmax.accumulate(cumulative, axis=0)

    nanmin((cumulative - max_return) / max_return, axis=0, out=out)
    assert out is not None  # for type checking
    if returns_1d:
        out = out.item()  # type: ignore[attr-defined]
    elif allocated_output and isinstance(returns, pd.DataFrame):
        out = pd.Series(out)

    return out


def _identify_drawdown_periods(
    returns: pd.Series | np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool] | None:
    """Identify distinct drawdown periods in a return series.

    Shared helper used by :func:`get_all_drawdowns` and
    :func:`get_all_drawdowns_detailed` to avoid duplicating the
    cumulative-return / rolling-max / transition-detection logic.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative returns.

    Returns
    -------
    tuple or None
        ``(dd_vals, starts, ends, ends_in_dd)`` where *dd_vals* is the
        drawdown array, *starts*/*ends* are index arrays of period
        boundaries, and *ends_in_dd* indicates whether the series ends
        while still in drawdown.  Returns ``None`` when there are no
        drawdown periods.
    """
    if len(returns) < 1:
        return None

    if not isinstance(returns, pd.Series):
        returns = pd.Series(returns)

    cum_ret = cum_returns(returns, starting_value=100)
    rolling_max = cum_ret.expanding().max()  # type: ignore[union-attr]
    drawdown = (cum_ret - rolling_max) / rolling_max

    dd_vals = drawdown.values
    is_dd = dd_vals < 0

    if not is_dd.any():
        return None

    shifted = np.empty_like(is_dd)
    shifted[0] = False
    shifted[1:] = is_dd[:-1]
    starts = np.where(is_dd & ~shifted)[0]
    ends = np.where(~is_dd & shifted)[0]

    ends_in_dd = len(ends) < len(starts)
    if ends_in_dd:
        ends = np.append(ends, len(dd_vals))

    return dd_vals, starts, ends, ends_in_dd


def get_all_drawdowns(returns: pd.Series | np.ndarray) -> list[float]:
    """Extract all distinct drawdown values from a return series.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative returns.

    Returns
    -------
    list of float
        List of drawdown magnitudes (negative values) for each distinct
        drawdown period.
    """
    result = _identify_drawdown_periods(returns)
    if result is None:
        return []

    dd_vals, starts, ends, _ends_in_dd = result
    return [float(dd_vals[s:e].min()) for s, e in zip(starts, ends, strict=False)]


def get_all_drawdowns_detailed(returns: pd.Series | np.ndarray) -> list[dict]:
    """Extract detailed information about all drawdown periods.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative returns.

    Returns
    -------
    list of dict
        List of dictionaries with keys 'value', 'duration', 'recovery_duration'
        for each distinct drawdown period.
    """
    result = _identify_drawdown_periods(returns)
    if result is None:
        return []

    dd_vals, starts, ends, ends_in_dd = result

    drawdown_periods = []
    for k, (s, e) in enumerate(zip(starts, ends, strict=False)):
        segment = dd_vals[s:e]
        trough_offset = int(np.argmin(segment))
        trough_idx = s + trough_offset
        value = float(segment[trough_offset])
        duration = trough_idx - s
        recovery_duration = None if ends_in_dd and k == len(starts) - 1 else e - trough_idx
        drawdown_periods.append(
            {
                "value": value,
                "duration": duration,
                "recovery_duration": recovery_duration,
            }
        )

    return drawdown_periods


def get_max_drawdown(
    returns: pd.Series,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """Determine the maximum drawdown of a strategy.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.

    Returns
    -------
    peak : datetime
        The date of the peak before the maximum drawdown.
    valley : datetime
        The date of the trough (maximum drawdown).
    recovery : datetime
        The date of recovery or NaT if not recovered.
    """
    returns = returns.copy()
    df_cum = cum_returns(returns, 1.0)
    running_max = np.maximum.accumulate(df_cum)
    underwater = df_cum / running_max - 1
    return get_max_drawdown_underwater(underwater)


def get_max_drawdown_underwater(
    underwater: pd.Series,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """Determines peak, valley, and recovery dates given an underwater returns.

    Parameters
    ----------
    underwater : pd.Series
        Underwater returns (cumulative returns minus rolling max).

    Returns
    -------
    peak : datetime
        The date of the peak before the maximum drawdown.
    valley : datetime
        The date of the trough (maximum drawdown).
    recovery : datetime
        The date of recovery or NaT if not recovered.
    """
    if underwater.min() >= 0:
        return pd.NaT, pd.NaT, pd.NaT

    valley = underwater.idxmin()  # end of the period
    # Find first 0 (peak is where underwater == 0 before valley)
    try:
        peak = underwater[:valley][underwater[:valley] == 0].index[-1]
    except IndexError:
        peak = underwater.index[0]
    # Find last 0 (recovery is where underwater == 0 after valley)
    try:
        recovery = underwater[valley:][underwater[valley:] == 0].index[0]
    except IndexError:
        recovery = pd.NaT  # drawdown isn't recovered

    return peak, valley, recovery


def get_top_drawdowns(
    returns: pd.Series,
    top: int = 10,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Find top drawdowns, sorted by severity.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    top : int, optional
        The amount of top drawdowns to find (default 10).

    Returns
    -------
    drawdowns : list
        List of (peak, valley, recovery) tuples.
    """
    returns = returns.copy()
    df_cum = cum_returns(returns, starting_value=1.0)
    running_max = np.maximum.accumulate(df_cum)
    underwater = df_cum / running_max - 1

    drawdowns = []
    for _ in range(top):
        peak, valley, recovery = get_max_drawdown_underwater(underwater)
        if pd.isnull(peak) or pd.isnull(valley):
            break

        # Slice out draw-down period
        if not pd.isnull(recovery):
            underwater = underwater.drop(underwater[peak:recovery].index[1:-1])  # type: ignore[index,union-attr]
        else:
            # the drawdown has not ended yet
            underwater = underwater.loc[:peak]  # type: ignore[index,union-attr]

        drawdowns.append((peak, valley, recovery))
        if (len(returns) == 0) or (len(underwater) == 0):
            break

    return drawdowns


def gen_drawdown_table(returns: pd.Series, top: int = 10) -> pd.DataFrame:
    """Place top drawdowns in a table.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    top : int, optional
        The amount of top drawdowns to find (default 10).

    Returns
    -------
    df_drawdowns : pd.DataFrame
        Information about top drawdowns.
    """
    df_cum = cum_returns(returns, starting_value=1.0)
    drawdown_periods = get_top_drawdowns(returns, top=top)
    df_drawdowns = pd.DataFrame(
        index=list(range(top)),
        columns=[
            "Net drawdown in %",
            "Peak date",
            "Valley date",
            "Recovery date",
            "Duration",
        ],
    )

    for i, (peak, valley, recovery) in enumerate(drawdown_periods):
        if pd.isnull(recovery):
            df_drawdowns.loc[i, "Duration"] = np.nan
        else:
            df_drawdowns.loc[i, "Duration"] = len(pd.date_range(peak, recovery, freq="B"))

        df_drawdowns.loc[i, "Peak date"] = pd.to_datetime(peak).strftime("%Y-%m-%d")
        df_drawdowns.loc[i, "Valley date"] = pd.to_datetime(valley).strftime("%Y-%m-%d")

        if pd.isnull(recovery):
            df_drawdowns.loc[i, "Recovery date"] = recovery
        else:
            df_drawdowns.loc[i, "Recovery date"] = pd.to_datetime(recovery).strftime("%Y-%m-%d")

        df_drawdowns.loc[i, "Net drawdown in %"] = ((df_cum.loc[peak] - df_cum.loc[valley]) / df_cum.loc[peak]) * 100  # type: ignore[union-attr]

    df_drawdowns["Peak date"] = pd.to_datetime(df_drawdowns["Peak date"])
    df_drawdowns["Valley date"] = pd.to_datetime(df_drawdowns["Valley date"])
    df_drawdowns["Recovery date"] = pd.to_datetime(df_drawdowns["Recovery date"])

    return df_drawdowns


def get_max_drawdown_period(
    returns: pd.Series,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Get the start and end dates of the maximum drawdown period.

    Parameters
    ----------
    returns : pd.Series
        Non-cumulative returns indexed by date.

    Returns
    -------
    (pd.Timestamp, pd.Timestamp)
        Tuple ``(start_date, end_date)`` of the maximum drawdown period,
        or ``(None, None)`` if it cannot be determined.
    """
    if len(returns) < 1:
        return None, None

    cum_ret = cum_returns(returns, starting_value=1)

    if not isinstance(cum_ret, pd.Series):
        return None, None

    # Calculate rolling maximum
    rolling_max = cum_ret.expanding().max()  # type: ignore[union-attr]

    # Calculate drawdown
    drawdown = cum_ret / rolling_max - 1

    # Find the end date of maximum drawdown
    end_date = drawdown.idxmin()

    # Find the start date of maximum drawdown (previous peak)
    start_date = cum_ret.loc[:end_date].idxmax()  # type: ignore[union-attr]

    return start_date, end_date


def max_drawdown_days(returns: pd.Series | np.ndarray) -> int | float:
    """Calculate the duration of the maximum drawdown in days.

    Parameters
    ----------
    returns : pd.Series or array-like
        Non-cumulative returns indexed by date or position.

    Returns
    -------
    int or float
        Number of days (or periods) between the peak and trough of the
        maximum drawdown, or ``NaN`` if it cannot be determined.
    """
    if len(returns) < 1:
        return np.nan

    if not isinstance(returns, pd.Series):
        returns = pd.Series(returns)

    cum_ret = cum_returns(returns, starting_value=100)
    rolling_max = cum_ret.expanding().max()  # type: ignore[union-attr]

    drawdown = cum_ret / rolling_max - 1
    end_idx = drawdown.idxmin()
    start_idx = cum_ret.loc[:end_idx].idxmax()  # type: ignore[union-attr]

    if isinstance(returns.index, pd.DatetimeIndex):
        return (end_idx - start_idx).days  # type: ignore[union-attr]
    start_pos = returns.index.get_loc(start_idx)
    end_pos = returns.index.get_loc(end_idx)
    return end_pos - start_pos  # type: ignore[return-value]


def max_drawdown_weeks(returns: pd.Series | np.ndarray) -> float:
    """Calculate the duration of the maximum drawdown in weeks.

    Parameters
    ----------
    returns : pd.Series or array-like
        Non-cumulative returns indexed by date or position.

    Returns
    -------
    float
        Number of weeks between the peak and trough of the maximum
        drawdown, or ``NaN`` if it cannot be determined.
    """
    days = max_drawdown_days(returns)
    if np.isnan(days):
        return np.nan
    return days / 7


def max_drawdown_months(returns: pd.Series | np.ndarray) -> float:
    """Calculate the duration of the maximum drawdown in months.

    Parameters
    ----------
    returns : pd.Series or array-like
        Non-cumulative returns indexed by date or position.

    Returns
    -------
    float
        Number of months between the peak and trough of the maximum
        drawdown, or ``NaN`` if it cannot be determined.
    """
    days = max_drawdown_days(returns)
    if np.isnan(days):
        return np.nan
    return days / 30


def max_drawdown_recovery_days(returns: pd.Series | np.ndarray) -> int | float:
    """Calculate the recovery time from maximum drawdown in days.

    This computes the number of days (or periods) from the trough of the
    maximum drawdown until the portfolio value recovers to the previous
    peak.

    Parameters
    ----------
    returns : pd.Series or array-like
        Non-cumulative returns indexed by date or position.

    Returns
    -------
    int or float
        Number of days (or periods) from the trough to recovery, or
        ``NaN`` if recovery does not occur or cannot be determined.
    """
    if len(returns) < 1:
        return np.nan

    cum_ret = cum_returns(returns, starting_value=1)

    if not isinstance(cum_ret, pd.Series):
        return np.nan

    rolling_max = cum_ret.expanding().max()
    drawdown = cum_ret / rolling_max - 1

    max_dd_date = drawdown.idxmin()
    post_dd_data = cum_ret.loc[max_dd_date:]
    recovery_level = rolling_max.loc[max_dd_date]

    recovery_mask = post_dd_data >= recovery_level
    if recovery_mask.any():
        recovery_date = post_dd_data[recovery_mask].index[0]
        if hasattr(recovery_date - max_dd_date, "days"):
            return (recovery_date - max_dd_date).days
        return int(recovery_date - max_dd_date)
    return np.nan


def max_drawdown_recovery_weeks(returns: pd.Series | np.ndarray) -> float:
    """Calculate the recovery time from maximum drawdown in weeks.

    Parameters
    ----------
    returns : pd.Series or array-like
        Non-cumulative returns indexed by date or position.

    Returns
    -------
    float
        Number of weeks from the trough to recovery, or ``NaN`` if
        recovery does not occur or cannot be determined.
    """
    days = max_drawdown_recovery_days(returns)
    if np.isnan(days):
        return np.nan
    return days / 7


def max_drawdown_recovery_months(returns: pd.Series | np.ndarray) -> float:
    """Calculate the recovery time from maximum drawdown in months.

    Parameters
    ----------
    returns : pd.Series or array-like
        Non-cumulative returns indexed by date or position.

    Returns
    -------
    float
        Number of months from the trough to recovery, or ``NaN`` if
        recovery does not occur or cannot be determined.
    """
    days = max_drawdown_recovery_days(returns)
    if np.isnan(days):
        return np.nan
    return days / 30


def second_max_drawdown(returns: pd.Series | np.ndarray) -> float:
    """Determine the second-largest drawdown of a strategy.

    This identifies all distinct drawdown periods and returns the
    second-most severe (second-most negative) drawdown.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.

    Returns
    -------
    float
        Second-largest drawdown, or ``NaN`` if there are fewer than two
        drawdown periods.
    """
    drawdown_periods = get_all_drawdowns(returns)

    if len(drawdown_periods) < 2:
        return np.nan

    sorted_drawdowns = np.sort(drawdown_periods)
    return sorted_drawdowns[1]


def third_max_drawdown(returns: pd.Series | np.ndarray) -> float:
    """Determine the third-largest drawdown of a strategy.

    This identifies all distinct drawdown periods and returns the
    third-most severe (third-most negative) drawdown.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.

    Returns
    -------
    float
        Third-largest drawdown, or ``NaN`` if there are fewer than three
        drawdown periods.
    """
    drawdown_periods = get_all_drawdowns(returns)

    if len(drawdown_periods) < 3:
        return np.nan

    sorted_drawdowns = np.sort(drawdown_periods)
    return sorted_drawdowns[2]


def second_max_drawdown_days(returns: pd.Series | np.ndarray) -> int | float:
    """Calculate the duration of the second maximum drawdown in days.

    Parameters
    ----------
    returns : pd.Series or array-like
        Non-cumulative returns indexed by date or position.

    Returns
    -------
    int or float
        Number of days (or periods) between the peak and trough of the
        second-largest drawdown, or ``NaN`` if there are fewer than two
        drawdown periods.
    """
    drawdown_periods = get_all_drawdowns_detailed(returns)

    if len(drawdown_periods) < 2:
        return np.nan

    sorted_drawdowns = sorted(drawdown_periods, key=lambda x: x["value"])
    return sorted_drawdowns[1]["duration"]


def second_max_drawdown_recovery_days(returns: pd.Series | np.ndarray) -> int | float:
    """Calculate the recovery time from the second maximum drawdown in days.

    Parameters
    ----------
    returns : pd.Series or array-like
        Non-cumulative returns indexed by date or position.

    Returns
    -------
    int or float
        Number of days from the trough to recovery for the second-largest
        drawdown, or ``NaN`` if recovery does not occur or there are fewer
        than two drawdown periods.
    """
    drawdown_periods = get_all_drawdowns_detailed(returns)

    if len(drawdown_periods) < 2:
        return np.nan

    sorted_drawdowns = sorted(drawdown_periods, key=lambda x: x["value"])
    recovery_duration = sorted_drawdowns[1]["recovery_duration"]
    return recovery_duration if recovery_duration is not None else np.nan


def third_max_drawdown_days(returns: pd.Series | np.ndarray) -> int | float:
    """Calculate the duration of the third maximum drawdown in days.

    Parameters
    ----------
    returns : pd.Series or array-like
        Non-cumulative returns indexed by date or position.

    Returns
    -------
    int or float
        Number of days (or periods) between the peak and trough of the
        third-largest drawdown, or ``NaN`` if there are fewer than three
        drawdown periods.
    """
    drawdown_periods = get_all_drawdowns_detailed(returns)

    if len(drawdown_periods) < 3:
        return np.nan

    sorted_drawdowns = sorted(drawdown_periods, key=lambda x: x["value"])
    return sorted_drawdowns[2]["duration"]


def third_max_drawdown_recovery_days(returns: pd.Series | np.ndarray) -> int | float:
    """Calculate the recovery time from the third maximum drawdown in days.

    Parameters
    ----------
    returns : pd.Series or array-like
        Non-cumulative returns indexed by date or position.

    Returns
    -------
    int or float
        Number of days from the trough to recovery for the third-largest
        drawdown, or ``NaN`` if recovery does not occur or there are fewer
        than three drawdown periods.
    """
    drawdown_periods = get_all_drawdowns_detailed(returns)

    if len(drawdown_periods) < 3:
        return np.nan

    sorted_drawdowns = sorted(drawdown_periods, key=lambda x: x["value"])
    recovery_duration = sorted_drawdowns[2]["recovery_duration"]
    return recovery_duration if recovery_duration is not None else np.nan
