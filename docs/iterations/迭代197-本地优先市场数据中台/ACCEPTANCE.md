# 迭代 197 验收文档：本地优先市场数据中台

> 文档状态：候选实现与本地验收已完成；未执行真实迁移、未调用真实 provider、未生产发布。
> 当前总判定：**`NOT_ACCEPTED`**。本文件定义未来实现候选必须满足的验收，而不把文档、mock、历史日志或局部代码审查写成通过证据。

## 1. 判定语言和证据规则

| 状态 | 定义 | 是否可作为上线依据 |
| --- | --- | --- |
| `PASS` | 在确定的候选提交、环境和命令下实际执行成功，保存 SHA、退出码、摘要与可复核工件。 | 仅与其余闸门共同满足时可以。 |
| `FAIL` | 实际执行后出现断言、迁移、行为或证据不符合。 | 不可以。 |
| `NOT_RUN` | 尚未执行，或只有 mock/静态阅读而没有本条要求的证据。 | 不可以。 |
| `BLOCKED` | 需要外部前置条件，例如 196 冻结、共享迁移链、准生产数据库、账户许可或维护窗口。 | 不可以；必须解除阻塞。 |

本次所有执行型条目均为 `NOT_RUN` 或 `BLOCKED`。后续不得把“测试文件存在”“SQLite fixture 通过”“页面截图”“历史日志”或“provider SDK 可导入”升级为真实验收通过。

## 2. 验收范围和不包含项

| 对象 | 未来验收范围 | 当前状态 |
| --- | --- | --- |
| AO-197-01 | 逻辑目录、唯一主存储和 exact 主数据/lookup key。 | `NOT_RUN` |
| AO-197-02 | 规范化 series、来源快照、观测修订、日历和可见性 receipt。 | `NOT_RUN` |
| AO-197-03 | local-only/local-first/refresh 覆盖规划、PIT 和本地回读。 | `NOT_RUN` |
| AO-197-04 | dataset-bound source policy、许可、用途、principal entitlement 和 retired policy replay。 | `NOT_RUN` |
| AO-197-05 | AkShare/OpenBB 精确 adapter 和隔离协议。 | `NOT_RUN` |
| AO-197-06 | HMAC cursor、防篡改分页、固定 provenance envelope 和工件完整性指纹。 | `NOT_RUN` |
| AO-197-07 | `/data/market` 灰度接入。 | `BLOCKED`：依赖 196/共享迁移和浏览器环境。 |
| AO-197-08 | `/investment/strategies` 严格工件绑定。 | `BLOCKED`：196 工件 schema 尚未冻结。 |

不包含：真实数据供应商的长期可用性保证、未经批准的数据商用权、生产库迁移、真实账户密钥、实时经纪商 tick、以及任何对 196 未提交代码的修改。

## 3. 验收前置条件

### 3.1 候选版本和环境

1. 验收在独立 197 候选工作树/提交运行，不能混入 196 的未提交工作树。
2. 保存 `git rev-parse HEAD`、`git status --short`、依赖锁版本、Python 版本、数据库方言、环境配置哈希和命令退出码。
3. Python 命令使用项目约定环境：

   ```bash
   /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python ...
   ```

4. 测试数据库必须隔离、可销毁；任何真实数据/凭据日志都需脱敏并受保留策略控制。
5. 启用 v2 前，`MARKET_DATA_QUERY_V2_ENABLED=false`、`MARKET_DATA_ONLINE_FETCH_ENABLED=false`，OpenBB 市场白名单为空。
6. 任何涉及 196 的执行都记录 196 commit/ref、工件 schema ID/version/hash、Alembic 起始/目标 head、环境身份和兼容范围；缺一项即保持相关条目 `BLOCKED`。

### 3.2 控制面和数据前置条件

1. 每个使用的数据集有唯一活动 primary storage，且 route 精确绑定其 dataset code/ID。
2. canonical identity、instrument version、lookup key、交易日历和 source policy descriptor 已导入并通过审核。
3. provider 同时在治理目录和来源注册中有效；license、allowed use、有效期、辖区、保留/再分发策略，以及在线获取与本地读取所需的 principal entitlement 均已批准。

### 3.3 shared binding migration 维护围栏

1. `20260908_market_data_shared_dataset_bindings` 的真实 MySQL 执行前，外部 runbook 必须先停止 API、collector 与 bootstrap writer，并记录已排空的证据；代码内的围栏不能自行证明该事实。
2. 仅在上述证据已具备后，授权 migration runner 才能设置 `MARKET_DATA_SHARED_BINDING_MAINTENANCE_FENCE=confirmed`。该值缺失时 migration 必须在任何 DDL 前 fail-closed。
3. runner 必须取得具名 MySQL lock，且 session `lock_wait_timeout=5`；PostgreSQL 在同一事务执行 `SET LOCAL lock_timeout = '5s'`。锁不可得、revision 漂移、writer 未排空或 offline `--sql` 计划均为失败/阻断，不允许绕过。
4. downgrade 使用相同围栏；它不得作为删除不可变事实的自动恢复手段。
4. strict replay 所用主数据、lookup key、日历和 observations 都有完整 `(visible_at, visibility_sequence)` anchor；不允许只凭 `created_at`、provider 自报时间或仅时间戳 cutoff。
5. retired policy descriptor 保留其历史用途授权和 descriptor hash；在线 route 显式关闭。

## 4. 自动化候选门槛

实现后，最小离线候选命令应覆盖目录、迁移、identity、lookup key、coverage、store、policy、cursor、adapter 和 HTTP 契约。项目实际文件名可在实施任务中落定，但最终必须有一次完整、候选 SHA 绑定的执行，例如：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q \
  tests/market_data_platform

/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check \
  app/api/data app/models app/schemas app/services/market_data \
  tests/market_data_platform
```

必要时补充 MySQL/PostgreSQL 迁移演练和前端 build/e2e。离线 suite 可以证明拒绝逻辑和契约；它不能证明真实 AkShare/OpenBB 可用性、数据许可或生产库恢复。

| 证据 ID | 命令/工件 | 未来通过标准 | 当前状态 |
| --- | --- | --- | --- |
| E-197-01 | 完整离线 `pytest` | 候选 SHA、退出码 0、总数与失败为零。 | `NOT_RUN` |
| E-197-02 | Ruff/format/diff check | 退出码 0，无未解释格式/静态错误。 | `NOT_RUN` |
| E-197-03 | 独立 197 migration chain 演练 | 预期起始 revision、升级、prepared/sealed 恢复和 schema/FK/index/约束审计通过；不接入 196 共享库。 | `NOT_RUN` |
| E-197-04 | 196/197 共享 migration lease 演练 | 合并后恰一个 head；并发执行器互斥、错误起始 revision fail-closed、跨版本兼容与失败恢复通过。 | `BLOCKED` |
| E-197-05 | 准生产 MySQL 恢复演练 | 升级、local-only 重放、恢复和不可变证据审计通过。 | `BLOCKED` |
| E-197-06 | 准生产 PostgreSQL 恢复演练 | 同 E-197-05。 | `BLOCKED` |
| E-197-07 | 真实 AkShare 小窗口 | 来源许可、精确请求、回执、seal、本地复读完整。 | `NOT_RUN` |
| E-197-08 | 真实 OpenBB runner 小窗口 | 隔离、协议、许可、回执、seal、本地复读完整。 | `NOT_RUN` |
| E-197-09 | 两页面 E2E 与 196 工件重放 | 浏览器/API/数据库/工件谱系和完整性指纹一致。 | `BLOCKED` |
| E-197-10 | `MD-197-SCOPE-MANIFEST` 交叉审计 | 196 基线 commit/ref、页面/DTO/目录输入、每行 hash 和所有当前受支持组合齐全；无代表样本缩减。 | `BLOCKED` |
| E-197-11 | 安全、合规、缓存与可观测性审计包 | 隔离/脱敏/限流/授权/留存/再分发/告警与跨主体缓存隔离的候选 SHA 绑定结果。 | `NOT_RUN` |

### 4.1 需求—验收可追踪矩阵

下表是设计冻结时的完整追踪索引。实现任务可以增加更细粒度的测试，但不能删除或用代表性样本替代已映射条目。

| 需求 | 契约级验证 | 运行/整合证据 | 当前状态 |
| --- | --- | --- | --- |
| FR-197-01：精确公共查询与范围清单 | AC-197-001、014、023、024、032 | E-197-01、E-197-09 | `NOT_RUN`；页面基线待 196 固定。 |
| FR-197-02：local-only/local-first/refresh/coverage | AC-197-004 至 007、025、028、036 | E-197-01、E-197-07、E-197-08 | `NOT_RUN` |
| FR-197-03：数据集、policy、当前读取授权隔离 | AC-197-008、009、020、028、030 | E-197-01、E-197-09 | `NOT_RUN`；页面接入 `BLOCKED`。 |
| FR-197-04：外部获取、回执、local reread | AC-197-010 至 012、025 | E-197-01、E-197-07、E-197-08 | `NOT_RUN` |
| FR-197-05：PIT、主数据与可见性 | AC-197-002、006、007、012、013、021、026、036 | E-197-01、E-197-05、E-197-06、E-197-09 | `NOT_RUN`；共享库/策略重放 `BLOCKED`。 |
| FR-197-06：防篡改分页 | AC-197-014、015、024、036 | E-197-01 | `NOT_RUN` |
| FR-197-07：AkShare/OpenBB adapter | AC-197-016、017、018、029、032 | E-197-07、E-197-08 | `NOT_RUN` |
| FR-197-08：196 工件 provenance/完整性 | AC-197-019、020、026、027 | IG-196-01 至 05、E-197-09 | `BLOCKED` |
| FR-197-09：页面迁移与遗留兼容 | AC-197-033、034、035 | E-197-09、E-197-10、IG-196-01 至 05 | `BLOCKED` |
| NFR：正确性与一致性 | AC-197-001、002、004、009、011、013、021、023、024 | E-197-01、E-197-05、E-197-06 | `NOT_RUN` |
| NFR：并发、恢复与性能 | AC-197-012、025、028、031 | E-197-01、E-197-03 至 06 | `NOT_RUN`；共享演练 `BLOCKED`。 |
| NFR：安全 | AC-197-014、017、020、029、031 | E-197-01、E-197-08、E-197-11 | `NOT_RUN` |
| NFR：合规 | AC-197-008、020、030 | E-197-07、E-197-08、E-197-11 | `NOT_RUN` |
| NFR：可观测性 | AC-197-011、012、025、031 | E-197-01、E-197-11 | `NOT_RUN` |

## 5. 契约级验收案例

| ID | 场景与操作 | 期望结果 | 当前状态 |
| --- | --- | --- | --- |
| AC-197-001 | canonical ID 与完整精确三元组分别解析；输入局部三元组、别名、近似代码、大小写近似、过期/重叠 identity。 | 只接受唯一精确权威身份；无样例或附近标的回退。 | `NOT_RUN` |
| AC-197-002 | 在 cutoff 后新增 instrument，或向旧 instrument 回填一个晚创建的 exact lookup key。 | strict 解析不能让晚知道的 instrument 或 lookup key 穿越 cutoff。 | `NOT_RUN` |
| AC-197-003 | 请求活动数据集、缺失/失活/歧义 primary binding、以及遗留表名。 | 仅活动唯一目录绑定可用；从不根据旧表名猜测。 | `NOT_RUN` |
| AC-197-004 | 对完整、缺头/中间/尾部、空和日历缺失/歧义窗口运行 coverage。 | 只有覆盖充分的冻结日历可得 `complete`；其余给精确 gaps 或 `unknown_calendar`。 | `NOT_RUN` |
| AC-197-005 | 对完整本地数据运行 `local_first`，记录 adapter 调用计数。 | 零网络、零新增来源快照；返回 sealed 本地 provenance。 | `NOT_RUN` |
| AC-197-006 | 已获当前 local-read entitlement 的主体，对缺口、未知日历、retired policy 的严格历史数据分别执行 `local_only` 与带冻结 anchor 的 `local_first`。 | 两种模式均永不触网；符合历史用途授权且当前主体仍有读取权的 sealed 事实可读；严格缺口稳定返回 `HISTORICAL_COVERAGE_UNAVAILABLE` 或 `unknown_calendar`，不伪装成功。 | `NOT_RUN` |
| AC-197-007 | 在未冻结 `best_effort` 下让 `refresh` 返回零行、部分行、完整新行和未知日历；再以冻结 strict anchor 重复同一请求。 | 前者明确 `fresh_incomplete`/`fresh_complete`/`fresh_unknown_calendar`，旧缓存不被称为新鲜；后者稳定返回 `STRICT_FETCH_FORBIDDEN`，adapter 调用数为零。 | `NOT_RUN` |
| AC-197-008 | active `DgProvider` 但来源注册被禁用、license 未批准、用途不匹配、超出有效期或 principal 无 entitlement。 | adapter 调用数为零、无新 source snapshot/revision；返回稳定授权拒绝码。 | `NOT_RUN` |
| AC-197-009 | 相同 asset/market 语义，唯一改变为另一个可写 dataset code/ID。 | route 不匹配、零网络、零写入；不能污染其它逻辑数据集。 | `NOT_RUN` |
| AC-197-010 | 两条 fallback route 处理同一公共 query。 | 每个来源快照保存不同 provider request ID、receipt 回显和完整 outbound DTO 的 fingerprint；query fingerprint 仅作关联。 | `NOT_RUN` |
| AC-197-011 | provider receipt 的 provider ID、route、request ID、身份、窗口、字段、语义、重复/越界事件或载荷大小不匹配。 | 结果不落库；后续经批准 route 可继续处理真实缺口；无堆栈/凭据泄露。 | `NOT_RUN` |
| AC-197-012 | 事务 A 写入 prepared evidence 后模拟 crash；分别执行 seal、abort、reconciler 重试。 | 未 seal 事实永不出现在任意 local/PIT 读取；seal 后由 receipt boundary 可见；每一步可审计且幂等。 | `NOT_RUN` |
| AC-197-013 | 对同一事件写两次修订，并在各 visibility boundary 前后重放；再写入同一 `visible_at` 但更高 `visibility_sequence` 的 receipt。 | 早 anchor 只见较早 sealed revision；同时间的后写 receipt 不穿越 anchor，晚修订不能回写或覆盖旧事实。 | `NOT_RUN` |
| AC-197-014 | 篡改一个格式合法 cursor 的 `knowledge_cutoff_at`、`max_visibility_sequence_at_or_before_cutoff`、排序 anchor、fingerprint、policy hash；跨主体/entitlement 重放。 | 在 resolver/store/provider 前以签名/主体错误失败，零网络、零写入。 | `NOT_RUN` |
| AC-197-015 | 正常分页期间写入较晚 revision、同一 `visible_at` 的更高 sequence receipt，或变更当前 policy。 | 后续页仍使用首屏冻结的完整 visibility anchor 和 policy descriptor；不触发在线补齐。 | `NOT_RUN` |
| AC-197-016 | AkShare 对每个启用 route 返回正确与错误市场/代码、越界时间、超时、超大响应和不支持资产。 | route 精确、有界、稳定失败；不访问遗留样例或其它资产。 | `NOT_RUN` |
| AC-197-017 | OpenBB runner 验证配置缺失、协议版本/ID 错配、非零退出、无效 JSON、超时、超大输出、声明转换语义。 | 主 Web 进程不加载扩展；runner 失败关闭；不合格结果不写入。 | `NOT_RUN` |
| AC-197-018 | 对所有七类资产和当前页面数据类型各选择一条批准 identity/窗口；没有安全 route 的组合也执行。 | 每行使用与 `data_kind` 相容的 bars/snapshot/event frequency semantics，得到本地命中/精确补齐，或明确 `UNSUPPORTED`/`NOT_CONFIGURED`；不得静默降级。 | `NOT_RUN` |
| AC-197-019 | 保存一个完整策略/回测工件后，分别篡改 provenance body、manifest hash、schema ID/version、payload 字节、payload hash 和 artifact fingerprint，并尝试读取/重放。 | 写入、读取与重放均重新计算并校验四类完整性字段；任一缺失或不匹配稳定拒绝，不能反查数据库补齐。 | `NOT_RUN` |
| AC-197-020 | 对原本可读的 sealed 事实与策略工件，使用无 entitlement 或已撤销 local-read entitlement 的 principal 执行 local-only、strict replay 和工件消费。 | 在 store/coverage/provider 前拒绝；历史采集决定不构成当前读取许可；零网络、零写入。 | `NOT_RUN` |
| AC-197-021 | 同一 `(data_series_id, event_at)` 写入多次 revision，包括同一 logical boundary、不同 `revision_ordinal` 和人为冲突的相同排序键/不同 fields hash。 | 完整 anchor 内选择最大 `(visibility_sequence, revision_ordinal, revision_id)`；排序键冲突且内容不同返回 `EVIDENCE_CONFLICT`，绝不按 `available_at`/`created_at` 猜测。 | `NOT_RUN` |
| AC-197-022 | 两个 196/197 migration 执行器同时启动；分别给出正确/错误预期起始 revision，并模拟兼容窗口内旧版应用与迁移失败。 | 单一 lease holder 执行 DDL；竞争者和错误 revision 在 DDL 前 fail-closed；旧新应用可运行，失败走前向修复/恢复且不删除不可变证据。 | `BLOCKED` |
| AC-197-023 | 分别提交 bars、quote snapshot、option chain、position report、reference series 的有效和无效 frequency semantics。 | 仅接受定义的组合；`null`、bars 搭配 `snapshot`、snapshot 搭配 bars 粒度和未注册 `event` 都在 resolver/provider 前稳定拒绝。 | `NOT_RUN` |
| AC-197-024 | 缺失/冲突的 dataset、selector、字段、用途、一致性、`knowledge_cutoff_at`/anchor、读取模式或语义轴；非法 UTC 半开窗口、超限窗口/页大小；客户端伪造 query fingerprint、provider request ID、authorization 决定或 cursor 签名。 | 严格 DTO 在 resolver/store/provider/写入前拒绝；query fingerprint 只可由服务器从业务语义生成，不能代替 outbound request、授权或 HMAC cursor。 | `NOT_RUN` |
| AC-197-025 | 同一缺口和同一 refresh intent 并发提交、HTTP 重试、重复 provider receipt、lease 失效和旧 worker 继续尝试 prepare/seal/abort。 | 同一 logical ingestion key 只有一个当前 fencing-token owner；并发者等待后 local reread；重复请求/receipt 不产生第二个 sealed snapshot 或 revision，旧 token 操作稳定拒绝。 | `NOT_RUN` |
| AC-197-026 | 对各一个 `research` 与 `backtest` 工件，在冻结 196 ref/schema/hash 后生成 provenance 和完整 visibility anchor，随后添加 identity、lookup key、calendar、revision、policy、同 timestamp 高 sequence receipt 及权限变化，再按原 anchor 重放。 | 两种工件分别保存并校验完整 provenance 与 artifact fingerprint；原 anchor 看不见后来事实，遇到历史缺口绝不调用 provider，内容或 schema/hash 篡改失败。 | `BLOCKED` |
| AC-197-027 | 逐一保持 IG-196-01 至 05 未通过或让固定 196 ref/schema/head/环境身份漂移，再尝试启用 v2 页面切换、策略工件消费或 online fetch。 | 每一种未解除/漂移情形均保持相应开关和运行时路径关闭；只返回稳定 `BLOCKED`/拒绝码，无页面读取、工件消费、网络或写入副作用。 | `BLOCKED` |
| AC-197-028 | 两个不同 principal/tenant 以相同 query、不同 entitlement/policy/visibility anchor 交替请求，并施加并发、限流和缓存命中压力。 | 缓存键和授权复核不跨越数据集、主体、entitlement、policy 或完整 anchor；不因缓存命中绕过限流/读取授权，返回内容和 provenance 不泄漏。 | `NOT_RUN` |
| AC-197-029 | 对 AkShare/OpenBB 配置、请求字段和异常文本注入 shell 元字符、过长值、敏感 token；检查 runner 进程、argv/stdin、环境和日志。 | runner 只使用受控 argv/JSON，不能执行拼接 shell；主应用凭据不进入 runner；错误、指标和审计记录脱敏且无密钥/未授权原始载荷。 | `NOT_RUN` |
| AC-197-030 | 对在线获取、本地读取和工件消费分别施加 license 过期、用途不匹配、辖区限制、保留到期、禁止再分发与 entitlement 撤销。 | 依据适用层稳定拒绝；历史 provenance 保留但不能突破当前 local-read/再分发约束；禁止动作零网络、零新证据、零跨主体泄漏。 | `NOT_RUN` |
| AC-197-031 | 触发本地命中、未知日历、route/online-read/local-read 拒绝、receipt mismatch、prepared/sealed/aborted、lease/fencing、cursor、质量和 provider 失败，并使告警阈值跨越。 | 每项产生规定的匿名化审计字段、指标和可操作告警；无秘密/原始敏感值，候选 SHA 与关联 ID 可将事件串联到证据。 | `NOT_RUN` |
| AC-197-032 | 以冻结 196 ref 生成 `MD-197-SCOPE-MANIFEST`，逐行比对 `/data/market`、`/investment/strategies`、后端 DTO 和数据目录中的当前组合。 | 资产、data kind、字段组、frequency semantics、语义轴、消费方、数据集和预期 route/`UNSUPPORTED`/`NOT_CONFIGURED` 一行不漏；输入版本和行 hash 可复核。 | `BLOCKED` |
| AC-197-033 | 在受控灰度下对七类资产、legacy `daily`/`weekly`/`monthly`、期货 market、日期区间、默认 lookup、`refresh_online=true` 和携带 strict anchor 的相同请求逐一经过行情页 facade。 | legacy projection 兼容；未冻结 display 默认转换为 local-first，已批准 refresh 才可触网；strict anchor 下绝不触网；结果来自 sealed local reread 并含 coverage/provenance，未持久化在线 payload 不可返回。 | `BLOCKED` |
| AC-197-034 | 对策略 UI 的 `symbol`、`timeframe`、`timeframe_n`、日期和已有/缺失/冲突的 `data_config` 测试全部七类资产，尤其是 option 与无法精确推断的输入。 | 只接受能形成完整 typed `MarketDataQuery` 和 sealed provenance 的请求；无完整 identity/provider/series/adjustment 时 fail closed，IG-196 未解除时策略读取/运行路径保持 `BLOCKED`。 | `BLOCKED` |
| AC-197-035 | 交叉测试 market query UI、coverage UI、strategy UI 的各个频率值，以及每个已批准 provider route、日历和本地 store。 | `daily`/`weekly`/`monthly` 只映射 `1d`/`1w`/`1mo`；`1h`/`30m`/`5m` 仅在已登记 route 后启用；coverage/策略 UI 的声明不能越过实际 capability，裸 `1m` 在 v2 拒绝。 | `NOT_RUN` |
| AC-197-037 | 在 bundle 开启后，对每个 21-family 卡片发放的 query contract 修改 family ID、版本、数据集、data kind、频率、字段或 source policy。 | server 在 identity/catalog 解析后拒绝全部轴漂移；query fingerprint 与所有分页响应保持相同 family binding。关闭 bundle 时的裸 bars compatibility path 单独标记，不得作为 family 覆盖证据。 | `NOT_RUN`：候选离线回归可作为实现证据，浏览器/API 联合灰度仍未执行。 |
| AC-197-038 | 写入或读取 `close='--'`、`N/A`、非有限数值、无效日期/时间、legacy `quality='pass'` 占位 revision。 | 新写入拒绝或规范化为不可用；coverage 保留 rejection reason；产品 API、分页和页面均不返回/绘制该 revision，更不能以 0 补值。 | `NOT_RUN`：需要冻结候选 SHA 的完整离线输出和浏览器/API 联合证据。 |
| AC-197-039 | 尝试以 offline `--sql`、未设置围栏的 MySQL、锁竞争、错误 revision、未停止 writer 和 downgrade 执行 shared binding migration。 | 每种未满足前置条件在 DDL 前 fail-closed；只有外部 writer-drain 证据、授权围栏和具名锁齐备时才可进入真实演练。 | `BLOCKED`：未授权真实数据库和维护窗口。 |
| AC-197-040 | OpenBB runner 返回重复规范化字段键、records 与 raw payload 不一致、并发请求超过运行器容量。 | 重复键/证据投影不一致稳定拒绝；过载请求不产生子进程；正常请求仍保留 request ID、raw payload 和规范化 projection 的可复算关联。 | `NOT_RUN`：真实 OpenBB operator 环境尚未执行。 |
| AC-197-036 | 首屏 strict query 冻结 anchor 后，追加一条 `visible_at` 与 anchor 时间相同、但 `visibility_sequence` 更高的 receipt（包含新事件或新 revision），再分页和严格重放。 | 新 receipt 绝不出现在首屏后页、cache 命中或原工件重放中；完整 `(knowledge_cutoff_at, max_visibility_sequence_at_or_before_cutoff)` 被 HMAC、provenance 和缓存 key 一致绑定。 | `NOT_RUN` |

## 6. 严格重放和工件验收

### 6.1 AC-197-026 的详细证据步骤

对 `research` 与 `backtest` 各选一个经过批准的数据集，执行：

1. 以带时区的 cutoff 解析并冻结完整 visibility anchor，再生成 `MarketDataQueryProvenance`。
2. 在 cutoff 后新增 instrument、lookup key、calendar、observation revision 和 policy 更新。
3. 用原 visibility anchor 和 provenance manifest 重放，记录 provider 调用计数为零。
4. 比较 canonical ID、metadata version、dataset ID、data series ID、calendar snapshot/version、policy descriptor hash、visibility receipt、source snapshots、revision IDs、字段 hash、`provenance_manifest_sha256`、artifact schema ID/version、`artifact_payload_sha256`、`artifact_fingerprint` 和输出行。

期望是两次重放结果完全一致，且看不见 cutoff 后事实。每个差异都按 `FAIL` 处理，不能用“上游数据更新”解释。

### IG-196 整合闸门

| 闸门 | 通过条件 | 当前状态 |
| --- | --- | --- |
| IG-196-01：接口冻结 | 196 研究/策略/回测的输入输出和工件 schema 已冻结，并有兼容性说明。 | `BLOCKED` |
| IG-196-02：迁移单 head | 196/197 Alembic 链合并，`alembic heads` 恰一个 head；migration lease、预期 revision preflight、跨版本兼容和升级/恢复演练通过。 | `BLOCKED` |
| IG-196-03：provenance 工件 | 196 保存完整 `MarketDataQueryProvenance`（包括完整 visibility anchor）、manifest hash、artifact schema ID/version、payload hash 和 artifact fingerprint，并拒绝缺失/篡改；不能仅存 policy ID 或可反查数据库键。 | `BLOCKED` |
| IG-196-04：行情页灰度 | `/data/market` 在关闭默认开关、授权和回退保护下完成 API/浏览器/DB 证据。 | `BLOCKED` |
| IG-196-05：策略页灰度 | `/investment/strategies` 只消费 sealed、严格工件；端到端历史重放通过。 | `BLOCKED` |

## 7. 真实数据和数据库验收

### 7.1 真实 AkShare/OpenBB

只能在来源条款、账户权限、限频和许可证已确认的环境执行。每次使用最小公开标的和小窗口，保存脱敏的请求语义、route、provider request ID、source snapshot ID、visibility receipt ID、revision IDs、字段 hash、网络计数和后续 `local_only` 复读结果。

真实 provider 成功不等于可全面启用。每个 provider/market/asset/data-kind/semantic combination 都需要独立批准；未批准组合保持路由未注册。

### 7.2 数据库迁移与灾备

在可恢复、生产拓扑等价的 MySQL/PostgreSQL 副本上：

1. 记录升级前 revision、schema、遗留 AkShare 表行数与抽样哈希。
2. 以两个并发执行器验证具名 migration lease，持有者在 lock 下重新校验预期起始 revision；竞争者或 revision 不符者必须在 DDL 前停止。
3. 确认合并后仅一个 Alembic head，并验证 expand/migrate/contract 兼容窗口中的旧新应用行为。
4. 升级后审计目录、证据、visibility receipt、FK、唯一约束、索引和不可变保护。
5. 验证迁移不改写遗留 AkShare 事实。
6. 对 prepared-but-unsealed 事实演练恢复与 reconciler；验证它们默认不可读。
7. 备份恢复后执行 `local_only` 严格重放并比对 provenance 与 artifact fingerprint。

任何多 head、并发 DDL、revision 预检绕过、旧新版不兼容、回滚静默删除证据、恢复后谱系/完整性指纹不一致或未 seal 事实可读均为 `FAIL`。

## 8. 上线和回退判定

建议顺序：先离线候选 → 迁移/恢复演练 → 一个许可来源的 local-only → 受控 local-first 小窗口 → 行情页灰度 → 196 工件绑定 → 策略页灰度。

以下任一项发生时停止扩大灰度并关闭相关在线 route：身份/数据集/receipt 不匹配；未知日历却声明完整；严格读取泄露未来事实；cursor 签名/主体绑定失效；许可或 entitlement 绕过；未 seal 事实可读；迁移多 head；196 工件缺少 provenance。

关闭在线获取和 v2 查询开关是可逆动作。不得为回退删除 source snapshot、revision、calendar、policy descriptor 或 visibility receipt；任何数据处置都必须按保留/许可策略产生治理记录。

## 9. 最终签收清单

- [ ] E-197-01 与 E-197-02 在候选 SHA 上 `PASS`。
- [ ] AC-197-001 至 AC-197-036 都有与场景匹配的证据。
- [ ] MySQL/PostgreSQL 迁移、恢复和 prepared/sealed 演练通过。
- [ ] E-197-10 的页面/DTO/目录范围清单与 E-197-11 的安全、合规、缓存和可观测性审计包通过。
- [ ] 所有启用的真实 provider/route/许可证/entitlement 已验收；其它组合明确未配置。
- [ ] IG-196-01 至 IG-196-05 全部解除阻塞。
- [ ] 开关、限流、审计、告警、reconciler 与回退流程已演练。
- [ ] 候选工作树无未解释改动，日志/文档/证据不含密钥或未授权原始数据。

在清单任一项未满足前，迭代 197 只能称为“设计完成”或“实现候选”，不能称为生产可用或验收通过。
