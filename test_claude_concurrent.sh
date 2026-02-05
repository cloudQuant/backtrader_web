#!/bin/bash
# Claude CLI 并发测试脚本（测试 10 个文档）

# 路径设置
STRATEGY_DIR="/home/yun/Downloads/论文/论文"
STRATEGIES_DIR="/home/yun/Documents/backtrader_web/strategies"
PROGRESS_FILE="${STRATEGIES_DIR}/99_PROGRESS.json"

# 并发数
CONCURRENCY=10

# 创建输出目录
mkdir -p "$STRATEGIES_DIR"

# 获取 HTML 文件（取前 10 个进行测试）
HTML_FILES=($(find "$STRATEGY_DIR" -maxdepth 1 -type f -name "*.html" | sort | head -n 10))
TOTAL=${#HTML_FILES[@]}

echo "======================================================================"
echo "Claude CLI 并发测试"
echo "======================================================================"
echo ""
echo "总文档数: $TOTAL"
echo "并发数: $CONCURRENCY"
echo ""
echo "测试文档:"
for i in "${!HTML_FILES[@]}"; do
    echo "  $((i+1)). ${HTML_FILES[$i]}"
done
echo ""
echo "======================================================================"
echo ""

# 加载进度
CURRENT_INDEX=0
if [ -f "$PROGRESS_FILE" ]; then
    CURRENT_INDEX=$(cat "$PROGRESS_FILE" | grep -oP '"current_index":\s*\K\d+')
fi

echo "当前索引: $CURRENT_INDEX"
echo ""

# 处理每个文件
for i in "${!HTML_FILES[@]}"; do
    INDEX=$((CURRENT_INDEX + i + 1))
    HTML_FILE="${HTML_FILES[$i]}"
    HTML_NAME=$(basename "$HTML_FILE")
    
    # 生成输出文件名
    OUTPUT_FILE="${STRATEGIES_DIR}/$(printf '%03d_%s' $INDEX "$HTML_NAME" | sed 's/.html$/.md/')"
    
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
1. 生成详细的 Markdown 文档
2. 文档必须包含以下章节：
   - 标题（H1）
   - 策略概述（H2）
   - 策略逻辑（H2）
   - 需要的数据（H2）
   - 策略有效性原因（H2）
   - 风险和注意事项（H2）
   - 实施步骤（H2）
   - 参数配置（H2）
   - Backtrader 实现框架（H2）
   - 参考链接（H2）
3. 每个章节必须详细、专业、准确
4. 使用适当的术语和格式
5. 包含代码示例和说明

## 策略类型分类
根据文件名和内容，自动分类策略类型：
- 动量策略: momentum, trend, price action
- 均值回归: mean reversion, mean, reversion
- 突破策略: breakout, channel, donchian
- 机器学习/AI: machine learning, neural, ai, lstm
- 期权策略: option, call, put, iron, condor
- 波动率策略: volatility, atr, std, vix
- 统计套利: pairs, arbitrage, cointegration
- 投资组合优化: optimization, portfolio, optimizer
- 风险管理: risk, drawdown, sharpe, crash, protection
- 收益预估: earnings, estimate, ibes, estimize
- 综合策略: financial hacker, quantstrat trader, quantpedia, quantstart
- 其他策略: 其他所有策略

## 输出格式
将生成的 Markdown 文档保存到: $OUTPUT_FILE

## 质量标准
- 详细性: 文档必须详细，包含所有必要的章节
- 准确性: 文档必须准确，不包含错误信息
- 可读性: 文档必须易于阅读，结构清晰
- 专业性: 文档必须专业，使用适当的术语和格式
- 完整性: 文档必须完整，包含所有必要的部分

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

请生成高质量、详细、专业的 Markdown 策略文档。
EOF
)
    
    # 保存提示词到临时文件
    TEMP_PROMPT="${STRATEGIES_DIR}/temp_prompt_${INDEX}.txt"
    echo "$PROMPT" > "$TEMP_PROMPT"
    
    # 使用 Claude CLI 处理（后台运行）
    echo "  启动 Claude CLI..."
    (
        echo "  Claude CLI 开始处理..."
        claude --dangerously-skip-permissions "$TEMP_PROMPT" > "$OUTPUT_FILE" 2>&1
        
        # 检查是否成功
        if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
            echo "  ✅ 成功: $OUTPUT_FILE"
            
            # 更新进度
            CURRENT_INDEX=$INDEX
            
            # 保存进度
            cat > "$PROGRESS_FILE" << EOF
{
  "current_index": $CURRENT_INDEX,
  "total": $TOTAL,
  "completed_count": $CURRENT_INDEX,
  "progress": "$((CURRENT_INDEX * 100 / TOTAL))%"
}
EOF
            
            # 删除临时文件
            rm -f "$TEMP_PROMPT"
        else
            echo "  ❌ 失败: $OUTPUT_FILE 未生成"
        fi
        
        echo "  Claude CLI 完成"
    ) &
    
    # 控制并发数（等待部分进程完成）
    ACTIVE=0
    PIDS=($!)
    
    # 获取当前后台进程数
    while read -r PID; do
        if kill -0 "$PID" 2>/dev/null; then
            PIDS+=("$PID")
        fi
    done < <(jobs -p)
    
    echo "  当前并发数: ${#PIDS[@]}"
    
    # 如果达到并发数限制，等待部分进程完成
    while [ ${#PIDS[@]} -ge $CONCURRENCY ]; do
        sleep 1
        ACTIVE=0
        
        # 检查进程状态
        for PID in "${PIDS[@]}"; do
            if ! kill -0 "$PID" 2>/dev/null; then
                ACTIVE=$((ACTIVE + 1))
            fi
        done
        
        echo "  等待... (并发: ${#PIDS[@]}, 活动: $ACTIVE)"
    done
    
    # 短暂延迟
    sleep 0.5
    
    echo ""
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
echo "已处理: $CURRENT_INDEX"
echo "完成率: $((CURRENT_INDEX * 100 / TOTAL))%"
echo ""

echo "生成的文档:"
for ((i=0; i<TOTAL; i++)); do
    INDEX=$((CURRENT_INDEX - TOTAL + i + 1))
    OUTPUT_FILE="${STRATEGIES_DIR}/$(printf '%03d_*.md' $INDEX)"
    if [ -f "$OUTPUT_FILE" ]; then
        echo "  ✅ $OUTPUT_FILE"
    else
        echo "  ❌ $OUTPUT_FILE (未生成)"
    fi
done

echo ""
echo "策略文档目录: $STRATEGIES_DIR"
echo ""
