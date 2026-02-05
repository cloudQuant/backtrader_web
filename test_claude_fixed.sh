#!/bin/bash
# Claude CLI 并发测试脚本（修复版）

# 路径设置
STRATEGY_DIR="/home/yun/Downloads/论文/论文"
STRATEGIES_DIR="/home/yun/Documents/backtrader_web/strategies"
PROGRESS_FILE="${STRATEGIES_DIR}/99_PROGRESS.json"

# 并发数
CONCURRENCY=2  # 测试时使用 2 个并发，避免过多并发

# 创建输出目录
mkdir -p "$STRATEGIES_DIR"

echo "======================================================================"
echo "Claude CLI 并发测试脚本（修复版）"
echo "======================================================================"
echo ""
echo "源目录: $STRATEGY_DIR"
echo "输出目录: $STRATEGIES_DIR"
echo ""

# 使用 find 命令获取 HTML 文件（以 null 字符分隔）
echo "正在查找 HTML 文件..."
echo ""

# 获取前 10 个文件（测试）
HTML_FILES=()
while IFS= read -r -d $'\0' file; do
    HTML_FILES+=("$file")
    if [ ${#HTML_FILES[@]} -ge 10 ]; then
        break
    fi
done < <(find "$STRATEGY_DIR" -maxdepth 1 -type f -name "*.html" -print0 | head -n 10)

TOTAL=${#HTML_FILES[@]}

echo "找到 $TOTAL 个 HTML 文件"
echo ""

echo "测试文件:"
for i in "${!HTML_FILES[@]}"; do
    echo "  $((i+1)). ${HTML_FILES[$i]}"
done
echo ""

echo "======================================================================"
echo "开始并发处理"
echo "======================================================================"
echo ""
echo "并发数: $CONCURRENCY"
echo ""

# 处理每个文件
for i in "${!HTML_FILES[@]}"; do
    HTML_FILE="${HTML_FILES[$i]}"
    HTML_NAME=$(basename "$HTML_FILE")
    
    # 生成输出文件名
    INDEX=$((i+1))
    SAFE_NAME=$(echo "$HTML_NAME" | sed 's/.html$//' | tr ' ' '_' | tr '(' '_' | tr ')' '_' | tr '[' '_' | tr ']' '_' | tr -d '[:cntrl:]')
    OUTPUT_FILE="${STRATEGIES_DIR}/${INDEX}_${SAFE_NAME}.md"
    
    echo "[$INDEX/$TOTAL] 处理: $HTML_NAME"
    echo "  输出: $OUTPUT_FILE"
    
    # 读取 HTML 内容
    HTML_CONTENT=$(cat "$HTML_FILE")
    
    # 读取提示词模板
    PROMPT_FILE="${STRATEGIES_DIR}/00_STRATEGY_SUMMARY_PROMPT.md"
    if [ -f "$PROMPT_FILE" ]; then
        PROMPT_TEMPLATE=$(cat "$PROMPT_FILE")
    else
        echo "  ⚠️  提示词模板不存在，使用默认模板"
        PROMPT_TEMPLATE="# 请生成一个详细的策略文档"
    fi
    
    # 生成提示词（简化版）
    PROMPT=$(cat <<EOF
请为以下 HTML 文件生成一个详细的量化交易策略 Markdown 文档：

文件名: $HTML_NAME

HTML 内容:
$HTML_CONTENT

请生成一个高质量、详细、专业的 Markdown 格式策略文档，包含以下章节：
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

每个章节必须详细、专业、准确。
使用 Markdown 格式（.md）。
使用适当的标题（H1, H2, H3）、代码块、列表等。

输出到: $OUTPUT_FILE
EOF
)
    
    # 保存提示词到临时文件
    TEMP_PROMPT="${STRATEGIES_DIR}/temp_prompt_${INDEX}.txt"
    echo "$PROMPT" > "$TEMP_PROMPT"
    
    # 使用 Claude CLI 处理
    echo "  启动 Claude CLI..."
    claude --dangerously-skip-permissions "$TEMP_PROMPT" > "$OUTPUT_FILE" 2>&1
    
    # 检查输出
    if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
        echo "  ✅ 成功: $OUTPUT_FILE ($(wc -c < "$OUTPUT_FILE") 字节))"
    else
        echo "  ❌ 失败: $OUTPUT_FILE"
    fi
    
    # 清理临时文件
    rm -f "$TEMP_PROMPT"
    
    echo ""
    
    # 等待一下，避免过快并发
    sleep 1
done

echo "======================================================================"
echo "测试完成"
echo "======================================================================"
echo ""
echo "总文档数: $TOTAL"
echo ""
echo "生成的文档:"
for i in "${!HTML_FILES[@]}"; do
    INDEX=$((i+1))
    SAFE_NAME=$(echo "${HTML_FILES[$i]}" | sed 's/.html$//' | tr ' ' '_' | tr '(' '_' | tr ')' '_' | tr '[' '_' | tr ']' '_' | tr -d '[:cntrl:]')
    OUTPUT_FILE="${STRATEGIES_DIR}/${INDEX}_${SAFE_NAME}.md"
    
    if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
        echo "  ✅ $OUTPUT_FILE"
    else
        echo "  ❌ $OUTPUT_FILE (未生成)"
    fi
done

echo ""
echo "策略文档目录: $STRATEGIES_DIR"
echo ""
