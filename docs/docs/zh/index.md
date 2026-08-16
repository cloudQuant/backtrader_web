---
title: AI for Investor
description: 面向量化投研团队的 AI 驱动研究、验证与交易辅助平台
---

# AI for Investor

AI for Investor 将自然语言研究、知识库检索、策略开发、回测验证、交易工作区和组合风险视图串成一条可追溯的量化投研流程。它帮助团队更快形成和验证研究假设，但不替代数据校验、风险控制或人工交易决策。

[开始使用](./getting-started/index.md){ .md-button }

## 从问题到可验证结果

1. 在 **AI 助手**中通过知识库检索研究规范、历史复盘或数据说明。
2. 在**策略中心**创建、审查或生成 Backtrader 策略草案；可将草案加入研究工作区。
3. 在**数据 → 市场数据**选择标的并检查覆盖与质量。页面默认读取本地 MySQL 行情仓库；只有点击查询时才主动向 AkShare 请求最新数据。
4. 在**研究工作区**运行回测、查看指标与稳健性验证，并保留结果和配置快照。
5. 将经过人工审核的方案放入**交易工作区**，再在组合页观察账户、持仓、成交、累计 P&L、回撤和资产配置。

## 核心能力

| 领域 | 当前能力 |
| --- | --- |
| AI 与知识 | 知识库、文档索引、引用型问答、策略构思、策略审查与 AI 投研 |
| 数据可信度 | AkShare 数据仓、MySQL 本地优先读取、覆盖矩阵、质量提示、查询时在线刷新与缓存 |
| 研究与回测 | Backtrader 回测、统一指标、结果报告、策略版本、研究工作区与稳健性检查 |
| 交易与风险 | 模拟/交易工作区、网关状态、组合聚合、持仓估值、P&L 与回撤视图 |
| 工程化 | FastAPI、Vue 3、SQLAlchemy、MySQL/PostgreSQL/SQLite、pytest、Vitest 与 Playwright |

## 使用边界

- AI 生成内容、RAG 检索结果和回测指标都应由研究人员复核；回测不等同于未来收益。
- 行情、策略和账户数据可能包含敏感业务信息。密钥只放在环境变量或密钥管理系统，绝不提交到仓库。
- 实盘或外部网关操作属于高风险能力，先在研究/模拟流程中验证，再按组织的审批和风控流程执行。

## 文档导航

- [快速开始](./getting-started/index.md)：安装、启动和首次研究闭环。
- [功能介绍](./features/index.md)：知识库、市场数据、策略、回测、交易工作区与优化。
- [开发指南](./development/index.md)：架构、API 和数据边界。
- [部署运维](./deployment/index.md)：Docker 与生产环境检查清单。
- [参考资料](./reference/index.md)：配置与常用命令。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、ECharts、Pinia |
| 后端 | FastAPI、Pydantic、SQLAlchemy 2、Uvicorn |
| 研究引擎 | Backtrader；fincore 可用时提供标准化指标适配，缺失时使用兼容计算 |
| 数据与 AI | AkShare、MySQL 行情仓、OpenAI-compatible 生成接口、可选 ChromaDB / sentence-transformers 语义检索 |

## 相关项目

| 项目 | 简介 |
| --- | --- |
| [backtrader](https://github.com/cloudQuant/backtrader) | 专业 Python 算法交易框架（回测 + 实盘），本平台策略研究引擎的基础 fork。 |
| [backtrader-skills](https://github.com/cloudQuant/backtrader-skills) | 离线策略"作者/评审/测试"产品：数据集与 StrategySpec v1 → pytest 策略或三文件包，静态评审 + 子进程验证。 |
| [backtrader-mcp](https://github.com/cloudQuant/backtrader-mcp) | 本地优先 MCP 服务器：CSV 固化数据集、类型化策略草稿、受限子进程运行与状态报告（离线、仅回测）。 |
| [backtrader_web](https://github.com/cloudQuant/backtrader_web) | 本平台：Web 全周期 Backtrader 策略管理（回测分析、模拟交易、实盘执行、数据管理）。 |
| [backtrader-agent](https://github.com/cloudQuant/backtrader-agent) | 离线优先策略编写 agent 运行时：内容寻址存储、规范校验、脚手架、静态评审与哈希绑定执行。 |
| [fincore](https://github.com/cloudQuant/fincore) | 统一 Python 工具集：金融指标、绩效分析、回测、AI 洞察与多数据库/多数据源支持。 |

完整项目入口、内部工程文档与归档策略见仓库中的 `docs/INDEX.md`。
