# CI 门禁策略说明

> 迭代 123-A T6+T7+T8 产出物

## 1. 分类原则

| 类别 | 含义 | 失败后果 |
|------|------|---------|
| **Blocker** | 必须通过才能合并 | CI 标红，`ci-summary` 返回 exit 1 |
| **Advisory** | 仅记录，不阻断合并 | 产出 warning 注解和报告 artifact |

## 2. CI 门禁分类表 (`ci.yml`)

### Blocker Jobs

| Job | 检查内容 | 阻断理由 |
|-----|---------|---------|
| `check-generated-artifacts` | 禁止提交生成物 | 仓库清洁性 |
| `check-doc-links` | 文档链接有效性 | 文档可维护性 |
| `check-deps-sync` | 前后端依赖同步 | 部署一致性 |
| `backend-lint` | Ruff lint + format + import sort | 代码风格一致性 |
| `backend-test` | pytest 单元测试 + 覆盖率 | 功能正确性 |
| `frontend-lint` | ESLint + vue-tsc 类型检查 | 代码风格与类型安全 |
| `frontend-test` | Vitest 单元测试 + 覆盖率 | 功能正确性 |
| `frontend-build` | 生产构建 | 构建可部署性 |
| `integration-test` | PostgreSQL 集成测试 | 跨层功能正确性 |

### Advisory Jobs

| Job | 检查内容 | 不阻断理由 |
|-----|---------|-----------|
| `backend-security` | Bandit + Safety | 安全扫描误报率高，需人工研判 |

## 3. Nightly 门禁分类表 (`nightly.yml`)

### Blocker Jobs

| Job | 检查内容 |
|-----|---------|
| `backend-full-tests` | 全量后端测试 |
| `frontend-full-tests` | 全量前端测试 |
| `e2e-full-tests` | 全浏览器 E2E 测试 |

### Advisory Jobs

| Job | 检查内容 | 不阻断理由 |
|-----|---------|-----------|
| `performance-tests` | API 性能测试 | 基准波动，需趋势分析 |
| `dependency-audit` | pip-audit + npm audit | 依赖审计误报率高 |

## 4. 本轮变更摘要

### 4.1 `ci.yml` 变更

1. **Integration test 升级为 Blocker**
   - 移除 `|| true`，失败将真实阻断 CI
   - 加入 `ci-summary` 的 `needs` 和失败检查条件

2. **`check-deps-sync` 加入 Summary**
   - 之前独立运行但不影响 `ci-summary` 结果
   - 现在纳入 Blocker 失败检查

3. **Security scan 标注为 Advisory**
   - 步骤名增加 `(advisory)` 标注
   - 失败时产出 GitHub warning annotation 而非静默吞掉
   - 仍保留 `|| true` 但增加 echo warning

4. **Summary 输出结构化**
   - 使用 `$GITHUB_STEP_SUMMARY` 输出 Markdown 表格
   - 明确区分 Blocker 和 Advisory 两组
   - 步骤重命名为 `Fail if any blocker job failed`

### 4.2 `nightly.yml` 保持现状

- Dependency audit 已正确使用 `|| true`（advisory）
- Performance tests 不在失败条件中（advisory）
- 三项核心测试（backend/frontend/e2e）已在失败条件中

## 5. 后续维护指引

- **新增 Blocker 检查**：加入 `ci-summary.needs` + 在 `Fail if any blocker job failed` 条件中添加
- **新增 Advisory 检查**：加入 `ci-summary.needs` + 在 Summary 表格中添加，但不加入失败条件
- **升级 Advisory → Blocker**：将 job 从 Advisory 表移到 Blocker 表，加入失败条件
