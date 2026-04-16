# 回测

## 概述

Backtrader Web 的回测引擎基于 **Backtrader**，使用 **fincore** 提供标准化金融指标。

## 主要特性

- **异步执行** - 非阻塞回测运行
- **进度流** - 通过 WebSocket 实时显示进度
- **多数据源** - AkShare、CSV、数据库
- **标准化指标** - fincore 驱动的分析
- **报告导出** - HTML/PDF/Excel 报告

## API 端点

### 运行回测

```http
POST /api/v1/backtests/run
Content-Type: application/json

{
  "strategy_id": 1,
  "symbol": "000001.SZ",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_cash": 100000,
  "commission": 0.001
}
```

### 获取回测结果

```http
GET /api/v1/backtests/{task_id}
```

### 列出回测历史

```http
GET /api/v1/backtests?page=1&page_size=20
```

## 金融指标

### 收益指标
- 总收益率
- 年化收益率
- 超额收益

### 风险指标
- 最大回撤
- 波动率
- 下行风险

### 风险调整收益
- 夏普比率
- 索提诺比率
- 卡玛比率

### 交易统计
- 胜率
- 盈亏比
- 平均持仓时间

## WebSocket 进度

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/backtest/{task_id}');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`进度: ${data.progress}%`);
};
```

## 报告导出

支持多种格式导出回测结果：

- **HTML** - 交互式图表
- **PDF** - 打印友好
- **Excel** - 原始数据
