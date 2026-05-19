# Source Tree Analysis

> Generated: 2026-02-24 | Scan Level: Deep

## Project Structure Overview

**Repository Type**: Multi-part (Frontend + Backend)
**Primary Languages**: Python 3.9+ / TypeScript
**Architecture**: Layered REST API + SPA

```
backtrader_web/
├── src/                          # 源代码根目录
│   ├── backend/                  # FastAPI 后端 (Part: backend)
│   │   ├── app/
│   │   │   ├── main.py           # ⚡ FastAPI 应用入口
│   │   │   ├── config.py         # 环境配置管理 (Settings)
│   │   │   ├── websocket_manager.py  # WebSocket 连接管理
│   │   │   │
│   │   │   ├── api/              # 🔌 API 路由层 (15 模块)
│   │   │   │   ├── router.py     # ⚡ 路由注册中心
│   │   │   │   ├── deps.py       # 依赖注入 (get_current_user)
│   │   │   │   ├── deps_permissions.py  # RBAC 权限依赖
│   │   │   │   ├── auth.py       # 认证 API (register/login/refresh)
│   │   │   │   ├── backtest.py   # 回测 API (run/status/list/cancel)
│   │   │   │   ├── backtest_enhanced.py  # 增强回测 (优化/报告导出/WS)
│   │   │   │   ├── strategy.py   # 策略管理 (CRUD/模板)
│   │   │   │   ├── optimization_api.py  # 参数优化 (提交/进度/结果)
│   │   │   │   ├── live_trading_api.py  # 实盘交易 (启停/订单/持仓)
│   │   │   │   ├── portfolio_api.py     # 投资组合 (概览/持仓/曲线)
│   │   │   │   ├── analytics.py  # 分析统计 (dashboard/performance)
│   │   │   │   ├── comparison.py # 回测对比
│   │   │   │   ├── paper_trading.py     # 模拟交易
│   │   │   │   ├── data.py       # 市场数据查询
│   │   │   │   ├── strategy_version.py  # 策略版本控制
│   │   │   │   ├── realtime_data.py     # 实时行情 WS
│   │   │   │   ├── monitoring.py # 监控告警
│   │   │   │   └── live_trading.py      # 加密货币交易 (CCXT)
│   │   │   │
│   │   │   ├── services/         # 🧠 业务逻辑层 (18 模块)
│   │   │   │   ├── auth_service.py       # 认证服务 (JWT/刷新令牌)
│   │   │   │   ├── backtest_service.py   # ⚡ 回测引擎服务 (核心)
│   │   │   │   ├── backtest_analyzers.py # FincoreAdapter 指标适配器
│   │   │   │   ├── fincore_metrics_helper.py # fincore 指标辅助
│   │   │   │   ├── strategy_service.py   # 策略 CRUD + 模板扫描
│   │   │   │   ├── optimization_service.py   # 贝叶斯/网格优化
│   │   │   │   ├── param_optimization_service.py # 参数网格生成
│   │   │   │   ├── live_trading_manager.py   # 实盘实例管理
│   │   │   │   ├── live_trading_service.py   # 实盘交易执行
│   │   │   │   ├── paper_trading_service.py  # 模拟交易服务
│   │   │   │   ├── analytics_service.py  # 分析统计服务
│   │   │   │   ├── comparison_service.py # 对比分析服务
│   │   │   │   ├── report_service.py     # 报告生成 (HTML/PDF/Excel)
│   │   │   │   ├── monitoring_service.py # 监控告警服务
│   │   │   │   ├── realtime_data_service.py  # 实时数据服务
│   │   │   │   ├── log_parser_service.py # 日志解析服务
│   │   │   │   └── strategy_version_service.py # 版本控制服务
│   │   │   │
│   │   │   ├── schemas/          # 📋 Pydantic 模型 (13 文件)
│   │   │   │   ├── auth.py       # UserCreate/Login/Token
│   │   │   │   ├── backtest.py   # BacktestRequest/Result
│   │   │   │   ├── strategy.py   # StrategyCreate/Response
│   │   │   │   └── ...
│   │   │   │
│   │   │   ├── models/           # 🗄️ SQLAlchemy ORM 模型
│   │   │   │   └── ...
│   │   │   │
│   │   │   ├── db/               # 数据库配置
│   │   │   │   ├── database.py   # 引擎/会话/初始化
│   │   │   │   └── ...
│   │   │   │
│   │   │   ├── middleware/       # 中间件
│   │   │   │   ├── logging.py    # 日志/审计/性能中间件
│   │   │   │   ├── exception_handling.py # 全局异常处理
│   │   │   │   └── security_headers.py   # 安全头
│   │   │   │
│   │   │   └── utils/            # 工具
│   │   │       ├── logger.py     # 结构化日志器
│   │   │       └── ...
│   │   │
│   │   └── tests/                # 后端测试 (40+ 文件)
│   │       ├── test_auth.py
│   │       ├── test_backtest.py
│   │       ├── test_data_api.py
│   │       └── ...
│   │
│   └── frontend/                 # Vue 3 前端 (Part: frontend)
│       ├── package.json          # Node 依赖
│       ├── vite.config.ts        # Vite 构建配置
│       ├── tsconfig.json         # TypeScript 配置
│       ├── playwright.config.ts  # Playwright E2E 配置
│       │
│       ├── src/
│       │   ├── main.ts           # ⚡ Vue 应用入口
│       │   ├── App.vue           # 根组件
│       │   │
│       │   ├── router/           # 🔀 路由 (12 路由)
│       │   │   └── index.ts      # Vue Router 定义 + 守卫
│       │   │
│       │   ├── views/            # 📄 页面组件 (12 页面)
│       │   │   ├── LoginPage.vue
│       │   │   ├── RegisterPage.vue
│       │   │   ├── Dashboard.vue
│       │   │   ├── BacktestPage.vue
│       │   │   ├── BacktestResultPage.vue
│       │   │   ├── OptimizationPage.vue
│       │   │   ├── StrategyPage.vue
│       │   │   ├── DataPage.vue
│       │   │   ├── LiveTradingPage.vue
│       │   │   ├── LiveTradingDetailPage.vue
│       │   │   ├── PortfolioPage.vue
│       │   │   └── SettingsPage.vue
│       │   │
│       │   ├── stores/           # 🏪 Pinia 状态管理
│       │   │   ├── auth.ts       # 认证状态 (token/user)
│       │   │   └── ...
│       │   │
│       │   ├── api/              # 🔌 API 客户端
│       │   │   ├── auth.ts       # → /api/v1/auth/*
│       │   │   ├── backtest.ts   # → /api/v1/backtest/*
│       │   │   └── ...
│       │   │
│       │   ├── components/       # 🧩 可复用组件
│       │   │   ├── common/       # 通用 (AppLayout)
│       │   │   └── ...
│       │   │
│       │   ├── types/            # TypeScript 类型定义
│       │   └── test/             # 前端单元测试 (Vitest)
│       │
│       └── e2e/                  # 🧪 E2E 测试 (Playwright TS)
│           └── tests/
│               ├── auth.spec.ts
│               ├── backtest.spec.ts
│               ├── strategy.spec.ts
│               ├── portfolio.spec.ts
│               ├── live-trading.spec.ts
│               ├── basic.spec.ts
│               └── smoke.spec.ts
│
├── strategies/                   # 📊 策略模板库 (118+ 策略)
│   ├── 001_simple_ma/
│   │   ├── config.yaml           # 策略配置
│   │   └── strategy_simple_ma.py # 策略代码
│   ├── 002_dual_ma/
│   └── ...
│
├── tests/                        # 🧪 项目级测试
│   ├── e2e/                      # Python E2E 测试 (Playwright pytest)
│   │   ├── conftest.py           # 共享 fixtures
│   │   ├── test_auth.py
│   │   ├── test_backtest.py
│   │   ├── test_dashboard.py
│   │   ├── test_data.py
│   │   ├── test_strategy.py
│   │   └── test_settings.py
│   └── test_backtest_e2e.py      # 独立回测 E2E 脚本
│
├── docs/                         # 📖 项目文档 (28+ 核心文档)
│   ├── INDEX.md                  # 文档索引
│   ├── TECHNICAL_DOCS.md         # 综合技术文档
│   └── ...
│
├── scripts/                      # 🔧 工具脚本
├── data/                         # 数据目录
├── datas/                        # 历史数据文件
├── logs/                         # 日志目录
├── .github/                      # GitHub Actions
└── _bmad/                        # BMAD 工作流系统
```

## Integration Points

```
Frontend (Vue 3)  ──HTTP/REST──→  Backend (FastAPI)
     │                                 │
     │  POST /api/v1/auth/login        │
     │  GET  /api/v1/backtest/         │──→ SQLAlchemy → DB
     │  POST /api/v1/backtest/run      │──→ BacktestService → Backtrader Engine
     │  GET  /api/v1/strategy/         │──→ StrategyService → strategies/ dir
     │  WS   /api/v1/backtests/ws/     │──→ WebSocketManager
     │  GET  /api/v1/data/query        │──→ AkShare (external)
     │                                 │
     └──WebSocket──→  实时数据推送      │──→ CCXT/CTP (external brokers)
```

## Critical Entry Points

| Entry Point | Path | Purpose |
|-------------|------|---------|
| Backend | `src/backend/app/main.py` | FastAPI app with lifespan |
| Frontend | `src/frontend/src/main.ts` | Vue 3 app bootstrap |
| Router Registry | `src/backend/app/api/router.py` | All API routes |
| Vue Router | `src/frontend/src/router/index.ts` | All frontend routes |
| Strategy Scanner | `src/backend/app/services/strategy_service.py` | Auto-loads 118+ strategies |
| Backtest Engine | `src/backend/app/services/backtest_service.py` | Core backtest execution |
