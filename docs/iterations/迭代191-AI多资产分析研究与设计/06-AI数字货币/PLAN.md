# 191F AI 数字货币实施计划

> 阻断前置条件：地区与运营主体法律意见、数据许可和隔离研究环境已批准。未满足时只实施技术夹具、纯函数与内部 fail-closed 研究，不启用 provider capability、接入真实来源、创建真实影子调度、宣称 T1 可验收或开放公众方向性建议。

## 1. 文件所有权

```text
src/backend/app/services/asset_research/plugins/crypto/
├── __init__.py
├── identity.py
├── products.py
├── calendar.py
├── venues.py
├── composite.py
├── derivatives.py
├── risk_scenarios.py
├── onchain.py
├── tokenomics.py
├── quality.py
├── policy.py
├── compliance.py
├── publishing.py
├── scheduling.py
├── promotion.py
├── report.py
└── outcomes.py
src/backend/tests/asset_research/crypto/
├── test_identity.py
├── test_products.py
├── test_time.py
├── test_market_quality.py
├── test_derivatives.py
├── test_risk_scenarios.py
├── test_onchain.py
├── test_policy.py
├── test_compliance.py
├── test_publishing.py
├── test_scheduling.py
├── test_promotion.py
├── test_outcomes.py
└── test_api.py
src/frontend/src/components/asset-analysis/panels/CryptoPanel.vue
src/frontend/src/__tests__/asset-analysis/CryptoPanel.test.ts
```

## 1.1 任务依赖、并行条件与公共契约冻结点

本节只描述可验证产物之间的实施门槛，不要求在数据库、API 或任务模型中增加任务依赖
字段。数字货币资产线只等待所列公共契约和法律/许可 Gate；未通过 Gate 时，技术夹具与
隔离研究实现仍可并行，但任何公共发布路径保持关闭。

公共冻结点：

- `C1 身份与插件`：`AssetResearchPlugin` 方法签名、公共资产类型、链上资产/venue
  product 身份、`canonical_id` 和 `identity_version`；
- `C2 证据与时点`：`RawObservation/RawAssetSnapshot`、来源注册、区块 finalized
  语义、内容哈希和四类时点语义；
- `C3 质量与决策`：`GateResult`、公共枚举、`ReasonCode`、`ResearchDecision`、
  地区门控、候选/发布隔离和 `access_principal`；
- `C4 预测与结果`：`PredictionHead`、`HorizonSpec`、结果唯一键、`OutcomeStatus`、
  `MaturityReason`、标准化风险情景和 `head_spec_hash`；
- `C5 调度与幂等`：schedule/run/prediction 生命周期、UTC cutoff、租约、
  `run_key/decision_input_hash/prediction_key`；
- `C6 发布与晋级`：模型状态机、`PromotionScope`、报告/导出/知识库发布边界和审计。

| 任务 | 最小前置产物 | 可并行条件 | 开始前必须冻结 |
| --- | --- | --- | --- |
| 1 身份和合规 | P0 身份插件骨架、法律/许可 Gate 接口 | 身份夹具与 fail-closed 合规测试可并行；未批准时不启用公共路由 | `C1`、`C3` |
| 2 24×7 数据 | 任务 1 的资产/product 身份、合法来源注册 | venue 行情、维护状态、复合参考和 CME 日历可并行；均写同一 raw envelope | `C1`、`C2` |
| 3 衍生/链上/tokenomics | 任务 1 的 product 路由、任务 2 的时点与报价 Schema | 三类适配器可并行；衍生结论等待完整风险情景契约 | `C2`、`C4` 的风险情景语义 |
| 4 质量和策略 | 任务 2/3 的可空 snapshot、公共地区能力 | 现货/衍生策略与地区真值表可并行，发布前统一 fail-closed 验证 | `C3`、`C4` |
| 5 候选和发布 | 任务 4 的 GateResult 与结构化策略输出 | API、报告和知识库过滤器可并行，共用 published decision 夹具 | `C3`、`C6` |
| 6 报告和页面 | 任务 5 的 published decision 与报告 envelope | 前后端在 DTO、证据 ID 和标准情景声明冻结后并行 | `C3`、`C6` |
| 7 多 head 结果 | 任务 2 的 point-in-time 行情、任务 3 的风险情景、任务 4 的成本口径 | 现货/衍生各 outcome 评估器可并行，共用 head spec 校验 | `C4` |
| 8 调度和补跑 | 任务 1 的产品身份、任务 2 的 UTC/finalized 规则、任务 5 的安全发布 | scheduler 可与任务 6/7 并行；启用前统一验证并发幂等和历史可见性 | `C5` |
| 9 晋级作用域 | 法律/许可 Gate 通过、任务 7 的成熟结果、任务 8 的连续 SHADOW 证据 | pooled/specific scope 证据可并行，状态切换等待全部门槛 | `C4`、`C6` |

## 2. 任务

### 任务 1：身份和合规优先

- [ ] 先写同 ticker 跨链、裸资产/产品和大陆绕过失败测试；
- [ ] 实现 CAIP 风格资产 ID 和 venue product ID；
- [ ] 建立服务端地区、产品和数据许可策略；
- [ ] 确保适配器接口不接受私钥和私有交易权限。

### 任务 2：24×7 市场数据

- [ ] 接入合法公共 REST/WebSocket、状态、维护和双边报价；
- [ ] 实现 UTC bar、完整性 gap、序列和跨 venue 校验；
- [ ] 实现复合参考、稳定币风险换算和目标名义深度；
- [ ] 明确 CME 等非 24×7 产品走专属日历。

### 任务 3：衍生、链上和 tokenomics

- [ ] 现货/永续/交割、线性/反向分路由；
- [ ] 收集 funding/index/mark/OI/清算并保存定义；
- [ ] 从 cutoff 时可用场所规则构造版本化 `STANDARDIZED_RESEARCH` 风险情景，
  冻结 quantity/notional/leverage/collateral/margin tier/清算公式/mark path；
- [ ] 风险情景及规则哈希进入 `decision_input_hash`，严禁读取账户或把情景称为
  实际仓位、清算价或杠杆建议；
- [ ] 对 BTC/ETH 等支持资产接入节点或批准链上源；
- [ ] 实现 provider 不支持、实体聚类版本和 token migration。

### 任务 4：质量和策略

- [ ] 实现脱锚、深度、停牌、异常价、历史不足和地区拒绝；
- [ ] 现货与衍生品策略完全分离；
- [ ] 只使用公共 `normalized_direction=LONG/SHORT/NEUTRAL/INDETERMINATE`、
  `position_context`、`trade_intent` 和 `recommendation` 枚举；
- [ ] 现货空仓 `SHORT` 不开空；衍生品由
  `short_open_research_allowed` 决定 `trade_intent=OPEN/NONE`，中国大陆固定
  `NONE`；
- [ ] 标准化情景缺任一保证金/清算字段时拒绝可行动衍生品结论，LLM 不能给杠杆、
  猜测缺失参数或绕过限制；
- [ ] 地区限制固定 `market_view=INDETERMINATE`、
  `normalized_direction=INDETERMINATE`、`recommendation=AVOID`、
  `trade_intent=NONE`、`actionability=REGION_RESTRICTED` 和
  `CRYPTO.REGION_RESTRICTED`。

### 任务 5：候选和安全发布

- [ ] 分离不可变 `candidate_decision_json` 与 `published_decision_json`；
- [ ] `SHADOW/SUSPENDED/未登记` 时普通用户固定
  `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
  `trade_intent=NONE`、`actionability=RESEARCH_ONLY` 和
  `recommendation=HOLD/AVOID`；
- [ ] 候选方向、概率和预期收益仅对隔离评估器和授权管理员开放；
- [ ] 未晋级使用 `COMMON.MODEL_NOT_PROMOTED`，数据过期和许可阻断分别使用
  `COMMON.DATA_STALE`、`COMMON.SOURCE_LICENSE_BLOCKED`；
- [ ] API、页面、报告、导出和知识库只读取发布决定；
- [ ] 只使用公共 `CRYPTO.*` `ReasonCode`，禁止自由文本原因码。

### 任务 6：报告和页面

- [ ] 实现十二章节、场所/产品、衍生、链上、tokenomics 和安全；
- [ ] 展示 UTC cutoff、维护、区块高度和 finalized；
- [ ] 清算卡展示标准情景全部冻结参数和版本，并固定标注“非实际仓位或杠杆建议”；
- [ ] 大陆模式无方向概率、交易链接、API key、托管和订单；
- [ ] 导出继承同一限制。

### 任务 7：多 head 结果

- [ ] 24h/7d/30d 现货和永续分开评分；
- [ ] 覆盖 fee/slippage/funding、稳定币换算、标准化清算压力情景和到期；
- [ ] 缺 funding 或退出报价不伪造完整结果；
- [ ] 现货分别落 `crypto.spot_pnl`、`crypto.benchmark_excess`、
  `crypto.risk_path`；
- [ ] 衍生品分别落 `crypto.derivative_pnl`、`crypto.liquidation_risk`、
  `crypto.risk_path`；
- [ ] 清算 outcome 只报告冻结情景的 `SURVIVED/LIQUIDATED`；场所规则或 mark path
  不完整时为 `UNSCORABLE + CRYPTO.LIQUIDATION_SCENARIO_INCOMPLETE`；
- [ ] 增加唯一键
  `(prediction_id,horizon_code,outcome_kind,evaluator_version)`；
- [ ] 只使用公共
  `OutcomeStatus=PENDING|PARTIAL|SCORED|UNSCORABLE`，到期单列
  `MaturityReason.HORIZON_REACHED/EXPIRY/ROLL/DELISTING`，不得使用
  `MATURED` 状态。

### 任务 8：每日影子调度和补跑

- [ ] 将审批静态清单配置时展开为单产品 schedule，禁止运行时扫描市场；
- [ ] 每个 UTC 自然日 00:00 冻结 cutoff、00:10 启动 schedule；
- [ ] 冻结 `schedule_version/cutoff_policy_version`，建立唯一 `run_key` 和
  `decision_input_hash/prediction_key`；
- [ ] 00:25、01:10 重试失败项，03:00 对账，重启后在下一 cutoff 前 catch-up；
- [ ] 所有补跑复用原 cutoff，拒绝后来才 available/finalized 的数据；
- [ ] 并发和重复触发只生成一条预测，维护和最终失败保留 `CRYPTO.*` 证据；
- [ ] 北京 19:10 盘中快照与每日 cohort、晋级分母分离。

### 任务 9：晋级作用域

- [ ] 为现货和衍生品分别注册唯一主 `PredictionHead` 的 target/scoreability 版本、
  标签、P&L/成本/no-trade band、模型与校准 artifact、training cutoff、基线版本和
  `head_spec_hash`；
- [ ] venue/product/quote、风险情景或 `head_spec_hash` 不同的 cohort 拒绝混算；
- [ ] 将公共 `PromotionScope` 规范化后计算 `promotion_scope_key`，固定资产、
  venue/product/quote 样本池、`signal_head` 和期限；版本列独立参与注册表唯一约束；
- [ ] `INSTRUMENT_SPECIFIC` 以单一产品至少 200 条成熟行动信号验收；
- [ ] `POOLED` 仅合并同 venue/product family、P&L/报价/结算、成本和策略，
  至少 5 个产品、每个 20 条、总计 200 条且单一产品不超过 40%；
- [ ] 禁止 spot/perpetual/delivery、linear/inverse、法币/稳定币报价跨池；
- [ ] 合法地区按精确 scope 连续 90 个 UTC 自然日运行 `SHADOW`，T2 通过后才
  `PROMOTED`。

## 3. 测试命令

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/crypto
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check \
  app/services/asset_research/plugins/crypto \
  tests/asset_research/crypto

cd ../../src/frontend
npm run typecheck
npm run test -- --run src/__tests__/asset-analysis/CryptoPanel.test.ts
```

## 4. 退出条件

- [ ] CRYPTO-FR-001 至 014 技术实现；
- [ ] [验收文档](./ACCEPTANCE.md)T1 全部通过；
- [ ] 法律、地区和数据许可 Gate 有证据；
- [ ] 大陆功能无法通过 API/前端绕过；
- [ ] 全球允许地区仍保持 `SHADOW` 至少 90 日，普通用户不可见候选方向；
- [ ] 日批次幂等、补跑、多 head 评分和两种晋级 scope 均有自动化证据。
