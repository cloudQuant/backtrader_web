# 迭代150：Strategy 安全与状态管理优化计划

## 1. 背景与目标

在完成迭代143-149的持续质量优化后，当前项目整体规范性已有明显提升，但在本轮审查中仍识别出一组更偏“正确性”和“可维护性”的问题，主要集中在 `strategy` 相关链路：

1. **接口安全边界仍有缺口**：`strategy` 详情接口存在按 ID 直接读取的路径，缺少用户所有权约束
2. **服务层权限校验逻辑重复**：`StrategyService` 中多处重复查询并校验归属，维护成本偏高
3. **前端状态管理不一致**：`strategy store` 的部分异步操作未统一维护 `loading` 状态
4. **列表/详情状态同步不足**：创建、更新、删除后，`strategies` / `total` / `currentStrategy` 之间可能出现不同步
5. **测试保护不够聚焦**：缺少“跨用户越权读取”回归测试，以及前端 store 状态同步测试

本轮迭代聚焦于：

- 修复 `strategy` 详情接口越权读取风险
- 抽取统一的所有权校验逻辑，降低重复代码
- 统一前端 `strategy store` 的异步加载模式
- 强化后端安全回归测试与前端状态管理测试

---

## 2. 项目状态评估

### 2.1 本轮识别的关键问题

| 问题 | 优先级 | 影响 | 说明 |
|------|--------|------|------|
| Strategy详情越权读取 | P1 | 安全性 | 已登录用户可通过ID读取他人策略详情 |
| 服务层归属校验重复 | P2 | 可维护性 | `update/delete/get` 存在重复的归属判断 |
| Store加载态不一致 | P2 | 交互一致性 | `fetchTemplates/create/update/delete/fetchStrategy` 未统一维护 `loading` |
| Store状态同步不完整 | P2 | 数据一致性 | 删除/更新后 `total` 与 `currentStrategy` 可能滞后 |
| 测试缺口 | P2 | 回归风险 | 缺少针对安全边界与状态同步的测试 |

### 2.2 本轮分析结论

#### 结论1：`strategy` 详情接口需要与更新/删除接口保持同等的归属校验

当前 `update_strategy` / `delete_strategy` 已按 `user_id` 控制访问，但 `get_strategy` 详情链路未严格复用同一所有权规则，存在行为不一致和潜在安全风险。

#### 结论2：归属校验应下沉到服务层统一封装

相比在 API 层分别重复拼装校验逻辑，更适合在 `StrategyService` 内部提供统一的 `_get_owned_strategy` 帮助方法，以保证：

- 读取、更新、删除遵循统一边界
- 权限规则只维护一处
- 后续新增接口更容易复用

#### 结论3：前端 store 应统一使用同一种异步状态模式

`backtest store` 已经有统一 loading 管理思路，而 `strategy store` 中只有部分操作维护 `loading`。这会导致：

- 某些页面请求期间没有加载反馈
- 异步失败后状态恢复行为不完全一致
- 测试语义分散，不利于长期维护

#### 结论4：`strategies` / `total` / `currentStrategy` 应视为同一聚合状态

用户在“列表页 → 详情 → 编辑/删除”链路中，若 store 不同步维护上述状态，会造成：

- 删除后详情仍残留旧对象
- 创建后总数不准确
- 更新后详情与列表展示不一致

---

## 3. 工作包定义

### WP1：Strategy 访问控制修复（P1）

#### 目标
修复 `GET /api/v1/strategy/{strategy_id}` 对他人策略详情的越权读取问题。

#### 执行策略
1. 将详情读取改为显式传入当前用户 ID
2. 未拥有资源时统一返回 404，避免暴露资源存在性
3. 增加跨用户读取的回归测试

#### 验收标准
- 非所有者访问他人策略详情返回 404
- 原有所有者读取流程保持可用

---

### WP2：StrategyService 重复权限逻辑收敛（P2）

#### 目标
抽取统一的策略归属校验逻辑，减少重复实现。

#### 执行策略
1. 在服务层新增 `_get_owned_strategy` 方法
2. `get/update/delete` 统一复用该方法
3. 保持 API 层返回契约不变

#### 验收标准
- 权限相关逻辑集中到单一帮助方法
- 既有接口语义不变

---

### WP3：前端 Strategy Store 状态管理统一（P2）

#### 目标
统一 `strategy store` 的异步加载模式与状态同步行为。

#### 执行策略
1. 引入统一的 `withLoading` 包装
2. 让 `fetchTemplates/create/update/delete/fetchStrategy` 全部纳入 loading 管理
3. 在新增、更新、删除时同步维护 `strategies`、`total`、`currentStrategy`

#### 验收标准
- 所有核心异步操作结束后 `loading` 能正确恢复
- 更新/删除后列表与详情状态一致
- 创建后总数正确增加

---

### WP4：回归测试补强（P2）

#### 目标
为本轮改动提供最小而有效的自动化回归保护。

#### 执行策略
1. 后端补充跨用户读取策略详情测试
2. 前端补充 strategy store 的状态同步与失败恢复测试

#### 验收标准
- 新增测试能够覆盖安全边界与关键状态变化
- 相关测试可稳定通过

---

## 4. 执行计划

### 阶段1：安全修复
- [x] WP1: 修复 strategy 详情越权读取
- [x] WP2: 抽取统一的 `_get_owned_strategy` 逻辑

### 阶段2：前端状态管理优化
- [x] WP3: 为 strategy store 引入统一 loading 包装
- [x] WP3: 补齐 create/update/delete/fetchStrategy 的状态同步

### 阶段3：测试加固
- [x] WP4: 增加后端跨用户读取回归测试
- [x] WP4: 增加前端 store 状态同步与失败恢复测试

### 阶段4：验证与收尾
- [x] 运行后端定向测试
- [x] 运行前端定向测试
- [x] 回填验证结果与完成总结

---

## 5. 已实施改动

### 后端
- `src/backend/app/services/strategy_service.py`
  - 新增 `_get_owned_strategy`
  - `get_strategy` 支持传入 `user_id` 做所有权校验
  - `update_strategy` / `delete_strategy` 复用统一校验逻辑

- `src/backend/app/api/strategy.py`
  - 详情接口读取时传入 `current_user.sub`

- `src/backend/tests/test_strategy_api.py`
  - 新增“跨用户不可读取他人策略详情”的回归测试

### 前端
- `src/frontend/src/stores/strategy.ts`
  - 新增 `withLoading`
  - 统一异步操作的 loading 行为
  - 新增 `total` 与 `currentStrategy` 的同步维护

- `src/frontend/src/test/stores/strategy.test.ts`
  - 补充详情获取、更新同步、删除同步、失败恢复等测试

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 安全修复改变既有接口行为 | 中 | 保持“未找到/无权限”统一返回404，减少客户端差异 |
| 前端 store 行为调整影响页面测试 | 中 | 只在 store 内部收敛模式，尽量不改页面调用约定 |
| 测试 mock 与真实 store 状态不一致 | 低 | 补充围绕 store 本身的单测验证 |

---

## 7. 成功指标

| 指标 | 当前问题 | 目标 |
|------|----------|------|
| Strategy详情访问控制 | 存在越权读取风险 | 所有权校验完整生效 |
| 权限校验重复逻辑 | 多处分散 | 集中到单一帮助方法 |
| Strategy store loading 一致性 | 不完整 | 核心异步操作全覆盖 |
| 状态同步正确性 | 存在滞后风险 | 列表/总数/详情保持一致 |
| 针对性测试覆盖 | 不足 | 新增安全与状态同步回归测试 |

---

**创建时间**: 2026-03-26
**完成时间**: 2026-03-26
**状态**: ✅ 已完成

---

## 8. 验证结果与完成总结

### 验证结果

- ✅ 后端 API 定向测试：`tests/test_strategy_api.py` 6 passed
- ✅ 后端服务层定向测试：`tests/test_iteration113_strategy_service_coverage.py` 6 passed
- ✅ 前端 store 定向测试：`src/test/stores/strategy.test.ts` 8 passed
- ✅ 前端类型检查：`npm run typecheck` 通过

### 本轮收益

- ✅ 修复了 `strategy` 详情读取的跨用户越权访问风险
- ✅ 将策略所有权校验逻辑统一收敛到服务层内部
- ✅ 统一了 `strategy store` 的加载态管理模式
- ✅ 保证了创建、更新、删除、详情读取后的状态同步一致性

### 后续建议

- 建议继续排查其他按资源 ID 读取的接口，确认是否都采用同样的所有权校验模式
- 建议将前端其他 store（如 `simulation`、`portfolioUi`）也逐步统一到相同的异步状态管理模式
