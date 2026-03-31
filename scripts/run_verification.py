#!/usr/bin/env python3
"""
验证脚本 - 运行所有待验证项
包括：前端测试、安全扫描、后端性能测试
"""

import subprocess
import sys
import time
from pathlib import Path


def run_command_with_timeout(cmd: list, cwd: Path, timeout: int = 120, name: str = "") -> tuple[bool, str]:
    """运行命令并设置超时"""
    print(f"\n{'='*50}")
    print(f"运行: {name or ' '.join(cmd)}")
    print(f"目录: {cwd}")
    print(f"超时: {timeout}s")
    print(f"{'='*50}")
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start_time
        
        if result.returncode == 0:
            print(f"✓ 成功 ({duration:.1f}s)")
            if result.stdout:
                # 只打印最后几行
                lines = result.stdout.strip().split('\n')
                if len(lines) > 20:
                    print("... (输出截断)")
                    print('\n'.join(lines[-20:]))
                else:
                    print(result.stdout)
            return True, result.stdout
        else:
            print(f"✗ 失败 (返回码: {result.returncode}, {duration:.1f}s)")
            if result.stderr:
                print(f"错误: {result.stderr[:500]}")
            if result.stdout:
                print(result.stdout[:500])
            return False, result.stderr or result.stdout
            
    except subprocess.TimeoutExpired:
        print(f"✗ 超时 ({timeout}s)")
        return False, f"命令超时 ({timeout}s)"
    except Exception as e:
        print(f"✗ 异常: {e}")
        return False, str(e)


def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    
    results = {}
    
    # 1. 前端测试
    print("\n" + "="*60)
    print("验证项 1: 前端测试 (npm run test)")
    print("="*60)
    
    frontend_dir = project_root / "src" / "frontend"
    if (frontend_dir / "package.json").exists():
        success, output = run_command_with_timeout(
            ["npm", "run", "test", "--", "--run"],
            cwd=frontend_dir,
            timeout=120,
            name="前端单元测试"
        )
        results["前端测试"] = success
    else:
        print("跳过: 前端目录不存在")
        results["前端测试"] = None
    
    # 2. 安全扫描
    print("\n" + "="*60)
    print("验证项 2: 安全扫描")
    print("="*60)
    
    # 2.1 后端依赖扫描
    backend_dir = project_root / "src" / "backend"
    if (backend_dir / "pyproject.toml").exists():
        # 先检查pip-audit是否安装
        check = subprocess.run(["pip-audit", "--version"], capture_output=True)
        if check.returncode != 0:
            print("安装 pip-audit...")
            subprocess.run(["pip", "install", "pip-audit", "-q"])
        
        success, output = run_command_with_timeout(
            ["pip-audit", "--desc"],
            cwd=backend_dir,
            timeout=60,
            name="Python依赖安全扫描"
        )
        results["后端安全扫描"] = success
    else:
        print("跳过: 后端目录不存在")
        results["后端安全扫描"] = None
    
    # 2.2 前端依赖扫描
    if (frontend_dir / "package.json").exists():
        success, output = run_command_with_timeout(
            ["npm", "audit", "--audit-level=high"],
            cwd=frontend_dir,
            timeout=60,
            name="Node依赖安全扫描"
        )
        results["前端安全扫描"] = success
    else:
        results["前端安全扫描"] = None
    
    # 3. 后端性能测试
    print("\n" + "="*60)
    print("验证项 3: 后端性能测试 (pytest -m performance)")
    print("="*60)
    
    if (backend_dir / "tests").exists():
        success, output = run_command_with_timeout(
            ["pytest", "-m", "performance", "-v", "--tb=short"],
            cwd=backend_dir,
            timeout=120,
            name="后端性能测试"
        )
        results["后端性能测试"] = success
    else:
        print("跳过: 后端测试目录不存在")
        results["后端性能测试"] = None
    
    # 汇总结果
    print("\n" + "="*60)
    print("验证结果汇总")
    print("="*60)
    
    all_passed = True
    for name, success in results.items():
        if success is None:
            status = "⊘ 跳过"
        elif success:
            status = "✓ 通过"
        else:
            status = "✗ 失败"
            all_passed = False
        print(f"  {name}: {status}")
    
    print("\n" + "="*60)
    if all_passed:
        print("✓ 所有验证项通过")
        return 0
    else:
        print("✗ 部分验证项失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
