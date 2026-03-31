#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目诊断脚本 - 分析代码质量和可改进之处"""

import os
import re
import subprocess
import sys
from pathlib import Path
from collections import defaultdict

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = PROJECT_ROOT / "src" / "backend"
FRONTEND_DIR = PROJECT_ROOT / "src" / "frontend"


def run_command(cmd, cwd=None, timeout=60):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd or PROJECT_ROOT,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"


def check_ruff():
    """检查 Ruff lint 状态"""
    print("\n" + "=" * 60)
    print("1. RUFF LINT 检查")
    print("=" * 60)
    
    ret, stdout, stderr = run_command("ruff check app/ --output-format=concise", cwd=BACKEND_DIR)
    
    if ret == 0:
        print("✅ Ruff 检查通过，无错误")
        return []
    
    errors = stdout.strip().split('\n') if stdout.strip() else []
    error_counts = defaultdict(int)
    
    for line in errors[:50]:  # 显示前50个
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 4:
                error_code = parts[-1].strip().split()[0] if parts[-1].strip() else "unknown"
                error_counts[error_code] += 1
    
    print(f"❌ 发现 {len(errors)} 个 Ruff 错误")
    for code, count in sorted(error_counts.items(), key=lambda x: -x[1]):
        print(f"  - {code}: {count} 处")
    
    return errors[:20]  # 返回前20个错误


def check_typescript():
    """检查 TypeScript 状态"""
    print("\n" + "=" * 60)
    print("2. TYPESCRIPT 类型检查")
    print("=" * 60)
    
    ret, stdout, stderr = run_command("npx vue-tsc --noEmit 2>&1 | head -50", cwd=FRONTEND_DIR, timeout=120)
    
    if ret == 0 or "error TS" not in stdout:
        print("✅ TypeScript 检查通过")
        return []
    
    errors = [line for line in stdout.split('\n') if 'error TS' in line]
    print(f"❌ 发现 {len(errors)} 个 TypeScript 错误")
    for err in errors[:10]:
        print(f"  - {err[:100]}")
    
    return errors[:10]


def check_tests():
    """检查测试覆盖率"""
    print("\n" + "=" * 60)
    print("3. 测试覆盖率分析")
    print("=" * 60)
    
    # 运行测试并获取覆盖率
    ret, stdout, stderr = run_command(
        "python -m pytest tests/ -q --tb=no --co 2>/dev/null | wc -l",
        cwd=BACKEND_DIR,
        timeout=30
    )
    
    # 检查低覆盖率文件
    coverage_file = BACKEND_DIR / ".coverage"
    if coverage_file.exists():
        ret, stdout, stderr = run_command(
            "python -m coverage report --skip-covered 2>/dev/null | head -30",
            cwd=BACKEND_DIR,
            timeout=30
        )
        if stdout:
            print("低覆盖率模块:")
            for line in stdout.split('\n')[2:]:  # 跳过表头
                if line.strip() and '%' in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        coverage = parts[-1]
                        try:
                            cov_val = int(coverage.replace('%', ''))
                            if cov_val < 50:
                                print(f"  - {parts[0]}: {coverage}")
                        except ValueError:
                            pass
    else:
        print("⚠️ 未找到覆盖率数据，运行快速测试统计...")
        ret, stdout, stderr = run_command(
            "python -m pytest tests/ -q --tb=no 2>&1 | tail -5",
            cwd=BACKEND_DIR,
            timeout=120
        )
        print(stdout)


def find_todos():
    """查找代码中的 TODO/FIXME 注释"""
    print("\n" + "=" * 60)
    print("4. TODO/FIXME 注释分析")
    print("=" * 60)
    
    todos = []
    patterns = [
        (r'#\s*TODO[:\s]*(.+)', 'TODO'),
        (r'#\s*FIXME[:\s]*(.+)', 'FIXME'),
        (r'//\s*TODO[:\s]*(.+)', 'TODO'),
        (r'//\s*FIXME[:\s]*(.+)', 'FIXME'),
    ]
    
    for ext in ['*.py', '*.ts', '*.vue']:
        for file_path in BACKEND_DIR.rglob(ext) if ext.endswith('.py') else FRONTEND_DIR.rglob(ext):
            if 'node_modules' in str(file_path) or '__pycache__' in str(file_path):
                continue
            try:
                content = file_path.read_text(encoding='utf-8')
                for line_num, line in enumerate(content.split('\n'), 1):
                    for pattern, tag in patterns:
                        match = re.search(pattern, line, re.IGNORECASE)
                        if match:
                            todos.append({
                                'file': str(file_path.relative_to(PROJECT_ROOT)),
                                'line': line_num,
                                'tag': tag,
                                'text': match.group(1).strip()[:50]
                            })
            except Exception:
                pass
    
    if todos:
        print(f"发现 {len(todos)} 处 TODO/FIXME:")
        for todo in todos[:20]:
            print(f"  - [{todo['tag']}] {todo['file']}:{todo['line']} - {todo['text']}")
    else:
        print("✅ 无遗留 TODO/FIXME")
    
    return todos


def check_security():
    """检查安全问题"""
    print("\n" + "=" * 60)
    print("5. 安全扫描 (Bandit)")
    print("=" * 60)
    
    ret, stdout, stderr = run_command("bandit -r app/ -q 2>&1 | head -30", cwd=BACKEND_DIR, timeout=60)
    
    if ret == 0 or "No issues identified" in stdout:
        print("✅ 无安全问题")
        return []
    
    issues = []
    for line in stdout.split('\n'):
        if 'Issue:' in line or 'Test ID:' in line:
            issues.append(line)
    
    if issues:
        print(f"⚠️ 发现 {len(issues)} 个安全告警:")
        for issue in issues[:10]:
            print(f"  - {issue[:100]}")
    else:
        print(stdout[:500] if stdout else "无输出")
    
    return issues


def check_dependencies():
    """检查依赖更新"""
    print("\n" + "=" * 60)
    print("6. 依赖分析")
    print("=" * 60)
    
    # Python 依赖
    pyproject = BACKEND_DIR / "pyproject.toml"
    if pyproject.exists():
        ret, stdout, stderr = run_command(
            "pip list --outdated 2>/dev/null | head -20",
            cwd=BACKEND_DIR,
            timeout=30
        )
        if stdout and "Package" in stdout:
            lines = stdout.strip().split('\n')[2:]  # 跳过表头
            if lines:
                print("Python 依赖更新:")
                for line in lines[:10]:
                    print(f"  - {line}")
            else:
                print("✅ Python 依赖均为最新")
    
    # Node 依赖
    package_json = FRONTEND_DIR / "package.json"
    if package_json.exists():
        ret, stdout, stderr = run_command(
            "npm outdated 2>/dev/null | head -20",
            cwd=FRONTEND_DIR,
            timeout=60
        )
        if stdout.strip():
            print("Node 依赖更新:")
            for line in stdout.strip().split('\n')[:10]:
                print(f"  - {line}")
        else:
            print("✅ Node 依赖均为最新")


def check_code_patterns():
    """检查代码模式问题"""
    print("\n" + "=" * 60)
    print("7. 代码模式分析")
    print("=" * 60)
    
    issues = []
    
    # 检查宽泛异常捕获
    except_count = 0
    for file_path in BACKEND_DIR.rglob('*.py'):
        if '__pycache__' in str(file_path):
            continue
        try:
            content = file_path.read_text(encoding='utf-8')
            count = len(re.findall(r'except\s+Exception\s*:', content))
            if count > 0:
                except_count += count
                if count >= 3:
                    issues.append(f"高频 except Exception: {file_path.relative_to(PROJECT_ROOT)} ({count}处)")
        except Exception:
            pass
    
    print(f"宽泛异常捕获 (except Exception): {except_count} 处")
    
    # 检查 Any 类型使用
    any_count = 0
    for file_path in BACKEND_DIR.rglob('*.py'):
        if '__pycache__' in str(file_path):
            continue
        try:
            content = file_path.read_text(encoding='utf-8')
            count = len(re.findall(r':\s*Any\b', content))
            if count > 0:
                any_count += count
                if count >= 3:
                    issues.append(f"高频 Any 类型: {file_path.relative_to(PROJECT_ROOT)} ({count}处)")
        except Exception:
            pass
    
    print(f"Any 类型使用: {any_count} 处")
    
    # 检查 console.log
    console_count = 0
    for file_path in FRONTEND_DIR.rglob('*.ts'):
        if 'node_modules' in str(file_path) or '.test.' in str(file_path):
            continue
        try:
            content = file_path.read_text(encoding='utf-8')
            count = len(re.findall(r'console\.(log|error|warn)\s*\(', content))
            if count > 0:
                console_count += count
                if count >= 2:
                    issues.append(f"console 输出: {file_path.relative_to(PROJECT_ROOT)} ({count}处)")
        except Exception:
            pass
    
    print(f"前端 console 输出: {console_count} 处")
    
    # 检查硬编码配置
    hardcoded = []
    for file_path in BACKEND_DIR.rglob('*.py'):
        if '__pycache__' in str(file_path) or 'test' in str(file_path):
            continue
        try:
            content = file_path.read_text(encoding='utf-8')
            # 检查硬编码 IP
            if re.search(r'["\']0\.0\.0\.0["\']', content) and 'config' not in str(file_path).lower():
                hardcoded.append(f"硬编码 0.0.0.0: {file_path.relative_to(PROJECT_ROOT)}")
            # 检查硬编码端口
            if re.search(r'["\':]\s*8000["\']', content) and 'config' not in str(file_path).lower():
                hardcoded.append(f"硬编码端口: {file_path.relative_to(PROJECT_ROOT)}")
        except Exception:
            pass
    
    if hardcoded:
        print(f"\n硬编码配置问题:")
        for h in hardcoded[:10]:
            print(f"  - {h}")
    
    return issues


def check_documentation():
    """检查文档完整性"""
    print("\n" + "=" * 60)
    print("8. 文档完整性检查")
    print("=" * 60)
    
    issues = []
    
    # 检查 API 文档
    api_docs = list((PROJECT_ROOT / "docs").glob("API*.md"))
    print(f"API 文档: {len(api_docs)} 个")
    
    # 检查 README
    readme = PROJECT_ROOT / "README.md"
    if readme.exists():
        print("✅ README.md 存在")
    else:
        issues.append("缺少 README.md")
        print("❌ 缺少 README.md")
    
    # 检查 CHANGELOG
    changelog = PROJECT_ROOT / "CHANGELOG.md"
    if changelog.exists():
        print("✅ CHANGELOG.md 存在")
    else:
        issues.append("缺少 CHANGELOG.md")
        print("⚠️ 缺少 CHANGELOG.md")
    
    # 检查贡献指南
    contributing = PROJECT_ROOT / "CONTRIBUTING.md"
    if contributing.exists():
        print("✅ CONTRIBUTING.md 存在")
    else:
        issues.append("缺少 CONTRIBUTING.md")
        print("⚠️ 缺少 CONTRIBUTING.md")
    
    return issues


def check_architecture():
    """检查架构问题"""
    print("\n" + "=" * 60)
    print("9. 架构健康度检查")
    print("=" * 60)
    
    issues = []
    
    # 检查大文件
    large_files = []
    for ext in ['*.py', '*.ts', '*.vue']:
        for file_path in (BACKEND_DIR if ext.endswith('.py') else FRONTEND_DIR).rglob(ext):
            if 'node_modules' in str(file_path) or '__pycache__' in str(file_path):
                continue
            try:
                lines = len(file_path.read_text(encoding='utf-8').split('\n'))
                if lines > 500:
                    large_files.append((file_path.relative_to(PROJECT_ROOT), lines))
            except Exception:
                pass
    
    if large_files:
        print("大文件 (>500行):")
        for path, lines in sorted(large_files, key=lambda x: -x[1])[:10]:
            print(f"  - {path}: {lines} 行")
            issues.append(f"大文件需拆分: {path}")
    else:
        print("✅ 无超大文件")
    
    # 检查循环导入风险
    print("\n检查模块导入...")
    ret, stdout, stderr = run_command(
        "python -c \"from app.main import app; print('导入成功')\" 2>&1",
        cwd=BACKEND_DIR,
        timeout=30
    )
    if "成功" in stdout:
        print("✅ 无循环导入问题")
    else:
        print(f"⚠️ 导入问题: {stdout[:200]}")
        issues.append("模块导入问题")
    
    return issues


def generate_summary():
    """生成改进建议摘要"""
    print("\n" + "=" * 60)
    print("改进建议摘要")
    print("=" * 60)
    
    suggestions = []
    
    # 运行所有检查并收集建议
    ruff_errors = check_ruff()
    if ruff_errors:
        suggestions.append({
            'priority': 'P1',
            'category': '代码规范',
            'issue': f'Ruff lint 错误 ({len(ruff_errors)}处)',
            'action': '运行 ruff check --fix 自动修复'
        })
    
    ts_errors = check_typescript()
    if ts_errors:
        suggestions.append({
            'priority': 'P1',
            'category': '类型安全',
            'issue': f'TypeScript 错误 ({len(ts_errors)}处)',
            'action': '修复类型定义错误'
        })
    
    check_tests()
    
    todos = find_todos()
    if todos:
        suggestions.append({
            'priority': 'P2',
            'category': '代码清理',
            'issue': f'TODO/FIXME 注释 ({len(todos)}处)',
            'action': '处理或删除遗留注释'
        })
    
    security = check_security()
    if security:
        suggestions.append({
            'priority': 'P1',
            'category': '安全',
            'issue': f'安全告警 ({len(security)}处)',
            'action': '评估并修复安全问题'
        })
    
    check_dependencies()
    
    patterns = check_code_patterns()
    if patterns:
        suggestions.append({
            'priority': 'P2',
            'category': '代码质量',
            'issue': '代码模式问题',
            'action': '优化异常处理和类型定义'
        })
    
    docs = check_documentation()
    if docs:
        suggestions.append({
            'priority': 'P3',
            'category': '文档',
            'issue': '文档不完整',
            'action': '补充缺失文档'
        })
    
    arch = check_architecture()
    if arch:
        suggestions.append({
            'priority': 'P2',
            'category': '架构',
            'issue': '架构健康度问题',
            'action': '拆分大文件，优化模块结构'
        })
    
    # 打印建议汇总
    print("\n" + "=" * 60)
    print("📋 改进优化建议汇总")
    print("=" * 60)
    
    if suggestions:
        for i, s in enumerate(suggestions, 1):
            print(f"\n{i}. [{s['priority']}] {s['category']}")
            print(f"   问题: {s['issue']}")
            print(f"   行动: {s['action']}")
    else:
        print("\n✅ 项目状态良好，无重大改进需求")
    
    return suggestions


if __name__ == "__main__":
    print("=" * 60)
    print("Backtrader Web 项目诊断报告")
    print(f"时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    suggestions = generate_summary()
    
    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)
