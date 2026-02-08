"""
沙箱安全执行测试
"""
import pytest
from app.utils.sandbox import StrategySandbox, execute_strategy_safely


VALID_STRATEGY = """
class MyStrategy(bt.Strategy):
    params = (('period', 20),)

    def __init__(self):
        self.sma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.params.period)

    def next(self):
        if self.data.close[0] > self.sma[0]:
            self.buy()
        elif self.data.close[0] < self.sma[0]:
            self.sell()
"""

NO_STRATEGY_CODE = """
x = 1 + 2
y = x * 3
"""

SYNTAX_ERROR_CODE = """
def broken(
    pass
"""


class TestCodeSafety:
    """代码安全检查测试"""

    def test_safe_code_passes(self):
        StrategySandbox._check_code_safety("x = 1 + 2")  # should not raise

    def test_dangerous_import_os(self):
        with pytest.raises(ValueError, match="不允许导入危险模块"):
            StrategySandbox._check_code_safety("import os")

    def test_dangerous_import_subprocess(self):
        with pytest.raises(ValueError, match="不允许导入危险模块"):
            StrategySandbox._check_code_safety("import subprocess")

    def test_dangerous_import_sys(self):
        with pytest.raises(ValueError, match="不允许导入危险模块"):
            StrategySandbox._check_code_safety("import sys")

    def test_dangerous_from_import(self):
        with pytest.raises(ValueError, match="不允许导入危险模块"):
            StrategySandbox._check_code_safety("from os import path")

    def test_dangerous_eval(self):
        with pytest.raises(ValueError, match="不允许使用危险函数"):
            StrategySandbox._check_code_safety("eval('1+1')")

    def test_dangerous_exec(self):
        with pytest.raises(ValueError, match="不允许使用危险函数"):
            StrategySandbox._check_code_safety("exec('pass')")

    def test_dangerous_open(self):
        with pytest.raises(ValueError, match="不允许使用危险函数"):
            StrategySandbox._check_code_safety("open('/etc/passwd')")

    def test_dangerous_compile(self):
        with pytest.raises(ValueError, match="不允许使用危险函数"):
            StrategySandbox._check_code_safety("compile('x=1', '', 'exec')")

    def test_dangerous_builtins_access(self):
        with pytest.raises(ValueError, match="不允许访问 __builtins__"):
            StrategySandbox._check_code_safety("x = __builtins__")

    def test_dangerous_globals_access(self):
        with pytest.raises(ValueError, match="不允许使用 globals"):
            StrategySandbox._check_code_safety("globals()['x'] = 1")

    def test_dangerous_locals_access(self):
        with pytest.raises(ValueError, match="不允许使用 globals"):
            StrategySandbox._check_code_safety("locals()['x'] = 1")

    def test_dangerous_pickle(self):
        with pytest.raises(ValueError, match="不允许导入危险模块"):
            StrategySandbox._check_code_safety("import pickle")

    def test_dangerous_socket(self):
        with pytest.raises(ValueError, match="不允许导入危险模块"):
            StrategySandbox._check_code_safety("import socket")

    def test_dangerous_shutil(self):
        with pytest.raises(ValueError, match="不允许导入危险模块"):
            StrategySandbox._check_code_safety("import shutil")


class TestCreateSafeGlobals:
    """安全全局命名空间测试"""

    def test_safe_globals_has_builtins(self):
        g = StrategySandbox._create_safe_globals()
        assert '__builtins__' in g
        assert 'abs' in g['__builtins__']
        assert 'int' in g['__builtins__']

    def test_safe_globals_has_bt(self):
        g = StrategySandbox._create_safe_globals()
        import backtrader as bt
        assert g['bt'] is bt

    def test_safe_globals_has_safe_import(self):
        g = StrategySandbox._create_safe_globals()
        assert '__import__' in g


class TestSafeImport:
    """安全导入测试"""

    def test_allowed_import(self):
        result = StrategySandbox._safe_import('datetime')
        assert result is not None

    def test_disallowed_import(self):
        with pytest.raises(ImportError, match="不被允许导入"):
            StrategySandbox._safe_import('os')

    def test_safe_print_does_nothing(self):
        StrategySandbox._safe_print("hello", "world")  # should not raise


class TestExecuteStrategySafely:
    """便捷函数测试"""

    def test_execute_safely_docker_raises(self):
        with pytest.raises((NotImplementedError, RuntimeError)):
            execute_strategy_safely("x=1", params={}, use_docker=True)
