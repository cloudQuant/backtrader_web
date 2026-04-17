"""Common utilities for display, data handling, and formatting."""

import importlib
import warnings
from collections.abc import Callable
from functools import wraps
from itertools import cycle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import as_strided
from packaging import version
from pandas.testing import assert_frame_equal, assert_series_equal
from pandas.tseries.offsets import BDay

from fincore.constants.color import COLORS

__all__ = [
    "HAS_IPYTHON",
    "SETTINGS",
    "DisplayFunc",
    "HTMLFunc",
    "analyze_dataframe_differences",
    "analyze_series_differences",
    "check_intraday",
    "clip_returns_to_benchmark",
    "configure_legend",
    "customize",
    "default_returns_func",
    "detect_intraday",
    "estimate_intraday",
    "extract_rets_pos_txn_from_zipline",
    "format_asset",
    "get_month_end_freq",
    "get_symbol_rets",
    "get_utc_timestamp",
    "make_timezone_aware",
    "one_dec_places",
    "percentage",
    "print_table",
    "register_return_func",
    "rolling_window",
    "sample_colormap",
    "standardize_data",
    "to_series",
    "to_utc",
    "two_dec_places",
    "vectorize",
]


DisplayFunc = Callable[..., Any]
HTMLFunc = Callable[[str], Any]

try:
    _ipy_display_mod = importlib.import_module("IPython.display")
except ModuleNotFoundError:  # pragma: no cover
    _IPY_HTML = None
    _IPY_display = None
else:
    _IPY_HTML = getattr(_ipy_display_mod, "HTML", None)
    _IPY_display = getattr(_ipy_display_mod, "display", None)


def _fallback_display(*objs: Any, **_kwargs: Any) -> None:
    # Minimal fallback for non-IPython environments.
    print(*objs)


def _fallback_html(string: str) -> str:
    return string


HAS_IPYTHON = _IPY_display is not None
display: DisplayFunc = _IPY_display if _IPY_display is not None else _fallback_display
HTML: HTMLFunc = _IPY_HTML if _IPY_HTML is not None else _fallback_html


def customize(func):
    """Decorator to set plotting context and axes style during function call.

    This is primarily intended for methods of classes that implement
    ``plotting_context`` and ``axes_style`` (for example ``Pyfolio``).
    It leaves the function behavior unchanged other than temporarily
    applying those style contexts when ``set_context`` is True.
    """

    @wraps(func)
    def call_w_context(*args, **kwargs):
        set_context = kwargs.pop("set_context", True)

        # If used as a bound method, the first argument should be ``self``.
        if not set_context:
            return func(*args, **kwargs)

        if args and hasattr(args[0], "plotting_context") and hasattr(args[0], "axes_style"):
            self = args[0]
            with self.plotting_context(), self.axes_style():
                return func(*args, **kwargs)

        # Fallback: call without any special context if no plotting helpers exist.
        return func(*args, **kwargs)

    return call_w_context


def analyze_dataframe_differences(daily_txn, expected):
    """
    Analyze the differences between two DataFrames, `daily_txn` and `expected`.

    Parameters
    ----------
    daily_txn : pd.DataFrame
        The first DataFrame to compare.
    expected : pd.DataFrame
        The second DataFrame to compare.

    Returns
    -------
    None
        Prints the differences between the two DataFrames.
    """
    print("Analyzing differences between daily_txn and expected...")

    # Check if the DataFrames are equal
    try:
        assert_frame_equal(daily_txn, expected)
        print("The DataFrames are identical.")
    except AssertionError as e:
        print("The DataFrames are not identical. Details below:")
        print(e)

    # Compare index
    print("\nComparing Index:")
    if not daily_txn.index.equals(expected.index):
        print("Indices are different:")
        print("daily_txn index:", daily_txn.index)
        print("expected index:", expected.index)
        print("daily_txn index freq:", daily_txn.index.freq)
        print("expected index freq:", expected.index.freq)
    else:
        print("Indices are identical.")

    # Compare columns
    print("\nComparing Columns:")
    if not daily_txn.columns.equals(expected.columns):
        print("Columns are different:")
        print("daily_txn columns:", daily_txn.columns)
        print("expected columns:", expected.columns)
    else:
        print("Columns are identical.")

    # Compare dtypes
    print("\nComparing Dtypes:")
    if not daily_txn.dtypes.equals(expected.dtypes):
        print("Dtypes are different:")
        print("daily_txn dtypes:", daily_txn.dtypes)
        print("expected dtypes:", expected.dtypes)
    else:
        print("Dtypes are identical.")

    # Compare values
    print("\nComparing Values:")
    if not daily_txn.equals(expected):
        print("Values are different:")
        print("Differences in daily_txn vs expected:")
        print(
            pd.concat([daily_txn, expected], axis=1, keys=["daily_txn", "expected"])
            .swaplevel(axis=1)
            .sort_index(axis=1)
        )
    else:
        print("Values are identical.")

    # Compare metadata (e.g., index frequency)
    print("\nComparing Metadata:")
    if daily_txn.index.freq != expected.index.freq:
        print("Index frequencies are different:")
        print("daily_txn index freq:", daily_txn.index.freq)
        print("expected index freq:", expected.index.freq)
    else:
        print("Index frequencies are identical.")


def analyze_series_differences(series1, series2):
    """
    Analyze the differences between two Series, `series1` and `series2`.

    Parameters
    ----------
    series1 : pd.Series
        The first Series to compare.
    series2 : pd.Series
        The second Series to compare.

    Returns
    -------
    None
        Prints the differences between the two Series.
    """
    print("Analyzing differences between series1 and series2...")

    # Check if the Series are equal
    try:
        assert_series_equal(series1, series2)
        print("The Series are identical.")
    except AssertionError as e:
        print("The Series are not identical. Details below:")
        print(e)

    # Compare index
    print("\nComparing Index:")
    if not series1.index.equals(series2.index):
        print("Indices are different:")
        print("series1 index:", series1.index)
        print("series2 index:", series2.index)
        print("series1 index freq:", series1.index.freq)
        print("series2 index freq:", series2.index.freq)
    else:
        print("Indices are identical.")

    # Compare dtypes
    print("\nComparing Dtypes:")
    if series1.dtype != series2.dtype:
        print("Dtypes are different:")
        print("series1 dtype:", series1.dtype)
        print("series2 dtype:", series2.dtype)
    else:
        print("Dtypes are identical.")

    # Compare values
    print("\nComparing Values:")
    if not series1.equals(series2):
        print("Values are different:")
        print("Differences in series1 vs series2:")
        # Use explicit column names to avoid relying on MultiIndex columns.
        differences = pd.concat(
            [series1.rename("series1"), series2.rename("series2")],
            axis=1,
        )
        print(differences[differences["series1"] != differences["series2"]])
    else:
        print("Values are identical.")

    # Compare metadata (e.g., index frequency)
    print("\nComparing Metadata:")
    if series1.index.freq != series2.index.freq:
        print("Index frequencies are different:")
        print("series1 index freq:", series1.index.freq)
        print("series2 index freq:", series2.index.freq)
    else:
        print("Index frequencies are identical.")


def one_dec_places(x, _pos):
    """
    Adds 1/10th decimal to plot ticks.
    """

    return "%.1f" % x


def two_dec_places(x, _pos):
    """
    Adds 1/100th decimal to plot ticks.
    """

    return "%.2f" % x


def percentage(x, _pos):
    """
    Adds percentage sign to plot ticks.
    """

    return "%.0f%%" % x


def format_asset(asset):
    """
    If zipline asset objects are used, we want to print them out prettily
    within the tear sheet. This function should only be applied directly
    before displaying.
    """

    try:
        import zipline.assets
    except ImportError:
        return asset

    if isinstance(asset, zipline.assets.Asset):
        return asset.symbol
    return asset


def vectorize(func):
    """
    Decorator so that functions can be written to work on Series but
    may still be called with DataFrames.
    """

    def wrapper(df, *args, **kwargs):
        if df.ndim == 1:
            return func(df, *args, **kwargs)
        if df.ndim == 2:
            return df.apply(func, *args, **kwargs)
        return None

    return wrapper


def extract_rets_pos_txn_from_zipline(backtest):
    """
    Extract returns, positions, transactions and leverage from the
    backtest data structure returned by zipline.TradingAlgorithm.run().

    The returned data structures are in a format compatible with the
    rest of pyfolio and can be directly passed to
    e.g., tears.create_full_tear_sheet().

    Parameters
    ----------
    backtest : pd.DataFrame :
        DataFrame returned by zipline.TradingAlgorithm.run()

    Returns
    -------
    returns : pd.Series
        Daily returns of strategy.
         - See full explanation in tears.create_full_tear_sheet.
    positions : pd.DataFrame
        Daily net position values.
         - See full explanation in tears.create_full_tear_sheet.
    transactions : pd.DataFrame
        Prices and `amounts` of executed trades.One row per trade.
         - See full explanation in tears.create_full_tear_sheet.


    Example (on the Quantopian research platform)
    ---------------------------------------------
    # >>> backtest = my_algo.run()
    # >>> returns, positions, transactions =
    # >>> pyfolio.utils.extract_rets_pos_txn_from_zipline(backtest)
    # >>> pyfolio.tears.create_full_tear_sheet(returns,
    # >>> positions, transactions)
    """

    backtest.index = backtest.index.normalize()
    if backtest.index.tzinfo is None:
        backtest.index = backtest.index.tz_localize("UTC")
    returns = backtest.returns
    raw_positions = []
    for dt, pos_row in backtest.positions.items():
        df = pd.DataFrame(pos_row)
        df.index = [dt] * len(df)
        raw_positions.append(df)
    if not raw_positions:
        raise ValueError("The backtest does not have any positions.")
    positions = pd.concat(raw_positions)

    # Lazy import to avoid circular dependency: fincore -> empyrical -> utils.common_utils
    from fincore.empyrical import Empyrical

    positions = Empyrical.extract_pos(positions, backtest.ending_cash)
    transactions = Empyrical.make_transaction_frame(backtest.transactions)

    if transactions.index.tzinfo is None:
        transactions.index = transactions.index.tz_localize("utc")

    return returns, positions, transactions


def print_table(table, name=None, float_format=None, formatters=None, header_rows=None, run_flask_app=False):
    """
    Pretty print a pandas DataFrame.

    Uses HTML output if running inside Jupyter Notebook, otherwise
    formatted text output.

    Parameters
    ----------
    table : pandas.Series or pandas.DataFrame
        Table to pretty-print.
    name : str, optional
        Table name to display in the upper-left corner.
    float_format : function, optional
        Formatter to use for displaying table elements, passed as the
        `float_format` arg to pd.Dataframe.to_html.
        E.g. `'{0:.2%}'.format` for displaying 100 as '100.00%'.
    formatters : list or dict, optional
        Formatters to use by column, passed as the `formatters` arg to
        pd.Dataframe.to_html.
    header_rows : dict, optional
        Extra rows to display at the top of the table.
    run_flask_app : bool, optional, default False
        Whether to run Flask app for displaying table in a web browser.
    """

    if isinstance(table, pd.Series):
        table = pd.DataFrame(table)

    if name is not None:
        table.columns.name = name

    html = table.to_html(float_format=float_format, formatters=formatters)

    if header_rows is not None:
        # Count the number of columns for the text to span
        n_cols = html.split("<thead>")[1].split("</thead>")[0].count("<th>")

        # Generate the HTML for the extra rows
        rows = ""
        for name, value in header_rows.items():
            rows += ('\n    <tr style="text-align: right;"><th>%s</th>' + "<td colspan=%d>%s</td></tr>") % (
                name,
                n_cols,
                value,
            )
        # Inject the new HTML
        html = html.replace("<thead>", "<thead>" + rows)
    if run_flask_app:
        # If running via the Flask app, persist the table under a local static/ directory.
        data_root = Path(__file__).parent
        target_static_path = data_root / "static"
        target_static_path.mkdir(parents=True, exist_ok=True)
        excel_file_path = target_static_path / f"strategy_performance_{name}.xlsx"
        try:
            table.to_excel(excel_file_path, index=True)
        except (OSError, ValueError) as e:
            import logging

            logging.getLogger(__name__).warning("Failed to save table export: %s", e)
    display(HTML(html))


def standardize_data(x):
    """
    Standardize an array with mean and standard deviation.

    Parameters
    ----------
    x : np.array
        Array to standardize.

    Returns
    -------
    np.array
        Standardized array.
    """

    return (x - np.mean(x)) / np.std(x)


def detect_intraday(positions, transactions, threshold=0.25):
    """
    Attempt to detect an intraday strategy. Get the number of
    positions held at the end of the day, and divide that by the
    number of unique stocks transacted every day. If the average quotient
    is below a threshold, then an intraday strategy is detected.

    Parameters
    ----------
    positions : pd.DataFrame
        Daily net position values.
         - See full explanation in create_full_tear_sheet.
    transactions : pd.DataFrame
        Prices and `amounts` of executed trades. One row per trade.
         - See full explanation in create_full_tear_sheet.
    threshold : default 0.25
    Returns
    -------
    boolean
        True if an intraday strategy is detected.
    """

    daily_txn = transactions.copy()
    daily_txn.index = daily_txn.index.date
    txn_count = daily_txn.groupby(level=0).symbol.nunique().sum()
    daily_pos = positions.drop("cash", axis=1).replace(0, np.nan)
    return daily_pos.count(axis=1).sum() / txn_count < threshold


def check_intraday(estimate, returns, positions, transactions):
    """
    Logic for checking if a strategy is intraday and processing it.

    Parameters
    ----------
    estimate: boolean or str, optional
        Approximate returns for intraday strategies.
        See description in tears.create_full_tear_sheet.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in create_full_tear_sheet.
    positions : pd.DataFrame
        Daily net position values.
         - See full explanation in create_full_tear_sheet.
    transactions : pd.DataFrame
        Prices and `amounts` of executed trades.One row per trade.
         - See full explanation in create_full_tear_sheet.

    Returns
    -------
    pd.DataFrame
        Daily net position values, adjusted for intraday movement.
    """

    if estimate == "infer":
        if positions is not None and transactions is not None:
            if detect_intraday(positions, transactions):
                warnings.warn(
                    "Detected intraday strategy; inferring positions from transactions. Set estimate_intraday"
                    + "=False to disable.",
                    stacklevel=2,
                )
                return estimate_intraday(returns, positions, transactions)
            return positions
        return positions

    if estimate:
        if positions is not None and transactions is not None:
            return estimate_intraday(returns, positions, transactions)
        raise ValueError("Positions and txns needed to estimate intraday")
    return positions


def estimate_intraday(returns, positions, transactions, eod_hour=23):
    """
    Intraday strategies will often not hold positions at the day end.
    This attempts to find the point in the day that best represents
    the activity of the strategy on that day, and effectively resamples
    the end-of-day positions with the positions at this point of day.
    The point of day is found by detecting when our exposure in the
    market is at its maximum point. Note that this is an estimate.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in create_full_tear_sheet.
    positions : pd.DataFrame
        Daily net position values.
         - See full explanation in create_full_tear_sheet.
    transactions : pd.DataFrame
        Prices and `amounts` of executed trades. One row per trade.
         - See full explanation in create_full_tear_sheet.
    eod_hour: default 23

    Returns
    -------
    pd.DataFrame
        Daily net position values, resampled for intraday behavior.
    """

    # Construct DataFrame of transaction amounts
    txn_val = transactions.copy()
    txn_val.index.names = ["date"]
    txn_val["value"] = txn_val.amount * txn_val.price
    txn_val = txn_val.reset_index().pivot_table(index="date", values="value", columns="symbol").replace(np.nan, 0)

    # Cumulate transaction amounts each day
    txn_val["day"] = txn_val.index.date
    txn_val = txn_val.groupby("day").cumsum()

    # Calculate exposure, then take peak of exposure every day
    txn_val["exposure"] = txn_val.abs().sum(axis=1)
    condition = txn_val["exposure"] == txn_val.groupby(pd.Grouper(freq="24h"))["exposure"].transform("max")
    txn_val = txn_val[condition].drop("exposure", axis=1)

    # Compute cash delta
    txn_val["cash"] = -txn_val.sum(axis=1)

    # Shift EOD positions to positions at start of next trading day
    positions_shifted = positions.copy().shift(1).fillna(0)
    divisor = 1 + returns.iloc[0]
    if divisor == 0 or not np.isfinite(divisor):
        divisor = 1.0
    starting_capital = positions.iloc[0].sum() / divisor
    positions_shifted.iloc[0, positions_shifted.columns.get_loc("cash")] = starting_capital

    # Format and add start positions to intraday position changes
    txn_val.index = txn_val.index.normalize()
    corrected_positions = positions_shifted.add(txn_val, fill_value=0)
    corrected_positions.index.name = "period_close"
    corrected_positions.columns.name = "sid"

    return corrected_positions


def clip_returns_to_benchmark(rets, benchmark_rets):
    """
    Drop entries from rets so that the start and end dates of rets match those
    of benchmark_rets.

    Parameters
    ----------
    rets : pd.Series
        Daily returns of the strategy, noncumulative.
         - See create_full_tear_sheet for more details

    benchmark_rets : pd.Series
        Daily returns of the benchmark, noncumulative.

    Returns
    -------
    clipped_rets : pd.Series
        Daily noncumulative returns with index clipped to match that of
        benchmark returns.
    """

    if (rets.index[0] < benchmark_rets.index[0]) or (rets.index[-1] > benchmark_rets.index[-1]):
        clipped_rets = rets[benchmark_rets.index]
    else:
        clipped_rets = rets

    return clipped_rets


def to_utc(df):
    """
    For use in tests, applied UTC timestamp to DataFrame.
    """

    try:
        df.index = df.index.tz_localize("UTC")
    except TypeError:
        df.index = df.index.tz_convert("UTC")

    return df


def to_series(df):
    """
    For use in tests; converts DataFrame's first column to Series.
    """

    return df[df.columns[0]]


def get_month_end_freq():
    """
    Get the appropriate month-end frequency string based on pandas version.

    Returns
    -------
    str
        'M' for pandas < 2.2.0, 'ME' for pandas >= 2.2.0
    """
    if version.parse(pd.__version__) < version.parse("2.2.0"):
        return "M"
    return "ME"


def make_timezone_aware(timestamp, target_tz):
    """
    Ensure a timestamp has the same timezone as target_tz.

    Parameters
    ----------
    timestamp : pd.Timestamp
        The timestamp to adjust
    target_tz : timezone or None
        The target timezone

    Returns
    -------
    pd.Timestamp
        Timestamp with matching timezone
    """
    if target_tz is not None:
        if timestamp.tz is None:
            return timestamp.tz_localize(target_tz)
        return timestamp.tz_convert(target_tz)
    if timestamp.tz is not None:
        # Target is tz-naive but timestamp is tz-aware, remove tz
        return timestamp.tz_localize(None)
    return timestamp


# These functions are simply a passthrough to empyrical, but is
# required by the register_returns_func and get_symbol_rets.

# Settings dict to store functions/values that may
# need to be overridden depending on the user's environment. To avoid
# circular imports with fincore.empyrical, we define the default as a
# small wrapper that imports Empyrical lazily on first use.


def _default_returns_func(*args, **kwargs):
    from fincore.empyrical import Empyrical

    return Empyrical.annual_return(*args, **kwargs)


SETTINGS = {"returns_func": _default_returns_func}


def register_return_func(func):
    """
    Registers the 'returns_func' that will be called for
    retrieving returns data.

    Parameters
    ----------
    func : function
        A function that returns a pandas Series of asset returns.
        The signature of the function must be as follows

        >>> func(symbol)

        Where symbol is an asset identifier

    Returns
    -------
    None
    """

    SETTINGS["returns_func"] = func


def get_symbol_rets(symbol, start=None, end=None):
    """
    Calls the currently registered 'returns_func'

    Parameters
    ----------
    symbol : object
        An identifier for the asset whose return
        series is desired.
        e.g., ticker symbol or database ID
    start : date, optional
        Earliest date to fetch data for.
        Defaults to the earliest date available.
    end : date, optional
        Latest date to fetch data for.
        Defaults to the latest date available.

    Returns
    -------
    pandas.Series
        Returned by the current 'returns_func'
    """

    return SETTINGS["returns_func"](symbol, start=start, end=end)


def configure_legend(ax, autofmt_xdate=True, change_colors=False, rotation=30, ha="right"):
    """
    Format legend for perf attribution plots:
    - put legend to the right of plot instead of overlapping with it
    - make legend order match up with graph lines
    - set colors, according to colormap
    """
    chart_box = ax.get_position()
    ax.set_position([chart_box.x0, chart_box.y0, chart_box.width * 0.75, chart_box.height])

    # make legend order match graph lines
    handles, labels = ax.get_legend_handles_labels()
    if len(labels) == 0:
        return

    def _legend_sort_key(item):
        handle = item[0]
        ydata_fn = getattr(handle, "get_ydata", None)
        if callable(ydata_fn):
            try:
                y = ydata_fn()
                return float(y[-1])
            except (TypeError, ValueError, IndexError):  # pragma: no cover -- Edge case for legend sorting
                return 0.0
        return 0.0

    handles_and_labels_sorted = sorted(
        zip(handles, labels, strict=False),
        key=_legend_sort_key,
        reverse=True,
    )

    handles_sorted = [h[0] for h in handles_and_labels_sorted]
    labels_sorted = [h[1] for h in handles_and_labels_sorted]

    if change_colors:
        for handle, color in zip(handles_sorted, cycle(COLORS), strict=False):
            handle.set_color(color)

    ax.legend(
        handles=handles_sorted,
        labels=labels_sorted,
        frameon=True,
        framealpha=0.5,
        loc="upper left",
        bbox_to_anchor=(1.05, 1),
        fontsize="large",
    )

    # manually rotate xticklabels instead of using matplotlib's autofmt_xdate
    # because it disables xticklabels for all but the last plot
    if autofmt_xdate:
        for label in ax.get_xticklabels():
            label.set_ha(ha)
            label.set_rotation(rotation)


def sample_colormap(cmap_name, n_samples):
    """
    Sample a colormap from matplotlib
    """
    import matplotlib as mpl

    # Use the non-deprecated colormaps registry (matplotlib >= 3.5).
    colormap = mpl.colormaps[cmap_name]

    return [colormap(i) for i in np.linspace(0, 1, n_samples)]


def get_utc_timestamp(dt):
    """
    Returns the Timestamp/DatetimeIndex
    with either localized or converted to UTC.

    Parameters
    ----------
    dt : Timestamp/DatetimeIndex
        the date(s) to be converted

    Returns
    -------
    same type as input
        date(s) converted to UTC
    """

    dt = pd.to_datetime(dt)
    try:
        dt = dt.tz_localize("UTC")
    except TypeError:
        dt = dt.tz_convert("UTC")
    return dt


_1_bday = BDay()


def _1_bday_ago():
    return pd.Timestamp.now().normalize() - _1_bday


def rolling_window(array, length, mutable=False):
    """
    Restride an array of shape

        (X_0, ... X_N)

    Into an array of shape

        (length, X_0 - length + 1, ... X_N)

    Where each slice at index i along the first axis is equivalent to

        Result[i] = array[length * i:length * (i + 1)]

    Parameters
    ----------
    array : np.ndarray
        The base array.
    length : int
        Length of the synthetic first axis to generate.
    mutable : bool, optional
        Return a mutable array? The returned array shares the same memory as
        the input array. This means that writes into the returned array affect
        ``array``. The returned array also uses strides to map the same values
        to multiple indices. Writes to a single index may appear to change many
        values in the returned array.

    Returns
    -------
    out : np.ndarray

    Example
    -------
    >>> from numpy import arange
    >>> a = arange(25).reshape(5, 5)
    >>> print(a)
    array([[ 0,  1,  2,  3,  4],
           [ 5,  6,  7,  8,  9],
           [10, 11, 12, 13, 14],
           [15, 16, 17, 18, 19],
           [20, 21, 22, 23, 24]])

    >>> rolling_window(a, 2)
    array([[[ 0,  1,  2,  3,  4],
            [ 5,  6,  7,  8,  9]],
    <BLANKLINE>
           [[ 5,  6,  7,  8,  9],
            [10, 11, 12, 13, 14]],
    <BLANKLINE>
           [[10, 11, 12, 13, 14],
            [15, 16, 17, 18, 19]],
    <BLANKLINE>
           [[15, 16, 17, 18, 19],
            [20, 21, 22, 23, 24]]])
    """
    if not length:
        raise ValueError("Can't have 0-length window")

    orig_shape = array.shape
    if not orig_shape:
        raise IndexError("Can't restride a scalar.")
    if orig_shape[0] < length:
        raise IndexError(f"Can't restride array of shape {orig_shape} with a window length of {length}")

    num_windows = orig_shape[0] - length + 1
    new_shape = (num_windows, length, *orig_shape[1:])

    new_strides = (array.strides[0], *array.strides)

    # Prefer the `writeable` kwarg when available; some NumPy versions disallow
    # flipping the WRITEABLE flag on as_strided views after creation.
    try:
        out = as_strided(array, new_shape, new_strides, writeable=mutable)
    except TypeError:
        out = as_strided(array, new_shape, new_strides)
        if mutable:
            try:
                out.setflags(write=True)
            except ValueError as e:
                raise ValueError(
                    "Cannot create a writable rolling window view on this NumPy build; use mutable=False instead."
                ) from e
    return out


def default_returns_func(returns):
    """
    Default returns processing function.

    This is a simple passthrough function that returns the input as-is.
    It's used by pyfolio for returns processing compatibility.
    """
    return returns
