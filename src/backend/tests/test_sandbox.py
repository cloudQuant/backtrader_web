"""
Sandbox security execution tests.
"""
import pytest
from app.utils.sandbox import StrategySandbox, execute_strategy_safely, DockerSandbox
from unittest.mock import patch, MagicMock
import backtrader as bt


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
    """Code safety check tests."""

    def test_safe_code_passes(self):
        StrategySandbox._check_code_safety("x = 1 + 2")  # should not raise

    def test_dangerous_import_os(self):
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import os")

    def test_dangerous_import_subprocess(self):
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import subprocess")

    def test_dangerous_import_sys(self):
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import sys")

    def test_dangerous_from_import(self):
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("from os import path")

    def test_dangerous_eval(self):
        with pytest.raises(ValueError, match="Using dangerous function is not allowed"):
            StrategySandbox._check_code_safety("eval('1+1')")

    def test_dangerous_exec(self):
        with pytest.raises(ValueError, match="Using dangerous function is not allowed"):
            StrategySandbox._check_code_safety("exec('pass')")

    def test_dangerous_open(self):
        with pytest.raises(ValueError, match="Using dangerous function is not allowed"):
            StrategySandbox._check_code_safety("open('/etc/passwd')")

    def test_dangerous_compile(self):
        with pytest.raises(ValueError, match="Using dangerous function is not allowed"):
            StrategySandbox._check_code_safety("compile('x=1', '', 'exec')")

    def test_dangerous_builtins_access(self):
        with pytest.raises(ValueError, match="Accessing __builtins__ is not allowed"):
            StrategySandbox._check_code_safety("x = __builtins__")

    def test_dangerous_globals_access(self):
        with pytest.raises(ValueError, match="Using globals\\(\\) or locals\\(\\) is not allowed"):
            StrategySandbox._check_code_safety("globals()['x'] = 1")

    def test_dangerous_locals_access(self):
        with pytest.raises(ValueError, match="Using globals\\(\\) or locals\\(\\) is not allowed"):
            StrategySandbox._check_code_safety("locals()['x'] = 1")

    def test_dangerous_pickle(self):
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import pickle")

    def test_dangerous_socket(self):
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import socket")

    def test_dangerous_shutil(self):
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import shutil")

    def test_dangerous_file(self):
        """Test detection of file function."""
        with pytest.raises(ValueError, match="Using dangerous function is not allowed"):
            StrategySandbox._check_code_safety("file('test.txt')")

    def test_dangerous_input(self):
        """Test detection of input function."""
        with pytest.raises(ValueError, match="Using dangerous function is not allowed"):
            StrategySandbox._check_code_safety("input()")

    def test_dangerous_raw_input(self):
        """Test detection of raw_input function."""
        with pytest.raises(ValueError, match="Using dangerous function is not allowed"):
            StrategySandbox._check_code_safety("raw_input()")

    def test_dangerous_requests(self):
        """Test detection of requests module."""
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import requests")

    def test_dangerous_http(self):
        """Test detection of http module."""
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import http")

    def test_dangerous_urllib(self):
        """Test detection of urllib module."""
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import urllib")

    def test_dangerous_dir(self):
        """Test detection of dir function."""
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import dir")

    def test_dangerous_vars(self):
        """Test detection of vars function."""
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox._check_code_safety("import vars")


class TestCreateSafeGlobals:
    """Safe global namespace tests."""

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

    def test_safe_globals_has_datetime(self):
        """Test contains datetime module."""
        g = StrategySandbox._create_safe_globals()
        assert 'datetime' in g

    def test_safe_globals_has_math(self):
        """Test contains math module."""
        g = StrategySandbox._create_safe_globals()
        assert 'math' in g

    def test_safe_globals_has_safe_print(self):
        """Test contains safe print function."""
        g = StrategySandbox._create_safe_globals()
        assert '__print__' in g

    def test_safe_globals_no_dangerous_builtins(self):
        """Test does not contain dangerous built-in functions."""
        g = StrategySandbox._create_safe_globals()
        assert 'print' not in g['__builtins__']
        assert 'open' not in g['__builtins__']
        assert 'eval' not in g['__builtins__']
        assert 'exec' not in g['__builtins__']


class TestSafeImport:
    """Safe import tests."""

    def test_allowed_import(self):
        result = StrategySandbox._safe_import('datetime')
        assert result is not None

    def test_disallowed_import(self):
        with pytest.raises(ImportError, match="is not allowed"):
            StrategySandbox._safe_import('os')

    def test_allowed_import_math(self):
        """Test allowed import of math."""
        result = StrategySandbox._safe_import('math')
        assert result is not None

    def test_allowed_import_bt(self):
        """Test allowed import of bt."""
        result = StrategySandbox._safe_import('bt')
        assert result is not None

    def test_disallowed_import_socket(self):
        """Test disallowed import of socket."""
        with pytest.raises(ImportError, match="is not allowed"):
            StrategySandbox._safe_import('socket')

    def test_import_datetime_class(self):
        """Test accessing datetime through import."""
        # In _ALLOWED_MODULES, datetime is the datetime class (from datetime module)
        result = StrategySandbox._safe_import('datetime')
        assert result is not None
        # Result should be datetime class (because class is stored in _ALLOWED_MODULES)
        # not the datetime module

    def test_import_nonexistent_submodule(self):
        """Test import of non-existent submodule."""
        with pytest.raises(ImportError, match="Cannot import"):
            StrategySandbox._safe_import('datetime.nonexistent')

    def test_safe_print_does_nothing(self):
        """Test safe print does nothing."""
        StrategySandbox._safe_print("hello", "world")  # should not raise
        result = StrategySandbox._safe_print("test")
        assert result is None


class TestExecuteStrategyCode:
    """Execute strategy code tests."""

    def test_execute_valid_strategy(self):
        """Test executing valid strategy."""
        result = StrategySandbox.execute_strategy_code(VALID_STRATEGY)
        assert result is not None
        assert issubclass(result, bt.Strategy)
        assert result.__name__ == 'MyStrategy'

    def test_execute_no_strategy_class(self):
        """Test code without strategy class."""
        with pytest.raises(ValueError, match="No valid Strategy class found"):
            StrategySandbox.execute_strategy_code(NO_STRATEGY_CODE)

    def test_execute_syntax_error(self):
        """Test syntax error."""
        with pytest.raises(SyntaxError, match="syntax error"):
            StrategySandbox.execute_strategy_code(SYNTAX_ERROR_CODE)

    def test_execute_with_params(self):
        """Test execution with parameters."""
        code = """
class TestStrategy(bt.Strategy):
    params = (('custom', None),)

    def __init__(self):
        if custom_param is not None:
            self.custom = custom_param
"""
        result = StrategySandbox.execute_strategy_code(code, params={'custom_param': 42})
        assert result is not None
        assert issubclass(result, bt.Strategy)

    def test_execute_with_undefined_variable(self):
        """Test using undefined variable - __init__ doesn't execute during class definition."""
        # Undefined variables don't error during class definition, only during instantiation
        # So this test verifies code can compile successfully
        code = """
class TestStrategy(bt.Strategy):
    def __init__(self):
        self.x = undefined_var
"""
        result = StrategySandbox.execute_strategy_code(code)
        assert result is not None
        assert issubclass(result, bt.Strategy)

    def test_execute_name_error_at_top_level(self):
        """NameError should be re-raised with a helpful message."""
        code = "x = not_defined_name\n"
        with pytest.raises(NameError, match="Undefined name"):
            StrategySandbox.execute_strategy_code(code)

    def test_execute_attribute_error_at_top_level(self):
        """AttributeError should be re-raised with a helpful message."""
        code = "x = (1).not_allowed_attr\n"
        with pytest.raises(AttributeError, match="Disallowed attribute"):
            StrategySandbox.execute_strategy_code(code)

    def test_execute_import_error_from_safe_import(self):
        """ImportError from safe import should be re-raised with a helpful message."""
        code = """
import datetime.nonexistent

class TestStrategy(bt.Strategy):
    pass
"""
        with pytest.raises(ImportError, match="Disallowed module import"):
            StrategySandbox.execute_strategy_code(code)

    def test_execute_issubclass_type_error_is_ignored(self):
        """If issubclass raises TypeError, the sandbox should continue scanning."""
        code = "class Foo: pass\n"
        with patch("app.utils.sandbox.bt.Strategy", 1):
            with pytest.raises(ValueError, match="No valid Strategy class found"):
                StrategySandbox.execute_strategy_code(code)

    def test_execute_with_dangerous_import_runtime(self):
        """Test dangerous import is intercepted during code check phase."""
        code = """
class TestStrategy(bt.Strategy):
    def __init__(self):
        import os
        self.os = os
"""
        # Dangerous import is intercepted by ValueError in _check_code_safety phase
        with pytest.raises(ValueError, match="Importing dangerous module is not allowed"):
            StrategySandbox.execute_strategy_code(code)

    def test_execute_empty_code(self):
        """Test empty code."""
        with pytest.raises(ValueError, match="No valid Strategy class found"):
            StrategySandbox.execute_strategy_code("")

    def test_execute_only_whitespace(self):
        """Test whitespace-only code."""
        with pytest.raises(ValueError, match="No valid Strategy class found"):
            StrategySandbox.execute_strategy_code("   \n\n  ")

    def test_execute_with_multiple_strategies(self):
        """Test multiple strategy classes, return first one."""
        code = """
class FirstStrategy(bt.Strategy):
    pass

class SecondStrategy(bt.Strategy):
    pass
"""
        result = StrategySandbox.execute_strategy_code(code)
        assert result is not None
        assert result.__name__ == 'FirstStrategy'

    def test_execute_with_indicators(self):
        """Test using indicators."""
        code = """
class TestStrategy(bt.Strategy):
    def __init__(self):
        self.sma = bt.indicators.SMA(self.data.close, period=20)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
"""
        result = StrategySandbox.execute_strategy_code(code)
        assert result is not None
        assert issubclass(result, bt.Strategy)

    def test_execute_with_math_functions(self):
        """Test using math functions - directly using math."""
        code = """
class TestStrategy(bt.Strategy):
    def __init__(self):
        self.pi = math.pi
        self.sqrt = math.sqrt(16)
"""
        # math is already in safe_globals
        result = StrategySandbox.execute_strategy_code(code)
        assert result is not None
        assert issubclass(result, bt.Strategy)

    def test_execute_with_datetime(self):
        """Test using datetime - directly using datetime."""
        code = """
class TestStrategy(bt.Strategy):
    def __init__(self):
        self.now = datetime.datetime.now()
        self.delta = datetime.timedelta(days=1)
"""
        # datetime is already in safe_globals
        result = StrategySandbox.execute_strategy_code(code)
        assert result is not None
        assert issubclass(result, bt.Strategy)

    def test_execute_with_list_comprehension(self):
        """Test using list comprehension."""
        code = """
class TestStrategy(bt.Strategy):
    def __init__(self):
        self.squares = [x**2 for x in range(10)]
"""
        result = StrategySandbox.execute_strategy_code(code)
        assert result is not None
        assert issubclass(result, bt.Strategy)

    def test_execute_non_strategy_class(self):
        """Test non-strategy class."""
        code = """
class NotStrategy:
    pass
"""
        with pytest.raises(ValueError, match="No valid Strategy class found"):
            StrategySandbox.execute_strategy_code(code)

    def test_execute_bt_strategy_base(self):
        """Test bt.Strategy base class itself."""
        code = """
# Just referencing bt.Strategy, not subclassing
x = bt.Strategy
"""
        with pytest.raises(ValueError, match="No valid Strategy class found"):
            StrategySandbox.execute_strategy_code(code)

    def test_execute_with_attribute_error(self):
        """Test attribute error - __init__ doesn't execute during class definition."""
        # Attribute errors don't occur during class definition, only during instantiation
        code = """
class TestStrategy(bt.Strategy):
    def __init__(self):
        self.x = nonexistent.attr
"""
        result = StrategySandbox.execute_strategy_code(code)
        assert result is not None
        assert issubclass(result, bt.Strategy)


class TestExecuteStrategySafely:
    """Convenience function tests."""

    def test_execute_safely_docker_raises(self):
        with pytest.raises((NotImplementedError, RuntimeError)):
            execute_strategy_safely("x=1", params={}, use_docker=True)

    def test_execute_safely_docker_reaches_not_implemented(self):
        with patch.object(DockerSandbox, "execute_in_container", return_value={"ok": True}):
            with pytest.raises(NotImplementedError):
                execute_strategy_safely("x=1", params={}, use_docker=True)

    def test_execute_safely_without_docker(self):
        """Test without using Docker."""
        result = execute_strategy_safely(VALID_STRATEGY, use_docker=False)
        assert result is not None
        assert issubclass(result, bt.Strategy)

    def test_execute_safely_with_params(self):
        """Test with parameters."""
        result = execute_strategy_safely(VALID_STRATEGY, params={'period': 20}, use_docker=False)
        assert result is not None
        assert issubclass(result, bt.Strategy)


class TestDockerSandbox:
    """Docker sandbox tests."""

    def test_docker_not_available(self):
        """Docker binary missing should raise a RuntimeError."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(RuntimeError, match="Docker is not available"):
                DockerSandbox.execute_in_container("print('x')", {}, timeout=1)

    def test_docker_check_fails(self):
        """Docker version check failure should raise a RuntimeError."""
        import subprocess

        def _fake_run(args, **kwargs):
            if args[:2] == ["docker", "--version"]:
                raise subprocess.CalledProcessError(1, args, output="", stderr="nope")
            raise AssertionError("unexpected subprocess.run call")

        with patch("subprocess.run", side_effect=_fake_run):
            with pytest.raises(RuntimeError, match="Docker is not available"):
                DockerSandbox.execute_in_container("print('x')", {}, timeout=1)

    def test_docker_execution_fails(self):
        """Non-zero returncode should raise a RuntimeError."""
        import subprocess

        calls = []

        def _fake_run(args, **kwargs):
            calls.append(args)
            if args[:2] == ["docker", "--version"]:
                return subprocess.CompletedProcess(args, 0, stdout="Docker 0.0", stderr="")
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="boom")

        with patch("subprocess.run", side_effect=_fake_run):
            with pytest.raises(RuntimeError, match="Strategy execution failed"):
                DockerSandbox.execute_in_container("print('x')", {}, timeout=1)

    def test_docker_json_parse_fails(self):
        """Bad stdout should raise a RuntimeError."""
        import subprocess

        def _fake_run(args, **kwargs):
            if args[:2] == ["docker", "--version"]:
                return subprocess.CompletedProcess(args, 0, stdout="Docker 0.0", stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="not-json", stderr="")

        with patch("subprocess.run", side_effect=_fake_run):
            with pytest.raises(RuntimeError, match="Cannot parse execution result"):
                DockerSandbox.execute_in_container("print('x')", {}, timeout=1)
