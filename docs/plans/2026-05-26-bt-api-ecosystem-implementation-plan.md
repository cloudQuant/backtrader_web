# bt_api_py / bt_api_xx Ecosystem Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 broker 能力从 `backtrader_web` 彻底收敛到独立 `bt_api_py` 核心与 `bt_api_xx` 外部扩展包体系，并给出第一批可执行的核心改造与样板扩展落地顺序。

**Architecture:** 现有 `bt_api_py.bt_api.BtApi` 已经内置 `PluginLoader`、`_RuntimeRegistrar` 与 `ExchangeRegistry` 消费路径；外部 `bt_api_xx` 包的标准形态应是 old plugin mode：`bt_api.plugins` entry point + `register_plugin(registry, runtime_factory)` + `feed / exchange_data / balance_handler / gateway adapter` layering。本计划以这个老模式为准推进首包 `bt_api_alpaca`，并补足 `bt_api_py` 侧 discovery / integration tests 与文档收口。

**Tech Stack:** Python 3.9+、`bt_api_base` old plugin mode、pytest / pytest-asyncio、setuptools entry points、独立 Python package 发布

---

## 0. 执行前提

### Repository roots

- Core repo: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py`
- Docs repo: `/Users/yunjinqi/Documents/new_projects/backtrader_web`
- First sample external package target: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca`

### Current facts to preserve

- `bt_api_py/bt_api_py/bt_api.py` 已经内置 `_RuntimeRegistrar` 与 `PluginLoader`
- `bt_api_py` 已通过 `ExchangeRegistry` 消费插件注册结果
- 标准外部包应注册 `feed`、`exchange_data`、`balance_handler`、可选 `subscribe` stream handler 与 `GatewayAdapter`
- 显式 `register()` 样板属于早期探索，已不再作为标准模式
- 当前没有在仓内找到明确的 `btapibroker.py` 规范路径，因此需要先固化 canonical integration path

### Hard rules

- 不在 `backtrader_web` 仓内实现 broker adapter 主逻辑
- 先做 core contract / loader / compatibility，再做外部包
- 每一步都先写失败测试，再补最小实现
- 只跑**非常小的目标测试**，不要一开始跑全量套件

说明：Task 1-4 主要记录核心仓的历史演进切片；对外部 `bt_api_xx` 包的标准形态，应以 Task 5 及之后明确的 old plugin mode 为准。

---

### Task 1: Stabilize the core broker registry and loader API

**Files:**
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/brokers/registry.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/brokers/loader.py`
- Modify: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/brokers/__init__.py`
- Modify: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/__init__.py`
- Test: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/tests/test_broker_loader.py`

**Step 1: Write the failing test**

```python
import pytest

from bt_api_py.brokers.loader import load_adapter
from bt_api_py.brokers.mock import MockBrokerAdapter


def test_load_adapter_returns_builtin_mock() -> None:
    adapter = load_adapter("mock")
    assert isinstance(adapter, MockBrokerAdapter)


def test_list_builtin_adapters_contains_mock_and_gateway_bridge() -> None:
    from bt_api_py.brokers.registry import list_registered_adapters

    adapters = list_registered_adapters()
    assert "mock" in adapters
    assert "gateway_bridge" in adapters
```

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_broker_loader.py::test_load_adapter_returns_builtin_mock -q
```

Expected: FAIL with import error because `bt_api_py.brokers.loader` does not exist.

**Step 3: Write minimal implementation**

```python
# bt_api_py/brokers/registry.py
from collections.abc import Callable

_ADAPTER_FACTORIES: dict[str, Callable[[], object]] = {}


def register_adapter(name: str, factory: Callable[[], object]) -> None:
    _ADAPTER_FACTORIES[name.strip().lower()] = factory


def get_adapter_factory(name: str):
    return _ADAPTER_FACTORIES.get(name.strip().lower())


def list_registered_adapters() -> list[str]:
    return sorted(_ADAPTER_FACTORIES)
```

```python
# bt_api_py/brokers/loader.py
from bt_api_py.brokers.gateway_bridge import GatewayBridgeAdapter
from bt_api_py.brokers.mock import MockBrokerAdapter
from bt_api_py.brokers.registry import get_adapter_factory, register_adapter

register_adapter("mock", MockBrokerAdapter)
register_adapter("gateway_bridge", GatewayBridgeAdapter)


def load_adapter(name: str):
    factory = get_adapter_factory(name)
    if factory is None:
        raise ValueError(f"adapter not found: {name}")
    return factory()
```

**Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_broker_loader.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add bt_api_py/brokers/registry.py bt_api_py/brokers/loader.py bt_api_py/brokers/__init__.py bt_api_py/__init__.py tests/test_broker_loader.py
git commit -m "feat(brokers): add core adapter loader and registry"
```

---

### Task 2: Add structured external adapter registration and unknown-adapter errors

**Files:**
- Modify: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/brokers/errors.py`
- Modify: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/brokers/registry.py`
- Modify: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/brokers/loader.py`
- Test: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/tests/test_broker_loader.py`

**Step 1: Write the failing test**

```python
import pytest

from bt_api_py.brokers.errors import BrokerError
from bt_api_py.brokers.loader import load_adapter
from bt_api_py.brokers.registry import register_adapter
from bt_api_py.brokers.mock import MockBrokerAdapter


def test_load_adapter_raises_structured_error_for_unknown_name() -> None:
    with pytest.raises(BrokerError) as exc_info:
        load_adapter("missing")
    assert exc_info.value.code.value == "adapter_not_installed"


def test_register_adapter_accepts_external_factory() -> None:
    register_adapter("external_mock", MockBrokerAdapter)
    adapter = load_adapter("external_mock")
    assert isinstance(adapter, MockBrokerAdapter)
```

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_broker_loader.py::test_load_adapter_raises_structured_error_for_unknown_name -q
```

Expected: FAIL because `adapter_not_installed` code does not exist.

**Step 3: Write minimal implementation**

```python
# bt_api_py/brokers/errors.py
class BrokerErrorCode(str, Enum):
    ...
    ADAPTER_NOT_INSTALLED = "adapter_not_installed"
```

```python
# bt_api_py/brokers/loader.py
from bt_api_py.brokers.errors import BrokerError, BrokerErrorCode


def load_adapter(name: str):
    factory = get_adapter_factory(name)
    if factory is None:
        raise BrokerError(BrokerErrorCode.ADAPTER_NOT_INSTALLED, f"adapter not found: {name}")
    return factory()
```

**Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_broker_loader.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add bt_api_py/brokers/errors.py bt_api_py/brokers/registry.py bt_api_py/brokers/loader.py tests/test_broker_loader.py
git commit -m "feat(brokers): add structured external adapter registration"
```

---

### Task 3: Create the canonical backtrader integration namespace

**Files:**
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/backtrader/__init__.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/backtrader/btapibroker.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/backtrader/mapping.py`
- Modify: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/__init__.py`
- Test: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/tests/test_btapibroker_import.py`

**Step 1: Write the failing test**

```python
def test_canonical_btapibroker_import_exists() -> None:
    from bt_api_py.backtrader.btapibroker import BtApiBroker

    assert BtApiBroker is not None
```

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_btapibroker_import.py -q
```

Expected: FAIL because `bt_api_py.backtrader` does not exist.

**Step 3: Write minimal implementation**

```python
# bt_api_py/backtrader/btapibroker.py
class BtApiBroker:
    """Canonical backtrader bridge entry point.

    First phase goal: provide a stable import path.
    Real behavior can wrap the existing bridge implementation incrementally.
    """

    def __init__(self, adapter_name: str = "mock") -> None:
        self.adapter_name = adapter_name
```

```python
# bt_api_py/backtrader/__init__.py
from bt_api_py.backtrader.btapibroker import BtApiBroker

__all__ = ["BtApiBroker"]
```

**Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_btapibroker_import.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add bt_api_py/backtrader/__init__.py bt_api_py/backtrader/btapibroker.py bt_api_py/backtrader/mapping.py bt_api_py/__init__.py tests/test_btapibroker_import.py
git commit -m "feat(backtrader): add canonical btapibroker namespace"
```

---

### Task 4: Strengthen the contract test harness for external packages

**Files:**
- Modify: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/testing/contract_cases.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/bt_api_py/testing/fixtures.py`
- Modify: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/tests/test_broker_contract.py`
- Test: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/tests/test_broker_contract.py`

**Step 1: Write the failing test**

```python
import pytest

from bt_api_py.brokers.mock import MockBrokerAdapter
from bt_api_py.testing.contract_cases import run_broker_contract_cases


@pytest.mark.asyncio
async def test_contract_report_exposes_case_results() -> None:
    report = await run_broker_contract_cases(MockBrokerAdapter())
    assert "cases" in report
    assert report["cases"][0]["name"] == "connect"
```

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_broker_contract.py::test_contract_report_exposes_case_results -q
```

Expected: FAIL because the report only contains `passed / method_count / capabilities`.

**Step 3: Write minimal implementation**

```python
# bt_api_py/testing/contract_cases.py
async def run_broker_contract_cases(adapter: BrokerAdapter) -> dict[str, object]:
    cases: list[dict[str, object]] = []
    await adapter.connect()
    cases.append({"name": "connect", "passed": True})
    ...
    return {
        "passed": passed,
        "method_count": len(methods),
        "capabilities": caps.as_dict(),
        "cases": cases,
    }
```

**Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_broker_contract.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add bt_api_py/testing/contract_cases.py bt_api_py/testing/fixtures.py tests/test_broker_contract.py
git commit -m "test(brokers): strengthen contract harness for external packages"
```

---

### Task 5: Create the first external package skeleton (`bt_api_alpaca`)

**Files:**
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/pyproject.toml`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/README.md`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/__init__.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/adapter.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/plugin.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/registry_registration.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/exchange_data.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/auth.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/mapping.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/transport.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/runtime/__init__.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/runtime/feed.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/gateway/__init__.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/gateway/adapter.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/containers/__init__.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/bt_api_alpaca/containers/alpaca_account.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/tests/test_plugin.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/tests/test_exchange_data.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/tests/test_runtime_feed.py`
- Create: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/tests/test_contract.py`

**Step 1: Write the failing test**

- `tests/test_plugin.py`: `register_plugin()` 返回 `PluginInfo`，并注册 `ALPACA___STK` 的 `feed` / `exchange_data` / `balance_handler` / `subscribe` handler 以及 `ALPACA` 的 gateway adapter
- `tests/test_exchange_data.py`: `AlpacaExchangeDataStock` 暴露预期的 REST / WSS 配置
- `tests/test_runtime_feed.py`: `AlpacaRequestDataStock.get_balance()` 返回 `RequestData`，其账户容器可被 `simple_balance_handler` 消费
- `tests/test_contract.py`: `AlpacaGatewayAdapter` 覆盖老模式 gateway adapter 的最小行为

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_contract.py -q
```

Expected: FAIL because old-mode plugin skeleton files do not exist.

**Step 3: Write minimal implementation**

- 在 `plugin.py` 中实现 `register_plugin(registry, runtime_factory) -> PluginInfo`
- 在 `registry_registration.py` 中集中注册 `feed`、`exchange_data`、`balance_handler`、`subscribe` handler
- 在 `gateway/adapter.py` 中实现 `AlpacaGatewayAdapter(BaseGatewayAdapter)`
- 在 `runtime/feed.py` 中实现 `AlpacaRequestDataStock`，至少覆盖 `get_balance()`、`get_account()`、`get_kline()`、`make_order()`、`cancel_order()`
- 在 `containers/alpaca_account.py` 中提供可被 `simple_balance_handler` 消费的账户容器
- `adapter.py` 仅保留兼容导出，不再作为新样板的主实现入口

**Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_contract.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml README.md bt_api_alpaca/__init__.py bt_api_alpaca/adapter.py bt_api_alpaca/plugin.py bt_api_alpaca/registry_registration.py bt_api_alpaca/exchange_data.py bt_api_alpaca/auth.py bt_api_alpaca/mapping.py bt_api_alpaca/transport.py bt_api_alpaca/runtime bt_api_alpaca/gateway bt_api_alpaca/containers tests/test_plugin.py tests/test_exchange_data.py tests/test_runtime_feed.py tests/test_contract.py
git commit -m "feat(alpaca): add first old-mode bt_api plugin skeleton"
```

---

### Task 6: Wire core-to-plugin discovery for the sample package

**Files:**
- Modify: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/pyproject.toml`
- Test: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/tests/test_bt_api_plugin_integration.py`

**Step 1: Write the failing test**

- monkeypatch `PluginLoader` 的 entry-point discovery，使其发现 `bt_api_alpaca.plugin:register_plugin`
- 断言 `ExchangeRegistry` 中出现 `ALPACA___STK`
- 断言 runtime registrar 中出现 `ALPACA`
- 断言 `BtApi({"ALPACA___STK": {...}}).update_total_balance()` 与 `subscribe()` 可以消费该插件

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_bt_api_plugin_integration.py -q
```

Expected: FAIL because `bt_api_alpaca` 还没有声明标准 `bt_api.plugins` entry point，且 `bt_api_py` 侧还没有对应的 discovery / integration test。

**Step 3: Write minimal implementation**

Use the standard old-mode strategy:

1. Add entry point declaration in `bt_api_alpaca/pyproject.toml`:

```toml
[project.entry-points."bt_api.plugins"]
alpaca = "bt_api_alpaca.plugin:register_plugin"
```

2. 在 `bt_api_py` 独立仓新增 `tests/test_bt_api_plugin_integration.py`：

- 用 `PluginLoader` 加载 `bt_api_alpaca`
- 验证 `ExchangeRegistry.create_feed()` 可创建 `AlpacaRequestDataStock`
- 验证 `BtApi.update_total_balance()` 与 `subscribe()` 可消费该插件

3. 不再引入显式 `register()` 或新适配器样板作为外部包首选发现路径。

**Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_bt_api_plugin_integration.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add /Users/yunjinqi/Documents/new_projects/bt_api/bt_api_alpaca/pyproject.toml /Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py/tests/test_bt_api_plugin_integration.py
git commit -m "test(bt_api): verify alpaca old-mode plugin discovery and consumption"
```

---

### Task 7: Document the compatibility contract and keep web-side docs thin

**Files:**
- Modify: `/Users/yunjinqi/Documents/new_projects/backtrader_web/docs/guides/BT_API_PY_BROKER_CONTRACT.md`
- Modify: `/Users/yunjinqi/Documents/new_projects/backtrader_web/docs/plans/2026-05-26-bt-api-ecosystem-design.md`
- Modify: `/Users/yunjinqi/Documents/new_projects/backtrader_web/docs/iterations/迭代171-FinceptTerminal迁移深化与产品化收口/index.md`
- Test: doc review only

**Step 1: Write the failing review checklist**

Create a checklist in the task notes:

```text
- Docs must say bt_api_py owns the contract
- Docs must say bt_api_xx owns concrete adapters
- Docs must say backtrader_web is consumer only
- Docs must link to implementation plan and package spec
```

**Step 2: Run review to verify it fails**

Manual check expected: at least one doc is missing the implementation-plan or package-spec link.

**Step 3: Write minimal implementation**

- Add a “Next execution docs” section to the ecosystem design doc
- Link both new docs from the broker guide or 171 doc
- Do not add new broker scope back into `backtrader_web`

**Step 4: Run review to verify it passes**

Manual check expected: all four checklist items are satisfied.

**Step 5: Commit**

```bash
git add /Users/yunjinqi/Documents/new_projects/backtrader_web/docs/guides/BT_API_PY_BROKER_CONTRACT.md /Users/yunjinqi/Documents/new_projects/backtrader_web/docs/plans/2026-05-26-bt-api-ecosystem-design.md /Users/yunjinqi/Documents/new_projects/backtrader_web/docs/iterations/迭代171-FinceptTerminal迁移深化与产品化收口/index.md
git commit -m "docs: link broker ecosystem execution plan and package spec"
```

---

## Final verification slice

Run these in small groups, in order:

```bash
python -m pytest tests/test_broker_loader.py tests/test_bt_api_plugin_integration.py tests/test_btapibroker_import.py tests/test_broker_contract.py -q
```

Then in the sample package:

```bash
python -m pytest tests/test_auth.py tests/test_mapping.py tests/test_transport.py tests/test_exchange_data.py tests/test_runtime_feed.py tests/test_plugin.py tests/test_contract.py -q
```

If and only if all targeted tests pass, run a slightly wider core slice:

```bash
python -m pytest tests/test_broker_loader.py tests/test_btapibroker_import.py tests/test_broker_contract.py -q
```

---

## Completion criteria

This plan is complete when all of the following are true:

- `bt_api_py` has a canonical `brokers/registry.py` and `brokers/loader.py`
- builtins `mock` and `gateway_bridge` load through the same API as external adapters
- a canonical `bt_api_py.backtrader.btapibroker` import path exists
- the contract harness produces richer case-level results for external-package validation
- a first external sample package (`bt_api_alpaca`) exists and passes the core contract harness
- `backtrader_web` docs point to the new implementation plan and package spec, but do not absorb broker implementation work back into the web repo
