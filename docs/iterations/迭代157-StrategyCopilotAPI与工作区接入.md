# 迭代157 - Strategy Copilot API与工作区接入

## 目标

把 AI 生成的 `strategy_draft` 从聊天结果推进到可执行资产：

1. 提供独立于 `kb_chat` 的专用 `Strategy Copilot API`
2. 支持把 AI 草稿直接添加到研究工作区
3. 补齐前后端测试与文档，让外部协作者知道本轮做了什么

## 本轮完成

### 1. 专用 Strategy Copilot API

新增后端接口：

- `POST /api/v1/strategy/copilot/draft`
  - 输入自然语言策略需求
  - 输出结构化 `strategy_draft`
- `POST /api/v1/strategy/copilot/workspaces/{workspace_id}/units`
  - 把 `strategy_draft` 持久化为策略
  - 直接创建研究工作区单元

涉及文件：

- [strategy.py](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/backend/app/api/strategy.py)
- [strategy_service.py](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/backend/app/services/strategy_service.py)
- [strategy.py](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/backend/app/schemas/strategy.py)

### 2. AI 草稿添加到工作区

AI 聊天页新增“添加到工作区”流程：

- 选择研究工作区
- 填写标的代码 / 标的名称
- 选择周期
- 指定分组名
- 保存后自动创建工作区单元

如果该草稿之前没有保存过策略，后端会先创建策略，再创建工作区单元。

涉及文件：

- [AIChatPage.vue](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/frontend/src/views/AIChatPage.vue)
- [strategy.ts](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/frontend/src/api/strategy.ts)

### 3. 测试补齐

新增覆盖：

- 后端 `strategy copilot draft` 生成
- 后端 `strategy draft -> workspace unit` 落库
- 前端 AI 聊天页“添加到工作区”交互

涉及文件：

- [test_strategy_api.py](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/backend/tests/test_strategy_api.py)
- [AIChatPage.test.ts](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/frontend/src/test/views/AIChatPage.test.ts)

## 结果

本轮之后，平台已经支持：

1. 一句话生成 Backtrader 策略草稿
2. 一键保存到策略中心
3. 可选直接添加到研究工作区

## 当前边界

1. 还没有直接把工作区单元送入 `bt_api_py` 执行链路
2. 还没有做“一句话 -> 自动创建工作区 -> 自动回测”的全自动编排
3. `strategy_draft` 仍是代码草稿，用户通常还需要做一轮审阅和调整

## 下一步建议

1. 从工作区单元继续接通回测执行入口
2. 为 `strategy_draft` 增加更强的结构化约束，方便自动编排
3. 把 AI 生成、工作区落库、执行结果串成端到端闭环
