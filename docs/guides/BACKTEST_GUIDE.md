# 回测指南

本文档介绍如何使用 Backtrader Web 进行策略回测。

## 1. 快速开始

### 1.1 访问回测页面

登录后，通过侧边栏点击「回测分析」或直接访问 `/backtest`。

### 1.2 基本回测流程

1. **选择策略** — 从策略下拉列表中选择一个内置模板或自定义策略
2. **配置参数** — 设置股票代码、日期范围、初始资金等
3. **运行回测** — 点击「运行回测」按钮
4. **查看结果** — 等待回测完成后查看指标和图表

## 2. 回测配置

### 2.1 基本参数

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| 策略 | 选择要回测的策略 | — | 双均线交叉策略 |
| 股票代码 | 交易标的代码 | `000001.SZ` | `600519.SH` |
| 开始日期 | 回测起始日期 | 2020-01-01 | 2022-01-01 |
| 结束日期 | 回测结束日期 | 2023-12-31 | 2024-12-31 |
| 初始资金 | 起始资金量 | 100,000 | 1,000,000 |
| 手续费率 | 交易佣金比例 | 0.001 (0.1%) | 0.0003 |

### 2.2 策略参数

每个策略有独特的参数。选择策略后，参数面板会显示该策略的可配置参数。

例如，双均线策略的参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `short_period` | 短期均线周期 | 5 |
| `long_period` | 长期均线周期 | 20 |

### 2.3 股票代码格式

| 市场 | 格式 | 示例 |
|------|------|------|
| 深圳 A 股 | `XXXXXX.SZ` | `000001.SZ` (平安银行) |
| 上海 A 股 | `XXXXXX.SH` | `600519.SH` (贵州茅台) |
| 创业板 | `3XXXXX.SZ` | `300750.SZ` (宁德时代) |
| 科创板 | `68XXXX.SH` | `688981.SH` (中芯国际) |

## 3. 回测结果

### 3.1 核心指标

回测完成后显示以下关键指标：

| 指标 | 说明 | 判断标准 |
|------|------|---------|
| **总收益率** | 策略总回报百分比 | >0 为盈利 |
| **年化收益率** | 按年折算的收益率 | 对标基准收益 |
| **夏普比率** | 风险调整后收益 | >1 优秀, >2 极好 |
| **最大回撤** | 最大亏损幅度 | <20% 较好 |
| **总交易次数** | 策略执行的交易数 | 过多/过少都需警惕 |
| **胜率** | 盈利交易占比 | >50% 较好 |
| **盈亏比** | 平均盈利/平均亏损 | >1.5 较好 |

指标数据由 **fincore** 库标准化计算，确保机构级精度。

### 3.2 图表

- **资金曲线图** — 显示账户价值随时间变化
- **回撤图** — 显示各时间点的回撤幅度
- **交易标记** — 在 K 线图上标注买卖点

### 3.3 回测历史

所有回测结果自动保存，可在回测历史区域查看和对比。

## 4. 报告导出

### 4.1 支持格式

| 格式 | 用途 | API 路径 |
|------|------|---------|
| HTML | 交互式报告，可在浏览器查看 | `/api/v1/backtests/{id}/report/html` |
| PDF | 正式报告，适合打印 | `/api/v1/backtests/{id}/report/pdf` |
| Excel | 数据分析，可用 Excel 打开 | `/api/v1/backtests/{id}/report/excel` |

### 4.2 API 导出示例

```bash
# 获取 HTML 报告
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/backtests/{task_id}/report/html \
  -o backtest_report.html

# 获取 Excel 报告
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/backtests/{task_id}/report/excel \
  -o backtest_report.xlsx
```

## 5. 高级用法

### 5.1 通过 API 运行回测

```bash
# 提交回测任务
curl -X POST http://localhost:8000/api/v1/backtest/run \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "002_dual_ma",
    "symbol": "000001.SZ",
    "start_date": "2022-01-01",
    "end_date": "2023-12-31",
    "initial_cash": 100000,
    "commission": 0.001
  }'

# 查询回测状态
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/backtest/{task_id}/status

# 获取回测结果
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/backtest/{task_id}
```

### 5.2 回测结果对比

通过对比 API 可以同时比较多个回测结果的指标：

```bash
curl -X POST http://localhost:8000/api/v1/comparisons/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"task_ids": ["task_1", "task_2", "task_3"]}'
```

### 5.3 取消和删除

```bash
# 取消运行中的回测
curl -X POST http://localhost:8000/api/v1/backtest/{task_id}/cancel \
  -H "Authorization: Bearer <token>"

# 删除回测结果
curl -X DELETE http://localhost:8000/api/v1/backtest/{task_id} \
  -H "Authorization: Bearer <token>"
```

## 6. 注意事项

1. **数据依赖** — 回测数据通过 AkShare 获取，需要网络连接
2. **回测偏差** — 历史回测不代表未来收益，注意过拟合风险
3. **手续费影响** — 合理设置手续费率，默认 0.1% 已包含印花税
4. **策略限制** — 内置策略为只读模板，如需修改请先创建副本
5. **并发限制** — 同时运行的回测任务有限制，请等待前一个完成

## 7. 相关文档

- [策略开发](STRATEGY_DEVELOPMENT.md) — 如何编写自定义策略
- [参数优化](OPTIMIZATION.md) — 如何优化策略参数
- [API 文档](API.md) — 完整 API 接口说明
