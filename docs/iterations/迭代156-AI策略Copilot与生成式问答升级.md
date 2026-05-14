# 迭代156：AI策略Copilot与生成式问答升级

## 1. 这轮为什么要做

对“世界上一流的 AI 量化交易管理平台”这个目标来说，当前项目最明显的短板不是界面，而是 AI 助手的真实性能边界：

- 前端叫“AI 助手”，但后端实际上只是返回知识库里最相近的一段文本
- 不支持显式的策略构思 / 策略生成 / 策略审查工作流
- 会话服务存在用户归属校验和删除返回值问题

这会直接影响平台可信度。

## 2. 本轮目标

把 AI 助手升级成一个可渐进增强的策略 Copilot：

1. 没有模型配置时，明确降级成检索问答
2. 有模型配置时，支持基于知识库上下文做结构化生成
3. 前端显式提供“策略构思 / Backtrader策略生成 / 策略审查”模式
4. 文档补齐，其他人能立刻知道新增了什么、怎么开

## 3. 已完成内容

### WP1：生成式 AI Provider 接入

- 新增 [ai_chat_service.py](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/backend/app/services/ai_chat_service.py)
- 新增 `AI_CHAT_*` 配置项
- 支持通过兼容 `chat/completions` 的模型端点生成答案

状态：已完成

### WP2：RAG 能力改造

- [rag_service.py](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/backend/app/services/rag_service.py)
  - 先检索，再决定是否走生成式回答
  - 无模型时给出明确的降级说明
  - 支持按模式生成不同风格的输出

状态：已完成

### WP3：AI 聊天服务安全修复

- [kb_chat_service.py](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/backend/app/services/kb_chat_service.py)
  - 修复历史会话读取未按用户归属校验的问题
  - 修复删除会话恒返回成功的问题
  - 新建会话标题按模式自动命名

状态：已完成

### WP4：前端 AI Copilot 模式化

- [AIChatPage.vue](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/frontend/src/views/AIChatPage.vue)
- [kbChat.ts](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/frontend/src/api/kbChat.ts)
- [kbChat.ts](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/frontend/src/stores/kbChat.ts)

新增：

- 知识问答
- 策略构思
- Backtrader策略生成
- 策略审查
- 深度模式
- `strategy_draft` 一键保存到策略中心

状态：已完成

### WP5：文档补齐

- 新增 [AI_STRATEGY_COPILOT.md](/Users/yunjinqi/Documents/new_projects/backtrader_web/docs/AI_STRATEGY_COPILOT.md)
- 更新 [INDEX.md](/Users/yunjinqi/Documents/new_projects/backtrader_web/docs/INDEX.md)
- 更新 [README.md](/Users/yunjinqi/Documents/new_projects/backtrader_web/README.md)

状态：已完成

### WP6：结构化策略草案契约

- 后端响应新增 `strategy_draft`
- 前端可以直接消费 `name / description / code / params / category`
- 为后续自动创建工作区单元保留了 `suggested_timeframe` 等结构化字段

状态：已完成

## 4. 这轮没有做但应该继续的内容

1. 把策略生成结果直接写入策略创建流程
2. 把结构化草案继续推进到工作区单元自动创建
3. 打通 `bt_api_py` 场景的编排接口
4. 增加 AI 生成质量验证与回归测试

## 5. 对平台演进的意义

这一轮的价值不在于“接了一个模型接口”，而在于把平台从“文档检索页”往“真实策略 Copilot”推进了一步：

- 用户知道当前是问答、构思、生成还是审查
- 平台知道何时该生成，何时只能降级
- 研发团队知道功能边界和下一步接入口
