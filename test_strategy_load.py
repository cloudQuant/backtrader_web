#!/usr/bin/env python3
"""Test: verify strategy loading and backtest execution for built-in templates."""
import sys
import traceback
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "src" / "backend"))

import backtrader as bt


def test_load_strategy(strategy_id: str = "002_dual_ma"):
    """Test loading a single strategy from templates."""
    from app.services.strategy_service import STRATEGIES_DIR, get_template_by_id

    print(f"\n{'='*60}")
    print(f"Testing strategy: {strategy_id}")
    print(f"STRATEGIES_DIR: {STRATEGIES_DIR}")
    print(f"STRATEGIES_DIR exists: {STRATEGIES_DIR.is_dir()}")

    # 1) Check template exists
    template = get_template_by_id(strategy_id)
    if not template:
        print(f"FAIL: Template '{strategy_id}' not found in STRATEGY_TEMPLATES")
        return False
    print(f"Template found: {template.name}")

    # 2) Check strategy file exists
    strategy_dir = STRATEGIES_DIR / strategy_id
    code_files = list(strategy_dir.glob("strategy_*.py"))
    print(f"Strategy dir: {strategy_dir}")
    print(f"Code files: {code_files}")

    # 3) Try loading via _load_strategy_from_code logic
    import types as _types

    module_name = f"strategy_{strategy_id}"
    import builtins
    module = _types.ModuleType(module_name)
    module.__dict__['__builtins__'] = builtins
    # Register in sys.modules so backtrader metaclass can find it
    sys.modules[module_name] = module

    if code_files:
        real_file = str(code_files[0])
        module.__dict__['__file__'] = real_file
        str_dir = str(strategy_dir)
        if str_dir not in sys.path:
            sys.path.insert(0, str_dir)
        print(f"Injected __file__: {real_file}")

    code = template.code
    print(f"Code length: {len(code)} chars")
    print(f"Code first 200 chars:\n{code[:200]}")
    print(f"\n--- Executing code ---")

    try:
        compiled = compile(code, module.__dict__.get('__file__', '<strategy>'), 'exec')
        exec(compiled, module.__dict__)
    except Exception as e:
        print(f"FAIL during exec: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

    # 4) Find Strategy subclass
    strategy_class = None
    for name, obj in module.__dict__.items():
        if isinstance(obj, type) and issubclass(obj, bt.Strategy) and obj is not bt.Strategy:
            strategy_class = obj
            print(f"Found strategy class: {name} -> {obj}")
            break

    if not strategy_class:
        print("FAIL: No bt.Strategy subclass found")
        # Show all classes defined
        for name, obj in module.__dict__.items():
            if isinstance(obj, type):
                print(f"  class: {name} bases={obj.__bases__}")
        return False

    # 5) Quick backtest smoke test
    print(f"\n--- Running mini backtest with {strategy_class.__name__} ---")
    try:
        cerebro = bt.Cerebro()
        cerebro.addstrategy(strategy_class)

        # Create minimal synthetic data
        import pandas as pd
        import numpy as np
        from datetime import datetime, timedelta

        dates = pd.date_range(start='2024-01-01', periods=100, freq='B')
        np.random.seed(42)
        price = 100 + np.cumsum(np.random.randn(100) * 0.5)
        df = pd.DataFrame({
            'open': price,
            'high': price + abs(np.random.randn(100) * 0.3),
            'low': price - abs(np.random.randn(100) * 0.3),
            'close': price + np.random.randn(100) * 0.2,
            'volume': np.random.randint(1000, 10000, 100).astype(float),
        }, index=dates)

        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        cerebro.broker.setcash(100000)
        cerebro.broker.setcommission(commission=0.001)

        results = cerebro.run()
        final = cerebro.broker.getvalue()
        print(f"SUCCESS: Backtest completed. Final value: {final:.2f}")
        return True
    except Exception as e:
        print(f"FAIL during backtest: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Test a few strategies
    test_ids = ["002_dual_ma", "029_macd_kdj", "025_boll"]
    results = {}
    for sid in test_ids:
        try:
            results[sid] = test_load_strategy(sid)
        except Exception as e:
            print(f"UNEXPECTED ERROR for {sid}: {e}")
            traceback.print_exc()
            results[sid] = False

    print(f"\n{'='*60}")
    print("RESULTS:")
    for sid, ok in results.items():
        print(f"  {sid}: {'PASS' if ok else 'FAIL'}")
