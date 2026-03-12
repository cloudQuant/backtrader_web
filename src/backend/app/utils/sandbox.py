"""
Strategy execution sandbox.

Safely executes user strategy code in a restricted environment.
"""

import math
from datetime import datetime
from typing import Any

import backtrader as bt


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
        name: str, globals: dict = None, locals: dict = None, fromlist: list = None, level: int = 0
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

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        pass

    @classmethod
    def execute_strategy_code(cls, code: str, params: dict | None = None) -> type:
        """Safely execute strategy code.

        Args:
            code: Strategy code string.
            params: Strategy parameter dictionary.

        Returns:
            Strategy class (inherits from bt.Strategy).

        Raises:
            ValueError: If the code is invalid or contains unsafe content.
            SyntaxError: If the code has syntax errors.
            RuntimeError: If the code execution fails.
        """
        # Pre-check code to prevent dangerous operations
        cls._check_code_safety(code)

        # Create safe namespace
        safe_globals = cls._create_safe_globals()

        # Add parameters to namespace if provided
        if params:
            safe_globals.update(params)

        try:
            # Compile code
            compiled_code = compile(code, "<strategy>", "exec")

            # Execute code
            exec(compiled_code, safe_globals)

            # Find strategy class
            strategy_class = None
            for name, obj in safe_globals.items():
                # Skip built-in modules and functions
                if name.startswith("_"):
                    continue
                if name in cls._ALLOWED_MODULES:
                    continue

                # Find class that inherits from bt.Strategy
                if isinstance(obj, type):
                    try:
                        # Check if it's a subclass of bt.Strategy
                        if issubclass(obj, bt.Strategy) and obj != bt.Strategy:
                            strategy_class = obj
                            break
                    except TypeError:
                        # issubclass may fail in some cases
                        continue

        except SyntaxError as e:
            raise SyntaxError(f"Strategy code syntax error: {e}")
        except NameError as e:
            raise NameError(f"Undefined name in strategy code: {e}")
        except AttributeError as e:
            raise AttributeError(f"Disallowed attribute in strategy code: {e}")
        except ImportError as e:
            raise ImportError(f"Disallowed module import in strategy code: {e}")
        except ValueError:
            # Re-raise ValueError directly (for "no strategy class found")
            raise
        except Exception as e:
            raise RuntimeError(f"Strategy code execution failed: {type(e).__name__}: {e}")

        # Check for strategy class after exception handling
        if not strategy_class:
            raise ValueError(
                "No valid Strategy class found in strategy code (must inherit from bt.Strategy)"
            )

        return strategy_class

    @classmethod
    def _check_code_safety(cls, code: str) -> None:
        """Check code safety.

        Prevents dangerous operations such as:
        - Importing dangerous modules
        - Executing system commands
        - File operations
        - Network operations

        Args:
            code: The code to check.

        Raises:
            ValueError: If the code contains dangerous operations.
        """
        # List of dangerous modules
        dangerous_modules = [
            "os",
            "sys",
            "subprocess",
            "shutil",
            "pickle",
            "socket",
            "urllib",
            "requests",
            "http",
            "eval",
            "exec",
            "compile",
            "__import__",
            "open",
            "file",
            "input",
            "raw_input",
            "globals",
            "locals",
            "vars",
            "dir",
        ]

        # List of dangerous functions
        dangerous_functions = [
            "eval",
            "exec",
            "compile",
            "open",
            "file",
            "input",
            "raw_input",
        ]

        # Check for dangerous module imports
        for module in dangerous_modules:
            if f"import {module}" in code or f"from {module}" in code:
                raise ValueError(f"Importing dangerous module is not allowed: {module}")

        # Check for dangerous function calls
        for func in dangerous_functions:
            if f"{func}(" in code:
                raise ValueError(f"Using dangerous function is not allowed: {func}")

        # Check for double underscore attribute access (may bypass restrictions)
        if "__" in code:
            # Check if accessing __builtins__
            if "__builtins__" in code:
                raise ValueError("Accessing __builtins__ is not allowed")

        # Check if trying to modify global namespace
        if "globals()[" in code or "locals()[" in code:
            raise ValueError("Using globals() or locals() is not allowed")


class DockerSandbox:
    """Docker container sandbox (optional implementation).

    Uses Docker containers to completely isolate the strategy execution environment.
    Provides the highest level of security but requires Docker support.
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
) -> type:
    """Safely execute strategy code.

    Args:
        code: Strategy code.
        params: Strategy parameters.
        use_docker: Whether to use Docker container isolation (more secure but requires Docker).

    Returns:
        Strategy class.
    """
    if use_docker:
        # Use Docker container isolation
        DockerSandbox.execute_in_container(code, params or {})
        # Assume Docker container returns serialized strategy class
        # Actual implementation requires more complexity
        raise NotImplementedError("Docker sandbox mode requires additional configuration")
    else:
        # Use restricted Python environment
        return StrategySandbox.execute_strategy_code(code, params)
