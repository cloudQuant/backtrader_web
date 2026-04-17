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

"""Metrics package.

This package contains modules extracted from :class:`fincore.empyrical.Empyrical`.
It is lazily imported to keep `import fincore` fast.
"""

# ---------------------------------------------------------------------------
# Lazy sub-module loading — each ``*_module`` alias is resolved on first
# attribute access via ``__getattr__``.  This avoids importing all 17
# sub-modules (and their transitive dependencies) when
# ``import fincore.metrics`` is executed.
# ---------------------------------------------------------------------------
import importlib as _importlib

_MODULE_MAP = {
    "basic_module": "fincore.metrics.basic",
    "returns_module": "fincore.metrics.returns",
    "drawdown_module": "fincore.metrics.drawdown",
    "risk_module": "fincore.metrics.risk",
    "ratios_module": "fincore.metrics.ratios",
    "alpha_beta_module": "fincore.metrics.alpha_beta",
    "stats_module": "fincore.metrics.stats",
    "consecutive_module": "fincore.metrics.consecutive",
    "rolling_module": "fincore.metrics.rolling",
    "bayesian_module": "fincore.metrics.bayesian",
    "positions_module": "fincore.metrics.positions",
    "transactions_module": "fincore.metrics.transactions",
    "round_trips_module": "fincore.metrics.round_trips",
    "perf_attrib_module": "fincore.metrics.perf_attrib",
    "perf_stats_module": "fincore.metrics.perf_stats",
    "timing_module": "fincore.metrics.timing",
    "yearly_module": "fincore.metrics.yearly",
}


def __getattr__(name: str):
    if name in _MODULE_MAP:
        mod = _importlib.import_module(_MODULE_MAP[name])
        globals()[name] = mod
        return mod
    raise AttributeError(f"module 'fincore.metrics' has no attribute {name!r}")
