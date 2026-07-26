# AI Strategy Copilot

## 目标

把现有知识库问答能力升级成面向量化研究与策略实现的 AI Copilot，而不是只返回一段检索命中的原文。

本轮完成后，AI 助手具备两层能力：

1. `知识库检索层`
   - 继续负责从知识库中找出最相关文档片段
2. `生成式 Copilot 层`
   - 当配置了兼容的聊天模型端点后，基于检索上下文生成结构化回答

如果没有配置生成式模型，系统会明确降级成“返回最相关片段”，而不是假装自己已经具备完整 AI 生成能力。

## 已新增的对话模式

AI 聊天页现在支持以下模式：

- `知识问答`
  - 面向文档理解、平台能力问答、配置项查询
- `策略构思`
  - 把一句话策略想法扩展成研究方案、信号设计、风控和回测计划
- `Backtrader策略生成`
  - 把自然语言需求转换成面向 Backtrader / 平台接入的策略代码骨架
- `策略审查`
  - 从逻辑、风控、数据与回测偏差角度审查策略描述

## 后端能力升级

### 1. 生成式 AI Provider 接入

新增了一个可配置的 AI 生成层：

- 文件: [ai_chat_service.py](/Users/yunjinqi/Documents/new_projects/ai-for-investor/src/backend/app/services/ai_chat_service.py)
- 作用:
  - 调用兼容 `chat/completions` 的模型端点
  - 把知识库检索结果拼装成上下文
  - 按对话模式注入不同的回答模板

### 2. RAG 降级路径更清晰

文件: [rag_service.py](/Users/yunjinqi/Documents/new_projects/ai-for-investor/src/backend/app/services/rag_service.py)

当前行为：

- 配置了 AI 模型:
  - 返回结构化生成答案
- 未配置 AI 模型:
  - 返回最相关知识库片段
  - 明确提示当前仍是降级模式

这让平台具备了“可上线、可解释、可渐进增强”的 AI 路线。

### 3. AI 会话安全与一致性修复

文件: [kb_chat_service.py](/Users/yunjinqi/Documents/new_projects/ai-for-investor/src/backend/app/services/kb_chat_service.py)

修复内容：

- `get_history` 现在按 `conversation_id + user_id` 校验归属，避免跨用户读取
- `delete_conversation` 现在按用户归属删除，不再错误返回恒为成功
- 新建会话标题会按模式自动带上前缀，便于区分“知识问答 / 策略生成 / 审查”

## 前端体验升级

### AI 聊天页

文件: [AIChatPage.vue](/Users/yunjinqi/Documents/new_projects/ai-for-investor/src/frontend/src/views/AIChatPage.vue)

新增：

- 对话模式切换
- 深度模式开关
- 按模式动态变化的快捷提示
- 面向策略生成的输入占位与空态文案
- 当返回 `strategy_draft` 时，可一键保存为“我的策略”
- 当返回 `strategy_draft` 时，可选择“添加到工作区”，直接生成研究工作区单元
- 已添加到工作区的草稿，可直接“一键回测”
- 回测完成后，可在 AI 聊天页直接生成工作区报告摘要
- 回测完成后会自动刷新状态并自动生成工作区报告
- 生成报告后会自动给出 AI 复盘结论与下一步优化建议

### 专用 Strategy Copilot API

文件：

- [strategy.py](/Users/yunjinqi/Documents/new_projects/ai-for-investor/src/backend/app/api/strategy.py)
- [strategy_service.py](/Users/yunjinqi/Documents/new_projects/ai-for-investor/src/backend/app/services/strategy_service.py)

新增接口：

- `POST /api/v1/strategy/copilot/draft`
  - 输入自然语言需求，返回结构化 `strategy_draft`
- `POST /api/v1/strategy/copilot/workspaces/{workspace_id}/units`
  - 把 `strategy_draft` 持久化为策略，并可直接创建研究工作区单元
- `POST /api/v1/strategy/copilot/workspaces/{workspace_id}/backtest`
  - 把 `strategy_draft` 持久化为策略
  - 创建研究工作区单元
  - 触发回测任务并返回运行状态快照

### API / Store 契约

文件：

- [kbChat.ts](/Users/yunjinqi/Documents/new_projects/ai-for-investor/src/frontend/src/api/kbChat.ts)
- [kbChat.ts](/Users/yunjinqi/Documents/new_projects/ai-for-investor/src/frontend/src/stores/kbChat.ts)

新增：

- `assistant_mode` 请求参数
- 模式化响应类型
- 发送失败时的前端兜底提示

## 配置方法

在 [src/backend/.env.example](/Users/yunjinqi/Documents/new_projects/ai-for-investor/src/backend/.env.example) 中已新增配置项：

```bash
AI_CHAT_ENABLED=false
AI_CHAT_BASE_URL=
AI_CHAT_API_KEY=
AI_CHAT_MODEL=
AI_CHAT_TIMEOUT=120
AI_CHAT_TEMPERATURE=0.2
```

说明：

- `AI_CHAT_ENABLED`
  - 是否启用生成式 AI 回答
- `AI_CHAT_BASE_URL`
  - 兼容 `chat/completions` 的模型服务地址前缀
- `AI_CHAT_API_KEY`
  - 对应模型服务密钥
- `AI_CHAT_MODEL`
  - 模型名

## 推荐使用方式

### 一句话生成策略

1. 进入 `/ai-chat`
2. 选择一个包含策略/平台文档的知识库
3. 切换到 `Backtrader策略生成`
4. 输入自然语言需求，例如：

```text
请帮我生成一个 20 日突破买入、10 日低点止损、ATR 控制仓位的趋势策略
```

5. AI 返回 `strategy_draft` 后，可以：
   - 点击“保存为策略”
   - 或点击“添加到工作区”
6. 如果选择“添加到工作区”，可以直接指定研究工作区、标的、周期和分组名
7. 生成的代码草案会进入策略中心，并可同步落到研究工作区单元，供后续回测
8. 已添加的草稿支持“一键回测”，并可在完成后直接生成工作区报告
9. 回测完成后，页面会自动产出报告摘要和 AI 复盘建议

### 做策略方案拆解

切换到 `策略构思`，输入：

```text
我想做一个基于成交量放大确认的均线趋势策略
```

### 做策略复盘和审查

切换到 `策略审查`，输入：

```text
请审查这个动量轮动策略是否存在未来函数、过拟合和仓位风险
```

## 当前边界

目前这仍然不是最终形态，主要边界有三条：

1. 生成式能力依赖外部模型端点配置
2. 生成结果已经可以落到“策略中心 / 研究工作区单元”，并可直接触发回测与自动报告
3. 还没有把生成结果自动编排到 `bt_api_py` 更细粒度执行流程和更深入的结果解释闭环

## 下一步建议

下一轮优先级建议：

1. 把 AI 生成结果与 `bt_api_py` 执行入口进一步打通
2. 增加基于回测明细的更细粒度 AI 诊断
3. 增加 AI 编排链路的端到端自动化测试
