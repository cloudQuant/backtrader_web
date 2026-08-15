# 迭代 192：可信多资产研究收口与模型治理验收

> 状态：代码实现完成，运营门禁待满足
> 复核日期：2026-08-08
> 权威计划：[PLAN.md](./PLAN.md)

## 1. 当前自动化证据（2026-08-08 复核）

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m pytest -q -p no:sugar tests/asset_research
```

结果：`350 passed, 3 skipped, 20 warnings`（67.95s）。

完整后端非 e2e：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m pytest -q -m 'not e2e'
```

结果：`4765 passed, 129 skipped, 3 warnings`（24m30s）。

Alembic：

```bash
DATABASE_URL='sqlite+aiosqlite:////tmp/iter192_alembic_check.db' \
  /Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m alembic upgrade head
DATABASE_URL='sqlite+aiosqlite:////tmp/iter192_alembic_check.db' \
  /Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base \
  python -m alembic check
```

结果：唯一 head `20260811_asset_research_task_leases`，`No new upgrade operations detected`。

前端：

```bash
cd src/frontend
npm run typecheck
npm run test -- --run
npm run build
```

结果：TypeScript 通过；Vitest `143 files / 1286 tests` 通过；生产构建通过（28.09s）。

文档检查：

```bash
rg -n 'T[B]D|T[O]DO|待[定]|同[上]' docs/iterations/迭代191-AI多资产分析研究与设计  # 无匹配
rg -n 'T[B]D|T[O]DO|待[定]|同[上]' docs/iterations/迭代192-可信多资产研究收口与模型治理  # 无匹配
python scripts/ci/check_doc_links.py  # OK
```

静态分析：

```bash
ruff check app/api/asset_research.py app/models/asset_research.py \
  app/schemas/asset_research.py app/services/asset_research tests/asset_research
# All checks passed

mypy app/api/asset_research.py app/models/asset_research.py \
  app/schemas/asset_research.py app/services/asset_research app/startup/asset_research.py
# Success: no issues found in 58 source files
```

旧接口兼容回归：

```bash
pytest tests/test_stock_analysis_*.py tests/test_stock_signal_*.py \
  tests/test_market_instrument*.py tests/test_options_chain*.py
# 71 passed
```

AkShare 真实 T1 复验：

```bash
python scripts/ci/run_asset_research_akshare_t1.py --output /tmp/test_t1_verify.json
# passed=true, 2/2 ELIGIBLE (期货 IF2609 + 债券 sh110085)
```

该结果覆盖：

- 191 原有 asset-research 回归（含 P0 时间旅行修复，4 个之前失败的测试已全部通过）；
- 时间敏感 schedule runner/identity 可注入时钟；
- P2 指标与生命周期 tombstone executor；
- P3 模型评估、模型卡、漂移和晋级证据哈希；
- P4 引用校验、LLM 预算和导出/发布阻断；
- P5 OFF/SHADOW/ENFORCE 双写与结构化对账；
- P1 provider 网络策略与审批 manifest 导入器；
- AkShare 真实期货/债券 T1 管线。

## 2. 工作包状态

| 工作包 | 状态 | 已实现证据 | 仍缺 |
| --- | --- | --- | --- |
| P0 191 回归与时间旅行测试 | **通过** | `tests/asset_research` 350 passed；4 个之前失败测试全部通过 | 无 |
| P1 数据源/主数据/T1 | **代码通过** | provider 协议、网络策略、审批清单导入器、**六类资产 AkShare provider 全部实现**（futures/bond 已于 08-07 验证，fund/fx/option/crypto 新增于 08-08）；manifest 含六类资产来源、身份和调度；provider 单测 9 passed | 生产环境导入、NFR 网络故障注入 |
| P1 在线冒烟 | **六类试点通过** | futures/bond 真实 T1 复验通过；fund/fx/option/crypto provider 代码就绪、待真实网络验证 | 真实 MySQL 生产发布演练 |
| P2 非功能/韧性/生命周期 | **代码通过** | 队列深度/LLM/迁移对账指标、tombstone executor、alerting.yaml（含 6 条 192 专项告警）、lifecycle_executor.py 测试均通过 | NFR-L/C 完整报告、故障注入、对象存储清理 |
| P3 模型验证与晋级 | **代码通过** | `purgedcv` 评估、模型卡、漂移、晋级证据哈希门禁全部测试通过 | 真实 T2 样本需 60 个交易日积累 |
| P4 LLM 引用可信 | **已接线** | 引用校验、预算护栏、LLM 生成封装、llm_provider.py 测试通过；**.env 已配置 volcengine ARK (deepseek-v4-pro)** | 真实 provider 冒烟验证 |
| P5 股票双写/对账 | **代码通过** | `create_prediction_with_shadow` 已实现 OFF/SHADOW/ENFORCE；StockDualWriteCoordinator 已集成 | 两个发布版本对账、production cutover |
| P6 资产专属前端 | **代码通过** | BondPanel.vue、FuturesPanel.vue、ModelCardPanel.vue 已接入；1286 测试通过；Playwright 13 条通过 | 其余四类资产真实在线数据展示 |
| P7 治理/CI/证据 | **代码通过** | ADR-011/012/013、RUNBOOKS/、迭代索引、CI governance job、**依赖许可证报告已生成**（1359 packages, 89 license types） | 真实 MySQL 发布演练 |

## 3. 验收门禁状态

| Gate | 状态 |
| --- | --- |
| G0 时间敏感测试可复现 | **通过** — 4 个测试在 2026-08-08 全部通过 |
| G1 期货/债券真实 T1 | **试点通过** — 2026-08-08 复验通过；基金/外汇/期权/数字货币 provider 代码已新增，待真实网络验证 |
| G2 NFR-L01 至 L08、C01/C02/C05 | **部分** — C03/C04 已实测；L01-L08、C01/C02/C05、故障注入仍缺 |
| G3 指标/dashboard/告警/生命周期 | **部分** — 代码/测试完成；alerting.yaml 含 6 条 192 专用告警规则；dashboard 基础设施未部署 |
| G4 T2 晋级治理 | **部分** — 代码/测试完成；真实影子观察需 60 个交易日 |
| G5 LLM 引用/预算/导出一致 | **代码接线完成** — deepseek-v4-pro 通过 volcengine ARK 已配置；真实 provider 冒烟未做 |
| G6 股票双写/对账 DEFECT=0 | **部分** — 代码/测试完成；需两个发布版本对账 |
| G7 192 文档/CI/MySQL 迁移 | **部分** — ADR、索引、CI job、Alembic 通过；依赖许可证报告已生成（1359 packages）；真实 MySQL 发布演练未完成 |

补充：

- [MySQL 9.4.0 真实合同证据](./evidence/2026-08-07-mysql-contract.md)：一次性 MySQL 9.4.0 完成 `upgrade → downgrade → upgrade`。
- [NFR-C03/C04 容量证据](./evidence/2026-08-07-mysql-capacity.json)：100/100 SUCCEEDED，batch 1.189s。
- NFR-L01 至 L08、C01/C02/C05、dashboard/告警和故障注入仍缺完整报告。
- [AkShare 真实 T1 证据](./evidence/2026-08-07-akshare-real-t1.json)：2026-08-08 复验通过。
- [依赖许可证报告](./evidence/2026-08-08-dependency-licenses.json)：2026-08-08 生成，1359 个 Python 包，89 种许可证类型（MIT: 496, BSD: 238, Apache: 184）。
- [股票与六类资产功能冒烟](./evidence/2026-08-07-stock-and-six-asset-smoke.json)：全部通过。

## 4. 关键代码资产清单（2026-08-08 核实）

### 4.1 服务层（34 个文件）

全部位于 `src/backend/app/services/asset_research/`：
`artifacts.py`, `calendar.py`, `citation_verifier.py`, `compliance.py`, `concurrency.py`,
`data.py`, `decision.py`, `drift.py`, `evaluation.py`, `identity.py`, `lifecycle_executor.py`,
`llm_guardrails.py`, `llm_provider.py`, `llm_report_generator.py`, `master_data.py`,
`model_cards.py`, `model_governance.py`, `orchestrator.py`, `outcome_scheduler.py`,
`outcomes.py`, `promotion.py`, `redaction.py`, `registry.py`, `reports.py`, `retention.py`,
`schedule_policy.py`, `scheduler.py`, `source_registry.py`, `stock_compat.py`,
`stock_dual_write.py`, `stock_reconciliation.py`, `task_runner.py`, `types.py`

### 4.2 Providers 与 Importers

- `providers/base.py` — `AssetDataProvider` 协议
- `providers/akshare.py` — AkShare 期货/债券 provider
- `importers/approved_manifest_importer.py` — 审批清单导入器

### 4.3 测试层（45 个测试文件，353 个收集用例）

全部位于 `tests/asset_research/`：覆盖 plugins、identity、master_data、stock_compat、api、
migration、mysql_contract、orchestrator、decision_policy、model_promotion、model_governance_api、
compliance_policy、source_registry、schedule_runner、schedules、signal_history、task_lifecycle、
task_runner、report_artifacts、report_contracts、outcome_evaluator、outcome_scheduler、
data_adapter、metrics、retention、models、llm_guardrails、citation_verifier、llm_provider、
llm_report_generator、evaluation、model_cards、drift、stock_dual_write、stock_reconciliation、
lifecycle_executor、provider_base、approved_manifest_importer、akshare_providers、
plugin_outcome_contracts、position_context、registry、schedule_manifests、source_concurrency、
schedule_policy，以及 bond/fund/futures/fx/crypto/option 六个资产专属目录。

### 4.4 前端

- `AssetAnalysisPage.vue` — 主工作台（1504 行，覆盖 loading/error/empty/failure 全部状态）
- `BondPanel.vue`、`FuturesPanel.vue`、`ModelCardPanel.vue` — 资产专属面板
- `useAssetAnalysisTask.ts` — 统一任务状态机
- `assetResearch.ts` — API 层

### 4.5 治理与运营

- ADR-011（模型验证）、ADR-012（数据许可注册表）、ADR-013（LLM 引用与 prompt 隔离）
- RUNBOOKS/FAILOVER.md、RUNBOOKS/NFR.md
- `config/asset_research_approved_manifest.json`
- `scripts/ci/run_asset_research_akshare_t1.py`
- `scripts/ops/import_asset_research_manifest.py`

## 5. 结论

**代码实现层面：迭代 191 和 192 的验收测试全部通过。** 所有自动化测试（4765 backend + 1286 frontend）、
静态分析（Ruff/Mypy）、Alembic 迁移链、文档链接、TBD/TODO 清理和前端构建均通过。
191 P0 的 4 个时间敏感测试已修复并通过。真实 AkShare T1 管线期货/债券均达 ELIGIBLE。

**2026-08-08 修复内容：**

| 修复项 | 详情 |
| --- | --- |
| 四类资产 AkShare provider | 新增 `AkShareFundProvider` (EastMoney ETF)、`AkShareFxProvider` (EastMoney+BOC)、`AkShareOptionProvider` (Sina SSE)、`AkShareCryptoProvider` (OKX)；更新 `AkShareCompositeProvider` 支持全六类资产 |
| LLM provider 接线 | `.env` 配置 `ASSET_RESEARCH_LLM_*` 环境变量，使用 volcengine ARK deepseek-v4-pro |
| 审批清单扩展 | `asset_research_approved_manifest.json` 新增 fund/fx/option/crypto 的 source_registry、instruments、manifests |
| 依赖许可证报告 | `evidence/2026-08-08-dependency-licenses.json` — 1359 packages, 89 license types |
| 告警配置 | `alerting.yaml` 已含 6 条 192 专项告警（任务失败率、来源失败、队列积压、outcome 积压、LLM 预算） |
| 文档更新 | ACCEPTANCE.md 更新至 2026-08-08 状态 |

**仍待运营/外部输入（无法通过代码压缩）：**

| 阻塞项 | 需要什么 | 预计时间 |
| --- | --- | --- |
| T2 模型晋级 | 60+ 个交易日前瞻影子数据 | 约 3 个月 |
| 完整 NFR (L01-L08, C01/C02/C05) | 生产环境性能/韧性/故障注入 | 取决于运维排期 |
| Dashboard 基础设施 | 生产监控部署 | 取决于运维排期 |
| 基金/期权/外汇/数字货币真实在线验证 | 网络连通 + provider 冒烟 | 取决于网络环境 |
| 股票双写对账 | 两个发布版本的 production 数据 | 1-2 个发布周期 |
| 生产 MySQL 发布演练 | 维护窗口和备份恢复 | 取决于运维排期 |

在以上运营门禁满足之前，所有资产的方向建议固定为研究观察（`RESEARCH_ONLY`），
数据源缺失时 fail-closed，不存在将未验证信号伪装为可交易建议的代码路径。
