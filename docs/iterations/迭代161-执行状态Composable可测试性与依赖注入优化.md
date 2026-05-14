# 迭代161 - 执行状态Composable可测试性与依赖注入优化

## 背景

上一轮已经把 AI 聊天页中的执行状态逻辑抽到了 composable：

- [useStrategyDraftWorkspaceExecution.ts](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/frontend/src/composables/useStrategyDraftWorkspaceExecution.ts)

但当时它仍然直接依赖：

- `workspaceApi`
- `ElMessage`

这会带来两个问题：

1. 单独测试 composable 成本高
2. 后续如果要替换执行实现或消息提示层，不够灵活

## 本轮优化

### 1. 为 composable 引入依赖注入

现在 `useStrategyDraftWorkspaceExecution` 支持可选依赖：

- `api`
- `notifier`

默认仍然使用现有：

- `workspaceApi`
- `ElMessage`

但测试场景和后续扩展场景可以注入自定义实现。

### 2. 增加 composable 独立测试

新增测试文件：

- [useStrategyDraftWorkspaceExecution.test.ts](/Users/yunjinqi/Documents/new_projects/backtrader_web/src/frontend/src/test/composables/useStrategyDraftWorkspaceExecution.test.ts)

当前覆盖：

- 添加执行状态后的基础落库行为
- 回测完成后的自动报告与自动分析
- 回测未完成时的报告生成告警

## 质量收益

1. composable 从“可用”提升为“可验证”
2. 页面层不再绑定具体 API/提示实现
3. 后续做更复杂的执行编排时更容易扩展

## 当前边界

1. 还没有把 AI 复盘规则进一步拆成纯函数模块
2. composable 的测试还没有覆盖所有异常路径
3. 还没有对轮询清理做更细的资源级测试

## 下一步建议

1. 把复盘分析逻辑拆成纯函数模块并单独测试
2. 给异常路径和轮询清理补更细的测试
3. 继续清理 `AIChatPage.vue` 中的工作区弹窗状态逻辑
