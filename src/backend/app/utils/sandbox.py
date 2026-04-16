"""
Strategy execution sandbox.

Safely executes user strategy code in a restricted environment.
"""

import ast
import math
import signal
import threading
from datetime import datetime
from typing import Any

import backtrader as bt


class _SandboxTimeoutError(Exception):
    """Raised when strategy code execution exceeds the time limit."""


class StrategySandbox:
    """Strategy code secure execution sandbox.

    Attributes:
        _ALLOWED_BUILTINS: Whitelist of allowed built-in functions.
        _ALLOWED_MODULES: Whitelist of allowed modules.
    """

    # Whitelist of allowed built-in functions and modules
    _ALLOWED_BUILTINS = {
        "__build_class__": __build_class__,
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "pow": pow,
        "range": range,
        "round": round,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
        "enumerate": enumerate,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "type": type,
    }

    # Whitelist of allowed modules
    _ALLOWED_MODULES = {
        "bt": bt,
        "datetime": datetime,
        "math": math,
    }

    @classmethod
    def _create_safe_globals(cls) -> dict[str, Any]:
        """Create a safe global namespace.

        Only includes whitelisted built-in functions and modules.

        Returns:
            A dictionary of safe global variables.
        """
        # Use existing module names to avoid errors when backtrader searches sys.modules
        safe_globals = {
            "__builtins__": cls._ALLOWED_BUILTINS.copy(),
            "__name__": "app.utils.sandbox",
            "__doc__": None,
            "__package__": "app.utils",
            "__loader__": None,
            "__spec__": None,
            **cls._ALLOWED_MODULES,
        }

        # Add security restrictions
        safe_globals["__import__"] = cls._safe_import
        safe_globals["__print__"] = cls._safe_print

        return safe_globals

    @staticmethod
    def _safe_import(
        name: str,
        globals: dict | None = None,
        locals: dict | None = None,
        fromlist: list | None = None,
        level: int = 0,
    ):
        """Safe import function.

        Only allows importing whitelisted modules.

        Args:
            name: Module name to import.
            globals: Global namespace (unused).
            locals: Local namespace (unused).
            fromlist: List of names to import (unused).
            level: Import level (unused).

        Returns:
            The imported module.

        Raises:
            ImportError: If the module is not whitelisted.
        """
        # Get base module name (without submodules)
        module_name = name.split(".")[0]

        # Check whether the base module is explicitly allowed.
        allowed_base_names = StrategySandbox._ALLOWED_MODULES.keys()
        if module_name not in allowed_base_names:
            raise ImportError(
                f"Module '{name}' is not allowed. Only: {', '.join(allowed_base_names)}"
            )

        # Only allow modules that are pre-imported and explicitly whitelisted.
        imported_module = StrategySandbox._ALLOWED_MODULES[module_name]

        # If it's a submodule, also check
        if "." in name:
            parts = name.split(".")
            current = imported_module
            for part in parts[1:]:
                try:
                    current = getattr(current, part)
                except AttributeError:
                    raise ImportError(f"Cannot import {name}")

        return imported_module

    @staticmethod
    def _safe_print(*args, **kwargs):
        """Safe print function.

        Disables print to prevent user strategy output.
        Intentionally does nothing - user strategy print calls are silently ignored.

        Args:
            *args: Variable length argument list (ignored).
            **kwargs: Arbitrary keyword arguments (ignored).
        """
        pass

    @classmethod
    def execute_strategy_code(
        cls, code: str, params: dict | None = None, timeout: int | None = None
    ) -> type:
        """Safely execute strategy code.

        Args:
            code: Strategy code string.
            params: Strategy parameter dictionary.
            timeout: Maximum execution time in seconds. Defaults to _EXECUTION_TIMEOUT.

        Returns:
            Strategy class (inherits from bt.Strategy).

        Raises:
            ValueError: If the code is invalid or contains unsafe content.
            SyntaxError: If the code has syntax errors.
            RuntimeError: If the code execution fails or times out.
        """
        execution_timeout = timeout if timeout is not None else cls._EXECUTION_TIMEOUT

        # Pre-check code to prevent dangerous operations (AST-based)
        cls._check_code_safety(code)

        # Create safe namespace
        safe_globals = cls._create_safe_globals()

        # Add parameters to namespace if provided
        if params:
            safe_globals.update(params)

        try:
            # Compile code
            compiled_code = compile(code, "<strategy>", "exec")

            # Execute with timeout enforcement
            cls._exec_with_timeout(compiled_code, safe_globals, execution_timeout)

            # Find strategy class
            strategy_class = cls._find_strategy_class(safe_globals)

        except _SandboxTimeoutError:
            raise RuntimeError(
                f"Strategy code execution timed out after {execution_timeout} seconds"
            )
        except SyntaxError as e:
            raise SyntaxError(f"Strategy code syntax error: {e}")
        except NameError as e:
            raise NameError(f"Undefined name in strategy code: {e}")
        except AttributeError as e:
            raise AttributeError(f"Disallowed attribute in strategy code: {e}")
        except ImportError as e:
            raise ImportError(f"Disallowed module import in strategy code: {e}")
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Strategy code execution failed: {type(e).__name__}: {e}")

        if not strategy_class:
            raise ValueError(
                "No valid Strategy class found in strategy code (must inherit from bt.Strategy)"
            )

        return strategy_class

    @classmethod
    def _exec_with_timeout(cls, compiled_code: Any, safe_globals: dict, timeout: int) -> None:
        """Execute compiled code with a timeout.

        Uses signal.alarm on Unix and threading.Timer as fallback.

        Args:
            compiled_code: The compiled code object.
            safe_globals: The safe global namespace.
            timeout: Timeout in seconds.

        Raises:
            _SandboxTimeoutError: If execution exceeds timeout.
        """
        if hasattr(signal, "SIGALRM"):
            # Unix: use signal-based timeout (works within the same thread)
            def _timeout_handler(signum, frame):
                raise _SandboxTimeoutError()

            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
            try:
                exec(compiled_code, safe_globals)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Fallback: use threading (less reliable but cross-platform)
            error: list[Exception] = []

            def _run():
                try:
                    exec(compiled_code, safe_globals)
                except Exception as e:
                    error.append(e)

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=timeout)
            if t.is_alive():
                raise _SandboxTimeoutError()
            if error:
                raise error[0]

    @classmethod
    def _find_strategy_class(cls, safe_globals: dict) -> type | None:
        """Find the bt.Strategy subclass in the executed globals.

        Args:
            safe_globals: The global namespace after code execution.

        Returns:
            The strategy class, or None if not found.
        """
        for name, obj in safe_globals.items():
            if name.startswith("_"):
                continue
            if name in cls._ALLOWED_MODULES:
                continue
            if isinstance(obj, type):
                try:
                    if issubclass(obj, bt.Strategy) and obj != bt.Strategy:
                        return obj
                except TypeError:
                    continue
        return None

    # Dangerous modules that must never be imported
    _DANGEROUS_MODULES = frozenset(
        {
            "os",
            "sys",
            "subprocess",
            "shutil",
            "pickle",
            "socket",
            "urllib",
            "requests",
            "http",
            "ctypes",
            "multiprocessing",
            "signal",
            "importlib",
            "pathlib",
            "io",
            "builtins",
            "code",
            "codeop",
            "compileall",
            "py_compile",
        }
    )

    # Dangerous function names that must never be called
    _DANGEROUS_CALLS = frozenset(
        {
            "eval",
            "exec",
            "compile",
            "open",
            "input",
            "raw_input",
            "__import__",
            "breakpoint",
            "exit",
            "quit",
        }
    )

    # Dangerous dunder attributes (legitimate ones like __init__ are allowed)
    _DANGEROUS_ATTRS = frozenset(
        {
            "__builtins__",
            "__subclasses__",
            "__bases__",
            "__mro__",
            "__globals__",
            "__code__",
            "__closure__",
            "__func__",
            "__self__",
            "__module__",
            "__dict__",
            "__class__",
            "__import__",
            "__loader__",
            "__spec__",
        }
    )

    # Default execution timeout in seconds
    _EXECUTION_TIMEOUT = 30

    @classmethod
    def _check_code_safety(cls, code: str) -> None:
        """Check code safety using AST analysis.

        Parses the code into an abstract syntax tree and walks every node
        to detect dangerous operations such as:
        - Importing disallowed modules (including via importlib)
        - Calling dangerous built-in functions
        - Accessing restricted dunder attributes
        - Using globals()/locals()/vars() to escape the sandbox

        Args:
            code: The code to check.

        Raises:
            ValueError: If the code contains dangerous operations.
            SyntaxError: If the code cannot be parsed.
        """
        try:
            tree = ast.parse(code, filename="<strategy>")
        except SyntaxError:
            raise  # Let SyntaxError propagate with its original message

        for node in ast.walk(tree):
            cls._check_node(node)

    @classmethod
    def _check_node(cls, node: ast.AST) -> None:
        """Check a single AST node for safety violations.

        Args:
            node: The AST node to check.

        Raises:
            ValueError: If the node represents a dangerous operation.
        """
        # Check import statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in cls._DANGEROUS_MODULES:
                    raise ValueError(f"Importing module '{alias.name}' is not allowed")

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base = node.module.split(".")[0]
                if base in cls._DANGEROUS_MODULES:
                    raise ValueError(f"Importing from module '{node.module}' is not allowed")

        # Check Name nodes for dangerous dunder names (e.g., bare __builtins__)
        elif isinstance(node, ast.Name):
            if node.id in cls._DANGEROUS_ATTRS:
                raise ValueError(f"Accessing attribute '{node.id}' is not allowed")

        # Check function calls
        elif isinstance(node, ast.Call):
            func_name = cls._get_call_name(node)
            if func_name in cls._DANGEROUS_CALLS:
                raise ValueError(f"Calling function '{func_name}' is not allowed")
            # Block globals(), locals(), vars() calls
            if func_name in ("globals", "locals", "vars", "dir"):
                raise ValueError(f"Calling '{func_name}()' is not allowed")
            # Block getattr/setattr/delattr with dangerous attr names
            if func_name in ("getattr", "setattr", "delattr") and len(node.args) >= 2:
                if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                    attr = node.args[1].value
                    if attr in cls._DANGEROUS_ATTRS:
                        raise ValueError(
                            f"Accessing attribute '{attr}' via {func_name}() is not allowed"
                        )

        # Check attribute access for dangerous dunder names
        elif isinstance(node, ast.Attribute):
            if node.attr in cls._DANGEROUS_ATTRS:
                raise ValueError(f"Accessing attribute '{node.attr}' is not allowed")

        # Check subscript access on globals()/locals()
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Call):
                name = cls._get_call_name(node.value)
                if name in ("globals", "locals", "vars"):
                    raise ValueError(f"Subscript access on '{name}()' is not allowed")

    @staticmethod
    def _get_call_name(node: ast.Call) -> str:
        """Extract the function name from a Call AST node.

        Args:
            node: The Call AST node.

        Returns:
            The function name, or empty string if not extractable.
        """
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""


class DockerSandbox:
    """Docker container sandbox for strategy execution.

    Uses Docker containers to completely isolate the strategy execution environment.
    Provides the highest level of security but requires Docker support.

    Implementation Status:
        - Core execution logic: Implemented
        - Resource limits: Implemented (CPU, memory, network isolation)
        - Security features: Implemented (read-only filesystem, noexec tmpfs)

    Requirements:
        - Docker must be installed and running
        - Docker image `backtrader-sandbox:latest` must be built or pulled
          (see project documentation for building the image)

    Note: This is an optional feature. The StrategySandbox class provides a
    simpler in-process sandbox that works without external dependencies.
    DockerSandbox is intended for production environments requiring stronger
    isolation where the overhead of container management is acceptable.

    Security Features:
        - No network access (--network=none)
        - CPU limit: 1 core (--cpus=1.0)
        - Memory limit: 512MB (--memory=512m)
        - Read-only root filesystem (--read-only)
        - No-exec temporary filesystem (--tmpfs /tmp:rw,noexec,nosuid,size=100m)
        - Read-only strategy mount
    """

    @staticmethod
    def execute_in_container(
        code: str, params: dict, docker_image: str = "backtrader-sandbox:latest", timeout: int = 300
    ) -> dict[str, Any]:
        """Execute strategy code in a Docker container.

        Args:
            code: Strategy code.
            params: Strategy parameters.
            docker_image: Docker image name.
            timeout: Timeout in seconds.

        Returns:
            Execution result dictionary.

        Raises:
            RuntimeError: If Docker is not available or execution fails.
        """
        import json
        import os
        import subprocess
        import tempfile

        # Check if Docker is available
        try:
            subprocess.run(["docker", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("Docker is not available, please install Docker first")

        # Create temporary directory
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write strategy code
            strategy_file = os.path.join(tmpdir, "strategy.py")
            with open(strategy_file, "w", encoding="utf-8") as f:
                f.write(code)

            # Write parameters
            params_file = os.path.join(tmpdir, "params.json")
            with open(params_file, "w", encoding="utf-8") as f:
                json.dump(params, f)

            # Execute in Docker container
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",  # Remove container after execution
                    "--network=none",  # No network access
                    "--cpus=1.0",  # Limit CPU
                    "--memory=512m",  # Limit memory
                    "--read-only",  # Read-only root filesystem (except /tmp)
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,size=100m",  # Temporary filesystem
                    "-v",
                    f"{tmpdir}:/data:ro",  # Read-only mount for strategy and params
                    "-e",
                    "PYTHONUNBUFFERED=1",  # Unbuffered output
                    docker_image,
                    "python",
                    "/data/strategy.py",
                ],
                capture_output=True,
                timeout=timeout,
                text=True,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                raise RuntimeError(f"Strategy execution failed: {error_msg}")

            # Parse return result
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Cannot parse execution result: {e}")


# Convenience function
def execute_strategy_safely(
    code: str, params: dict | None = None, use_docker: bool = False
) -> type | dict[str, Any]:
    """Safely execute strategy code.

    Args:
        code: Strategy code.
        params: Strategy parameters.
        use_docker: Whether to use Docker container isolation (more secure but requires Docker).

    Returns:
        Strategy class (non-Docker mode) or execution result dict (Docker mode).

    Raises:
        RuntimeError: If Docker mode is requested but Docker is not available.
    """
    if use_docker:
        # Use Docker container isolation
        # Note: Docker mode returns execution result dict, not strategy class
        return DockerSandbox.execute_in_container(code, params or {})
    else:
        # Use restricted Python environment
        return StrategySandbox.execute_strategy_code(code, params)
