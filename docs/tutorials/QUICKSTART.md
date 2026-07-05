# 快速上手：5 分钟完成首次回测

本指南帮助你从零开始，在 5 分钟内启动 AI for Investor 并完成一次策略回测。

> **前置条件**：Python 3.10+、Node.js 20+、Git

---

## 第 1 步：克隆并安装（约 2 分钟）

```bash
# 克隆项目
git clone https://github.com/cloudQuant/ai-for-investor.git
cd ai-for-investor

# 后端安装
cd src/backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev,backtrader]"

# 创建最小配置（SQLite，无需额外数据库）
cp .env.example .env
```

> 默认使用 SQLite，无需安装 PostgreSQL 或 MySQL。

```bash
# 前端安装（新终端窗口）
cd src/frontend
npm install
```

---

## 第 2 步：启动服务（约 30 秒）

打开两个终端窗口：

**终端 1 - 后端：**

```bash
cd src/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

看到 `Uvicorn running on http://127.0.0.1:8000` 即启动成功。

**终端 2 - 前端：**

```bash
cd src/frontend
npm run dev
```

看到 `Local: http://localhost:3000` 即启动成功。

---

## 第 3 步：注册并登录（约 30 秒）

1. 打开浏览器访问 http://localhost:3000
2. 点击「注册」，填写用户名、邮箱和密码
3. 注册成功后自动跳转到登录页，输入账号密码登录

---

## 第 4 步：运行首次回测（约 2 分钟）

### 方式 A：通过 Web 界面（推荐新手）

1. 登录后进入「策略管理」页面
2. 从「策略模板」中选择一个内置策略（如「均线交叉策略」）
3. 点击「回测」按钮，填写参数：
   - **标的代码**：`000001.SZ`（平安银行）
   - **起止日期**：`2023-01-01` ~ `2023-12-31`
   - **初始资金**：`100000`
   - **手续费率**：`0.001`
4. 点击「开始回测」，等待完成
5. 查看回测结果：收益曲线、交易记录、绩效指标

### 方式 B：通过 API（推荐开发者）

```bash
# 1. 注册用户
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "email": "demo@example.com", "password": "Test12345678"}'

# 2. 登录获取 Token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "Test12345678"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3. 查看可用策略模板
curl -s http://localhost:8000/api/v1/strategy/templates \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 4. 提交回测任务（使用第一个模板）
curl -X POST http://localhost:8000/api/v1/backtests/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "<模板ID>",
    "symbol": "000001.SZ",
    "start_date": "2023-01-01T00:00:00",
    "end_date": "2023-12-31T00:00:00",
    "initial_cash": 100000,
    "commission": 0.001,
    "params": {}
  }'

# 5. 查询回测结果（用返回的 task_id 替换）
curl -s http://localhost:8000/api/v1/backtests/<task_id> \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### 方式 C：运行示例脚本（最快）

```bash
cd src/backend
source venv/bin/activate
pip install httpx  # 示例脚本依赖

# 一键完成注册 + 登录 + 回测
python ../../examples/backend_api_enhanced_backtest_demo.py --wait
```

脚本会自动注册用户、选择策略模板、提交回测并轮询结果。

---

## 验证成功

回测完成后，你应该能看到：

- ✅ **收益率** (total_return) - 策略总收益
- ✅ **夏普比率** (sharpe_ratio) - 风险调整后收益
- ✅ **最大回撤** (max_drawdown) - 最大亏损幅度
- ✅ **交易次数** - 策略产生的买卖信号数

在 Web 界面中还可以查看：
- 📈 资金曲线图
- 📊 K 线图 + 交易信号标注
- 📋 月度收益热力图
- 📄 导出 HTML/PDF/Excel 报告

---

## 常见问题

### Q: 后端启动报错 `ModuleNotFoundError`

确保已激活虚拟环境并安装依赖：

```bash
cd src/backend
source venv/bin/activate
pip install -e ".[dev,backtrader]"
```

### Q: 前端页面空白或 API 报 CORS 错误

确认后端运行在 8000 端口，前端 Vite 会自动代理 `/api` 请求到后端。

### Q: 回测提交后一直 pending

检查后端终端是否有报错日志。常见原因：
- 策略代码语法错误
- 数据源未配置（首次使用内置模板不需要额外数据）

### Q: 想使用 PostgreSQL/MySQL 而非 SQLite

编辑 `src/backend/.env`，修改数据库配置：

```bash
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader
```

---

## 下一步

| 目标 | 文档 |
|------|------|
| 编写自定义策略 | [策略开发指南](STRATEGY_DEVELOPMENT.md) |
| 了解完整 API | [API 文档](API_OVERVIEW.md) |
| 参数优化 | [API 文档 - 优化模块](API_OVERVIEW.md#5-optimization参数优化) |
| 模拟交易 | [API 文档 - 模拟交易](API_OVERVIEW.md#9-paper-trading模拟交易) |
| AI 策略助手 | [AI 策略 Copilot](AI_STRATEGY_COPILOT.md) |
| 本地开发环境 | [开发指南](DEVELOPMENT.md) |
| Docker 部署 | `docker/compose/prod.yml` 配合根目录 `docker-compose.yml` base |
