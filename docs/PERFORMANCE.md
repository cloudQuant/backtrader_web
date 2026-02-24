# 性能优化指南

> 适用版本: v2.1.0 | 更新日期: 2026-02-24

本文档提供 Backtrader Web 平台的性能基准、优化建议和扩展指南。

---

## 1. 性能基准

### 1.1 API 响应时间

| 端点 | 典型响应时间 | 说明 |
|------|-------------|------|
| `GET /auth/me` | < 10ms | JWT 解码，无数据库查询 |
| `GET /strategy/templates` | < 50ms | 文件系统扫描 118 个模板 |
| `POST /backtest/run` | < 100ms | 创建任务，回测异步执行 |
| `GET /analytics/{id}/detail` | 50-200ms | 取决于结果数据大小 |
| `GET /portfolio/overview` | 100-500ms | 聚合多个实盘实例数据 |
| `GET /data/kline` | 200-2000ms | 取决于数据源（AkShare 外部调用） |

### 1.2 回测执行时间

| 场景 | 数据量 | 典型耗时 |
|------|--------|----------|
| 单标的日线 1 年 | ~250 bar | 1-3 秒 |
| 单标的日线 5 年 | ~1250 bar | 3-8 秒 |
| 单标的分钟线 1 月 | ~5760 bar | 5-15 秒 |
| 多标的日线 1 年 × 10 | ~2500 bar | 10-30 秒 |
| 参数优化 100 组合 | 取决于单次回测 | 单次 × 100 / n_workers |

### 1.3 前端加载时间

| 指标 | 开发模式 | 生产构建 |
|------|----------|----------|
| 首次加载 (FCP) | ~800ms | ~300ms |
| 可交互时间 (TTI) | ~1200ms | ~500ms |
| JS 包大小 | N/A (HMR) | ~400KB (gzip) |

---

## 2. 后端优化

### 2.1 数据库优化

#### 索引策略

```sql
-- 回测任务查询（按用户 + 状态排序）
CREATE INDEX idx_backtest_user_status ON backtest_tasks(user_id, status, created_at DESC);

-- 策略列表（按用户 + 分类）
CREATE INDEX idx_strategy_user_category ON strategies(user_id, category);

-- 告警查询（按状态 + 时间）
CREATE INDEX idx_alerts_status_time ON alerts(status, created_at DESC);
```

#### 查询优化

- 使用 `exists()` 替代 `count()` 做存在性检查
- 列表接口使用分页（默认 20 条/页）
- 回测结果中大 JSON 字段（equity_curve、trades）按需加载
- 使用 `select_in_loading` 避免 N+1 查询

#### 连接池配置

```python
# config.py 推荐配置
SQLALCHEMY_POOL_SIZE = 10          # 连接池大小
SQLALCHEMY_MAX_OVERFLOW = 20       # 溢出连接数
SQLALCHEMY_POOL_TIMEOUT = 30       # 获取连接超时（秒）
SQLALCHEMY_POOL_RECYCLE = 3600     # 连接回收时间（秒）
```

### 2.2 回测引擎优化

#### 策略加载缓存

策略模板在首次加载后缓存在内存中，避免重复的文件 I/O：

```python
# backtest_service.py 中的 LRU 缓存
@lru_cache(maxsize=256)
def _load_template_config(template_id: str) -> dict:
    ...
```

#### 多进程优化

参数优化使用多进程并行：

```python
# optimization_service.py
n_workers = min(os.cpu_count() or 4, request.n_workers)
# 每个 worker 独立运行 Backtrader Cerebro 实例
```

**建议**:
- `n_workers` 不超过 CPU 核心数
- 每个 worker 约占 200-500MB 内存
- 生产环境建议预留 2 核给 API 服务

#### 数据加载优化

```python
# 避免重复下载同一标的数据
# 使用本地缓存（文件或 Redis）
MARKET_DATA_CACHE_TTL = 3600  # K线数据缓存1小时
```

### 2.3 API 性能优化

#### 慢查询监控

系统内置 `PerformanceLoggingMiddleware`，超过 5 秒的请求自动记录：

```
[SLOW] GET /api/v1/analytics/xxx/detail - 5.2s
```

#### 限流配置

```python
# 默认限流规则
RATE_LIMIT_DEFAULT = "60/minute"     # 普通接口
RATE_LIMIT_AUTH = "10/minute"        # 登录接口
RATE_LIMIT_BACKTEST = "5/minute"     # 回测提交
```

#### 响应压缩

FastAPI 默认启用 gzip 压缩，对大响应体（回测结果 JSON）效果显著：
- 未压缩: ~500KB
- gzip 压缩后: ~80KB

---

## 3. 前端优化

### 3.1 代码分割

Vue Router 使用懒加载，每个页面独立 chunk：

```typescript
// router/index.ts
component: () => import('@/views/BacktestPage.vue')
```

### 3.2 图表性能

ECharts 大数据量优化：

- 数据量 > 1000 点时启用 `sampling: 'lttb'`（最小三角形采样）
- K 线图使用 `dataZoom` 而非全量渲染
- WebSocket 实时数据使用增量更新而非全量刷新

### 3.3 状态管理

Pinia store 优化：
- 回测历史列表使用分页加载
- 策略模板列表使用 `staleTime` 缓存（5 分钟内不重复请求）
- 大数据（equity_curve）不存入 store，直接传递给图表组件

### 3.4 构建优化

```bash
# 分析构建产物大小
npx vite-bundle-visualizer

# 生产构建配置（vite.config.ts）
build: {
  rollupOptions: {
    output: {
      manualChunks: {
        'element-plus': ['element-plus'],
        'echarts': ['echarts'],
      }
    }
  }
}
```

---

## 4. 扩展指南

### 4.1 单机扩展

| 资源 | 建议 | 说明 |
|------|------|------|
| CPU | 4 核+ | 2 核 API + 2 核回测 |
| 内存 | 8GB+ | 回测每 worker 200-500MB |
| 磁盘 | SSD | 策略日志 I/O 密集 |
| 数据库 | PostgreSQL | 生产环境替换 SQLite |

### 4.2 水平扩展

```
                    ┌─────────────┐
                    │  Nginx LB   │
                    └──────┬──────┘
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼────┐ ┌────▼─────┐ ┌────▼─────┐
        │  API 1   │ │  API 2   │ │  API 3   │
        └─────┬────┘ └────┬─────┘ └────┬─────┘
              │            │            │
              └────────────┼────────────┘
                    ┌──────▼──────┐
                    │ PostgreSQL  │
                    │  (主从)     │
                    └─────────────┘
```

**关键考虑**:
- WebSocket 连接需 sticky session（Nginx `ip_hash`）
- 回测任务应使用消息队列（Redis / RabbitMQ）分发
- 策略文件需共享存储（NFS / S3）

### 4.3 监控指标

| 指标 | 健康阈值 | 告警阈值 |
|------|----------|----------|
| API P99 延迟 | < 500ms | > 2000ms |
| 数据库连接使用率 | < 70% | > 90% |
| 内存使用 | < 70% | > 85% |
| 回测队列长度 | < 10 | > 50 |
| WebSocket 连接数 | < 100 | > 500 |

---

## 5. 常见性能问题

### 问题 1: 回测执行慢

**原因**: 策略代码中包含复杂计算（如自定义指标嵌套循环）

**解决**:
- 使用 `pandas` / `numpy` 向量化计算替代 Python 循环
- 避免在 `next()` 中做大量 I/O 操作
- 减少日志输出频率

### 问题 2: 策略模板加载慢

**原因**: 118 个模板目录的文件系统扫描

**解决**:
- 已内置 LRU 缓存
- 如果模板数量持续增长，考虑使用数据库存储元数据

### 问题 3: 前端首屏慢

**原因**: Element Plus 全量导入

**解决**:
```bash
# 使用按需导入插件
npm install unplugin-element-plus -D
```

### 问题 4: WebSocket 连接过多

**原因**: 页面切换未正确断开 WebSocket

**解决**:
- 在 Vue `onUnmounted` 中关闭 WebSocket 连接
- 服务端设置连接超时自动回收

---

*本文档持续更新，随系统演进补充新的性能数据和优化建议。*
