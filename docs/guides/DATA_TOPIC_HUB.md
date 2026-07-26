# Data Topic Hub 指南

这份指南说明迭代 170 新增的 `DataTopicHub` 是什么、当前实现支持哪些 TopicPolicy 字段、以及它如何为 quote / history / news / option 等能力提供统一主题层。

## 当前实现位置

- `src/backend/app/services/data_topic_hub.py`
- `src/backend/app/api/data_topics.py`
- `src/backend/tests/test_data_topic_hub.py`

共享单例入口：

```python
from app.services.data_topic_hub import get_shared_data_topic_hub
```

## 核心概念

`DataTopicHub` 提供统一的主题注册、缓存读取、订阅与 producer 刷新语义。

主要对象：

- **`TopicPolicy`**：定义某个 topic 的缓存与 fan-out 行为。
- **`Producer`**：上游数据生产者，声明自己能刷新哪些 topic。
- **`DataTopicHub`**：管理 topic state、subscription、coalesce 和错误通知。

## TopicPolicy 字段

当前已实现字段：

| 字段 | 含义 |
|---|---|
| `ttl_ms` | 缓存新鲜期。未过期时 `peek()` 直接返回缓存值。 |
| `min_interval_ms` | 刷新节流。距离上次 refresh 太近时直接复用旧值。 |
| `refresh_timeout_ms` | producer 刷新超时时间。超时会发出 `refresh_timeout` 错误事件。 |
| `push_only` | 只允许 producer 主动 push；`request()` / `peek()` 不主动拉。 |
| `coalesce_within_ms` | 高频 push 合并窗口；窗口内只投递最后一个值。 |
| `drop_on_idle` | 当前字段已存在并可配置；MVP 里测试覆盖了 topic retire 路径。 |
| `pause_when_inactive` | 当前字段已入模，保留给后续页面可见性控制。 |

## 当前公开语义

### 注册 topic

```python
hub.register_topic("market:quote:RB2510", TopicPolicy(ttl_ms=200))
```

### 注册 producer

```python
hub.register_producer(my_producer)
```

producer 需要提供：

- `topic_patterns()`
- `refresh(topics)`
- `max_requests_per_sec()`

### 读取缓存

```python
value = await hub.peek("market:quote:RB2510")
```

### 直接读取原始值

```python
value = hub.peek_raw("market:quote:RB2510")
```

### 强制刷新

```python
value = await hub.request("market:quote:RB2510", force=True)
```

### 订阅

```python
subscription_id = hub.subscribe("page-1", "market:quote:*", callback)
```

支持 `fnmatch` 风格 pattern，例如：

- `market:quote:*`
- `market:history:*`

### 取消订阅

```python
hub.unsubscribe(subscription_id)
```

### 错误订阅

```python
hub.subscribe_errors(error_callback)
```

### 主动 push

```python
await hub.push("market:quote:RB2510", {"price": 102})
```

### retire topic

```python
hub.retire_topic("market:quote:RB2510")
```

## REST API

当前最小 API 在 `app/api/data_topics.py`：

### 注册 topic

```http
POST /api/v1/data-topics/register
```

请求示例：

```json
{
  "topic": "market:quote:RB2510",
  "policy": {
    "ttl_ms": 200,
    "coalesce_within_ms": 50
  }
}
```

### Peek

```http
GET /api/v1/data-topics/{topic}/peek
```

### Push

```http
POST /api/v1/data-topics/{topic}/push
```

请求示例：

```json
{
  "value": {
    "price": 101.5
  }
}
```

## 命名建议

当前项目中建议沿用以下命名约定：

- `market:quote:<symbol>`
- `market:history:<symbol>:<period>:<interval>`
- `news:symbol:<symbol>`
- `option:chain:<symbol>:<expiry>`
- `broker:<broker>:<account>:positions`

## 错误模型

当前 `_emit_error()` 会向错误订阅者广播结构化字典。已覆盖的典型错误：

```json
{
  "topic": "market:history:RB2510:D1:1d",
  "code": "refresh_timeout"
}
```

另外也可能出现：

- `refresh_failed`

## 当前测试覆盖

`tests/test_data_topic_hub.py` 已覆盖：

- TTL 缓存命中
- `push_only`
- `coalesce_within_ms`
- `retire_topic`
- `refresh_timeout_ms`
- `subscribe_errors`

## 当前限制

- `drop_on_idle` / `pause_when_inactive` 目前主要是契约字段，尚未形成完整后台清理与页面可见性暂停机制。
- 目前 `Producer.max_requests_per_sec()` 还没有接入统一调度器，只作为接口保留。
- 目前还没有独立 `/stats` 和 WebSocket `/ws/data-topics/*` 路由，后续可在 `ws_gateway` 统一接入。
