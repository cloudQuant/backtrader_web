# 迭代127 - 方案B：研发执行任务拆解

> **文档状态**: 执行版  
> **最后更新**: 2026-04-13  
> **适用目标**: 研发排期 / 开发协同 / 测试跟踪

## 1. 文档目标

本方案将迭代127拆解为可执行的研发任务包，供前端、后端、测试协同推进。拆解原则如下：

- **按闭环拆解，而不是按功能堆叠拆解**
- **按依赖顺序推进，避免前后端相互阻塞**
- **优先交付 P0，P1/P2 可顺延**
- **每个阶段结束后都应处于可联调、可演示状态**

### 技术经理执行修订

- 交易工作区继续复用统一 `workspace` 模型与路由，不新开一套 trading-only CRUD。
- 交易运行时复用 `live_trading_manager.py`，通过 `TradingWorkspaceService` 做工作区级编排，不再新增独立 `TradingRuntimeManager`。
- 前端不在 `WorkspaceUnitsTab.vue` 上继续堆条件分支，而是新增 `TradingWorkspaceUnitsTab.vue` 承接交易表格和工具栏，公共弹窗继续复用。
- 首批上线只要求轮询闭环可用，WebSocket、自动交易、旧入口下线均不阻塞上线。

---

## 2. 执行原则

### 2.1 开发顺序原则

- 先扩展模型与接口，再接前端入口和页面骨架
- 先打通手动交易闭环，再做自动化能力
- 先保证模拟单元流程，再验证实盘安全路径
- 先保留旧入口，最后再考虑清理替换

### 2.2 协作原则

- 后端先提供稳定 Schema 和接口契约
- 前端优先复用策略研究组件，减少新建页面
- 测试从阶段3开始提前介入，避免最后集中补测
- 产品在阶段0冻结口径，阶段3参与验收闭环

### 2.3 完成定义

每个任务包完成时，至少满足：

- 代码可联调
- 关键场景可验证
- 有对应测试或验收结论
- 不破坏策略研究现有能力

---

## 3. 里程碑总览

| 里程碑 | 目标 | 预计工期 | 上线价值 |
|------|------|------|------|
| M0 | 范围冻结与接口口径确认 | 0.5天 | 防止范围膨胀 |
| M1 | 数据模型与基础接口可用 | 2天 | 为前端搭建提供稳定基础 |
| M2 | 新入口与工作区主流程可访问 | 2天 | 用户可看到新交易入口 |
| M3 | 手动交易闭环可联调 | 3-4天 | 达到首批上线门槛 |
| M4 | 研究互通与体验增强 | 2天 | 提升迁移和使用效率 |
| M5 | 自动交易与增强能力 | 2-3天 | 补齐 P1 |
| M6 | 旧入口下线与清理 | 1-2天 | 完成统一替换 |

---

## 4. 任务拆解

## 4.1 M0：范围冻结与接口口径确认

### 产品/架构任务

| ID | 任务 | 产出 | 依赖 |
|------|------|------|------|
| PM-001 | 冻结 P0/P1/P2 范围 | 范围清单 | 无 |
| PM-002 | 冻结首批上线验收口径 | 验收清单 | PM-001 |
| PM-003 | 冻结实盘安全规则 | 启动确认与校验规则 | PM-001 |
| ARC-001 | 确认 API 口径与字段模型 | 文档一致性 | PM-001 |

**完成标准：**

- 研发不再对 P0 范围存在歧义
- 自动交易不进入首批上线门槛
- 旧入口保留成为共识

---

## 4.2 M1：数据模型与基础接口

### 后端任务

| ID | 模块 | 任务 | 主要文件 | 优先级 |
|------|------|------|------|------|
| BE-101 | 数据模型 | Workspace 增加 `workspace_type`、`trading_config` | `app/models/workspace.py` | P0 |
| BE-102 | 数据模型 | StrategyUnit 增加 `trading_mode`、`gateway_config`、`lock_trading`、`lock_running`、`trading_instance_id`、`trading_snapshot` | `app/models/workspace.py` | P0 |
| BE-103 | 迁移 | 编写 Alembic 迁移脚本 | `alembic/versions/*` | P0 |
| BE-104 | Schema | 扩展 workspace 相关请求/响应 | `app/schemas/workspace.py` | P0 |
| BE-105 | Schema | 新建交易专属 Schema | `app/schemas/trading.py` | P0 |
| BE-106 | Service | 扩展工作区 CRUD，支持 trading 类型 | `app/services/workspace_service.py` | P0 |
| BE-107 | API | 工作区列表支持 `workspace_type` 过滤 | `app/api/workspace_api.py` | P0 |

### 前端任务

| ID | 模块 | 任务 | 主要文件 | 优先级 |
|------|------|------|------|------|
| FE-101 | 类型 | 扩展交易相关类型定义 | `src/frontend/src/types/workspace.ts` | P0 |
| FE-102 | API | 扩展 workspace API 适配交易字段 | `src/frontend/src/api/workspace.ts` | P0 |

### QA任务

| ID | 任务 | 类型 | 优先级 |
|------|------|------|------|
| QA-101 | 工作区 CRUD + 过滤测试 | 后端单测/集成 | P0 |
| QA-102 | 单元创建字段兼容性测试 | 后端单测 | P0 |
| QA-103 | 策略研究回归测试 | 回归 | P0 |

**完成标准：**

- 可创建 `trading` 工作区
- 可保存交易单元字段
- 策略研究功能不回归

---

## 4.3 M2：新入口与工作区主流程

### 前端任务

| ID | 模块 | 任务 | 主要文件 | 优先级 |
|------|------|------|------|------|
| FE-201 | 路由 | 新增 `/trading`、`/trading/:id` | `src/frontend/src/router/index.ts` | P0 |
| FE-202 | 布局 | 侧边栏新增“策略交易”入口 | `src/frontend/src/components/common/AppLayout.vue` | P0 |
| FE-203 | 列表页 | 复用工作区列表页，按 trading 过滤 | `views/workspace/WorkspaceListPage.vue` | P0 |
| FE-204 | 详情页 | 复用工作区详情页骨架 | `views/workspace/WorkspaceDetailPage.vue` | P0 |
| FE-205 | 新建单元 | 创建单元弹窗支持交易模式与网关 | `components/workspace/CreateUnitDialog.vue` | P0 |
| FE-206 | 网关选择 | 新建 `TradingGatewaySelect.vue` | `components/workspace/TradingGatewaySelect.vue` | P0 |

### 后端协同任务

| ID | 任务 | 说明 | 优先级 |
|------|------|------|------|
| BE-201 | 返回交易工作区详情字段 | 支撑页面渲染 | P0 |
| BE-202 | 返回网关预设所需数据 | 支撑实盘单元创建 | P0 |

### QA任务

| ID | 任务 | 类型 | 优先级 |
|------|------|------|------|
| QA-201 | 新入口可访问测试 | E2E | P0 |
| QA-202 | 创建交易工作区流程测试 | E2E | P0 |
| QA-203 | 创建模拟/实盘单元测试 | E2E | P0 |

**完成标准：**

- 用户可进入新入口
- 可创建交易工作区和交易单元
- 实盘单元需要网关配置

---

## 4.4 M3：手动交易闭环

### 后端任务

| ID | 模块 | 任务 | 主要文件 | 优先级 |
|------|------|------|------|------|
| BE-301 | 运行时 | 复用现有 `live_trading_manager.py`，不新增独立 TradingRuntimeManager | `app/services/live_trading_manager.py` | P0 |
| BE-302 | 编排 | 新建 `TradingWorkspaceService` | `app/services/trading_workspace_service.py` | P0 |
| BE-303 | API | 新增 `start/stop/status` 接口 | `app/api/workspace_api.py` | P0 |
| BE-304 | 集成 | `workspace_service.py` 按 `workspace_type` 分流到交易编排服务 | `app/services/workspace_service.py` | P0 |
| BE-305 | 模式 | `paper/live` 模式参数适配与网关校验 | `app/services/trading_workspace_service.py` | P0 |
| BE-306 | 快照 | 轮询刷新并持久化 `trading_snapshot` | `app/services/trading_workspace_service.py` | P0 |
| BE-307 | 安全 | 实盘启动前网关和参数校验 | 服务层 | P0 |

### 前端任务

| ID | 模块 | 任务 | 主要文件 | 优先级 |
|------|------|------|------|------|
| FE-301 | 单元列表 | 新建交易单元表格与工具栏，实现交易状态和交易字段列 | `components/workspace/TradingWorkspaceUnitsTab.vue` | P0 |
| FE-302 | Store | 新增 `fetchTradingStatus/startTrading/stopTrading` | `src/frontend/src/stores/workspace.ts` | P0 |
| FE-303 | 轮询 | 交易工作区轮询状态 | `WorkspaceDetailPage.vue` / store | P0 |
| FE-304 | 安全交互 | 实盘启动前弹出二次确认 | `TradingWorkspaceUnitsTab.vue` | P0 |
| FE-305 | 状态展示 | 盈亏、价格、涨跌幅格式化和着色 | `TradingWorkspaceUnitsTab.vue` | P0 |

### QA任务

| ID | 任务 | 类型 | 优先级 |
|------|------|------|------|
| QA-301 | 模拟单元启停测试 | 集成/E2E | P0 |
| QA-302 | 实盘单元启动前校验测试 | 集成/E2E | P0 |
| QA-303 | 状态轮询显示测试 | 组件/E2E | P0 |
| QA-304 | 页面刷新后快照恢复测试 | E2E | P0 |

**完成标准：**

- 模拟和实盘单元都能完成手动启停
- 关键状态字段可展示
- 实盘操作有确认与失败提示
- 阶段完成即可进入首批验收

---

## 4.5 M4：研究互通与体验增强

### 前后端任务

| ID | 模块 | 任务 | 主要文件 | 优先级 |
|------|------|------|------|------|
| BE-401 | 导入兼容 | 研究导出 JSON 导入交易时补默认字段 | 导入服务/接口 | P0 |
| BE-402 | 导出兼容 | 交易导出回流研究时忽略交易字段 | 导出服务/接口 | P0 |
| FE-401 | 工具栏整理 | 高频动作直出，低频动作收纳 | `WorkspaceUnitsTab.vue` | P0 |
| FE-402 | 字段布局 | 优化列顺序、默认显隐、横向滚动 | `WorkspaceUnitsTab.vue` | P0 |
| FE-403 | 错误提示 | 网关失败、状态失败、快照过期提示文案 | 页面与 store | P0 |

### QA任务

| ID | 任务 | 类型 | 优先级 |
|------|------|------|------|
| QA-401 | 研究→交易导入测试 | E2E | P0 |
| QA-402 | 交易→研究回流测试 | E2E | P0 |
| QA-403 | 工具栏可用性检查 | 走查/E2E | P0 |

**完成标准：**

- 研究与交易的互通路径可演示
- 工具栏不会压垮主操作体验
- 常见异常有明确反馈

---

## 4.6 M5：P1增强能力

### 后端任务

| ID | 模块 | 任务 | 主要文件 | 优先级 |
|------|------|------|------|------|
| BE-501 | 自动交易 | `GET/PUT auto-config` | `app/api/workspace_api.py` / service | P1 |
| BE-502 | 自动交易 | `GET auto-schedule` | service | P1 |
| BE-503 | 锁定 | `POST lock` | API/service | P1 |
| BE-504 | 头寸管理 | `GET positions` | service | P1 |
| BE-505 | 汇总 | 交易日汇总查询接口 | service/model | P1 |

### 前端任务

| ID | 模块 | 任务 | 主要文件 | 优先级 |
|------|------|------|------|------|
| FE-501 | 自动交易 | `AutoTradingConfigDialog.vue` | 新组件 | P1 |
| FE-502 | 锁定 | 锁定交易/运行/解锁按钮 | `WorkspaceUnitsTab.vue` | P1 |
| FE-503 | 头寸管理 | `PositionManagerDialog.vue` | 新组件 | P1 |
| FE-504 | 汇总展示 | 交易日汇总入口和展示 | 详情页/新组件 | P1 |

**执行补充：**

- `FE-501` 已按复用策略落地到 `components/workspace/AutoTradingConfigDialog.vue`，并接入 `TradingWorkspaceUnitsTab.vue`。
- `FE-502`、`FE-503` 已在交易工作区主表工具栏中交付。
- `FE-504` 已通过交易工作区“交易日统计选项”对话框落地基础版展示。

### QA任务

| ID | 任务 | 类型 | 优先级 |
|------|------|------|------|
| QA-501 | 自动交易配置测试 | 组件/集成 | P1 |
| QA-502 | 锁定逻辑测试 | 集成 | P1 |
| QA-503 | 头寸聚合测试 | 组件/集成 | P1 |

---

## 4.7 M6：旧入口下线与清理

### 前后端任务

| ID | 模块 | 任务 | 主要文件 | 优先级 |
|------|------|------|------|------|
| FE-601 | 路由清理 | 删除 `/simulate`、`/live-trading` 路由 | `router/index.ts` | P2 |
| FE-602 | 页面清理 | 删除旧页面与残留引用 | `views/*` | P2 |
| FE-603 | 菜单清理 | 移除旧侧边栏入口 | `AppLayout.vue` | P2 |
| BE-601 | 引用清理 | 清理旧接口残留引用 | API/service | P2 |
| QA-601 | 回归检查 | 死链、菜单、测试清理验证 | 回归 | P2 |

**前置条件：**

- 新入口通过业务验收
- P0/P1 阻断缺陷已关闭
- 确认具备回退能力或保留旧分支

**执行补充：**

- 旧菜单入口已移除，`/simulate` 与 `/live-trading` 前端路由改为兼容重定向到 `/trading`。
- 旧前端页面与页面级测试已清理，统一入口完成收口。

---

## 5. 推荐并行方式

### 5.1 可并行任务

- `BE-101 ~ BE-107` 可与 `FE-101 ~ FE-102` 并行
- `FE-201 ~ FE-206` 可在基础字段稳定后推进
- `BE-301 ~ BE-307` 与 `FE-301 ~ FE-305` 可以接口联调方式并行
- QA 可从 M2 开始预写用例，M3 起介入联调

### 5.2 不建议并行的事项

- 不要在 M3 未稳定前推进旧入口删除
- 不要在实盘安全规则未冻结前推进批量自动交易
- 不要在导入导出兼容未验证前宣称研究与交易完全打通

---

## 6. 联调优先级

### 第一优先级

- 创建交易工作区
- 创建模拟/实盘单元
- 手动启动/停止单元
- 状态轮询与快照恢复

### 第二优先级

- 研究→交易导入导出
- 工具栏体验优化
- 错误提示完善

### 第三优先级

- 自动交易
- 锁定逻辑
- 头寸管理器
- 交易日汇总

---

## 7. 建议排期

### 紧凑版

- M0 + M1 + M2 + M3 + M4
- 约 `9.5-10天`
- 适合先上线 MVP

### 完整版

- 紧凑版基础上增加 M5 + M6
- 约 `13-15天`
- 适合资源更充分、希望一轮做完替换

---

## 8. 最终建议

如果团队当前目标是**尽快让迭代127形成可上线版本**，建议先按以下顺序执行：

1. `M0` 范围冻结
2. `M1` 模型与接口打底
3. `M2` 新入口搭建
4. `M3` 手动交易闭环
5. `M4` 研究互通与体验增强

如果团队当前目标是**本轮尽量做完统一替换**，则在上述基础上继续推进：

6. `M5` 自动交易与增强能力
7. `M6` 旧入口下线与清理

本方案的核心不是把任务拆得更碎，而是让每个阶段都能清楚回答一个问题：

**这一阶段完成后，产品离“可上线”又近了多少。**
