"""
沙箱安全执行测试

测试策略代码的安全执行功能
"""
import pytest
from app.utils.sandbox import StrategySandbox, DockerSandbox, execute_strategy_safely
import backtrader as bt


class TestStrategySandbox:
    """测试受限 Python 环境沙箱"""

    def test_safe_globals_creation(self):
        """测试安全命名空间创建"""
        safe_globals = StrategySandbox._create_safe_globals()

        # 检查允许的内置函数存在
        assert 'abs' in safe_globals
        assert 'sum' in safe_globals
        assert 'max' in safe_globals
        assert 'min' in safe_globals

        # 检查允许的模块存在
        assert 'bt' in safe_globals
        assert 'datetime' in safe_globals
        assert 'math' in safe_globals

        # 检查危险的内置函数不存在
        assert 'eval' not in safe_globals
        assert 'exec' not in safe_globals
        assert 'open' not in safe_globals
        assert '__import__' not in safe_globals

        # 检查 __builtins__ 受保护
        assert isinstance(safe_globals['__builtins__'], dict)

    def test_safe_import_rejects_dangerous_modules(self):
        """测试安全的 import 函数拒绝危险模块"""
        safe_globals = StrategySandbox._create_safe_globals()

        # 尝试导入危险模块应该失败
        with pytest.raises(ImportError, match="不允许导入危险模块"):
            StrategySandbox._safe_import('os')

        with pytest.raises(ImportError, match="不允许导入危险模块"):
            StrategySandbox._safe_import('sys')

        with pytest.raises(ImportError, match="不允许导入危险模块"):
            StrategySandbox._safe_import('subprocess')

        # 导入允许的模块应该成功
        result = StrategySandbox._safe_import('datetime')
        assert result.__name__ == 'datetime'

    def test_check_code_safety_rejects_dangerous_code(self):
        """测试代码安全性检查拒绝危险代码"""

        # 包含危险模块导入的代码
        dangerous_imports = [
            "import os",
            "from os import path",
            "import subprocess",
            "import sys",
        ]

        for code in dangerous_imports:
            with pytest.raises(ValueError, match="不允许导入危险模块"):
                StrategySandbox._check_code_safety(code)

        # 包含危险函数调用的代码
        dangerous_functions = [
            "eval('1 + 1')",
            "exec('print(1)')",
            "open('/etc/passwd')",
            "globals()[',
        ]

        for code in dangerous_functions:
            with pytest.raises(ValueError, match="不允许使用危险函数"):
                StrategySandbox._check_code_safety(code)

        # 包含访问 __builtins__ 的代码
        dangerous_builtins = [
            "__builtins__",
            "globals()[',
            "locals()[',
        ]

        for code in dangerous_builtins:
            with pytest.raises(ValueError, match="不允许访问"):
                StrategySandbox._check_code_safety(code)

    def test_execute_strategy_code_valid(self):
        """测试执行有效的策略代码"""
        # 有效的双均线策略代码
        valid_code = '''
import backtrader as bt

class MaCrossStrategy(bt.Strategy):
    """双均线交叉策略"""
    params = (
        ('fast_period', 5),
        ('slow_period', 20),
    )
    
    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=self.p.fast_period)
        self.slow_ma = bt.indicators.SMA(period=self.p.slow_period)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
    
    def next(self):
        if not self.position:
            if self.crossover > 0:
                self.buy()
        elif self.crossover < 0:
            self.sell()
'''

        # 执行应该成功
        strategy_class = StrategySandbox.execute_strategy_code(valid_code)

        # 验证返回的是策略类
        assert isinstance(strategy_class, type)
        assert issubclass(strategy_class, bt.Strategy)
        assert strategy_class.__name__ == 'MaCrossStrategy'

    def test_execute_strategy_code_invalid_syntax(self):
        """测试执行无效语法的策略代码"""
        invalid_code = '''
import backtrader as bt

class MaCrossStrategy(bt.Strategy):
    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=5
        # 缺少右括号
'''

        with pytest.raises(SyntaxError, match="策略代码语法错误"):
            StrategySandbox.execute_strategy_code(invalid_code)

    def test_execute_strategy_code_no_strategy_class(self):
        """测试执行没有 Strategy 类的代码"""
        no_strategy_code = '''
import backtrader as bt

class SomeClass:
    pass
'''

        with pytest.raises(ValueError, match="未找到有效的 Strategy 类"):
            StrategySandbox.execute_strategy_code(no_strategy_code)

    def test_execute_strategy_code_with_params(self):
        """测试执行带参数的策略代码"""
        code = '''
import backtrader as bt

class TestStrategy(bt.Strategy):
    params = (('period', 20),)
    
    def __init__(self):
        self.sma = bt.indicators.SMA(period=self.p.period)
    
    def next(self):
        pass
'''

        params = {'period': 30}

        strategy_class = StrategySandbox.execute_strategy_code(code, params)

        # 验证参数被正确传递
        strategy_instance = strategy_class()
        assert strategy_instance.params.period == 30


class TestDockerSandbox:
    """测试 Docker 容器沙箱（需要 Docker）"""

    @pytest.mark.skipif(
        not pytest.importors.skip('subprocess').skip('docker'),
        reason="Docker not available"
    )
    def test_docker_not_available(self):
        """测试 Docker 不可用时的错误处理"""
        # 模拟 Docker 不可用
        import subprocess
        original_run = subprocess.run

        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(1, 'docker')

        subprocess.run = mock_run

        try:
            with pytest.raises(RuntimeError, match="Docker 不可用"):
                DockerSandbox.execute_in_container("print('test')", {}, timeout=5)
        finally:
            subprocess.run = original_run


class TestExecuteStrategySafely:
    """测试便捷函数"""

    def test_execute_with_sandbox(self):
        """测试使用沙箱执行"""
        code = '''
import backtrader as bt

class TestStrategy(bt.Strategy):
    params = (('period', 10),)
    
    def __init__(self):
        self.sma = bt.indicators.SMA(period=self.p.period)
    
    def next(self):
        pass
'''

        strategy_class = execute_strategy_safely(code, use_docker=False)

        assert issubclass(strategy_class, bt.Strategy)

    def test_execute_with_docker_flag(self):
        """测试使用 Docker 标志"""
        code = '''
import backtrader as bt

class TestStrategy(bt.Strategy):
    params = (('period', 10),)
    
    def __init__(self):
        self.sma = bt.indicators.SMA(period=self.p.period)
    
    def next(self):
        pass
'''

        # 测试 Docker 模式（会被跳过如果 Docker 不可用）
        try:
            import subprocess
            subprocess.run(['docker', '--version'], check=True, capture_output=True)
            docker_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            docker_available = False

        if docker_available:
            with pytest.raises(NotImplementedError):
                execute_strategy_safely(code, use_docker=True)
