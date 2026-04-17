"""Function registry for auto-generating Empyrical class methods.

This module defines the mapping from Empyrical method names to their
underlying metric functions.  The registry is consumed by empyrical.py
to auto-generate class methods, eliminating ~1000 lines of hand-written
boilerplate delegation code.

Each entry is a tuple of:
    (method_name, module_alias, function_name, method_type)

Method types:
    'static'  — exposed as staticmethod (utility helpers)
    'class'   — exposed as classmethod-like static forwarding
    'dual_r'  — _dual_method that auto-fills ``returns`` from instance
    'dual_rf' — _dual_method that auto-fills ``returns`` and ``factor_returns``
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Static methods  (module_alias, func_name)
# ---------------------------------------------------------------------------
STATIC_METHODS = {
    "_ensure_datetime_index_series": ("_basic", "ensure_datetime_index_series"),
    "_flatten": ("_basic", "flatten"),
    "_adjust_returns": ("_basic", "adjust_returns"),
    "annualization_factor": ("_basic", "annualization_factor"),
    "_to_pandas": ("_basic", "to_pandas"),
    "_aligned_series": ("_basic", "aligned_series"),
}

# ---------------------------------------------------------------------------
# Class methods — simple forwarding to module function.
# Each entry: (method_name, module_alias, func_name).
# ---------------------------------------------------------------------------
CLASSMETHOD_REGISTRY = {
    # Returns group
    "simple_returns": ("_returns", "simple_returns"),
    "cum_returns": ("_returns", "cum_returns"),
    "cum_returns_final": ("_returns", "cum_returns_final"),
    "aggregate_returns": ("_returns", "aggregate_returns"),
    "normalize": ("_returns", "normalize"),
    # drawdown
    "max_drawdown": ("_drawdown", "max_drawdown"),
    "_get_all_drawdowns": ("_drawdown", "get_all_drawdowns"),
    "_get_all_drawdowns_detailed": ("_drawdown", "get_all_drawdowns_detailed"),
    "get_max_drawdown": ("_drawdown", "get_max_drawdown"),
    "get_max_drawdown_underwater": ("_drawdown", "get_max_drawdown_underwater"),
    "get_top_drawdowns": ("_drawdown", "get_top_drawdowns"),
    "gen_drawdown_table": ("_drawdown", "gen_drawdown_table"),
    # risk
    "annual_volatility": ("_risk", "annual_volatility"),
    "downside_risk": ("_risk", "downside_risk"),
    "value_at_risk": ("_risk", "value_at_risk"),
    "conditional_value_at_risk": ("_risk", "conditional_value_at_risk"),
    "tail_ratio": ("_risk", "tail_ratio"),
    "tracking_error": ("_risk", "tracking_error"),
    "trading_value_at_risk": ("_risk", "trading_value_at_risk"),
    # ratios
    "sharpe_ratio": ("_ratios", "sharpe_ratio"),
    "sortino_ratio": ("_ratios", "sortino_ratio"),
    "excess_sharpe": ("_ratios", "excess_sharpe"),
    "calmar_ratio": ("_ratios", "calmar_ratio"),
    "omega_ratio": ("_ratios", "omega_ratio"),
    "information_ratio": ("_ratios", "information_ratio"),
    "stability_of_timeseries": ("_ratios", "stability_of_timeseries"),
    "capture": ("_ratios", "capture"),
    "up_capture": ("_ratios", "up_capture"),
    "down_capture": ("_ratios", "down_capture"),
    "up_down_capture": ("_ratios", "up_down_capture"),
    "adjusted_sharpe_ratio": ("_ratios", "adjusted_sharpe_ratio"),
    "conditional_sharpe_ratio": ("_ratios", "conditional_sharpe_ratio"),
    # alpha_beta
    "alpha": ("_alpha_beta", "alpha"),
    "alpha_aligned": ("_alpha_beta", "alpha_aligned"),
    "beta": ("_alpha_beta", "beta"),
    "beta_aligned": ("_alpha_beta", "beta_aligned"),
    "alpha_beta": ("_alpha_beta", "alpha_beta"),
    "alpha_beta_aligned": ("_alpha_beta", "alpha_beta_aligned"),
    "up_alpha_beta": ("_alpha_beta", "up_alpha_beta"),
    "down_alpha_beta": ("_alpha_beta", "down_alpha_beta"),
    "annual_alpha": ("_alpha_beta", "annual_alpha"),
    "annual_beta": ("_alpha_beta", "annual_beta"),
    "alpha_percentile_rank": ("_alpha_beta", "alpha_percentile_rank"),
    # stats
    "skewness": ("_stats", "skewness"),
    "kurtosis": ("_stats", "kurtosis"),
    "hurst_exponent": ("_stats", "hurst_exponent"),
    "stutzer_index": ("_stats", "stutzer_index"),
    "stock_market_correlation": ("_stats", "stock_market_correlation"),
    "bond_market_correlation": ("_stats", "bond_market_correlation"),
    "var_cov_var_normal": ("_stats", "var_cov_var_normal"),
    # consecutive
    "max_consecutive_up_days": ("_consecutive", "max_consecutive_up_days"),
    "max_consecutive_down_days": ("_consecutive", "max_consecutive_down_days"),
    "max_consecutive_gain": ("_consecutive", "max_consecutive_gain"),
    "max_consecutive_loss": ("_consecutive", "max_consecutive_loss"),
    "max_single_day_gain": ("_consecutive", "max_single_day_gain"),
    "max_single_day_loss": ("_consecutive", "max_single_day_loss"),
    # timing
    "treynor_mazuy_timing": ("_timing", "treynor_mazuy_timing"),
    "henriksson_merton_timing": ("_timing", "henriksson_merton_timing"),
    "market_timing_return": ("_timing", "market_timing_return"),
    "cornell_timing": ("_timing", "cornell_timing"),
    # yearly
    "annual_return": ("_yearly", "annual_return"),
    "annual_return_by_year": ("_yearly", "annual_return_by_year"),
    "sharpe_ratio_by_year": ("_yearly", "sharpe_ratio_by_year"),
    "max_drawdown_by_year": ("_yearly", "max_drawdown_by_year"),
    # rolling
    "rolling_volatility": ("_rolling", "rolling_volatility"),
    "rolling_sharpe": ("_rolling", "rolling_sharpe"),
    "rolling_beta": ("_rolling", "rolling_beta"),
    "rolling_regression": ("_rolling", "rolling_regression"),
    # positions
    "get_percent_alloc": ("_positions", "get_percent_alloc"),
    "get_top_long_short_abs": ("_positions", "get_top_long_short_abs"),
    "get_long_short_pos": ("_positions", "get_long_short_pos"),
    "gross_lev": ("_positions", "gross_lev"),
    "get_max_median_position_concentration": ("_positions", "get_max_median_position_concentration"),
    "extract_pos": ("_positions", "extract_pos"),
    "get_sector_exposures": ("_positions", "get_sector_exposures"),
    "compute_style_factor_exposures": ("_positions", "compute_style_factor_exposures"),
    "compute_sector_exposures": ("_positions", "compute_sector_exposures"),
    "compute_cap_exposures": ("_positions", "compute_cap_exposures"),
    "compute_volume_exposures": ("_positions", "compute_volume_exposures"),
    "stack_positions": ("_positions", "stack_positions"),
    # transactions
    "get_txn_vol": ("_transactions", "get_txn_vol"),
    "get_turnover": ("_transactions", "get_turnover"),
    "make_transaction_frame": ("_transactions", "make_transaction_frame"),
    "daily_txns_with_bar_data": ("_transactions", "daily_txns_with_bar_data"),
    "days_to_liquidate_positions": ("_transactions", "days_to_liquidate_positions"),
    "get_max_days_to_liquidate_by_ticker": ("_transactions", "get_max_days_to_liquidate_by_ticker"),
    "get_low_liquidity_transactions": ("_transactions", "get_low_liquidity_transactions"),
    "apply_slippage_penalty": ("_transactions", "apply_slippage_penalty"),
    "map_transaction": ("_transactions", "map_transaction"),
    "adjust_returns_for_slippage": ("_transactions", "adjust_returns_for_slippage"),
    # round_trips
    "extract_round_trips": ("_round_trips", "extract_round_trips"),
    "gen_round_trip_stats": ("_round_trips", "gen_round_trip_stats"),
    "agg_all_long_short": ("_round_trips", "agg_all_long_short"),
    "add_closing_transactions": ("_round_trips", "add_closing_transactions"),
    "apply_sector_mappings_to_round_trips": ("_round_trips", "apply_sector_mappings_to_round_trips"),
    # perf_attrib
    "compute_exposures": ("_perf_attrib", "compute_exposures"),
    "create_perf_attrib_stats": ("_perf_attrib", "create_perf_attrib_stats"),
    "_cumulative_returns_less_costs": ("_perf_attrib", "cumulative_returns_less_costs"),
    # perf_stats
    "perf_stats": ("_perf_stats", "perf_stats"),
    "calc_bootstrap": ("_perf_stats", "calc_bootstrap"),
    "perf_stats_bootstrap": ("_perf_stats", "perf_stats_bootstrap"),
    "calc_distribution_stats": ("_perf_stats", "calc_distribution_stats"),
    # bayesian
    "model_returns_t_alpha_beta": ("_bayesian", "model_returns_t_alpha_beta"),
    "model_returns_normal": ("_bayesian", "model_returns_normal"),
    "model_returns_t": ("_bayesian", "model_returns_t"),
    "model_best": ("_bayesian", "model_best"),
    "model_stoch_vol": ("_bayesian", "model_stoch_vol"),
    "compute_bayes_cone": ("_bayesian", "compute_bayes_cone"),
    "compute_consistency_score": ("_bayesian", "compute_consistency_score"),
    "run_model": ("_bayesian", "run_model"),
    "simulate_paths": ("_bayesian", "simulate_paths"),
    "summarize_paths": ("_bayesian", "summarize_paths"),
    "forecast_cone_bootstrap": ("_bayesian", "forecast_cone_bootstrap"),
}

# ---------------------------------------------------------------------------
# Dual methods — auto-fill ``returns`` from instance state.
# Each entry: (method_name, module_alias, func_name).
# ---------------------------------------------------------------------------
DUAL_RETURNS_REGISTRY = {
    "get_max_drawdown_period": ("_drawdown", "get_max_drawdown_period"),
    "max_drawdown_days": ("_drawdown", "max_drawdown_days"),
    "second_max_drawdown": ("_drawdown", "second_max_drawdown"),
    "third_max_drawdown": ("_drawdown", "third_max_drawdown"),
    "second_max_drawdown_days": ("_drawdown", "second_max_drawdown_days"),
    "second_max_drawdown_recovery_days": ("_drawdown", "second_max_drawdown_recovery_days"),
    "third_max_drawdown_days": ("_drawdown", "third_max_drawdown_days"),
    "third_max_drawdown_recovery_days": ("_drawdown", "third_max_drawdown_recovery_days"),
    "max_drawdown_weeks": ("_drawdown", "max_drawdown_weeks"),
    "max_drawdown_months": ("_drawdown", "max_drawdown_months"),
    "max_drawdown_recovery_days": ("_drawdown", "max_drawdown_recovery_days"),
    "max_drawdown_recovery_weeks": ("_drawdown", "max_drawdown_recovery_weeks"),
    "max_drawdown_recovery_months": ("_drawdown", "max_drawdown_recovery_months"),
    "serial_correlation": ("_stats", "serial_correlation"),
    "win_rate": ("_stats", "win_rate"),
    "loss_rate": ("_stats", "loss_rate"),
    "max_consecutive_up_weeks": ("_consecutive", "max_consecutive_up_weeks"),
    "max_consecutive_down_weeks": ("_consecutive", "max_consecutive_down_weeks"),
    "max_consecutive_up_months": ("_consecutive", "max_consecutive_up_months"),
    "max_consecutive_down_months": ("_consecutive", "max_consecutive_down_months"),
    "max_single_day_gain_date": ("_consecutive", "max_single_day_gain_date"),
    "max_single_day_loss_date": ("_consecutive", "max_single_day_loss_date"),
    "max_consecutive_up_start_date": ("_consecutive", "max_consecutive_up_start_date"),
    "max_consecutive_up_end_date": ("_consecutive", "max_consecutive_up_end_date"),
    "max_consecutive_down_start_date": ("_consecutive", "max_consecutive_down_start_date"),
    "max_consecutive_down_end_date": ("_consecutive", "max_consecutive_down_end_date"),
    "extract_interesting_date_ranges": ("_timing", "extract_interesting_date_ranges"),
    "common_sense_ratio": ("_ratios", "common_sense_ratio"),
    "gpd_risk_estimates": ("_risk", "gpd_risk_estimates"),
    "gpd_risk_estimates_aligned": ("_risk", "gpd_risk_estimates_aligned"),
    "var_excess_return": ("_risk", "var_excess_return"),
    "annualized_cumulative_return": ("_yearly", "annual_return"),
    "roll_sharpe_ratio": ("_rolling", "roll_sharpe_ratio"),
    "roll_max_drawdown": ("_rolling", "roll_max_drawdown"),
    "sterling_ratio": ("_ratios", "sterling_ratio"),
    "burke_ratio": ("_ratios", "burke_ratio"),
    "kappa_three_ratio": ("_ratios", "kappa_three_ratio"),
    "deflated_sharpe_ratio": ("_ratios", "deflated_sharpe_ratio"),
    "annual_volatility_by_year": ("_yearly", "annual_volatility_by_year"),
    "mar_ratio": ("_ratios", "mar_ratio"),
    "r_cubed_turtle": ("_stats", "r_cubed_turtle"),
}

# ---------------------------------------------------------------------------
# Dual methods — auto-fill ``returns`` AND ``factor_returns`` from instance.
# Each entry: (method_name, module_alias, func_name).
# ---------------------------------------------------------------------------
DUAL_RETURNS_FACTOR_REGISTRY = {
    "futures_market_correlation": ("_stats", "futures_market_correlation"),
    "r_cubed": ("_stats", "r_cubed"),
    "tracking_difference": ("_stats", "tracking_difference"),
    "beta_fragility_heuristic": ("_risk", "beta_fragility_heuristic"),
    "beta_fragility_heuristic_aligned": ("_risk", "beta_fragility_heuristic_aligned"),
    "treynor_ratio": ("_ratios", "treynor_ratio"),
    "m_squared": ("_ratios", "m_squared"),
    "residual_risk": ("_risk", "residual_risk"),
    "roll_alpha": ("_rolling", "roll_alpha"),
    "roll_beta": ("_rolling", "roll_beta"),
    "roll_alpha_beta": ("_rolling", "roll_alpha_beta"),
    "roll_up_capture": ("_rolling", "roll_up_capture"),
    "roll_down_capture": ("_rolling", "roll_down_capture"),
    "roll_up_down_capture": ("_rolling", "roll_up_down_capture"),
    "annual_active_return": ("_yearly", "annual_active_return"),
    "annual_active_return_by_year": ("_yearly", "annual_active_return_by_year"),
    "information_ratio_by_year": ("_yearly", "information_ratio_by_year"),
    "relative_win_rate": ("_stats", "relative_win_rate"),
    "capm_r_squared": ("_stats", "capm_r_squared"),
    "up_capture_return": ("_ratios", "up_capture_return"),
    "down_capture_return": ("_ratios", "down_capture_return"),
}

# ---------------------------------------------------------------------------
# Module alias → fully qualified module path
# ---------------------------------------------------------------------------
MODULE_PATHS = {
    "_basic": "fincore.metrics.basic",
    "_returns": "fincore.metrics.returns",
    "_drawdown": "fincore.metrics.drawdown",
    "_risk": "fincore.metrics.risk",
    "_ratios": "fincore.metrics.ratios",
    "_alpha_beta": "fincore.metrics.alpha_beta",
    "_stats": "fincore.metrics.stats",
    "_consecutive": "fincore.metrics.consecutive",
    "_rolling": "fincore.metrics.rolling",
    "_bayesian": "fincore.metrics.bayesian",
    "_positions": "fincore.metrics.positions",
    "_transactions": "fincore.metrics.transactions",
    "_round_trips": "fincore.metrics.round_trips",
    "_perf_attrib": "fincore.metrics.perf_attrib",
    "_perf_stats": "fincore.metrics.perf_stats",
    "_timing": "fincore.metrics.timing",
    "_yearly": "fincore.metrics.yearly",
}
