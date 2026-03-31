# Backtrader Web - API 使用指南

> 本文档提供 Backtrader Web API 的详细使用指南、常见用例和最佳实践。

**API 基础 URL**: `http://localhost:8000/api/v1`  
**Swagger 文档**: `http://localhost:8000/docs`  
**ReDoc 文档**: `http://localhost:8000/redoc`

---

## 目录

1. [认证](#认证)
2. [策略管理](#策略管理)
3. [回测执行](#回测执行)
4. [参数优化](#参数优化)
5. [实盘交易](#实盘交易)
6. [错误处理](#错误处理)
7. [最佳实践](#最佳实践)
8. [常见用例](#常见用例)

---

## 认证

### 1. 用户注册

**端点**: `POST /api/v1/auth/register`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "trader001",
    "email": "trader@example.com",
    "password": "SecurePass123!"
  }'
```

**Python 示例**:
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/auth/register",
    json={
        "username": "trader001",
        "email": "trader@example.com",
        "password": "SecurePass123!"
    }
)
print(response.json())
```

**成功响应** (200):
```json
{
  "id": 1,
  "username": "trader001",
  "email": "trader@example.com",
  "created_at": "2026-03-07T10:00:00Z"
}
```

**错误响应**:
- `400 Bad Request`: 用户名或邮箱已存在
- `422 Unprocessable Entity`: 输入验证失败

**注意事项**:
- 密码至少 8 个字符
- 邮箱格式必须有效
- 速率限制：5 次/小时/IP

---

### 2. 用户登录

**端点**: `POST /api/v1/auth/login`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "trader001",
    "password": "SecurePass123!"
  }'
```

**成功响应** (200):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**使用 Token**:
```bash
# 在后续请求中添加 Authorization header
curl -X GET "http://localhost:8000/api/v1/strategy/" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**注意事项**:
- Token 有效期：24 小时
- 速率限制：10 次/分钟/IP
- 失败登录会被记录审计日志

---

### 3. 刷新 Token

**端点**: `POST /api/v1/auth/login/refresh`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login/refresh" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "YOUR_REFRESH_TOKEN"
  }'
```

**最佳实践**:
- 在 Token 过期前 1 小时刷新
- 存储 refresh_token 到安全位置（如 httpOnly cookie）

---

## 策略管理

### 1. 创建策略

**端点**: `POST /api/v1/strategy/`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/strategy/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "双均线策略",
    "description": "基于快慢均线交叉的趋势跟踪策略",
    "code": "# Python 代码\nimport backtrader as bt\n\nclass DualMAStrategy(bt.Strategy):\n    params = (\n        (\"fast_period\", 10),\n        (\"slow_period\", 30),\n    )\n    \n    def __init__(self):\n        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.p.fast_period)\n        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.p.slow_period)\n        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)\n    \n    def next(self):\n        if self.crossover > 0:\n            self.buy()\n        elif self.crossover < 0:\n            self.sell()",
    "category": "trend_following",
    "parameters": {
      "fast_period": {"type": "int", "default": 10, "min": 5, "max": 50},
      "slow_period": {"type": "int", "default": 30, "min": 20, "max": 100}
    }
  }'
```

**Python 示例**:
```python
import requests

strategy_data = {
    "name": "双均线策略",
    "description": "基于快慢均线交叉的趋势跟踪策略",
    "code": open("strategies/dual_ma_strategy.py").read(),
    "category": "trend_following",
    "parameters": {
        "fast_period": {"type": "int", "default": 10, "min": 5, "max": 50},
        "slow_period": {"type": "int", "default": 30, "min": 20, "max": 100}
    }
}

response = requests.post(
    "http://localhost:8000/api/v1/strategy/",
    headers={"Authorization": f"Bearer {token}"},
    json=strategy_data
)
print(response.json())
```

**成功响应** (200):
```json
{
  "id": "uuid-string",
  "name": "双均线策略",
  "description": "基于快慢均线交叉的趋势跟踪策略",
  "category": "trend_following",
  "created_at": "2026-03-07T10:00:00Z",
  "updated_at": "2026-03-07T10:00:00Z"
}
```

**策略分类**:
- `trend_following`: 趋势跟踪
- `mean_reversion`: 均值回归
- `momentum`: 动量策略
- `arbitrage`: 套利策略
- `custom`: 自定义

---

### 2. 获取策略列表

**端点**: `GET /api/v1/strategy/`

**请求示例**:
```bash
# 获取所有策略
curl -X GET "http://localhost:8000/api/v1/strategy/" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 按分类过滤
curl -X GET "http://localhost:8000/api/v1/strategy/?category=trend_following&limit=10&offset=0" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**查询参数**:
- `limit`: 每页数量 (1-100, 默认 20)
- `offset`: 偏移量 (默认 0)
- `category`: 分类过滤 (可选)

**成功响应** (200):
```json
{
  "strategies": [
    {
      "id": "uuid-1",
      "name": "策略1",
      "description": "描述",
      "category": "trend_following"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

### 3. 获取策略模板

**端点**: `GET /api/v1/strategy/templates`

**请求示例**:
```bash
curl -X GET "http://localhost:8000/api/v1/strategy/templates" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**用途**:
- 查看内置策略模板
- 学习策略编写模式
- 快速开始开发

---

## 回测执行

### 1. 提交回测任务

**端点**: `POST /api/v1/backtest/run`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/backtest/run" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "your-strategy-uuid",
    "symbol": "000001.SZ",
    "start_date": "2020-01-01",
    "end_date": "2023-12-31",
    "initial_cash": 100000,
    "commission": 0.001,
    "slippage": 0.0005,
    "parameters": {
      "fast_period": 10,
      "slow_period": 30
    }
  }'
```

**Python 完整示例**:
```python
import requests
import time

# 1. 提交回测
response = requests.post(
    "http://localhost:8000/api/v1/backtest/run",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "strategy_id": "your-strategy-uuid",
        "symbol": "000001.SZ",
        "start_date": "2020-01-01",
        "end_date": "2023-12-31",
        "initial_cash": 100000,
        "commission": 0.001,
        "slippage": 0.0005,
        "parameters": {
            "fast_period": 10,
            "slow_period": 30
        }
    }
)

task_id = response.json()["task_id"]
print(f"回测任务已提交: {task_id}")

# 2. 轮询状态
while True:
    status_response = requests.get(
        f"http://localhost:8000/api/v1/backtest/{task_id}/status",
        headers={"Authorization": f"Bearer {token}"}
    )
    status = status_response.json()["status"]
    print(f"当前状态: {status}")
    
    if status == "completed":
        break
    elif status == "failed":
        print("回测失败")
        break
    
    time.sleep(5)

# 3. 获取结果
result_response = requests.get(
    f"http://localhost:8000/api/v1/backtest/{task_id}",
    headers={"Authorization": f"Bearer {token}"}
)
result = result_response.json()
print(f"总收益率: {result['total_return']:.2%}")
print(f"夏普比率: {result['sharpe_ratio']:.2f}")
print(f"最大回撤: {result['max_drawdown']:.2%}")
```

**成功响应** (200):
```json
{
  "task_id": "task-uuid-string",
  "status": "pending",
  "created_at": "2026-03-07T10:00:00Z"
}
```

**参数说明**:
- `strategy_id`: 策略 UUID
- `symbol`: 股票代码 (格式: `代码.市场`，如 `000001.SZ`)
- `start_date` / `end_date`: 回测日期范围 (格式: `YYYY-MM-DD`)
- `initial_cash`: 初始资金 (默认: 100000)
- `commission`: 手续费率 (默认: 0.001)
- `slippage`: 滑点 (默认: 0.0005)
- `parameters`: 策略参数 (覆盖默认值)

**注意事项**:
- 并发限制：全局最多 10 个并发回测
- 超时：单个回测最长 30 分钟
- 数据源：目前支持 A 股历史数据

---

### 2. 查询回测状态

**端点**: `GET /api/v1/backtest/{task_id}/status`

**请求示例**:
```bash
curl -X GET "http://localhost:8000/api/v1/backtest/task-uuid/status" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**成功响应** (200):
```json
{
  "task_id": "task-uuid",
  "status": "running"
}
```

**状态说明**:
- `pending`: 等待执行
- `running`: 正在执行
- `completed`: 执行完成
- `failed`: 执行失败
- `cancelled`: 已取消

---

### 3. 获取回测结果

**端点**: `GET /api/v1/backtest/{task_id}`

**成功响应** (200):
```json
{
  "task_id": "task-uuid",
  "status": "completed",
  "total_return": 0.256,
  "sharpe_ratio": 1.85,
  "max_drawdown": -0.123,
  "win_rate": 0.65,
  "profit_factor": 2.3,
  "total_trades": 150,
  "metrics_source": "fincore",
  "trades": [
    {
      "date": "2020-01-15",
      "type": "BUY",
      "price": 10.5,
      "shares": 1000,
      "commission": 10.5
    }
  ],
  "equity_curve": [100000, 102000, 101500, ...],
  "created_at": "2026-03-07T10:00:00Z",
  "completed_at": "2026-03-07T10:05:00Z"
}
```

**指标说明**:
- `total_return`: 总收益率 (小数)
- `sharpe_ratio`: 夏普比率
- `max_drawdown`: 最大回撤 (负数)
- `win_rate`: 胜率 (0-1)
- `profit_factor`: 盈亏比
- `total_trades`: 总交易次数
- `metrics_source`: 指标计算来源 (fincore/manual)

---

### 4. WebSocket 实时进度

**连接**: `ws://localhost:8000/ws/backtest/{task_id}`

**JavaScript 示例**:
```javascript
const token = localStorage.getItem('token');
const ws = token
  ? new WebSocket('ws://localhost:8000/ws/backtest/task-uuid', ['access-token', token])
  : new WebSocket('ws://localhost:8000/ws/backtest/task-uuid');

ws.onopen = () => {
  console.log('WebSocket 连接已建立');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('进度更新:', data);
  
  if (data.type === 'completed') {
    console.log('回测完成！结果:', data.result);
    ws.close();
  }
};

ws.onerror = (error) => {
  console.error('WebSocket 错误:', error);
};
```

**消息格式**:
```json
{
  "type": "progress",
  "task_id": "task-uuid",
  "status": "running",
  "progress": 45,
  "message": "正在处理 2021 年数据...",
  "data": {}
}
```

**事件类型**:
- `connected`: 握手成功
- `task_created`: 任务已提交，状态为 `pending`
- `progress`: 任务运行中，带 `progress/message/data`
- `completed`: 任务完成，带完整 `result`
- `failed`: 任务失败，带 `message/error`
- `cancelled`: 任务取消

---

## 参数优化

### 1. 提交优化任务

**权威端点**: `POST /api/v1/optimization/submit/backtest`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/optimization/submit/backtest" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "your-strategy-uuid",
    "backtest_config": {
      "strategy_id": "your-strategy-uuid",
      "symbol": "000001.SZ",
      "start_date": "2020-01-01T00:00:00",
      "end_date": "2023-12-31T00:00:00",
      "initial_cash": 100000,
      "commission": 0.001,
      "params": {}
    },
    "method": "grid",
    "param_grid": {
      "fast_period": [5, 10, 15, 20],
      "slow_period": [20, 30, 40, 50, 60]
    },
    "metric": "sharpe_ratio"
  }'
```

**优化方法**:
- `grid`: 网格搜索
- `bayesian`: 贝叶斯优化

**目标指标**:
- `sharpe_ratio`: 夏普比率
- `total_return`: 总收益率
- `max_drawdown`: 最大回撤（最小化）

**兼容入口**:
- `POST /api/v1/backtests/optimization/grid`
- `POST /api/v1/backtests/optimization/bayesian`

兼容入口当前仅用于旧调用方迁移，服务端会代理到统一任务式主链路，并返回 deprecated 相关响应头，不建议新接入继续使用。

---

## 实盘交易

### 1. 启动实盘交易

**端点**: `POST /api/v1/live-trading/start`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/live-trading/start" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "your-strategy-uuid",
    "broker_config": {
      "broker": "eastmoney",
      "account": "your-account",
      "password": "your-password"
    },
    "symbols": ["000001.SZ", "600000.SH"],
    "initial_capital": 100000,
    "risk_management": {
      "max_position_pct": 0.3,
      "stop_loss_pct": 0.05,
      "take_profit_pct": 0.15
    }
  }'
```

**⚠️ 警告**: 实盘交易涉及真实资金，请谨慎使用！

**最佳实践**:
1. 先在模拟环境充分测试
2. 使用小额资金开始
3. 设置严格的风控参数
4. 监控系统实时运行状态

---

## 错误处理

### HTTP 状态码

| 状态码 | 含义 | 处理方式 |
|--------|------|----------|
| 200 | 成功 | 正常处理 |
| 201 | 创建成功 | 资源已创建 |
| 400 | 请求错误 | 检查请求参数 |
| 401 | 未认证 | 重新登录获取 token |
| 403 | 无权限 | 检查用户权限 |
| 404 | 未找到 | 检查资源 ID |
| 422 | 验证失败 | 检查输入格式 |
| 429 | 请求过多 | 降低请求频率 |
| 500 | 服务器错误 | 联系管理员 |

### 错误响应格式

```json
{
  "detail": "错误描述",
  "status_code": 400,
  "timestamp": "2026-03-07T10:00:00Z"
}
```

### 错误处理示例

```python
import requests
from requests.exceptions import HTTPError

try:
    response = requests.post(
        "http://localhost:8000/api/v1/backtest/run",
        headers={"Authorization": f"Bearer {token}"},
        json=backtest_data
    )
    response.raise_for_status()
    result = response.json()
    
except HTTPError as e:
    if e.response.status_code == 401:
        print("Token 已过期，请重新登录")
        # 重新登录逻辑
    elif e.response.status_code == 429:
        print("请求过于频繁，等待后重试")
        time.sleep(60)
    else:
        print(f"请求失败: {e.response.json()['detail']}")
        
except Exception as e:
    print(f"未知错误: {e}")
```

---

## 最佳实践

### 1. Token 管理

```python
# ✅ 好的做法：使用环境变量
import os
from datetime import datetime, timedelta

class TokenManager:
    def __init__(self):
        self.token = None
        self.expires_at = None
    
    def get_valid_token(self):
        if self.token and datetime.now() < self.expires_at:
            return self.token
        
        # 刷新 token
        response = requests.post(
            "http://localhost:8000/api/v1/auth/login",
            json={
                "username": os.getenv("API_USERNAME"),
                "password": os.getenv("API_PASSWORD")
            }
        )
        self.token = response.json()["access_token"]
        self.expires_at = datetime.now() + timedelta(hours=23)
        return self.token
```

### 2. 批量操作

```python
# ✅ 好的做法：批量获取结果
def get_multiple_results(task_ids):
    results = []
    for task_id in task_ids:
        result = requests.get(
            f"http://localhost:8000/api/v1/backtest/{task_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        results.append(result.json())
    return results

# ❌ 避免：并发大量请求（会触发速率限制）
```

### 3. 错误重试

```python
import time
from functools import wraps

def retry(max_attempts=3, delay=5):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except HTTPError as e:
                    if e.response.status_code == 429:
                        wait_time = delay * (attempt + 1)
                        print(f"速率限制，等待 {wait_time} 秒...")
                        time.sleep(wait_time)
                    else:
                        raise
            raise Exception(f"重试 {max_attempts} 次后仍失败")
        return wrapper
    return decorator

@retry(max_attempts=3, delay=5)
def submit_backtest(data):
    return requests.post(
        "http://localhost:8000/api/v1/backtest/run",
        headers={"Authorization": f"Bearer {token}"},
        json=data
    )
```

### 4. 数据缓存

```python
from functools import lru_cache
import time

@lru_cache(maxsize=128)
def get_strategy(strategy_id):
    """缓存策略数据，避免重复请求"""
    response = requests.get(
        f"http://localhost:8000/api/v1/strategy/{strategy_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()

# 定期清理缓存
def clear_cache_periodically():
    while True:
        time.sleep(3600)  # 每小时清理一次
        get_strategy.cache_clear()
```

---

## 常见用例

### 用例1：自动化回测流程

```python
import requests
import time
import json

def automated_backtest_workflow():
    """自动化回测工作流"""
    
    # 1. 登录
    login_response = requests.post(
        "http://localhost:8000/api/v1/auth/login",
        json={"username": "user", "password": "pass"}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. 创建策略
    strategy_response = requests.post(
        "http://localhost:8000/api/v1/strategy/",
        headers=headers,
        json={
            "name": "自动策略",
            "code": open("strategy.py").read(),
            "category": "custom"
        }
    )
    strategy_id = strategy_response.json()["id"]
    
    # 3. 提交回测
    backtest_response = requests.post(
        "http://localhost:8000/api/v1/backtest/run",
        headers=headers,
        json={
            "strategy_id": strategy_id,
            "symbol": "000001.SZ",
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "initial_cash": 100000
        }
    )
    task_id = backtest_response.json()["task_id"]
    
    # 4. 等待完成
    while True:
        status_response = requests.get(
            f"http://localhost:8000/api/v1/backtest/{task_id}/status",
            headers=headers
        )
        status = status_response.json()["status"]
        if status in ["completed", "failed"]:
            break
        time.sleep(5)
    
    # 5. 获取结果
    result_response = requests.get(
        f"http://localhost:8000/api/v1/backtest/{task_id}",
        headers=headers
    )
    result = result_response.json()
    
    # 6. 保存结果
    with open("backtest_result.json", "w") as f:
        json.dump(result, f, indent=2)
    
    return result

# 执行
result = automated_backtest_workflow()
print(f"回测完成！收益率: {result['total_return']:.2%}")
```

### 用例2：批量参数优化

```python
def batch_parameter_optimization():
    """批量参数优化"""
    
    # 定义参数范围
    parameter_sets = [
        {"fast_period": 5, "slow_period": 20},
        {"fast_period": 10, "slow_period": 30},
        {"fast_period": 15, "slow_period": 40},
    ]
    
    results = []
    
    for params in parameter_sets:
        # 提交回测
        response = requests.post(
            "http://localhost:8000/api/v1/backtest/run",
            headers=headers,
            json={
                "strategy_id": strategy_id,
                "symbol": "000001.SZ",
                "start_date": "2020-01-01",
                "end_date": "2023-12-31",
                "parameters": params
            }
        )
        task_id = response.json()["task_id"]
        
        # 等待完成
        wait_for_completion(task_id)
        
        # 获取结果
        result = get_result(task_id)
        results.append({
            "parameters": params,
            "sharpe_ratio": result["sharpe_ratio"],
            "total_return": result["total_return"]
        })
    
    # 找到最优参数
    best_result = max(results, key=lambda x: x["sharpe_ratio"])
    print(f"最优参数: {best_result['parameters']}")
    print(f"夏普比率: {best_result['sharpe_ratio']:.2f}")
    
    return best_result
```

### 用例3：实时监控仪表盘

```python
import websocket
import json

class BacktestMonitor:
    def __init__(self, task_id, token):
        self.task_id = task_id
        self.token = token
        self.ws = None
    
    def on_message(self, ws, message):
        data = json.loads(message)
        event_type = data.get('type')
        if event_type == 'progress':
            print(f"进度: {data['progress']}% - {data['message']}")
        
        if event_type == 'completed':
            print("✅ 回测完成！")
            self.display_summary(data['result'])
            ws.close()
    
    def on_error(self, ws, error):
        print(f"❌ 错误: {error}")
    
    def on_open(self, ws):
        print(f"🔌 已连接到回测任务: {self.task_id}")
    
    def display_summary(self, result):
        print("\n" + "="*50)
        print("📊 回测结果摘要")
        print("="*50)
        print(f"总收益率: {result['total_return']:.2%}")
        print(f"夏普比率: {result['sharpe_ratio']:.2f}")
        print(f"最大回撤: {result['max_drawdown']:.2%}")
        print(f"胜率: {result['win_rate']:.2%}")
        print(f"总交易次数: {result['total_trades']}")
        print("="*50 + "\n")
    
    def start(self):
        ws_url = f"ws://localhost:8000/ws/backtest/{self.task_id}"
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error
        )
        self.ws.run_forever()

# 使用
monitor = BacktestMonitor(task_id, token)
monitor.start()
```

---

## 附录

### A. 完整 API 端点列表

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/api/v1/auth/register` | POST | 用户注册 | ❌ |
| `/api/v1/auth/login` | POST | 用户登录 | ❌ |
| `/api/v1/auth/login/refresh` | POST | 刷新 token | ❌ |
| `/api/v1/strategy/` | GET | 策略列表 | ✅ |
| `/api/v1/strategy/` | POST | 创建策略 | ✅ |
| `/api/v1/strategy/{id}` | GET | 策略详情 | ✅ |
| `/api/v1/strategy/{id}` | PUT | 更新策略 | ✅ |
| `/api/v1/strategy/{id}` | DELETE | 删除策略 | ✅ |
| `/api/v1/strategy/templates` | GET | 策略模板 | ✅ |
| `/api/v1/backtest/run` | POST | 提交回测 | ✅ |
| `/api/v1/backtest/{task_id}` | GET | 回测结果 | ✅ |
| `/api/v1/backtest/{task_id}/status` | GET | 回测状态 | ✅ |
| `/api/v1/backtest/` | GET | 回测列表 | ✅ |
| `/api/v1/optimization/submit/backtest` | POST | 参数优化（权威入口） | ✅ |
| `/api/v1/live-trading/start` | POST | 启动实盘 | ✅ |
| `/ws/backtest/{task_id}` | WebSocket | 实时进度 | ✅ |

### B. 速率限制

| 端点类型 | 限制 | 窗口 |
|---------|------|------|
| 认证端点 | 5-10 次 | 每分钟/IP |
| API 端点 | 100 次 | 每分钟/用户 |
| 回测提交 | 10 次 | 每小时/用户 |

### C. 联系支持

- **文档**: `/docs` (Swagger UI)
- **问题反馈**: GitHub Issues
- **API 状态**: `/health` 端点

---

**最后更新**: 2026-03-07  
**版本**: 1.0.0  
**作者**: Backtrader Web Team
