#!/bin/bash
# Claude CLI 并发处理脚本（简单版）

# 路径设置
STRATEGY_DIR="/home/yun/Downloads/论文/论文"
STRATEGIES_DIR="/home/yun/Documents/backtrader_web/strategies"
PROMPT_FILE="${STRATEGIES_DIR}/00_STRATEGY_SUMMARY_PROMPT.md"

# 并发数（测试时使用 2）
CONCURRENCY=2

# 创建输出目录
mkdir -p "$STRATEGIES_DIR"

echo "======================================================================"
echo "Claude CLI 并发处理脚本（简单版）"
echo "======================================================================"
echo ""

# 读取提示词模板
if [ -f "$PROMPT_FILE" ]; then
    PROMPT_TEMPLATE=$(cat "$PROMPT_FILE")
else
    echo "⚠️  提示词模板不存在，使用简化提示词"
    PROMPT_TEMPLATE="请生成一个详细的策略文档"
fi

# 获取所有 HTML 文件
mapfile -t -n 10 HTML_FILES < <(find "$STRATEGY_DIR" -maxdepth 1 -type f -name "*.html" | sort)

# 显示要处理的文件
echo "要处理的文件（前 10 个）："
for i in "${!HTML_FILES[@]}"; do
    echo "  $((i+1))). ${HTML_FILES[$i]}"
done
echo ""

echo "======================================================================"
echo "开始并发处理"
echo "======================================================================"
echo ""

# 处理每个文件
for i in "${!HTML_FILES[@]}"; do
    HTML_FILE="${HTML_FILES[$i]}"
    INDEX=$((i + 1))
    
    # 生成输出文件名
    SAFE_NAME=$(basename "$HTML_FILE" | sed 's/.html$//' | tr ' ' '_' | tr '(' '_' | tr ')' '_' | tr '[' '_' | tr ']' '_' | tr '-' '_' | tr '/' '_' | tr '.' '_' | tr ',' '_')
    OUTPUT_FILE="${STRATEGIES_DIR}/${INDEX}_${SAFE_NAME}.md"
    
    echo "[$INDEX] 处理: $HTML_FILE"
    
    # 读取 HTML 内容
    HTML_CONTENT=$(cat "$HTML_FILE")
    
    # 生成提示词（简化版）
    PROMPT=$(cat <<EOF
你是一个专业的量化交易策略分析师和文档编写者。你的任务是为给定的策略 HTML 文件生成高质量、详细、专业的 Markdown 格式策略文档。

## 输入文件
HTML 文件路径: $HTML_FILE

## 策略内容
以下是从 HTML 文件中提取的内容：

$HTML_CONTENT

## 文档生成要求
请生成一个高质量的 Markdown 格式策略文档，包含以下章节：
1. 标题（策略名称）
2. 策略概述（核心思想、策略优势、策略特点）
3. 策略逻辑（核心步骤、技术指标、信号生成、仓位管理、风险控制）
4. 需要的数据（价格数据、指标数据、基本面数据、宏观经济数据）
5. 策略有效性原因（理论支撑、实证证据、学术研究、行业应用）
6. 风险和注意事项（市场风险、策略风险、执行风险、技术风险、合规风险、风险管理建议）
7. 实施步骤（7 个详细步骤：策略理解、数据准备、策略实现、回测验证、参数优化、模拟交易、实盘验证）
8. 参数配置（策略参数、参数说明、参数优化建议）
9. Backtrader 实现框架（完整的 Python 代码）
10. 参考链接（原始资源、相关资源）

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

## 输出格式
将生成的 Markdown 文档输出到: $OUTPUT_FILE

## 洊量标准
- 详细性: 文档必须详细，包含所有必要的章节和子章节
- 准确性: 文档必须准确，不包含错误信息
- 可读性: 文档必须易于阅读，结构清晰，层次分明
- 专业性: 文档必须专业，使用适当的术语和格式
- 完整性: 文档必须完整，包含所有必要的部分

请生成高质量、详细、专业的 Markdown 策略文档。
EOF
)
    
    # 保存提示词到临时文件
    TEMP_PROMPT="${STRATEGIES_DIR}/temp_prompt.txt"
    echo "$PROMPT" > "$TEMP_PROMPT"
    
    # 使用 Claude CLI 处理
    echo "  启动 Claude CLI..."
    
    # 使用 Claude CLI（假设可以读取文件）
    claude --dangerously-skip-permissions "$TEMP_PROMPT" > "$OUTPUT_FILE" 2>&1
    
    # 检查输出
    if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
        FILE_SIZE=$(wc -c < "$OUTPUT_FILE")
        echo "  ✅ 成功: $OUTPUT_FILE ($FILE_SIZE 字节)"
    else
        echo "  ❌ 失败: $OUTPUT_FILE"
    fi
    
    # 删除临时文件
    rm -f "$TEMP_PROMPT"
    
    echo ""
    
    # 等待一下（控制并发）
    sleep 2
done

# 等待所有后台进程完成
wait

echo ""
echo "======================================================================"
echo "所有文件处理完成！"
echo "======================================================================"
echo ""
echo "生成的文档:"

# 显示生成的文档
cd "$STRATEGIES_DIR" || exit 1
for i in "${!HTML_FILES[@]}"; do
    INDEX=$((i + 1))
    SAFE_NAME=$(basename "${HTML_FILES[$i]}" | sed 's/.html$//' | tr ' ' '_' | tr '(' '_' | tr ')' '_' | tr '[' '_' | tr ']' '_' | tr '-' '_' | tr '/' '_' | tr '.' '_' | tr ',' '_')
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
