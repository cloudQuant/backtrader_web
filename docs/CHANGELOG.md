# 更新日志

本文档记录 Backtrader Web 的版本更新历史。

## [2.2.0] - 2026-02-24

### E2E 测试加固
- ✅ 消除静默跳过：16 处 `if count()>0` 改为 `pytest.skip()` 并附带原因
- ✅ `FRONTEND_URL` 集中化：13 个测试文件统一从 `conftest.py` 导入
- ✅ 新增 `test_data_ready` session fixture，通过 API 预创建回测数据
- ✅ `test_strategy_crud.py` 中 4 处预期元素改为显式 skip

### API 文档增强
- ✅ `API.md` 新增 5 个核心端点的 curl 请求 + JSON 响应示例
- ✅ `API.md` examples/ 引用从 7 个补齐至全部 12 个脚本

### 架构可视化
- ✅ `DATABASE.md` ASCII ER 图替换为 Mermaid erDiagram（9 实体、8 关系）

### 后端测试修复
- ✅ 运行 1481 后端单测 → 修复 `test_fincore_import.py` 3 个失败（namespace package 无 `__version__`）

### 开发体验
- ✅ `.env.example` 补齐缺失变量（CORS、admin、BACKTEST_TIMEOUT）并修正端口为 8001
- ✅ 新增 `.pre-commit-config.yaml`（Ruff lint/format + 通用文件检查）
- ✅ `README.md` 更新：端口 8001/3000、Node 20+、技术栈增 fincore/测试、项目结构

### 文档维护
- ✅ `TESTING.md` 更新端口和测试文件列表（新增 6 个）
- ✅ `CODING_STANDARDS.md` 修正 Python 3.10+ 和 Ruff 配置
- ✅ `docs/CONTRIBUTING.md` 去重为指向根目录的重定向（329→15 行）
- ✅ `INDEX.md` 分类调整 + 迭代历史链接
- ✅ 迭代笔记归档：`docs/迭代/` 残留移入 `docs/iterations/`
- ✅ 3 个已完成审查/计划文档标记 ✅ 完成

---

## [2.1.0] - 2026-02-24

### 新增功能

#### E2E 测试覆盖扩展
- ✅ 新增 6 个 E2E 测试文件，覆盖 optimization、backtest-result、live-trading、portfolio、strategy-crud、data-query 页面
- ✅ E2E 测试总数从 74 增至 **127 个**，全部通过
- ✅ 路由覆盖率从 67% 提升至 **100%**（12/12 路由）
- ✅ 改进 `conftest.py`：API 直接注册（跳过 UI）、增加超时、正则 URL 匹配

#### 文档体系完善
- ✅ 新增 `BACKTEST_GUIDE.md` — 回测使用说明
- ✅ 新增 `LIVE_TRADING.md` — 实盘交易文档
- ✅ 新增 `OPTIMIZATION.md` — 参数优化指南
- ✅ 新增 `TROUBLESHOOTING.md` — 故障排查手册
- ✅ 新增 `PERFORMANCE.md` — 性能优化指南
- ✅ `API.md` 全面更新：15 模块 80+ 端点完整记录
- ✅ `TECHNICAL_DOCS.md` 精简：用交叉引用替换重复内容（709 行→~400 行）
- ✅ `ARCHITECTURE.md` 增加 Mermaid 序列图（回测流程、实盘流程、部署架构）
- ✅ 迭代历史文档迁移至 `docs/iterations/`
- ✅ `INDEX.md` 更新：修复 6 个断链

#### 项目扫描与质量分析
- ✅ 生成 `project-scan-report.json` 项目全扫描报告
- ✅ 生成 `source-tree-analysis.md` 源码树分析
- ✅ 生成 `EDITORIAL_REVIEW_STRUCTURE.md` 结构审查报告
- ✅ 生成 `E2E_TEST_COVERAGE_ANALYSIS.md` 测试覆盖率分析

### 修复

- 修复 E2E 测试中 Playwright CSS 选择器语法错误（`i` 标志不支持）
- 修复 live-trading 页面标题断言（h1 为全局标题而非页面标题）
- 修复 optimization 提交按钮测试（按钮需先选策略才显示）
- 修复 strategy-crud 对话框可见性判断（Element Plus 动画延迟）
- 修正 Vite proxy 和 conftest.py 中的后端端口配置

## [2.0.0] - 2024-02-24

### 新增功能

#### 安全增强
- ✅ JWT Refresh Token 支持，实现 Token 轮换机制
- ✅ 全局异常处理中间件，统一错误响应格式
- ✅ 安全头中间件 (CSP, HSTS, X-Frame-Options 等)
- ✅ 输入验证和清理工具 (SQL注入、XSS、命令注入防护)
- ✅ 环境变量验证 (生产环境安全检查)
- ✅ 自定义异常层次结构

#### 性能优化
- ✅ 数据库批量操作 (bulk_create, bulk_update, bulk_delete)
- ✅ 高效的 exists() 方法替代 count()
- ✅ get_by_fields() 多字段查询
- ✅ count() 支持 IN 查询
- ✅ update() 可选 refresh 参数

#### API 改进
- ✅ API Schema 添加 json_schema_extra 示例
- ✅ 改进的错误响应格式

#### 测试
- ✅ 1462 个测试全部通过
- ✅ 测试覆盖率提升

#### 文档
- ✅ 完整的中文文档
- ✅ API 文档
- ✅ 安全指南
- ✅ 架构设计文档
- ✅ 数据库设计文档

### 修复

- 修正认证状态码 (401 vs 403)
- 修复 metrics_source 字段处理
- 修复测试中的 mock 对象问题

### 技术栈更新

- FastAPI 0.100+
- SQLAlchemy 2.0+
- Python 3.10+

## [1.9.0] - 2024-02-15

### 新增功能

- Fincore 库集成用于财务指标计算
- 回测结果对比功能
- 策略版本控制和分支管理
- 实时市场数据 WebSocket 推送
- 监控和告警系统

### 优化

- 改进回测性能
- 优化数据库查询
- 添加缓存层

## [1.8.0] - 2024-01-30

### 新增功能

- 参数优化功能 (网格搜索、贝叶斯优化)
- 回测报告导出 (HTML/PDF/Excel)
- 模拟交易环境
- WebSocket 实时推送

### 改进

- 重构 API 路由结构
- 改进错误处理
- 添加日志中间件

## [1.5.0] - 2024-01-15

### 新增功能

- 策略管理 (CRUD)
- 历史数据回测
- 基础技术指标

### 初始版本

- FastAPI 后端框架
- Vue 3 前端框架
- SQLite 数据库支持

## 版本命名规则

- **主版本号**: 重大架构变更
- **次版本号**: 新功能添加
- **修订号**: Bug 修复和小改进

## 更新记录

查看详细变更历史:

```bash
git log --oneline -20
```

## 即将发布

- [ ] 前端界面优化
- [ ] 更多技术指标
- [ ] 机器学习策略支持
- [ ] 分布式回测
