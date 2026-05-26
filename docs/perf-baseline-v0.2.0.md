# v0.2.0 性能基线

> 采集时间：2026-05-24 17:40 UTC+08
> 环境：macOS 本地开发环境，Python 3.11.8，FastAPI TestClient / in-memory SQLite，`pytest-benchmark 5.1.0`

## 采集命令

```bash
cd src/backend
pytest tests/perf/test_api_performance.py -q --tb=short
pytest tests/perf/test_backtest_throughput.py -q --tb=short
```

## API 基线

测试文件：`src/backend/tests/perf/test_api_performance.py`

| 场景 | 状态 | Mean | 备注 |
|------|------|------|------|
| 登录 | baseline | 444.1 ms | 包含密码校验成本 |
| 策略列表 | baseline | 15.8 ms | 已预置 1 条策略 |
| 回测提交 | baseline | 8.6 ms | 注入 fake backtest service，不启动真实 subprocess |
| 回测结果获取 | baseline | 13.1 ms | 注入 fake completed result |
| 知识库搜索 | baseline | 76.0 ms | keyword search，内存 SQLite，已预索引单文档 |
| KB Chat 往返 | baseline | 114.2 ms | AI 未配置时走本地诊断/引用路径，不调用外部模型 |

## 回测吞吐基线

测试文件：`src/backend/tests/perf/test_backtest_throughput.py`

| 场景 | 状态 | Mean | 备注 |
|------|------|------|------|
| 5 策略状态轮询 | baseline | 102.1 ms | 5 个已完成任务 `/status` 轮询 |
| 5 策略任务提交 | baseline | 382.6 ms | API + DB 任务创建；no-op runner 关闭执行协程 |
| 5 策略提交并轮询 | baseline | 334.2 ms | 每轮创建 5 个任务后查询状态 |

## 解释边界

- 当前基线主要用于衡量 API/DB/序列化/任务编排开销，不代表真实策略执行耗时。
- T12 文档目标中的“5 个内置策略 + 1 年沪深300数据”在本轮以轻量 no-op runner 落地，避免性能基线测试触发真实回测 subprocess 和本地数据依赖。
- 后续如需测真实回测吞吐，应新增单独慢速 benchmark，并用 `pytest.mark.slow` 与普通 CI 路径隔离。
- 当前运行会出现第三方 `backtrader.feeds.quandl` deprecation warning，与本项目性能测试逻辑无关。

## 后续目标

- 后续优化目标：相同环境下回测任务创建/轮询链路 Mean 降低 60%。
- CI 建议：`pytest tests/perf/ --benchmark-only --benchmark-json=perf.json` 作为非阻断告警；超过基线 +20% 时提示人工检查。
