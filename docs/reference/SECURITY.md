# 安全指南

本文档介绍 Backtrader Web 的安全最佳实践。

## 认证安全

### 密码策略

- 最小长度: 8 个字符
- 必须包含: 大写字母、小写字母、数字、特殊字符
- 使用 bcrypt 加密存储 (cost=12)

### JWT Token

- Access Token 有效期: 24 小时
- Refresh Token 有效期: 30 天
- Refresh Token 轮换机制
- 使用 SHA-256 哈希存储 Refresh Token

### 密钥管理

```bash
# 生成安全密钥
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 在生产环境中设置
SECRET_KEY=<生成的密钥>
JWT_SECRET_KEY=<另一个生成的密钥>
```

## 输入验证

### SQL 注入防护

使用参数化查询，避免字符串拼接：

```python
# ✅ 正确
await session.execute(
    select(User).where(User.id == user_id)
)

# ❌ 错误
await session.execute(
    f"SELECT * FROM users WHERE id = '{user_id}'"
)
```

### XSS 防护

- 所有用户输入都需要经过验证和清理
- 使用 Content-Security-Policy 头
- 对输出进行 HTML 转义

### 命令注入防护

```python
# ✅ 正确 - 使用参数验证
from app.utils.validation import detect_command_injection

if detect_command_injection(user_input):
    raise InvalidInputError("Invalid input")

# ❌ 错误 - 直接使用用户输入
os.system(f"process_data {user_input}")
```

## API 安全

### 速率限制

- 认证接口: 10 次/分钟
- 其他接口: 60 次/分钟
- 超过限制返回 429 状态码

### CORS 配置

```python
# 生产环境 CORS 配置
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

### HTTPS

生产环境必须使用 HTTPS：

```python
# 强制 HTTPS
SECURE_SSL_REDIRECT=true
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
```

## 数据安全

### 敏感数据加密

- 密码: bcrypt 加密
- API 密钥: 加密存储
- 数据库: 使用 SSL 连接

### 数据备份

- 定期备份数据库
- 异地存储备份
- 测试恢复流程

### 日志安全

- 不记录敏感信息 (密码、Token)
- 日志文件权限控制
- 定期清理旧日志

## 权限控制

### 用户隔离

- 用户只能访问自己的数据
- 管理员可以访问所有数据
- 使用 RBAC (基于角色的访问控制)

### API 权限检查

```python
# 检查资源所有权
if task.user_id != current_user.id and not current_user.is_admin:
    raise InsufficientPermissionsError(resource="backtest_task")
```

## 安全配置检查清单

### 部署前检查

- [ ] 修改默认 SECRET_KEY
- [ ] 修改默认 JWT_SECRET_KEY
- [ ] 修改默认管理员密码
- [ ] 配置 CORS_ORIGINS
- [ ] 启用 HTTPS
- [ ] 配置速率限制
- [ ] 关闭 DEBUG 模式

### 环境变量

```bash
# 必须修改
SECRET_KEY=change-me-in-production
JWT_SECRET_KEY=change-me-in-production
ADMIN_PASSWORD=change-me-in-production

# 生产环境
DEBUG=false
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
```

## 安全监控

### 日志监控

监控以下安全事件：

- 登录失败
- 速率限制触发
- 异常请求
- SQL 注入尝试

### 告警通知

配置关键安全事件的告警：

```python
from app.utils.logger import audit_logger

# 登录失败告警
audit_logger.log_login(username, success=False, ip=client_ip)
```

## 定期安全审查

### 代码审查

- 检查 SQL 查询
- 检查用户输入处理
- 检查权限验证

### 依赖更新

```bash
# 检查过期的依赖
pip list --outdated

# 更新依赖
pip install --upgrade package_name
```

### 漏洞扫描

```bash
# 安全扫描
pip install safety
safety check

# 代码扫描
pip install bandit
bandit -r app/
```

## 常见安全问题

### 1. 默认凭证

**问题**: 使用默认的密钥和密码

**解决**: 部署前必须修改所有默认值

### 2. 调试模式

**问题**: 生产环境开启 DEBUG

**解决**: 设置 `DEBUG=false`

### 3. 敏感信息泄露

**问题**: 错误信息暴露敏感数据

**解决**: 使用统一错误处理

### 4. 不安全的反序列化

**问题**: 直接反序列化用户输入

**解决**: 使用 Pydantic 验证所有输入

## 安全资源

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP Python Security](https://cheatsheetseries.owasp.org/cheatsheets/Python_Security_Cheat_Sheet.html)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
