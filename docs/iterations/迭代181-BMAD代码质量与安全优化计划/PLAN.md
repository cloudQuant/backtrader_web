# 迭代 181 - BMAD 代码质量与安全优化计划

> **创建日期**: 2026-06-16
> **来源方法**: `bmad-help` 定位 + 仓库静态扫描 + 既有迭代 177-180 安全/质量基线复核
> **性质**: 安全收口 / 质量债棘轮 / CI 门禁硬化 / 非产品新功能
> **沟通语言**: 中文；代码、命令和配置名保留英文
> **本轮验收**: 见 `ACCEPTANCE.md`

---

## 0. 一句话目标

在 177-180 已建立的安全扫描、mypy 棘轮、产品域整合和大文件治理基础上，把当前仍开放的高风险尾巴继续收口：
**历史凭据治理进入 owner 可执行闭环，命令执行链路不再暴露密码，前端 HTML/Token 小尾巴清零，CI advisory 项逐步有牙齿，并把 mypy/大文件/类型逃逸继续向下拧。**

---

## 1. BMAD Help 定位

本次按 `.kiro/skills/bmad-help/SKILL.md` 的数据源规则读取了：

- `.kiro/bmad/_config/bmad-help.csv`
- `.kiro/bmad/config.toml`
- `.kiro/bmad/config.user.toml`
- `.kiro/bmad/output/code-review-adversarial-findings.md`
- `.kiro/bmad/output/test-artifacts/test-review.md`
- `.kiro/bmad/output/test-artifacts/ci-pipeline-progress.md`
- `.kiro/bmad/output/implementation-artifacts/sprint-status.yaml`

结论：

| 项 | 当前状态 |
| --- | --- |
| BMAD 模块 | `BMad Method` + `Test Architecture Enterprise` 均已安装 |
| 当前阶段 | 处于 implementation / quality assurance 后段，既有 epics 已完成，适合做代码审查、NFR 安全评估、测试审查和下一轮 sprint planning |
| 已有产物 | PRD、Architecture、Epics、Readiness、Adversarial Code Review、Test Review、CI Progress、Sprint Status |
| 输出语言 | `communication_language = Chinese` |
| 下一步建议 | 本文档作为新的迭代计划；实施前建议在新上下文运行 `[CR] bmad-code-review` 或 `[ECH] bmad-review-edge-case-hunter` 聚焦 `sync` / `gateway` / `auth token` 三条高风险链路；安全验收前建议运行 `bmad-testarch-nfr` |

> 注意：BMAD 配置中的 `output_folder` 指向 `{project-root}/_bmad-output`，但当前仓库里实际可见产物位于 `.kiro/bmad/output/`。这不影响本次分析，但应在 181-H 中统一说明，避免后续代理按旧路径找不到产物。

---

## 2. 本轮扫描摘要

扫描范围以真实业务代码和质量配置为主，排除了明显噪音目录：`node_modules`、`.venv*`、`data/exports`、大批 vendored 数据抓取脚本。

### 2.1 关键证据

| 类别 | 实测证据 | 判断 |
| --- | --- | --- |
| secret scan | `.github/workflows/ci.yml` 中 PR 新增 secret 扫描 blocking；full-history scan 仍由 `SECRET_SCAN_HISTORY_BLOCKING` 控制，默认 advisory，并注明历史约 114 findings | 新增泄露已有闸门；历史凭据仍待 owner 轮换 + purge + force-push |
| 历史凭据 | `docs/iterations/迭代178-.../ROTATION_RUNBOOK.md` 已有轮换和历史重写流程；`git log --all -- src/backend/data/manual_gateways.json ...` 仍命中多次历史提交 | 工具齐全，执行动作仍开放 |
| 可疑 tracked 文件 | `src/bt_api_py/configs/ibkr_cookies.json` 当前被 git 跟踪，内容包含 `SBID`、`device.info`、`XYZAB*` 等 cookie 值；`src/clientportal.gw/root/vertx.jks`、`demo.zip` 也被跟踪 | 需要分类：示例/第三方 demo 还是敏感运行时产物；`ibkr_cookies.json` 优先移出真实值 |
| mypy 棘轮 | `scripts/ci/mypy_app_baseline.json` 当前 baseline 为 `958`，注释显示 177: 1065、178: 1017、179: 958 | 棘轮有效，181 继续下调目标应从 958 起算 |
| 超大文件 | `sync_service.py` 2490 行、`gateway/manual.py` 2044 行、`KnowledgeBasePage.vue` 1282 行、`WorkspaceUnitsTab.vue` 1271 行 | 后端 `sync` 和 `gateway` 仍是最值得切片区域 |
| 类型逃逸 | 后端业务代码 `type: ignore` 11 处；前端生产代码 `any` 只有 2 处，测试代码中有大量 `as any` | 生产前端类型风险低；测试辅助和后端局部 ignore 适合做棘轮 |
| 异常吞没 | 核心业务代码未发现 `except Exception: pass`；仅 `scripts/diagnostics/test_ctp_all_servers.py` 有 4 处 bare `except: pass` | 178 的吞异常治理没有明显回归；诊断脚本仍可清理 |
| 命令执行 | `src/backend/app/services/sync/transport.py` 多处用 `f"-p{password}"` 和 `MYSQL_PWD=...` 拼入命令；`run_exec()` 失败/超时时会把 `join_command(args)` 放进错误 | 同步链路存在密码进 argv / 错误消息 / 进程列表暴露风险 |
| 前端 HTML | `StrategyDetailDialog.vue` 唯一 `v-html` 调用仍注释 “consider sanitizing”；项目已有 `utils/markdown-sanitizer.ts` | 应统一由组件或调用方保证 sanitizer 契约并补 XSS 回归测试 |
| Token 存储 | `auth` store 使用 `sessionStorage`，但 `utils/session.ts` 仍保留 legacy `localStorage` fallback/write helper | 需要把迁移尾巴从“长期兼容”变成“有限窗口 + 清除策略” |
| CI advisory | i18n full strict `continue-on-error: true`，e2e i18n `|| true`，monorepo-check job 与 step 均 `continue-on-error: true` | 部分合理保留，但要有 baseline 和解锁条件，不能永久 advisory |

### 2.2 已确认的正向基线

- Python 质量工具已启用：Ruff 规则含 `E/F/I/W/B/UP/C4/T201`，mypy 有分包 strict scope。
- 依赖安全已有 blocking：backend `pip-audit` blocking，frontend `npm audit --audit-level=high`。
- 安全头中间件已存在，生产 CSP 中 `script-src 'self'`，DEBUG 下才允许 `unsafe-inline` / `unsafe-eval`。
- 生产配置已 fail-fast：默认 `SECRET_KEY` / `JWT_SECRET_KEY` / `ADMIN_PASSWORD` 在生产模式会报错。
- `v-html` 相关工具链已引入 DOMPurify，只差契约统一和测试覆盖。

---

## 3. 范围与非范围

### 本迭代做

- 181-A：历史凭据闭环准备与 tracked cookie / demo key 分类。
- 181-B：`sync` 命令执行链路安全加固，重点消除密码进 argv 和错误消息。
- 181-C：`gateway/manual.py` 和命令探测继续切片，降低阻塞 I/O 与大文件风险。
- 181-D：前端 HTML 渲染与 Token 存储尾巴收口。
- 181-E：CI advisory 项转为 baseline-gated 或明确解锁条件。
- 181-F：mypy / `type: ignore` / frontend test `any` 棘轮。
- 181-G：大文件治理下一批切片。
- 181-H：BMAD 产物路径和质量文档同步。

### 本迭代不做

- 不由 agent 自动执行 provider 密钥轮换、`git filter-repo` 历史重写、force-push、协作者 re-clone 等破坏性运维动作。
- 不做大规模产品功能重构，不改变 180 的产品域整合主线。
- 不一次性拆完 `sync_service.py` / `gateway/manual.py`，只做安全收益最高且可回归测试的切片。
- 不把 i18n full strict 直接 blocking，除非先建立稳定 baseline 并证明误报可控。

---

## 4. 181-A - 凭据与敏感文件治理

### 问题

177-178 已经把“新增 secret 阻断”和“历史清理 runbook”建立起来，但 full-history secret scan 仍是 advisory。除此之外，当前树中仍有需要分类的敏感候选：

- `src/bt_api_py/configs/ibkr_cookies.json`：被跟踪且包含 cookie-like 值。
- `src/clientportal.gw/root/vertx.jks`：Java keystore，可能是 third-party demo，也可能被误认为密钥材料。
- `src/clientportal.gw/root/demo.zip`：二进制 demo 包，需说明来源和是否需要入库。

### 建议

1. Owner 按 `docs/iterations/迭代178-安全纵深收口与质量债治理/ROTATION_RUNBOOK.md` 完成 provider 轮换、历史 purge、force-push 和协作者 re-clone。
2. 将 `src/bt_api_py/configs/ibkr_cookies.json` 改为不含真实值的 `.example`，真实 cookies 只允许从 `.env`、本机 keychain、或 gitignored runtime path 注入。
3. 为 `src/clientportal.gw/root/vertx.jks` / `demo.zip` 建立 classification 记录：来源、用途、是否第三方官方 demo、是否可下载重建、校验和、是否应移到 `vendor/` 或 install script。
4. 历史清理完成后设置 `SECRET_SCAN_HISTORY_BLOCKING=true`，使 full-history gitleaks 从 advisory 变 blocking。
5. 增加一个轻量 CI 检查：`git ls-files` 中命中 cookie/key/jks/env/db/zip 等模式时必须出现在 allowlist 并附解释。

### 验收

- [x] `ibkr_cookies.json` 不再包含真实 cookie 值；若保留，只保留 `.example`。
- [ ] `gitleaks detect --config .gitleaks.toml --no-banner --redact` 在历史清理后为 0 findings。
- [ ] `SECRET_SCAN_HISTORY_BLOCKING=true` 已设置并有一次 CI 通过记录。
- [ ] 可疑二进制/keystore 文件均有分类结论和 owner。

---

## 5. 181-B - 同步链路命令执行与密码暴露收口

### 问题

`src/backend/app/services/sync/transport.py` 当前存在以下模式：

- 本地 MySQL 命令使用 `f"-p{password}"`，密码会进入进程 argv。
- 远端命令使用 `MYSQL_PWD=...` 拼进 shell 命令字符串。
- `run_exec()` 在超时/失败时可能输出 `join_command(args)`，把包含密码的参数拼回错误消息。
- `run_bash(["bash", "-lc", command])` 和远端 `bash -lc` 是必要但高风险的运维能力，应当集中建模，而不是任意字符串扩散。

### 建议

1. 为 MySQL CLI 调用引入安全凭据注入方式：
   - 本地优先使用临时 `defaults-extra-file`，权限 `0600`，执行后清理。
   - 远端优先生成远端临时 defaults file 或通过受限 heredoc 创建，避免把密码放进命令字符串。
   - 如果必须使用环境变量，确保错误消息、审计日志和 command preview 全部脱敏。
2. 引入 `redact_command(args, sensitive_values)`，所有异常、日志、测试断言只展示脱敏命令。
3. 对 database/table/object 名称增加白名单校验，禁止通过名称拼接注入 shell / SQL 元字符。
4. 对 `where_sql` 这类高风险参数补来源约束：只能由内部 builder 产生，不能直接来自请求；若来自请求必须改成结构化 filter。
5. 为 `sync_transport` 增加单测：
   - 构造包含特殊字符密码，断言 argv/log/error 不出现原文。
   - 构造恶意 database/table 名，断言被拒绝。
   - 超时/失败路径也必须脱敏。

### 验收

- [x] `rg "f\"-p\\{password\\}\"|MYSQL_PWD=.*password|join_command\\(args\\)" src/backend/app/services/sync` 不再命中未脱敏路径。
- [x] 同步服务失败/超时日志不泄露密码。
- [x] `pytest src/backend/tests/test_sync* -q` 或新增专项测试通过。
- [x] 迁移文档说明新凭据注入方式与故障排查方法。

---

## 6. 181-C - Gateway 阻塞 I/O 与大文件切片

### 问题

`src/backend/app/services/gateway/manual.py` 仍有 2044 行，且保留多处 `subprocess.run`、`subprocess.Popen`、`urllib.request.urlopen`。179 已计划 psutil-first 和 helper 抽取，当前仍值得继续推进。

### 建议

1. 按能力拆分：
   - `gateway/manual_ports.py`：端口占用、进程发现、psutil-first fallback。
   - `gateway/manual_ctp_proxy.py`：CTP/TUN 代理绕行、路由探测、Clash 规则写入。
   - `gateway/manual_network.py`：网络接口、代理、Client Portal 健康探测。
   - `gateway/manual_process.py`：启动/停止与进程生命周期。
2. 所有 subprocess 调用统一经过小型 wrapper，强制 timeout、stderr 上限、脱敏、结构化错误。
3. 对 `urlopen` 调用统一封装 timeout、异常类型和可观测性字段。
4. 不在本迭代拆 gateway family 的全部业务路径，只切纯 helper 和探测逻辑。

### 验收

- [x] `manual.py` 行数下降到 1700 以下，且新增模块均有单测。
- [x] 端口探测在 psutil 可用时不 shell out。
- [x] `pytest src/backend/tests/test_*gateway* src/backend/tests/test_live_trading* -q` 通过。
- [x] 相关文档/REFACTORING_BACKLOG 更新切片状态。

---

## 7. 181-D - 前端 HTML 渲染与 Token 存储尾巴

### 问题

- `StrategyDetailDialog.vue` 使用 `v-html="renderedReadme"`，但组件自身只接收字符串 prop，注释仍写 “consider sanitizing with DOMPurify”。项目已有 `utils/markdown-sanitizer.ts`，但契约不够强。
- `utils/session.ts` 已说明主存储为 `sessionStorage`，但仍提供 legacy `localStorage` fallback 和 `setAccessToken()` 写 localStorage 的能力。

### 建议

1. 将 Markdown 渲染契约收敛到一个方向：
   - 方案 A：组件接收 raw markdown，自行调用 `renderMarkdown()`，禁止调用方传 HTML。
   - 方案 B：prop 改名为 `sanitizedReadmeHtml`，并在类型/注释/测试中明确必须已 sanitizer。
   - 推荐 A，避免所有调用方都要记住安全约束。
2. 增加 XSS 回归测试：
   - `<script>` 被移除。
   - `javascript:` 链接被移除或失效。
   - `img onerror` 被移除。
3. Token 存储尾巴：
   - `setAccessToken()` 不再写 legacy localStorage，只保留清理函数。
   - localStorage fallback 设置明确 sunset：保留一个迭代用于迁移，之后删除。
   - WebSocket 认证继续避免 query token；若未来审计要求更高，改短期 WS ticket。

### 验收

- [x] 生产代码 `v-html` 调用只有受控 sanitizer 契约，并有测试覆盖。
- [ ] 生产代码 `as any` 降为 0。
- [x] 登录 token 不再主动写入 legacy localStorage。
- [x] `npm run typecheck && npm run test -- --run` 通过。

---

## 8. 181-E - CI Advisory 门禁硬化

### 问题

当前 CI 中仍有合理但长期化的 advisory 项：

- `Strict scan full (advisory; CJK + English over-reach)`：`continue-on-error: true`
- e2e i18n：`npx playwright test e2e/i18n/ --reporter=list || true`
- `monorepo-check`：job 和 step 均 `continue-on-error: true`
- full-history gitleaks：依赖 `SECRET_SCAN_HISTORY_BLOCKING`

### 建议

1. i18n e2e 不直接全量 blocking，先做 baseline-gated：
   - 记录当前失败用例数量/路径。
   - 新增失败不得增加。
   - 每次修复下调 baseline。
2. monorepo-check 拆出可 blocking 子集：
   - lockfile/deps sync、ruff、format、typecheck 分别 blocking。
   - 重型或环境敏感步骤保留 nightly advisory。
3. full-history gitleaks 在 181-A 完成后 flip blocking。
4. CI summary 中 advisory 项必须显示“为什么 advisory + 解锁条件 + 当前 baseline”，避免永久软失败。

### 验收

- [x] 至少一个现有 advisory 项转为 blocking 或 baseline-gated。
- [ ] 剩余 advisory 均有明确 owner、baseline、解锁条件。
- [ ] `scripts/dev/check_all.sh` 的失败项可被定位到具体子任务。

---

## 9. 181-F - 类型与测试质量棘轮

### 问题

- mypy 全仓 baseline 已降到 958，但仍有较大存量。
- 后端业务代码仍有 11 处 `type: ignore`。
- 前端生产 `any` 风险低，但测试里大量 `(wrapper.vm as any)` 降低重构反馈质量。

### 建议

1. mypy baseline 目标：958 -> 900 以下。优先包：
   - `app/services/sync`
   - `app/services/stock_analysis`
   - `app/db`
   - `app/middleware`
2. `type: ignore` 目标：11 -> 6 以下。每个保留项必须有具体 error code 和原因。
3. 前端测试引入 typed mount helpers：
   - 常用 view 暴露最小 VM interface。
   - 用 `findComponent` / DOM 行为断言替代直接读 `wrapper.vm as any`。
4. 新增“类型逃逸清单”脚本或文档片段，纳入每轮迭代收口。

### 验收

- [ ] `scripts/ci/mypy_app_baseline.json` 低于 900，且 `python scripts/ci/mypy_ratchet.py` 通过。
- [x] 后端业务 `type: ignore` 少于等于 6。
- [x] 前端生产 `any` 为 0。
- [ ] 测试 `as any` 有下降并记录数值。

---

## 10. 181-G - 大文件治理下一批

### 问题

超大文件继续集中在后端 service 和前端页面：

| 文件 | 行数 | 优先级 |
| --- | ---: | --- |
| `src/backend/app/services/sync_service.py` | 2490 | P1 |
| `src/backend/app/services/gateway/manual.py` | 1697 | P1 |
| `src/frontend/src/views/KnowledgeBasePage.vue` | 1282 | P2 |
| `src/frontend/src/components/workspace/WorkspaceUnitsTab.vue` | 1271 | P2 |
| `src/frontend/src/views/GatewayStatusPage.vue` | 1256 | P2 |
| `src/frontend/src/components/workspace/WorkspaceOptimizationTab.vue` | 1193 | P2 |

### 建议

1. `sync_service.py` 先按安全边界拆，而不是按函数机械搬家：
   - `sync/credential_resolver.py`
   - `sync/mysql_cli.py`
   - `sync/schema_ops.py`
   - `sync/table_diff.py`
2. 前端优先拆 `KnowledgeBasePage.vue` 和 `GatewayStatusPage.vue`：
   - composable 承接状态/副作用。
   - 子组件承接表格、表单、状态卡。
   - 页面只保留编排。
3. 每个切片都要保持旧 API/旧路由兼容，不与 180 产品域整合互相踩踏。

### 验收

- [ ] `sync_service.py` 下降到 2100 行以下。
- [x] `manual.py` 下降到 1700 行以下。
- [ ] 至少一个前端 >1200 行页面下降到 900 行以下，且交互测试通过。

---

## 11. 181-H - BMAD 产物路径与文档同步

### 问题

`bmad-help` 默认数据源文档写的是 `{project-root}/_bmad/_config/bmad-help.csv` 和 `_bmad-output`，但当前项目实际在 `.kiro/bmad/_config/bmad-help.csv`、`.kiro/bmad/output/...`。历史报告里也混用 `_bmad-output` 和 `.kiro/bmad/output`。

### 建议

1. 在 `docs/reference/project-context.md` 或新的 BMAD 使用说明中明确本仓库的实际 BMAD 路径。
2. 如果后续仍使用 `.kiro/bmad`，则修正文档中 `_bmad-output` 的引用，或者建立兼容软链接/说明。
3. 更新 `docs/reports/archive/CODE_QUALITY_REPORT.md` 中旧的 BMAD 建议，把 181 的实际下一步补进去。
4. 推荐后续在新上下文运行：
   - `[CR] bmad-code-review`：聚焦 181-B / 181-C 的实现变更。
   - `[ECH] bmad-review-edge-case-hunter`：聚焦 sync 命令注入、凭据脱敏、gateway 探测边界。
   - `bmad-testarch-nfr`：在安全加固完成后做 NFR 评估。

### 验收

- [ ] BMAD 路径说明不再互相矛盾。
- [ ] 新加入项目的人能从 README / docs 找到当前 BMAD 产物位置。
- [ ] 181 收口文档记录实际运行过的 BMAD 检查及结论。

---

## 12. 执行顺序

建议按风险收益排序执行：

1. **181-A**：敏感文件分类和历史凭据 owner 闭环准备。
2. **181-B**：sync 密码不进 argv / 错误消息脱敏。
3. **181-D**：前端 `v-html` sanitizer 契约和 token localStorage 尾巴。
4. **181-C**：gateway 探测和 subprocess wrapper 切片。
5. **181-E**：CI advisory baseline-gated / blocking。
6. **181-F**：mypy 和类型逃逸棘轮。
7. **181-G**：大文件切片。
8. **181-H**：BMAD 文档同步和收口报告。

---

## 13. 总体验收标准

- [ ] 安全：新增 secret 继续 blocking；历史 secret 清理有 owner 执行记录；敏感 tracked 文件均分类或移出。
- [x] 安全：sync 命令执行错误、日志、进程 argv 不暴露 MySQL 密码。
- [x] 安全：前端 `v-html` 只有受控 sanitizer 契约，且有 XSS 回归测试。
- [ ] 质量：mypy baseline 从 958 下调到 900 以下。
- [x] 质量：后端业务 `type: ignore` 少于等于 6，前端生产 `any` 为 0。
- [x] 质量：至少一个 CI advisory 项转为 blocking 或 baseline-gated。
- [x] 可维护性：`sync_service.py` / `gateway/manual.py` 至少完成一个安全相关切片，行数下降并补单测。
- [x] 文档：BMAD 产物路径、181 发现、执行记录和剩余风险均在 docs 中闭环。

---

## 14. 验证命令建议

```bash
# Secret / tracked sensitive candidate scan
git ls-files | rg "(^|/)(\\.env|.*\\.env|.*secret.*|.*credential.*|.*cookies.*|.*token.*|.*\\.pem|.*\\.key|.*\\.p12|.*\\.jks|.*\\.db|.*\\.sqlite|.*\\.zip)$" -S
gitleaks detect --config .gitleaks.toml --no-banner --redact

# Backend quality
cd src/backend
ruff check .
ruff format --check .
python ../../scripts/ci/mypy_ratchet.py
pytest -m "not e2e" -q

# Focused sync/gateway tests
pytest tests/test_sync* tests/test_*gateway* tests/test_live_trading* -q

# Frontend quality
cd src/frontend
npm run typecheck
npm run lint
npm run test -- --run

# CI advisory inventory
rg -n "continue-on-error|\\|\\| true|SECRET_SCAN_HISTORY_BLOCKING" .github/workflows scripts
```

---

## 15. 主要风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 历史 purge / force-push 影响所有协作者 | 高 | 只由 owner 在维护窗口执行；执行前备份、通知、要求 re-clone |
| sync CLI 凭据注入方式改变导致导入导出失败 | 中高 | 先加 transport 单测，再灰度到一个本地 MySQL case，保留 feature flag 一个迭代 |
| gateway 探测切片影响实盘连接 | 高 | 只动探测/helper，实盘下单路径不动；用现有 gateway/live_trading 测试回归 |
| i18n / monorepo 直接 blocking 带来误报 | 中 | 先 baseline-gated，不直接全量 blocking |
| 前端 token localStorage fallback 删除影响老会话 | 中 | 设置一个迭代 sunset，先迁移并清理，再删除 fallback |
