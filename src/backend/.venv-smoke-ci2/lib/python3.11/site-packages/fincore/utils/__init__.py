#
# Copyright 2018 Quantopian, Inc.
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

"""Utility module.

This package contains helper functions refactored from the original
``empyrical/utils.py``.
"""

from .common_utils import (
    SETTINGS,
    _1_bday_ago,
    analyze_dataframe_differences,
    analyze_series_differences,
    check_intraday,
    clip_returns_to_benchmark,
    configure_legend,
    customize,
    default_returns_func,
    detect_intraday,
    estimate_intraday,
    extract_rets_pos_txn_from_zipline,
    format_asset,
    get_month_end_freq,
    get_symbol_rets,
    get_utc_timestamp,
    make_timezone_aware,
    one_dec_places,
    percentage,
    print_table,
    register_return_func,
    sample_colormap,
    standardize_data,
    to_series,
    to_utc,
    two_dec_places,
    vectorize,
)
from .data_utils import down, roll, rolling_window, up
from .date_utils import timer
from .deprecate import deprecated
from .math_utils import (
    nanargmax,
    nanargmin,
    nanmax,
    nanmean,
    nanmin,
    nanstd,
    nansum,
)

__all__ = [
    "SETTINGS",
    "_1_bday_ago",
    "analyze_dataframe_differences",
    "analyze_series_differences",
    "check_intraday",
    "clip_returns_to_benchmark",
    "configure_legend",
    # common_utils
    "customize",
    "default_returns_func",
    # deprecate
    "deprecated",
    "detect_intraday",
    "down",
    "estimate_intraday",
    "extract_rets_pos_txn_from_zipline",
    "format_asset",
    "get_month_end_freq",
    "get_symbol_rets",
    "get_utc_timestamp",
    "make_timezone_aware",
    "nanargmax",
    "nanargmin",
    "nanmax",
    # math_utils
    "nanmean",
    "nanmin",
    "nanstd",
    "nansum",
    "one_dec_places",
    "percentage",
    "print_table",
    "register_return_func",
    "roll",
    # data_utils
    "rolling_window",
    "sample_colormap",
    "standardize_data",
    # date_utils
    "timer",
    "to_series",
    "to_utc",
    "two_dec_places",
    "up",
    "vectorize",
]
