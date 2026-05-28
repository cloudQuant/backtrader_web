# Story 2.2: 创建生产部署指南

Status: ready-for-dev

## Story

As a **运维人员**,
I want **有完整的生产部署指南**,
so that **在服务器上部署可靠的生产实例**.

## Acceptance Criteria

1. **Given** 服务器环境（Ubuntu 20.04+），**When** 部署生产实例，**Then** 文档包含 systemd 服务配置文件示例
2. 文档包含 supervisor 配置文件示例
3. 文档说明数据库配置和迁移步骤
4. 文档包含 TLS/HTTPS 配置说明
5. 文档说明环境变量配置（SECRET_KEY, 数据库 URL 等）
6. 文档包含防火墙和端口配置建议
7. 文档包含日志配置和轮转设置
8. 部署步骤已在测试服务器上验证
9. 文档位于 `docs/DEPLOYMENT.md`

## Tasks / Subtasks

- [ ] **Task 1: 创建部署指南** (AC: #1-8)
  - [ ] Subtask 1.1: 创建 docs/DEPLOYMENT.md
  - [ ] Subtask 1.2: 添加 systemd 配置示例
  - [ ] Subtask 1.3: 添加 supervisor 配置示例
  - [ ] Subtask 1.4: 添加数据库配置说明
  - [ ] Subtask 1.5: 添加 HTTPS/TLS 配置
  - [ ] Subtask 1.6: 添加环境变量配置
  - [ ] Subtask 1.7: 添加防火墙配置
  - [ ] Subtask 1.8: 添加日志配置

## Dev Notes

### Previous Story Intelligence

**Story 2.1 完成记录:**
- 安装指南已创建
- 包含虚拟环境设置说明
- 包含故障排查部分

### Architecture Intelligence

**目标文件:**
- `docs/DEPLOYMENT.md` - 新建文件

**参考文档:**
- `docs/INSTALLATION.md` - 安装指南
- `src/backend/README.md` - 后端文档
- `.env.example` - 环境变量示例

### Implementation Guardrails

**DO:**
- 使用生产级配置示例
- 包含安全最佳实践
- 提供完整的配置文件
- 验证部署步骤

**DON'T:**
- 不要使用开发环境的配置
- 不要跳过安全配置
- 不要遗漏重要步骤

### Testing Strategy

**验证步骤:**
1. 在测试服务器上按文档部署
2. 验证所有服务正常运行
3. 验证安全配置生效

## References

- **PRD**: [Source: _bmad-output/planning-artifacts/prd.md#NFR-SEC]
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
