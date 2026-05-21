# 迭代164 - 自然语言驱动交易

> **文档状态**: 设计中
> **创建日期**: 2026-05-20
> **核心目标**: 在现有 AI Copilot + bt_api_py 网关基础上，实现用自然语言直接驱动交易执行

---

## 1. 背景与调研

### 1.1 行业参考项目

| 项目 | 架构 | 核心思路 | 适用性 |
|------|------|----------|--------|
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) (77k⭐) | 多Agent协作 (LangGraph) | 分析师团队→研究员辩论→交易员决策→风控审批 | 决策流程参考，但不直接执行交易 |
| [CryptoTrade](https://github.com/Xtra-Computing/CryptoTrade) (EMNLP 2024) | 反思式LLM Agent | 每日分析→决策→反思→改进 | 反思机制可借鉴 |
| [AI-Trader](https://github.com/HKUDS/AI-Trader) | LLM + 实时行情 | 自然语言理解市场→生成交易信号 | 信号生成参考 |
| [Gajesh2007/ai-trading-agent](https://github.com/Gajesh2007/ai-trading-agent) | LLM + Hyperliquid | 直接对接交易所API执行 | 执行层参考 |

### 1.2 当前项目已有能力

- ✅ AI Copilot 4种模式（知识问答、策略构思、策略生成、策略审查）
- ✅ bt_api_py 多交易所网关（CTP/IB/Binance/OKX/MT5）
- ✅ 实盘交易实例管理（启动/停止/监控）
- ✅ ZMQ 网关通信（command/event/market endpoints）
- ✅ 模拟交易账户系统
- ✅ 实时行情 WebSocket 推送

### 1.3 缺失的关键能力

- ❌ 自然语言 → 交易指令解析（Intent Recognition）
- ❌ 直接下单 API（绕过策略子进程）
- ❌ AI 交易模式（第5种 Copilot 模式）
- ❌ 交易确认与风控审批流程
- ❌ 交易执行反馈与反思机制
- ❌ 交易历史与 AI 决策日志

---

## 2. 架构设计

### 2.1 整体流程

```
用户自然语言输入
    ↓
┌─────────────────────────────────────────┐
│  AI Trading Agent (新增第5种模式)         │
│  ┌───────────┐  ┌──────────────────┐    │
│  │ Intent    │  │ Market Context   │    │
│  │ Parser    │  │ Enricher         │    │
│  │ (LLM)     │  │ (行情+持仓+账户) │    │
│  └─────┬─────┘  └────────┬─────────┘    │
│        └────────┬─────────┘              │
│                 ↓                        │
│  ┌──────────────────────────────┐        │
│  │ Trade Decision Engine (LLM)  │        │
│  │ - 解析交易意图               │        │
│  │ - 生成结构化交易指令          │        │
│  │ - 风险评估                   │        │
│  └──────────────┬───────────────┘        │
│                 ↓                        │
│  ┌──────────────────────────────┐        │
│  │ Risk Guard (规则+LLM)        │        │
│  │ - 仓位限制检查               │        │
│  │ - 单笔金额限制               │        │
│  │ - 频率限制                   │        │
│  │ - 人工确认（可配置）          │        │
│  └──────────────┬───────────────┘        │
└─────────────────┼───────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│  Order Execution Layer                   │
│  ┌──────────────────────────────┐        │
│  │ Direct Order API (新增)       │        │
│  │ - 通过 bt_api_py 直接下单    │        │
│  │ - 支持市价/限价/止损          │        │
│  │ - 支持多交易所路由            │        │
│  └──────────────┬───────────────┘        │
│                 ↓                        │
│  ┌──────────────────────────────┐        │
│  │ Gateway Router               │        │
│  │ - CTP / IB / Binance / OKX  │        │
│  └──────────────────────────────┘        │
└─────────────────────────────────────────┘
                  ↓
          交易执行结果
                  ↓
┌─────────────────────────────────────────┐
│  Feedback & Reflection                   │
│  - 执行结果记录                          │
│  - AI 反思与建议                         │
│  - 交易日志持久化                        │
└─────────────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 Trading Intent Parser

将自然语言解析为结构化交易指令：

```python
class TradingIntent:
    action: Literal["buy", "sell", "close", "cancel", "query", "modify"]
    symbol: str | None          # 交易品种
    exchange: str | None        # 交易所
    quantity: float | None      # 数量
    price: float | None         # 价格（None=市价）
    order_type: Literal["market", "limit", "stop"] = "market"
    stop_loss: float | None     # 止损价
    take_profit: float | None   # 止盈价
    reason: str                 # AI 给出的交易理由
    confidence: float           # 置信度 0-1
    risk_level: Literal["low", "medium", "high"]
```

示例解析：
- "买入1手螺纹钢主力合约" → `{action: "buy", symbol: "rb2501", quantity: 1, order_type: "market"}`
- "以3500限价卖出2手铁矿石" → `{action: "sell", symbol: "i2501", quantity: 2, price: 3500, order_type: "limit"}`
- "帮我在币安买入0.1个BTC" → `{action: "buy", symbol: "BTCUSDT", exchange: "binance", quantity: 0.1}`

#### 2.2.2 Risk Guard

多层风控机制：

1. **硬性规则**（不可绕过）：
   - 单笔最大金额限制
   - 单日最大交易次数
   - 最大持仓比例
   - 禁止交易品种列表

2. **软性规则**（可配置是否需要确认）：
   - 大额交易需人工确认
   - 非常规时段交易警告
   - 连续亏损后暂停建议

3. **AI 风控**：
   - LLM 评估交易合理性
   - 与当前市场环境对比
   - 历史类似交易回顾

#### 2.2.3 Direct Order API

新增直接下单接口，绕过策略子进程：

```
POST /api/v1/ai-trading/execute
{
    "intent": { ... },
    "gateway_id": "...",
    "confirm": true,
    "dry_run": false
}
```

### 2.3 安全设计

1. **默认模拟模式**：首次使用默认连接模拟交易账户
2. **双重确认**：实盘交易默认需要用户确认
3. **金额限制**：可配置单笔/单日最大交易金额
4. **审计日志**：所有 AI 交易决策完整记录
5. **紧急停止**：一键停止所有 AI 交易

---

## 3. 实施计划

### Phase 1: 后端核心（AI Trading Agent Service）

1. 创建 `app/services/ai_trading_service.py` — AI 交易核心服务
2. 创建 `app/schemas/ai_trading.py` — 交易意图/指令/结果 Schema
3. 创建 `app/services/trading_intent_parser.py` — 自然语言→交易意图解析
4. 创建 `app/services/trading_risk_guard.py` — 风控规则引擎
5. 创建 `app/services/direct_order_service.py` — 直接下单服务（对接 bt_api_py）
6. 创建 `app/api/ai_trading.py` — AI 交易 API 路由
7. 创建 `app/models/ai_trading.py` — 交易日志 ORM 模型

### Phase 2: AI Copilot 集成

8. 扩展 `ai_chat_service.py` — 添加 `trading_execution` 模式
9. 更新 `kb_chat_service.py` — 支持交易模式路由
10. 创建交易确认流程（WebSocket 推送确认请求）

### Phase 3: 前端交互

11. 扩展 `AIChatPage.vue` — 添加"交易执行"模式 Tab
12. 创建交易确认对话框组件
13. 创建交易执行状态卡片
14. 创建 AI 交易历史面板

### Phase 4: 高级功能

15. 交易反思机制（执行后 AI 分析）
16. 交易策略记忆（学习用户偏好）
17. 多轮对话交易（上下文理解）
18. 条件单支持（"如果BTC跌到6万就买入"）

---

## 4. 技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| LLM 调用方式 | 复用现有 AI_CHAT_BASE_URL | 统一配置，无需额外部署 |
| 交易指令格式 | 结构化 JSON（类似 strategy_draft） | 与现有 Copilot 模式一致 |
| 网关通信 | 直接调用 bt_api_py Python API | 避免 ZMQ 子进程复杂度 |
| 风控引擎 | 规则 + LLM 混合 | 硬性规则保底，LLM 提供智能判断 |
| 确认机制 | WebSocket 推送 + 前端弹窗 | 实时性好，用户体验流畅 |
| 交易日志 | 数据库持久化 | 审计需求，支持回溯分析 |

---

## 5. 风险与约束

1. **LLM 准确性**：自然语言解析可能出错，必须有确认环节
2. **网络延迟**：LLM 调用 + 网关通信可能导致滑点
3. **资金安全**：必须有硬性风控规则，不能完全依赖 AI
4. **合规性**：需要完整的审计日志
5. **bt_api_py 依赖**：需要确认 bt_api_py 支持同步/异步直接下单

---

## 6. 验收标准

1. 用户可以用自然语言描述交易意图，AI 正确解析
2. 模拟交易模式下可以直接执行
3. 实盘模式下需要用户确认
4. 风控规则正确拦截超限交易
5. 交易执行结果实时反馈
6. 完整的交易日志可查询
