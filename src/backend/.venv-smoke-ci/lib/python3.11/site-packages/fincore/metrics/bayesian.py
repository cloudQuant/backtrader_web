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

"""Bayesian models and helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from fincore.metrics.returns import cum_returns

__all__ = [
    "compute_bayes_cone",
    "compute_consistency_score",
    "forecast_cone_bootstrap",
    "model_best",
    "model_returns_normal",
    "model_returns_t",
    "model_returns_t_alpha_beta",
    "model_stoch_vol",
    "run_model",
    "simulate_paths",
    "summarize_paths",
]


def model_returns_t_alpha_beta(
    data: pd.Series,
    bmark: pd.Series,
    samples: int = 2000,
    progressbar: bool = True,
) -> tuple[Any, Any]:
    """Run Bayesian alpha-beta model assuming returns are T-distributed.

    Parameters
    ----------
    data : pd.Series
        Daily returns of the strategy, noncumulative.
    bmark : pd.Series
        Daily noncumulative returns of the benchmark.
    samples : int, optional
        Number of posterior samples to draw.
    progressbar : bool, optional
        Show progress bar during sampling.

    Returns
    -------
    model : pymc.Model
        PyMC model containing all random variables.
    trace : pymc3.sampling.BaseTrace
        A trace object that contains samples for each parameter.
    """
    import pymc as pm

    if len(data) != len(bmark):
        data, bmark = data.align(bmark, join="inner")

    data_array = np.asarray(data)
    bmark_array = np.asarray(bmark)

    with pm.Model() as model:
        sigma = pm.HalfCauchy("sigma", beta=1)
        nu = pm.Exponential("nu_minus_two", 1 / 29.0) + 2.0

        alpha = pm.Normal("alpha", mu=0, sigma=0.1)
        beta = pm.Normal("beta", mu=0, sigma=1)

        mu = alpha + beta * bmark_array

        _returns = pm.StudentT("returns", nu=nu, mu=mu, sigma=sigma, observed=data_array)

        trace = pm.sample(samples, progressbar=progressbar, return_inferencedata=False)

    return model, trace


def model_returns_normal(
    data: pd.Series,
    samples: int = 500,
    progressbar: bool = True,
) -> tuple[Any, Any]:
    """Run Bayesian model assuming returns are normally distributed.

    Parameters
    ----------
    data : pd.Series
        Daily returns of the strategy, noncumulative.
    samples : int, optional
        Number of posterior samples to draw.
    progressbar : bool, optional
        Show progress bar during sampling.

    Returns
    -------
    model : pymc.Model
        PyMC model containing all random variables.
    trace : pymc3.sampling.BaseTrace
        A trace object that contains samples for each parameter.
    """
    import pymc as pm

    data_array = np.asarray(data)

    with pm.Model() as model:
        mu = pm.Normal("mean_returns", mu=0, sigma=0.01)
        sigma = pm.HalfCauchy("volatility", beta=1)

        _returns = pm.Normal("returns", mu=mu, sigma=sigma, observed=data_array)

        trace = pm.sample(samples, progressbar=progressbar, return_inferencedata=False)

    return model, trace


def model_returns_t(
    data: pd.Series,
    samples: int = 500,
    progressbar: bool = True,
) -> tuple[Any, Any]:
    """Run Bayesian model assuming returns are Student-T distributed.

    Parameters
    ----------
    data : pd.Series
        Daily returns of the strategy, noncumulative.
    samples : int, optional
        Number of posterior samples to draw.
    progressbar : bool, optional
        Show progress bar during sampling.

    Returns
    -------
    model : pymc.Model
        PyMC model containing all random variables.
    trace : pymc3.sampling.BaseTrace
        A trace object that contains samples for each parameter.
    """
    import pymc as pm

    data_array = np.asarray(data)

    with pm.Model() as model:
        mu = pm.Normal("mean_returns", mu=0, sigma=0.01)
        sigma = pm.HalfCauchy("volatility", beta=1)
        nu = pm.Exponential("nu_minus_two", 1 / 29.0) + 2.0

        _returns = pm.StudentT("returns", nu=nu, mu=mu, sigma=sigma, observed=data_array)

        trace = pm.sample(samples, progressbar=progressbar, return_inferencedata=False)

    return model, trace


def model_best(
    y1: pd.Series | np.ndarray,
    y2: pd.Series | np.ndarray,
    samples: int = 1000,
    progressbar: bool = True,
) -> tuple[Any, Any]:
    """Bayesian Estimation Supersedes the T-Test.

    This model runs a Bayesian hypothesis comparing if y1 and y2 come
    from the same distribution. Returns are assumed to be T-distributed.

    Parameters
    ----------
    y1 : array-like
        Array of returns (e.g., in-sample).
    y2 : array-like
        Array of returns (e.g., out-of-sample).
    samples : int, optional
        Number of posterior samples to draw.
    progressbar : bool, optional
        Show progress bar during sampling.

    Returns
    -------
    model : pymc.Model
        PyMC model containing all random variables.
    trace : pymc3.sampling.BaseTrace
        A trace object that contains samples for each parameter.
    """
    import pymc as pm

    y = pd.DataFrame({"y1": y1, "y2": y2})
    y = y.dropna()

    y1_array = np.asarray(y["y1"])
    y2_array = np.asarray(y["y2"])

    mu_m = np.mean(np.concatenate([y1_array, y2_array]))
    mu_p = np.std(np.concatenate([y1_array, y2_array])) * 1000

    sigma_low = np.std(np.concatenate([y1_array, y2_array])) / 1000
    sigma_high = np.std(np.concatenate([y1_array, y2_array])) * 1000

    with pm.Model() as model:
        group1_mean = pm.Normal("group1_mean", mu=mu_m, sigma=mu_p)
        group2_mean = pm.Normal("group2_mean", mu=mu_m, sigma=mu_p)
        group1_std = pm.Uniform("group1_std", lower=sigma_low, upper=sigma_high)
        group2_std = pm.Uniform("group2_std", lower=sigma_low, upper=sigma_high)
        nu = pm.Exponential("nu_minus_two", 1 / 29.0) + 2.0

        _returns_1 = pm.StudentT("returns_1", nu=nu, mu=group1_mean, sigma=group1_std, observed=y1_array)
        _returns_2 = pm.StudentT("returns_2", nu=nu, mu=group2_mean, sigma=group2_std, observed=y2_array)

        _diff_of_means = pm.Deterministic("difference_of_means", group1_mean - group2_mean)

        trace = pm.sample(samples, progressbar=progressbar, return_inferencedata=False)

    return model, trace


def model_stoch_vol(
    data: pd.Series,
    samples: int = 2000,
    progressbar: bool = True,
) -> tuple[Any, Any]:
    """Run a stochastic volatility model.

    This model estimates the volatility of a returns series over time.
    Returns are assumed to be T-distributed.

    Parameters
    ----------
    data : pd.Series
        Return series to model.
    samples : int, optional
        Posterior samples to draw.
    progressbar : bool, optional
        Show progress bar during sampling.

    Returns
    -------
    model : pymc.Model
        PyMC model containing all random variables.
    trace : pymc3.sampling.BaseTrace
        A trace object that contains samples for each parameter.
    """
    import pymc as pm

    data_array = np.asarray(data)

    with pm.Model() as model:
        sigma = pm.Exponential("sigma", 50.0)
        nu = pm.Exponential("nu", 0.1)
        s = pm.GaussianRandomWalk("s", sigma=sigma, shape=len(data_array))

        _r = pm.StudentT("r", nu=nu, sigma=pm.math.exp(-2 * s), observed=data_array)

        trace = pm.sample(samples, progressbar=progressbar, return_inferencedata=False)

    return model, trace


def compute_bayes_cone(
    preds: np.ndarray,
    starting_value: float = 1.0,
) -> dict[int, list[float]]:
    """Compute Bayesian cone from predictions.

    Parameters
    ----------
    preds : np.ndarray
        Predicted returns from posterior samples.
    starting_value : float, optional
        Starting portfolio value.

    Returns
    -------
    dict
        Dictionary of percentiles (1, 5, 25, 50, 75, 95, 99).
    """
    cum_preds = np.cumprod(preds + 1, axis=1) * starting_value

    def scoreatpercentile(cum_predictions, p):
        return np.percentile(cum_predictions, p, axis=0).tolist()

    return {
        1: scoreatpercentile(cum_preds, 1),
        5: scoreatpercentile(cum_preds, 5),
        25: scoreatpercentile(cum_preds, 25),
        50: scoreatpercentile(cum_preds, 50),
        75: scoreatpercentile(cum_preds, 75),
        95: scoreatpercentile(cum_preds, 95),
        99: scoreatpercentile(cum_preds, 99),
    }


def compute_consistency_score(
    returns_test: pd.Series,
    preds: np.ndarray,
) -> list[float]:
    """Compute consistency score.

    Parameters
    ----------
    returns_test : pd.Series
        Out-of-sample returns to evaluate.
    preds : np.ndarray
        Predicted returns from posterior samples.

    Returns
    -------
    list
        Consistency scores at each time point.
    """
    returns_test_cum = cum_returns(returns_test, starting_value=1.0)
    returns_arr = np.asarray(returns_test_cum)

    cum_preds = np.cumprod(preds + 1, axis=1)

    return (cum_preds < returns_arr[np.newaxis, :]).mean(axis=0).tolist()


def run_model(
    model: str,
    returns_train: pd.Series,
    returns_test: pd.Series | None = None,
    bmark: pd.Series | None = None,
    samples: int = 500,
    ppc: bool = False,
    progressbar: bool = True,
) -> tuple[Any, Any]:
    """Run Bayesian model on returns data.

    Parameters
    ----------
    model : str
        Model type: 'alpha_beta', 't', 'normal', or 'best'.
    returns_train : pd.Series
        Training returns.
    returns_test : pd.Series, optional
        Test returns for evaluation.
    bmark : pd.Series, optional
        Benchmark returns.
    samples : int, optional
        Number of posterior samples.
    ppc : bool, optional
        Whether to run posterior predictive check.
    progressbar : bool, optional
        Show progress bar during sampling.

    Returns
    -------
    model : pymc.Model
        PyMC model.
    trace : pymc3.sampling.BaseTrace
        Posterior trace.
    """
    if model == "alpha_beta":
        model_obj, trace = model_returns_t_alpha_beta(returns_train, bmark, samples=samples, progressbar=progressbar)
    elif model == "t":
        model_obj, trace = model_returns_t(returns_train, samples=samples, progressbar=progressbar)
    elif model == "normal":
        model_obj, trace = model_returns_normal(returns_train, samples=samples, progressbar=progressbar)
    elif model == "best":
        model_obj, trace = model_best(returns_train, bmark, samples=samples, progressbar=progressbar)
    else:
        raise NotImplementedError(f"Model {model} not implemented.")

    return model_obj, trace


def simulate_paths(
    is_returns: pd.DataFrame | pd.Series | np.ndarray,
    num_days: int,
    _starting_value: float = 1,
    num_samples: int = 1000,
    random_seed: int | None = None,
) -> np.ndarray:
    """Generate alternate paths using available values from in-sample returns.

    Parameters
    ----------
    is_returns : pandas.core.frame.DataFrame
        Non-cumulative in-sample returns.
    num_days : int
        Number of days to project the probability cone forward.
    _starting_value : int or float
        Starting value of the out sample period.
    num_samples : int
        Number of samples to draw from the in-sample daily returns.
    random_seed : int
        Seed for the pseudorandom number generator.

    Returns
    -------
    samples : numpy.ndarray
    """
    rng = np.random.RandomState(seed=random_seed)
    is_values = np.asarray(is_returns)
    indices = rng.randint(0, len(is_values), size=(num_samples, num_days))
    return is_values[indices]


def summarize_paths(
    samples: np.ndarray,
    cone_std: tuple[float, ...] | float = (1.0, 1.5, 2.0),
    starting_value: float = 1.0,
) -> pd.DataFrame:
    """Generate the upper and lower bounds of an n standard deviation cone.

    Parameters
    ----------
    samples : numpy.ndarray
        Alternative paths, or series of possible outcomes.
    cone_std : list of int/float
        Number of standard deviations to use in the boundaries of
        the cone.
    starting_value : float
        Starting value for cumulative returns.

    Returns
    -------
    pandas.DataFrame
        Cone bounds.
    """
    from fincore.metrics.returns import cum_returns

    cum_samples = cum_returns(samples.T, starting_value=starting_value).T

    cum_mean = cum_samples.mean(axis=0)
    cum_std = cum_samples.std(axis=0)

    stds: list[float] = [float(cone_std)] if isinstance(cone_std, (float, int)) else list(cone_std)

    cone_bounds = pd.DataFrame(columns=pd.Index([], dtype="float64"))
    for num_std in stds:
        cone_bounds.loc[:, float(num_std)] = cum_mean + cum_std * num_std
        cone_bounds.loc[:, float(-num_std)] = cum_mean - cum_std * num_std

    return cone_bounds


def forecast_cone_bootstrap(
    is_returns: pd.Series,
    num_days: int,
    cone_std: tuple[float, ...] | float = (1.0, 1.5, 2.0),
    starting_value: float = 1,
    num_samples: int = 1000,
    random_seed: int | None = None,
) -> pd.DataFrame:
    """Determine the upper and lower bounds of an n standard deviation cone.

    Future cumulative mean and standard deviation are computed by repeatedly sampling from the
    in-sample daily returns (i.e., bootstrap). This cone is non-parametric,
    meaning it does not assume that returns are normally distributed.

    Parameters
    ----------
    is_returns : pd.Series
        In-sample daily returns of the strategy, noncumulative.
    num_days : int
        Number of days to project the probability cone forward.
    cone_std : int, float, or list of int/float
        Number of standard deviations to use in the boundaries of
        the cone. If multiple values are passed, cone bounds will
        be generated for each value.
    starting_value : int or float
        Starting value of the out sample period.
    num_samples : int
        Number of samples to draw from the in-sample daily returns.
    random_seed : int
        Seed for the pseudorandom number generator.

    Returns
    -------
    pd.DataFrame
        Contains upper and lower cone boundaries.
    """
    samples = simulate_paths(
        is_returns=is_returns,
        num_days=num_days,
        _starting_value=starting_value,
        num_samples=num_samples,
        random_seed=random_seed,
    )

    return summarize_paths(samples=samples, cone_std=cone_std, starting_value=starting_value)
