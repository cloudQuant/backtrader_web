# 迭代124 - 优化回测分析功能 - 文档索引

> **迭代目标**: 参考 TBQuant 策略研究功能，新增工作区驱动的策略研究平台  
> **文档状态**: 全部已对齐优化版实施计划（2026-03-15）  
> **交付对象**: 研发团队

---

## 📋 文档清单

### 需求与规划

| 文档 | 说明 | 阅读顺序 |
|------|------|----------|
| [需求.md](需求.md) | 原始需求描述 + UI 截图参考 | 1️⃣ 先读 |
| [实施计划.md](实施计划.md) | **优化版** 分阶段实施计划（P0/P1/P2 分级、排期、风险） | 2️⃣ 必读 |

### 架构与数据设计

| 文档 | 说明 | 阅读顺序 |
|------|------|----------|
| [总体架构设计.md](总体架构设计.md) | 整体架构图、复用边界、概念映射、设计原则、不做项 | 3️⃣ |
| [数据模型设计.md](数据模型设计.md) | 新增5张表 SQL Schema、JSON 结构、引用+快照模式说明 | 4️⃣ |

### 前后端详细设计

| 文档 | 说明 | 阅读顺序 |
|------|------|----------|
| [后端API设计.md](后端API设计.md) | API 路由表（含优先级）、请求/响应 Schema、执行流程、状态刷新方案 | 5️⃣ |
| [前端组件设计.md](前端组件设计.md) | 路由、页面结构、组件拆分、Pinia Store、TypeScript 类型、轮询/WS 方案 | 6️⃣ |

### 功能详细设计

| 文档 | 说明 | 阅读顺序 |
|------|------|----------|
| [工作区功能详细设计.md](工作区功能详细设计.md) | 列表页、详情页、工具栏、表格列、弹窗交互、导入导出、状态刷新 | 7️⃣ |
| [优化与报告功能详细设计.md](优化与报告功能详细设计.md) | 优化参数/线程设置、执行流程、结果展示、组合报告、图表 | 8️⃣ |

---

## 🖼️ UI 参考截图

| 截图 | 对应功能 |
|------|----------|
| [工作区样式.png](工作区样式.png) | 工作区详情页整体布局 |
| [新建策略单元.png](新建策略单元.png) | CreateUnitDialog |
| [数据源设置.png](数据源设置.png) | DataSourceDialog |
| [策略单元设置.png](策略单元设置.png) | UnitSettingsDialog |
| [策略应用设置.png](策略应用设置.png) | StrategyParamsDialog |
| [优化参数设置.png](优化参数设置.png) | OptimizationConfigDialog |
| [优化线程设置.png](优化线程设置.png) | OptimizationThreadDialog |
| [参数优化结果.png](参数优化结果.png) | WorkspaceOptimizationTab |
| [策略报告.png](策略报告.png) | WorkspaceReportTab |
| [导入策略.png](导入策略.png) | ImportUnitDialog |
| [导出策略.png](导出策略.png) | ExportUnit |
| [分组更名.png](分组更名.png) | GroupRenameDialog |
| [单元重命名.png](单元重命名.png) | UnitRenameDialog |

---

## 🎯 优先级速览

### P0（首版必须交付）
- 工作区 CRUD + 列表/详情页
- 策略单元 CRUD + 表格展示
- 数据源/单元设置/策略参数/优化参数 弹窗
- 运行/并行运行/停止 + 轮询状态刷新
- 参数优化（复用现有引擎）+ 结果表格
- 数据库迁移（3张核心表: workspaces, strategy_units, unit_backtest_results）

### P1（增强，可独立交付）
- WebSocket 增强（轮询回退）
- 优化结果图表（折线图/面积图）
- 组合报告 Tab
- 导入/导出（JSON）
- 分组更名/单元重命名
- 优化线程设置
- 应用最佳参数

### P2（顺延/预留）
- 切换商品（预留按钮禁用态）
- K线联动
- XML 导入导出
- 自定义字段计算公式
- 参数热力图
- 从回测/优化页面跳转到工作区
- 样本外递进检验

---

## 📁 新增文件清单（供研发参考）

### 后端
```
src/backend/app/models/workspace.py          # SQLAlchemy Models
src/backend/app/schemas/workspace.py         # Pydantic Schemas
src/backend/app/api/workspace_api.py         # API Router
src/backend/app/services/workspace_service.py # 业务逻辑
alembic/versions/xxx_add_workspace_tables.py # 数据库迁移
```

### 前端
```
src/frontend/src/views/workspace/            # 页面组件 (5个)
src/frontend/src/components/workspace/       # 子组件 (17个)
src/frontend/src/stores/workspace.ts         # Pinia Store
src/frontend/src/api/workspace.ts            # API 调用
src/frontend/src/types/workspace.ts          # TypeScript 类型
```

### 需修改的现有文件
```
src/backend/app/api/router.py                # 注册新路由
src/backend/app/models/__init__.py           # 注册新 Model
src/frontend/src/router/index.ts             # 添加工作区路由
src/frontend/src/components/common/AppLayout.vue  # 添加导航项
```
