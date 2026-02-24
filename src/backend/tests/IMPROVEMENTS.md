# 测试改进指南

本文档提供了根据 TEA 测试审查建议的具体改进示例。

## 改进概览

| 改进项 | 优先级 | 状态 |
|--------|--------|------|
| 创建测试数据工厂 | 高 | ✅ 完成 |
| 添加断言消息 | 高 | ✅ 完成 |
| 参数化测试 | 中 | ✅ 完成 |

---

## 1. 测试数据工厂 (tests/factories.py)

### 用法示例

```python
from tests.factories import UserFactory, BacktestRequestFactory, HTTP

# 创建带默认值的用户
user = UserFactory.create()

# 创建带自定义值的用户
admin = UserFactory.create(username="admin", role="admin")

# 批量创建
users = UserFactory.create_batch(3)

# 使用 HTTP 常量
assert response.status_code == HTTP.OK  # 而不是 200
assert response.status_code == HTTP.UNAUTHORIZED  # 而不是 401
```

### 可用的工厂类

| 工厂类 | 用途 |
|--------|------|
| `UserFactory` | 用户注册/登录数据 |
| `StrategyFactory` | 策略数据 |
| `BacktestRequestFactory` | 回测请求数据 |
| `AccountFactory` | 模拟账户数据 |
| `AlertRuleFactory` | 告警规则数据 |
| `ComparisonFactory` | 对比数据 |

---

## 2. 描述性断言消息

### 改进前

```python
async def test_register_success(self, client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "password123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "newuser"
```

### 改进后

```python
async def test_register_success(self, client: AsyncClient):
    user_data = UserFactory.create()
    resp = await client.post("/api/v1/auth/register", json=user_data)

    assert resp.status_code == HTTP.OK, \
        f"Registration failed: {resp.text}"

    data = resp.json()
    assert data["username"] == user_data["username"], \
        f"Username mismatch: expected {user_data['username']}, got {data.get('username')}"
```

### 为什么这很重要？

当断言失败时：
- ❌ 改进前: `AssertionError`
- ✅ 改进后: `AssertionError: Username mismatch: expected 'newuser', got 'newuser2'`

---

## 3. 参数化测试

### 改进前 - 多个重复测试

```python
async def test_register_short_password(self, client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "username": "shortpw", "email": "short@test.com", "password": "123",
    })
    assert resp.status_code == 422

async def test_register_invalid_email(self, client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "username": "bademail", "email": "not-an-email", "password": "password123",
    })
    assert resp.status_code == 422

async def test_register_short_username(self, client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "username": "a", "email": "a@test.com", "password": "password123",
    })
    assert resp.status_code == 422
```

### 改进后 - 单个参数化测试

```python
@pytest.mark.parametrize("field,value,expected_in_error", [
    ("password", "123", "password"),      # Too short
    ("email", "not-an-email", "email"),   # Invalid format
    ("username", "", "username"),         # Empty
    ("username", "a", "username"),        # Too short
])
async def test_register_validation_errors(self, client: AsyncClient, field, value, expected_in_error):
    """Test various validation errors return 422."""
    user_data = UserFactory.create(**{field: value})
    resp = await client.post("/api/v1/auth/register", json=user_data)

    assert resp.status_code == HTTP.UNPROCESSABLE_ENTITY, \
        f"Expected 422 for invalid {field}, got {resp.status_code}: {resp.text}"

    detail = resp.json().get("detail", [])
    if isinstance(detail, list) and len(detail) > 0:
        error_loc = str(detail[0].get("loc", []))
        assert expected_in_error in error_loc
```

### 参数化测试的优势

1. **减少代码重复** - 一个测试函数覆盖多个场景
2. **更容易添加新用例** - 只需在参数列表中添加一行
3. **更清晰的测试结构** - 所有相关测试在一起
4. **更好的报告** - pytest 显示每个参数组合的结果

---

## 4. 迁移现有测试

### 步骤指南

1. **导入工厂**
   ```python
   from tests.factories import UserFactory, HTTP
   ```

2. **替换硬编码数据**
   ```python
   # 之前
   "username": "testuser",
   "email": "test@example.com",
   "password": "password123"

   # 之后
   UserFactory.create()
   ```

3. **添加断言消息**
   ```python
   # 之前
   assert resp.status_code == 200

   # 之后
   assert resp.status_code == HTTP.OK, f"Request failed: {resp.text}"
   ```

4. **合并重复测试**
   ```python
   # 使用 @pytest.mark.parametrize 合并相似测试
   ```

---

## 5. 参考示例

查看 `test_auth_improved.py` 获取完整的改进示例。

### 运行改进后的测试

```bash
cd src/backend
pytest tests/test_auth_improved.py -v
```

---

## 6. 下一步建议

1. **将改进应用到所有测试文件**
   - 优先级: API 测试 > 服务测试 > 工具测试

2. **添加性能基准测试**
   ```python
   @pytest.mark.performance
   async def test_login_performance(benchmark, client):
       async def login():
           return await client.post("/api/v1/auth/login", json={...})
       result = await benchmark(login)
       assert result.status_code == 200
   ```

3. **集成 E2E 测试**
   - 使用 Playwright 添加前端集成测试

---

*文档创建日期: 2026-02-24*
*基于 TEA 测试审查建议*
