"""Pyfolio class: tear sheet generation and plotting utilities.

Extends Empyrical with ~66 methods: tear sheet creation (~11), plotting (~30),
and helpers (adjust_returns_for_slippage, get_leverage).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

import matplotlib
import matplotlib.pyplot as plt

from fincore.constants import (
    APPROX_BDAYS_PER_MONTH,
    CAPACITY_SWEEP_MAX_PV,
    CAPACITY_SWEEP_MIN_PV,
    CAPACITY_SWEEP_STEP,
    FACTOR_PARTITIONS,
)
from fincore.utils.common_utils import customize

DisplayFunc = Callable[..., Any]
MarkdownFunc = Callable[[str], Any]


def _fallback_display(*objs: Any, **_kwargs: Any) -> None:
    print(*objs)


def _fallback_markdown(text: str) -> str:
    return text


display: DisplayFunc = _fallback_display
Markdown: MarkdownFunc = _fallback_markdown

try:
    _ipy_display_mod = importlib.import_module("IPython.display")
except ModuleNotFoundError:  # pragma: no cover
    pass
else:
    display = getattr(_ipy_display_mod, "display", _fallback_display)
    Markdown = getattr(_ipy_display_mod, "Markdown", _fallback_markdown)

if matplotlib.get_backend().lower() in ("", "agg") or not hasattr(matplotlib, "_called_from_pytest"):
    try:
        matplotlib.use("Agg")
    except (ImportError, RuntimeError) as e:  # pragma: no cover -- Edge case for matplotlib backend
        import logging

        logging.getLogger(__name__).debug("matplotlib.use('Agg') failed: %s", e)
cmap = plt.get_cmap("gist_rainbow")


from fincore.empyrical import Empyrical
from fincore.tearsheets import (
    _plot_bayes_cone as _plot_bayes_cone_internal,
)
from fincore.tearsheets import (
    axes_style as _axes_style,
)
from fincore.tearsheets import (
    create_bayesian_tear_sheet as _create_bayesian_tear_sheet,
)
from fincore.tearsheets import (
    create_capacity_tear_sheet as _create_capacity_tear_sheet,
)
from fincore.tearsheets import (
    # sheets
    create_full_tear_sheet as _create_full_tear_sheet,
)
from fincore.tearsheets import (
    create_interesting_times_tear_sheet as _create_interesting_times_tear_sheet,
)
from fincore.tearsheets import (
    create_perf_attrib_tear_sheet as _create_perf_attrib_tear_sheet,
)
from fincore.tearsheets import (
    create_position_tear_sheet as _create_position_tear_sheet,
)
from fincore.tearsheets import (
    create_returns_tear_sheet as _create_returns_tear_sheet,
)
from fincore.tearsheets import (
    create_risk_tear_sheet as _create_risk_tear_sheet,
)
from fincore.tearsheets import (
    create_round_trip_tear_sheet as _create_round_trip_tear_sheet,
)
from fincore.tearsheets import (
    create_simple_tear_sheet as _create_simple_tear_sheet,
)
from fincore.tearsheets import (
    create_txn_tear_sheet as _create_txn_tear_sheet,
)
from fincore.tearsheets import (
    plot_alpha_returns as _plot_alpha_returns,
)
from fincore.tearsheets import (
    plot_annual_returns as _plot_annual_returns,
)
from fincore.tearsheets import (
    plot_bayes_cone as _plot_bayes_cone,
)
from fincore.tearsheets import (
    # bayesian
    plot_best as _plot_best,
)
from fincore.tearsheets import (
    plot_cap_exposures_gross as _plot_cap_exposures_gross,
)
from fincore.tearsheets import (
    plot_cap_exposures_longshort as _plot_cap_exposures_longshort,
)
from fincore.tearsheets import (
    plot_cap_exposures_net as _plot_cap_exposures_net,
)
from fincore.tearsheets import (
    # capacity
    plot_capacity_sweep as _plot_capacity_sweep,
)
from fincore.tearsheets import (
    plot_cones as _plot_cones,
)
from fincore.tearsheets import (
    plot_daily_turnover_hist as _plot_daily_turnover_hist,
)
from fincore.tearsheets import (
    plot_daily_volume as _plot_daily_volume,
)
from fincore.tearsheets import (
    plot_drawdown_periods as _plot_drawdown_periods,
)
from fincore.tearsheets import (
    plot_drawdown_underwater as _plot_drawdown_underwater,
)
from fincore.tearsheets import (
    plot_exposures as _plot_exposures,
)
from fincore.tearsheets import (
    plot_factor_contribution_to_perf as _plot_factor_contribution_to_perf,
)
from fincore.tearsheets import (
    plot_gross_leverage as _plot_gross_leverage,
)
from fincore.tearsheets import (
    # positions
    plot_holdings as _plot_holdings,
)
from fincore.tearsheets import (
    plot_long_short_holdings as _plot_long_short_holdings,
)
from fincore.tearsheets import (
    plot_max_median_position_concentration as _plot_max_median_position_concentration,
)
from fincore.tearsheets import (
    plot_monthly_returns_dist as _plot_monthly_returns_dist,
)
from fincore.tearsheets import (
    plot_monthly_returns_heatmap as _plot_monthly_returns_heatmap,
)
from fincore.tearsheets import (
    plot_monthly_returns_timeseries as _plot_monthly_returns_timeseries,
)
from fincore.tearsheets import (
    plot_perf_attrib_returns as _plot_perf_attrib_returns,
)
from fincore.tearsheets import (
    plot_perf_stats as _plot_perf_stats,
)
from fincore.tearsheets import (
    plot_prob_profit_trade as _plot_prob_profit_trade,
)
from fincore.tearsheets import (
    plot_return_quantiles as _plot_return_quantiles,
)
from fincore.tearsheets import (
    plot_returns as _plot_returns,
)
from fincore.tearsheets import (
    plot_risk_exposures as _plot_risk_exposures,
)
from fincore.tearsheets import (
    plot_rolling_beta as _plot_rolling_beta,
)
from fincore.tearsheets import (
    plot_rolling_returns as _plot_rolling_returns,
)
from fincore.tearsheets import (
    plot_rolling_sharpe as _plot_rolling_sharpe,
)
from fincore.tearsheets import (
    plot_rolling_volatility as _plot_rolling_volatility,
)
from fincore.tearsheets import (
    # round_trips
    plot_round_trip_lifetimes as _plot_round_trip_lifetimes,
)
from fincore.tearsheets import (
    plot_sector_allocations as _plot_sector_allocations,
)
from fincore.tearsheets import (
    plot_sector_exposures_gross as _plot_sector_exposures_gross,
)
from fincore.tearsheets import (
    plot_sector_exposures_longshort as _plot_sector_exposures_longshort,
)
from fincore.tearsheets import (
    plot_sector_exposures_net as _plot_sector_exposures_net,
)
from fincore.tearsheets import (
    plot_slippage_sensitivity as _plot_slippage_sensitivity,
)
from fincore.tearsheets import (
    plot_slippage_sweep as _plot_slippage_sweep,
)
from fincore.tearsheets import (
    plot_stoch_vol as _plot_stoch_vol,
)
from fincore.tearsheets import (
    # risk
    plot_style_factor_exposures as _plot_style_factor_exposures,
)
from fincore.tearsheets import (
    # transactions
    plot_turnover as _plot_turnover,
)
from fincore.tearsheets import (
    plot_txn_time_hist as _plot_txn_time_hist,
)
from fincore.tearsheets import (
    plot_volume_exposures_gross as _plot_volume_exposures_gross,
)
from fincore.tearsheets import (
    plot_volume_exposures_longshort as _plot_volume_exposures_longshort,
)

# Import plotting and display helpers from tearsheets.
from fincore.tearsheets import (
    # utils
    plotting_context as _plotting_context,
)
from fincore.tearsheets import (
    print_round_trip_stats as _print_round_trip_stats,
)
from fincore.tearsheets import (
    show_and_plot_top_positions as _show_and_plot_top_positions,
)
from fincore.tearsheets import (
    show_perf_attrib_stats as _show_perf_attrib_stats,
)
from fincore.tearsheets import (
    show_perf_stats as _show_perf_stats,
)
from fincore.tearsheets import (
    show_profit_attribution as _show_profit_attribution,
)
from fincore.tearsheets import (
    show_worst_drawdown_periods as _show_worst_drawdown_periods,
)

__all__ = ["DisplayFunc", "MarkdownFunc", "Pyfolio"]


class Pyfolio(Empyrical):
    def __init__(
        self,
        returns=None,
        positions=None,
        transactions=None,
        market_data=None,
        benchmark_rets=None,
        slippage=None,
        live_start_date=None,
        sector_mappings=None,
        bayesian=False,
        round_trips=False,
        estimate_intraday="infer",
        hide_positions=False,
        cone_std=(1.0, 1.5, 2.0),
        bootstrap=False,
        unadjusted_returns=None,
        style_factor_panel=None,
        sectors=None,
        caps=None,
        shares_held=None,
        volumes=None,
        percentile=None,
        turnover_denom="AGB",
        set_context=True,
        factor_returns=None,
        factor_loadings=None,
        pos_in_dollars=True,
        header_rows=None,
        factor_partitions=None,
    ):
        """
        Initialize a Pyfolio instance.

        Parameters
        ----------
        returns : pd.Series, optional
            Daily returns of the strategy, noncumulative.
        positions : pd.DataFrame, optional
            Daily net position values.
        transactions : pd.DataFrame, optional
            Executed trade volumes and fill prices.
        market_data : pd.Panel or dict, optional
            Panel/dict with items axis of 'price' and 'volume' DataFrames.
        benchmark_rets : pd.Series, optional
            Benchmark returns for comparison.
        factor_returns : pd.DataFrame, optional
            Returns by factor, with date as index and factors as columns.
        factor_loadings : pd.DataFrame, optional
            Factor loadings for all days in the date range.
        ... (other parameters are consistent with ``create_full_tear_sheet``)
        """
        super().__init__(
            returns=returns, positions=positions, factor_returns=factor_returns, factor_loadings=factor_loadings
        )
        self.transactions = transactions
        self.market_data = market_data
        self.benchmark_rets = benchmark_rets
        self.slippage = slippage
        self.live_start_date = live_start_date
        self.sector_mappings = sector_mappings
        self.bayesian = bayesian
        self.round_trips = round_trips
        self.estimate_intraday = estimate_intraday
        self.hide_positions = hide_positions
        self.cone_std = cone_std
        self.bootstrap = bootstrap
        self.unadjusted_returns = unadjusted_returns
        self.style_factor_panel = style_factor_panel
        self.sectors = sectors
        self.caps = caps
        self.shares_held = shares_held
        self.volumes = volumes
        self.percentile = percentile
        self.turnover_denom = turnover_denom
        self.set_context = set_context
        self.pos_in_dollars = pos_in_dollars
        self.header_rows = header_rows
        self.factor_partitions = factor_partitions

    def plot_best(self, trace=None, data_train=None, data_test=None, samples=1000, burn=200, axs=None):
        """
        Plot the BEST significance analysis.
        See fincore.tearsheets.bayesian.plot_best for full documentation.
        """
        return _plot_best(
            self, trace=trace, data_train=data_train, data_test=data_test, samples=samples, burn=burn, axs=axs
        )

    def plot_stoch_vol(self, data, trace=None, ax=None):
        """
        Plot stochastic volatility model.
        See fincore.tearsheets.bayesian.plot_stoch_vol for full documentation.
        """
        return _plot_stoch_vol(self, data, trace=trace, ax=ax)

    def _plot_bayes_cone(self, returns_train, returns_test, preds, plot_train_len=None, ax=None):
        """
        Internal Bayesian cone plot.
        See fincore.tearsheets.bayesian._plot_bayes_cone for full documentation.
        """
        # Avoid Python name-mangling for ``__name`` identifiers inside classes.
        return _plot_bayes_cone_internal(self, returns_train, returns_test, preds, plot_train_len=plot_train_len, ax=ax)

    def plot_bayes_cone(self, returns_train, returns_test, ppc, plot_train_len=50, ax=None):
        """
        Generate Bayesian cone plot.
        See fincore.tearsheets.bayesian.plot_bayes_cone for full documentation.
        """
        return _plot_bayes_cone(self, returns_train, returns_test, ppc, plot_train_len=plot_train_len, ax=ax)

    def plot_style_factor_exposures(self, tot_style_factor_exposure, factor_name=None, ax=None):
        """
        Plots style factor exposures.
        See fincore.tearsheets.risk.plot_style_factor_exposures for full documentation.
        """
        return _plot_style_factor_exposures(tot_style_factor_exposure, factor_name=factor_name, ax=ax)

    def plot_sector_exposures_longshort(self, long_exposures, short_exposures, sector_dict=None, ax=None):
        """
        Plots sector exposures (long/short).
        See fincore.tearsheets.risk.plot_sector_exposures_longshort for full documentation.
        """
        return _plot_sector_exposures_longshort(long_exposures, short_exposures, sector_dict=sector_dict, ax=ax)

    def plot_sector_exposures_gross(self, gross_exposures, sector_dict=None, ax=None):
        """
        Plots gross sector exposures.
        See fincore.tearsheets.risk.plot_sector_exposures_gross for full documentation.
        """
        return _plot_sector_exposures_gross(gross_exposures, sector_dict=sector_dict, ax=ax)

    def plot_sector_exposures_net(self, net_exposures, sector_dict=None, ax=None):
        """
        Plots net sector exposures.
        See fincore.tearsheets.risk.plot_sector_exposures_net for full documentation.
        """
        return _plot_sector_exposures_net(net_exposures, sector_dict=sector_dict, ax=ax)

    def plot_cap_exposures_longshort(self, long_exposures, short_exposures, ax=None):
        """
        Plots cap exposures (long/short).
        See fincore.tearsheets.risk.plot_cap_exposures_longshort for full documentation.
        """
        return _plot_cap_exposures_longshort(long_exposures, short_exposures, ax=ax)

    def plot_cap_exposures_gross(self, gross_exposures, ax=None):
        """
        Plots gross cap exposures.
        See fincore.tearsheets.risk.plot_cap_exposures_gross for full documentation.
        """
        return _plot_cap_exposures_gross(gross_exposures, ax=ax)

    def plot_cap_exposures_net(self, net_exposures, ax=None):
        """
        Plots net cap exposures.
        See fincore.tearsheets.risk.plot_cap_exposures_net for full documentation.
        """
        return _plot_cap_exposures_net(net_exposures, ax=ax)

    def plot_volume_exposures_longshort(self, longed_threshold, shorted_threshold, percentile, ax=None):
        """
        Plots volume exposures (long/short).
        See fincore.tearsheets.risk.plot_volume_exposures_longshort for full documentation.
        """
        return _plot_volume_exposures_longshort(longed_threshold, shorted_threshold, percentile, ax=ax)

    def plot_volume_exposures_gross(self, grossed_threshold, percentile, ax=None):
        """
        Plots gross volume exposures.
        See fincore.tearsheets.risk.plot_volume_exposures_gross for full documentation.
        """
        return _plot_volume_exposures_gross(grossed_threshold, percentile, ax=ax)

    @customize

    # # Tear sheet creation methods
    # =================
    def create_full_tear_sheet(
        self,
        returns,
        positions=None,
        transactions=None,
        market_data=None,
        benchmark_rets=None,
        slippage=None,
        live_start_date=None,
        sector_mappings=None,
        bayesian=False,
        round_trips=False,
        estimate_intraday="infer",
        hide_positions=False,
        cone_std=(1.0, 1.5, 2.0),
        bootstrap=False,
        unadjusted_returns=None,
        style_factor_panel=None,
        sectors=None,
        caps=None,
        shares_held=None,
        volumes=None,
        percentile=None,
        turnover_denom="AGB",
        set_context=True,
        factor_returns=None,
        factor_loadings=None,
        pos_in_dollars=True,
        header_rows=None,
        factor_partitions=FACTOR_PARTITIONS,
    ):
        """
        Generate full tear sheet.
        See fincore.tearsheets.sheets.create_full_tear_sheet for full documentation.
        """
        return _create_full_tear_sheet(
            self,
            returns,
            positions=positions,
            transactions=transactions,
            market_data=market_data,
            benchmark_rets=benchmark_rets,
            slippage=slippage,
            live_start_date=live_start_date,
            sector_mappings=sector_mappings,
            bayesian=bayesian,
            round_trips=round_trips,
            estimate_intraday=estimate_intraday,
            hide_positions=hide_positions,
            cone_std=cone_std,
            bootstrap=bootstrap,
            unadjusted_returns=unadjusted_returns,
            style_factor_panel=style_factor_panel,
            sectors=sectors,
            caps=caps,
            shares_held=shares_held,
            volumes=volumes,
            percentile=percentile,
            turnover_denom=turnover_denom,
            set_context=set_context,
            factor_returns=factor_returns,
            factor_loadings=factor_loadings,
            pos_in_dollars=pos_in_dollars,
            header_rows=header_rows,
            factor_partitions=factor_partitions,
        )

    @customize
    def create_simple_tear_sheet(
        self,
        returns,
        positions=None,
        transactions=None,
        benchmark_rets=None,
        slippage=None,
        estimate_intraday="infer",
        live_start_date=None,
        turnover_denom="AGB",
        header_rows=None,
    ):
        """
        Generate simple tear sheet.
        See fincore.tearsheets.sheets.create_simple_tear_sheet for full documentation.
        """
        return _create_simple_tear_sheet(
            self,
            returns,
            positions=positions,
            transactions=transactions,
            benchmark_rets=benchmark_rets,
            slippage=slippage,
            estimate_intraday=estimate_intraday,
            live_start_date=live_start_date,
            turnover_denom=turnover_denom,
            header_rows=header_rows,
        )

    @customize
    def create_returns_tear_sheet(
        self,
        returns,
        positions=None,
        transactions=None,
        live_start_date=None,
        cone_std=(1.0, 1.5, 2.0),
        benchmark_rets=None,
        bootstrap=False,
        turnover_denom="AGB",
        header_rows=None,
        run_flask_app=False,
    ):
        """
        Generate returns tear sheet.
        See fincore.tearsheets.sheets.create_returns_tear_sheet for full documentation.
        """
        return _create_returns_tear_sheet(
            self,
            returns,
            positions=positions,
            transactions=transactions,
            live_start_date=live_start_date,
            cone_std=cone_std,
            benchmark_rets=benchmark_rets,
            bootstrap=bootstrap,
            turnover_denom=turnover_denom,
            header_rows=header_rows,
            run_flask_app=run_flask_app,
        )

    @customize
    def create_position_tear_sheet(
        self,
        returns,
        positions,
        show_and_plot_top_pos=2,
        hide_positions=False,
        run_flask_app=False,
        sector_mappings=None,
        transactions=None,
        estimate_intraday="infer",
    ):
        """
        Generate position tear sheet.
        See fincore.tearsheets.sheets.create_position_tear_sheet for full documentation.
        """
        return _create_position_tear_sheet(
            self,
            returns,
            positions,
            show_and_plot_top_pos=show_and_plot_top_pos,
            hide_positions=hide_positions,
            run_flask_app=run_flask_app,
            sector_mappings=sector_mappings,
            transactions=transactions,
            estimate_intraday=estimate_intraday,
        )

    @customize
    def create_txn_tear_sheet(
        self, returns, positions, transactions, unadjusted_returns=None, estimate_intraday="infer", run_flask_app=False
    ):
        """
        Generate transaction tear sheet.
        See fincore.tearsheets.sheets.create_txn_tear_sheet for full documentation.
        """
        return _create_txn_tear_sheet(
            self,
            returns,
            positions,
            transactions,
            unadjusted_returns=unadjusted_returns,
            estimate_intraday=estimate_intraday,
            run_flask_app=run_flask_app,
        )

    @customize
    def create_round_trip_tear_sheet(
        self, returns, positions, transactions, sector_mappings=None, estimate_intraday="infer", run_flask_app=False
    ):
        """
        Generate round trip tear sheet.
        See fincore.tearsheets.sheets.create_round_trip_tear_sheet for full documentation.
        """
        return _create_round_trip_tear_sheet(
            self,
            returns,
            positions,
            transactions,
            sector_mappings=sector_mappings,
            estimate_intraday=estimate_intraday,
            run_flask_app=run_flask_app,
        )

    @customize
    def create_interesting_times_tear_sheet(self, returns, benchmark_rets=None, legend_loc="best", run_flask_app=False):
        """
        Generate interesting times tear sheet.
        See fincore.tearsheets.sheets.create_interesting_times_tear_sheet for full documentation.
        """
        return _create_interesting_times_tear_sheet(
            self, returns, benchmark_rets=benchmark_rets, legend_loc=legend_loc, run_flask_app=run_flask_app
        )

    @customize
    def create_capacity_tear_sheet(
        self,
        returns,
        positions,
        transactions,
        market_data,
        liquidation_daily_vol_limit=0.2,
        trade_daily_vol_limit=0.05,
        last_n_days=APPROX_BDAYS_PER_MONTH * 6,
        days_to_liquidate_limit=1,
        estimate_intraday="infer",
        run_flask_app=False,
    ):
        """
        Generate capacity tear sheet.
        See fincore.tearsheets.sheets.create_capacity_tear_sheet for full documentation.
        """
        return _create_capacity_tear_sheet(
            self,
            returns,
            positions,
            transactions,
            market_data,
            liquidation_daily_vol_limit=liquidation_daily_vol_limit,
            trade_daily_vol_limit=trade_daily_vol_limit,
            last_n_days=last_n_days,
            days_to_liquidate_limit=days_to_liquidate_limit,
            estimate_intraday=estimate_intraday,
            run_flask_app=run_flask_app,
        )

    @customize
    def create_bayesian_tear_sheet(
        self,
        returns,
        benchmark_rets=None,
        live_start_date=None,
        samples=2000,
        run_flask_app=False,
        stoch_vol=False,
        progressbar=True,
    ):
        """
        Generate Bayesian tear sheet.
        See fincore.tearsheets.sheets.create_bayesian_tear_sheet for full documentation.
        """
        return _create_bayesian_tear_sheet(
            self,
            returns,
            benchmark_rets=benchmark_rets,
            live_start_date=live_start_date,
            samples=samples,
            run_flask_app=run_flask_app,
            stoch_vol=stoch_vol,
            progressbar=progressbar,
        )

    @customize
    def create_risk_tear_sheet(
        self,
        positions,
        style_factor_panel=None,
        sectors=None,
        caps=None,
        shares_held=None,
        volumes=None,
        percentile=None,
        returns=None,
        transactions=None,
        estimate_intraday="infer",
        run_flask_app=False,
    ):
        """
        Generate risk tear sheet.
        See fincore.tearsheets.sheets.create_risk_tear_sheet for full documentation.
        """
        return _create_risk_tear_sheet(
            self,
            positions,
            style_factor_panel=style_factor_panel,
            sectors=sectors,
            caps=caps,
            shares_held=shares_held,
            volumes=volumes,
            percentile=percentile,
            returns=returns,
            transactions=transactions,
            estimate_intraday=estimate_intraday,
            run_flask_app=run_flask_app,
        )

    @customize
    def create_perf_attrib_tear_sheet(
        self,
        returns,
        positions,
        factor_returns,
        factor_loadings,
        transactions=None,
        pos_in_dollars=True,
        run_flask_app=False,
        factor_partitions=FACTOR_PARTITIONS,
    ):
        """
        Generate performance attribution tear sheet.
        See fincore.tearsheets.sheets.create_perf_attrib_tear_sheet for full documentation.
        """
        return _create_perf_attrib_tear_sheet(
            self,
            returns,
            positions,
            factor_returns,
            factor_loadings,
            transactions=transactions,
            pos_in_dollars=pos_in_dollars,
            run_flask_app=run_flask_app,
            factor_partitions=factor_partitions,
        )

    def plotting_context(self, context="notebook", font_scale=1.5, rc=None):
        """
        Create pyfolio default plotting style context.
        See fincore.tearsheets.utils.plotting_context for full documentation.
        """
        return _plotting_context(context=context, font_scale=font_scale, rc=rc)

    def axes_style(self, style="darkgrid", rc=None):
        """
        Create pyfolio default axes style context.
        See fincore.tearsheets.utils.axes_style for full documentation.
        """
        return _axes_style(style=style, rc=rc)

    def plot_monthly_returns_heatmap(self, returns, ax=None, **kwargs):
        """
        Plots a heatmap of returns by month.
        See fincore.tearsheets.returns.plot_monthly_returns_heatmap for full documentation.
        """
        return _plot_monthly_returns_heatmap(self, returns, ax=ax, **kwargs)

    def plot_annual_returns(self, returns, ax=None, **kwargs):
        """
        Plots a bar graph of returns by year.
        See fincore.tearsheets.returns.plot_annual_returns for full documentation.
        """
        return _plot_annual_returns(self, returns, ax=ax, **kwargs)

    def plot_monthly_returns_dist(self, returns, ax=None, **kwargs):
        """
        Plots a distribution of monthly returns.
        See fincore.tearsheets.returns.plot_monthly_returns_dist for full documentation.
        """
        return _plot_monthly_returns_dist(self, returns, ax=ax, **kwargs)

    # # Plotting methods
    # ======
    def plot_holdings(self, returns, positions, legend_loc="best", ax=None, **kwargs):
        """
        Plots total holdings.
        See fincore.tearsheets.positions.plot_holdings for full documentation.
        """
        return _plot_holdings(self, returns, positions, legend_loc=legend_loc, ax=ax, **kwargs)

    def plot_long_short_holdings(self, returns, positions, legend_loc="upper left", ax=None, **_kwargs):
        """
        Plots long and short holdings.
        See fincore.tearsheets.positions.plot_long_short_holdings for full documentation.
        """
        return _plot_long_short_holdings(returns, positions, legend_loc=legend_loc, ax=ax, **_kwargs)

    def plot_drawdown_periods(self, returns, top=10, ax=None, **kwargs):
        """
        Plots cumulative returns highlighting top drawdown periods.
        See fincore.tearsheets.returns.plot_drawdown_periods for full documentation.
        """
        return _plot_drawdown_periods(self, returns, top=top, ax=ax, **kwargs)

    def plot_drawdown_underwater(self, returns, ax=None, **kwargs):
        """
        Plots underwater drawdown chart.
        See fincore.tearsheets.returns.plot_drawdown_underwater for full documentation.
        """
        return _plot_drawdown_underwater(self, returns, ax=ax, **kwargs)

    def plot_perf_stats(self, returns, factor_returns, ax=None):
        """
        Create a box plot of performance metrics.
        See fincore.tearsheets.returns.plot_perf_stats for full documentation.
        """
        return _plot_perf_stats(self, returns, factor_returns, ax=ax)

    def show_perf_stats(
        self,
        returns,
        factor_returns=None,
        positions=None,
        transactions=None,
        turnover_denom="AGB",
        live_start_date=None,
        bootstrap=False,
        header_rows=None,
        run_flask_app=False,
    ):
        """
        Prints some performance metrics of the strategy.
        See fincore.tearsheets.returns.show_perf_stats for full documentation.
        """
        return _show_perf_stats(
            self,
            returns,
            factor_returns=factor_returns,
            positions=positions,
            transactions=transactions,
            turnover_denom=turnover_denom,
            live_start_date=live_start_date,
            bootstrap=bootstrap,
            header_rows=header_rows,
            run_flask_app=run_flask_app,
        )

    def plot_returns(self, returns, live_start_date=None, ax=None):
        """
        Plots raw returns over time.
        See fincore.tearsheets.returns.plot_returns for full documentation.
        """
        return _plot_returns(returns, live_start_date=live_start_date, ax=ax)

    def plot_rolling_returns(
        self,
        returns,
        factor_returns=None,
        live_start_date=None,
        logy=False,
        cone_std=None,
        legend_loc="best",
        volatility_match=False,
        cone_function=None,
        ax=None,
        **kwargs,
    ):
        """
        Plots cumulative rolling returns.
        See fincore.tearsheets.returns.plot_rolling_returns for full documentation.
        """
        if cone_function is None:
            cone_function = Empyrical.forecast_cone_bootstrap
        return _plot_rolling_returns(
            self,
            returns,
            factor_returns=factor_returns,
            live_start_date=live_start_date,
            logy=logy,
            cone_std=cone_std,
            legend_loc=legend_loc,
            volatility_match=volatility_match,
            cone_function=cone_function,
            ax=ax,
            **kwargs,
        )

    def plot_rolling_beta(self, returns, factor_returns, legend_loc="best", ax=None, **kwargs):
        """
        Plots rolling beta.
        See fincore.tearsheets.returns.plot_rolling_beta for full documentation.
        """
        return _plot_rolling_beta(self, returns, factor_returns, legend_loc=legend_loc, ax=ax, **kwargs)

    def plot_rolling_volatility(
        self, returns, factor_returns=None, rolling_window=None, legend_loc="best", ax=None, **kwargs
    ):
        """
        Plots rolling volatility.
        See fincore.tearsheets.returns.plot_rolling_volatility for full documentation.
        """
        return _plot_rolling_volatility(
            self,
            returns,
            factor_returns=factor_returns,
            rolling_window=rolling_window,
            legend_loc=legend_loc,
            ax=ax,
            **kwargs,
        )

    def plot_rolling_sharpe(
        self, returns, factor_returns=None, rolling_window=None, legend_loc="best", ax=None, **kwargs
    ):
        """
        Plots rolling Sharpe ratio.
        See fincore.tearsheets.returns.plot_rolling_sharpe for full documentation.
        """
        return _plot_rolling_sharpe(
            self,
            returns,
            factor_returns=factor_returns,
            rolling_window=rolling_window,
            legend_loc=legend_loc,
            ax=ax,
            **kwargs,
        )

    def plot_gross_leverage(self, _returns, positions, ax=None, **kwargs):
        """
        Plots gross leverage.
        See fincore.tearsheets.positions.plot_gross_leverage for full documentation.
        """
        return _plot_gross_leverage(self, _returns, positions, ax=ax, **kwargs)

    def plot_exposures(self, returns, positions, ax=None, **_kwargs):
        """
        Plots long and short exposure.
        See fincore.tearsheets.positions.plot_exposures for full documentation.
        """
        return _plot_exposures(returns, positions, ax=ax, **_kwargs)

    def show_and_plot_top_positions(
        self,
        returns,
        positions_alloc,
        show_and_plot=2,
        hide_positions=False,
        legend_loc="real_best",
        ax=None,
        run_flask_app=False,
        **kwargs,
    ):
        """
        Prints and/or plots the top 10 held positions.
        See fincore.tearsheets.positions.show_and_plot_top_positions for full documentation.
        """
        return _show_and_plot_top_positions(
            self,
            returns,
            positions_alloc,
            show_and_plot=show_and_plot,
            hide_positions=hide_positions,
            legend_loc=legend_loc,
            ax=ax,
            run_flask_app=run_flask_app,
            **kwargs,
        )

    def plot_max_median_position_concentration(self, positions, ax=None, **_kwargs):
        """
        Plots position concentration.
        See fincore.tearsheets.positions.plot_max_median_position_concentration for full documentation.
        """
        return _plot_max_median_position_concentration(self, positions, ax=ax, **_kwargs)

    def plot_sector_allocations(self, _returns, sector_alloc, ax=None, **kwargs):
        """
        Plots sector allocations.
        See fincore.tearsheets.positions.plot_sector_allocations for full documentation.
        """
        return _plot_sector_allocations(_returns, sector_alloc, ax=ax, **kwargs)

    def plot_return_quantiles(self, returns, live_start_date=None, ax=None, **kwargs):
        """
        Plots return quantiles.
        See fincore.tearsheets.returns.plot_return_quantiles for full documentation.
        """
        return _plot_return_quantiles(self, returns, live_start_date=live_start_date, ax=ax, **kwargs)

    def plot_turnover(self, returns, transactions, positions, legend_loc="best", ax=None, **kwargs):
        """
        Plots turnover.
        See fincore.tearsheets.transactions.plot_turnover for full documentation.
        """
        return _plot_turnover(self, returns, transactions, positions, legend_loc=legend_loc, ax=ax, **kwargs)

    def plot_slippage_sweep(
        self, returns, positions, transactions, slippage_params=(3, 8, 10, 12, 15, 20, 50), ax=None, **_kwargs
    ):
        """
        Plots slippage sweep.
        See fincore.tearsheets.transactions.plot_slippage_sweep for full documentation.
        """
        return _plot_slippage_sweep(
            self, returns, positions, transactions, slippage_params=slippage_params, ax=ax, **_kwargs
        )

    def plot_slippage_sensitivity(self, returns, positions, transactions, ax=None, **_kwargs):
        """
        Plots slippage sensitivity.
        See fincore.tearsheets.transactions.plot_slippage_sensitivity for full documentation.
        """
        return _plot_slippage_sensitivity(self, returns, positions, transactions, ax=ax, **_kwargs)

    def plot_capacity_sweep(
        self,
        returns,
        transactions,
        market_data,
        bt_starting_capital,
        min_pv=CAPACITY_SWEEP_MIN_PV,
        max_pv=CAPACITY_SWEEP_MAX_PV,
        step_size=CAPACITY_SWEEP_STEP,
        ax=None,
    ):
        """
        Plots capacity sweep.
        See fincore.tearsheets.capacity.plot_capacity_sweep for full documentation.
        """
        return _plot_capacity_sweep(
            self,
            returns,
            transactions,
            market_data,
            bt_starting_capital,
            min_pv=min_pv,
            max_pv=max_pv,
            step_size=step_size,
            ax=ax,
        )

    def plot_daily_turnover_hist(self, transactions, positions, ax=None, **kwargs):
        """
        Plots daily turnover histogram.
        See fincore.tearsheets.transactions.plot_daily_turnover_hist for full documentation.
        """
        return _plot_daily_turnover_hist(self, transactions, positions, ax=ax, **kwargs)

    def plot_daily_volume(self, returns, transactions, ax=None, **kwargs):
        """
        Plots daily trading volume.
        See fincore.tearsheets.transactions.plot_daily_volume for full documentation.
        """
        return _plot_daily_volume(self, returns, transactions, ax=ax, **kwargs)

    def plot_txn_time_hist(self, transactions, bin_minutes=5, tz="America/New_York", ax=None, **kwargs):
        """
        Plots transaction time histogram.
        See fincore.tearsheets.transactions.plot_txn_time_hist for full documentation.
        """
        return _plot_txn_time_hist(transactions, bin_minutes=bin_minutes, tz=tz, ax=ax, **kwargs)

    def show_worst_drawdown_periods(self, returns, top=5, run_flask_app=False):
        """
        Prints worst drawdown periods.
        See fincore.tearsheets.returns.show_worst_drawdown_periods for full documentation.
        """
        return _show_worst_drawdown_periods(self, returns, top=top, run_flask_app=run_flask_app)

    def plot_monthly_returns_timeseries(self, returns, ax=None, **_kwargs):
        """
        Plots monthly returns timeseries.
        See fincore.tearsheets.returns.plot_monthly_returns_timeseries for full documentation.
        """
        return _plot_monthly_returns_timeseries(self, returns, ax=ax, **_kwargs)

    def plot_round_trip_lifetimes(self, round_trips, disp_amount=16, lsize=18, ax=None):
        """
        Plots round trip lifetimes.
        See fincore.tearsheets.round_trips.plot_round_trip_lifetimes for full documentation.
        """
        return _plot_round_trip_lifetimes(round_trips, disp_amount=disp_amount, lsize=lsize, ax=ax)

    def show_profit_attribution(self, round_trips, run_flask_app=False):
        """
        Prints profit attribution.
        See fincore.tearsheets.round_trips.show_profit_attribution for full documentation.
        """
        return _show_profit_attribution(round_trips, run_flask_app=run_flask_app)

    def plot_prob_profit_trade(self, round_trips, ax=None):
        """
        Plots profit probability distribution.
        See fincore.tearsheets.round_trips.plot_prob_profit_trade for full documentation.
        """
        return _plot_prob_profit_trade(round_trips, ax=ax)

    def plot_cones(
        self,
        name,
        bounds,
        oos_returns,
        _num_samples=1000,
        ax=None,
        cone_std=(1.0, 1.5, 2.0),
        _random_seed=None,
        num_strikes=3,
    ):
        """
        Plots forecast cones.
        See fincore.tearsheets.capacity.plot_cones for full documentation.
        """
        return _plot_cones(
            self,
            name,
            bounds,
            oos_returns,
            _num_samples=_num_samples,
            ax=ax,
            cone_std=cone_std,
            _random_seed=_random_seed,
            num_strikes=num_strikes,
        )

    def print_round_trip_stats(self, round_trips, hide_pos=False, run_flask_app=False):
        """
        Prints round-trip statistics.
        See fincore.tearsheets.round_trips.print_round_trip_stats for full documentation.
        """
        return _print_round_trip_stats(self, round_trips, hide_pos=hide_pos, run_flask_app=run_flask_app)

    def show_perf_attrib_stats(
        self, returns, positions, factor_returns, factor_loadings, transactions=None, pos_in_dollars=True
    ):
        """
        Shows performance attribution statistics.
        See fincore.tearsheets.perf_attrib.show_perf_attrib_stats for full documentation.
        """
        return _show_perf_attrib_stats(
            self,
            returns,
            positions,
            factor_returns,
            factor_loadings,
            transactions=transactions,
            pos_in_dollars=pos_in_dollars,
        )

    def plot_perf_attrib_returns(self, perf_attrib_data, cost=None, ax=None):
        """
        Plots performance attribution returns.
        See fincore.tearsheets.perf_attrib.plot_perf_attrib_returns for full documentation.
        """
        return _plot_perf_attrib_returns(self, perf_attrib_data, cost=cost, ax=ax)

    def plot_alpha_returns(self, alpha_returns, ax=None):
        """
        Plots alpha returns histogram.
        See fincore.tearsheets.perf_attrib.plot_alpha_returns for full documentation.
        """
        return _plot_alpha_returns(alpha_returns, ax=ax)

    def plot_factor_contribution_to_perf(
        self, perf_attrib_data, ax=None, title="Cumulative common returns attribution"
    ):
        """
        Plots factor contribution to performance.
        See fincore.tearsheets.perf_attrib.plot_factor_contribution_to_perf for full documentation.
        """
        return _plot_factor_contribution_to_perf(self, perf_attrib_data, ax=ax, title=title)

    def plot_risk_exposures(self, exposures, ax=None, title="Daily risk factor exposures"):
        """
        Plots risk exposures.
        See fincore.tearsheets.perf_attrib.plot_risk_exposures for full documentation.
        """
        return _plot_risk_exposures(exposures, ax=ax, title=title)
