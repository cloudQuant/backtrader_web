# 迭代160 - AIChat执行状态逻辑解耦与质量优化

## 背景

随着 AI 策略闭环能力不断叠加，`AIChatPage.vue` 逐渐同时承担了：

1. 聊天界面渲染
2. 策略草稿保存
3. 工作区单元接入
4. 回测触发
5. 报告生成
6. 自动轮询
7. 报告复盘解释

这导致组件职责过多，后续维护和扩展成本上升。

## 本轮优化

### 1. 抽离执行状态 composable

新增：

- [useStrategyDraftWorkspaceExecution.ts](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/frontend/src/composables/useStrategyDraftWorkspaceExecution.ts)

职责集中到 composable：

- 工作区执行状态存储
- 回测任务触发
- 自动轮询
- 报告生成
- 报告复盘分析
- 轮询资源清理

### 2. 简化 AIChatPage.vue

更新：

- [AIChatPage.vue](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/frontend/src/views/AIChatPage.vue)

优化点：

- 组件保留页面编排职责
- 执行状态和自动报告逻辑从页面移除
- 减少页面内大段状态管理与副作用逻辑

## 质量收益

本轮优化后的直接收益：

1. `AIChatPage.vue` 认知负担下降
2. 执行状态逻辑有了单独归属点
3. 后续若把同一能力复用到其它页面，可以直接复用 composable
4. 自动报告与复盘逻辑更容易继续演进

## 当前边界

1. 复盘分析仍是规则化解释
2. composable 目前仍面向 AI 策略草稿这一单一场景
3. 还没有对 composable 单独补专项测试

## 下一步建议

1. 给 composable 增加独立测试
2. 继续把策略草稿接入后的表单状态也拆分出去
3. 将规则化复盘升级为模型驱动复盘
