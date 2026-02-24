# 数据库设计

本文档描述 Backtrader Web 的数据库模型设计。

## 数据库选择

- **开发环境**: SQLite (无需额外安装)
- **生产环境**: PostgreSQL / MySQL

## 核心表结构

### 用户表 (users)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(36) | 主键 UUID |
| username | String(50) | 用户名 (唯一) |
| email | String(100) | 邮箱 (唯一) |
| hashed_password | String(255) | 加密密码 |
| is_active | Boolean | 是否激活 |
| is_admin | Boolean | 是否管理员 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

### 索引
- `idx_username` on username
- `idx_email` on email

### 刷新令牌表 (refresh_tokens)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(64) | 主键 (token_hash) |
| token_hash | String(128) | Token哈希 (唯一) |
| user_id | String(36) | 用户ID (外键) |
| expires_at | DateTime | 过期时间 |
| created_at | DateTime | 创建时间 |
| revoked_at | DateTime | 撤销时间 |
| is_revoked | Boolean | 是否已撤销 |

### 索引
- `idx_token_hash` on token_hash
- `idx_user_id` on user_id
- `idx_is_revoked` on is_revoked

### 策略表 (strategies)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(36) | 主键 UUID |
| user_id | String(36) | 所有者ID (外键) |
| name | String(100) | 策略名称 |
| description | Text | 策略描述 |
| code | Text | 策略代码 |
| params | JSON | 参数定义 |
| category | String(50) | 分类 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

### 索引
- `idx_user_id` on user_id
- `idx_category` on category

### 回测任务表 (backtest_tasks)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(36) | 主键 UUID |
| user_id | String(36) | 用户ID (外键) |
| strategy_id | String(36) | 策略ID (外键) |
| symbol | String(20) | 交易标的 |
| status | String(20) | 状态 (pending/running/completed/failed) |
| request_data | JSON | 请求数据 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

### 索引
- `idx_user_id` on user_id
- `idx_strategy_id` on strategy_id
- `idx_status` on status
- `idx_created_at` on created_at

### 回测结果表 (backtest_results)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(36) | 主键 UUID |
| task_id | String(36) | 任务ID (外键) |
| total_return | Float | 总收益率 |
| annual_return | Float | 年化收益率 |
| sharpe_ratio | Float | 夏普比率 |
| max_drawdown | Float | 最大回撤 |
| win_rate | Float | 胜率 |
| total_trades | Integer | 总交易次数 |
| equity_curve | JSON | 资金曲线 |
| trades | JSON | 交易记录 |
| metrics_source | String(20) | 指标来源 |

### 索引
- `idx_task_id` on task_id (唯一)

### 模拟交易账户表 (paper_accounts)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(36) | 主键 UUID |
| user_id | String(36) | 用户ID (外键) |
| name | String(100) | 账户名称 |
| initial_cash | Float | 初始资金 |
| current_cash | Float | 当前现金 |
| created_at | DateTime | 创建时间 |

### 模拟交易订单表 (paper_orders)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(36) | 主键 UUID |
| account_id | String(36) | 账户ID (外键) |
| symbol | String(20) | 交易标的 |
| side | String(10) | 方向 (buy/sell) |
| quantity | Float | 数量 |
| price | Float | 价格 |
| status | String(20) | 状态 |
| created_at | DateTime | 创建时间 |

### 索引
- `idx_account_id` on account_id
- `idx_status` on status

### 告警表 (alerts)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(36) | 主键 UUID |
| user_id | String(36) | 用户ID (外键) |
| name | String(100) | 告警名称 |
| type | String(20) | 类型 |
| condition | JSON | 触发条件 |
| is_active | Boolean | 是否启用 |
| created_at | DateTime | 创建时间 |

### 索引
- `idx_user_id` on user_id
- `idx_is_active` on is_active

## ER 图

```
┌─────────────┐
│    users    │
└──────┬──────┘
       │
       ├── refresh_tokens
       ├── strategies
       ├── backtest_tasks
       ├── paper_accounts
       └── alerts

┌─────────────┐           ┌──────────────┐
│backtest_tasks│───────────│backtest_results│
└─────────────┘           └──────────────┘

┌─────────────┐           ┌──────────────┐
│paper_accounts│───────────│ paper_orders │
└─────────────┘           └──────────────┘
```

## 数据迁移

### 初始化数据库

```python
from app.db.database import init_db

await init_db()
```

### 表创建策略

- 使用 SQLAlchemy ORM 自动创建
- 支持版本化迁移 (可选 Alembic)

## 备份策略

### SQLite

```bash
# 备份
cp backtrader.db backtrader.db.backup

# 恢复
cp backtrader.db.backup backtrader.db
```

### PostgreSQL

```bash
# 备份
pg_dump backtrader_web > backup.sql

# 恢复
psql backtrader_web < backup.sql
```

## 性能优化

### 索引策略

- 为外键创建索引
- 为常用查询字段创建索引
- 复合索引优化多条件查询

### 查询优化

- 使用批量操作
- 避免循环查询
- 使用连接查询 (eager loading)

### 缓存策略

```python
# Redis 缓存回测结果
await cache.set(f"backtest:{task_id}", result, ttl=3600)
```
