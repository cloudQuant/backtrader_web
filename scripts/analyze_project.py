#!/usr/bin/env python3
"""项目分析脚本 - 识别改进优化点"""
import os
import re
import subprocess
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent

def count_lines_in_file(filepath):
    """统计文件行数"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except:
        return 0

def find_large_files(directory, extension, threshold=300):
    """查找大文件"""
    large_files = []
    for root, dirs, files in os.walk(directory):
        # 排除 node_modules, __pycache__, .git 等
        dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', '.git', '.ruff_cache', 'htmlcov', '.benchmarks']]
        for f in files:
            if f.endswith(extension):
                filepath = Path(root) / f
                lines = count_lines_in_file(filepath)
                if lines > threshold:
                    large_files.append((str(filepath.relative_to(PROJECT_ROOT)), lines))
    return sorted(large_files, key=lambda x: -x[1])

def count_exception_handling(directory):
    """统计异常处理模式"""
    patterns = {
        'broad_exception': r'except\s+Exception\s*:',
        'bare_except': r'except\s*:',
        'specific_exception': r'except\s+\([^)]+\)\s*:',
    }
    counts = defaultdict(int)
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', '.git', '.ruff_cache', 'htmlcov', '.benchmarks']]
        for f in files:
            if f.endswith('.py'):
                filepath = Path(root) / f
                try:
                    with open(filepath, 'r', encoding='utf-8') as file:
                        content = file.read()
                        for name, pattern in patterns.items():
                            matches = re.findall(pattern, content)
                            counts[name] += len(matches)
                except:
                    pass
    return counts

def count_type_ignore(directory):
    """统计 type: ignore 注释"""
    count = 0
    files_with_ignore = []
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', '.git', '.ruff_cache', 'htmlcov', '.benchmarks']]
        for f in files:
            if f.endswith('.py'):
                filepath = Path(root) / f
                try:
                    with open(filepath, 'r', encoding='utf-8') as file:
                        content = file.read()
                        ignores = len(re.findall(r'#\s*type:\s*ignore', content))
                        if ignores > 0:
                            count += ignores
                            files_with_ignore.append((str(filepath.relative_to(PROJECT_ROOT)), ignores))
                except:
                    pass
    return count, sorted(files_with_ignore, key=lambda x: -x[1])[:10]

def count_any_types(directory):
    """统计 Any 类型使用"""
    count = 0
    files_with_any = []
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', '.git', '.ruff_cache', 'htmlcov', '.benchmarks']]
        for f in files:
            if f.endswith('.py'):
                filepath = Path(root) / f
                try:
                    with open(filepath, 'r', encoding='utf-8') as file:
                        content = file.read()
                        # 匹配 from typing import ... Any ... 或 : Any 或 -> Any
                        any_matches = re.findall(r'\bAny\b', content)
                        if any_matches:
                            count += len(any_matches)
                            files_with_any.append((str(filepath.relative_to(PROJECT_ROOT)), len(any_matches)))
                except:
                    pass
    return count, sorted(files_with_any, key=lambda x: -x[1])[:10]

def count_pass_statements(directory):
    """统计 pass 语句"""
    count = 0
    files_with_pass = []
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', '.git', '.ruff_cache', 'htmlcov', '.benchmarks']]
        for f in files:
            if f.endswith('.py') and 'test' not in f:  # 排除测试文件
                filepath = Path(root) / f
                try:
                    with open(filepath, 'r', encoding='utf-8') as file:
                        content = file.read()
                        passes = len(re.findall(r'^\s*pass\s*$', content, re.MULTILINE))
                        if passes > 0:
                            count += passes
                            files_with_pass.append((str(filepath.relative_to(PROJECT_ROOT)), passes))
                except:
                    pass
    return count, sorted(files_with_pass, key=lambda x: -x[1])[:10]

def check_test_coverage():
    """检查测试覆盖率"""
    backend_dir = PROJECT_ROOT / 'src' / 'backend'
    tests_dir = backend_dir / 'tests'
    app_dir = backend_dir / 'app'
    
    # 统计源文件数
    source_files = list(app_dir.rglob('*.py'))
    test_files = list(tests_dir.rglob('*.py'))
    
    return {
        'source_files': len(source_files),
        'test_files': len(test_files),
        'ratio': f"{len(test_files)}/{len(source_files)}"
    }

def check_frontend_issues():
    """检查前端问题"""
    frontend_dir = PROJECT_ROOT / 'src' / 'frontend' / 'src'
    
    issues = {
        'vue_files': 0,
        'ts_files': 0,
        'large_vue_files': [],
        'large_ts_files': [],
    }
    
    # 统计文件数
    issues['vue_files'] = len(list(frontend_dir.rglob('*.vue')))
    issues['ts_files'] = len(list(frontend_dir.rglob('*.ts')))
    
    # 查找大文件
    for f in frontend_dir.rglob('*.vue'):
        lines = count_lines_in_file(f)
        if lines > 300:
            issues['large_vue_files'].append((str(f.relative_to(PROJECT_ROOT)), lines))
    
    for f in frontend_dir.rglob('*.ts'):
        lines = count_lines_in_file(f)
        if lines > 200:
            issues['large_ts_files'].append((str(f.relative_to(PROJECT_ROOT)), lines))
    
    issues['large_vue_files'] = sorted(issues['large_vue_files'], key=lambda x: -x[1])[:5]
    issues['large_ts_files'] = sorted(issues['large_ts_files'], key=lambda x: -x[1])[:5]
    
    return issues

def main():
    print("=" * 60)
    print("项目改进优化分析报告")
    print("=" * 60)
    
    backend_dir = PROJECT_ROOT / 'src' / 'backend' / 'app'
    
    # 1. 大文件分析
    print("\n## 1. 大文件分析 (>300行)")
    print("-" * 40)
    large_py = find_large_files(backend_dir, '.py', 300)
    for f, lines in large_py[:10]:
        print(f"  - {f}: {lines} 行")
    
    # 2. 异常处理分析
    print("\n## 2. 异常处理分析")
    print("-" * 40)
    exception_counts = count_exception_handling(backend_dir)
    print(f"  - 宽泛异常捕获 (except Exception:): {exception_counts['broad_exception']}")
    print(f"  - 裸异常捕获 (except:): {exception_counts['bare_except']}")
    print(f"  - 特定异常捕获: {exception_counts['specific_exception']}")
    
    # 3. 类型安全分析
    print("\n## 3. 类型安全分析")
    print("-" * 40)
    ignore_count, ignore_files = count_type_ignore(backend_dir)
    print(f"  - type:ignore 注释: {ignore_count} 处")
    for f, c in ignore_files[:5]:
        print(f"    - {f}: {c} 处")
    
    any_count, any_files = count_any_types(backend_dir)
    print(f"  - Any 类型使用: {any_count} 处")
    for f, c in any_files[:5]:
        print(f"    - {f}: {c} 处")
    
    # 4. 代码质量分析
    print("\n## 4. 代码质量分析")
    print("-" * 40)
    pass_count, pass_files = count_pass_statements(backend_dir)
    print(f"  - pass 语句 (非测试): {pass_count} 处")
    for f, c in pass_files[:5]:
        print(f"    - {f}: {c} 处")
    
    # 5. 测试覆盖分析
    print("\n## 5. 测试覆盖分析")
    print("-" * 40)
    coverage = check_test_coverage()
    print(f"  - 源文件数: {coverage['source_files']}")
    print(f"  - 测试文件数: {coverage['test_files']}")
    print(f"  - 比例: {coverage['ratio']}")
    
    # 6. 前端分析
    print("\n## 6. 前端分析")
    print("-" * 40)
    frontend = check_frontend_issues()
    print(f"  - Vue 文件数: {frontend['vue_files']}")
    print(f"  - TS 文件数: {frontend['ts_files']}")
    if frontend['large_vue_files']:
        print(f"  - 大型 Vue 文件:")
        for f, lines in frontend['large_vue_files']:
            print(f"    - {f}: {lines} 行")
    
    # 7. 总结
    print("\n## 7. 改进建议汇总")
    print("-" * 40)
    
    recommendations = []
    
    if exception_counts['broad_exception'] > 20:
        recommendations.append(f"P1: 优化宽泛异常捕获 ({exception_counts['broad_exception']}处)")
    
    if any_count > 100:
        recommendations.append(f"P2: 减少Any类型使用 ({any_count}处)")
    
    if ignore_count > 5:
        recommendations.append(f"P2: 清理type:ignore注释 ({ignore_count}处)")
    
    if len(large_py) > 5:
        recommendations.append(f"P2: 重构大文件 ({len(large_py)}个文件>300行)")
    
    if pass_count > 10:
        recommendations.append(f"P3: 清理空pass语句 ({pass_count}处)")
    
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec}")
    
    print("\n" + "=" * 60)

if __name__ == '__main__':
    main()
