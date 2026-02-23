# Story 1.3: 迁移基础性能指标

Status: done

## Story

As a **量化交易者**,
I want **系统使用 fincore 计算基础性能指标**,
so that **获得与行业标准一致的可靠结果**.

## Acceptance Criteria

1. **Given** FincoreAdapter 基础架构已实现，**When** 运行回测任务，**Then** Sharpe Ratio 通过 fincore 计算
2. Maximum Drawdown 通过 fincore 计算
3. Total Returns 通过 fincore 计算
4. Annual Returns 通过 fincore 计算
5. Win Rate 通过 fincore 计算
6. 计算结果存储到 backtest_results 表
7. API 响应返回 fincore 计算的指标
8. 回归测试验证新结果与手动计算在可接受误差范围内（< 0.01%）

## Tasks / Subtasks

- [x] **Task 1: 更新回测服务使用 FincoreAdapter** (AC: #1-5)
  - [x] Subtask 1.1: 在 `backtest_service.py` 中导入 FincoreAdapter
  - [x] Subtask 1.2: 修改结果计算逻辑使用 FincoreAdapter (use_fincore=True)
  - [x] Subtask 1.3: 确保所有基础指标通过适配器计算
- [x] **Task 2: 更新数据库模型存储 fincore 指标** (AC: #6)
  - [x] Subtask 2.1: 在 backtest_results 表中添加字段标记使用 fincore
  - [x] Subtask 2.2: 存储计算来源 (manual/fincore)
  - [x] Subtask 2.3: 创建数据库迁移脚本
- [x] **Task 3: 更新 API 响应** (AC: #7)
  - [x] Subtask 3.1: 更新 backtest schemas 包含 fincore 指标
  - [x] Subtask 3.2: 确保响应包含计算来源标识
- [x] **Task 4: 创建回归测试** (AC: #8)
  - [x] Subtask 4.1: 创建对比测试验证 fincore 与手动计算一致性
  - [x] Subtask 4.2: 验证误差在可接受范围内 (< 0.01%)
  - [x] Subtask 4.3: 记录测试结果

## Dev Notes

### Previous Story Intelligence

**Story 1.2 完成记录:**
- FincoreAdapter 类已创建，包含 5 个指标方法
- 默认 use_fincore=False 保持向后兼容
- 26 个测试全部通过

### Architecture Intelligence

**集成文件:**
- `src/backend/app/services/backtest_service.py` - 回测服务
- `src/backend/app/models/backtest.py` - 数据模型
- `src/backend/app/schemas/backtest.py` - API 模式

**策略:**
- 首先创建新的测试用例验证 fincore 计算正确性
- 然后修改服务层代码
- 最后更新 API 响应

### Implementation Guardrails

**DO:**
- 使用 FincoreAdapter(use_fincore=True) 启用 fincore 计算
- 创建对比测试验证一致性
- 保留手动计算代码作为备份
- 记录计算来源

**DON'T:**
- 不要在启用 fincore 前删除手动计算代码
- 不要假设 fincore 可用（添加错误处理）
- 不要破坏现有 API 响应格式

### Testing Strategy

**新增测试:** `tests/test_fincore_integration.py`

**对比测试:**
- 计算 fincore 和手动计算的结果
- 验证差异 < 0.01%
- 边界条件测试

## References

- **PRD**: [Source: _bmad-output/planning-artifacts/prd.md#FR24]
- **Architecture**: [Source: _bmad-output/planning-artifacts/architecture.md#Fincore Integration]
- **Epic 1 Stories**: [Source: _bmad-output/planning-artifacts/epics.md#Epic 1]
- **Previous Story**: [Source: _bmad-output/implementation-artifacts/1-2-adapter-pattern.md]

## Dev Agent Record

### Agent Model Used

_(待开发时填写)_

### Debug Log References

_(待开发时填写)_

### Completion Notes List

_(待开发时填写)_

### File List

_(待开发时填写)_
