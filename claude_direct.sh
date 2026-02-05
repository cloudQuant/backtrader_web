#!/bin/bash
# Claude Code CLI 简化测试脚本（不并发）

# 路径设置
STRATEGY_DIR="/home/yun/Downloads/论文/论文"
STRATEGIES_DIR="/home/yun/Documents/backtrader_web/strategies"
PROMPT_FILE="${STRATEGIES_DIR}/00_STRATEGY_SUMMARY_PROMPT.md"

# 创建输出目录
mkdir -p "$STRATEGIES_DIR"

echo "======================================================================"
echo "Claude Code CLI 简化测试脚本（不并发）"
echo "======================================================================"
echo ""
echo "源目录: $STRATEGY_DIR"
echo "输出目录: $STRATEGIES_DIR"
echo ""

# 获取前 3 个文件（测试）
HTML_FILES=($(find "$STRATEGY_DIR" -maxdepth 1 -type f -name "*.html" | sort -z | head -n 3))
TOTAL=${#HTML_FILES[@]}

echo "找到 $TOTAL 个 HTML 文件"
echo ""

echo "测试文件:"
for i in "${!HTML_FILES[@]}"; do
    echo "  $((i+1))). ${HTML_FILES[$i]}"
done
echo ""

echo "======================================================================"
echo "开始测试处理（不并发）"
echo "======================================================================"
echo ""

# 读取提示词模板
if [ -f "$PROMPT_FILE" ]; then
    PROMPT_TEMPLATE=$(cat "$PROMPT_FILE")
else
    echo "⚠️  提示词模板不存在，使用简化提示词"
    PROMPT_TEMPLATE="# 请生成一个详细的策略文档"
fi

# 处理每个文件（顺序执行，不并发）
for i in "${!HTML_FILES[@]}"; do
    HTML_FILE="${HTML_FILES[$i]}"
    INDEX=$((i + 1))
    HTML_NAME=$(basename "$HTML_FILE")
    
    # 生成输出文件名
    SAFE_NAME=$(echo "$HTML_NAME" | sed 's/.html$//' | tr ' ' '_' | tr '(' '_' | tr ')' '_' | tr '[' '_' | tr ']' '_' | tr '-' '_' | tr '/' '_' | tr '.' '_' | tr ',' '_')
    OUTPUT_FILE="${STRATEGIES_DIR}/${INDEX}_${SAFE_NAME}.md"
    
    echo "[$INDEX/$TOTAL] 处理: $HTML_NAME"
    echo "  输出: $OUTPUT_FILE"
    
    # 读取 HTML 内容
    HTML_CONTENT=$(cat "$HTML_FILE")
    
    # 生成提示词
    PROMPT=$(cat <<EOF
你是一个专业的量化交易策略分析师和文档编写者。你的任务是为给定的策略 HTML 文件生成高质量、详细、专业的 Markdown 格式策略文档。

## 输入文件
HTML 文件路径: $HTML_FILE

## 策略内容
以下是从 HTML 文件中提取的内容：

$HTML_CONTENT

## 文档生成要求
生成一个详细的 Markdown 格式策略文档，包含以下章节：
1. 标题（H1）
2. 策略概述（H2）
3. 策略逻辑（H2）
4. 需要的数据（H2）
5. 策略有效性原因（H2）
6. 风险和注意事项（H2）
7. 实施步骤（H2）
8. 参数配置（H2）
9. Backtrader 实现框架（H2）
10. 参考链接（H2）

## 策略类型分类
根据文件名和内容，自动分类策略类型。

## 输出格式
将生成的 Markdown 文档输出到标准输出（不要保存到文件）。

## 洛量标准
- 详细性: 文档必须详细，包含所有必要的章节
- 准确性: 文档必须准确，不包含错误信息
- 可读性: 文档必须易于阅读，结构清晰
- 专业性: 文档必须专业，使用适当的术语和格式
- 完整性: 文档必须完整，包含所有必要的部分

请生成高质量、详细、专业的 Markdown 策略文档。
EOF
)
    
    # 直接调用 claude（不使用 npx）
    echo "  直接调用 claude..."
    
    # 使用 claude 命令（假设可以直接调用）
    claude --dangerously-skip-permissions "$PROMPT" > "$OUTPUT_FILE" 2>&1
    
    # 检查输出
    if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
        FILE_SIZE=$(wc -c < "$OUTPUT_FILE")
        echo "  ✅ 成功: $OUTPUT_FILE ($FILE_SIZE 字节)"
        
        # 查看文档内容（前 20 行）
        echo ""
        echo "  文档预览（前 20 行）："
        head -n 20 "$OUTPUT_FILE" | sed 's/^/    /'
        echo ""
    else
        echo "  ❌ 失败: $OUTPUT_FILE"
    fi
    
    echo ""
done

echo "======================================================================"
echo "测试完成"
echo "======================================================================"
echo ""
echo "总文档数: $TOTAL"
echo ""
echo "生成的文档:"
cd "$STRATEGIES_DIR" || exit 1
for i in "${!HTML_FILES[@]}"; do
    INDEX=$((i + 1))
    SAFE_NAME=$(echo "${HTML_FILES[$i]}" | sed 's/.html$//' | tr ' ' '_' | tr '(' '_' | tr ')' '_' | tr '[' '_' | tr ']' '_' | tr '-' '_' | tr '/' '_' | tr '.' '_' | tr ',' '_')
    OUTPUT_FILE="${INDEX}_${SAFE_NAME}.md"
    
    if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
        echo "  ✅ $OUTPUT_FILE"
    else
        echo "  ❌ $OUTPUT_FILE (未生成)"
    fi
done

echo ""
echo "策略文档目录: $STRATEGIES_DIR"
echo ""
