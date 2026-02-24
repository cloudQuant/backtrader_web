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
- [迭代历史](iterations/README.md) - 迭代 45–114 开发记录

## 项目概述

| 模块 | 状态 | 说明 |
|------|------|------|
| 策略管理 | ✅ 完成 | CRUD + 版本控制 |
| 回测分析 | ✅ 完成 | 历史数据回测 + fincore 标准化指标 |
| 参数优化 | ✅ 完成 | 网格搜索 + 贝叶斯优化 |
| 报告导出 | ✅ 完成 | HTML/PDF/Excel |
| 模拟交易 | ✅ 完成 | 账户、订单、持仓 |
| 实盘交易 | ✅ 完成 | 多券商支持 (CCXT/CTP) |
| 实时数据 | ✅ 完成 | WebSocket 推送 |
| 监控告警 | ✅ 完成 | 实时监控 |
| 投资组合 | ✅ 完成 | 多策略组合管理 |

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
