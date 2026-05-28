# Adversarial Code Review — 发现报告

**项目**: Backtrader Web  
**评审日期**: 2025-03-10  
**评审范围**: 后端核心代码 (router, main, strategy_service, exception_handling, simulation API)

---

## 发现项（按严重程度排序）

### 🔴 严重 — 安全漏洞

1. **模拟交易 API 存在 IDOR（不安全的直接对象引用）**  
   `simulation.py` 中 `get_simulation_detail`、`get_simulation_kline`、`get_simulation_monthly_returns` 以及 `_get_strategy_log_dir` 调用 `mgr.get_instance(instance_id)` 时**未传入 `user_id`**。当 `user_id` 为 `None` 时，`LiveTradingManager.get_instance` 不会进行权限校验，任何已认证用户只要知道 `instance_id` 即可查看其他用户的模拟交易详情、K 线数据与月度收益。  
   **修复建议**：在上述所有调用处传入 `current_user.sub`，并确保 `_get_strategy_log_dir` 接受 `user_id` 参数或由调用方在调用前校验归属。

2. **start_all / stop_all 未按用户过滤**  
   模拟交易的 `start_all` 和 `stop_all` 调用 `mgr.start_all()` 和 `mgr.stop_all()`，而 `LiveTradingManager` 的这两个方法会操作**全局所有实例**，不区分用户。结果是：用户 A 可以启动/停止用户 B 的模拟实例。  
   **修复建议**：为 `start_all` / `stop_all` 增加 `user_id` 参数，仅操作该用户的实例；或从模拟交易 API 中移除这两个端点，改由前端对当前用户实例列表逐条 start/stop。

---

### 🟠 高 — 设计与可维护性

3. **异常处理中重复的校验逻辑**  
   `exception_handling.py` 中 `handle_validation_error`（Pydantic ValidationError）与 `handle_request_validation_error`（FastAPI RequestValidationError）逻辑高度重复。FastAPI 的 `RequestValidationError` 继承自 Pydantic `ValidationError`，两套 handler 存在冗余。  
   **修复建议**：合并为一个 handler，或抽成共享函数，减少重复并保证行为一致。

4. **strategy_service 类型推断不完整**  
   在 `_scan_strategies_folder` 中，对 `raw_params` 的 `ptype` 推断仅为 `"float"` 或 `"int"`，未处理 `str`、`bool`、`list` 等情况。若 config.yaml 中有 `param: "some_string"` 或 `param: true`，会错误地归类为 `int`。  
   **修复建议**：补充完整类型分支，或使用 `type(v).__name__` / 显式 schema 定义参数类型。

5. **list_strategies 参数类型不符合 PEP 484**  
   `StrategyService.list_strategies` 中 `category: str = None` 应改为 `category: Optional[str] = None`，以符合类型注解规范，并配合 mypy 等工具。  
   **修复建议**：`from typing import Optional` 并将签名改为 `category: Optional[str] = None`。

---

### 🟡 中 — 代码质量

6. **模块级副作用影响可测试性**  
   `strategy_service.py` 在导入时即执行 `_scan_strategies_folder`，填充 `STRATEGY_TEMPLATES_*` 与 `_TEMPLATE_MAP_*`。单元测试难以注入 mock 或替换策略目录，且依赖真实文件系统。  
   **修复建议**：改为惰性加载或通过依赖注入传入策略目录路径，便于测试时覆盖。

7. **simulation 中 STRATEGIES_DIR 路径假设脆弱**  
   `_get_strategy_log_dir` 使用 `STRATEGIES_DIR / inst["strategy_id"]`，假定 `strategy_id` 与目录名完全对应。若 `strategy_id` 含 `backtest/xxx` 等形式，会得到错误路径。`strategy_service` 中模板 ID 格式为 `{type}/{dir_name}`，此处需确认一致性。  
   **修复建议**：统一策略 ID 与目录结构的约定，或在解析时显式处理 `type/name` 格式。

8. **get_simulation_detail 中 bare except**  
   `simulation.py` 的月度收益计算处有 `except Exception: continue`，会吞掉所有异常（包括 `KeyError`、`IndexError` 等），难以排查数据格式问题。  
   **修复建议**：捕获更具体的异常类型，或在 `continue` 前记录日志，便于问题定位。

9. **router 中可选路由的 try/except ImportError 过于宽泛**  
   `router.py` 中对可选 API 使用 `try/except ImportError` 静默忽略。若模块存在但内部有语法/导入错误，会误以为“可选功能未安装”而隐藏真实错误。  
   **修复建议**：在开发环境或 DEBUG 下至少打出 warning；或对 `ImportError` 与 `ModuleNotFoundError` 分别处理，区分“未安装”与“安装但加载失败”。

---

### 🟢 低 — 改进建议

10. **status_code 应使用常量**  
    `simulation.py` 中部分 `HTTPException` 使用字面量 `status_code=404`，而其他处使用 `status.HTTP_404_NOT_FOUND`。为保持风格统一，建议全部使用 `status` 常量。

11. **Health check 中裸 except**  
    `main.py` 的 `health_check` 使用 `except Exception` 并调用 `logger.exception`，虽已记录堆栈，但在健康检查失败时可能需要区分数据库不可用与配置错误。考虑对 `OperationalError`、`ConnectionError` 等做更细分处理，便于监控与告警。

12. **WebSocket 未校验 task_id 归属**  
    `main.py` 中 `websocket_backtest_progress` 按 `task_id` 连接，未见对 `task_id` 与当前用户关联的校验。若 task_id 可被枚举或预测，可能存在越权访问回测进度的风险。  
    **修复建议**：在 `ws_manager.connect` 中或前置中间件里校验 task 归属当前用户。

---

## 已修复项（2025-03-10）

- ✅ **#1 IDOR**：simulation.py 与 live_trading_api.py 中所有 `get_instance`、`_get_strategy_log_dir` 已改为传入 `user_id`
- ✅ **#2 start_all/stop_all**：`LiveTradingManager.start_all(user_id)`、`stop_all(user_id)` 已支持用户过滤；simulation 与 live_trading API 已传入 `current_user.sub`
- ✅ **#3 异常处理重复**：提取 `_build_validation_error_response()` 共享逻辑，`handle_validation_error` 与 `handle_request_validation_error` 共用
- ✅ **#4 类型推断**：strategy_service 中 ParamSpec 的 ptype 已支持 bool、int、float、string
- ✅ **#5 类型注解**：`list_strategies(category: Optional[str] = None)` 已修正
- ✅ **#6 模块级副作用**：策略模板改为 `@lru_cache` 惰性加载（`_get_templates_for_type`）
- ✅ **#7 路径假设**：新增 `get_strategy_dir()`，带路径遍历校验，simulation/live_trading/portfolio API 已改用
- ✅ **#8 bare except**：`simulation.py` 月度收益循环改为 `except (IndexError, KeyError, TypeError, ValueError)` 并记录日志

## 建议的修复优先级

| 优先级 | 发现项 | 建议时间 |
|--------|--------|----------|
| P0 | #1 IDOR、#2 start_all/stop_all | 立即 |
| P1 | #3 异常处理重复、#4 类型推断、#5 类型注解 | 本周 |
| P2 | #6 模块级副作用、#7 路径假设、#8 bare except | 下次迭代 |
| P3 | #9–#12 | 技术债清理时 |

---

## 后续建议

- 运行 **Edge Case Hunter**（`/bmad-review-edge-case-hunter`）补充分支与边界情况审查
- 运行 **Test Review**（`/bmad-tea-testarch-test-review`）检查测试覆盖与质量
- 为 `simulation` API 补充权限与安全相关的单元/集成测试
