#!/bin/bash
# Claude Code CLI 并发处理脚本（使用正确的包名）

# 路径设置
STRATEGY_DIR="/home/yun/Downloads/论文/论文"
STRATEGIES_DIR="/home/yun/Documents/backtrader_web/strategies"
PROMPT_FILE="${STRATEGIES_DIR}/00_STRATEGY_SUMMARY_PROMPT.md"

# 并发数（测试时使用 2）
CONCURRENCY=2

# 创建输出目录
mkdir -p "$STRATEGIES_DIR"

echo "======================================================================"
echo "Claude Code CLI 并发处理脚本（使用 npx）"
echo "======================================================================"
echo ""
echo "源目录: $STRATEGY_DIR"
echo "输出目录: $STRATEGIES_DIR"
echo ""

# 使用 npx 获取所有 HTML 文件（前 10 个）
echo "正在查找 HTML 文件..."
echo ""

# 获取前 10 个 HTML 文件
HTML_FILES=()
COUNT=0
while IFS= read -r -d $'\0' file; do
    HTML_FILES+=("$file")
    COUNT=$((COUNT + 1))
    if [ $COUNT -ge 10 ]; then
        break
    fi
done < <(find "$STRATEGY_DIR" -maxdepth 1 -type f -name "*.html" -print0 | sort -z)

TOTAL=${#HTML_FILES[@]}

echo "找到 $TOTAL 个 HTML 文件"
echo ""

echo "测试文件:"
for i in "${!HTML_FILES[@]}"; do
    echo "  $((i+1))). ${HTML_FILES[$i]}"
done
echo ""

echo "======================================================================"
echo "开始处理"
echo "======================================================================"
echo ""
echo "并发数: $CONCURRENCY"
echo "使用: npx @anthropic-ai/claude-code"
echo ""

# 读取提示词模板
if [ -f "$PROMPT_FILE" ]; then
    PROMPT_TEMPLATE=$(cat "$PROMPT_FILE")
else
    echo "⚠️  提示词模板不存在，使用简化提示词"
    PROMPT_TEMPLATE="# 请生成一个详细的策略文档"
fi

# 处理每个文件
for i in "${!HTML_FILES[@]}"; do
    INDEX=$((i + 1))
    HTML_FILE="${HTML_FILES[$i]}"
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

## 文档结构
每个生成的 Markdown 文档应包含以下主要章节：
1. 标题
2. 策略概述（包含：核心思想、策略优势、策略特点、适用市场）
3. 策略逻辑（包含：核心步骤、技术指标、信号生成、仓位管理、风险控制）
4. 需要的数据（包含：价格数据、指标数据、基本面数据、宏观经济数据）
5. 策略有效性原因（包含：理论支撑、实证证据、学术研究、行业应用）
6. 风险和注意事项（包含：市场风险、策略风险、执行风险、技术风险、合规风险、风险管理建议）
7. 实施步骤（包含：7 个详细步骤）
8. 参数配置（包含：策略参数、参数说明、参数优化建议）
9. Backtrader 实现框架（包含：完整的 Python 代码）
10. 参考链接（包含：原始资源、相关资源）

## 洛量标准
- 详细性: 文档必须详细，包含所有必要的章节
- 准确性: 文档必须准确，不包含错误信息
- 可读性: 文档必须易于阅读，结构清晰
- 专业性: 文档必须专业，使用适当的术语和格式
- 完整性: 文档必须完整，包含所有必要的部分

请生成高质量、详细、专业的 Markdown 策略文档。
EOF
)
    
    # 保存提示词到临时文件
    TEMP_PROMPT="${STRATEGIES_DIR}/temp_prompt_${INDEX}.txt"
    echo "$PROMPT" > "$TEMP_PROMPT"
    
    # 使用 npx 运行 claude-code（后台运行）
    (
        echo "[$INDEX/$TOTAL] 启动 Claude Code CLI..."
        
        # 使用 npx 运行 claude-code
        # 注意：claude-code 可能需要一些参数，这里使用基本的参数
        npx @anthropic-ai/claude-code "$TEMP_PROMPT" > "$OUTPUT_FILE" 2>&1
        
        # 检查输出
        if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
            FILE_SIZE=$(wc -c < "$OUTPUT_FILE")
            echo "  ✅ 成功: $OUTPUT_FILE ($FILE_SIZE 字节)"
        else
            echo "  ❌ 失败: $OUTPUT_FILE"
        fi
        
        # 清理临时文件
        rm -f "$TEMP_PROMPT"
    ) &
    
    # 控制并发数（等待部分进程完成）
    ACTIVE=0
    PIDS=($!)
    
    # 获取当前后台进程数
    for PID in "${PIDS[@]}"; do
        if kill -0 "$PID" 2>/dev/null; then
            ACTIVE=$((ACTIVE + 1))
        fi
    done
    
    # 如果达到并发数限制，等待部分进程完成
    while [ $ACTIVE -ge $CONCURRENCY ]; do
        sleep 1
        ACTIVE=0
        for PID in "${PIDS[@]}"; do
            if kill -0 "$PID" 2>/dev/null; then
                ACTIVE=$((ACTIVE + 1))
            fi
        done
    done
    
    echo ""
    
    # 短暂延迟
    sleep 0.5
done

# 等待所有后台进程完成
echo ""
echo "======================================================================"
echo "等待所有后台进程完成..."
echo "======================================================================"
echo ""

wait

# 输出总结
echo ""
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
