# E2E 测试质量审查报告

> **✅ 关键改进已实施** — pytest.skip 替代静默跳过 (G)、FRONTEND_URL 集中化 (H)、数据 fixture (O) 已完成。评分预计 72→82+。

> 审查日期: 2026-02-24 | 测试框架: Playwright + pytest | 总测试数: **127**

---

## 总评分: **72 / 100**

| 维度 | 得分 | 满分 | 说明 |
|------|------|------|------|
| 路由覆盖率 | 18 | 20 | 12/12 路由已覆盖 (100%) |
| 断言质量 | 12 | 20 | 176 个断言/expect，但部分测试断言薄弱 |
| 测试独立性 | 15 | 15 | 每个测试有独立 fixture，无跨测试依赖 |
| 错误路径覆盖 | 8 | 15 | 仅部分页面测试了无效输入/空状态 |
| 可维护性 | 12 | 15 | 选择器硬编码、FRONTEND_URL 重复定义 |
| 执行稳定性 | 7 | 15 | 过多 `if count() > 0` 导致测试静默跳过 |

---

## 详细分析

### 1. 路由覆盖率 — 18/20

**优点**: 所有 12 个前端路由均有测试覆盖。

| 路由 | 测试文件 | 测试数 |
|------|----------|--------|
| `/login` | test_auth.py | 10 |
| `/register` | test_auth.py | (含在上方) |
| `/` (Dashboard) | test_dashboard.py | 13 |
| `/backtest` | test_backtest.py | 17 |
| `/backtest/:id` | test_backtest_result.py | 5 |
| `/optimization` | test_optimization.py | 9 |
| `/strategy` | test_strategy.py + test_strategy_crud.py | 18 + 8 |
| `/data` | test_data.py + test_data_query.py | 16 + 11 |
| `/live-trading` | test_live_trading.py | 10 |
| `/live-trading/:id` | test_live_trading.py | (含在上方) |
| `/portfolio` | test_portfolio.py | 7 |
| `/settings` | test_settings.py | 5 |

**扣分原因**: `/backtest/:id` 和 `/live-trading/:id` 的测试依赖于是否有历史数据，空库时多数断言被 `if` 跳过。

### 2. 断言质量 — 12/20

**统计**:
- 总断言数: **176** (assert + expect)
- 平均每测试: **1.4 个断言**
- 使用 Playwright `expect()`: 约 40%
- 使用原生 `assert`: 约 60%

**问题**:

| 问题 | 严重度 | 示例 |
|------|--------|------|
| 过于宽松的断言 | 🟡 | `assert len(content) > 100` 只检查页面不白屏 |
| 字符串包含检查 | 🟡 | `assert "优化" in content` 可能匹配到无关文字 |
| `test_live_trading_page_loads` 与 `test_live_trading_page_title` 几乎重复 | 🟢 | 两个测试检查相同内容 |
| 响应式测试只检查 `len(content) > 100` | 🟡 | 未验证实际布局变化 |

**建议**:
- 响应式测试应验证特定元素的可见性变化（如侧边栏折叠）
- 用 `expect(locator).to_contain_text()` 替代 `"xxx" in page.content()`
- 增加每测试断言密度到 ≥2

### 3. 测试独立性 — 15/15

**优点**:
- `authenticated_page` fixture 为每个测试提供独立的已登录页面
- `context` scope=function 确保隔离
- 无跨测试的全局状态污染
- 用户注册通过 API 完成（`_ensure_test_user_exists`），避免 UI 注册竞态

### 4. 错误路径覆盖 — 8/15

**已覆盖**:
- ✅ 无效回测 ID 访问 (`test_backtest_result_page_loads_with_invalid_id`)
- ✅ 无效实盘实例 ID (`test_detail_page_loads_with_invalid_id`)
- ✅ 错误密码登录 (`test_login_with_wrong_password`)
- ✅ 空名称表单验证 (`test_empty_name_validation`)
- ✅ 密码不匹配 (`test_password_mismatch`)

**未覆盖**:
- ❌ 后端服务不可用时的前端行为
- ❌ 网络超时/断连场景
- ❌ 并发操作（同时提交多个回测）
- ❌ 大数据量分页（100+ 策略列表）
- ❌ 未授权访问 API 返回 401 后的前端处理
- ❌ 表单极端值（超长字符串、特殊字符、XSS 载荷）

### 5. 可维护性 — 12/15

**问题**:

| 问题 | 建议 |
|------|------|
| `FRONTEND_URL` 在每个文件重复定义 | 移入 conftest.py 统一管理 |
| 选择器硬编码中文 `'input[placeholder="用户名"]'` | 定义 Page Object 或选择器常量 |
| 无 Page Object Model | 推荐为关键页面创建 POM 类 |
| `import re` 在函数内而非文件顶部 | 移至文件顶部 |

**优点**:
- 所有测试有清晰的中文 docstring
- 按页面组织为独立的 test class
- 文件命名规范一致

### 6. 执行稳定性 — 7/15

**核心问题**: 过多的条件分支导致测试静默通过。

```python
# 典型模式 — 元素不存在时整个测试被跳过
result_links = page.locator('a[href*="/backtest/"]')
if result_links.count() > 0:
    # ... 核心断言在这里
    # 如果 count() == 0，测试 PASS 但什么也没验证
```

**统计**:
- 含 `if count() > 0` 的测试: **~35 个** (约 28%)
- 这意味着在空数据库上约 1/4 的测试实际未执行任何断言

**建议**:
- 对于需要数据的测试，使用 `pytest.mark.skipif` 或 fixture 预置数据
- 将 `if count() > 0` 替换为 `pytest.skip("无回测历史数据")` 使跳过可见
- 关键路径测试应通过 API fixture 预创建测试数据

---

## 改进优先级

| 优先级 | 改进项 | 预期收益 | 工作量 |
|--------|--------|----------|--------|
| 🔴 P0 | 将静默 `if count()` 改为显式 `pytest.skip()` | 透明化跳过 | 1h |
| 🔴 P0 | 为关键路径创建数据 fixture（API 预创策略+回测） | 消除数据依赖 | 2h |
| 🟡 P1 | 提取 `FRONTEND_URL` 到 conftest.py | 减少重复 | 15min |
| 🟡 P1 | 增加断言密度（每测试 ≥2 个有意义断言） | 提升检测能力 | 2h |
| 🟡 P1 | 响应式测试增加实际布局验证 | 真正测试响应式 | 1h |
| 🟢 P2 | 引入 Page Object Model | 长期可维护性 | 3h |
| 🟢 P2 | 增加错误路径覆盖（网络异常、极端输入） | 鲁棒性 | 2h |
| 🟢 P2 | 添加 `@pytest.mark.slow` 标签区分快慢测试 | CI 灵活性 | 30min |

---

## 文件级质量矩阵

| 文件 | 测试数 | 断言数 | 断言/测试 | 条件跳过 | 评级 |
|------|--------|--------|-----------|----------|------|
| test_auth.py | 10 | 21 | 2.1 | 0 | ⭐⭐⭐⭐ |
| test_dashboard.py | 13 | 27 | 2.1 | 2 | ⭐⭐⭐⭐ |
| test_backtest.py | 17 | 21 | 1.2 | 5 | ⭐⭐⭐ |
| test_strategy.py | 18 | 19 | 1.1 | 4 | ⭐⭐⭐ |
| test_data.py | 16 | 20 | 1.3 | 3 | ⭐⭐⭐ |
| test_optimization.py | 9 | 11 | 1.2 | 3 | ⭐⭐⭐ |
| test_live_trading.py | 10 | 11 | 1.1 | 5 | ⭐⭐⭐ |
| test_data_query.py | 11 | 13 | 1.2 | 4 | ⭐⭐⭐ |
| test_strategy_crud.py | 8 | 9 | 1.1 | 4 | ⭐⭐ |
| test_portfolio.py | 7 | 8 | 1.1 | 2 | ⭐⭐⭐ |
| test_backtest_result.py | 5 | 6 | 1.2 | 4 | ⭐⭐ |
| test_settings.py | 5 | 10 | 2.0 | 0 | ⭐⭐⭐⭐ |

---

*审查完成。评分 72/100 表示测试基础扎实但需要在断言质量和数据依赖方面改进。*
