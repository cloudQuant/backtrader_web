# Request-Scoped Session / Unit-of-Work 模式指南

本文档说明如何使用 request-scoped session 和 unit-of-work 模式进行数据库事务管理。

## 背景

为了支持跨多个 repository 的事务操作，项目引入了 session provider 和新的 repository 模式。

### 优势

1. **事务一致性**：多个 repository 操作可以在同一个事务中执行
2. **灵活性**：repository 可以接收外部 session，支持 unit-of-work
3. **可测试性**：更容易进行单元测试和集成测试
4. **向后兼容**：旧的调用方式仍然有效

## 使用方式

### 1. 在 API 端点中使用 Request-Scoped Session

**传统方式**（仍然支持）：

```python
from fastapi import Depends
from app.models.user import User
from app.db.sql_repository import SQLRepository

@router.get("/users/{user_id}")
async def get_user(user_id: str):
    user_repo = SQLRepository(User)
    return await user_repo.get_by_id(user_id)
```

**新方式**（推荐）：

```python
from fastapi import Depends
from app.models.user import User
from app.db.sql_repository import SQLRepository
from app.db.session_provider import create_dependency

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(create_dependency())
):
    user_repo = SQLRepository(User, session=session)
    return await user_repo.get_by_id(user_id)
```

**优势**：
- 所有使用该 session 的操作都在同一个事务中
- FastAPI 自动管理 session 生命周期

### 2. Unit-of-Work 模式

用于需要确保多个 repository 操作在同一事务中完成的业务场景。

```python
from fastapi import Depends
from app.models.user import User
from app.models.backtest_task import BacktestTask
from app.db.sql_repository import SQLRepository
from app.db.session_provider import unit_of_work

@router.post("/backtest/run")
async def run_backtest(
    data: BacktestRequest,
    session: AsyncSession = Depends(create_dependency())
):
    # 使用同一个 session 创建所有 repository
    user_repo = SQLRepository(User, session=session)
    task_repo = SQLRepository(BacktestTask, session=session)
    
    try:
        # 所有操作在同一个事务中
        user = await user_repo.get_by_id(data.user_id)
        
        # 创建回测任务
        task = await task_repo.create({
            'user_id': data.user_id,
            'strategy_id': data.strategy_id,
            'symbol': data.symbol,
            'start_date': data.start_date,
            'end_date': data.end_date,
        })
        
        # 更新用户统计
        # ... 其他操作 ...
        
        # 所有操作完成
        return task
        
    except Exception as e:
        # session 会自动回滚
        raise HTTPException(status_code=500, detail=str(e))
```

### 3. 手动 Session 管理

如果需要完全控制 session 生命周期：

```python
from app.db.session_provider import SessionProvider

@router.post("/custom-operation")
async def custom_operation():
    async with SessionProvider.get_session() as session:
        # 完全手动控制
        result1 = await session.execute(query1)
        result2 = await session.execute(query2)
        await session.commit()
        return {'result1': result1, 'result2': result2}
```

### 4. Unit-of-Work 带自动提交

```python
from app.db.session_provider import unit_of_work

@router.post("/complex-operation")
async def complex_operation():
    async with unit_of_work() as session:
        # 所有操作在一个事务中
        # 自动提交
        user = await user_repo.create(user_data)
        profile = await profile_repo.create(profile_data)
        settings = await settings_repo.create(settings_data)
        
        return user
```

### 5. 创建带有外部 Session 的 Repository

某些场景下，可能需要在函数外部创建 session：

```python
from app.db.sql_repository import SQLRepository
from app.db.session_provider import unit_of_work

async def business_operation():
    async with unit_of_work() as session:
        user_repo = SQLRepository(User, session=session)
        task_repo = SQLRepository(BacktestTask, session=session)
        
        # 使用 session 执行操作
        user = await user_repo.create(user_data)
        task = await task_repo.create(task_data)
        
        return user
```

## API 端点中的最佳实践

### 推荐模式

```python
from fastapi import Depends, HTTPException
from app.models.user import User
from app.db.sql_repository import SQLRepository
from app.db.session_provider import create_dependency

@router.get("/profile/{user_id}")
async def get_profile(
    user_id: str,
    session: AsyncSession = Depends(create_dependency())
):
    user_repo = SQLRepository(User, session=session)
    
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 在同一个 session 中加载关联数据
    profile = await session.execute(
        select(Profile).where(Profile.user_id == user_id)
    ).unique()
    
    return user
```

### 复杂业务流程

```python
@router.post("/register-with-initial-data")
async def register_with_initial_data(
    registration_data: RegistrationRequest,
    session: AsyncSession = Depends(create_dependency())
):
    user_repo = SQLRepository(User, session=session)
    profile_repo = SQLRepository(Profile, session=session)
    settings_repo = SQLRepository(UserSettings, session=session)
    
    # 所有操作在同一个事务中
    user = await user_repo.create(registration_data.dict())
    profile = await profile_repo.create({
        'user_id': user.id,
        'display_name': registration_data.display_name,
    })
    settings = await settings_repo.create({
        'user_id': user.id,
        'theme': 'light',
    })
    
    return user
```

## Repository 实现

### SQLRepository 改进

现在 `SQLRepository` 支持两种模式：

1. **默认模式**（向后兼容）：每个方法自己管理 session
2. **外部 session 模式**：使用外部提供的 session

```python
from app.db.sql_repository import SQLRepository

# 默认模式
user_repo = SQLRepository(User)
user = await user_repo.create(user_data)

# 外部 session 模式
async with unit_of_work() as session:
    user_repo = SQLRepository(User, session=session)
    user = await user_repo.create(user_data)
```

### SessionProvider 工具类

提供三种 session 管理方式：

1. `get_session()` - 手动 session 上下文管理
2. `unit_of_work()` - 自动提交的事务上下文
3. `create_dependency()` - FastAPI 依赖注入

使用场景：

- **手动管理**：需要精细控制或多个异步操作不在同一个事务中
- **unit_of_work**：需要事务一致性的业务流程
- **依赖注入**：API 端点中的请求

## 测试建议

### 单元测试

使用外部 session 进行测试：

```python
from app.db.sql_repository import SQLRepository
from app.db.session_provider import unit_of_work

@pytest.mark.asyncio
async def test_create_user_with_profile():
    async with unit_of_work() as session:
        user_repo = SQLRepository(User, session=session)
        profile_repo = SQLRepository(Profile, session=session)
        
        user = await user_repo.create({'username': 'test'})
        profile = await profile_repo.create({
            'user_id': user.id,
            'bio': 'test bio',
        })
        
        assert user.username == 'test'
        assert profile.user_id == user.id
```

### 集成测试

在测试中模拟 FastAPI 依赖注入：

```python
from app.db.session_provider import SessionProvider

@pytest.mark.asyncio
async def test_api_endpoint(client: AsyncClient):
    # 模拟依赖注入
    async with SessionProvider.unit_of_work() as session:
        user_repo = SQLRepository(User, session=session)
        user = await user_repo.create({'username': 'test'})
    
    response = await client.post("/users/")
    assert response.status_code == 200
```

## 迁移指南

### 迁移步骤

1. **优先级 1**：认证流程（推荐先实现）
   - 登录 → 获取 token → 刷新 token
   - 涉及 User 和 RefreshToken 两个 repository

2. **优先级 2**：回测任务与结果写入
   - 创建任务 → 执行回测 → 写入结果
   - 涉及 BacktestTask、BacktestResult 和 Analytics 三个 repository

3. **优先级 3**：投资组合更新
   - 多个策略交易记录需要原子更新
   - 涉及 Portfolio、Position、Trade 等多个 repository

### 兼容性策略

- 新旧代码可以共存，不需要一次性大重构
- 在新代码中使用新模式，旧代码保持不变
- 随着时间积累经验，逐步迁移其他代码

## 注意事项

### 1. Session 生命周期

- 不要在异步上下文外保存 session 引用
- 不要跨请求传递 session（除非确实需要）
- 让 FastAPI 的依赖注入管理 session 生命周期

### 2. 事务边界

- 一个 unit-of_work 应该对应一个完整的业务操作
- 避免在事务中执行长时间运行的操作（如外部 API 调用）

### 3. 错误处理

- unit_of_work 会在异常时自动回滚
- 不需要在 except 中手动调用 session.rollback()
- 在 except 块中重新抛出异常以触发回滚

### 4. 性能考虑

- 过度嵌套的 unit_of_work 可能影响并发性能
- 对于只读操作，可以直接使用 get_session() 依赖注入

## 示例：认证与刷新 Token

```python
from fastapi import Depends, HTTPException
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.db.sql_repository import SQLRepository
from app.db.session_provider import create_dependency, unit_of_work

@router.post("/auth/login")
async def login(
    credentials: LoginRequest,
    session: AsyncSession = Depends(create_dependency())
):
    user_repo = SQLRepository(User, session=session)
    token_repo = SQLRepository(RefreshToken, session=session)
    
    # 在同一个事务中验证用户并创建 refresh token
    result = await session.execute(
        select(User).where(User.username == credentials.username)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # 验证密码
    if not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # 创建 refresh token
    token_data = await token_repo.create({
        'user_id': user.id,
        'token': generate_refresh_token(),
        'expires_at': calculate_expiry(),
    })
    
    return {
        'access_token': generate_access_token(user.id),
        'refresh_token': token_data.token,
    }
```

---

*最后更新: 2026-03-08*
