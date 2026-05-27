# First `bt_api_xx` Package Specification

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为首个外部 broker/exchange 扩展包定义统一规范，使后续所有 `bt_api_xx` 包都能按同一模板实现、测试、发布并兼容 `bt_api_py`。

**Architecture:** 首个样板包采用 `bt_api_alpaca`，因为它的认证模型简单、支持 paper/live 区分、适合作为外部包模板。规范要求外部包以 old plugin mode 为准：依赖 `bt_api_base` 的公共插件接口，暴露 `bt_api.plugins` entry point 与 `register_plugin(registry, runtime_factory)`，由 `bt_api_py.bt_api.BtApi` 通过 `PluginLoader` / `ExchangeRegistry` 消费。

**Tech Stack:** Python 3.9+、setuptools、pytest / pytest-asyncio、`bt_api_base` old plugin mode

**Execution Validation (2026-05-26):** 本规范已在首批 14 个独立扩展包上完成实战验证：`bt_api_tradier / bt_api_saxo / bt_api_zerodha / bt_api_upstox / bt_api_angelone / bt_api_fyers / bt_api_dhan / bt_api_shoonya / bt_api_aliceblue / bt_api_5paisa / bt_api_iifl / bt_api_kotak / bt_api_motilal / bt_api_groww`。这批包均已完成 old plugin mode 落地、本地验证、GitHub push 与 `CI = success`。

---

## 1. 命名规范

### 包名

统一采用：

```text
bt_api_<exchange_or_broker>
```

例如：

- `bt_api_alpaca`
- `bt_api_ibkr`
- `bt_api_5paisa`
- `bt_api_ctp`
- `bt_api_okx`
- `bt_api_binance`

### 注册名

统一采用小写短名：

- `alpaca`
- `ibkr`
- `5paisa`
- `ctp`
- `okx`
- `binance`

要求：

- loader 使用的 name 必须稳定
- 包名和注册名允许不同，但推荐一致语义
- 一旦对外发布，注册名不能随意改
- 如包名前有稳定前缀，则后缀部分可以保留数字；例如实际落地使用 `bt_api_5paisa`，而不是额外改写成 `bt_api_fivepaisa`

---

## 2. 目录结构规范

首个样板包建议使用：

```text
bt_api_alpaca/
  pyproject.toml
  README.md
  bt_api_alpaca/
    __init__.py
    adapter.py              # 可选兼容导出
    plugin.py
    registry_registration.py
    exchange_data.py
    auth.py
    mapping.py
    transport.py
    runtime/
      __init__.py
      feed.py
    gateway/
      __init__.py
      adapter.py
    containers/
      __init__.py
      alpaca_account.py
  tests/
    test_plugin.py
    test_exchange_data.py
    test_runtime_feed.py
    test_contract.py
    test_auth.py
    test_mapping.py
```

### 每个文件职责

- `__init__.py`
  - 导出 `AlpacaExchangeData*`，必要时导出兼容 `AlpacaGatewayAdapter`
  - 如需要，导出 `__all__`

- `adapter.py`
  - 仅做兼容导出
  - 指向 `gateway.adapter.AlpacaGatewayAdapter`

- `plugin.py`
  - 实现 `register_plugin(registry, runtime_factory)`
  - 返回 `PluginInfo`

- `registry_registration.py`
  - 汇总 `ExchangeRegistry` 注册逻辑
  - 注册 `feed`、`exchange_data`、`balance_handler`、`subscribe` handler

- `exchange_data.py`
  - 描述场所配置、URL、路径、period mapping

- `runtime/feed.py`
  - 提供 `BtApi` 可消费的 request/feed 实现
  - 返回 `RequestData` 与账户容器

- `gateway/adapter.py`
  - 实现老模式 `BaseGatewayAdapter`

- `auth.py`
  - 只处理该 broker 的认证、header、token/paper-live 环境切换

- `mapping.py`
  - 处理订单、账户、行情等字段归一化

- `transport.py`
  - HTTP/WebSocket 包装，避免把请求细节塞进 `adapter.py`

- `containers/alpaca_account.py`
  - 提供可被 `balance_handler` 消费的账户容器

---

## 3. 与 `bt_api_py` 的边界

### 允许依赖

外部包可以依赖：

- `bt_api_base.plugins.protocol.PluginInfo`
- `bt_api_base.registry.ExchangeRegistry`
- `bt_api_base.gateway.adapters.base.BaseGatewayAdapter`
- `bt_api_base.balance_utils.simple_balance_handler`
- `bt_api_base.containers.*`
- 测试中可选依赖 `bt_api_py.bt_api.BtApi` 做消费 smoke test

### 不允许依赖

外部包不应直接依赖：

- `backtrader_web`
- `backtrader_web` 的任何 service / API / model
- `bt_api_py` 内部未声明为公共接口的私有实现细节
- 其他 `bt_api_xx` 包

### 重要原则

- **contract 向核心收敛**
- **实现向扩展外置**
- **标准模式以 `bt_api.plugins` 为准**
- **web 侧不反向侵入 adapter**

---

## 4. `__init__.py` 规范

首个样板包建议至少提供：

```python
from bt_api_alpaca.exchange_data import AlpacaExchangeData, AlpacaExchangeDataStock
from bt_api_alpaca.gateway.adapter import AlpacaGatewayAdapter

__all__ = [
    "AlpacaExchangeData",
    "AlpacaExchangeDataStock",
    "AlpacaGatewayAdapter",
    "__version__",
]
```

要求：

- 不要在 import 时偷偷做网络连接
- import 成本应尽量低
- 不要在 `__init__.py` 中承担 `register_plugin()` 主实现

---

## 5. `plugin.py` / `gateway` / `runtime` 规范

### 最低要求

`plugin.py` 必须实现：

```python
def register_plugin(registry, runtime_factory) -> PluginInfo:
    ...
```

并至少完成：

- 注册 `feed`
- 注册 `exchange_data`
- 注册 `balance_handler`
- 如有需要注册 `subscribe` handler
- 注册 `GatewayAdapter`

### `gateway/adapter.py` 最低要求

`gateway/adapter.py` 必须实现 `BaseGatewayAdapter`，至少覆盖：

- `connect()`
- `disconnect()`
- `subscribe_symbols()`
- `get_balance()`
- `get_positions()`
- `place_order()`
- `cancel_order()`

### `runtime/feed.py` 最低要求

`runtime/feed.py` 至少覆盖：

- `get_balance()`
- `get_account()`
- `get_kline()`
- `make_order()`
- `cancel_order()`

以 `bt_api_alpaca` 为例：

```python
class AlpacaRequestDataStock(Feed):
    def __init__(
        self,
        data_queue=None,
        api_key: str = "",
        api_secret: str = "",
        paper: bool = True,
        base_url: str | None = None,
        timeout_sec: float = 10.0,
    ) -> None:
        ...
```

规范要求：

- 必需鉴权参数放显式参数，不塞进 `**kwargs`
- 环境切换参数显式化，例如 `paper=True`
- timeout / transport 参数显式化
- 不要在 `__init__` 时发真实网络请求
- `get_balance()` / `get_account()` 应返回 `RequestData`，其中账户列表可被 `balance_handler` 消费

---

## 6. `auth.py` 规范

`auth.py` 只做该 broker 的认证逻辑。

### 必须做的事情

- 认证 header 生成
- live / paper base URL 区分
- token / session / key 校验
- 敏感字段日志脱敏，避免裸打 key / secret

### 不该做的事情

- 不要把订单、行情、持仓映射塞进 `auth.py`
- 不要在这里写 `RequestData` / container 主体逻辑
- 不要依赖 `backtrader_web` secrets 逻辑

---

## 7. `mapping.py` 规范

`mapping.py` 负责把 broker 原生返回映射到 plugin runtime / gateway 可消费的统一 payload。

### 至少应有的函数形态

```python
def map_order_payload(payload: dict) -> dict[str, object]: ...

def map_quote_payload(symbol: str, payload: dict, *, provider: str) -> dict[str, object]: ...
```

### 映射原则

- 原生字段差异在这里消化
- runtime / gateway 输出必须稳定
- 缺失字段要有降级策略
- 不要把原始 payload 直接裸透给上层调用方

---

## 8. 错误处理规范

### 外部包内部可以有私有错误

例如：

- `AlpacaTransportError`
- `AlpacaAuthError`
- `AlpacaRateLimitError`

### 但对外部可见边界的出口必须统一

推荐约束：

- 认证/配置校验错误使用稳定的 `ValueError` 或包内私有异常
- 请求层错误优先复用 `bt_api_base.exceptions.RequestError`、`RequestFailedError`、`RequestTimeoutError`
- gateway / runtime 的期望失败应尽量返回可消费的规范化结果，而不是泄露底层 SDK 异常

禁止：

- 直接把底层 SDK/HTTP client 的原始异常类型暴露给上层调用方
- 在异常消息中包含明文凭证

---

## 9. 注册 / 加载规范

### 标准方式

必须通过 entry points 暴露老模式插件入口：

```toml
[project.entry-points."bt_api.plugins"]
alpaca = "bt_api_alpaca.plugin:register_plugin"
```

### 约束

- `register_plugin(registry, runtime_factory)` 是外部包的唯一标准注册入口
- 测试或调试时可以直接 import `register_plugin`，但这不是首选消费方式
- `PluginLoader` discovery 是第一阶段就必须打通的路径，不是增强项

---

## 10. 测试规范

### 必测 1：plugin registration 测试

每个 `bt_api_xx` 包必须至少有：

```python
def test_register_plugin_returns_plugin_info() -> None:
    info = register_plugin(ExchangeRegistry, runtime_factory)
    assert info.supported_exchanges == ("ALPACA___STK",)
```

### 必测 2：runtime / exchange_data 单测

- `get_balance()` 返回 `RequestData`
- 账户容器可被 `simple_balance_handler` 消费
- `exchange_data` 路径与 URL 配置正确

### 必测 3：gateway adapter 单测

- `connect()` / `disconnect()`
- `get_balance()` / `get_positions()`
- `place_order()` / `cancel_order()`

### 必测 4：认证单测

- header 生成正确
- live / paper URL 切换正确
- 缺失 key 时报稳定错误

### 必测 5：映射单测

- order payload -> 统一订单 dict
- quote payload -> 统一行情 dict

### 必测 6：`BtApi` 消费 smoke test

- `PluginLoader` 可发现插件
- `ExchangeRegistry.create_feed()` 可创建 feed
- `BtApi.update_total_balance()` 可消费插件

### 可选 7：sandbox/integration test

- 需要真实环境变量时单独加 marker
- 默认 CI 不跑真实网络

---

## 11. `pyproject.toml` 规范

首个样板包建议至少包括：

```toml
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "bt_api_alpaca"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
  "bt_api_base>=0.15,<1.0",
]

[project.entry-points."bt_api.plugins"]
alpaca = "bt_api_alpaca.plugin:register_plugin"

[project.optional-dependencies]
dev = [
  "pytest>=7.0",
  "pytest-asyncio>=0.21.0",
]
```

### 版本原则

- 外部包必须锁定兼容的 `bt_api_base` 主次版本范围
- 如需额外声明消费侧约束，应在 README 中注明已验证的 `bt_api_py` 版本范围
- 不要直接写无上界依赖

---

## 12. README 规范

每个 `bt_api_xx` 包的 `README.md` 至少包含：

- 这个包实现了哪个 broker/exchange
- 如何安装
- 如何通过 `bt_api.plugins` 被发现
- 如何用 `BtApi` 或 `gateway adapter` 使用
- 支持哪些 exchange / asset type / 能力
- 哪些能力还没实现
- 如何运行 plugin/runtime/gateway 测试

示例章节：

- Install
- Plugin Entry Point
- Usage
- Capabilities
- Testing
- Limitations

---

## 13. 首包选择建议：为什么用 `bt_api_alpaca`

首个样板包推荐用 `bt_api_alpaca`，原因：

- 认证模型相对简单
- paper/live 语义清晰
- 适合先做 plugin / loader / registry / package boundary 验证
- 不会一开始就卷入 CTP/IBKR 那类复杂会话问题

这不代表 Alpaca 一定是最终最优先生产 broker，只代表它更适合作为**样板包**。

---

## 14. 与 `backtrader_web` 的关系

`backtrader_web` 对 `bt_api_xx` 的角色必须保持克制：

- 可以记录文档边界
- 可以消费 `bt_api_py` 稳定接口
- 可以做能力展示 / 配置映射 / 审计
- **不应该**直接承接 `bt_api_xx` 包内部实现

如果 web 仓需要增加支持，应优先写成：

- 配置层改动
- capability 展示
- 接口消费兼容

而不是把 adapter 逻辑搬回 web 仓。

---

## 15. 完成标准

一个 `bt_api_xx` 包只有在满足以下条件后，才算达到最小可接受标准：

- 有独立包名与稳定注册名
- 只依赖稳定的 `bt_api_base` 插件 contract（测试中可选使用 `BtApi`）
- 声明 `bt_api.plugins` entry point
- 能注册 `feed`、`exchange_data`、`balance_handler`，必要时注册 `subscribe` handler 与 `GatewayAdapter`
- 至少有 plugin / runtime / gateway / auth / mapping 基本单测
- 至少有一个 `BtApi` 消费 smoke test
- README 可指导安装和使用
- 不依赖 `backtrader_web` 私有实现

补充说明：

- 迭代 172 的首批 14 个包已经证明，上述完成标准足以支撑批量券商扩展包落地、统一测试和 CI 验证

---

## 16. 首包落地顺序

推荐顺序：

1. 创建 `bt_api_alpaca` skeleton
2. 先打通 `plugin.py`、`registry_registration.py` 与最小 `gateway/adapter.py`
3. 再补 `exchange_data.py`、`runtime/feed.py`、账户容器
4. 再接 `PluginLoader` discovery 与 `BtApi` 消费测试
5. 最后才考虑更复杂 broker

这个顺序能最大化降低第一次拆包的失败成本。
