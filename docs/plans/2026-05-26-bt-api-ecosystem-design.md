# bt_api_py / bt_api_xx Ecosystem Design

> **For Claude:** 后续如果要执行该设计，请在独立仓 / 独立 worktree 中推进，并优先保证 `bt_api_py` 与 `backtrader` 的兼容链路不破坏。

**Goal:** 明确 broker 能力不再在 `ai-for-trader` 内持续产品化，而是沉淀为 `bt_api_py` 统一核心 + `bt_api_xx` 独立交易所/券商扩展包的长期演进路线。

**Architecture:** `bt_api_py` 继续作为统一能力入口与 `btapibroker` 集成层，对外消费 `bt_api_base` 的 `ExchangeRegistry` / `PluginLoader` 能力；每个交易所 / 券商实现拆成单独 `bt_api_xx` 包，并按老模式暴露 `bt_api.plugins` entry point 与 `register_plugin(registry, runtime_factory)`；`ai-for-trader` 只消费稳定接口，不再承担 broker adapter 主实现。整个体系以“核心稳定、接入外置、兼容优先”为原则。

**Tech Stack:** Python 3.10+、`bt_api_base` old plugin mode、Backtrader integration、独立可发布 Python packages

---

## 1. 背景

当前项目已经明确：

- `bt_api_py` 是统一 broker 能力层
- `backtrader` 底层通过 `btapibroker` 接入 `bt_api_py`
- `ai-for-trader` 是上层消费方，而不是 broker 平台宿主

因此，后续如果继续把 broker registry、native adapter、paper/native/gateway 混合实现堆在 `ai-for-trader` 中，会产生三个问题：

- **职责重复**：`ai-for-trader` 和 `bt_api_py` 会同时维护 broker 抽象
- **发布耦合**：每新增一个券商都要跟随 web 仓发版
- **生态不可扩展**：交易所/券商实现无法独立测试、独立发布、独立演进

所以需要一条更清晰的路线：

- `bt_api_py` 做稳定核心
- `bt_api_xx` 做独立扩展
- `ai-for-trader` 只接标准接口

---

## 2. 设计目标

### 2.1 要解决的问题

- 给 broker 能力一个**唯一权威宿主**
- 允许每个交易所 / 券商**独立拆包和发布**
- 不破坏现有 `btapibroker -> bt_api_py -> adapter` 的使用方式
- 给 `ai-for-trader` 一个稳定、薄的消费边界

### 2.2 非目标

以下内容不在本设计内直接落地：

- 在 `ai-for-trader` 中重建 broker registry 平台
- 一次性完成全部 broker 的独立拆包
- 重新设计 backtrader 的执行引擎
- 在本轮设计里引入复杂插件市场 / 远程包管理中心

---

## 3. 包结构建议

### 3.1 核心包：`bt_api_py`

`bt_api_py` 保留为**统一能力入口**，负责：

- `integration`
  - `bt_api_py.bt_api.BtApi`
  - `btapibroker`
  - backtrader 所需映射逻辑

- `loading`
  - 在启动时调用 `PluginLoader`
  - 通过 `ExchangeRegistry` / runtime registrar 消费外部插件注册结果
  - 保留必要 builtin / compatibility shim

- `testing`
  - 插件发现测试
  - `BtApi` 消费链 smoke / integration test
  - builtin / compatibility regression test

### 3.2 扩展包：`bt_api_xx`

每个交易所 / 券商一个独立包，例如：

- `bt_api_ibkr`
- `bt_api_alpaca`
- `bt_api_ctp`
- `bt_api_binance`
- `bt_api_okx`
- `bt_api_mt5`

这些包只做一件事：

- 基于 `bt_api_base` 老插件约定实现 `feed` / `exchange_data` / `gateway adapter`
- 暴露 `plugin.py` 中的 `register_plugin(registry, runtime_factory)`
- 自带该 broker 的 runtime、gateway、测试、文档与依赖

### 3.3 Web 消费方：`ai-for-trader`

`ai-for-trader` 不再承担 broker 主实现，仅保留：

- 统一配置/别名映射
- 能力展示与审计
- 业务编排
- 与 `bt_api_py` 的稳定接口调用

---

## 4. 兼容原则

### 4.1 必须保持稳定的链路

核心兼容链路为：

```text
backtrader strategy
  -> btapibroker
  -> bt_api_py BtApi / PluginLoader / ExchangeRegistry
  -> bt_api_xx plugin
  -> broker/exchange API
```

这条链路必须满足：

- `btapibroker` 不依赖具体 `bt_api_xx` 包内部细节
- `bt_api_xx` 只依赖稳定的 `bt_api_base` 插件 contract，并通过 `bt_api_py` 被消费
- `ai-for-trader` 不直接 import 单个 broker 的私有实现细节

### 4.2 旧模式兼容

如果当前存在：

- `bt_api_py.brokers.mock`
- `bt_api_py.brokers.gateway_bridge`

那么短期内可以保留，但要定义为：

- **core-owned builtins**：核心包内置能力
- 非核心 broker 实现未来应迁移为外部包

也就是说：

- `mock` 可继续留在 `bt_api_py`
- `gateway_bridge` 若是通用桥层，也可留在 `bt_api_py`
- 具体券商/交易所接入则优先迁到 `bt_api_xx`

---

## 5. 推荐加载模型

标准模式采用“entry point discovery + registry consumption”。

### 5.1 外部包标准注册入口

每个 `bt_api_xx` 包应暴露：

```python
def register_plugin(registry, runtime_factory) -> PluginInfo:
    ...
```

并在 `pyproject.toml` 中声明：

```toml
[project.entry-points."bt_api.plugins"]
alpaca = "bt_api_alpaca.plugin:register_plugin"
```

`register_plugin()` 的职责是：

- 向 `ExchangeRegistry` 注册 `feed`
- 注册 `exchange_data`
- 注册 `balance_handler`
- 如有需要注册 `subscribe` stream handler
- 向 runtime registrar 注册 `GatewayAdapter`

### 5.2 `bt_api_py` 侧消费方式

`bt_api_py.bt_api` 在启动时通过 `PluginLoader` 扫描 `bt_api.plugins`，把插件提交到全局 `ExchangeRegistry` 与 runtime registrar，然后 `BtApi` 只按交易所名消费这些注册结果，例如：

```python
from bt_api_py.bt_api import BtApi

api = BtApi({"ALPACA___STK": {"api_key": "...", "api_secret": "...", "paper": True}})
```

说明：

- 显式 `register()` 样板是早期探索，不再作为标准模式
- 外部包不需要 `load_adapter("alpaca")` 这类新 contract loader 作为首选入口
- 缺失插件时应在插件发现或 `ExchangeRegistry.create_feed()` 阶段暴露结构化失败

---

## 6. 推荐模块划分

### 6.1 `bt_api_py`

建议稳定下来的顶层结构：

```text
bt_api_py/
  brokers/
    base.py
    types.py
    errors.py
    capabilities.py
    loader.py
    registry.py
    mock.py
    gateway_bridge.py
  backtrader/
    btapibroker.py
    mapping.py
  testing/
    contract_cases.py
    fixtures.py
```

说明：

- `registry.py` 负责统一注册表抽象
- `loader.py` 负责按名称加载 builtin / external adapters
- `mock.py`、`gateway_bridge.py` 作为 core-owned builtin 保留
- `btapibroker.py` 不关心具体 broker 包内部结构

### 6.2 `bt_api_xx`

以 `bt_api_alpaca` 为例：

```text
bt_api_alpaca/
  __init__.py
  adapter.py                  # 可选兼容导出
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
```

其中：

- `plugin.py` 暴露 `register_plugin()`
- `registry_registration.py` 汇总 `ExchangeRegistry` 注册逻辑
- `exchange_data.py` 描述场所配置与路径
- `runtime/feed.py` 提供 `BtApi` 可消费的 request/feed 实现
- `gateway/adapter.py` 提供老模式 `BaseGatewayAdapter`
- `tests/` 需覆盖 plugin registration、runtime feed、exchange_data 与 gateway adapter

---

## 7. 版本与依赖策略

### 7.1 版本原则

- `bt_api_py` 作为核心 contract，应尽量保持慢变
- `bt_api_xx` 可以更快发版
- `bt_api_xx` 应声明兼容的 `bt_api_base` 版本范围，并确保与 `bt_api_py` 的插件消费路径兼容，例如：

```text
bt_api_base>=0.15,<1.0
```

### 7.2 破坏性变更原则

若 `bt_api_base` 插件 contract 或 `BtApi` 消费路径发生破坏性升级：

- 必须先在 `bt_api_py` / `bt_api_base` 提供兼容层
- 至少经历一个 deprecation 周期
- `btapibroker` 与已发布 `bt_api_xx` 插件 smoke test 必须先跑通再让扩展包跟进

---

## 8. 测试策略

### 8.1 `bt_api_py` 核心测试

核心仓负责：

- contract 测试定义
- builtin adapters 测试
- `btapibroker` 集成 smoke test
- loader / registry / compatibility test

### 8.2 `bt_api_xx` 扩展测试

每个扩展包必须至少提供：

- plugin registration test
- runtime feed / exchange_data / auth / mapping 单测
- `BtApi` 消费 smoke test
- fake HTTP 或 mock SDK 测试
- 可选的 sandbox/integration test

### 8.3 `ai-for-trader` 测试

web 仓不再承担 broker adapter 验证，只保留：

- API 消费 smoke test
- 配置 / 展示 /审计路径测试
- 对 `bt_api_py` 暴露稳定接口的集成测试

---

## 9. 推荐迁移顺序

### Phase 1

- 固化 `bt_api_py` contract
- 明确 `mock` / `gateway_bridge` 属于 core builtins
- 稳定 `btapibroker` 对 core contract 的依赖

### Phase 2

- 选 1 个高价值交易所做首个 `bt_api_xx` 样板
- 推荐从依赖清晰、认证模型稳定的适配器开始
- 形成标准包模板

### Phase 3

- 再迁 1-2 个 broker/exchange
- 验证不同风格接入都能兼容同一 contract
- 收敛 loader / registry 设计

### Phase 4

- `ai-for-trader` 只保留统一消费边界
- 新 broker 需求默认走 `bt_api_xx`
- 停止在 web 仓内部追加 broker 平台代码

---

## 10. 对 iteration 171 的影响

该设计意味着：

- `iteration 171` 中与 broker 相关的内容，应理解为**跨仓协同前置项**
- `ai-for-trader` 在 171 中不继续做 broker adapter 实装
- `171` 的重点仍是：
  - Data Connector Registry
  - Portfolio Ledger
  - Equity Research
  - News Intelligence
  - Options Chain
  - Scanner DSL
  - Quant Tool Registry
  - WS Gateway migration

而 broker 方向单独遵循本设计文档推进。

---

## 11. 最终结论

长期稳定结构应为：

- **`bt_api_py`**：统一核心
- **`bt_api_xx`**：单交易所 / 单券商独立扩展
- **`btapibroker`**：backtrader 集成桥
- **`ai-for-trader`**：统一消费方

这能最大程度避免职责重复，并保持 broker 能力在独立生态中可测试、可发布、可扩展。

---

## 12. 下一步执行文档

- 实施计划：`docs/plans/2026-05-26-bt-api-ecosystem-implementation-plan.md`
- 首个扩展包规范：`docs/plans/2026-05-26-first-bt-api-xx-package-spec.md`
