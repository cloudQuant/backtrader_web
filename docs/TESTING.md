# 测试指南

本文档介绍 Backtrader Web 项目的测试策略、测试框架和运行方法。

## 测试架构概览

```
测试层级
├── 单元测试 (Unit Tests)          — pytest, 后端服务/模型/工具
├── API 集成测试 (Integration)     — pytest + httpx, FastAPI 路由
├── 前端单元测试 (Frontend Unit)   — Vitest, Vue 组件/Store
├── E2E 测试 (End-to-End)         — Playwright, 浏览器全流程
└── 策略加载测试 (Strategy Load)   — pytest, 动态策略加载验证
```

## 1. 后端测试

### 1.1 测试文件位置

```
src/backend/tests/
├── test_auth.py                    # 认证服务测试
├── test_backtest.py                # 回测 API 测试
├── test_backtest_service.py        # 回测服务层测试
├── test_backtest_analyzers.py      # 分析器/指标测试
├── test_fincore_adapter.py         # fincore 适配器测试
├── test_fincore_advanced_metrics.py # fincore 高级指标
├── test_strategy_service.py        # 策略服务测试
├── test_comparison.py              # 回测对比测试
├── test_cache.py                   # 缓存测试
├── test_config.py                  # 配置测试
├── test_db.py                      # 数据库测试
├── test_deps.py                    # 依赖注入测试
├── test_factory.py                 # 工厂模式测试
├── test_input_validation.py        # 输入验证测试
├── test_enhanced_logger.py         # 日志测试
└── ... (40+ 测试文件)
```

### 1.2 运行后端测试

```bash
# 运行所有后端测试
cd src/backend
python -m pytest tests/ -v

# 运行特定测试文件
python -m pytest tests/test_auth.py -v

# 运行特定测试函数
python -m pytest tests/test_auth.py::test_login_success -v

# 带覆盖率报告
python -m pytest tests/ --cov=app --cov-report=html

# 只运行快速测试（跳过慢速集成测试）
python -m pytest tests/ -v -m "not slow"
```

### 1.3 测试覆盖率

当前后端测试覆盖率目标：

| 模块 | 目标覆盖率 | 当前状态 |
|------|-----------|---------|
| `app/api/` | 80%+ | ✅ |
| `app/services/` | 85%+ | ✅ |
| `app/schemas/` | 90%+ | ✅ |
| `app/utils/` | 75%+ | ✅ |
| `app/middleware/` | 70%+ | ✅ |

### 1.4 编写后端测试

```python
"""示例：API 路由测试"""
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_login_success(client):
    response = await client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()
```

## 2. 前端测试

### 2.1 单元测试 (Vitest)

```bash
cd src/frontend

# 运行所有前端单元测试
npm run test

# 监听模式
npm run test:watch

# 覆盖率报告
npm run test:coverage
```

### 2.2 测试文件约定

- 测试文件放在 `src/test/` 目录下
- 文件名格式：`*.test.ts` 或 `*.spec.ts`
- 使用 Vitest + Vue Test Utils

## 3. E2E 测试

项目有两套 E2E 测试：

### 3.1 TypeScript 套件 (Playwright)

```bash
cd src/frontend

# 安装 Playwright 浏览器
npx playwright install

# 运行 E2E 测试（无头模式）
npm run test:e2e

# UI 模式（可视化调试）
npm run test:e2e:ui

# 运行单个测试文件
npx playwright test e2e/tests/auth.spec.ts

# 调试模式
npx playwright test --debug
```

**测试文件位置**: `src/frontend/e2e/tests/`

| 文件 | 覆盖范围 |
|------|---------|
| `smoke.spec.ts` | Playwright 环境验证 |
| `basic.spec.ts` | 所有主要页面加载 |
| `auth.spec.ts` | 登录/注册/验证 |
| `backtest.spec.ts` | 回测页面元素 |
| `strategy.spec.ts` | 策略管理页面 |
| `live-trading.spec.ts` | 实盘交易页面 |
| `portfolio.spec.ts` | 投资组合页面 |

### 3.2 Python 套件 (Playwright + pytest)

```bash
# 安装依赖
pip install playwright pytest
python -m playwright install chromium

# 运行 Python E2E 测试
cd tests/e2e
python -m pytest -v

# 运行特定模块
python -m pytest test_auth.py -v
python -m pytest test_backtest.py -v
```

**测试文件位置**: `tests/e2e/`

| 文件 | 覆盖范围 |
|------|---------|
| `test_auth.py` | 认证流程 (注册/登录/重定向) |
| `test_dashboard.py` | 仪表盘 (统计/导航/登出) |
| `test_backtest.py` | 回测 (表单/历史/响应式) |
| `test_backtest_result.py` | 回测结果 (指标/图表/导航) |
| `test_data.py` | 数据查询 (表单/图表/下载) |
| `test_data_query.py` | 数据查询流程 (填写/提交/结果) |
| `test_strategy.py` | 策略管理 (CRUD/模板/搜索) |
| `test_strategy_crud.py` | 策略 CRUD 完整流程 |
| `test_optimization.py` | 参数优化 (表单/策略选择/响应式) |
| `test_live_trading.py` | 实盘交易 (实例/启停/详情) |
| `test_portfolio.py` | 投资组合 (概览/标签页/响应式) |
| `test_settings.py` | 设置页面 (个人信息/密码) |

### 3.3 独立回测 E2E 脚本

```bash
# 完整回测流程测试（需要后端+前端运行中）
python tests/test_backtest_e2e.py          # 有头模式
python tests/test_backtest_e2e.py --headless  # 无头模式
```

### 3.4 E2E 前置条件

运行 E2E 测试前需要：
1. 后端运行在 `http://localhost:8001`
2. 前端运行在 `http://localhost:3000`
3. 数据库已初始化
4. admin 用户已创建（默认密码 admin123）

```bash
# 启动后端
cd src/backend && uvicorn app.main:app --reload --port 8001

# 启动前端
cd src/frontend && npm run dev
```

## 4. 策略加载测试

```bash
# 验证策略动态加载
python -m pytest test_strategy_load.py -v
```

验证内容：
- 策略文件扫描（118+ 模板）
- `exec()` 动态加载 + `sys.modules` 注册
- backtrader Strategy 子类检测
- `config.yaml` + `strategy_*.py` 配对

## 5. 测试最佳实践

### 命名约定
- 测试函数：`test_<功能>_<场景>_<预期结果>`
- 测试类：`Test<模块名>`
- fixture：描述性名称，如 `authenticated_page`

### 测试隔离
- 每个测试应独立运行，不依赖执行顺序
- 使用 fixture 管理测试数据和状态
- E2E 测试使用唯一用户名避免冲突

### 断言规范
- 使用具体断言而非宽泛匹配
- E2E 中优先使用 `waitForSelector` 替代 `waitForTimeout`
- 验证关键业务逻辑而非仅验证元素存在

## 6. 覆盖率基线 (2026-02-24)

| 层级 | 测试数 | 覆盖率 | 说明 |
|------|--------|--------|------|
| 后端单元测试 | 1481 | **42%** | models/schemas 100%，services 11-51% |
| E2E 测试 | 129 | 路由 100% | 12/12 前端路由全覆盖 |
| 前端单测 | — | 待补充 | Vitest 框架已配置 |

**薄弱区域** (覆盖率 <20%):
- `monitoring_service.py` (11%)
- `log_parser_service.py` (11%)
- `param_optimization_service.py` (12%)
- `comparison_service.py` (15%)

```bash
# 生成覆盖率报告
cd src/backend
python -m pytest tests/ --cov=app --cov-report=html -q
open htmlcov/index.html
```

## 7. 持续集成

参见 [CI/CD 文档](CI_CD.md) 了解测试在 CI 流水线中的集成方式。

详细的 E2E 测试覆盖率分析参见 [E2E 测试覆盖率分析](E2E_TEST_COVERAGE_ANALYSIS.md)。
