# 策略解释器说明

> 适用范围：AI for Investor 迭代 166 的策略解释器。解释结果仅供研究参考，不构成投资建议。

## 1. 目标

策略解释器用于回答：这段 Backtrader 策略代码到底在做什么、什么时候买入、什么时候卖出、使用了哪些指标和风控。

系统输出：

- 策略一句话总结
- 指标说明
- 买入逻辑说明
- 卖出逻辑说明
- 参数说明
- 适配市场环境
- AST 静态证据：指标、参数、信号、风控、数据源
- `disclaimer`：解释仅供研究参考，不构成投资建议

## 2. 后端处理流程

```text
策略源码 / strategy_id / backtest_id
  → 解析策略源码
  → AST 静态分析
  → 尝试 LLM JSON 解释
  → 失败或未配置 AI 时回退静态解释
  → 按 code_hash 缓存结果
```

## 3. AST 静态分析

核心文件：`src/backend/app/services/strategy_explainer/ast_extractor.py`

可识别内容：

- `bt.indicators.*` / `bt.ind.*` / `bt.talib.*` 指标调用
- `params = (...)` 与 `params = dict(...)` 参数定义
- `self.buy(...)`、`self.sell(...)`、`self.close(...)` 买卖信号
- `order_target_percent(...)` 与 `order_target_size(...)` 仓位目标信号
- `size=...` 仓位控制
- `stop_loss` / `stoploss` / `trailing_stop` 参数型风控
- 常见 `self.data`、`close`、`open`、`high`、`low`、`volume` 数据源引用

解析失败时返回：

- `parsable=false`
- `raw_code`
- `parse_error`

这样前端仍可展示降级状态，LLM 路径也可以继续基于原始源码尝试解释。

## 4. LLM 解释路径

核心文件：`src/backend/app/services/strategy_explainer/llm_explainer.py`

当 `AIChatService` 已启用时，解释器会把 AST 结构和源码片段发送给模型，并要求只返回 JSON 对象。

要求字段：

- `summary`
- `indicators_explanation`
- `entry_explanation`
- `exit_explanation`
- `params_explanation`
- `market_fit`
- `risk_notes`

稳定性策略：

- 支持从 Markdown JSON code fence 中提取 JSON
- JSON 解析失败返回 `None`，不会中断解释服务
- 必填字段缺失或为空时回退静态解释
- `risk_notes` 会标准化为字符串数组
- AI 未配置或返回异常时返回 `reason_code=static_fallback`

## 5. API

### 生成解释

```http
POST /api/v1/strategy/explain
```

请求至少提供一个来源：

```json
{
  "code": "class Demo(bt.Strategy): ...",
  "strategy_id": null,
  "backtest_id": null,
  "strategy_name": "双均线策略",
  "category": "trend"
}
```

### 查询缓存

```http
GET /api/v1/strategy/explain/cached/{code_hash}
```

缓存策略：

- 对源码计算 SHA-256 `code_hash`
- 相同代码优先返回缓存
- 缓存命中时 `cached=true`

## 6. 前端展示

核心文件：`src/frontend/src/components/backtest/StrategyExplanationCard.vue`

页面展示：

- 6 段自然语言解释
- 指标和参数证据
- 买入/卖出信号示意
- 仓位/风控证据
- AST 解析状态
- AI/静态 fallback 来源标识

集成位置：`src/frontend/src/views/BacktestResultPage.vue`

## 7. 解读边界

| 边界 | 说明 |
|------|------|
| AST 只能识别常见静态模式 | 动态生成指标、元编程或复杂封装可能无法完全提取 |
| LLM 解释依赖外部模型配置 | 未配置时仍会返回静态 fallback |
| 解释不是交易建议 | 只帮助理解策略逻辑，不判断是否实盘 |
| 风控识别不等于风控充分 | 检测到 `stop_loss` 参数不代表策略实际严格止损 |

## 8. 推荐工作流

1. 在回测详情页查看评分和过拟合检测
2. 查看策略解释器的买卖逻辑和风控证据
3. 如果 AST 解析失败，优先检查策略源码结构是否为常见 Backtrader 写法
4. 如果 AI 解释不可用，先使用静态 fallback 理解关键结构
5. 对高风险策略结合过拟合检测和源码人工复核
