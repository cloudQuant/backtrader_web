# WS Gateway Migration Plan

本文档记录当前项目内尚未统一接入 `app/services/ws_gateway/` 的 WebSocket 入口，并给出迁移优先级。

---

## 1. 当前状态

### 已接入新网关的能力

- `data_topics` 已通过 `get_shared_ws_gateway()` 与 `DataTopicHub` 联动
- 路径：`app/api/data_topics.py`
- 说明：当前 `data-topics` 已作为新网关与 topic fan-out 的参考实现

### 尚未迁移的已发现 WebSocket 路由

| 文件 | 路由 | 当前用途 | 建议优先级 |
|---|---|---|---|
| `app/api/realtime_data.py` | `/ws/ticks/{broker_id}` | 实时行情 tick 推送 | P0 |
| `app/api/paper_trading.py` | `/ws/account/{account_id}` | 纸交易账户实时更新 | P0 |
| `app/api/monitoring.py` | `/ws/alerts` | 告警流 | P1 |
| `app/api/strategy_version.py` | `/ws/strategies/{strategy_id}` | 策略版本状态流 | P1 |

---

## 2. 迁移原则

1. **保持旧路由 URL 不变**，只替换其底层连接管理与 fan-out 实现。
2. **先统一连接生命周期**：鉴权、心跳、订阅、断连清理。
3. **先迁高价值读路径**，不要在 171 早期混入高风险写路径。
4. **事件源通过 topic / subscription router 暴露**，不要让页面直接耦合具体 service 的 broadcast 细节。
5. **每迁一条路由，补一组测试**，至少覆盖：鉴权失败、订阅成功、fan-out、断连清理。

---

## 3. 171 建议迁移顺序

### 171A

- `realtime_data.py` `/ws/ticks/{broker_id}`
- `paper_trading.py` `/ws/account/{account_id}`

原因：

- 与 FinceptTerminal 的实时 terminal 使用场景最接近
- 与 `DataTopicHub` / broker / portfolio 能力联动价值最高
- 最适合作为统一 topic fan-out 的第二批迁移对象

### 171B

- `monitoring.py` `/ws/alerts`
- `strategy_version.py` `/ws/strategies/{strategy_id}`

原因：

- 业务价值高，但与核心行情/账户流相比优先级略低
- 更适合在新网关模型稳定后迁移

---

## 4. 每条路由的迁移动作模板

对于每个旧 WS 路由，按以下方式迁移：

1. 抽离当前 route 内的连接/心跳/订阅逻辑
2. 改为使用 `get_shared_ws_gateway()` 管理连接
3. 若消息源天然适合 topic 化，则通过 `DataTopicHub` 推送
4. 若消息源暂不适合 topic 化，则至少统一到 `ws_gateway.publish(...)`
5. 保留原协议字段，避免前端一次性大改
6. 补测试与验证记录

---

## 5. 171 验收目标

- 至少 2 条旧 WS 路由迁移到 `ws_gateway`
- 迁移后不破坏已有前端消费者
- `tests/test_ws_gateway.py` 扩展覆盖迁移后的真实路由场景
- 文档中明确哪些 WS 路由仍未迁移，避免状态失真
