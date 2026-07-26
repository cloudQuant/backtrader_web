# Story 2.1: 创建安装和快速入门指南

Status: done

## Story

As a **新用户**,
I want **有清晰的安装和快速入门文档**,
so that **在 10 分钟内完成本地部署并运行第一次回测**.

## Acceptance Criteria

1. **Given** 新用户访问项目文档，**When** 阅读安装指南，**Then** 文档包含 Python 版本要求（3.8+）
2. 文档提供 pip install 安装命令
3. 文档包含虚拟环境设置说明
4. 文档提供首次运行配置步骤
5. 文档包含首次登录和创建策略的快速入门
6. 文档包含常见安装问题排查部分
7. 安装步骤已验证在干净环境中成功
8. 文档位于 `docs/INSTALLATION.md`

## Tasks / Subtasks

- [ ] **Task 1: 创建安装指南** (AC: #1-7)
  - [ ] Subtask 1.1: 创建 docs/INSTALLATION.md
  - [ ] Subtask 1.2: 添加 Python 版本要求和依赖说明
  - [ ] Subtask 1.3: 添加虚拟环境设置步骤
  - [ ] Subtask 1.4: 添加 pip install 安装命令
  - [ ] Subtask 1.5: 添加配置步骤说明
  - [ ] Subtask 1.6: 添加快速入门部分
  - [ ] Subtask 1.7: 添加故障排查部分

## Dev Notes

### Previous Epic Intelligence

**Epic 1 完成记录:**
- fincore 库已集成
- 88 个测试全部通过
- 依赖项已添加到 pyproject.toml

### Architecture Intelligence

**目标文件:**
- `docs/INSTALLATION.md` - 新建文件

**参考文档:**
- `README.en.md` - 现有项目说明
- `src/backend/README.md` - 后端文档
- `pyproject.toml` - 依赖列表

### Implementation Guardrails

**DO:**
- 创建清晰的步骤说明
- 包含命令行示例
- 添加故障排查部分
- 验证安装步骤

**DON'T:**
- 不要跳过重要步骤
- 不要假设用户有高级知识
- 不要遗漏依赖项

### Testing Strategy

**验证步骤:**
1. 在新环境中按文档执行安装
2. 验证所有命令可运行
3. 验证服务可启动

## References

- **PRD**: [Source: _bmad-output/planning-artifacts/prd.md#FR1-5]
- **Architecture**: [Source: _bmad-output/planning-artifacts/architecture.md#Deployment]
- **Epic 2 Stories**: [Source: _bmad-output/planning-artifacts/epics.md#Epic 2]

## Dev Agent Record

### Agent Model Used

_(待开发时填写)_

### Debug Log References

_(待开发时填写)_

### Completion Notes List

_(待开发时填写)_

### File List

_(待开发时填写)_
