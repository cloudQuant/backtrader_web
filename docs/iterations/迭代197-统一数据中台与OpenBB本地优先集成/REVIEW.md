# 迭代 197 方案评审意见

> 文档性质：对迭代 197 七份设计文档（README / RESEARCH / DATA_SCOPE / REQUIREMENTS / DESIGN / IMPLEMENTATION_PLAN / ACCEPTANCE）的独立评审；不是设计、需求或验收结论的替代。
> 评审日期：2026-09-05。
> 评审基线：`dev@a18bcf52` 工作区 + GitHub 远端 + OpenBB 本地仓库实测（同日）。
> 评审方法：文档一致性与追踪矩阵检查 + 关键论断代码/文件复核 + 与迭代治理约定（183/194 大文件棘轮、196 容量合同、196 评审先例）对照。

## 1. 总体结论

**这是本项目至今事实密度最高的一套设计文档**：抽查的引用全部真实（存量测试文件、`api/data/trust.py`、`assetDataFamilySpecs`、189 未合入论断、196 worktree 文件、OpenBB 本地仓库与 AGPL 声明，详见第 6 节）；数据语义的防伪劣化设计（日线不得伪造分钟线、`quote_kind=last_bar_close`、持仓不得冒充价格、PIT 双视图）和 196 依赖的诚实处理（`BLOCKED_DEPENDENCY_196`、不复制未合入实现）都达到可执行水平。

主要问题集中在三处，均属**"方案与现实之间缺一块显式粘合"**，而非方案本身错误：

1. **A1 容量现实**：计划按"两名后端 + 一名前端 + QA/运维 + 196 负责人"的虚构团队估算 74—113 人天，而本项目是单人开发；196 评审后确立的"容量与暂停合同"（196 README 8.1，FOUNDATION_CHECKPOINT 路径）在本计划中没有对应物。
2. **A2 许可证栈恶化未归属**：仓库既存的"MIT 声明 vs 生产镜像含 GPLv3 backtrader"冲突至今未修（2026-09-05 实测），197 再引入 AGPL-3.0 OpenBB worker 与镜像分发；文档承认风险但 T0—T9、G0—G4 中没有任何任务拥有"代码许可义务核定"。
3. **A3 安全面假设与存量安全债脱节**：授权模型与防密封绕过（FR-22/D10.3/AC-36）假设真实凭据与角色隔离成立，但 brokers.py 等业务端点至今无鉴权、audit `is_admin` bug 仍在（同日实测）——联合门的"真实部署拒绝证据"会建立在漏风地基上。

另有一个值得实施前解决的设计缺口（B1：series 身份键含全部版本维度，版本晋升会切断数据延续）和四个文档修订项。

**建议**：A1—A3 在 G0 签署前处置；B1 在 T1 schema 冻结前修订设计；其余随批修订。

## 2. 值得保持（修订时不要动）

- 证据纪律的延续：`NOT_RUN` 默认、BLOCKED 分类、OPENBB-LIVE 不许用 AAPL demo 顶替、"模型存在 ≠ 中国标的有数据"；
- 数据语义防伪劣化的具体合同（DATA_SCOPE 2.2 拒绝路由表、RESEARCH 2.2 不能混淆的数据清单）——这是整套文档最有长期价值的部分；
- 对 196 的边界处理：197 不重定义研究门、公共 API 不加 partition 参数放开密封、`ResearchDatasetBridge` 不把 `md_dataset_versions.id` 冒充 snapshot_id；
- 迁移克制：不动 1,106 个脚本、不删 legacy 表、不预设 189 已实现（实测确认 `data_governance.py` 确无 `DgDataset`）；
- 发布顺序与文件一致性（D7.2/D7.3）：对象先持久、epoch 锁、固定锁序、GC mark-review-sweep——这些细节在多数设计文档里是缺失的。

## 3. A 类问题（G0 签署前必须裁决）

### A1：容量假设与单人项目现实脱节，无暂停合同

**位置**：IMPLEMENTATION_PLAN 第 4 节（57—87 人天 + 30% = 74—113 人天；"建议配置两名后端、一名前端并有 QA/运维及 196 负责人参与"）、第 1 节责任表。

**问题**：

- 建议配置的团队不存在（本项目 599+ commits 单人开发，见 9/2 调研）。74—113 人天按单人全职折算约 4—6 个月，且与迭代 196 的未闭合实现债（`IMPLEMENTATION_ACCEPTED=NO-GO` 项：真实部署阶段执行器、隔离 runner、多服务隔离、冷重放）并行竞争同一份时间——196 的遗留项在本计划中只有 T7 的 `BLOCKED_DEPENDENCY_196` 一处表述，没有双线资源安排。
- 196 评审（A1/8.1）后确立的治理先例——容量评估 + 完整/分波双路径 + `FOUNDATION_CHECKPOINT`——是本项目防止"全有全无悬置"的标准机制，197 计划没有对应物。当前唯一的弹性条款是"若资源不足，允许拆 PR/里程碑"，但 DATA_SCOPE 的"已有功能不能被悄悄列为后续阶段"和 T5 退出条件"所有七类主要功能接入后才进入完整页面切换"实际上封死了按资产类的渐进交付。
- 这正是迭代 196 评审 A1 指出的同一结构性风险的更大版本。

**修正建议**：

1. T0 交付物增加**容量与波次合同**：按单人 + AI 协作口径重标人日，并预签双路径——完整路径（S0—S4 全量）与分波路径（W1 = T0—T3 + 股票日线"查询→缺口→补齐→落库→复用→工件"全链 FOUNDATION 检查点 → W2 = T4—T5 全七类 → W3 = T6—T7 两页与桥接 → W4 = T8—T9）；
2. 每个波次定义独立可验收边界与用户价值（W1 单独可灰度股票链路），波次间允许日历间隔吸收 196 等待；
3. 明确"七类全覆盖仍是完整迭代验收条件，分波只影响交付顺序与中间可用性"，避免与 DATA_SCOPE 的范围冻结冲突。

### A2：许可证栈从一处未解冲突恶化到三许可证组合，义务核定无归属任务

**位置**：RESEARCH 6（"OpenBB 核心声明 AGPL-3.0……独立进程不是自动免除义务的结论"）、D5.3（"AGPL……按实际使用核定"）；T0—T9 与 G0—G4 全部任务清单。

**问题**：

- 文档两处承认 AGPL 风险，但**没有任何任务、门禁或 AC 拥有它的结论**——T0 的"许可/保留范围"探测针对的是数据源使用许可，不是代码许可。风险被如实写下，又被如实悬空。
- 更重要的是既存冲突只字未提：仓库 LICENSE 仍声明 MIT，而生产镜像内含 GPLv3 backtrader（2026-09-05 实测 LICENSE 为 MIT、无 NOTICE；该冲突自 9/2 调研列为 P0 后未修）。RESEARCH 提到"项目后端元数据为 MIT"时未提示该冲突。
- 197 之后分发物将同时包含：GPLv3 主应用镜像 + AGPL OpenBB worker 镜像 + MIT 声明的自有代码。三个 copyleft 边界（进程隔离是否成立、AGPL 网络条款是否触发、镜像分发源码义务）叠在尚未解决的两方冲突之上，复杂度非线性上升。

**修正建议**：G0 增加具名交付物《代码许可义务矩阵》：(a) 修正既存 MIT/GPLv3 冲突（NOTICE + 声明对齐，即 9/2 调研的路径 A 最小动作）；(b) AGPL worker 的进程隔离边界与镜像分发义务结论；(c) 自有代码声明与未来双授权的保留条件。指派 owner 与完成门；在 OpenBB 镜像对外分发/联合部署（G3/G4）前必须闭合。该依赖不因商业化迭代文档被移除而消失。

### A3：安全隔离假设与仓库存量安全债脱节

**位置**：D10.3（"真实部署通过凭据、数据库 role、存储权限和出口限制验证"）、AC-36（"每条通路真实拒绝"）、FR-22（来源权限与使用政策）。

**问题**（2026-09-05 实测）：

- `src/backend/app/api/brokers.py` 仍 0 处 `get_current_user`（9/2 调研列出的 brokers/portfolio_api/prompt_templates/sync_api/live_trading_api/ai_observability 同类问题至今未收敛）；
- `src/backend/app/api/audit.py:99` 的 `is_admin` 路径仍因 TokenPayload 缺字段恒为 False。

197 的新端点可以做到完整鉴权，但 D10.3 要防的恰是"Explorer 通过公开行情接口绕过密封"这类旁路——在一个旧业务端点都不设防的应用里，"真实部署的拒绝证据"无法自证；FR-22 的授权模型对整个应用边界而言是漏风的。197 文档没有任何一处登记这批存量债。

**修正建议**：T0 基线核对显式登记存量安全债清单（至少上述两类），并将"鉴权收敛 + is_admin 修复"列为 G3 联合门的前置依赖或先行小切片（工作量周级，远小于 197 主体），否则建议 AC-36 明确写上"在存量端点收敛完成前，本 AC 只能在隔离验收环境成立"的边界。

## 4. B 类问题（实施前修订文档）

### B1：series 身份键包含全部版本维度，版本晋升会切断数据延续（设计缺口）

**位置**：DESIGN D2.2（`series_semantic_key = hash(dataset_code, canonical_id, instrument_metadata_version, frequency, multiplier, adjustment_policy_version, price_basis, currency, unit_policy_version, calendar_version, schema_version, entitlement_scope)`）。

**问题**：键中含 `instrument_metadata_version / schema_version / unit_policy_version / calendar_version`。任何一次**非语义**的元数据或政策版本晋升（例如标的描述修订、单位政策措辞调整、交易日历补充）都会派生新 series：旧 series 已落库的数据在新 series 下不可见 → 覆盖判定为空 → 触发全量重抓。这会周期性击穿"本地优先"的核心承诺（FR-04/NFR-03），且升级越频繁重抓越多。

设计未回答：哪些字段变化是"身份语义"的（理应新 series）、哪些不是（不应入键）；版本晋升时旧 series 的数据如何衔接（alias、supersede 链、覆盖 carry-over 迁移）；查询解析到新键时如何发现旧键的可复用数据。

**修正建议**：D2.2 增补《版本晋升与 series 延续规则》：(a) 区分身份语义字段（canonical_id、frequency、adjustment/price_basis/currency 等）与 lineage 记录字段（metadata/schema/policy 版本仅随行记录，不入键），或 (b) 保留现键但定义显式 supersede/carry-over 合同 + 覆盖迁移步骤，并为"版本晋升后本地数据仍可复用"新增一条 AC（当前 AC-01/AC-02 都不覆盖此场景）。

### B2：T6/T7 与大文件棘轮基线的交互未声明

**位置**：IMPLEMENTATION_PLAN T6（修改 `useDataPage.ts`、`DataPage.vue`）、T7（修改 `useStrategyPage.ts`、`StrategyPage.vue`）。

**实测**：`useStrategyPage.ts` 6,795 行——基线注释明确"kept at pre-regression baseline to force in-place fix (**ratchet only goes down**)"且存在登记的回归债务（6738→6795 递延项）；`useDataPage.ts` 2,024 行、`DataPage.vue` 728 行均在 `large_file_baseline.json` 治理范围内。

**问题**：T6/T7 对这些文件的净增长会触发棘轮门禁；按 183/194 治理，"同 PR 刷基线"被禁止（需 `ALLOW_BASELINE_UPDATE=1` + 审阅）。任务包没有大文件治理条目，实施者大概率在第一次 PR 就撞门。

**修正建议**：T6/T7 增加"大文件治理"条目：新逻辑全部落在新增文件（计划中已有 `useMarketDataQuery.ts` 等新文件，方向正确），存量文件只做接线与替换性修改并记录净变化（目标 ≤ 0）；如确需拆分，按 L 级递延规则登记到工程债切片，不得顺手重构。

### B3：NFR-01 缺"现状基线测量"步骤

**位置**：REQUIREMENTS 5（"以下为设计验收目标，不是现有性能测量。G0 冻结硬件……G4 使用相同条件测量"）、ACCEPTANCE AC-46。

**问题**：G0 冻结目标、G4 测目标，但没有先测**现有** kline/lookup/coverage 端点的 P95 基线。500ms 目标无法判断是改善还是退化；若现状已优于目标，或差距一个数量级，应走 NFR 版本化调整（196 先例：先记录基线，不合理走评审调整而不是静默降低）。

**修正建议**：T0/G0 增加"现有端点性能基线采集"输出进 evidence（`performance.json` 留 baseline 区分），AC-46 附带与基线的对比结论。

### B4：NFR-08 无障碍子句无具名验收场景

**位置**：ACCEPTANCE 第 7 节追踪矩阵（NFR-08 → AC-29/AC-30）。

**问题**：NFR-08 要求"核心组件无新增 serious/critical 可访问性问题"，但 AC-29/30 只有竞态与键盘断言，没有 axe 扫描场景；弱于迭代 196 的 AC-A11Y-001 先例（axe serious/critical=0 + 焦点管理 + 状态不只靠颜色）。

**修正建议**：AC-29 增加 axe 断言，或补一条 AC-49（对行情页/策略数据准备流程的静态 axe 场景，允许复用 196 的 a11y 测试基建）。

### B5：G3 环境维度缺"出口可达性"显式登记

**位置**：DESIGN D5.2（declared/installed/verified 三级能力）、ACCEPTANCE G3。

**问题**：OpenBB 实际可用性强依赖网络出口（yfinance 等供应商在部分部署环境不可达）。三级能力模型能表达该状态，但若 G0 探测清单不把"出口可达性"列为 verified_capability 的必检项，环境不可达会被误读为产品缺陷，或反过来让 BLOCKED 判定含糊。

**修正建议**：T0 第 4 步探测清单明确加入出口可达性检测与记录格式；G3 的 BLOCKED 判据写明"环境不可达"与"能力不支持"是两种不同状态。

## 5. C 类建议（登记即可）

1. **迭代重号历史**：本目录之前曾短暂存在"迭代197-商业化路线与首发冲刺"（文档已被移除、残留目录已清理）。建议在 `docs/iterations/README.md` 备注一行编号沿革，防止外部引用或记忆混淆；
2. **AC-46 基准库生成规则**：1,000 万行基准库的合成 fixture 生成种子与规则应在 G0 冻结，保证可重放、跨机器可比；
3. **T5 golden contract 体积预算**：七类 golden 响应文件可能很大，建议登记 fixture 存储与大小预算，避免测试仓库膨胀；
4. **README 导航补 REVIEW 行**（本评审已加入）。

## 6. 抽查验证记录（2026-09-05）

| 检查项 | 方式 | 结果 |
| --- | --- | --- |
| ACCEPTANCE 命令模板引用的 7 个存量测试文件 | `ls src/backend/tests/*.py` 逐一核对 | **全部存在**，无幻影路径 |
| `app/api/data/trust.py`、`assetDataFamilySpecs` | 文件存在性 + grep | 存在；`assetDataFamilySpecs` 定义于 `useDataPage.ts` |
| RESEARCH E13：`data_governance.py` 无 `DgDataset` | grep class Dg* | 属实：有 DgProvider/DgEndpoint/DgIngestJob，无 DgDataset（189 确未合入） |
| RESEARCH 证据基线：196 worktree `dataset_registry.py` | 文件存在性 | 存在于 `.worktrees/codex/iteration-196-ai-research-trust/` |
| RESEARCH：OpenBB 本地仓库基线 | `git rev-parse HEAD` | `3e071fcc...` 与文档声明一致 |
| RESEARCH：OpenBB 核心为 AGPL | 本地 LICENSE 文本 grep | 属实：GNU AFFERO GENERAL PUBLIC LICENSE |
| RESEARCH E02：`market_instrument.py:265` lookup | sed 定位 | 属实 |
| 巨型文件规模（B2 依据） | `wc -l` + `large_file_baseline.json` | useStrategyPage.ts 6,795（ratchet only goes down）、useDataPage.ts 2,024、DataPage.vue 728 |
| 存量安全债（A3 依据） | grep `get_current_user` 计数、audit.py:99 | brokers.py 0 处；`is_admin` 恒 False 路径仍在 |
| 既存许可证冲突（A2 依据） | LICENSE 头部 + NOTICE 存在性 | LICENSE 仍为 MIT，无 NOTICE 文件 |

方案文档的行号级论断抽查全部命中——本评审未发现事实性错误；问题全部集中在容量、依赖登记与一处设计延续性规则。

## 7. 处置顺序建议

| 顺序 | 事项 | 产出 | 阻断 |
| --- | --- | --- | --- |
| 1 | A1 容量与波次合同 | IMPLEMENTATION_PLAN 增补（重标人日 + W1—W4 + 暂停判据） | 阻断 G0 签署 |
| 2 | A2 许可义务矩阵归属 | G0 具名交付物 + 既存冲突登记 | 阻断 OpenBB 镜像分发与 G3 |
| 3 | A3 存量安全债登记与前置 | T0 基线清单 + G3 前置依赖 | 阻断 G3 联合门 |
| 4 | B1 series 延续规则 | DESIGN D2.2 增补 + 新增 AC | 阻断 T1 schema 冻结 |
| 5 | B2—B5 文档修订 | 任务包/验收增补 | 不阻断，建议随批提交 |
| 6 | C1—C4 登记 | 文档小节 | 不阻断 |
| 7 | 逐条处置回填（采纳/部分采纳/不采纳 + 理由） | 本文件附记或 REVIEW_DISPOSITION 文件 | 治理留痕 |

处置遵循迭代治理棘轮规则；A 类未处置前不应启动 T0 之后的实施。
