# 迭代 197：本地优先市场数据中台

本迭代把行情页面和策略研究所需的市场数据收敛到一条可追溯的读取链路：先读取规范化本地数据；只有本地数据缺失、字段不全或覆盖证据不足时，才按受控策略调用 AkShare 或隔离的 OpenBB 运行器；所有成功获取的结果都以原始来源回执和不可变观测修订写回本地库。

## 文档索引

- [需求文档](REQUIREMENTS.md)：范围、用户故事、行为边界和验收口径。
- [设计文档](DESIGN.md)：数据模型、读取/写入流程、接口、迁移和运维设计。
- [验收文档](ACCEPTANCE.md)：自动化证据、待验证外部依赖和迭代 196 的整合闸门。
- [范围清单闸门](SCOPE_MANIFEST.md)：从 21 个家族合同和当前 UI/API 输入生成可复核清单；没有冻结的迭代 196 基线时失败关闭。
- [数据产品扩展计划](PRODUCT_EXPANSION_PLAN.md)：21 个页面家族的实际能力台账，以及 11 个单记录和 4 个多记录产品的后续模型、来源与验收要求。

当前实现已为 11 个 B1 单记录家族建立惰性的逻辑数据集目录、精确 family-shape 白名单和合同驱动的页面状态。其中 `stock.liquidity`、`fund.liquidity` 和 `fx.range` 已完成候选代码开通：它们具有各自的 `ready` family contract、精确来源策略和页面显式选择路径；其余八个 B1 家族仍为 `unconfigured`。这只表示代码合同与离线回归已具备，不能表示所有产品已经通过真实 provider、数据库或页面灰度验收。

> 当前候选仍处于实现与离线验证阶段，不能视为发布验收通过。真实 OpenBB `yfinance` 小窗口曾受到上游 HTTP 429 限流，跨 MySQL/PostgreSQL 的 PIT 验证、OpenBB 的操作系统级隔离、以及与迭代 196 合并后的迁移演练均保留为 `NOT_RUN` 或 `BLOCKED`，具体证据边界见 [验收文档](ACCEPTANCE.md)。

## 迭代边界

迭代 196 正在收尾，因此 197 在独立工作树和独立 Alembic 链中实现。它不修改 196 的未提交代码，也不把新的行情读取层直接接入尚未冻结的 AI 研究、回测或策略页面契约。当前两条链共同从 `20260811_asset_research_task_leases` 分叉：196 已继续产生研究审批修订，197 从 `20260908_market_data_catalog` 经 durable fetch lease 继续到 exact-identity collation 修订。把两个工作树合并会形成双 head；196 冻结后，必须重基 197 或创建受审查的 Alembic merge revision，并在空库和候选 MySQL/PostgreSQL 副本验证唯一 head，才可以开启策略页的正式消费开关。

## 核心约束

- 覆盖现有页面支持的全部资产类型：股票、期货、债券、基金、期权、外汇、加密资产。
- 不使用旧 `MarketInstrumentService` 的样例、附近合约或模糊代码回退。
- 不以物理 AkShare 表名作为数据集身份；读取和写入只通过逻辑数据集、主数据版本和来源策略确定。
- 研究与回测使用严格一致性和知识截止点，读取 `available_at <= knowledge_cutoff` 的数据。
- `research_cache_fill` 只表示用户明确请求的当前数据缓存补齐：它只能走 `local_first + display`、不得携带 PIT 截止点或分页游标、须保留研究用途的来源授权，并且只写中台 receipt/事实表。它不是迭代 196 的研究、回测或审批工件。
- 对需要按事件判断完整性的 `bars` 请求，覆盖事件必须来自经审核导入的 `(market, data_kind, frequency, event timestamp)` 显式网格；日线、周线、月线和任何分钟粒度各自有独立网格，不从交易日、周末规则或另一粒度推断。
- 同一事件读取“满足本次字段集、质量门槛和截止点的最新修订”；较新的窄字段修订不得遮蔽仍可满足宽字段请求的旧修订，也不得把不同修订的字段拼接成未经来源证明的行。
- 相同 `local_first` 缺口在同一 Web 进程内由 singleflight 合并，并由 `md_fetch_leases` 的 owner/fence/expiry 协议跨 worker 协调；事实和 publication 都受 fence guard 保护。该候选实现仍未替代真实多 worker、多方言、时钟和故障接管验收，不能据此宣称全局去重已上线。
- OpenBB 扩展只在受控子进程运行；FastAPI 进程不导入 OpenBB 扩展代码。运行器返回有上限的预规范化原始记录封套及 SHA-256，父进程复算哈希后才接受回执。
- 受控环境变量与工作目录只能缩小子进程继承面，不能代替操作系统隔离。生产 OpenBB 必须运行在独立 service account 或容器中，且不挂载主应用工作树、数据库凭据或其他应用密钥。
- 外部数据许可、来源策略和原始回执必须可审计；代码接入不等于数据商用授权。
- 每次 v2 读取都重新检查 `data:read` 与当前来源 registry；旧回执或旧 cursor 不授予永久读取权。当前注册流程不自动赋予该角色，灰度前须走独立 RBAC provisioning。
