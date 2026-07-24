# 功能介绍

产品按“研究依据 → 策略与验证 → 交易准备 → 风险观察”组织。页面导航是主要入口；接口细节以运行中服务的 OpenAPI 为准。

## 功能地图

| 工作流 | 页面入口 | 关键边界 |
| --- | --- | --- |
| 知识与 AI | `/ai/chat`、`/ai/knowledge-base` | 先索引再问答；回答应携带上下文或可读诊断 |
| 市场数据 | `/data/market` | 本地 MySQL 优先；仅显式查询才调用 AkShare |
| 策略与 AI 投研 | `/investment/strategies` | 代码、研究目标和结果均需人工复核 |
| 回测与验证 | `/research/workspaces`、`/backtest` | 指标基于所选数据和配置，不构成收益承诺 |
| 交易工作区 | `/trading` | 将研究与交易运行状态分开管理 |
| 组合与风险 | `/portfolio` | 聚合账户、持仓、成交、P&L、回撤和资产配置 |
| 管理配置 | `/config/data`、`/config/ai`、`/config/gateways` | 管理员权限；密钥只保存在环境或密钥服务中 |

## 深入阅读

- [知识库与 AI 问答](./knowledge-base.md)
- [市场数据与可信度](./market-data.md)
- [策略与 AI 投研](./strategy-management.md)
- [回测与验证](./backtesting.md)
- [交易工作区与模拟](./paper-trading.md)
- [实盘准备与网关](./live-trading.md)
- [参数优化](./optimization.md)

## API 约定

核心 API 位于 `/api/v1`。常用领域包括 `/strategy`、`/backtests`、`/workspace`、`/data`、`/data/trust`、`/knowledge-base`、`/rag`、`/kb-chat`、`/portfolio` 和 `/live-trading`。部分模块按依赖和配置可选注册，因此不要依赖过时的端点清单；请使用 `http://localhost:8000/docs` 检查当前环境实际提供的契约。
