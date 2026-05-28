# Backtrader Web 敏捷开发文档

> 基于迭代100需求，按照行业最佳实践构建的敏捷开发文档

---

## 1. 产品愿景 (Product Vision)

### 1.1 愿景陈述

**为** 量化交易开发者和研究人员  
**提供** 一个现代化的Web回测平台  
**它** 基于backtrader引擎，提供直观的可视化界面和API服务  
**不同于** 传统命令行回测工具  
**我们的产品** 让策略开发、回测、分析和部署更加便捷高效

### 1.2 产品目标

| 目标 | 关键结果 (KR) | 优先级 |
|------|--------------|--------|
| 易用性 | 5分钟内完成首次回测 | P0 |
| 可视化 | 专业K线图+10+分析图表 | P0 |
| 性能 | 10年日线回测<5秒 | P1 |
| 可扩展 | 支持自定义策略热加载 | P1 |
| API化 | RESTful API 100%覆盖 | P1 |

### 1.3 目标用户画像

| 用户类型 | 特征 | 核心需求 |
|---------|------|---------|
| **量化新手** | Python基础，无Web开发经验 | 开箱即用，可视化操作 |
| **策略研究员** | 熟悉backtrader，需要快速验证 | 批量回测，参数优化 |
| **量化开发者** | 需要集成到现有系统 | API接口，可编程 |
| **团队管理者** | 需要查看团队策略表现 | 多用户，权限管理 |

---

## 2. 产品待办列表 (Product Backlog)

### 2.1 Epic列表

| Epic ID | Epic名称 | 描述 | 优先级 |
|---------|---------|------|--------|
| E1 | 后端基础架构 | FastAPI + 数据库 + 认证 | P0 |
| E2 | 回测核心服务 | Backtrader集成 + 任务管理 | P0 |
| E3 | 前端框架搭建 | Vue3 + 路由 + 状态管理 | P0 |
| E4 | 可视化图表 | Echarts K线 + 分析图表 | P0 |
| E5 | 策略管理 | CRUD + 配置 + 版本 | P1 |
| E6 | 用户系统 | 注册登录 + 权限 | P1 |
| E7 | 数据管理 | 行情数据 + 导入导出 | P2 |
| E8 | 参数优化 | 网格搜索 + 遗传算法 | P2 |

### 2.2 用户故事 (User Stories)

#### Epic 1: 后端基础架构

```
US-1.1 项目初始化
作为 开发者
我想要 一个标准的FastAPI项目结构
以便 快速开始开发

验收标准:
- [ ] FastAPI项目可启动，访问/docs看到Swagger文档
- [ ] 目录结构符合规范 (app/api, app/services, app/db, app/schemas)
- [ ] .env配置加载正常
- [ ] 日志系统配置完成 (loguru)

故事点: 3
```

```
US-1.2 数据库抽象层
作为 开发者
我想要 统一的数据库接口
以便 通过环境变量切换不同数据库

验收标准:
- [ ] 支持SQLite/PostgreSQL/MySQL/MongoDB
- [ ] DATABASE_TYPE环境变量控制数据库类型
- [ ] Repository模式实现CRUD
- [ ] SQLite模式零配置可运行

故事点: 5
```

```
US-1.3 用户认证
作为 用户
我想要 注册和登录功能
以便 保护我的策略和回测数据

验收标准:
- [ ] POST /api/auth/register 注册接口
- [ ] POST /api/auth/login 登录接口，返回JWT
- [ ] JWT中间件验证
- [ ] 密码bcrypt加密存储

故事点: 5
```

#### Epic 2: 回测核心服务

```
US-2.1 回测API
作为 用户
我想要 通过API运行回测
以便 程序化调用回测服务

验收标准:
- [ ] POST /api/backtest/run 提交回测任务
- [ ] GET /api/backtest/{id} 查询回测状态和结果
- [ ] GET /api/backtest/list 列出历史回测
- [ ] 返回数据包含：收益率、夏普、最大回撤、交易列表

故事点: 8
```

```
US-2.2 回测结果存储
作为 用户
我想要 回测结果持久化
以便 后续查看和对比

验收标准:
- [ ] 回测结果存储到数据库
- [ ] 包含：参数、指标、交易记录、资金曲线
- [ ] 支持按时间/策略/收益排序查询
- [ ] 支持删除历史回测

故事点: 5
```

```
US-2.3 异步回测任务
作为 用户
我想要 长时间回测异步执行
以便 不阻塞界面操作

验收标准:
- [ ] 回测任务后台执行
- [ ] 返回task_id，可轮询状态
- [ ] 支持取消运行中的任务
- [ ] (可选) WebSocket推送进度

故事点: 5
```

#### Epic 3: 前端框架搭建

```
US-3.1 Vue3项目初始化
作为 前端开发者
我想要 标准的Vue3项目结构
以便 快速开始前端开发

验收标准:
- [ ] Vite + Vue3 + TypeScript项目可运行
- [ ] Vue Router路由配置
- [ ] Pinia状态管理
- [ ] Element Plus组件库集成
- [ ] Axios HTTP封装

故事点: 3
```

```
US-3.2 布局框架
作为 用户
我想要 清晰的页面布局
以便 快速找到功能入口

验收标准:
- [ ] 侧边栏导航菜单
- [ ] 顶部Header (用户信息、设置)
- [ ] 响应式布局 (支持1280px+)
- [ ] 暗色/亮色主题切换

故事点: 3
```

```
US-3.3 登录页面
作为 用户
我想要 登录和注册界面
以便 访问系统

验收标准:
- [ ] 登录表单 (用户名/密码)
- [ ] 注册表单 (用户名/邮箱/密码)
- [ ] 表单验证
- [ ] 登录后跳转Dashboard
- [ ] Token存储到localStorage

故事点: 3
```

#### Epic 4: 可视化图表

```
US-4.1 K线图组件
作为 用户
我想要 专业的K线图
以便 分析行情走势

验收标准:
- [ ] 标准K线显示 (OHLC)
- [ ] MA均线叠加 (可配置周期)
- [ ] 成交量柱状图
- [ ] DataZoom缩放
- [ ] 十字线联动
- [ ] Tooltip详情

故事点: 8
```

```
US-4.2 资金曲线图
作为 用户
我想要 查看回测资金曲线
以便 了解策略收益变化

验收标准:
- [ ] 资金曲线折线图
- [ ] 基准对比线 (可选)
- [ ] 回撤区域阴影
- [ ] 买卖点标记

故事点: 5
```

```
US-4.3 回测统计面板
作为 用户
我想要 回测关键指标展示
以便 快速评估策略表现

验收标准:
- [ ] 总收益率、年化收益
- [ ] 夏普比率、索提诺比率
- [ ] 最大回撤、回撤周期
- [ ] 胜率、盈亏比
- [ ] 交易次数、持仓时间

故事点: 3
```

#### Epic 5: 策略管理

```
US-5.1 策略列表
作为 用户
我想要 查看我的策略列表
以便 管理和选择策略

验收标准:
- [ ] 策略列表页面
- [ ] 显示：名称、描述、创建时间、最近回测
- [ ] 支持搜索和筛选
- [ ] 支持删除策略

故事点: 3
```

```
US-5.2 策略创建
作为 用户
我想要 通过界面创建策略
以便 快速定义交易规则

验收标准:
- [ ] 策略代码编辑器 (Monaco Editor)
- [ ] Python语法高亮
- [ ] 策略模板选择
- [ ] 参数配置表单
- [ ] 代码校验

故事点: 5
```

```
US-5.3 YAML策略配置
作为 用户
我想要 通过YAML配置策略参数
以便 无需修改代码调整参数

验收标准:
- [ ] YAML配置解析
- [ ] 参数类型验证 (int/float/string/enum)
- [ ] 参数范围限制 (min/max)
- [ ] 配置热加载

故事点: 5
```

---

## 3. Sprint规划

### 3.1 Sprint概览

| Sprint | 周期 | 目标 | 核心交付 |
|--------|------|------|---------|
| Sprint 1 | Week 1-2 | 后端基础 | FastAPI框架 + 数据库层 |
| Sprint 2 | Week 3-4 | 回测服务 | 回测API + 结果存储 |
| Sprint 3 | Week 5-6 | 前端基础 | Vue3框架 + 登录 |
| Sprint 4 | Week 7-8 | 图表组件 | K线图 + 资金曲线 |
| Sprint 5 | Week 9-10 | 核心页面 | 回测页面 + Dashboard |
| Sprint 6 | Week 11-12 | 策略管理 | 策略CRUD + 配置 |

### 3.2 Sprint 1 详细规划

**Sprint目标**: 搭建后端基础架构，实现数据库抽象层

**Sprint Backlog**:

| 任务ID | 任务描述 | 故事点 | 负责人 | 状态 |
|--------|---------|--------|--------|------|
| T1.1 | FastAPI项目脚手架 | 2 | - | Todo |
| T1.2 | 目录结构规范 | 1 | - | Todo |
| T1.3 | 配置管理 (.env + pydantic-settings) | 2 | - | Todo |
| T1.4 | 日志系统 (loguru) | 1 | - | Todo |
| T1.5 | Repository基类定义 | 2 | - | Todo |
| T1.6 | SQLRepository实现 | 3 | - | Todo |
| T1.7 | MongoRepository实现 | 3 | - | Todo |
| T1.8 | 数据库工厂 | 2 | - | Todo |
| T1.9 | 用户模型定义 | 2 | - | Todo |
| T1.10 | 注册/登录API | 3 | - | Todo |
| T1.11 | JWT中间件 | 2 | - | Todo |
| T1.12 | 单元测试 | 3 | - | Todo |

**Sprint容量**: 26 故事点

**每日站会问题**:
1. 昨天完成了什么？
2. 今天计划做什么？
3. 有什么阻碍？

### 3.3 Sprint 2 详细规划

**Sprint目标**: 实现回测核心服务

**Sprint Backlog**:

| 任务ID | 任务描述 | 故事点 | 状态 |
|--------|---------|--------|------|
| T2.1 | BacktestService封装 | 5 | Todo |
| T2.2 | Backtest API路由 | 3 | Todo |
| T2.3 | 回测请求/响应Schema | 2 | Todo |
| T2.4 | 回测结果模型 | 2 | Todo |
| T2.5 | 回测结果Repository | 3 | Todo |
| T2.6 | 异步任务框架 (可选Celery或asyncio) | 5 | Todo |
| T2.7 | 任务状态管理 | 3 | Todo |
| T2.8 | 策略动态加载 | 3 | Todo |
| T2.9 | 集成测试 | 3 | Todo |

**Sprint容量**: 29 故事点

---

## 4. Definition of Done (DoD)

### 4.1 代码完成标准

- [ ] 代码通过所有lint检查 (ruff/eslint)
- [ ] 单元测试覆盖率 > 80%
- [ ] 无新增的安全漏洞
- [ ] 代码已Review并合并到main分支
- [ ] 相关文档已更新

### 4.2 功能完成标准

- [ ] 满足用户故事的所有验收标准
- [ ] 在开发环境验证通过
- [ ] 无已知Bug (或已记录到Issue)
- [ ] 性能满足要求

### 4.3 Sprint完成标准

- [ ] 所有计划的用户故事已完成
- [ ] Sprint Review会议已召开
- [ ] Sprint回顾总结已记录
- [ ] 待办列表已更新

---

## 5. 技术架构

### 5.1 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     前端 (Vue3 SPA)                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │Dashboard │ │ Backtest │ │ Strategy │ │ Settings │       │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │
│       └────────────┴────────────┴────────────┘              │
│                         │ Axios                             │
└─────────────────────────┼───────────────────────────────────┘
                          │ HTTP/WebSocket
┌─────────────────────────┼───────────────────────────────────┐
│                     后端 (FastAPI)                           │
│  ┌──────────────────────┴──────────────────────┐            │
│  │                API Router                    │            │
│  │  /api/auth  /api/backtest  /api/strategy    │            │
│  └──────────────────────┬──────────────────────┘            │
│                         │                                    │
│  ┌──────────────────────┴──────────────────────┐            │
│  │              Service Layer                   │            │
│  │  AuthService  BacktestService  StrategyService│           │
│  └──────────────────────┬──────────────────────┘            │
│                         │                                    │
│  ┌──────────────────────┴──────────────────────┐            │
│  │              Repository Layer                │            │
│  │  UserRepo  BacktestRepo  StrategyRepo       │            │
│  └──────────────────────┬──────────────────────┘            │
└─────────────────────────┼───────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────┐
│                     数据层                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │ SQLite/  │ │ MongoDB  │ │  Redis   │                    │
│  │ PG/MySQL │ │ (可选)   │ │ (可选)   │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 项目目录结构

```
backtrader_web/
├── backend/                      # 后端项目
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI入口
│   │   ├── config.py            # 配置管理
│   │   ├── api/                 # API路由
│   │   │   ├── __init__.py
│   │   │   ├── router.py        # 路由汇总
│   │   │   ├── auth.py          # 认证API
│   │   │   ├── backtest.py      # 回测API
│   │   │   └── strategy.py      # 策略API
│   │   ├── services/            # 业务逻辑
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── backtest_service.py
│   │   │   └── strategy_service.py
│   │   ├── db/                  # 数据库层
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # Repository基类
│   │   │   ├── sql_repository.py
│   │   │   ├── mongo_repository.py
│   │   │   └── factory.py       # 数据库工厂
│   │   ├── models/              # ORM模型
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── backtest.py
│   │   │   └── strategy.py
│   │   ├── schemas/             # Pydantic模型
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── backtest.py
│   │   │   └── strategy.py
│   │   └── utils/               # 工具函数
│   │       ├── __init__.py
│   │       ├── security.py      # JWT/密码
│   │       └── logger.py        # 日志
│   ├── tests/                   # 测试
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   └── test_backtest.py
│   ├── strategies/              # 内置策略
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── ma_cross.py
│   │   └── rsi.py
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/                    # 前端项目
│   ├── src/
│   │   ├── api/                 # API调用
│   │   │   ├── index.ts
│   │   │   ├── auth.ts
│   │   │   ├── backtest.ts
│   │   │   └── strategy.ts
│   │   ├── components/          # 组件
│   │   │   ├── charts/          # 图表组件
│   │   │   │   ├── KlineChart.vue
│   │   │   │   ├── EquityCurve.vue
│   │   │   │   └── StatsPanel.vue
│   │   │   ├── common/          # 通用组件
│   │   │   │   ├── AppHeader.vue
│   │   │   │   └── AppSidebar.vue
│   │   │   └── form/            # 表单组件
│   │   │       └── BacktestForm.vue
│   │   ├── views/               # 页面
│   │   │   ├── Dashboard.vue
│   │   │   ├── BacktestPage.vue
│   │   │   ├── StrategyPage.vue
│   │   │   ├── LoginPage.vue
│   │   │   └── RegisterPage.vue
│   │   ├── stores/              # Pinia状态
│   │   │   ├── auth.ts
│   │   │   ├── backtest.ts
│   │   │   └── strategy.ts
│   │   ├── router/
│   │   │   └── index.ts
│   │   ├── types/               # 类型定义
│   │   │   └── index.d.ts
│   │   ├── App.vue
│   │   └── main.ts
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── tailwind.config.js
│
├── docs/                        # 文档
│   ├── AGILE_DEVELOPMENT.md     # 本文档
│   ├── API.md                   # API文档
│   └── DEPLOYMENT.md            # 部署文档
│
├── .gitignore
├── README.md
└── LICENSE
```

### 5.3 技术栈清单

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **前端** | Vue | 3.4+ | UI框架 |
| | TypeScript | 5.0+ | 类型安全 |
| | Vite | 5.0+ | 构建工具 |
| | Pinia | 2.1+ | 状态管理 |
| | Vue Router | 4.2+ | 路由 |
| | Element Plus | 2.4+ | UI组件 |
| | Echarts | 5.4+ | 图表 |
| | Axios | 1.6+ | HTTP |
| | TailwindCSS | 3.4+ | 样式 |
| **后端** | Python | 3.10+ | 运行时 |
| | FastAPI | 0.109+ | Web框架 |
| | Uvicorn | 0.27+ | ASGI服务 |
| | Pydantic | 2.5+ | 数据验证 |
| | SQLAlchemy | 2.0+ | ORM |
| | Backtrader | 1.9+ | 回测引擎 |
| | Loguru | 0.7+ | 日志 |
| | python-jose | 3.3+ | JWT |
| | Passlib | 1.7+ | 密码 |
| **数据库** | SQLite | 3.40+ | 默认存储 |
| | PostgreSQL | 15+ | 可选 |
| | MySQL | 8.0+ | 可选 |
| | MongoDB | 7.0+ | 可选 |
| **测试** | Pytest | 7.4+ | 后端测试 |
| | Vitest | 1.2+ | 前端测试 |

---

## 6. 开发规范

### 6.1 Git工作流

```
main ──────●────────●────────●──────────── 稳定版本
            \      /          \
develop ─────●────●────●───────●─────────● 开发分支
              \  /      \     /
feature ───────●─────────●───●            功能分支
```

**分支命名**:
- `feature/US-1.1-project-init`
- `bugfix/issue-123`
- `hotfix/security-patch`

**Commit规范**:
```
<type>(<scope>): <subject>

type: feat|fix|docs|style|refactor|test|chore
scope: api|db|ui|auth|backtest|strategy
```

示例:
```
feat(api): add backtest run endpoint
fix(db): fix connection pool leak
docs(readme): update installation guide
```

### 6.2 代码规范

**Python (后端)**:
- 使用 `ruff` 进行lint和format
- 类型注解必须
- docstring使用Google风格

```python
def run_backtest(
    strategy_id: str,
    params: BacktestParams,
) -> BacktestResult:
    """Run backtest with given strategy and parameters.
    
    Args:
        strategy_id: Strategy identifier.
        params: Backtest parameters including date range and capital.
    
    Returns:
        BacktestResult containing metrics and trades.
    
    Raises:
        StrategyNotFoundError: If strategy_id doesn't exist.
    """
    ...
```

**TypeScript (前端)**:
- 使用 `eslint` + `prettier`
- 组件使用 `<script setup>` 语法
- Props/Emits必须类型定义

```vue
<script setup lang="ts">
interface Props {
  data: KlineData
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  height: 400,
})

const emit = defineEmits<{
  (e: 'range-change', range: DateRange): void
}>()
</script>
```

### 6.3 API设计规范

**RESTful原则**:
```
GET    /api/backtests          # 列表
POST   /api/backtests          # 创建
GET    /api/backtests/{id}     # 详情
PUT    /api/backtests/{id}     # 更新
DELETE /api/backtests/{id}     # 删除
```

**响应格式**:
```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

**错误响应**:
```json
{
  "code": 40001,
  "message": "Invalid parameters",
  "detail": "start_date must be before end_date"
}
```

---

## 7. 环境配置

### 7.1 开发环境

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

### 7.2 环境变量 (.env)

```bash
# 应用配置
APP_NAME=backtrader_web
DEBUG=true
SECRET_KEY=your-secret-key-change-in-production

# 数据库配置 (二选一)
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite:///./backtrader.db

# DATABASE_TYPE=postgresql
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader

# 可选: Redis缓存
# REDIS_URL=redis://localhost:6379/0

# JWT配置
JWT_SECRET_KEY=your-jwt-secret
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
```

---

## 8. 里程碑计划

```
Week 1-2:   Sprint 1 - 后端基础 ████████░░░░░░░░░░░░
Week 3-4:   Sprint 2 - 回测服务 ████████░░░░░░░░░░░░
Week 5-6:   Sprint 3 - 前端基础 ████████░░░░░░░░░░░░
Week 7-8:   Sprint 4 - 图表组件 ████████░░░░░░░░░░░░
Week 9-10:  Sprint 5 - 核心页面 ████████░░░░░░░░░░░░
Week 11-12: Sprint 6 - 策略管理 ████████░░░░░░░░░░░░
────────────────────────────────────────────────────
MVP交付: Week 12 (约3个月)
```

### 里程碑检查点

| 里程碑 | 时间 | 交付物 | 验收标准 |
|--------|------|--------|---------|
| M1 | Week 4 | 后端可用 | API可调用，数据库可存储 |
| M2 | Week 8 | 前端可用 | 登录+K线图展示 |
| M3 | Week 12 | MVP发布 | 完整回测流程可用 |

---

## 9. 风险管理

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Backtrader集成复杂 | 中 | 高 | 提前调研，保留降级方案 |
| 前端图表性能问题 | 中 | 中 | 使用虚拟滚动，分片加载 |
| 数据库切换问题 | 低 | 中 | 充分测试Repository层 |
| 进度延期 | 中 | 中 | 预留20%缓冲时间 |

---

## 10. 附录

### 10.1 参考项目

- [stock-backtrader-web-app](https://github.com/xxx) - 原型参考
- [backtrader](https://github.com/mementum/backtrader) - 回测引擎
- [FastAPI最佳实践](https://github.com/zhanymkanov/fastapi-best-practices)
- [Vue3企业级项目模板](https://github.com/vbenjs/vue-vben-admin)

### 10.2 术语表

| 术语 | 说明 |
|------|------|
| Cerebro | Backtrader核心引擎类 |
| Strategy | 交易策略类 |
| Analyzer | 回测分析器 |
| Feed | 数据源 |
| Broker | 模拟经纪商 |
| OHLCV | 开盘/最高/最低/收盘/成交量 |
| Sharpe Ratio | 夏普比率 |
| Max Drawdown | 最大回撤 |

---

*文档版本: v1.0*  
*最后更新: 2026-01-09*
