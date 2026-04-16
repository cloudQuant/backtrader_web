# 数据库设计

## 支持的数据库

- **SQLite** (默认) - 零配置，适合开发
- **PostgreSQL** - 推荐用于生产
- **MySQL** - 备选用于生产

## 数据库 URL 配置

```bash
# SQLite
DATABASE_URL=sqlite:///./backtrader.db

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader

# MySQL
DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/backtrader
```

## 核心表

### users

| 列 | 类型 | 说明 |
|----|------|------|
| id | Integer | 主键 |
| username | String | 唯一用户名 |
| email | String | 唯一邮箱 |
| password_hash | String | Bcrypt 加密密码 |
| is_active | Boolean | 账户状态 |
| is_admin | Boolean | 管理员角色 |
| created_at | DateTime | 创建时间 |

### strategies

| 列 | 类型 | 说明 |
|----|------|------|
| id | Integer | 主键 |
| user_id | Integer | 所有者用户 ID |
| name | String | 策略名称 |
| description | Text | 策略描述 |
| code | Text | 策略代码 |
| parameters | JSON | 策略参数 |
| is_template | Boolean | 内置模板 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 最后更新时间 |

### strategy_versions

| 列 | 类型 | 说明 |
|----|------|------|
| id | Integer | 主键 |
| strategy_id | Integer | 父策略 ID |
| version_name | String | 版本名称 |
| version_hash | String | 内容哈希 |
| code | Text | 此版本的策略代码 |
| message | String | 版本消息 |
| is_default | Boolean | 默认版本 |
| created_at | DateTime | 创建时间 |

### backtest_tasks

| 列 | 类型 | 说明 |
|----|------|------|
| id | Integer | 主键 |
| user_id | Integer | 所有者用户 ID |
| strategy_id | Integer | 使用的策略 |
| status | String | pending/running/completed/failed |
| parameters | JSON | 回测参数 |
| result | JSON | 回测结果 |
| created_at | DateTime | 创建时间 |
| completed_at | DateTime | 完成时间 |

### paper_trading_sessions

| 列 | 类型 | 说明 |
|----|------|------|
| id | Integer | 主键 |
| user_id | Integer | 所有者用户 ID |
| name | String | 会话名称 |
| initial_cash | Float | 起始资金 |
| status | String | active/stopped |
| created_at | DateTime | 创建时间 |

### optimization_tasks

| 列 | 类型 | 说明 |
|----|------|------|
| id | Integer | 主键 |
| user_id | Integer | 所有者用户 ID |
| strategy_id | Integer | 使用的策略 |
| status | String | pending/running/completed/failed |
| method | String | grid/bayesian |
| parameters | JSON | 优化参数 |
| results | JSON | 优化结果 |
| created_at | DateTime | 创建时间 |

## 迁移

数据库迁移由 Alembic 处理。

```bash
# 创建迁移
alembic revision --autogenerate -m "add column"

# 运行迁移
alembic upgrade head
```

## 性能索引

为以下字段创建索引：
- `backtest_tasks.user_id, status`
- `optimization_tasks.user_id, status`
- `paper_trading_orders.session_id`
