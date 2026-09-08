# 迭代 197：本地优先市场数据中台

> 文档状态：**设计冻结候选（仅文档，不开发）**
> 基线：`dev` / 迭代 196 尚未冻结（2026-09-08）

迭代 197 设计一条可追溯的市场数据链路，供 `/data/market` 和最终的 `/investment/strategies` 使用：先读取经验证的规范化本地事实；只有本地覆盖不足时，才按服务器维护的策略向 AkShare 或隔离的 OpenBB 运行器请求精确缺口；任何外部结果都必须先成为本地证据，随后才可参与响应。

本次交付**仅包含方案文档**。不安装 OpenBB、不执行迁移、不抓取真实数据、不修改页面、不启用开关，也不把任何实验性代码或局部测试当作迭代交付证据。

## 文档索引

- [需求文档](REQUIREMENTS.md)：范围、功能需求、非功能约束和不做事项。
- [设计文档](DESIGN.md)：数据中台目标架构、PIT、来源治理、接口和并行实施安排。
- [验收文档](ACCEPTANCE.md)：验收案例、证据标准、外部验证和迭代 196 整合闸门。

## 当前基线（只读源码审计）

当前 `/data/market` 以七类页签覆盖股票、期货、债券、基金、期权、外汇和加密资产；其页面数据族包括行情/历史、估值或参考序列、以及期权链等。市场页面的初次 lookup 读取本地仓库，手动 `refresh_online=true` 才进入 AkShare 在线分支；当前在线主路径未形成已证实的持久化闭环，不能作为“抓取后写库、下次本地命中”的证据。

当前页面频率也存在三个不同层面：市场查询 UI 提供 `daily`/`weekly`/`monthly`，coverage UI 另展示 `1d`/`1h`/`30m`/`5m`，策略 UI 提供 `1d`/`1h`/`30m`/`5m`。UI 声明不等于已验证 provider 或本地存储能力：现有 coverage 刷新只确认 `1d`，且策略输入中的 `data_config` 尚未形成完整的七类资产、provider、series 和 provenance 契约。详见 [需求文档](REQUIREMENTS.md#21-资产和数据类型) 的全量范围与能力矩阵。

`commodity` 虽出现在底层 trust schema，但当前两个页面和市场服务没有对应分支，因此不纳入本期页面范围。当前源码也没有 OpenBB 集成；197 把它设计为受控、隔离的新增 provider，而非现有代码的隐式依赖。

## 能否与迭代 196 并行

可以，但必须按依赖边界拆分，而不是让两个迭代同时改同一条页面、迁移链或研究工件契约。

| 工作包 | 可与 196 并行 | 必须等待 196 冻结 |
| --- | --- | --- |
| 数据目录、精确主数据索引、规范化事实模型、来源策略、适配器契约、离线测试设计 | 是；放在独立工作树和独立分支中。 | 否。 |
| OpenBB 运行器隔离、AkShare 显式路由、存储回读、治理/可观测性实现 | 是；不得接入页面、不得启用真实在线抓取。 | 否。 |
| Alembic 链合并、共享数据库升级、真实数据回填、provider 凭据/许可启用 | 否。 | 是；需要一个共同的 migration head、迁移 lease、预期 revision 预检、跨版本兼容窗口和可恢复演练。 |
| `/data/market` 灰度切换 | 否。 | 是；需要目录、主数据、日历、来源策略和浏览器证据。 |
| `/investment/strategies` 的研究/回测工件绑定 | 否。 | 是；196 的输入、输出和工件 schema 必须冻结。 |

因此，196 进行中的事实不妨碍 197 先完成独立的数据中台基础；它只阻塞最终集成、迁移发布和页面切换。

## 后续实施工作包（非本次交付）

| 工作包 | 目标 | 与 196 的关系 |
| --- | --- | --- |
| WP-197-01 | 冻结 `MD-197-SCOPE-MANIFEST`、数据目录、精确身份、日历和 source policy。 | 可独立完成，页面基线版本须记录。 |
| WP-197-02 | 建立 canonical series、来源快照、revision、visibility receipt、PIT/coverage/cursor 和授权模型。 | 可在隔离数据库验证。 |
| WP-197-03 | 建立 AkShare route registry、OpenBB JSON runner、幂等/lease/fencing 与本地回读。 | 可独立实现，真实 route/许可按验收逐项启用。 |
| WP-197-04 | 合并 migration、冻结 196 工件 schema、绑定 provenance 与完整性指纹。 | 必须等 IG-196 闸门解除。 |
| WP-197-05 | 灰度市场页，再灰度策略页，完成真实数据和灾备验收。 | 必须等共享数据库、浏览器和工件证据齐备。 |

## 核心硬约束

- 覆盖当前两个页面已经支持的资产类型：股票、期货、债券、基金、期权、外汇、加密资产。某组合尚无安全来源时必须显式返回“未配置/不支持”，不得伪造覆盖。
- 每个在线路由必须同时绑定逻辑数据集、精确身份、市场、频率、字段口径、用途、来源登记、预期 receipt provider 和许可状态。
- `bars`、快照和未来事件型数据使用彼此明确的 `frequency_semantics`，不能用空频率或 K 线粒度伪装非 K 线查询。
- 本地历史重放不得依赖仍在运行的在线 provider；已退役的来源策略必须保留不可变历史描述和用途授权，在线能力则可单独关闭。
- 历史采集授权只解释当时的证据；每次本地读取、严格重放和策略工件消费仍需校验当前主体的读取授权。
- 外部数据的 query 语义哈希与 provider request ID 必须分开保存。回执必须回显后者，不能只用可复算的公共 query 哈希证明来源一致性。
- 196/197 工件须同时保存并校验 provenance manifest hash、工件 schema/version、payload hash 和 artifact fingerprint，不能靠日后数据库反查补全。
- 分页游标必须带服务器 HMAC，绑定主体、查询语义、策略版本、排序锚点和冻结的可见性边界；Base64 JSON 不是安全游标。
- 严格 PIT 读取以已 sealed receipt 的完整 `(visible_at, visibility_sequence)` anchor 为准；固定 anchor 下的缺口不触网补齐。仅有 provider 自报时间、应用收据时间或未提交事务中的行都不足以证明历史可见性。
- OpenBB 只在最小权限的独立运行器中运行；FastAPI 进程不导入扩展，且默认不注册 OpenBB 在线 fallback。

## OpenBB 参考输入

方案以本地 checkout 为主、GitHub 社区仓库为补充，记录的基线如下：

| 输入 | 已借鉴内容 | 本方案中的落点 |
| --- | --- | --- |
| `/Users/yunjinqi/Documents/new_projects/OpenBB`，`3e071fcc2cd9f891cac6040ae60296dba76dab46` | ODP 的“连接一次、多个消费面”、provider/extension 与标准化模型边界。 | 控制面、provider request/receipt、隔离 runner；不把 OpenBB runtime 直接嵌入 Web 进程。 |
| `/Users/yunjinqi/Documents/new_projects/openbb-docs`，`acd5b2bf2d8603f574bd6b2da2e15e1aae8b017d` | provider 选择、命令参数和 ODP 文档化的能力声明。 | 服务器维护的 route capability、版本化 policy descriptor 和显式“不支持”结果。 |
| `/Users/yunjinqi/Documents/new_projects/agents-for-openbb`，`aa1073d2b098ae6cf597dabf0635822aa808dd81` | raw data 与解释/引用分离、agent 作为受控消费者。 | `MarketDataQueryProvenance`，让页面和策略工件消费已冻结数据证据而非直接抓取。 |
| [OpenBB-finance GitHub 社区仓库](https://github.com/orgs/OpenBB-finance/repositories) | Platform、docs、backends 和 agents 的分仓边界。 | 后续 provider/runner/前端集成保持独立评审和版本锁定。 |

这些参考只用于架构与契约设计。具体 extension、provider、数据许可、版本和运行器是否可用，必须在迭代 197 的真实验收中逐项确认。
