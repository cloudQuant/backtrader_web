# 迭代163 - Goal 夜间项目完善任务书

> **文档状态**: 可执行  
> **创建日期**: 2026-05-14  
> **使用场景**: 适合交给 `goal` 类自动化开发技能通宵执行  
> **核心目标**: 在不破坏现有业务、不触碰真实交易风险的前提下，持续提升 Backtrader Web 的稳定性、可用性、测试覆盖和产品完成度。

---

## 1. 总目标

让项目在一个夜间自动迭代周期内变得更完善，优先处理“长期需要持续打磨、且自动化代理能独立推进”的事项。

本轮不是做大改版，也不是引入新基础设施。目标是把已有功能打磨得更稳：

1. 知识库和 AI 问答继续优化；
2. 策略 Copilot、工作区、回测报告链路继续补强；
3. 统一修复前端空状态、错误状态、加载状态；
4. 补充测试覆盖，减少回归；
5. 改善数据库兼容、自启动、错误提示和文档一致性。

---

## 2. 夜间执行原则

### 2.1 可以自动做

1. 修复明确的 bug；
2. 增加防御式空值处理；
3. 补单元测试、组件测试、API 测试；
4. 改善错误提示和日志上下文；
5. 提升现有页面的空状态、加载态、失败态；
6. 整理文档、补验收说明；
7. 小范围重构重复逻辑，但必须保持接口兼容；
8. 给已有功能补充缺失的边界校验。

### 2.2 不要自动做

1. 不要接入真实交易网关或主动下单；
2. 不要修改 `.env` 中的真实密钥；
3. 不要删除用户数据、数据库文件、大目录数据集；
4. 不要执行破坏性 Git 命令；
5. 不要引入大规模新依赖或替换技术栈；
6. 不要重写认证、权限、数据库底层架构；
7. 不要把临时大文件、PDF 数据、运行态文件提交进 Git。

---

## 3. 持续优化模块判断

除了知识库和 AI 两个功能外，项目中还适合持续优化的模块如下。

| 优先级 | 模块 | 为什么需要持续优化 | 夜间适合做什么 |
|------|------|------------------|----------------|
| P0 | 知识库与 AI 问答 | 当前仍在快速迭代，涉及索引、RAG、对话、引用、模型配置 | 修复问答失败、索引状态、引用展示、空状态、错误提示、测试 |
| P0 | AI 策略 Copilot | 已连接策略生成、保存、工作区、回测、报告，链路长、回归风险高 | 补测试、补失败态、校验策略草稿字段、优化报告状态展示 |
| P0 | 工作区与回测报告 | 是策略研究主闭环，影响用户核心使用 | 修复执行状态、报告生成、空数据展示、状态轮询、测试 |
| P1 | 数据管理 | 后续策略研究依赖数据质量和任务执行稳定性 | 优化任务列表、执行状态、错误提示、空表空状态、文档 |
| P1 | 回测分析与结果页 | 用户判断策略质量的关键页面 | 指标解释、异常值展示、图表空数据、防御式渲染、测试 |
| P1 | 数据库兼容与启动自检 | 本地 SQLite、PostgreSQL、MySQL 兼容容易出现旧库缺表/缺列问题 | 补 schema compatibility、启动日志、迁移文档、测试 |
| P1 | 前端全局体验 | 页面多、状态复杂，容易出现未处理 Promise 和空值崩溃 | 统一 loading/error/empty、防止 watcher 抛错、补组件测试 |
| P1 | 安全与配置 | 策略执行、AI、网关、密钥都属于敏感边界 | 强化配置校验、默认值警告、敏感信息隐藏、测试 |
| P2 | 实盘/网关管理 | 高风险模块，不适合夜间大改 | 只做只读页面、错误提示、日志展示、测试，不做连接行为变更 |
| P2 | 文档站与开发文档 | 功能多，文档容易落后 | 同步用户文档、开发文档、验收清单 |

---

## 4. 推荐夜间执行顺序

### 阶段一：安全扫描与现状确认

- [x] 读取当前 `git status --short`，识别已有脏文件，避免覆盖用户改动；
- [ ] 读取最近失败日志和测试失败输出；
- [x] 只选择与本任务相关的文件修改；
- [x] 明确本轮不碰真实交易连接、密钥和运行态数据。

验收标准：

1. 不误删文件；
2. 不把运行态数据加入提交；
3. 后续改动都有明确模块归属。

### 阶段二：知识库与 AI 问答稳定性

- [ ] 检查 `/knowledge-base`、`/rag`、`/kb-chat` API 的失败路径；
- [x] 优化文档未索引、空知识库、空文档、删除文档后的问答表现；
- [x] 修复 AIChat 页面 watcher、computed、模板中的空值风险；
- [ ] 让后端错误能在前端显示真实原因；
- [x] 补充 API 测试和前端 store/view 测试。

验收标准：

1. 空知识库提问不会 500；
2. 未索引文档可自动进入可检索状态；
3. 删除知识库或文档后，会话列表和引用不会崩；
4. 前端不会出现未处理 Promise 导致整页白屏。

### 阶段三：AI 策略 Copilot 与工作区闭环

- [x] 检查策略草稿字段缺失时的保存、添加工作区、回测按钮状态；
- [x] 优化 `useStrategyDraftWorkspaceExecution` 的轮询、报告生成、失败提示；
- [ ] 补齐“添加工作区失败 / 回测提交失败 / 报告生成失败”的 UI 状态；
- [x] 增加对 strategy draft schema 的测试样例；
- [ ] 确保 AI 生成策略不影响已有策略管理 API。

验收标准：

1. 策略草稿缺字段时不会前端崩溃；
2. 添加工作区和一键回测失败时提示明确；
3. 报告生成失败不会卡在“生成中”；
4. 相关测试通过。

### 阶段四：工作区、回测报告、数据管理体验补强

- [ ] 检查工作区列表、详情页、报表页的空状态；
- [ ] 检查回测结果缺指标、缺图表数据时的展示；
- [ ] 优化数据管理任务失败时的用户提示；
- [ ] 给关键页面补组件测试；
- [ ] 保持页面视觉与现有 Element Plus 工作台风格一致。

验收标准：

1. 没有数据时页面有明确空状态；
2. API 失败时页面不崩；
3. 图表无数据时不报错；
4. 不引入营销式大改版。

### 阶段五：数据库兼容、配置与启动质量

- [ ] 检查新表/新列是否在 `ensure_schema_compatibility()` 中兼容旧数据库；
- [ ] 检查 `.env.example` 是否覆盖新增配置；
- [ ] 检查启动日志是否能说明缺少哪些可选能力；
- [ ] 给 schema compatibility 补测试；
- [ ] 避免强制自动创建默认管理员，保持当前安全策略。

验收标准：

1. 旧 SQLite 本地库启动不会因为缺表缺列直接 500；
2. 配置缺失时有清晰日志；
3. 测试覆盖兼容逻辑。

### 阶段六：文档与测试收尾

- [x] 更新对应迭代文档；
- [ ] 更新必要的用户说明或开发说明；
- [x] 补充测试命令与结果；
- [x] 汇总改动清单；
- [x] 输出剩余风险和下一轮建议。

验收标准：

1. 文档能解释为什么改、改了什么、怎么验收；
2. 测试命令可复现；
3. 剩余风险有明确记录。

---

## 5. 推荐任务池

### P0 - 建议今晚优先完成

- [x] `AIChatPage` 所有 API watcher 增加错误隔离；
- [x] `kbChat` store 对异常响应、空数组、缺字段做兼容；
- [x] `RAGService` 对空文档、文件夹、重复索引、旧 chunk 做回归测试；
- [x] 知识库删除后，会话和 chunk 级联行为补测试；
- [x] 策略草稿操作按钮在字段缺失时禁用并提示原因；
- [x] 工作区回测轮询失败后恢复按钮状态；
- [x] 前端 `npm run typecheck` 保持通过；
- [ ] 后端知识库/AI/工作区相关测试保持通过。

### P1 - 有时间继续做

- [ ] 知识库页增加“重建索引”或“索引状态说明”的轻量入口；
- [ ] AI 问答引用展示增加空内容保护；
- [ ] 回测报告页面缺指标时展示 `-` 或解释性空状态；
- [ ] 数据管理任务失败原因展示后端 detail；
- [ ] `.env.example` 补 AI_CHAT、知识库、DB schema 相关说明；
- [ ] 文档站补“AI 策略 Copilot 使用说明”索引入口。

### P2 - 只在前面完成后做

- [ ] 全局错误处理统一抽一个 helper；
- [ ] 给常见 API list response 增加前端运行时兼容；
- [ ] 清理重复的测试 mock；
- [ ] 小范围整理迭代文档索引；
- [ ] 给可选 router 状态增加前端可见诊断页。

---

## 6. 推荐验证命令

后端最小验证：

```bash
cd src/backend
pytest tests/test_iteration129_knowledge_base_api.py tests/test_iteration129_kb_chat_api.py tests/test_iteration129_rag_api.py
pytest tests/test_live_trading_api.py tests/test_strategy_api.py
```

后端扩展验证：

```bash
cd src/backend
pytest tests/test_db.py tests/test_gateway_preset_and_launch.py tests/test_extracted_modules.py
```

前端最小验证：

```bash
cd src/frontend
npm run typecheck
npm run test -- src/test/views/AIChatPage.test.ts src/test/stores/kbChat.test.ts src/test/composables/useStrategyDraftWorkspaceExecution.test.ts --run
```

前端扩展验证：

```bash
cd src/frontend
npm run test -- --run
```

---

## 7. 停止条件

如果出现以下任一情况，`goal` 应停止并输出报告，不要继续扩大修改范围：

1. 同一个测试连续失败 3 次且原因不明确；
2. 需要真实交易账号、真实网关、真实密钥才能继续；
3. 需要删除或迁移用户数据；
4. 需要大规模数据库迁移且没有备份方案；
5. 改动跨越 5 个以上核心业务模块且没有清晰验收边界；
6. 前端页面需要完整重设计而不是修复/补强；
7. 发现当前工作区已有用户改动与目标冲突。

---

## 8. 输出格式要求

夜间执行结束后，输出一份总结：

```markdown
# Goal 夜间执行总结

## 完成内容
- ...

## 修改文件
- ...

## 测试结果
- 命令：...
- 结果：...

## 未完成事项
- ...

## 风险与建议
- ...
```

---

## 9. 本轮 Goal 执行结果

### 9.1 完成内容

- 显式清理知识库删除时关联的 `chat_messages`、`chat_conversations`、`document_chunks`、`kb_documents`，降低 SQLite 旧库或外键未启用时的残留风险。
- 删除单篇知识库文档时显式清理对应 chunk，避免删除文档后旧引用继续被检索。
- 为 RAG 增加空知识库、文件夹跳过、空文档跳过、重复自动索引不重复建 chunk、文档更新后旧 chunk 清理的回归测试。
- `kbChat` store 对历史记录缺 `messages`、发送响应缺 `citations` / `strategy_draft` / `reasoning` 等字段做兼容。
- `kbChat` store 在发送成功但刷新会话列表失败时不再把本次 AI 回答误判为发送失败。
- `AIChatPage` 对策略草稿缺关键字段时禁用保存、添加工作区、一键回测、生成报告，并在卡片内提示缺失原因。
- 工作区回测自动轮询失败后会清理轮询并把运行态标记为 `status_unknown`，避免用户误以为仍在正常等待。
- 迭代文档已同步本轮执行结果和验证命令。

### 9.2 修改文件

- `src/backend/app/services/knowledge_base_service.py`
- `src/backend/tests/test_iteration129_knowledge_base_api.py`
- `src/backend/tests/test_iteration129_rag_api.py`
- `src/frontend/src/stores/kbChat.ts`
- `src/frontend/src/views/AIChatPage.vue`
- `src/frontend/src/composables/useStrategyDraftWorkspaceExecution.ts`
- `src/frontend/src/test/stores/kbChat.test.ts`
- `src/frontend/src/test/composables/useStrategyDraftWorkspaceExecution.test.ts`
- `docs/iterations/迭代163-Goal夜间项目完善/index.md`

### 9.3 测试结果

- 命令：`cd src/backend && pytest tests/test_iteration129_knowledge_base_api.py tests/test_iteration129_kb_chat_api.py tests/test_iteration129_rag_api.py`
- 结果：`23 passed, 7 warnings`
- 命令：`cd src/frontend && npm run test -- src/test/views/AIChatPage.test.ts src/test/stores/kbChat.test.ts src/test/composables/useStrategyDraftWorkspaceExecution.test.ts --run`
- 结果：`21 passed`
- 命令：`cd src/frontend && npm run typecheck`
- 结果：通过

### 9.4 未完成事项

- 未执行前端全量测试 `npm run test -- --run`。
- 未执行后端扩展验证 `tests/test_live_trading_api.py`、`tests/test_strategy_api.py`、`tests/test_db.py`、网关相关测试。
- P1/P2 的数据管理、回测结果页、全局错误处理和文档站入口未在本轮展开。

### 9.5 风险与建议

- 当前知识库/AI 闭环已有最小回归覆盖，但真实生成式模型返回的 strategy draft 仍可能存在非标准结构，建议下一轮继续把后端 schema 校正和前端运行时校验合并成统一 validator。
- 后端数据库兼容已覆盖缺表缺列启动场景，但删除级联仍建议后续补一组服务层单测，避免不同数据库方言行为差异。
- 下一轮优先补“重建索引”入口、AI 模型配置诊断提示、回测报告空指标展示。

---

## 9. 最推荐的夜间目标

如果只能选一个方向，优先做：

> **知识库 + AI 问答 + 策略 Copilot + 工作区报告闭环的稳定性打磨。**

原因：

1. 这是当前项目最活跃、最容易出回归的功能线；
2. 用户体验直接受益；
3. 自动化代理可以通过测试、空状态和错误处理持续推进；
4. 不需要真实交易环境；
5. 改进成果容易验收。

第二优先级是：

> **数据库兼容、配置自检、前端错误隔离。**

这类工作不会显著改变产品形态，但能明显降低本地运行和后续开发的不确定性。
