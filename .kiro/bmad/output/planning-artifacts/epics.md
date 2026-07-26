---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
lastStep: 4
status: 'complete'
completedAt: '2026-02-23'
inputDocuments:
  - "prd.md"
  - "architecture.md"
  - "product-brief-backtrader_web-2026-02-23.md"
---

# backtrader_web - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for backtrader_web, decomposing the requirements from the PRD and Architecture requirements into implementable stories.

**Project Context:** Brownfield - Existing features complete, focusing on fincore integration and deployment documentation.

## Requirements Inventory

### Functional Requirements

#### User Management & Authentication (FR1-5)
- FR1: Users can register a new account with username, email, and password
- FR2: Users can log in with username and password to receive an authentication token
- FR3: Users can change their password
- FR4: Users can view their own profile information
- FR5: Admin users can manage user permissions and access control

#### Strategy Management (FR6-12)
- FR6: Users can create custom trading strategies with Python code
- FR7: Users can view built-in strategy templates with pre-defined parameters
- FR8: Users can update strategy code and parameter definitions
- FR9: Users can delete their own strategies
- FR10: Users can categorize strategies by type (trend, mean-reversion, etc.)
- FR11: Users can manage multiple versions of a strategy
- FR12: Users can configure strategy parameters separately from code (YAML)

#### Backtesting (FR13-19)
- FR13: Users can submit backtest tasks with selected strategy, symbol, date range, and parameters
- FR14: Users can view backtest task status and progress in real-time
- FR15: Users can view detailed backtest results including performance metrics
- FR16: Users can view equity curve and drawdown charts for backtest results
- FR17: Users can view individual trade records from backtest results
- FR18: Users can export backtest results as HTML, PDF, or Excel reports
- FR19: Users can access backtest history and compare multiple runs

#### Parameter Optimization (FR20-24)
- FR20: Users can run grid search optimization across parameter combinations
- FR21: Users can run Bayesian optimization for intelligent parameter search
- FR22: Users can view optimization results sorted by performance metrics
- FR23: Users can select optimization objective (Sharpe ratio, max drawdown, total return)
- FR24: **System calculates all performance metrics using fincore library**

#### Paper Trading (FR25-31)
- FR25: Users can create paper trading accounts with initial capital and commission settings
- FR26: Users can view account status including cash, positions, and P&L
- FR27: Users can place buy/sell orders in paper trading accounts
- FR28: Users can view open positions and unrealized P&L
- FR29: Users can view order status and execution details
- FR30: Users can view trade history for paper trading accounts
- FR31: Users can receive real-time account updates via WebSocket

#### Live Trading (FR32-36)
- FR32: Users can deploy strategies to live trading environments
- FR33: Users can monitor live trading instances in real-time
- FR34: Users can start and stop live trading instances
- FR35: Users can configure risk management rules for live trading
- FR36: Users can receive real-time trading updates via WebSocket

#### Analytics & Reporting (FR37-40)
- FR37: Users can view standardized performance metrics calculated via fincore
- FR38: Users can view monthly return breakdowns
- FR39: Users can compare performance across multiple backtests
- FR40: Users can view trade-by-trade performance attribution

#### Monitoring & Alerts (FR41-45)
- FR41: Users can create custom alert rules based on account, position, or strategy conditions
- FR42: Users can configure alert severity levels (info, warning, error, critical)
- FR43: Users can receive alert notifications in real-time
- FR44: Users can acknowledge and resolve alerts
- FR45: Users can configure multiple notification channels for alerts

#### Data Management (FR46-48)
- FR46: System stores all user data with encryption at rest
- FR47: System logs all user actions with timestamps for audit purposes
- FR48: System maintains data isolation between users unless explicitly shared

### NonFunctional Requirements

#### Performance (NFR-PERF)
- NFR-PERF-01: API response time < 500ms (P95) for standard API calls
- NFR-PERF-02: WebSocket latency < 1s for real-time updates
- NFR-PERF-03: Backtest completion < 5 minutes for standard 1-year backtest
- NFR-PERF-04: Report generation < 30s for PDF/Excel export

#### Security (NFR-SEC)
- NFR-SEC-01: Sensitive data encrypted at rest (AES-256)
- NFR-SEC-02: TLS 1.3 for all API communications
- NFR-SEC-03: bcrypt password hashing with minimum 8 rounds
- NFR-SEC-04: JWT tokens with configurable expiration (max 24h)
- NFR-SEC-05: Role-Based Access Control (RBAC)
- NFR-SEC-06: Audit logging for all user actions

#### Reliability (NFR-REL)
- NFR-REL-01: 99.5% uptime during market hours
- NFR-REL-02: ACID compliance for financial transactions
- NFR-REL-03: Graceful degradation on component failure
- NFR-REL-04: Daily automated backups with 30-day retention

#### Data Accuracy (NFR-ACC)
- NFR-ACC-01: All metrics calculated via fincore library
- NFR-ACC-02: Consistency checks against industry standards
- NFR-ACC-03: Minimum 6 decimal places for financial calculations

#### Integration (NFR-INT)
- NFR-INT-01: 100% Backtrader ecosystem compatibility
- NFR-INT-02: Extensible architecture for multiple data sources
- NFR-INT-03: Support for multiple broker execution APIs
- NFR-INT-04: WebSocket auto-reconnection with < 5s recovery

#### Maintainability (NFR-MAINT)
- NFR-MAINT-01: Maintain ≥ 100% code coverage
- NFR-MAINT-02: Auto-generated OpenAPI documentation
- NFR-MAINT-03: Google-style docstrings for all modules

### Additional Requirements

#### Technical Requirements from Architecture
- **fincore Integration:** Use Adapter Pattern to replace all manual metric calculations in `backtest_analyzers.py`
- **Integration Point:** `src/backend/app/services/backtest_analyzers.py` is the primary integration location
- **Caching Strategy:** No caching - always recalculate for accuracy
- **Deployment Method:** pip install + systemd/supervisor for process management

#### Infrastructure Requirements
- WebSocket real-time push (backtest progress, account updates, live trading)
- Async task processing (backtests, optimizations)
- Health monitoring and automatic alerts

#### Security Requirements
- Strategy code encryption at rest (AES-256)
- JWT authentication + RBAC permission control
- Audit logging for all user actions

### FR Coverage Map

| FR Category | FR Range | Implementation Status | Epic Assignment |
|-------------|----------|----------------------|-----------------|
| User Management & Authentication | FR1-5 | ✅ Complete | N/A (Existing) |
| Strategy Management | FR6-12 | ✅ Complete | N/A (Existing) |
| Backtesting | FR13-19 | ✅ Complete | Epic 1 (fincore Integration) |
| Parameter Optimization | FR20-24 | ✅ Complete | Epic 1 (fincore Integration) |
| Paper Trading | FR25-31 | ✅ Complete | N/A (Existing) |
| Live Trading | FR32-36 | ✅ Complete | N/A (Existing) |
| Analytics & Reporting | FR37-40 | 🔄 Partial | Epic 1 (fincore Integration) |
| Monitoring & Alerts | FR41-45 | ✅ Complete | N/A (Existing) |
| Data Management | FR46-48 | ✅ Complete | N/A (Existing) |

**Note:** This is a brownfield project. Most features are already implemented. Epics focus on fincore integration and deployment documentation.

## Epic List

### Epic 1: fincore 性能指标标准化

**史诗目标:** 使用 fincore 库替换所有手动金融指标计算，提供标准化、机构级的性能指标，确保与行业标准一致。

**用户价值:** 用户可以获得可信的、与行业标准一致的绩效指标，支持更准确的策略评估和比较。

**FRs covered:** FR24, FR37, FR40
**NFRs covered:** NFR-ACC-01, NFR-ACC-02, NFR-MAINT-01

**Implementation Notes:**
- 使用适配器模式确保安全过渡
- 集成点: `src/backend/app/services/backtest_analyzers.py`
- 保持与现有 API 的兼容性
- 包含验证步骤对比新旧计算结果

**Estimated Stories:** 5

---

### Epic 2: 部署与运维文档

**史诗目标:** 提供完整的部署指南和运维文档，使用户能够在 10 分钟内完成本地或服务器部署。

**用户价值:** 用户可以快速部署平台，减少从发现到使用的时间成本。

**FRs covered:** FR1-5 (部署后验证)
**NFRs covered:** NFR-SEC-01, NFR-SEC-02, NFR-REL-01, NFR-REL-04

**Implementation Notes:**
- pip install 安装指南
- 本地开发环境设置
- 生产服务器部署（systemd/supervisor）
- 配置说明（安全、数据库、日志）

**Estimated Stories:** 3

---

### Epic 3: 验证与质量保证（可选）

**史诗目标:** 确保 fincore 集成后的系统质量和性能符合预期。

**用户价值:** 用户获得可靠、准确的性能指标计算结果。

**FRs covered:** N/A (quality focused)
**NFRs covered:** NFR-MAINT-01, NFR-PERF-01/02/03/04

**Implementation Notes:**
- 回归测试套件
- 性能基准测试
- 指标准确性验证

**Estimated Stories:** 2

---

## Detailed FR Coverage Map

| FR | Description | Epic Assignment | Status |
|----|-------------|-----------------|--------|
| FR1 | User registration | Epic 2 (deployment verification) | ✅ Existing |
| FR2 | User login | Epic 2 (deployment verification) | ✅ Existing |
| FR3 | Password change | Epic 2 (deployment verification) | ✅ Existing |
| FR4 | View profile | Epic 2 (deployment verification) | ✅ Existing |
| FR5 | Admin permission management | Epic 2 (deployment verification) | ✅ Existing |
| FR6-12 | Strategy Management | N/A (existing) | ✅ Complete |
| FR13-19 | Backtesting | Epic 1 (fincore enhancement) | ✅ Existing |
| FR20-23 | Parameter Optimization | N/A (existing) | ✅ Complete |
| FR24 | **fincore metrics calculation** | **Epic 1** | 🔄 **New** |
| FR25-31 | Paper Trading | N/A (existing) | ✅ Complete |
| FR32-36 | Live Trading | N/A (existing) | ✅ Complete |
| FR37 | **Standardized metrics via fincore** | **Epic 1** | 🔄 **Enhancement** |
| FR38-39 | Monthly returns & comparison | N/A (existing) | ✅ Complete |
| FR40 | **Trade-by-trade attribution** | **Epic 1** | 🔄 **Enhancement** |
| FR41-45 | Monitoring & Alerts | N/A (existing) | ✅ Complete |
| FR46-48 | Data Management | N/A (existing) | ✅ Complete |

---

## Epic 1: fincore 性能指标标准化

**Epic Goal:** 使用 fincore 库替换所有手动金融指标计算，提供标准化、机构级的性能指标，确保与行业标准一致。

**User Value:** 用户可以获得可信的、与行业标准一致的绩效指标，支持更准确的策略评估和比较。

**FRs covered:** FR24, FR37, FR40
**NFRs covered:** NFR-ACC-01, NFR-ACC-02, NFR-MAINT-01

**Implementation Notes:**
- 使用适配器模式确保安全过渡
- 集成点: `src/backend/app/services/backtest_analyzers.py`
- 保持与现有 API 的兼容性
- 包含验证步骤对比新旧计算结果

---

### Story 1.1: 安装和配置 fincore 库

As a 开发者,
I want 安装和配置 fincore 库及其依赖,
So that 系统可以使用标准化的金融指标计算.

**Acceptance Criteria:**

**Given** clean Python 环境
**When** 执行 `pip install fincore`
**Then** fincore 库成功安装到项目虚拟环境
**And** `pyproject.toml` 文件包含 fincore 依赖声明
**And** fincore 可以成功导入并在 Python shell 中运行 `import fincore`
**And** 版本号被记录到依赖文件中
**And** 现有测试套件仍然通过（无破坏性变更）

**Requirements:** NFR-MAINT-01

---

### Story 1.2: 实现适配器模式基础架构

As a 开发者,
I want 创建 fincore 适配器模式基础架构,
So that 可以安全地逐步替换手动计算而不破坏现有功能.

**Acceptance Criteria:**

**Given** fincore 库已安装
**When** 创建 `FincoreAdapter` 类在 `backtest_analyzers.py`
**Then** 适配器类包含所有要替换的指标方法签名
**And** 每个方法都有清晰的文档字符串说明输入输出
**And** 适配器实现保留现有手动计算作为回退
**And** 单元测试验证适配器接口符合预期
**And** 现有 API 端点继续工作（向后兼容性）

**Requirements:** FR24, NFR-INT-01

---

### Story 1.3: 迁移基础性能指标

As a 量化交易者,
I want 系统使用 fincore 计算基础性能指标,
So that 获得与行业标准一致的可靠结果.

**Acceptance Criteria:**

**Given** FincoreAdapter 基础架构已实现
**When** 运行回测任务
**Then** Sharpe Ratio 通过 fincore 计算
**And** Maximum Drawdown 通过 fincore 计算
**And** Total Returns 通过 fincore 计算
**And** Annual Returns 通过 fincore 计算
**And** Win Rate 通过 fincore 计算
**And** 计算结果存储到 backtest_results 表
**And** API 响应返回 fincore 计算的指标
**And** 回归测试验证新结果与手动计算在可接受误差范围内（< 0.01%）

**Requirements:** FR24, FR37, NFR-ACC-01, NFR-ACC-02

---

### Story 1.4: 迁移高级分析指标

As a 量化研究员,
I want 系统使用 fincore 计算高级分析指标,
So that 获得深入的绩效归因分析.

**Acceptance Criteria:**

**Given** 基础性能指标已迁移到 fincore
**When** 请求分析报告
**Then** 月度回报分解通过 fincore 计算
**And** 逐笔交易归因通过 fincore 计算
**And** 权益曲线数据点通过 fincore 生成
**And** 回撤曲线数据点通过 fincore 生成
**And** 交易级别指标（盈亏比、平均持仓时间）通过 fincore 计算
**And** `/api/v1/analytics/*` 端点返回 fincore 计算的结果
**And** 导出报告（PDF/Excel）包含 fincore 计算的指标

**Requirements:** FR37, FR40, NFR-ACC-03

---

### Story 1.5: 验证和清理

As a 开发者,
I want 移除旧的手动计算代码,
So that 简化代码库并减少维护负担.

**Acceptance Criteria:**

**Given** 所有指标已通过 fincore 计算并验证
**When** 执行代码清理任务
**Then** 所有手动指标计算函数已移除或标记为弃用
**And** 测试覆盖率保持 ≥ 100%
**And** 性能测试验证 fincore 计算在可接受范围内（< 5s 变化）
**And** 代码审查确认无死代码残留
**And** 文档更新说明指标计算使用 fincore
**And** 迁移指南文档已创建供未来参考

**Requirements:** NFR-MAINT-01, NFR-PERF-03

---

## Epic 2: 部署与运维文档

**Epic Goal:** 提供完整的部署指南和运维文档，使用户能够在 10 分钟内完成本地或服务器部署。

**User Value:** 用户可以快速部署平台，减少从发现到使用的时间成本。

**FRs covered:** FR1-5 (部署后验证)
**NFRs covered:** NFR-SEC-01, NFR-SEC-02, NFR-REL-01, NFR-REL-04

**Implementation Notes:**
- pip install 安装指南
- 本地开发环境设置
- 生产服务器部署（systemd/supervisor）
- 配置说明（安全、数据库、日志）

---

### Story 2.1: 创建安装和快速入门指南

As a 新用户,
I want 有清晰的安装和快速入门文档,
So that 在 10 分钟内完成本地部署并运行第一次回测.

**Acceptance Criteria:**

**Given** 新用户访问项目文档
**When** 阅读安装指南
**Then** 文档包含 Python 版本要求（3.8+）
**And** 文档提供 pip install 安装命令
**And** 文档包含虚拟环境设置说明
**And** 文档提供首次运行配置步骤
**And** 文档包含首次登录和创建策略的快速入门
**And** 文档包含常见安装问题排查部分
**And** 安装步骤已验证在干净环境中成功
**And** 文档位于 `docs/INSTALLATION.md`

**Requirements:** FR1-5, NFR-SEC-03

---

### Story 2.2: 创建生产部署指南

As a 运维人员,
I want 有完整的生产部署指南,
So that 在服务器上部署可靠的生产实例.

**Acceptance Criteria:**

**Given** 服务器环境（Ubuntu 20.04+）
**When** 部署生产实例
**Then** 文档包含 systemd 服务配置文件示例
**And** 文档包含 supervisor 配置文件示例
**And** 文档说明数据库配置和迁移步骤
**And** 文档包含 TLS/HTTPS 配置说明
**And** 文档说明环境变量配置（SECRET_KEY, 数据库 URL 等）
**And** 文档包含防火墙和端口配置建议
**And** 文档包含日志配置和轮转设置
**And** 部署步骤已在测试服务器上验证
**And** 文档位于 `docs/DEPLOYMENT.md`

**Requirements:** NFR-SEC-01, NFR-SEC-02, NFR-REL-01

---

### Story 2.3: 创建运维和故障排除指南

As a 系统管理员,
I want 有运维和故障排除指南,
So that 保持系统稳定运行并快速解决问题.

**Acceptance Criteria:**

**Given** 运行的生产实例
**When** 发生系统问题或需要维护
**Then** 文档包含健康检查端点说明
**And** 文档包含数据库备份和恢复步骤
**And** 文档包含日志位置和级别配置说明
**And** 文档包含常见错误和解决方案
**And** 文档包含性能调优建议
**And** 文档包含监控和告警配置
**And** 文档包含升级迁移步骤
**And** 文档位于 `docs/OPERATIONS.md`

**Requirements:** NFR-REL-03, NFR-REL-04

---

## Story Summary

| Epic | Story Count | FRs Covered | Status |
|------|-------------|-------------|--------|
| Epic 1: fincore 集成 | 5 stories | FR24, FR37, FR40 | ✅ Stories Created |
| Epic 2: 部署文档 | 3 stories | FR1-5 | ✅ Stories Created |

**Total:** 8 user stories ready for implementation

---

*Epics and Stories document completed via BMAD workflow on 2026-02-23*
*Project: backtrader_web - Quantitative Trading Research & Investment Management Platform*
*Workflow Type: Create Epics and Stories*
