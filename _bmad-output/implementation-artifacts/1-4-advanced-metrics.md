# Story 1.4: 迁移高级分析指标

Status: done

## Story

As a **量化研究员**,
I want **系统使用 fincore 计算高级分析指标**,
so that **获得深入的绩效归因分析**.

## Acceptance Criteria

1. **Given** 基础性能指标已迁移到 fincore，**When** 请求分析报告，**Then** 月度回报分解通过 fincore 计算
2. 逐笔交易归因通过 fincore 计算
3. 权益曲线数据点通过 fincore 生成
4. 回撤曲线数据点通过 fincore 生成
5. 交易级别指标（盈亏比、平均持仓时间）通过 fincore 计算
6. `/api/v1/analytics/*` 端点返回 fincore 计算的结果
7. 导出报告（PDF/Excel）包含 fincore 计算的指标

## Tasks / Subtasks

- [x] **Task 1: 扩展 FincoreAdapter 添加高级指标方法** (AC: #1-5)
  - [x] Subtask 1.1: 添加月度回报计算方法
  - [x] Subtask 1.2: 添加盈亏比计算方法
  - [x] Subtask 1.3: 添加平均持仓时间计算方法
  - [x] Subtask 1.4: 添加权益曲线归因方法
- [x] **Task 2: 更新 analytics_service.py** (AC: #6)
  - [x] Subtask 2.1: 导入 FincoreAdapter
  - [x] Subtask 2.2: 修改分析方法使用适配器
  - [x] Subtask 2.3: 确保所有高级指标通过适配器计算
- [x] **Task 3: 更新 API schemas** (AC: #6)
  - [x] Subtask 3.1: 更新 analytics schemas 包含 metrics_source
  - [x] Subtask 3.2: 确保响应包含计算来源标识
- [x] **Task 4: 创建高级指标测试** (AC: #7)
  - [x] Subtask 4.1: 创建测试验证高级指标计算
  - [x] Subtask 4.2: 验证一致性
  - [x] Subtask 4.3: 测试报告生成

## Dev Notes

### Previous Story Intelligence

**Story 1.3 完成记录:**
- FincoreAdapter 已集成到 backtest_service.py
- 47 个测试全部通过
- metrics_source 字段已添加到数据库模型
- 基础指标已通过统一接口计算

### Architecture Intelligence

**集成文件:**
- `src/backend/app/services/analytics_service.py` - 分析服务
- `src/backend/app/api/analytics.py` - 分析 API
- `src/backend/app/schemas/analytics.py` - 分析模式

**策略:**
- 扩展 FincoreAdapter 添加高级指标方法
- 更新 analytics_service 使用适配器
- 保持与现有 API 的兼容性

### Implementation Guardrails

**DO:**
- 扩展 FincoreAdapter 添加新方法
- 保持一致的计算模式
- 添加完整的测试覆盖
- 记录指标来源

**DON'T:**
- 不要破坏现有分析 API
- 不要改变现有响应格式
- 不要假设数据完整性

### Testing Strategy

**新增测试:** `tests/test_fincore_advanced_metrics.py`

**测试覆盖:**
- 月度回报计算
- 盈亏比计算
- 平均持仓时间计算
- 权益曲线归因
- 回撤曲线计算

## References

- **PRD**: [Source: _bmad-output/planning-artifacts/prd.md#FR37]
- **Architecture**: [Source: _bmad-output/planning-artifacts/architecture.md#Fincore Integration]
- **Epic 1 Stories**: [Source: _bmad-output/planning-artifacts/epics.md#Epic 1]
- **Previous Story**: [Source: _bmad-output/implementation-artifacts/1-3-basic-metrics.md]

## Dev Agent Record

### Agent Model Used

_(待开发时填写)_

### Debug Log References

_(待开发时填写)_

### Completion Notes List

_(待开发时填写)_

### File List

_(待开发时填写)_
