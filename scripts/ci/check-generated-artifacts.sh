#!/usr/bin/env bash
# 检查是否有生成物文件被提交

set -euo pipefail

ERRORS=0
TRACKED_GENERATED_FILES="$(
  git ls-files | grep -E '^(coverage/|coverage\.json$|src/backend/coverage/|src/backend/coverage\.json$|src/frontend/coverage/|src/frontend/e2e-results/|src/frontend/playwright-report/|src/frontend/test-results/)' || true
)"

echo "检查受保护的生成物路径..."

if [ -n "$TRACKED_GENERATED_FILES" ]; then
    echo "❌ 错误: 发现以下生成物文件仍被 Git 跟踪:"
    echo "$TRACKED_GENERATED_FILES"
    ERRORS=$((ERRORS + 1))
fi

if [ "$ERRORS" -gt 0 ]; then
    echo ""
    echo "❌ 检查失败: 发现 $ERRORS 个问题"
    echo ""
    echo "解决方法:"
    echo "1. 将生成物文件/目录添加到 .gitignore"
    echo "2. 运行 'git rm -r --cached <path>' 从 Git 索引中移除"
    echo "3. 提交 .gitignore 的修改"
    exit 1
fi

echo "✅ 检查通过: 没有发现生成物文件被跟踪"
