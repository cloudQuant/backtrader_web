"""
策略代码安全执行沙箱

使用受限 Python 环境安全执行用户策略代码
"""
import sys
import types
from typing import Any, Dict, Optional
import backtrader as bt
from datetime import datetime
import math


class StrategySandbox:
    """策略代码安全执行沙箱"""

    # 允许的内置函数和模块白名单
    _ALLOWED_BUILTINS = {
        'abs': abs,
        'all': all,
        'any': any,
        'bool': bool,
        'dict': dict,
        'float': float,
        'int': int,
        'len': len,
        'list': list,
        'max': max,
        'min': min,
        'pow': pow,
        'range': range,
        'round': round,
        'sorted': sorted,
        'str': str,
        'sum': sum,
        'tuple': tuple,
        'zip': zip,
        'enumerate': enumerate,
        'isinstance': isinstance,
        'issubclass': issubclass,
        'type': type,
    }

    # 允许的模块白名单
    _ALLOWED_MODULES = {
        'bt': bt,
        'datetime': datetime,
        'math': math,
    }

    @classmethod
    def _create_safe_globals(cls) -> Dict[str, Any]:
        """
        创建安全的全局命名空间

        只包含白名单中的内置函数和模块
        """
        safe_globals = {
            '__builtins__': cls._ALLOWED_BUILTINS.copy(),
            **cls._ALLOWED_MODULES,
        }

        # 添加安全限制
        safe_globals['__import__'] = cls._safe_import
        safe_globals['__print__'] = cls._safe_print

        return safe_globals

    @staticmethod
    def _safe_import(name: str, globals: Dict = None, locals: Dict = None, fromlist: list = None, level: int = 0):
        """
        安全的 import 函数

        只允许导入白名单中的模块
        """
        # 获取基础模块名（不带子模块）
        module_name = name.split('.')[0]

        # 检查是否在白名单中
        allowed_base_names = StrategySandbox._ALLOWED_MODULES.keys()
        if module_name not in allowed_base_names:
            raise ImportError(f"模块 '{name}' 不被允许导入。仅允许: {', '.join(allowed_base_names)}")

        # 导入模块
        imported_module = __import__(name, globals, locals, fromlist, level)

        # 如果是子模块，也检查
        if '.' in name:
            parts = name.split('.')
            current = imported_module
            for part in parts[1:]:
                try:
                    current = getattr(current, part)
                except AttributeError:
                    raise ImportError(f"无法导入 {name}")

        return imported_module

    @staticmethod
    def _safe_print(*args, **kwargs):
        """
        安全的 print 函数

        禁用 print 防止用户策略输出信息
        """
        pass

    @classmethod
    def execute_strategy_code(cls, code: str, params: Optional[Dict] = None) -> type:
        """
        安全执行策略代码

        Args:
            code: 策略代码字符串
            params: 策略参数字典

        Returns:
            策略类（继承自 bt.Strategy）

        Raises:
            ValueError: 如果代码无效或包含不安全内容
            SyntaxError: 如果代码有语法错误
            RuntimeError: 如果代码执行出错
        """
        # 预先检查代码，防止危险操作
        cls._check_code_safety(code)

        # 创建安全的命名空间
        safe_globals = cls._create_safe_globals()

        # 如果有参数，添加到命名空间
        if params:
            safe_globals.update(params)

        try:
            # 编译代码
            compiled_code = compile(code, '<strategy>', 'exec')

            # 执行代码
            exec(compiled_code, safe_globals)

            # 查找策略类
            strategy_class = None
            for name, obj in safe_globals.items():
                # 跳过内置模块和内置函数
                if name.startswith('_'):
                    continue
                if name in cls._ALLOWED_MODULES:
                    continue

                # 查找继承自 bt.Strategy 的类
                if isinstance(obj, type):
                    try:
                        # 检查是否是 bt.Strategy 的子类
                        if issubclass(obj, bt.Strategy) and obj != bt.Strategy:
                            strategy_class = obj
                            break
                    except TypeError:
                        # issubclass 在某些情况下会失败
                        continue

            if not strategy_class:
                raise ValueError("策略代码中未找到有效的 Strategy 类（必须继承自 bt.Strategy）")

            return strategy_class

        except SyntaxError as e:
            raise SyntaxError(f"策略代码语法错误: {e}")
        except NameError as e:
            raise NameError(f"策略代码中使用了未定义的名称: {e}")
        except AttributeError as e:
            raise AttributeError(f"策略代码中使用了不允许的属性: {e}")
        except ImportError as e:
            raise ImportError(f"策略代码中导入了不允许的模块: {e}")
        except Exception as e:
            raise RuntimeError(f"策略代码执行失败: {type(e).__name__}: {e}")

    @classmethod
    def _check_code_safety(cls, code: str) -> None:
        """
        检查代码安全性

        防止危险操作，如：
        - 导入危险模块
        - 执行系统命令
        - 文件操作
        - 网络操作
        """
        # 危险模块列表
        dangerous_modules = [
            'os', 'sys', 'subprocess', 'shutil', 'pickle',
            'socket', 'urllib', 'requests', 'http',
            'eval', 'exec', 'compile', '__import__',
            'open', 'file', 'input', 'raw_input',
            'globals', 'locals', 'vars', 'dir',
        ]

        # 危险函数列表
        dangerous_functions = [
            'eval', 'exec', 'compile',
            'open', 'file', 'input', 'raw_input',
        ]

        # 检查危险模块导入
        for module in dangerous_modules:
            if f'import {module}' in code or f'from {module}' in code:
                raise ValueError(f"不允许导入危险模块: {module}")

        # 检查危险函数调用
        for func in dangerous_functions:
            if f'{func}(' in code:
                raise ValueError(f"不允许使用危险函数: {func}")

        # 检查双下划线属性访问（可能绕过限制）
        if '__' in code:
            # 检查是否访问 __builtins__
            if '__builtins__' in code:
                raise ValueError("不允许访问 __builtins__")

        # 检查是否尝试修改全局命名空间
        if 'globals()[' in code or 'locals()[' in code:
            raise ValueError("不允许使用 globals() 或 locals()")


class DockerSandbox:
    """
    Docker 容器沙箱（可选实现）

    使用 Docker 容器完全隔离策略执行环境
    提供最高级别的安全性，但需要 Docker 支持
    """

    @staticmethod
    def execute_in_container(
        code: str,
        params: Dict,
        docker_image: str = "backtrader-sandbox:latest",
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        在 Docker 容器中执行策略代码

        Args:
            code: 策略代码
            params: 策略参数
            docker_image: Docker 镜像名称
            timeout: 超时时间（秒）

        Returns:
            执行结果字典

        Raises:
            RuntimeError: 如果 Docker 不可用或执行失败
        """
        import subprocess
        import json
        import tempfile
        import os

        # 检查 Docker 是否可用
        try:
            subprocess.run(['docker', '--version'], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("Docker 不可用，请先安装 Docker")

        # 创建临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            # 写入策略代码
            strategy_file = os.path.join(tmpdir, 'strategy.py')
            with open(strategy_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # 写入参数
            params_file = os.path.join(tmpdir, 'params.json')
            with open(params_file, 'w', encoding='utf-8') as f:
                json.dump(params, f)

            # 在 Docker 容器中执行
            result = subprocess.run([
                'docker', 'run',
                '--rm',  # 执行后删除容器
                '--network=none',  # 无网络访问
                '--cpus=1.0',  # 限制 CPU
                '--memory=512m',  # 限制内存
                '--read-only',  # 只读根文件系统（除了 /tmp）
                '--tmpfs', '/tmp:rw,noexec,nosuid,size=100m',  # 临时文件系统
                '-v', f'{tmpdir}:/data:ro',  # 只读挂载策略和参数
                '-e', f'PYTHONUNBUFFERED=1',  # 不缓冲输出
                docker_image,
                'python', '/data/strategy.py'
            ], capture_output=True, timeout=timeout, text=True)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                raise RuntimeError(f"策略执行失败: {error_msg}")

            # 解析返回结果
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError as e:
                raise RuntimeError(f"无法解析执行结果: {e}")


# 便捷函数
def execute_strategy_safely(
    code: str,
    params: Optional[Dict] = None,
    use_docker: bool = False
) -> type:
    """
    安全执行策略代码

    Args:
        code: 策略代码
        params: 策略参数
        use_docker: 是否使用 Docker 容器隔离（更安全但需要 Docker）

    Returns:
        策略类
    """
    if use_docker:
        # 使用 Docker 容器隔离
        result = DockerSandbox.execute_in_container(code, params or {})
        # 假设 Docker 容器返回序列化的策略类
        # 实际实现需要更复杂
        raise NotImplementedError("Docker 沙箱模式需要额外配置")
    else:
        # 使用受限 Python 环境
        return StrategySandbox.execute_strategy_code(code, params)
