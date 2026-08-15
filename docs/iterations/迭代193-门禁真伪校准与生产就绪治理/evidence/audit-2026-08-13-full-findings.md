# 迭代 193 全维度审计证据清单

> 审计日期:2026-08-13。方法:8 维度并行只读审计 + 关键结论独立复核(复核修正见 PLAN.md §5)。
> 严重度:P0 阻断 / P1 高 / P2 中 / P3 低;工作量:S <1 天 / M 1-3 天 / L >3 天。
> 说明:此清单为 PLAN.md 的原始证据底稿,保留全部 file:line 定位;已被复核修正的结论在此以**修正后**表述呈现。

---

## 一、后端架构与代码质量

| ID | 严重度 | 工作量 | 发现 | 证据 |
| --- | --- | --- | --- | --- |
| B1 | P0→Task A | M | 大文件棘轮红灯:192 新增 5 个 god file + 3 处基线回归 | 实跑 `scripts/ci/large_file_ratchet.py` exit 1 |
| B2 | P1 | L | `_run_pipeline` 单方法 1363 行;另有 8 个 110-190 行方法 | `services/ai_strategy_research_service.py:486` |
| B3 | P1 | L | `contract_spec_for` 492 行;`get_portfolio_equity` 239 行 | `services/position_valuation.py`、`api/portfolio/api.py:2912` |
| B4 | P1 | S | `evaluate_due_outcomes` N+1:循环内逐条 `db.get`,单批次最多 ~4000 次 DB 往返 | `services/asset_research/orchestrator.py:1613-1638` |
| B5 | P1 | S | async 端点内同步文件 I/O(`parse_value_log` 等 5 处调用点阻塞事件循环) | `api/portfolio/api.py:2506,2555,2681,2872,2961`;实现 `services/log_parser_service.py:378` |
| B6 | P2 | S | 7 处 `sys.modules[__name__]` 兼容 shim 超期未清理(174 承诺一个迭代周期) | `services/backtest_service.py:5`、`api/live_trading_api.py:5`、`services/manual_gateway_service.py:5`、`api/deps.py:9`、`api/portfolio_api.py:5`、`services/strategy_service.py:5`、`services/live_trading_manager.py:5` |
| B7 | P2 | M | 77 个 relationship 全部默认 `lazy="select"`,全库仅 9 处 eager load → 隐式 N+1 / async 下 MissingGreenlet 风险 | `models/*.py`(0 处指定 lazy=) |
| B8 | P2 | S | 异常→HTTP 状态码按 error_code 字符串硬编码,新异常类未登记则静默 500 | `middleware/exception_handling.py:97-114` |
| B9 | P2 | M | `market_instrument.py` 9 个 `_lookup_*` 方法 53-65% 复制粘贴重复 | difflib 实测相似度 |
| B10 | P2 | M | 分页风格不统一:`limit`/`page_size`/`limit+offset`/`tail` 四种并存,无统一 envelope | `api/workspace_api.py:77`、`api/paper_trading.py:75`、`api/ai_observability.py:67`、`api/simulation.py:330` |
| B11 | P2 | S | 惰性单例 check-then-act 无同步保护(并发首请求可双建引擎/缓存双算) | `db/database.py:22-52`、`config.py:850-862`、`main_routes.py:26-34` |
| B12 | P2 | S | Alembic revision 三种命名风格混用 | `alembic/versions/` 32 个迁移 |
| B13 | P2 | S | 适配器默认值硬编码于代码(12-Factor 违规) | `services/ai_router/ollama_adapter.py:22`、`health.py:44`、`services/workspace/config.py:35-52` |

本维度已达标:统一错误 envelope、session 生命周期封装、Alembic 三层防护(实跑漂移检查 "OK: schema aligned")、0 裸 except、services 层零依赖 app.api。

## 二、测试体系质量

| ID | 严重度 | 工作量 | 发现 | 证据 |
| --- | --- | --- | --- | --- |
| T1 | P1 | S | 时间敏感测试定时炸弹:`fire_at=datetime(2026,8,3)` 已过期;`persist_identity` 不传 valid_from 时用真实 now(与 192 的 4 个失败同根因);全仓无 freezegun,~50 处 `datetime.now()` | `tests/asset_research/test_schedule_runner.py:419-542`、`test_report_artifacts.py:224-227`、`test_schedule_manifests.py:94` |
| T2 | P2 | S | 真实时钟 2 秒容差断言,负载 CI 可 flaky 且断言价值极低 | `tests/test_datetime_utils.py:24` |
| T3 | P2 | S | 全局单例清理不完整:`DataTopicHub`/`WSGateway` 等无统一 conftest 重置,测试顺序依赖隐患 | `tests/conftest.py:94-118`;对照 `test_main_lifespan_and_websocket.py:149-152` 自行 patch |
| T4 | P2 | M-L | mock 滥用:2598 行测试 191 处 patch、3776 行测试 47 处 assert_called;部分测试只验证 mock 自身;全库 265 处 assert_called | `tests/test_live_trading_manager.py:80-89`、`tests/test_extracted_modules.py` |
| T5 | P1 | M | `.coveragerc` 把 5 个实盘关键模块排除出覆盖率分母(其中 3 个已有测试文件)——门禁审计套利 | `src/backend/.coveragerc:3-20` |
| T6 | P1 | M | 4 个核心服务模块零直接测试(~1700 行):`quant_tools_runtime.py` 653 行、`data_connectors/executor.py+registry.py` 615 行、`semantic_retrieval_service.py` 296 行;`chunk_service.py` 144 行全库零引用疑似死代码 | grep 零引用 |
| T7 | P2 | S | 覆盖率门禁数字三处不一致:后端 70%(文档表述 75)、增量 60%、前端 functions 52% | `ci.yml:575,580`、`src/frontend/vitest.config.ts` |
| T8 | P2 | S | governance job 硬编码测试文件清单(13+2 个),与 tests/asset_research/ 43 个文件不同步 | `ci.yml:226-248` |
| T9 | P1 | L | 实盘失败路径覆盖薄弱:manual_gateway/live_execution 无专属测试;下单失败/拒单/部分成交/断连重连无系统化测试 | `tests/test_smoke_ctp_gateway_script.py`(仅 smoke 级) |
| T10 | P1 | M | 资金计算全 happy path:`test_portfolio_ledger.py` 0 处 pytest.raises;全库仅 27% 测试文件含 raises | `tests/test_portfolio_ledger.py:14-60` |
| T11 | P2 | M | akshare scheduler 无异常路径测试(网络异常/超时/退避是最高频真实故障) | `tests/test_akshare_scheduler.py`;对照 `test_akshare_network_proxy.py`(做得好) |
| T12 | P2 | S | `--maxfail=5` 使 CI 覆盖率门禁基于不完整运行,可能虚报 | `src/backend/pytest.ini:12` + `ci.yml:575` |
| T13 | P2 | M | parametrize 仅 35 处,大量"循环+多断言"测试(1121 行测试文件单函数数十 assert) | `tests/test_run_dual_exchange_simulation.py:25-161` |
| T14 | P1 | M | 20 skip + 16 skipif 无 ticket 引用;含 4 个"前存故障"僵尸 skip;性能套件 100% skip 整体失效;marker 体系(slow/integration/e2e/security)实际 0 使用 | `tests/test_extracted_modules.py:2237,2738`、`test_performance_baseline.py:58-198` |
| T15 | P2 | M | 真实 sleep + 时序断言:`time.sleep(0.5)` + gather 顺序断言;flaky marker 仅 2 处使用 | `tests/test_live_trading_api.py:259-292`、`test_refresh_token.py:105` |
| T16 | P1 | S | 本地 `run-e2e.sh` 不设 DATABASE_URL,会污染开发者真实数据库;CI 设了 sqlite 隔离,行为不一致 | `scripts/dev/run-e2e.sh:80-85`;对照 `e2e.yml:100-108` |
| T17 | P2 | M | e2e workers=1 串行;workspace 核心流程(RAG/AI 对话/优化器/监控)无 e2e 覆盖 | `src/frontend/playwright.config.ts:41` |

本维度已达标:conftest 每测试 create_all/drop_all + StaticPool + 文件路径重定向;asset_research 43 个测试文件几乎零 mock 且注入式断言具体;前端 139 测试文件、92% 具体断言;Playwright 4 配置 + storageState + only-on-failure trace。

## 三、安全纵深

| ID | 严重度 | 工作量 | 发现 | 证据 |
| --- | --- | --- | --- | --- |
| S1 | P1 | M | 跨用户操作全局网关(BOLA):网关进程级全局字典,端点仅 `get_current_user`,任意登录用户可断开/查询他人实盘网关 | `api/live_trading/api.py:141-216`;`services/live_trading/manager.py` 无 user_id 参数 |
| S2 | P1 | S | 用户名 `admin` 抢占即获管理员权限:管理员判定基于 `username == ADMIN_USERNAME`,注册无保留名,默认管理员不预创建 | `services/auth_service.py:53-56,159-171`;`config.py:347,558` |
| S3 | P1 | S | 生产限流键失效:nginx 反代后 `get_remote_address` 恒为代理 IP → 全平台共享单桶可被 DoS;`REDIS_URL` 默认 None 时 in-memory 桶随 worker 分裂 | `rate_limit.py:47`;`docker/compose/prod.yml` 无 ports/proxy-headers;`config.py:358` |
| S4 | P1 | M | 资金/下单敏感操作无服务端权威审计:审计事件由客户端上报可伪造,下单/网关/实例服务中 audit 调用零命中 | `api/audit.py:40-65`;`services/direct_order_service.py`、`live_trading/manager.py` grep 零命中 |
| S5 | P2 | M | 禁用用户既有 token 仍有效:JWT 7 天、`get_current_user` 不查库;对照 `api/data/deps.py:20-58` 有 is_active 校验但仅数据/经纪商路由使用 | `api/_dependencies.py:41-74`;`prod.yml:76`(JWT_EXPIRE_MINUTES=10080) |
| S6 | P2 | S | 生产安全护栏 fail-open:DEBUG 未设置时 `_is_production` 返回 False,默认 JWT 密钥可被用于伪造 token | `config.py:44-52,674-712`(默认密钥 `config.py:366-368`) |
| S7 | P0→Task B | S | 供应链漂移:镜像按 `src/backend/requirements-prod.lock` 安装(310 行含 extras),CI 阻断审计 `config/requirements-prod.lock`(68 行),已漂移且无 diff 门禁 | `src/backend/Dockerfile:21-26`;`ci.yml:644-655`;asgiref 3.11.1 vs 3.12.1 |
| S8 | P2 | S | 权限依赖基础设施是坏的死代码:`has_permission` 迭代 `TokenPayload.roles`(不存在)→ 被引用即 500;`/audit/records` 依赖 `TokenPayload.is_admin` 恒 403 | `api/_dependencies.py:103-138`;`schemas/auth.py:113-119`;`api/audit.py:99` |
| S9 | P2 | S | 未认证写接口 `POST /api/v1/airflow/callback`:任意人可伪造任务执行记录污染数据治理 | `api/airflow_callback.py:19-45` |
| S10 | P2 | S | SPA 静态资源无安全响应头(后端中间件只覆盖 /api/v1);生产公开 /docs /redoc /openapi.json;/postman 无鉴权导出 | `docker/nginx.prod.conf:83-104`;`api/docs.py:182-200` |
| S11 | P2 | M | AI/公共端点无速率限制:`limiter.limit` 仅命中 `api/auth.py`;AI_BUDGET_MODE 默认 soft 不阻断 | grep 全仓;`config.py:441-442` |
| S12 | P2 | S | XFF 无代理校验直接信任,审计溯源 IP 可伪造;与限流键修复需配套否则引入新绕过 | `middleware/logging.py:55-65`;`api/audit.py:27-37` |
| S13 | P2 | S | JWT_ALGORITHM 无白名单 validator,误配 `none` 等弱算法即签名失效(疑似,需运维误配) | `config.py:370` |
| S14 | P2 | S | `scripts/ci/security_scan.sh` 与 CI 实际门禁双轨:脚本仍为旧版裸扫描,手工执行得弱结论 | `scripts/ci/security_scan.sh` |

本维度已达标:路由鉴权覆盖广(实例/账户/文档/策略均有归属校验)、网关凭据全量脱敏、SQL 全参数化 + 动态标识符白名单、SSRF DNS-rebinding 抗性、生产 CSP 无 unsafe-inline、沙箱化 AI 策略执行、gitleaks 全历史+基线指纹闭环、审计基础设施(事件校验/异步持久化/留存清理)完整。

## 四、性能与可扩展性

| ID | 严重度 | 工作量 | 发现 | 证据 |
| --- | --- | --- | --- | --- |
| P1 | P1 | S | `/data/kline` async 路由内直连 akshare(最长 10s 阻塞)+ 无缓存;同仓 `market_instrument.py:468` 已有正确 to_thread 模式 | `api/data/base.py:48,78` |
| P2 | P1 | S-M | MySQL 用 NullPool:每请求新建物理连接;惰性引擎在同 loop 创建后 QueuePool 不存在注释所担心的跨 loop 问题 | `db/database.py:31-35`、`db/akshare_data_database.py:54-55` |
| P3 | P1 | M | 回测/过拟合 WebSocket 每客户端每秒 1 次 DB 轮询;叠加 NullPool 放大连接 churn;已有 ws_manager 但无状态广播 | `api/backtest_enhanced.py:552-573`、`api/overfitting.py:152-171` |
| P4 | P1 | S | 扫描器同步重计算直接运行在 async 路由(数据获取+因子计算线性于 universe) | `api/scanners.py:212-216` → `services/scanner_service.py:44-105` |
| P5 | P2 | S | analytics 详情链路事件循环内同步解析日志文件(include_logs 默认 True);live_trading 同函数已正确 to_thread,两处不一致 | `api/analytics.py:117` → `services/log_parser_service.py:378`;对照 `api/live_trading/api.py:485,599-600` |
| P6 | P2 | S | **响应缓存键不含用户身份**:缓存 HIT 时所有权校验被跳过,任意用户可用他人 task_id 命中缓存取他人回测结果 | `api/backtest_enhanced.py:187`;`utils/response_cache.py:165-173`;对照 `backtest/service.py:580-600` 先鉴权后缓存 |
| P7 | P2 | S | workspace 单元重排序 N+1(每个单元一次 SELECT) | `services/workspace/units.py:540-545` |
| P8 | P2 | S | paper orders/trades 缺 `(account_id, created_at)` 复合索引,列表按 account_id 过滤 + created_at 排序将 filesort | `models/paper_trading.py:170-183,219+` |
| P9 | P2 | S | 扫描计划运行记录列表无分页(累积全量返回),同类端点均有分页 | `api/scanners.py:194-205` → `services/scanner_plan.py:161-175` |
| P10 | P2 | S-M | 行情/回测图表端点无数据量上限 + 指标计算 O(n·period) 在事件循环内 | `api/analytics.py:410-480`、`api/data/base.py:22-107` |
| P11 | P2 | M | echarts 全量引入(含 echarts-gl),可减 40-60% | `components/charts/EquityCurve.vue:27`、`useWorkspaceOptimizationTab.ts:4` |
| P12 | P3 | M | 告警规则逐规则逐 tick 查库,频率 = 规则数/间隔 | `services/monitoring_service.py:369-380` |
| P13 | P3 | S | 扫描器任务结果字典无淘汰,进程生命周期内无界增长 | `services/scanner_service.py:100` |

本维度已达标:quote/实盘/AI provider 全链路 to_thread 覆盖、双缓存后端 + LRU 有界、热点列表端点分页齐备、summary 摘要端点、日志轮转、鉴权零 DB 开销、ai_call_logs 等高频表索引覆盖 + 启动缺失索引自动补齐。

## 五、CI/CD 与工程基础设施

| ID | 严重度 | 工作量 | 发现 | 证据 |
| --- | --- | --- | --- | --- |
| C1 | ~~P0~~ 已复核 | S | ~~容器健康检查 404 → 生产栈无法启动~~ **修正**:根路径 `/health` 存在(`main_routes.py:99` 经 `main.py:129` 注册),探针路径有效。保留硬化项:就绪探测 `curl -s` 不带 `-f` | 复核修正 |
| C2 | P1 | S | Lighthouse CI 死门禁:配置路径错误(根级 `lighthouserc.js` 不存在,实际 `config/lighthouserc.js`)+ `\|\|` 吞退出码 → 恒绿,a11y≥90 阻断从未执行 | `ci.yml:966-968` |
| C3 | P1 | S | monorepo-check 空转:未装任何工具,check_all.sh 全部 "WARN: skipping" 后 exit 0,叠加 continue-on-error | `ci.yml:1243-1265`;`scripts/dev/check_all.sh:79-111` |
| C4 | P1 | M | `src/bt_api_py`(交易所适配层)CI 零覆盖:7 个 workflow 全部无引用,本地 check_all 却覆盖之 | grep 全仓 0 命中;`scripts/dev/check_all.sh:22` |
| C5 | P1 | M | 246.7MB 被跟踪数据文件,每次 CI checkout 全量下载 | `data/datas/bond_merged_all_data.csv` 69.9MB 等;`data/dev/backtrader.db.bak.*` |
| C6 | P1 | S | 多数 job 无 timeout-minutes(挂死可烧 6 小时);e2e/nightly/pr-check 全部无 | e2e.yml/nightly.yml/pr-check.yml 全文 |
| C7 | P1 | M | docker-publish 不打测试门禁直接推镜像,无镜像冒烟,无 provenance/sbom,同 tag 可被覆盖 | `docker-publish.yml:80-95` |
| C8 | P1 | M | deploy-preview 假预览:只构建 + 评论虚构 URL "Preview Environment Deployed",无任何托管/清理 | `deploy-preview.yml:26,56-117` |
| C9 | P1 | S | `pull_request_target` 执行不受信任的 PR 代码(pip install -e 构建钩子 + npm ci postinstall),workflow 声明 pull-requests: write | `pr-check.yml:6-7,151-181` |
| C10 | P2 | S | 棘轮基线可"同 PR 刷基线"绕过;baseline 注释自述已发生过一次刷新吸收漂移;无 CODEOWNERS | `scripts/ci/mypy_ratchet.py:119-122` 等 |
| C11 | P2 | S | 15 个第三方 action 全部钉可变 tag(tj-actions 曾有投毒事件) | `pr-check.yml:61` 等 |
| C12 | P2 | S | 5 个 workflow 无 concurrency,过期 run 堆积 | 仅 docs.yml/docker-publish.yml 有 |
| C13 | P2 | S | ci.yml 无顶层 permissions,GITHUB_TOKEN 用默认权限 | `ci.yml:1-12` |
| C14 | P2 | S | e2e Playwright 缓存死缓存:只在 e2e-setup 保存,4 个 job 从不恢复 | `e2e.yml:60-66` |
| C15 | P2 | S | 夜间巡检失败不可见:pip-audit/npm audit 均 `\|\| true`;`report_nightly_failure.sh` 存在但零引用 | `nightly.yml:342-350,511-516` |
| C16 | P2 | S | 测试超时/重试脚本是死代码:CI 裸跑 pytest 无 timeout/reruns | `scripts/ci/run_tests.py:29` 等 3 个脚本零引用 |
| C17 | P2 | S | 生产 compose MySQL 8.0 vs CI 契约 9.4.0(硬断言) | `docker/compose/prod.yml:15` vs `ci.yml:134` |
| C18 | P2 | S | compose 覆盖文件相对挂载路径失效(按文件目录解析 → `docker/compose/datas` 不存在) | `docker/compose/prod.yml:96-99`、`airflow.yml:23-24` |
| C19 | P2 | S | 无 dependabot/renovate,依赖升级全人工 | `.github/` 无 dependabot.yml |
| C20 | P2 | S | 杂项:docs.yml pip 未锁版本;`diff-cover --compare-branch=origin/master` 对 dev PR 比较对象错误;pr-check 双触发重复 smoke + fork PR 拿不到 merge-ready;`check_deps_sync.py` 名不副实(只查 15 个包存在性);`.kiro/` 20MB 被跟踪 | 各 workflow 对应行 |

本维度已达标:gitleaks 8.30.1 钉版本 + 全历史 + 基线指纹校验 + PR 增量阻断(少见的完整闭环)、npm_audit_ratchet 绑定 lock SHA-256 防无感刷新、mypy_ratchet 钉 mypy 版本、多版本矩阵 3.10/3.11/3.12、backend 镜像非 root + healthcheck、ci-summary 用 needs.*.result 汇总 26 job、chromium 失败上传截图+trace。

## 六、前端质量

| ID | 严重度 | 工作量 | 发现 | 证据 |
| --- | --- | --- | --- | --- |
| F1 | P1 | L | `StrategyPage.vue` 3122 行(模板 2862 行),分解只抽了 3 个弹窗组件 | `src/frontend/src/views/StrategyPage.vue` |
| F2 | P1 | L | `useStrategyPage.ts` 6795 行单一组合式函数,超基线 57 行 | `views/strategy/useStrategyPage.ts:43` |
| F3 | P1 | M | `StockAnalysisPage.vue` 1613 行(+180 超基线);`AssetAnalysisPage.vue` 1504 行新文件超 1000 限制 | ratchet 实跑 |
| F4 | P1 | M | i18n "CJK 清零"未完成:600+ 行硬编码中文(StrategyPage.vue 179 行、useStrategyPage.ts 278 行、PortfolioLedgerPage.vue 40 行、AssetAnalysisPage.vue 82 行等) | `StrategyPage.vue:229,237,312,334,353,365` 等 |
| F5 | P2 | S | 模板中调用方法 `liveReadinessChecklistForReview(...)` 4 处(含 v-for 内复合调用),每帧重算 | `StrategyPage.vue:1551,1557,2393,2399` |
| F6 | P2 | M | echarts 全量引入 + echarts-gl,未按需注册 | `composables/useChartResize.ts:2` 等 5 处 |
| F7 | P2 | S | 死依赖:`vue-echarts`、`@monaco-editor/loader` 全库 0 import | `package.json:11,21` |
| F8 | P2 | S | main.ts 全局注册全部 Element Plus 图标(~300 个) | `main.ts:66-68` |
| F9 | P2 | S | 路由缺 404 catch-all,未知 URL 空白页 | `router/index.ts` 无 `:pathMatch(.*)*` |
| F10 | P2 | S | auth store 反向依赖 3 个业务 store,后续易成环 | `stores/auth.ts:7-9` |
| F11 | P2 | M | 超大 store/composable:`quote.ts` 672 行管 6 类关注点、`useAIChatPage.ts` 851 行、`useKnowledgeBasePage.ts` 755 行 | `stores/quote.ts` 等 |
| F12 | P2 | M | `StrategyPage.test.ts` 8380 行单一 describe;断言绑定 zh-CN 文案(locale 变化即挂) | `__tests__/views/StrategyPage.test.ts:908-918` |
| F13 | P2 | S | 全局错误处理仅 console.error(TODO 上报),与 ErrorBoundary 未联动 | `main.ts:49-56` |
| F14 | P3 | S | 动态 `import('vue')` 取 watch;生产代码唯一 `any` | `main.ts:86`;`views/GatewayConnectDialog.vue:496` |

本维度已达标:路由懒加载 100%、strict TS + 生产代码仅 1 处 any、axios 单实例 + 指数退避重试 + 幂等 + 401 自动登出、三态(loading/error/empty)覆盖、图表 role="img" + aria-label、8 locale + fallbackLocale、vitest 阈值 75% + 8 核心模块 90%、bundle budget 硬门禁、无死组件、v-for 全带 key。

## 七、可观测性与数据治理

| ID | 严重度 | 工作量 | 发现 | 证据 |
| --- | --- | --- | --- | --- |
| O1 | P0→Task C | L | HTTP/DB/错误/回测/实盘 Prometheus 指标全部死指标(record_* 零调用,唯一在用的是 asset_research 系列) | `middleware/metrics.py:64-87,424,502,523` |
| O2 | P1 | M | 生产 OTel 默认关闭 + 无 collector + SDK 无 shutdown(最后一批 span 丢失) | `.env.example:106`;`prod.yml:60-102`;`telemetry.py:88-111`;`startup/__init__.py:32-40` |
| O3 | P1 | M | 日志与请求上下文断裂:InterceptHandler 丢弃 extra;`contextualize` 全仓零使用;服务层日志 request_id 恒 N/A | `utils/logger.py:46-70`;`middleware/logging.py:94-100` |
| O4 | P1 | S | 审计清理任务从未调度:`cleanup_old_records` 实现完整但零调用方,`AUDIT_CLEANUP_HOUR` 只出现在 config 定义处 → 审计表无限增长 | `config.py:529-531`;`services/audit_service.py:282-330` |
| O5 | P1 | S | `config/alerting.yaml` 死配置:指标名与代码不符,全仓无代码消费,运营按此配置告警 100% 静默 | `config/alerting.yaml:8-46` |
| O6 | P2 | S | request_id 仅 8 位 hex(32 bit),~6.5 万请求即 50% 碰撞 | `middleware/logging.py:81,151`;`exception_handling.py:87` |
| O7 | P2 | S | `/api/v1/metrics` 无鉴权;`_SKIP_PATHS` 只含 `/metrics` 前缀不匹配,刮取噪音进日志 | `api/metrics.py:18-36`;`middleware/logging.py:36` |
| O8 | P2 | M | AI 可观测覆盖不均:`log_ai_call` 装饰器 0 使用;策略研究/kb/rag 的 LLM 调用不写 ai_call_log;`_record_ai_call` 无 request_id | `services/ai_observability/logger.py:184-235` |
| O9 | P2 | S | `ai_call_log` 无保留/清理策略(含用户级行为数据) | `services/ai_observability/` 无 cleanup |
| O10 | P2 | M | 告警规则重启后静默失联:monitoring task 只在创建请求里启动,无启动恢复 | `services/monitoring_service.py:117`;`api/monitoring.py:47` |
| O11 | P2 | S | 运维脚本日志每次启动截断丢失(崩溃重启的日志恰是排障最需要的)+ ANSI 转义码 | `scripts/ops/start_app.sh:34-51`;`backend-8000.log` 首行实测 `[32m` |
| O12 | P2 | S | 慢请求阈值 0.5s 与告警 p95>5s 口径不一致,生产日志噪音 | `main.py:126` |
| O13 | P2 | S | 异常日志无 user_id,无法按用户聚合分析 | `middleware/exception_handling.py:24-26,90-94` |
| O14 | P2 | S | XFF 直接信任(与审计中间件 scope client 口径不一致) | `middleware/logging.py:58-60` vs `:231` |
| O15 | P2 | M | 生产 compose 默认 `DB_AUTO_CREATE_SCHEMA=true` + `DB_AUTO_CREATE_DEFAULT_ADMIN=true`:schema 由 create_all 兜底而非 alembic,默认管理员弱口令风险 | `docker/compose/prod.yml:87-88` |
| O16 | P2 | S | 行情数据目录 210MB 无保留策略/清理机制;MySQL 备份无轮转、无恢复演练文档 | `data/datas/`;`scripts/ops/backup_mysql.py` |
| O17 | P2 | S | 日志消息 10000 字符截断丢上下文;InterceptHandler 固定帧深 `sys._getframe(6)` 脆弱 | `utils/logger.py:344-346,64` |
| O18 | P2 | S | `LoggingMiddleware.dispatch` 与 `__call__` 双实现死代码,逻辑已分叉 | `middleware/logging.py:78-139` |

本维度已达标:loguru + InterceptHandler 统一、生产 JSON 结构化、四级文件轮转+压缩+保留、敏感数据多层脱敏、logs↔traces 关联(span 注入 JSON 日志)、`/health` + `/ready` 分项探测 + 优雅停机、低基数指标规范(asset_research 12+ 指标已接线)、Alembic 单头线性链。

## 八、文档与开发者体验

| ID | 严重度 | 工作量 | 发现 | 证据 |
| --- | --- | --- | --- | --- |
| D1 | P1 | M | `README.en.md` 16 个死链接 + 错误仓库名 + 错误 docker 路径(Diátaxis 迁移后入口未同步) | `README.en.md:78,129,310-322` |
| D2 | P1 | S | `CONTRIBUTING.md:21` 克隆命令指向不存在的仓库 | `git clone .../YOUR_USERNAME/ai-for-investor.git` |
| D3 | P1 | S-M | `src/bt_api_py` 已空壳化(0 个 .py、无 pyproject)但根 pyproject members/check_all.sh/CONTRIBUTING 仍声明其为成员 → `make check-all`、`uv sync --workspace` 必然失败 | 根 `pyproject.toml:13-14`;`check_all.sh:24`;`CONTRIBUTING.md:142-171` |
| D4 | P1 | M | CHANGELOG 停更 17 个迭代(176-192 无条目),版本块逆序违反 Keep a Changelog,死链接 + placeholder URL | `CHANGELOG.md:8-33,44,56,194` |
| D5 | P1 | S | 版本号四处不一致:main.py "2.0.0" vs pyproject "0.1.0" vs CHANGELOG 0.2.0-rc1 vs README "v1.x" | `src/backend/app/main.py:104` 等 |
| D6 | P2 | S | AGENTS.md 两处死链接 + ruff 规则集/ pre-commit 清单描述漂移 | `AGENTS.md:55,156,179,180` |
| D7 | P2 | S | iterations/README.md 状态表 4 处与磁盘证据脱节(174 已完成标进行中、179/180 已收口标规划中、192 应更新) | `docs/iterations/README.md:22,27,28,40` |
| D8 | P2 | S | check_doc_links 只扫 docs/**,根级死链接全部漏检(实测 docs 范围内 OK,根级 16+ 死链) | `scripts/ci/check_doc_links.py:16,53-54` |
| D9 | P2 | M | 重要决策缺 ADR:uv workspace、三层数据平台/PIT、192 模型治理/G4 影子观察 | `docs/adr/README.md:10-24` 停在 013 |
| D10 | P2 | S | README 快速开始缺 seed 说明(建表自动完成但演示数据入口未提) | `README.md:47-67,98-104` |
| D11 | P2 | M | API docstring 覆盖 62% summary/64% docstring;14 个 api 文件无模块 docstring;openapi.json 无发布产物 | `app/api/` 473 路由实测 |
| D12 | P2 | S | `.readthedocs.yml` 失效配置(根无 [project] 节,pip install .[docs] 必然失败) | `.readthedocs.yml:1-26` |
| D13 | P2 | S | docs/INDEX.md 缺 explanation/tutorials/examples/architecture 四行 | `docs/INDEX.md:16-32` |
| D14 | P2 | S-M | 迭代 185/186/187 只有 readme.md,182 是 bug 清单非 PLAN,191 无 PLAN;与 190/192 标准结构不一致 | `docs/iterations/迭代185/186/187` |
| D15 | P2 | S | MVP_PRELAUNCH_NOTES.md 过时根级文档,未按归档策略处理 | `MVP_PRELAUNCH_NOTES.md:3` |
| D16 | P2 | M | `app/services` 254 模块中 56 个(22%)缺模块 docstring | 实测统计 |

本维度已达标:Diátaxis 双层治理真实落地、zh/en 发布文档 22/22 完全对齐、PR 模板 diff-aware blocking 门禁、Makefile 7 个 target 全部指向真实脚本、ADR 模板+索引+13 条且近期仍在新增、依赖文档与事实自洽、DX 工具链(.editorconfig/.pre-commit/.nvmrc)互相一致、迭代 190/192 文档是仓库范本。

---

## 九、跨维度统计

- 发现总数:~110(P0×3、P1×40、P2×~70)
- 快速赢项(S 级、可 <1 天完成):30+ 项,集中在 Task D/H/J/L 的 S 级条目
- 跨维度同根因聚类:
  1. **"接线断裂"**:死指标(O1)、死配置(O4/O5)、死脚本(C16)、死门禁(C2/C3)、死缓存(C14)——基础设施已实现但未接通,是 169-192 治理后遗留的最大一类问题
  2. **"棘轮被绕过/欠治理"**:大文件棘轮红灯(B1/F1-F3)、基线同 PR 刷(C10)、coverage omit 套利(T5)——门禁存在但信用受损
  3. **"单一事实源分裂"**:双锁(S7)、版本号四处(D5)、分页风格四种(B10)、安全脚本双轨(S14)、迭代文档结构不统一(D14)
  4. **"收口后入口漂移"**:Diátaxis 迁移后根级文档死链(D1/D2/D6/D8)、CHANGELOG 停更(D4)、iterations 状态表脱节(D7)
