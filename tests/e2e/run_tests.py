#!/usr/bin/env python3
"""
Playwright E2E 测试运行脚本

使用方法:
1. 确保后端和前端服务已启动
2. 安装依赖: pip install playwright pytest pytest-playwright
3. 安装浏览器: playwright install chromium
4. 运行测试: python run_tests.py

或者直接使用 pytest:
    pytest tests/e2e/ -v --headed  # 显示浏览器
    pytest tests/e2e/ -v           # 无头模式
"""

import subprocess
import sys
import os
import time
import signal


def check_services():
    """检查服务是否运行"""
    import requests
    
    frontend_url = "http://localhost:3000"
    backend_url = "http://localhost:8000/docs"
    
    print("检查服务状态...")
    
    # 检查后端
    try:
        resp = requests.get(backend_url, timeout=5)
        print(f"✓ 后端服务运行中: {backend_url}")
    except:
        print(f"✗ 后端服务未启动: {backend_url}")
        print("  请运行: cd backend && uvicorn app.main:app --reload --port 8000")
        return False
    
    # 检查前端
    try:
        resp = requests.get(frontend_url, timeout=5)
        print(f"✓ 前端服务运行中: {frontend_url}")
    except:
        print(f"✗ 前端服务未启动: {frontend_url}")
        print("  请运行: cd frontend && npm run dev")
        return False
    
    return True


def install_playwright():
    """安装 Playwright 浏览器"""
    print("安装 Playwright 浏览器...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])


def run_tests(headed=False, verbose=True):
    """运行测试"""
    print("\n开始运行 E2E 测试...")
    print("=" * 50)
    
    # 构建 pytest 命令
    cmd = [sys.executable, "-m", "pytest", "tests/e2e/", "-v"]
    
    if headed:
        cmd.append("--headed")
    
    # 运行测试
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    return result.returncode


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Playwright E2E 测试运行器")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--install", action="store_true", help="安装 Playwright 浏览器")
    parser.add_argument("--skip-check", action="store_true", help="跳过服务检查")
    
    args = parser.parse_args()
    
    if args.install:
        install_playwright()
        return 0
    
    if not args.skip_check:
        if not check_services():
            print("\n请先启动后端和前端服务后再运行测试")
            return 1
    
    return run_tests(headed=args.headed)


if __name__ == "__main__":
    sys.exit(main())
