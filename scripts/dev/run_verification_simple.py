#!/usr/bin/env python3
"""
简化验证脚本 - 分别运行各项验证
"""

import subprocess
import sys
import time
from pathlib import Path


def run_cmd(cmd: list, cwd: Path, timeout: int = 60) -> tuple[bool, str]:
    """运行命令"""
    print(f"\n{'='*50}")
    print(f"运行: {' '.join(cmd)}")
    print(f"目录: {cwd}")
    
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        duration = time.time() - start if 'start' in dir() else 0
        
        if result.returncode == 0:
            print(f"✓ 成功")
            return True, result.stdout
        else:
            print(f"✗ 失败 (返回码: {result.returncode})")
            if result.stderr:
                print(result.stderr[:1000])
            return False, result.stderr
            
    except subprocess.TimeoutExpired:
        print(f"✗ 超时 ({timeout}s)")
        return False, "timeout"
    except Exception as e:
        print(f"✗ 异常: {e}")
        return False, str(e)


def main():
    project_root = Path(__file__).parent.parent
    results = {}
    
    # 1. 后端性能测试
    print("\n" + "="*60)
    print("验证项 1: 后端性能测试")
    print("="*60)
    
    backend_dir = project_root / "src" / "backend"
    success, _ = run_cmd(
        ["pytest", "-m", "performance", "-v", "--tb=short", "-x"],
        cwd=backend_dir,
        timeout=60
    )
    results["后端性能测试"] = success
    
    # 2. 前端测试 (只运行新增的测试文件)
    print("\n" + "="*60)
    print("验证项 2: 前端测试 (新增组件)")
    print("="*60)
    
    frontend_dir = project_root / "src" / "frontend"
    # 运行新增的两个测试文件
    success, _ = run_cmd(
        ["npm", "run", "test", "--", "--run", 
         "src/views/__tests__/LiveTradingPage.spec.ts",
         "src/views/__tests__/OptimizationPage.spec.ts"],
        cwd=frontend_dir,
        timeout=60
    )
    results["前端测试"] = success
    
    # 汇总
    print("\n" + "="*60)
    print("验证结果汇总")
    print("="*60)
    
    for name, success in results.items():
        status = "✓ 通过" if success else "✗ 失败"
        print(f"  {name}: {status}")
    
    all_passed = all(results.values())
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
