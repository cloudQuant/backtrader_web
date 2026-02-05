#!/bin/bash
# Claude CLI 并发测试脚本（最终修复版）

# 路径设置
STRATEGY_DIR="/home/yun/Downloads/论文/论文"
STRATEGIES_DIR="/home/yun/Documents/backtrader_web/strategies"
PROGRESS_FILE="${STRATEGIES_DIR}/99_PROGRESS.json"

# 并发数（测试时使用 2，避免过多并发）
CONCURRENCY=2

# 创建输出目录
mkdir -p "$STRATEGIES_DIR"

echo "======================================================================"
echo "Claude CLI 并发测试脚本（最终修复版）"
echo "======================================================================"
echo ""
echo "源目录: $STRATEGY_DIR"
echo "输出目录: $STRATEGIES_DIR"
echo ""

# 使用 find 命令获取 HTML 文件（正序）
echo "正在查找 HTML 文件..."
echo ""

# 获取所有 HTML 文件并按名称排序（正序）
HTML_FILES=()
while IFS= read -r -d $'\0' file; do
    HTML_FILES+=("$file")
done < <(find "$STRATEGY_DIR" -maxdepth 1 -type f -name "*.html" -print0 | sort -z)

TOTAL=${#HTML_FILES[@]}

echo "找到 $TOTAL 个 HTML 文件"
echo ""

# 测试前 10 个文件
TEST_COUNT=10
if [ $TOTAL -lt $TEST_COUNT ]; then
    TEST_COUNT=$TOTAL
fi

echo "测试文件数: $TEST_COUNT"
echo ""
echo "测试文件:"
for i in $(seq 0 $((TEST_COUNT - 1))); do
    echo "  $((i+1))). ${HTML_FILES[$i]}"
done
echo ""

echo "======================================================================"
echo "开始测试处理"
echo "======================================================================"
echo ""

# 处理每个文件
for i in $(seq 0 $((TEST_COUNT - 1))); do
    HTML_FILE="${HTML_FILES[$i]}"
    HTML_NAME=$(basename "$HTML_FILE")
    
    # 生成输出文件名 (XXX_FILENAME.md 格式)
    INDEX=$((i + 1))
    SAFE_NAME=$(echo "$HTML_NAME" | sed 's/.html$//' | tr ' ' '_' | tr '(' '_' | tr ')' '_' | tr '[' '_' | tr ']' '_')
    OUTPUT_FILE="${STRATEGIES_DIR}/${INDEX}_${SAFE_NAME}.md"
    
    echo "[$INDEX/$TEST_COUNT] 处理: $HTML_NAME"
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
根据文件名和内容，自动分类策略类型：
- 动量策略: momentum, trend, price action, time series momentum, breakout
- 均值回归: mean reversion, mean, reversion, dollar cost averaging
- 突破策略: breakout, channel, donchian, breakthrough, support, resistance
- 机器学习/AI: machine learning, neural, ai, lstm, deep learning, random forest, gradient boosting
- 期权策略: option, call, put, iron, condor, butterfly, straddle, spread
- 波动率策略: volatility, atr, std, vix, volatility index, implied volatility
- 统计套利: pairs, arbitrage, cointegration, statistical arbitrage, pairs trading
- 投资组合优化: optimization, portfolio, optimizer, mean-variance, efficient frontier
- 风险管理: risk, drawdown, sharpe, crash, protection, edge
- 收益预估: earnings, estimate, ibes, estimize, forecast, analyst
- 综合策略: financial hacker, quantstrat trader, quantpedia, quantstart, robot wealth, quantinsti
- 其他策略: 其他所有策略

## 输出要求
1. 文档必须详细、专业、准确
2. 文档必须包含所有 10 个主要章节
3. 每个章节必须包含所有必要的子章节
4. 代码示例必须有详细的注释和说明
5. 使用 Markdown 格式（.md）
6. 文件编码: UTF-8
7. 换行符: LF (Unix 风格)

## 输出格式
将生成的 Markdown 文档输出到标准输出
EOF
)
    
    # 使用 Claude CLI 处理
    (
        echo "[$INDEX/$TEST_COUNT] 启动 Claude CLI..."
        claude --dangerously-skip-permissions -p "$PROMPT" > "$OUTPUT_FILE" 2>&1
        
        # 检查输出
        if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
            FILE_SIZE=$(wc -c < "$OUTPUT_FILE")
            echo "  ✅ 成功: $OUTPUT_FILE ($FILE_SIZE 字节)"
        else
            echo "  ❌ 失败: $OUTPUT_FILE (未生成或为空)"
        fi
    ) &
    
    # 等待当前文档处理完成（控制并发）
    wait
    
    echo ""
done

echo "======================================================================"
echo "测试完成"
echo "======================================================================"
echo ""
echo "总文档数: $TOTAL"
echo "测试文档数: $TEST_COUNT"
echo ""
echo "生成的文档:"
echo ""

# 显示生成的文档
cd "$STRATEGIES_DIR" || exit 1
for i in $(seq 1 $TEST_COUNT); do
    OUTPUT_FILE="${STRATEGIES_DIR}/${i}_*.md"
    if [ -f "$OUTPUT_FILE" ]; then
        echo "✅ $OUTPUT_FILE"
    fi
done

echo ""
echo "策略文档目录: $STRATEGIES_DIR"
echo ""
