# 快速上手指南

本指南将帮助你在 5 分钟内完成首次回测。

## 前置条件

- Python 3.10+
- 已完成 [安装指南](INSTALLATION.md)

## 第一步：启动后端服务

```bash
cd src/backend
source venv/bin/activate  # Windows: venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

## 第二步：注册用户

访问 http://localhost:8000/docs

使用 `/api/v1/auth/register` 接口注册：

```json
{
  "username": "myuser",
  "email": "myuser@example.com",
  "password": "SecurePass123!"
}
```

## 第三步：登录获取 Token

使用 `/api/v1/auth/login` 接口登录：

```json
{
  "username": "myuser",
  "password": "SecurePass123!"
}
```

保存返回的 `access_token`。

## 第四步：运行回测

使用 `/api/v1/backtest/run` 接口运行回测：

```json
{
  "strategy_id": "ma_cross",
  "symbol": "000001.SZ",
  "start_date": "2023-01-01T00:00:00",
  "end_date": "2024-01-01T00:00:00",
  "initial_cash": 100000,
  "commission": 0.001
}
```

## 第五步：查看结果

使用返回的 `task_id` 通过 `/api/v1/backtest/results/{task_id}` 获取结果。

## 下一步

- 阅读 [策略开发指南](STRATEGY_DEVELOPMENT.md)
- 了解 [参数优化功能](OPTIMIZATION.md)
- 查看 [完整 API 文档](API.md)
