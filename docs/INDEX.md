# Backtrader Web 文档索引

Backtrader Web 是一个基于 Backtrader 的现代化**量化交易管理平台**。

> **重要提示**: 本项目不仅仅是回测平台，而是全功能的量化交易管理系统，支持策略管理、回测、模拟交易、实盘交易、实时监控等全流程功能。

## 核心文档

### 📖 综合技术文档
- **[技术文档 (推荐)](TECHNICAL_DOCS.md)** - 系统功能概览、API 模块、数据模型、部署运维的完整技术文档

### 快速开始
- [安装指南](INSTALLATION.md) - 环境配置和安装步骤
- [快速上手](QUICKSTART.md) - 5分钟完成首次回测
- [API 文档](API.md) - RESTful API 接口说明

### 环境校验与排查
- **[Backtrader 导入问题排查](BACKTRADER_IMPORT_TROUBLESHOOTING.md)** - 详细的 backtrader 模块导入问题排查步骤

### 开发指南
- [开发指南](DEVELOPMENT.md) - 本地开发环境配置
- [代码规范](CODING_STANDARDS.md) - 代码风格和最佳实践
- [测试指南](TESTING.md) - 单元测试、集成测试和E2E测试
- [部署指南](DEPLOYMENT.md) - 生产环境部署
- [贡献指南](CONTRIBUTING.md) - 如何参与项目开发

### 运维文档
- [运维手册](OPERATIONS.md) - 监控、日志、备份
- [故障排查](TROUBLESHOOTING.md) - 常见问题解决方案
- [性能优化](PERFORMANCE.md) - 性能基准、优化建议、扩展指南
- [日志系统](LOGGING.md) - 日志配置和管理
- [CI/CD](CI_CD.md) - 持续集成和部署

### 架构文档
- [系统架构](ARCHITECTURE.md) - 整体架构设计
- [数据库设计](DATABASE.md) - 数据模型和关系
- [数据库初始化指南](DATABASE_INIT.md) - 数据库设置和初始化（默认不在启动时自动执行，可通过显式环境开关启用兼容自举）
- [Request-Scoped Session 指南](REQUEST_SCOPED_SESSION.md) - 事务管理模式和最佳实践
- [安全指南](SECURITY.md) - 安全最佳实践

### 功能文档
- [策略开发](STRATEGY_DEVELOPMENT.md) - 如何编写交易策略
- [回测指南](BACKTEST_GUIDE.md) - 回测使用说明
- [实盘交易](LIVE_TRADING.md) - 实盘对接说明
- [参数优化](OPTIMIZATION.md) - 参数优化功能
- [用户手册](USER_GUIDE.md) - 终端用户使用指南

### 质量与测试
- [E2E 测试覆盖率分析](E2E_TEST_COVERAGE_ANALYSIS.md) - E2E 测试现状和改进建议
- [E2E 测试质量审查](E2E_TEST_QUALITY_REVIEW.md) - 测试质量评分 (72/100) 和改进优先级
- [文档改进计划](DOCUMENTATION_IMPROVEMENT_PLAN.md) - 文档质量提升路线图

### 项目管理
- [项目完成报告](PROJECT_COMPLETION.md) - Epic 完成总结
- [敏捷开发](AGILE_DEVELOPMENT.md) - 敏捷流程说明
- [更新日志](CHANGELOG.md) - 版本更新记录
- [安全增强记录](SECURITY_ENHANCEMENTS.md) - 安全改进历史
- [项目改进与优化建议（2026-03）](PROJECT_OPTIMIZATION_RECOMMENDATIONS.md) - 基于代码与配置核对的可落地优化清单
- [迭代历史](iterations/README.md) - 迭代 45–129 开发记录
- [迭代115：工程基线治理与质量收敛计划](iterations/迭代115-工程基线治理与质量收敛计划.md) - 面向初级工程师的短周期改进迭代计划
- [迭代116：开发环境校验与可复现治理](iterations/迭代116-开发环境校验与可复现治理.md) - 开发环境自检与安装入口统一
- [迭代117：运行时稳定性与交付一致性提升计划](iterations/迭代117-运行时稳定性与交付一致性提升计划.md) - 面向中级工程师的后端稳定性与交付治理计划
- [迭代118：验收缺陷修复与交付闸门加固计划](iterations/迭代118-验收缺陷修复与交付闸门加固计划.md) - 面向当前阻断问题和质量闸门缺口的收口计划
- [迭代119：认证事务边界与测试信号清洁计划](iterations/迭代119-认证事务边界与测试信号清洁计划.md) - 认证事务一致性和测试 warning 收敛
- [迭代120：修复模拟盘策略模拟的问题](iterations/迭代120-修复模拟盘策略模拟的问题.md) - 聚焦模拟盘策略运行异常与链路修复
- [迭代121：修复模拟交易情况](iterations/迭代121-修复模拟交易情况.md) - 补齐模拟交易运行与状态问题修复记录
- [迭代122：参考tbquant3完善策略管理界面](iterations/迭代122-参考tbquant3完善策略管理界面.md) - 面向策略管理体验与交互补强的迭代
- [迭代123：当前项目优化与迭代计划](iterations/迭代123-当前项目优化与迭代计划.md) - 基于当前代码现状整理的后续优化路线图
- [迭代123-A：任务执行与CI闸门收口计划](iterations/迭代123-A-任务执行与CI闸门收口计划.md) - 面向任务状态语义统一与 CI 阻断策略收口的执行方案
- [迭代123-B：实盘与网关管理解耦计划](iterations/迭代123-B-实盘与网关管理解耦计划.md) - 面向 live trading manager 复杂度下降的解耦方案
- [迭代123-C：实时链路与占位能力补全计划](iterations/迭代123-C-实时链路与占位能力补全计划.md) - 面向实时数据链路与未闭环接口收口的执行方案
- [迭代124：测试可信度、遗留链路清理与基线同步计划](iterations/迭代124-测试可信度、遗留链路清理与基线同步计划.md) - 面向后123阶段残留收口的执行计划
- [迭代125：全面质量审查与优化迭代计划](iterations/迭代125-全面质量审查与优化迭代计划.md) - 面向全面质量审查后的可执行优化与收口计划
- [迭代126：当前项目优化审查与执行计划](iterations/迭代126-当前项目优化审查与执行计划.md) - 基于当前真实代码状态核对后的新一轮执行入口
- [迭代127：运行时契约统一与文档对齐计划](iterations/迭代127-运行时契约统一与文档对齐计划.md) - 面向 WebSocket、API 权威入口、数据库启动语义与文档真相源统一的新一轮收口计划
- [迭代128：当前项目优化候选清单与待确认执行计划](iterations/迭代128-当前项目优化候选清单与待确认执行计划.md) - 面向回测主链路、参数优化能力统一与前端编排降复杂度的待确认执行计划
- [迭代129：当前项目执行面收口与体验一致性优化计划](iterations/迭代129-当前项目执行面收口与体验一致性优化计划.md) - 面向权威入口收口、前端体验一致性和运行时验证闭环的新一轮执行计划

## 项目概述

| 模块 | 状态 | 说明 |
|------|------|------|
| 策略管理 | 完成 | CRUD + 版本控制 |
| 回测分析 | 完成 | 历史数据回测 + fincore 标准化指标 |
| 参数优化 | 完成 | 网格搜索 + 贝叶斯优化 |
| 报告导出 | 完成 | HTML/PDF/Excel |
| 模拟交易 | 完成 | 账户、订单、持仓 |
| 实盘交易 | 完成 | 多券商支持 (CCXT/CTP) |
| 实时数据 | 完成 | WebSocket 推送 |
| 监控告警 | 完成 | 实时监控 |
| 投资组合 | 完成 | 多策略组合管理 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus |
| 后端 | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 |
| 数据库 | SQLite / PostgreSQL / MySQL |
| 回测引擎 | Backtrader + fincore |
| 测试 | pytest + Playwright (E2E) + Vitest (前端) |

## 联系方式

- 问题反馈: [GitHub Issues](https://github.com/xxx/backtrader-web/issues)
- 邮件: support@example.com
