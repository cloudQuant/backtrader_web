#!/usr/bin/env python
"""
运行所有测试的脚本

采用测试驱动开发（TDD）模式，确保所有功能测试通过
"""
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


# 颜色输出
class Colors:
    """ANSI 颜色代码"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

    @classmethod
    def success(cls, msg: str):
        return f"{cls.GREEN}✓ {msg}{cls.RESET}"

    @classmethod
    def warning(cls, msg: str):
        return f"{cls.YELLOW}⚠ {msg}{cls.RESET}"

    @classmethod
    def error(cls, msg: str):
        return f"{cls.RED}✗ {msg}{cls.RESET}"

    @classmethod
    def info(cls, msg: str):
        return f"{cls.BLUE}ℹ {msg}{cls.RESET}"

    @classmethod
    def header(cls, msg: str):
        return f"{cls.BOLD}{msg}{cls.RESET}"


def run_command(
    command: List[str],
    cwd: Path,
    env: dict = None,
    timeout: int = 300
) -> Tuple[int, str, str]:
    """
    运行命令并返回结果

    Args:
        command: 命令列表
        cwd: 工作目录
        env: 环境变量
        timeout: 超时时间（秒）

    Returns:
        (返回码, 标准输出, 标准错误）
    """
    import os
    import shlex

    # 合并环境变量
    env = os.environ.copy()
    if env:
        env.update(env)

    # 打印命令
    print(f"\n{Colors.info('Running:')} {' '.join(shlex.quote(c) for c in command)}")

    # 运行命令
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout)
        returncode = process.returncode
    except subprocess.TimeoutExpired:
        process.kill()
        returncode = -1
        stdout = ""
        stderr = "Command timed out"

    return returncode, stdout, stderr


def run_pytest(
    test_path: Path,
    project_root: Path,
    extra_args: List[str] = None,
    timeout: int = 600
) -> bool:
    """
    运行 pytest

    Args:
        test_path: 测试文件路径
        project_root: 项目根目录
        extra_args: 额外的 pytest 参数
        timeout: 超时时间（秒）

    Returns:
        bool: 是否成功
    """
    cmd = [
        sys.executable, "-m", "pytest",
        "-v",  # 详细输出
        "--tb=short",  # 回溯信息
        "--strict-markers",  # 严格标记
        "--cov=app",  # 覆盖率
        "--cov-report=term-missing",  # 缺失的覆盖率
        "--cov-report=html",  # HTML 覆盖率报告
        "--cov-report=xml",  # XML 覆盖率报告
        "--asyncio-mode=auto",  # 异步模式
        str(test_path),
    ]

    # 添加额外的参数
    if extra_args:
        cmd.extend(extra_args)

    # 运行测试
    returncode, stdout, stderr = run_command(
        cmd,
        cwd=project_root,
        timeout=timeout
    )

    # 检查结果
    if returncode == 0:
        print(Colors.success(f"Tests passed: {test_path}"))
        return True
    else:
        print(Colors.error(f"Tests failed: {test_path}"))
        if stderr:
            print(f"\n{Colors.error('STDERR:')}\n{stderr}")
        return False


def run_all_tests(project_root: Path):
    """
    运行所有测试（TDD 模式）

    按照 TDD 红绿重构模式运行测试：
    1. 单元测试
    2. 集成测试
    3. API 测试
    4. 端到端测试
    """
    backend_dir = project_root / "backend"
    tests_dir = backend_dir / "tests"

    print(f"\n{Colors.header('=' * 70)}")
    print(f"{Colors.header('TDD Test Execution - Backtrader Web')}")
    print(f"{Colors.header('=' * 70)}\n")

    # 测试套件配置
    test_suites = [
        {
            "name": "Security Tests",
            "description": "测试沙箱安全执行和 RBAC 权限控制",
            "tests": [
                "tests/test_sandbox.py",
                "tests/test_rbac.py",
            ],
            "priority": "P0",
            "required": True,
        },
        {
            "name": "Validation Tests",
            "description": "测试增强的输入验证",
            "tests": [
                "tests/test_validation_enhanced.py",
            ],
            "priority": "P0",
            "required": True,
        },
        {
            "name": "Service Tests",
            "description": "测试参数优化和报告导出服务",
            "tests": [
                "tests/test_optimization_service.py",
                "tests/test_report_service.py",
            ],
            "priority": "P1",
            "required": True,
        },
        {
            "name": "WebSocket Tests",
            "description": "测试 WebSocket 实时推送",
            "tests": [
                "tests/test_websocket_manager.py",
            ],
            "priority": "P1",
            "required": True,
        },
        {
            "name": "API Tests",
            "description": "测试增强的 API 端点",
            "tests": [
                "tests/test_api_backtest_enhanced.py",
            ],
            "priority": "P1",
            "required": True,
        },
    ]

    # 运行测试套件
    all_passed = True
    failed_suites = []

    for suite in test_suites:
        print(f"\n{Colors.header(f'{'=' * 70)}')}")
        print(f"{Colors.header(f'  {suite["name"]}')} - {suite["description"]} [{suite["priority"]}]")
        print(f"{Colors.header(f'{'=' * 70)}')}\n")

        suite_passed = True

        for test_file in suite["tests"]:
            test_path = tests_dir / test_file

            # 检查文件是否存在
            if not test_path.exists():
                print(Colors.warning(f"Test file not found: {test_file}"))
                if suite["required"]:
                    suite_passed = False
                    all_passed = False
                continue

            # 运行测试
            success = run_pytest(
                test_path,
                project_root,
                extra_args=["-m", "unit"],  # 标记为单元测试
                timeout=600,  # 10 分钟超时
            )

            if not success:
                suite_passed = False
                all_passed = False
                if suite["required"]:
                    failed_suites.append(suite["name"])

        print(f"\n{Colors.info('Suite Status:')} {'PASSED' if suite_passed else 'FAILED'}")

    # 打印总结
    print(f"\n{Colors.header('=' * 70)}")
    print(f"{Colors.header('  TEST EXECUTION SUMMARY')}")
    print(f"{Colors.header('=' * 70)}\n")

    if all_passed:
        print(Colors.success("✓ ALL TESTS PASSED!"))
        print(Colors.success("  All TDD test suites completed successfully."))
        print("\n" + Colors.info("Next steps:") + """
    1. Review test coverage report: backend/htmlcov/index.html
    2. Run integration tests: pytest -m integration
    3. Run end-to-end tests: pytest -m e2e
    4. Deploy to staging environment
    """)
        return True
    else:
        print(Colors.error("✗ SOME TESTS FAILED!"))
        print(f"\n{Colors.error('Failed suites:')} {', '.join(failed_suites)}\n")
        print(Colors.warning("Required tests failed. Please fix before proceeding.") + """
    
    TDD Red-Green-Refactor Cycle:
    ---------------------------------
    1. 🔴 RED: Write failing test (already done)
    2. 🟢 GREEN: Make tests pass (current step)
    3. 🔵 BLUE: Refactor code (improve without breaking)
    4. 🟢 GREEN: Run tests again
    5. Repeat...
    """)
        return False


def check_coverage(project_root: Path, min_coverage: float = 80.0):
    """
    检查测试覆盖率

    Args:
        project_root: 项目根目录
        min_coverage: 最小覆盖率（百分比）

    Returns:
        bool: 是否达到最小覆盖率
    """
    print(f"\n{Colors.header('=' * 70)}")
    print(f"{Colors.header('  CHECKING TEST COVERAGE')}")
    print(f"{Colors.header('=' * 70)}\n")

    # 运行覆盖率检查
    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=app",
        "--cov-report=term-missing",
        "--cov-fail-under", str(min_coverage),
        "tests/",
    ]

    returncode, stdout, stderr = run_command(
        cmd,
        cwd=project_root / "backend",
        timeout=600
    )

    # 解析覆盖率结果
    if returncode == 0:
        print(Colors.success(f"✓ Coverage {min_coverage}%+ achieved!"))
        return True
    else:
        print(Colors.error(f"✗ Coverage below {min_coverage}%"))
        if "coverage" in stderr.lower():
            print(Colors.error(stderr))
        return False


def main():
    """主函数"""
    import os

    # 项目根目录
    project_root = Path(__file__).resolve().parent

    # 检查虚拟环境
    venv_python = project_root / "venv" / "bin" / "python"
    if venv_python.exists():
        sys.executable = str(venv_python)
        print(Colors.info(f"Using virtual environment: {venv_python}"))
    else:
        print(Colors.warning("No virtual environment found, using system Python"))

    # 设置环境变量
    env = {
        "PYTHONPATH": str(project_root / "backend"),
        "PYTHONDONTWRITEBYTECODE": "1",  # Python 3.8+
    }

    # 运行所有测试
    all_passed = run_all_tests(project_root)

    # 如果所有测试通过，检查覆盖率
    if all_passed:
        print(Colors.info("\nAll tests passed! Checking coverage...\n"))
        coverage_ok = check_coverage(project_root, min_coverage=80.0)

        if coverage_ok:
            print(Colors.success("\n" + "=" * 70))
            print(Colors.success("  ✓ TDD COMPLETE! ALL TESTS PASSED AND COVERAGE OK!"))
            print(Colors.success("=" * 70))
            sys.exit(0)
        else:
            print(Colors.warning("\n" + "=" * 70))
            print(Colors.warning("  ⚠ COVERAGE BELOW TARGET - PLEASE IMPROVE TESTS"))
            print(Colors.warning("=" * 70))
            sys.exit(1)
    else:
        print(Colors.error("\n" + "=" * 70))
        print(Colors.error("  ✗ TDD FAILED - SOME TESTS FAILED"))
        print(Colors.error("=" * 70))
        sys.exit(1)


if __name__ == "__main__":
    main()
