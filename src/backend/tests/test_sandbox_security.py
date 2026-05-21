"""
Tests for the strategy sandbox security module.

Covers:
- Code safety checks (AST analysis)
- Safe import restrictions
- Dangerous module/function blocking
- Safe globals creation
"""

import pytest

from app.utils.sandbox import StrategySandbox


class TestCodeSafety:
    """Test _check_code_safety AST analysis."""

    def test_safe_strategy_code_passes(self):
        """Valid strategy code should pass safety checks."""
        code = """
import bt
import math

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
        # Should not raise
        StrategySandbox._check_code_safety(code)

    def test_import_os_blocked(self):
        """Importing os module should be blocked."""
        code = "import os\nos.system('rm -rf /')"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_import_subprocess_blocked(self):
        """Importing subprocess module should be blocked."""
        code = "import subprocess\nsubprocess.run(['ls'])"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_import_sys_blocked(self):
        """Importing sys module should be blocked."""
        code = "import sys\nsys.exit(1)"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_from_os_import_blocked(self):
        """from os import ... should be blocked."""
        code = "from os import path"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_import_socket_blocked(self):
        """Importing socket module should be blocked."""
        code = "import socket"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_import_importlib_blocked(self):
        """Importing importlib should be blocked."""
        code = "import importlib"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_access_builtins_blocked(self):
        """Accessing __builtins__ should be blocked."""
        code = "x = __builtins__"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_access_class_blocked(self):
        """Accessing __class__ attribute should be blocked."""
        code = "x = self.__class__.__mro__"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_access_subclasses_blocked(self):
        """Accessing __subclasses__ should be blocked."""
        code = "x = object.__subclasses__()"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_globals_call_blocked(self):
        """Calling globals() should be blocked."""
        code = "x = globals()"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_locals_call_blocked(self):
        """Calling locals() should be blocked."""
        code = "x = locals()"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_eval_call_blocked(self):
        """Calling eval() should be blocked."""
        code = "eval('__import__(\"os\")')"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_exec_call_blocked(self):
        """Calling exec() should be blocked."""
        code = "exec('import os')"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_compile_call_blocked(self):
        """Calling compile() should be blocked."""
        code = "compile('import os', '<string>', 'exec')"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_getattr_with_dangerous_attr_blocked(self):
        """getattr with dangerous attribute name should be blocked."""
        code = "getattr(obj, '__class__')"
        with pytest.raises(ValueError, match="not allowed"):
            StrategySandbox._check_code_safety(code)

    def test_syntax_error_propagates(self):
        """Syntax errors should propagate as SyntaxError."""
        code = "def foo(:\n  pass"
        with pytest.raises(SyntaxError):
            StrategySandbox._check_code_safety(code)

    def test_safe_math_operations(self):
        """Math operations should be allowed."""
        code = """
import math
x = math.sqrt(16)
y = abs(-5)
z = max(1, 2, 3)
"""
        StrategySandbox._check_code_safety(code)

    def test_safe_datetime_import(self):
        """datetime import should be allowed."""
        code = "import datetime\ntoday = datetime.date.today()"
        StrategySandbox._check_code_safety(code)


class TestSafeImport:
    """Test _safe_import function."""

    def test_import_bt_allowed(self):
        """Importing bt (backtrader) should be allowed."""
        result = StrategySandbox._safe_import("bt")
        import backtrader

        assert result is backtrader

    def test_import_math_allowed(self):
        """Importing math should be allowed."""
        result = StrategySandbox._safe_import("math")
        import math

        assert result is math

    def test_import_datetime_allowed(self):
        """Importing datetime should be allowed."""
        result = StrategySandbox._safe_import("datetime")
        # The sandbox maps 'datetime' to whatever is in _ALLOWED_MODULES
        assert result is not None

    def test_import_os_blocked(self):
        """Importing os should raise ImportError."""
        with pytest.raises(ImportError, match="not allowed"):
            StrategySandbox._safe_import("os")

    def test_import_subprocess_blocked(self):
        """Importing subprocess should raise ImportError."""
        with pytest.raises(ImportError, match="not allowed"):
            StrategySandbox._safe_import("subprocess")

    def test_import_socket_blocked(self):
        """Importing socket should raise ImportError."""
        with pytest.raises(ImportError, match="not allowed"):
            StrategySandbox._safe_import("socket")

    def test_import_requests_blocked(self):
        """Importing requests should raise ImportError."""
        with pytest.raises(ImportError, match="not allowed"):
            StrategySandbox._safe_import("requests")


class TestSafeGlobals:
    """Test _create_safe_globals."""

    def test_safe_globals_has_builtins(self):
        """Safe globals should include whitelisted builtins."""
        globals_dict = StrategySandbox._create_safe_globals()
        builtins = globals_dict["__builtins__"]
        assert "abs" in builtins
        assert "len" in builtins
        assert "range" in builtins
        assert "int" in builtins
        assert "float" in builtins

    def test_safe_globals_no_dangerous_builtins(self):
        """Safe globals should NOT include dangerous builtins."""
        globals_dict = StrategySandbox._create_safe_globals()
        builtins = globals_dict["__builtins__"]
        assert "eval" not in builtins
        assert "exec" not in builtins
        assert "compile" not in builtins
        assert "open" not in builtins
        assert "__import__" not in builtins

    def test_safe_globals_has_allowed_modules(self):
        """Safe globals should include allowed modules."""
        globals_dict = StrategySandbox._create_safe_globals()
        assert "bt" in globals_dict
        assert "math" in globals_dict
        assert "datetime" in globals_dict

    def test_safe_globals_no_dangerous_modules(self):
        """Safe globals should NOT include dangerous modules."""
        globals_dict = StrategySandbox._create_safe_globals()
        assert "os" not in globals_dict
        assert "sys" not in globals_dict
        assert "subprocess" not in globals_dict

    def test_safe_globals_has_safe_import(self):
        """Safe globals should have __import__ set to safe_import."""
        globals_dict = StrategySandbox._create_safe_globals()
        assert globals_dict["__import__"] == StrategySandbox._safe_import


class TestSafePrint:
    """Test _safe_print function."""

    def test_safe_print_does_nothing(self):
        """_safe_print should silently do nothing."""
        # Should not raise or produce output
        StrategySandbox._safe_print("hello", "world")
        StrategySandbox._safe_print()
        StrategySandbox._safe_print(sep=",", end="\n")
