# Database Design

## Supported Databases

- **SQLite** (default) - Zero configuration, good for development
- **PostgreSQL** - Recommended for production
- **MySQL** - Alternative for production

## Database URL Configuration

```bash
# SQLite
DATABASE_URL=sqlite:///./backtrader.db

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader

# MySQL
DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/backtrader
```

## Key Tables

### users

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| username | String | Unique username |
| email | String | Unique email |
| password_hash | String | Bcrypt hashed password |
| is_active | Boolean | Account status |
| is_admin | Boolean | Admin role |
| created_at | DateTime | Creation time |

### strategies

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| user_id | Integer | Owner user ID |
| name | String | Strategy name |
| description | Text | Strategy description |
| code | Text | Strategy code |
| parameters | JSON | Strategy parameters |
| is_template | Boolean | Built-in template |
| created_at | DateTime | Creation time |
| updated_at | DateTime | Last update |

### strategy_versions

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| strategy_id | Integer | Parent strategy |
| version_name | String | Version name |
| version_hash | String | Content hash |
| code | Text | Strategy code at this version |
| message | String | Version message |
| is_default | Boolean | Default version |
| created_at | DateTime | Creation time |

### backtest_tasks

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| user_id | Integer | Owner user ID |
| strategy_id | Integer | Strategy used |
| status | String | pending/running/completed/failed |
| parameters | JSON | Backtest parameters |
| result | JSON | Backtest results |
| created_at | DateTime | Creation time |
| completed_at | DateTime | Completion time |

### paper_trading_sessions

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| user_id | Integer | Owner user ID |
| name | String | Session name |
| initial_cash | Float | Starting capital |
| status | String | active/stopped |
| created_at | DateTime | Creation time |

### optimization_tasks

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| user_id | Integer | Owner user ID |
| strategy_id | Integer | Strategy used |
| status | String | pending/running/completed/failed |
| method | String | grid/bayesian |
| parameters | JSON | Optimization parameters |
| results | JSON | Optimization results |
| created_at | DateTime | Creation time |

## Migrations

Database migrations are handled by Alembic.

```bash
# Create migration
alembic revision --autogenerate -m "add column"

# Run migrations
alembic upgrade head
```

## Performance Indexes

Key indexes are created for:
- `backtest_tasks.user_id, status`
- `optimization_tasks.user_id, status`
- `paper_trading_orders.session_id`
