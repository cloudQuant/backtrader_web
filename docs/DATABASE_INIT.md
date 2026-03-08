# 数据库初始化指南

本文档说明如何初始化 Backtrader Web 数据库。

## 重要变更

**自 2026-03-08 起，数据库初始化不再在应用启动时自动执行。**

这是为了更好的生产环境部署实践：
1. 明确区分应用启动和基础设施初始化
2. 避免在生产环境中隐式执行数据库结构变更
3. 为后续引入数据库迁移工具（如 Alembic）预留接口
4. 提供更清晰的权限和审计边界

## 开发环境初始化

### 首次启动

在首次启动应用之前，运行初始化脚本：

```bash
cd src/backend

# 初始化所有内容（表 + 默认管理员）
python scripts/init_db.py --init-all
```

### 或分步初始化

```bash
# 1. 创建数据库表
python scripts/init_db.py --create-tables

# 2. 创建默认管理员账户
python scripts/init_db.py --create-admin
```

### 启动应用

```bash
# 启动应用（不再自动初始化数据库）
uvicorn app.main:app --reload --port 8000
```

## 生产环境初始化

### 推荐流程

1. **配置数据库**

在服务器上配置好 PostgreSQL 或 MySQL，确保数据库连接字符串正确。

2. **初始化数据库结构**

```bash
# 创建表
python scripts/init_db.py --create-tables
```

3. **创建管理员账户**

根据安全策略，创建管理员账户：

**选项 1：使用脚本（仅开发/测试环境）**

```bash
python scripts/init_db.py --create-admin
```

**选项 2：通过 API 创建（推荐用于生产）**

1. 启动应用
2. 注册第一个用户账户
3. 在数据库中将该用户标记为管理员（通过数据库直接操作或 API）

### 安全注意事项

1. **修改默认管理员密码**

环境变量 `ADMIN_PASSWORD` 仅用于开发环境。生产环境必须：

- 修改 `src/backend/.env` 中的 `ADMIN_PASSWORD` 为强密码
- 或通过 API 注册第一个管理员账户
- 启动后立即修改密码

2. **数据库迁移**

目前版本使用 SQLAlchemy 的 `create_all` 方法。未来的版本将引入 Alembic 进行迁移管理。

## 初始化脚本说明

### 脚本位置

`src/backend/scripts/init_db.py`

### 脚本选项

- `--create-tables`：创建所有数据库表
- `--create-admin`：创建默认管理员账户
- `--init-all`：执行以上两个步骤（推荐）

### 何时需要重新初始化

1. 首次部署应用
2. 更换数据库或清空数据库后
3. 修改数据模型结构后（在引入迁移工具前）
4. 需要重置管理员账户时

## 故障排查

### 问题：应用启动时报告"数据库表不存在"

**解决方案**：运行初始化脚本

```bash
cd src/backend
python scripts/init_db.py --create-tables
```

### 问题：无法登录默认管理员账户

**解决方案 1**：确认初始化已执行

```bash
cd src/backend
python scripts/init_db.py --create-admin
```

**解决方案 2**：检查环境变量

确认 `.env` 文件中的配置：

```bash
grep "ADMIN_" src/backend/.env
```

应该看到：
```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_EMAIL=admin@example.com
```

### 问题：生产环境数据库初始化失败

**检查项**：

1. 数据库连接是否正确
2. 数据库用户是否有创建表的权限
3. 磁盘空间是否充足

**日志位置**：`logs/backend.log`

## 版本历史

- **2026-03-08**: 移除应用启动时的隐式初始化，引入显式初始化脚本

---

*最后更新: 2026-03-08*
