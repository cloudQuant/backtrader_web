# `bt_api_py` Broker Contract 指南

这份指南说明迭代 170 为独立第三方包 `bt_api_py` 新增的 broker contract 是什么、当前有哪些类型与错误码、以及 bridge 写路径为什么默认关闭。

## 当前生效的架构边界

- `bt_api_py` 继续承担统一 broker contract 与 `btapibroker` 集成路径。
- `ai-for-trader` 是消费方，不再继续扩 broker registry / adapter / native-paper 实装平台。
- 后续新增交易所 / 券商接入，优先按独立 `bt_api_xx` 包演进，并与现有 `bt_api_py` 模式保持兼容。

## 重要约束

`bt_api_py` 是独立 Python 包，不应在 `ai-for-trader/src/bt_api_py` 中直接扩展。

当前新增实现位于独立仓：

```text
/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/brokers
```

## 当前文件

- `bt_api_py/brokers/base.py`
- `bt_api_py/brokers/types.py`
- `bt_api_py/brokers/errors.py`
- `bt_api_py/brokers/mock.py`
- `bt_api_py/brokers/gateway_bridge.py`
- `bt_api_py/testing/contract_cases.py`

## 后续扩展方向

- `bt_api_py` 保持统一抽象层、测试契约与 backtrader 集成层稳定。
- 单个交易所 / 券商的具体实现，优先拆分到独立 `bt_api_xx` 包。
- `ai-for-trader` 侧如果需要配合，只做统一消费、展示、调度、审计与文档边界，不再承接 broker 主实现。

相关执行文档：

- `docs/plans/2026-05-26-bt-api-ecosystem-implementation-plan.md`
- `docs/plans/2026-05-26-first-bt-api-xx-package-spec.md`

## 抽象基类

`BrokerAdapter` 当前要求以下方法：

- `connect()`
- `disconnect()`
- `health()`
- `capabilities()`
- `list_accounts()`
- `get_account(account_id)`
- `list_positions(account_id)`
- `list_orders(account_id)`
- `place_order(request)`
- `cancel_order(request)`
- `get_quote(symbol)`
- `stream_events()`

当前 `stream_events()` 提供默认 async iterator 占位。

## 当前类型

### `BrokerCapabilities`

当前能力位字段：

- `supports_market_data`
- `supports_order_submit`
- `supports_order_cancel`
- `supports_positions`
- `supports_account`
- `supports_streaming`
- `supports_native_paper`
- `supports_margin`
- `supports_options`
- `supports_destructive_write`

可以通过：

```python
caps.as_dict()
```

转换为可序列化字典。

### `OrderRequest`

字段：

- `account_id`
- `symbol`
- `side`
- `quantity`
- `order_type`
- `price`
- `client_order_id`
- `idempotency_key`
- `extra`

### `CancelOrderRequest`

字段：

- `account_id`
- `order_id`
- `symbol`
- `idempotency_key`

### `OrderSnapshot`

字段：

- `order_id`
- `account_id`
- `symbol`
- `side`
- `quantity`
- `status`
- `order_type`
- `price`
- `filled_quantity`
- `average_price`
- `submitted_at`
- `updated_at`

### `PositionSnapshot`

字段：

- `account_id`
- `symbol`
- `quantity`
- `average_price`
- `market_price`
- `unrealized_pnl`

### `AccountSnapshot`

字段：

- `account_id`
- `currency`
- `cash`
- `equity`
- `margin_used`
- `available_cash`
- `updated_at`

## 错误码

当前 `BrokerErrorCode` 包含：

- `AUTH_FAILED`
- `RATE_LIMITED`
- `NETWORK_ERROR`
- `NOT_SUPPORTED`
- `INVALID_ORDER`
- `INSUFFICIENT_FUNDS`
- `ORDER_NOT_FOUND`

`BrokerError` 结构：

- `code`
- `message`
- `retryable`
- `cause`

可通过：

```python
error.to_dict()
```

输出：

```json
{
  "code": "not_supported",
  "message": "bridge write path disabled",
  "retryable": false
}
```

## MockBrokerAdapter

`MockBrokerAdapter` 用于：

- 合约测试
- 本地开发
- 不依赖真实券商 SDK 的 smoke test

当前 contract smoke test 已验证：

- `run_broker_contract_cases(MockBrokerAdapter())` 返回 `passed=True`
- `method_count >= 12`
- `supports_native_paper = True`
- 独立 `bt_api_py` 仓已新增 `tests/test_broker_contract.py`，并通过 `pytest tests/test_broker_contract.py --cov=bt_api_py.brokers.mock --cov-report=term-missing -q --tb=short` 回放到 **MockBrokerAdapter 100.00% coverage**

### 验证边界

- 在 `ai-for-trader` 仓内，推荐把 `tests/test_broker_contract.py` 作为集成 smoke test 回放。
- `MockBrokerAdapter` 的覆盖率 gate 需要回到独立 editable 仓 `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py` 执行。
- 原因是 `ai-for-trader/src/backend/.coveragerc` 当前固定 `source = app`，只统计 backend `app` 包；而 `bt_api_py.brokers.mock` 的实际导入路径位于独立仓。
- 因此，`ai-for-trader/src/backend` 下的 `pytest --cov=bt_api_py.brokers.mock ...` 不再视作本仓稳定验收命令。

## GatewayBridgeAdapter

`GatewayBridgeAdapter` 是把现有 gateway 能力桥接到标准合约的最小适配层。

当前行为：

- `health()` 返回：
  - `connected`
  - `adapter="gateway_bridge"`
  - `gateway`
- `list_accounts()` / `get_account()` 返回最小账户快照
- `list_positions()` / `list_orders()` 当前返回空列表
- `get_quote()` 返回占位 quote

### 为什么写路径默认关闭

`place_order()` 和 `cancel_order()` 当前默认受环境变量保护：

```bash
BT_API_PY_BRIDGE_ENABLE_WRITE=0
```

只有当：

```bash
BT_API_PY_BRIDGE_ENABLE_WRITE=1
```

时，bridge 才会暴露 `supports_destructive_write=True`。

即便打开该开关，当前实现仍然：

- 先通过 feature flag
- 再抛出 `NotImplementedError`

所以本轮仅是**只读桥接 MVP**，不是实盘写路径开放。

## 合约测试

统一合约测试入口：

```python
from bt_api_py.testing.contract_cases import run_broker_contract_cases
```

当前 contract case 会验证：

- 连接 / 断开
- health
- capabilities
- 账户读取
- 持仓读取
- 订单读取
- 下单
- quote

返回结构示例：

```json
{
  "passed": true,
  "method_count": 12,
  "capabilities": {
    "supports_market_data": true,
    "supports_order_submit": true,
    "supports_destructive_write": false
  }
}
```

在 `ai-for-trader` 仓内，当前推荐的最小回放命令是：

```bash
pytest tests/test_broker_contract.py -q --tb=short
```

在独立 `bt_api_py` 仓内，当前 coverage gate 回放命令是：

```bash
pytest tests/test_broker_contract.py --cov=bt_api_py.brokers.mock --cov-report=term-missing -q --tb=short
```

## 凭证与安全约定

当前项目约束是：

- **不要**把真实券商密钥写进数据库明文字段
- 优先存环境变量名引用
- API 响应只能返回脱敏信息

推荐环境变量占位：

```bash
BT_API_PY_BRIDGE_ENABLE_WRITE=0
BT_BROKER_SIM_KEY=replace-with-broker-key
BT_BROKER_SIM_SECRET=replace-with-broker-secret
```

## 当前限制

- 还没有 `registry.py` / `capabilities.py` 独立模块。
- `GatewayBridgeAdapter` 还是 mock/占位读路径，不是生产级实盘桥。
- 当前错误码集合与迭代规划文档中的完整未来态略有差异，应以当前独立包代码为准。
