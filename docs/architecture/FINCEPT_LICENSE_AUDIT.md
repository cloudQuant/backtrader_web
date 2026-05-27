# Fincept License Audit Ledger

这份台账用于记录迭代 170 中哪些能力借鉴了 FinceptTerminal 的**能力形态**，以及当前实现是否遵守 clean-room 约束。

## 使用规则

- 这里只记录**能力参考**、接口形态和验证说明，不贴任何 Fincept 源码片段。
- Implementer 只能基于规格和当前项目实现填写，不应回贴上游源码。
- 每新增一个借鉴能力，都追加一行记录。

## 当前记录

| 日期 | 能力 | 本地参考范围 | 当前项目实现 | 借鉴边界说明 | Implementer | Reviewer | 状态 |
|---|---|---|---|---|---|---|---|
| 2026-05-26 | Data Connector Registry | Fincept 数据源/接口治理能力形态 | `src/backend/app/models/data_governance.py`、`app/services/data_connectors/*`、`app/api/data_governance.py` | 仅借鉴“provider / endpoint / job / quality rule”产品分层；代码为当前项目独立实现 | Cascade | 待补 | 已记录 |
| 2026-05-26 | Data Topic Hub | Fincept DataHub topic + TTL 策略能力形态 | `src/backend/app/services/data_topic_hub.py`、`app/api/data_topics.py` | 仅借鉴 topic policy 与 producer 抽象方向；当前实现为 Python/FastAPI 重写 | Cascade | 待补 | 已记录 |
| 2026-05-26 | Broker Contract | Fincept 标准化 broker 能力组织方式 | 独立包 `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/brokers/*` | 仅借鉴 adapter / capabilities / contract test 组织方式；实现位于独立 `bt_api_py` 包 | Cascade | 待补 | 已记录 |
| 2026-05-26 | Portfolio Ledger | Fincept 独立组合账本能力形态 | `src/backend/app/services/portfolio_ledger.py`、`app/api/portfolio_ledger.py` | 仅借鉴“独立组合账本”产品边界；当前实现为最小内存态 MVP | Cascade | 待补 | 已记录 |
| 2026-05-26 | News / Options / Quant Tools | Fincept 新闻情报、期权链、Agent 工具化方向 | `app/services/news_intelligence.py`、`app/services/options_chain.py`、`app/services/quant_tools.py` | 仅借鉴模块边界与能力组合；具体字段与运行逻辑以当前项目实现为准 | Cascade | 待补 | 已记录 |

## 待补字段

后续正式评审时，建议补充：

- Reader 名称
- Reviewer 名称
- 对应 PR / commit hash
- 是否经过法律 checkpoint
- 是否存在任何上游命名/注释残留排查结果
