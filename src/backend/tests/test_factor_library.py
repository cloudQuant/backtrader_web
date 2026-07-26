import pytest


@pytest.mark.asyncio
async def test_factor_registry_lists_builtin_factors():
    from app.services.factor_lib.registry import FactorRegistry

    registry = FactorRegistry.with_builtin_factors()
    factors = registry.list_factors()

    ids = {factor.id for factor in factors}
    assert {"momentum_5", "volatility_5", "reversal_1"}.issubset(ids)
    assert all(factor.category in {"momentum", "risk", "reversal"} for factor in factors)


@pytest.mark.asyncio
async def test_factor_registry_gets_factor_by_id():
    from app.services.factor_lib.registry import FactorRegistry

    registry = FactorRegistry.with_builtin_factors()
    factor = registry.get_factor("momentum_5")

    assert factor.id == "momentum_5"
    assert factor.lookback == 5


@pytest.mark.asyncio
async def test_momentum_factor_calculates_period_return():
    from app.services.factor_lib.registry import FactorRegistry

    registry = FactorRegistry.with_builtin_factors()
    values = registry.calculate(
        "momentum_5",
        [{"close": value} for value in [100, 101, 102, 103, 104, 110]],
    )

    assert values[:5] == [None, None, None, None, None]
    assert values[5] == pytest.approx(0.10)


@pytest.mark.asyncio
async def test_volatility_factor_calculates_return_std():
    from app.services.factor_lib.registry import FactorRegistry

    registry = FactorRegistry.with_builtin_factors()
    values = registry.calculate(
        "volatility_5",
        [{"close": value} for value in [100, 101, 102, 103, 104, 110]],
    )

    assert values[:5] == [None, None, None, None, None]
    assert values[5] is not None
    assert values[5] > 0


@pytest.mark.asyncio
async def test_reversal_factor_calculates_negative_one_period_return():
    from app.services.factor_lib.registry import FactorRegistry

    registry = FactorRegistry.with_builtin_factors()
    values = registry.calculate("reversal_1", [{"close": value} for value in [100, 98]])

    assert values == [None, pytest.approx(0.02)]


@pytest.mark.asyncio
async def test_factor_registry_raises_for_unknown_factor():
    from app.services.factor_lib.registry import FactorRegistry

    registry = FactorRegistry.with_builtin_factors()

    with pytest.raises(KeyError):
        registry.get_factor("unknown")
