# 迭代 197：验收文档

> 本文是后续验收规范，不是实现验收报告。全部运行用例初始状态为 `NOT_RUN`。
> 本次仅做文档一致性检查；没有请求行情、修改数据库或执行产品代码测试。

## 1. 状态与门禁

| 状态 | 含义 |
| --- | --- |
| PASS | 在本次冻结代码/配置/数据上执行，断言与证据都满足 |
| FAIL | 已执行且违反合同 |
| BLOCKED | 缺来源授权、环境、有效数据或 196 等外部前置；写清具体缺项 |
| NOT_RUN | 没有执行；不能被合并统计为通过 |

`UNSUPPORTED` 是某查询组合的能力结果；“正确拒绝不支持频率”用例可以 PASS，但这不等于取得该频率数据，也不能用来删除原本支持的功能。历史产物、synthetic connector、mock/录制回放不能作为本轮真实来源验收。

| 门 | 范围 | 通过要求 |
| --- | --- | --- |
| G0 | 实施现场基线与合同 | 冻结代码、189/196 接口、数据范围、来源权限、主数据、DDL/容量、依赖、验收负载；当前设计交付不等同 G0 全部通过 |
| G1 | 确定性正确性 | 身份/日历/覆盖/质量/幂等/权限/版本及所有适配合同通过；有外网拒绝约束的测试 |
| G2 | 真实应用与本地持久化 | 隔离真实数据库 + 候选 API/UI/worker，使用可控来源验证写入、重启、多进程和两页流转；fixture 来源显式标明 |
| G3 | 真实来源与联合研究 | 七类实际数据闭环；OpenBB 至少一条同范围真实来源闭环；196 最终实际接口与受控 runner 消费证据 |
| G4 | 容量、迁移与灰度运维 | 性能达标、升级/存量导入/备份恢复/回滚/真实环境访问拒绝、连续灰度观察通过 |

完整结项：所有 P0 对应 G1—G4 通过，G0 未决清零；`FAIL=0/BLOCKED=0/NOT_RUN=0`。如果七类之一只能完成本地合同而真实来源阻塞，允许报告该切片已完成，完整迭代继续保持未验收。196 未就绪时单列 `BLOCKED_DEPENDENCY_196`，不能宣称联合研究已通过。

## 2. 验收环境与证据包

### 2.1 环境配置

- 所有写入、故障注入、迁移和恢复使用隔离数据库/对象目录，不使用业务库做破坏性测试。
- G1 阻断外网，来源以明确 fixture 提供；G2 使用真实候选 API/数据库和至少两个 worker 进程，不能用内存 repository 替代。
- G3 使用获准的真实 endpoint/数据，不打印凭据；选择与请求语义对应的有效标的和窗口，不随机选一个成功代码代替失败标的。
- MySQL、PostgreSQL 的并发与事务分别执行；SQLite 执行单 writer 的完整持久化/恢复合同，不用 SQLite 通过代替另外两个数据库。
- 固定来源时间与冻结日历测试周末/休市；真实源验收记录实际采集时间、实际市场时间及所用权限。

### 2.2 每次运行的证据

保存到拟建 `docs/iterations/迭代197-统一数据中台与OpenBB本地优先集成/evidence/<run-id>/`，至少包含：

| 文件 | 内容 |
| --- | --- |
| `manifest.json` | 候选 Git SHA/dirty allowlist、构建/依赖 hash、数据库类型/版本、政策版本、执行时间、case IDs |
| `capability-matrix.json` | M/F 项、市场/标的/频率/kind、declared/installed/verified、所需 key/权限、真实状态 |
| `query-and-provider-trace.jsonl` | 归一请求、gap plan、实际调用/窗口/分页、失败/重试和来源关联；全部脱敏 |
| `storage-receipts.jsonl` | batch/work/version、事务提交回执、行数/hash、覆盖重读；不只报“保存成功”字符串 |
| `db-invariants.json` | 唯一键、重复有效行=0、revision、未提交行不可读、outbox 一致性 |
| `snapshot-manifests.jsonl` | 实际 artifact bytes/schema hash、版本/切分/预检/run 绑定、重放对照；外部报告不放受控 URI |
| `tests.xml`、`ui-traces/` | 机器测试结果、Playwright trace/截图、API request ID；说明来源是否 mock |
| `performance.json` | 负载、样本数、P50/P95/P99、网络调用、CPU/内存/IO、执行计划 |
| `migration-restore-report.md` | 迁移前后行数/DDL/hash、坏行台账、RPO/RTO、回滚读回 |
| `result.json` | 每条 case 的 PASS/FAIL/BLOCKED/NOT_RUN 和证据引用；汇总不能吞掉 skips |

保存许可证允许的原始证据，受限材料只存受控引用和 hash。公开文档不得泄漏用户数据权限、连接串、密钥或受控工件地址。

## 3. 核心功能用例

### 3.1 本地优先与覆盖

| ID / 门 | 场景与步骤 | 必须断言 |
| --- | --- | --- |
| AC-01 / G1,G2 | 注入完整合格历史，阻断所有 Provider 网络，查询两次并重启 API/worker 再查 | 内容相同；外部调用=0；version/persisted 正确；不能依赖内存缓存 |
| AC-02 / G2,G3 | 空规范库、无可用 legacy，发 local_first → provider 返回 → 写入 → 重查 100 次 | 首次数据有 committed receipt；后续 100 次及重启后网络=0；所有行可读回 |
| AC-03 / G1,G2 | 构造头部 3、中间 2、尾部 5 个缺 session；同时有大量已保存行 | 精确 gap 集合和实际提取窗；只补缺口或已声明来源最小块；最终 100% |
| AC-04 / G1,G2 | 本地只存起止两天/260 行，查询跨 3 年 | MIN/MAX 有交集不能 PASS；分页全部读完无截断，无遗漏/重复 |
| AC-05 / G1 | 日历覆盖节假日、午休、夜盘、DST、周末、crypto 24×7、已证实停牌 | expected 与独立人工/fixture oracle 一致；未知停牌仍是 gap |
| AC-06 / G1,G2 | 查询未来日期、上市前/退市后、未收盘日/周/月；再查完整旧历史窗口 | requested/effective range 及理由正确；provisional 不进入严格研究；旧历史不因当前日期变晚就重复下载 |
| AC-07 / G1,G2 | 报价过 TTL、日线仍完整，执行普通查询和显式 refresh | 只更新需要刷新的 kind；观测时间与抓取时间分开；显式刷新额度和 commit 生效 |
| AC-08 / G1,G2 | 分别返回 429、暂时空、确证不存在、未发布报告，随后补新主数据或到达新发布时间 | 负缓存按源/类型失效；错误空结果不把 coverage 标 complete；不会热点风暴 |

### 3.2 身份、资产和数据语义

| ID / 门 | 场景与步骤 | 必须断言 |
| --- | --- | --- |
| AC-09 / G1,G2 | 同代码不同资产/交易所、SH/SZ 前后缀、期货到期月、期权到期/strike/call-put | canonical identity 完整，歧义拒绝或明确选项，不返回首个样例 |
| AC-10 / G1,G2 | 请求不存在标的或原范围外数据，同时库内有其他热门样例 | 不替换 symbol/market；范围外数据不计覆盖，不进入策略 |
| AC-11 / G1,G2 | 对比 qfq/hfq/raw、不同复权 vintage、连续/具体期货合约 | 不混写/混拼；修订生成新版本，连续合约有明确来源和换月规则 |
| AC-12 / G1,G2 | 1m/月与 1m/分钟、1M、timeframe_n；5min 聚合 30min/1h/周/月 | 入口映射无歧义；成交量/OI/settle 聚合规则正确；缺基础行时聚合不合格；日线无法伪造分钟 |
| AC-13 / G1,G2 | 同时传 bars、期权链和 CME 报告 | chain 按 snapshot+contract，report 按 report identity；不按行数冒充交易日、不把持仓画成价格 |
| AC-14 / G1,G2 | 人工设置合法零量、null、负期货价、单位手/股/币、percent/fraction、ETF价/NAV、FX牌价 | 按各数据合同转换或拒绝；不统一补零/强制正价，不混淆单位和报价口径 |
| AC-15 / G1,G2,G3 | 逐项执行 DATA_SCOPE 的 M-STOCK—M-CRYPTO 和 F01—F21 | 每项独立结果；所有当前可用功能成功/复用证据齐全；目录主题如实标签，没有夸大“风险曲面已就绪” |

### 3.3 来源与持久化

| ID / 门 | 场景与步骤 | 必须断言 |
| --- | --- | --- |
| AC-16 / G1,G3 | AkShare 主源失败，获准且等价的 OpenBB 后备成功；反向安排主源顺序 | 路由遵守 policy；真实来源/platform/upstream 保留；后备数据写入后重复查不联网 |
| AC-17 / G1,G3 | OpenBB 模型存在但中国期货/可转债或币对不可用；再提供不等价替代 | 不能以 Yahoo 海外期货替 RB、BTCUSD 替 BTCJPY、CNY 替 CNH；明确 unsupported/source mismatch |
| AC-18 / G1,G2 | 缺 key、授权套餐不足、schema 漂移、超时、5xx、429；多 SDK 同 upstream | 不可重试错误 0 额外重试；总预算、共享额度、Retry-After、熔断、可终止 runner 均生效 |
| AC-19 / G2 | Provider 成功后在 DB 写入处注入异常，保留 durable raw | 不返回新行已保存或可研究；从 raw 重试，不再调用来源；若 raw 未持久要明确重抓 |
| AC-20 / G2 | 数据行写入后 coverage/version 更新前异常，再于事务 commit 后响应前断线 | 前一种全部不可见；后一种可幂等恢复且不重抓；覆盖与行一致 |
| AC-21 / G2 | 同业务键相同内容重复导入，再导入修订值；同 series 不同来源并发发布，读取分页及多 series 快照 | 相同内容 no-op，修订追加；旧版仍可被 snapshot 读取；0 重复有效行；提交水位无晚提交穿越，分页版本和快照版本向量不漂移 |
| AC-22 / G1,G2 | 异常列/NaN/Inf/错误身份/顺序/日期、合格坏行混合批次 | 错误分级、raw hash、隔离行和剩余 gap 可追踪；未发布数据不进 coverage |
| AC-23 / G2 | 应用库投影写入失败、规范库已提交，重启 outbox consumer | 事实不丢，投影最终一致，重复事件幂等；不因 UI 元数据失败重采集 |

### 3.4 并发和恢复

| ID / 门 | 场景与步骤 | 必须断言 |
| --- | --- | --- |
| AC-24 / G2 | 20 个并发同缺口、两个 worker；另测试部分重叠区间及采集中新增区间 | 正常场景同源最小块一次有效提取；区间合并正确，新增尾部不丢，所有请求独立权限 |
| AC-25 / G2 | worker A 拿 lease 后阻塞，过期由 B 接管，再让 A 返回 | A 被 fencing 拒绝；B 在恢复 SLO 内纳管；外部重复调用如实计数，数据库仅一份有效发布 |
| AC-26 / G2 | 提取/暂存/校验/提交各阶段 kill；全部重启 | 状态可解释恢复，无永久 RUNNING；有 raw 从 raw 恢复；commit 后不重放 |
| AC-27 / G2 | 两个查询共享 work，取消其中一个，再取消最后一个/到 deadline | 不影响未取消订阅者；不得杀其他工作；必要时停止 runner；无超时残留进程 |
| AC-28 / G2 | 模拟超配额、队列满、磁盘水位不足 | 受理/执行前阻断或延期；不超卖预算，不删历史数据腾空间；本地满足的查询仍成功 |

## 4. 两页与研究集成用例

| ID / 门 | 场景与步骤 | 必须断言 |
| --- | --- | --- |
| AC-29 / G2 | 行情页七类切换，出现部分缺失→补齐→已保存；另测失败/延迟/无权限 | 实际 API 与 UI 一致；保留本地部分，图/表类型正确；无“在线成功=已保存”误报 |
| AC-30 / G1,G2 | 查询 A 后快速切 B，A 的 provider/轮询晚返回；卸载页面 | A 不覆盖 B，状态/图表/任务绑定 query_id；订阅释放，键盘可操作 |
| AC-31 / G2 | 对照精确查询、coverage 矩阵、trust precheck，同一 series/version | 行数/时间/字段/质量一致；错误 legacy summary 不能使 precheck 通过 |
| AC-32 / G1,G2 | 旧 lookup false/true、kline 格式、options、dg preview、相关表浏览 | false 仍无网络、true 显式刷新；新页面默认 local_first；synthetic/preview 不呈现 committed |
| AC-33 / G2,G3 | 策略页 ensure → artifact → precheck → 请求启动，七类身份及 4 个频率均测试能力 | 支持组合成功；不支持组合原因准确；更换参数使旧预检过期，不自动创建新 epoch |
| AC-34 / G2,G3 | 固定工件，核对预检 hash、实际 runner 打开文件及全部内容 hash | 实际消费与预检一致；没有 CSV 模糊合约匹配或运行中临时联网 |
| AC-35 / G1,G2,G3 | 更换 artifact bytes、schema、URI 或原始 dataset revision 后请求研究 | hash/绑定验证拒绝；冻结旧工件不被覆盖；新 revision 不能偷偷进入旧实验 |
| AC-36 / G1,G3 | 用 196 Explorer token 访问 sealed URI，以及同范围 `/queries`、legacy kline/表导出/原库/provider | 每条通路真实拒绝，不能依靠只隐藏 URI；credential/文件挂载/网络身份隔离有运行证据 |
| AC-37 / G1,G3 | 当前下载的旧历史无发布证据、供应商后修订、freeze 前数据冒充 forward | LATEST_REPRODUCIBLE 与 AS_KNOWN_THEN 分明；strict PIT 拒绝；forward 只能使用 freeze 后观测 |
| AC-38 / G2,G3 | 来源不可用/修订后，对冻结候选断网冷重放 | 数据内容 hash 100% 一致；明确 196 的 runner/候选合同若未就绪则 BLOCKED |

## 5. 权限、迁移与运维用例

| ID / 门 | 场景与步骤 | 必须断言 |
| --- | --- | --- |
| AC-39 / G1,G2,G3 | 同数据不同用户/共享域、撤销 license、只允许 display 不允许 persist/research/export | 复用前重新授权；未获准数据不能落库或跨域读取；请求用途不可自行提升权限 |
| AC-40 / G1,G2 | 把 token/DSN/原始 SQL/控制 URI 放入异常和 provider extra；模拟 Agent 引用 | 浏览器/日志/导出无泄漏；引用只能指向有权限且可验证的数据版本；synthetic 仍可辨认 |
| AC-41 / G2,G4 | 带真实形状存量表/CSV的迁移，存在重复/未知复权/缺字段/正在追加数据 | input=accepted+quarantined+conflicting+skipped（去重策略单列）；原表/文件不改，断点追赶无丢行 |
| AC-42 / G2,G4 | MySQL、PostgreSQL、SQLite 分别 upgrade/check；隔离空库 downgrade/再升；189/196 不同迁移基线 | 每事务域唯一合法 head；旧行可读；不在 request 做 DDL，不把一个引擎结果外推全部 |
| AC-43 / G2,G4 | 旧脚本调度写 legacy，新 importer/用户补齐同时触发 | 旧 task ID/SQL/表保持，规范发布幂等；preview 状态不会被当采集成功 |
| AC-44 / G4 | shadow → canary → provider/应用回滚；写主库交接各步骤注入崩溃，并让旧 worker 晚返回 | 影子读不增加外部流量；七类分别观察；新规范数据和快照完整保留，兼容读取或明确暂停；旧库 epoch 停写后才激活新库，恢复和回切始终只有一个 write_primary；旧 generation 拒绝发布，落后副本不能冒充新版本 |
| AC-45 / G4 | 同水位备份目录库、规范库及对象，恢复到新环境 | RPO≤24h/RTO≤4h；全部 pin 工件和引用 hash 可读；不是只恢复一份 SQL dump |
| AC-46 / G4 | 固定负载执行 NFR-01，查询 1,000 万行基准库、20 并发；另做 100 次复用 | P95/P99 达标、执行计划走索引、实际网络调用=0；记录冷数据库/暖数据库和进程重启结果 |
| AC-47 / G2,G4 | 删除响应缓存，延迟 outbox、kill worker、制造保存失败和 hash 错误 | 告警/trace 定位到 query/work/batch/version；metrics 不依赖页面自报命中，不泄漏高基数敏感标签 |
| AC-48 / G4 | GC 扫描未引用对象，存在 pin/正在提交/超期 raw；模拟磁盘不足 | 只清理经过标记/复核/保留期的获准对象；pin/事务对象不删；保留模式与 raw 可重放状态真实 |

## 6. 真实资产验收账本

下面每行都必须留独立 trace、storage receipt 和二次查询证据。标的/日期在 G0 填写，不能用一个硬编码的过期合约验收所有环境。

| 覆盖项 | 标的/市场/窗口 | 真实源/数据 kind | 首次取数和落库 | 重启后复用 | 策略准备/或语义拒绝 | 初始状态 |
| --- | --- | --- | --- | --- | --- | --- |
| M-STOCK | G0 冻结 | AkShare / bars+quote+已有估值 | 待执行 | 待执行 | 待执行 | NOT_RUN |
| M-FUTURES | G0 冻结 | 中国合约 / bars+settle+OI | 待执行 | 待执行 | 待执行 | NOT_RUN |
| M-BOND | G0 冻结 | 可转债 / bars+quote | 待执行 | 待执行 | 待执行 | NOT_RUN |
| M-FUND | G0 冻结 | ETF / bars+quote | 待执行 | 待执行 | 待执行 | NOT_RUN |
| M-OPTION | G0 冻结 | 具体合约 bars + 到期月 chain | 待执行 | 待执行 | chain 不得冒充 bars | NOT_RUN |
| M-FX | G0 冻结 | 行情 bars+quote / 牌价分离 | 待执行 | 待执行 | 待执行 | NOT_RUN |
| M-CRYPTO | G0 冻结 | 指定币对 quote/实际支持 bars + CME report | 待执行 | 待执行 | report 不得冒充 bars | NOT_RUN |
| OPENBB-LIVE | 七类范围中实证可用组合 | 实际 OpenBB provider，不能只用与当前范围无关的 AAPL demo | 待执行 | 待执行 | 对应合格数据集生成工件 | NOT_RUN |

若某类在旧实现本来只有快照/结构数据，完成这些实际功能的持久化仍必须验收；请求 bars 时应补到真实 bars 或正确拒绝。拒绝用例不能替代该类已有成功功能的验证。OpenBB 合并进通用闭环的证据是独立必需项。

G4 建议在 staging 连续观察至少 5 个交易 session，包含一次闭市/重新开市；crypto 包含连续 7 个自然日。按 dataset/source 记录命中、gap、429、保存失败和身份冲突；真实市场等待期不能压缩为 fixture 时间跳跃。

## 7. 需求—设计—验收追踪

| 需求 | 设计位置 | 具名验收 |
| --- | --- | --- |
| FR-01 | D1/D9；DATA_SCOPE | AC-15, AC-29, AC-33 |
| FR-02 | D3/D11 | AC-41, AC-42, AC-43 |
| FR-03 | D2 | AC-09, AC-10 |
| FR-04 | D4 | AC-01, AC-02 |
| FR-05 | D4 | AC-03, AC-04, AC-24 |
| FR-06 | D2/D4 | AC-05, AC-06, AC-13 |
| FR-07 | D2/D4/D7 | AC-11, AC-12, AC-14 |
| FR-08 | D5 | AC-16, AC-17, OPENBB-LIVE |
| FR-09 | D5/D6 | AC-17, AC-18, AC-28 |
| FR-10 | D7 | AC-19, AC-20, AC-23 |
| FR-11 | D6/D7 | AC-21, AC-24, AC-25, AC-26, AC-27 |
| FR-12 | D7 | AC-10, AC-14, AC-22 |
| FR-13 | D2/D7 | AC-11, AC-21, AC-35, AC-37 |
| FR-14 | D8 | AC-29, AC-31, AC-32 |
| FR-15 | D9 | AC-07, AC-29, AC-30 |
| FR-16 | D3/D4/D8 | AC-03, AC-04, AC-31 |
| FR-17 | D9/D10 | AC-33, AC-34 |
| FR-18 | D10 | AC-35, AC-36, AC-37 |
| FR-19 | D10 | AC-34, AC-35, AC-38 |
| FR-20 | D11 | AC-32, AC-41, AC-42, AC-43 |
| FR-21 | D6/D11 | AC-26, AC-27, AC-43 |
| FR-22 | D2/D3/D5/D10 | AC-18, AC-36, AC-39, AC-40 |
| FR-23 | D12 | AC-47 |
| FR-24 | D11/D12 | AC-44, AC-45, AC-48 |
| FR-25 | D5/D8/D10 | AC-15, AC-17, AC-32, AC-37, AC-40 |
| NFR-01 | D3/D12 | AC-46 |
| NFR-02 | D4/D5/D8 | AC-18, AC-29 |
| NFR-03 | D4/D6 | AC-01, AC-02, AC-24, AC-46 |
| NFR-04 | D6 | AC-25, AC-26, AC-27 |
| NFR-05 | D2/D10 | AC-34, AC-35, AC-38 |
| NFR-06 | D3/D11 | AC-42 |
| NFR-07 | D5/D12 | AC-27, AC-28, AC-45, AC-48 |
| NFR-08 | D9 | AC-29, AC-30 |
| MIG-01 | D11 | AC-41, AC-43 |
| MIG-02 | D3/D11 | AC-42 |
| MIG-03 | D8/D11/D12 | AC-32, AC-44, AC-45 |
| MIG-04 | D10 | AC-33—AC-38 |

## 8. 后续执行命令合同

这些是后续开发/验收命令模板，本次未执行。`tests/market_data_platform/` 和 `scripts/acceptance/iteration197_data_platform.py` 尚待实施，不能将当前不存在的命令写成已通过。macOS Python 命令一律使用用户 Anaconda base；Provider runner 的独立锁定环境由验收脚本调用。

```bash
cd /Users/yunjinqi/Downloads/backtrader_web/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q tests/market_data_platform/
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q tests/test_market_instrument_api.py tests/test_market_instrument_freshness.py tests/test_market_data_coverage_service.py tests/test_market_data_precheck_service.py tests/test_data_trust_api.py tests/test_akshare_script_service.py tests/test_akshare_scheduler.py
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m ruff check app/services/market_data app/models/market_data_platform.py app/schemas/market_data_platform.py tests/market_data_platform
cd /Users/yunjinqi/Downloads/backtrader_web/src/frontend
npm run typecheck
npm run test -- --run
npm run build
```

验收驱动脚本必须提供 `--mode offline|integration|live|recovery|performance`、`--case`、`--asset-type`、`--output`、`--dry-run`；live 检查指定的安全环境配置和已批准 source manifest，缺配置退出 `BLOCKED`。返回码约定：0=所选必须项全 PASS，1=FAIL，2=BLOCKED，3=未完整执行/无有效用例。不能在 offline 模式触发 provider 网络。

前端新增具名 `e2e/iteration197-market-data.spec.ts` 与 `e2e/iteration197-strategy-data.spec.ts`，G2 与 G3 分开配置 fixture/真实来源并生成 trace。完整产品回归使用届时基线确认的后端 `tests/` 入口；不使用根目录裸 pytest 误收集历史 live 诊断脚本。196 回归以其最终集成为准，不照抄本次状态文档中的测试数字。

## 9. 文档检查（本次交付）

检查七份文档均存在、Markdown 内部文件引用可解析、FR/NFR/MIG 在追踪矩阵无遗漏、AC-01—AC-48 定义唯一、DATA_SCOPE 覆盖七类/21 主题、所有运行状态保留 NOT_RUN，以及 Git 改动只包含本迭代文档与索引。该检查没有推导产品 PASS 的权力。
