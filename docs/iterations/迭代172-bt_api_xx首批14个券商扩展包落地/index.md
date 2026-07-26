# 迭代 172 - `bt_api_xx` 首批 14 个券商扩展包落地

> **文档状态**: 已完成（首批 14 个券商扩展包已在独立 `bt_api` 生态完成实现、验证、推送与 CI 收口）
> **创建日期**: 2026-05-26
> **前置基线**: 迭代 170 已完成 FinceptTerminal 能力迁移底座与 broker 边界收口；迭代 171 继续推进 Web 产品化缺口；`bt_api_alpaca / bt_api_ib_web / bt_api_mt5 / bt_api_binance / bt_api_okx / bt_api_ctp` 已作为当前已实现基线存在
> **核心目标**: 在不把 broker 主实现回流到 `backtrader_web` 的前提下，基于既有 old plugin mode 模板，完成首批 14 个缺失券商扩展包的统一实现规划与执行切片：`Tradier / Saxo / Zerodha / Upstox / Angel One / Fyers / Dhan / Shoonya / AliceBlue / 5paisa / IIFL / Kotak / Motilal / Groww`。

---

## 0. 立项背景

在迭代 170 / 171 之后，broker 能力的职责边界已经明确：

- `bt_api_py` 是统一 broker / exchange 能力入口
- `bt_api_xx` 是按交易所 / 券商拆分的独立扩展包
- `backtrader_web` 只做消费、展示、配置映射、审计与文档，不再承担 broker adapter 主实现

当前已明确存在并应视为已实现的基线包包括：

- `bt_api_alpaca`
- `bt_api_ib_web`（作为当前 `IBKR` 既有实现口径）
- `bt_api_mt5`
- `bt_api_binance`
- `bt_api_okx`
- `bt_api_ctp`

在此前对 FinceptTerminal broker inventory 的盘点中，仍有 14 个优先券商尚未进入 `bt_api_xx` 生态。迭代 172 的作用不是在 `backtrader_web` 仓内直接编码这些 broker，而是：

1. 把这 14 个扩展包纳入同一轮明确执行范围。
2. 固化统一的包命名、注册名、old plugin mode 形态与验收标准。
3. 给跨仓执行提供清晰的分批顺序、最小可交付定义与风险切片。

## 0.1 落地结果（2026-05-26）

本轮主实施已在独立 `bt_api` 生态完成，结果如下：

- 首批 14 个扩展包已全部按独立仓 / 独立包落地：
  - `bt_api_tradier`
  - `bt_api_saxo`
  - `bt_api_zerodha`
  - `bt_api_upstox`
  - `bt_api_angelone`
  - `bt_api_fyers`
  - `bt_api_dhan`
  - `bt_api_shoonya`
  - `bt_api_aliceblue`
  - `bt_api_5paisa`
  - `bt_api_iifl`
  - `bt_api_kotak`
  - `bt_api_motilal`
  - `bt_api_groww`
- 所有包均按 old plugin mode 收口：
  - `bt_api.plugins` entry point
  - `register_plugin(registry, runtime_factory)`
  - `ExchangeRegistry / runtime feed / gateway adapter`
  - `BtApi` 消费 smoke test
- push 后 GitHub Actions `CI` 已全部 `success`
- 本轮尾部单独补完并复核的包包括：
  - `bt_api_motilal`：本地 `ruff` + `pytest` 通过，`19 passed`，commit `6771de2`
  - `bt_api_groww`：本地 `ruff` + `pytest` 通过，`18 passed`，commit `ad7da77`

---

## 1. 范围定义

### 1.1 本迭代纳入实现的 14 个券商

按本轮确认顺序，纳入 172 的对象为：

1. `Tradier`
2. `Saxo`
3. `Zerodha`
4. `Upstox`
5. `Angel One`
6. `Fyers`
7. `Dhan`
8. `Shoonya`
9. `AliceBlue`
10. `5paisa`
11. `IIFL`
12. `Kotak`
13. `Motilal`
14. `Groww`

### 1.2 本迭代明确不纳入的对象

以下对象不在 172 范围内：

- `Alpaca / IBKR / MT5 / Binance / OKX / CTP`
  - 原因：已作为当前已实现基线存在，不在本轮新增名单内。
- `MetaTrader4 / MetaApi`
  - 原因：桥接性质更强，运行环境与验证路径明显不同，延后到后续迭代。
- `backtrader_web` 内部 broker registry / adapter / native integration 新实现
  - 原因：与既定边界冲突。
- `Quant Tool Registry MCP server 化` 与 `AI Quant Lab` 深化
  - 原因：本轮 172 优先级切换到 broker 生态扩展，相关工作顺延。

### 1.3 主实施仓边界

本迭代的主实施仓为：

- Core repo: `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py`
- External package root: `/Users/yunjinqi/Documents/new_projects/bt_api/`

`backtrader_web` 在 172 中仅承担：

- 迭代文档与边界说明
- 消费侧 alias / capability / 配置映射的最小配合
- 跨仓执行顺序、验收标准、集成验证清单的固化

---

## 2. 总目标

| 维度 | 当前状态 | 迭代 172 目标 |
|---|---|---|
| 扩展包覆盖 | 基线只有 `alpaca / ib_web / mt5 / binance / okx / ctp` | 首批新增 14 个 `bt_api_xx` 包进入统一路线 |
| 形态一致性 | 已明确 old plugin mode，但只有 Alpaca 刚完成清晰样板收口 | 所有新增包统一遵循 `bt_api.plugins + register_plugin(registry, runtime_factory)` |
| 批量交付能力 | 目前更像单包推进 | 抽象出可复用模板、共享测试片段与统一验收口径 |
| bt_api_py 消费链 | 已验证 Alpaca 插件发现与消费 | 所有新增包都必须能被 `BtApi` 发现、创建 feed、更新余额并完成最小订阅/请求 smoke test |
| backtrader_web 边界 | 171 已明确收口，但后续执行次序未固化 | 明确 172 为 broker 生态扩展批次，web 侧继续只做消费方 |

---

## 3. 执行原则

### 3.1 必须遵守的架构原则

1. **全部新增券商都走独立 `bt_api_xx` 包**。
2. **全部新增包统一采用 old plugin mode**。
3. **`backtrader_web` 不承接任何 broker 主实现**。
4. **优先复用 `bt_api_alpaca` 已收口的模板结构**。
5. **先打通 package skeleton / plugin registration / `BtApi` 消费，再扩深资产类型与高级能力**。

### 3.2 每个包的最低结构要求

每个新包至少应包含：

- `pyproject.toml`
- `README.md`
- `<package>/__init__.py`
- `<package>/plugin.py`
- `<package>/registry_registration.py`
- `<package>/exchange_data.py`
- `<package>/runtime/feed.py`
- `<package>/gateway/adapter.py`
- `<package>/containers/<broker>_account.py`
- `tests/test_plugin.py`
- `tests/test_exchange_data.py`
- `tests/test_runtime_feed.py`
- `tests/test_contract.py`

### 3.3 每个包的最低能力要求

每个新增包至少要完成：

- `bt_api.plugins` entry point 声明
- `register_plugin(registry, runtime_factory) -> PluginInfo`
- `ExchangeRegistry` 中的 `feed / exchange_data / balance_handler`
- 如有条件，最小 `subscribe` handler
- `BaseGatewayAdapter` 兼容实现
- `BtApi` 侧最小消费 smoke test

---

## 4. 14 个扩展包清单与规范化命名

| 券商 | 推荐包名 | 推荐注册名 | P0 最小 exchange 目标 | P1 扩展目标 | 推荐批次 |
|---|---|---|---|---|---|
| Tradier | `bt_api_tradier` | `tradier` | `TRADIER___STK` | `TRADIER___OPT` | 172A |
| Saxo | `bt_api_saxo` | `saxo` | `SAXO___STK` | `SAXO___FX` | 172A |
| Zerodha | `bt_api_zerodha` | `zerodha` | `ZERODHA___STK` | `ZERODHA___FUT` / `ZERODHA___OPT` | 172B |
| Upstox | `bt_api_upstox` | `upstox` | `UPSTOX___STK` | `UPSTOX___FUT` / `UPSTOX___OPT` | 172B |
| Angel One | `bt_api_angelone` | `angelone` | `ANGELONE___STK` | `ANGELONE___FUT` / `ANGELONE___OPT` | 172B |
| Fyers | `bt_api_fyers` | `fyers` | `FYERS___STK` | `FYERS___FUT` / `FYERS___OPT` | 172B |
| Dhan | `bt_api_dhan` | `dhan` | `DHAN___STK` | `DHAN___FUT` / `DHAN___OPT` | 172B |
| Shoonya | `bt_api_shoonya` | `shoonya` | `SHOONYA___STK` | `SHOONYA___FUT` / `SHOONYA___OPT` | 172C |
| AliceBlue | `bt_api_aliceblue` | `aliceblue` | `ALICEBLUE___STK` | `ALICEBLUE___FUT` / `ALICEBLUE___OPT` | 172C |
| 5paisa | `bt_api_5paisa` | `5paisa` | `5PAISA___STK` | `5PAISA___FUT` / `5PAISA___OPT` | 172C |
| IIFL | `bt_api_iifl` | `iifl` | `IIFL___STK` | `IIFL___FUT` / `IIFL___OPT` | 172C |
| Kotak | `bt_api_kotak` | `kotak` | `KOTAK___STK` | `KOTAK___FUT` / `KOTAK___OPT` | 172C |
| Motilal | `bt_api_motilal` | `motilal` | `MOTILAL___STK` | `MOTILAL___FUT` / `MOTILAL___OPT` | 172C |
| Groww | `bt_api_groww` | `groww` | `GROWW___STK` | `GROWW___FUT` / `GROWW___OPT` | 172C |

说明：

- `5paisa` 的实际包名采用 `bt_api_5paisa`；由于前缀 `bt_api_` 已满足 Python 包名规则，因此不需要额外改写成 `fivepaisa`。
- `5paisa` 的 entry point 使用 `5paisa`，exchange key 统一为 `5PAISA___*`。
- `Angel One` 的包名与注册名统一收口为 `angelone`，避免空格和多写法并存。
- 上表中的 `P0 / P1` 是交付层级，不代表所有 broker 都必须在第一天完成全部资产类型。

---

## 5. 分批顺序

### 172A：国际 broker 样板批（P0）

目标：先用两个国际 broker 验证“Alpaca 之外的证券型券商”模板是否稳定。

- [x] `bt_api_tradier`
  - P0：`STK`
  - P1：`OPT`
  - 重点：证券账户 / 订单 / quote / history / 基础期权口径

- [x] `bt_api_saxo`
  - P0：`STK`
  - P1：`FX`
  - 重点：多市场 symbol mapping、账户结构、较复杂认证/会话

### 172B：Indian core batch（P0/P1）

目标：优先落地最具代表性的印度券商，形成可批量复用的 auth / symbol / order / F&O 模板。

- [x] `bt_api_zerodha`
- [x] `bt_api_upstox`
- [x] `bt_api_angelone`
- [x] `bt_api_fyers`
- [x] `bt_api_dhan`

共同要求：

- P0 至少先打通 `STK`
- P1 逐步补 `FUT / OPT`
- 抽离共性：Indian broker auth、instrument token / symbol lookup、product/order mapping、NSE/BSE/F&O 资产分层

### 172C：Indian long-tail batch（P1）

目标：在 172B 模板稳定后，批量补齐剩余 7 个券商。

- [x] `bt_api_shoonya`
- [x] `bt_api_aliceblue`
- [x] `bt_api_5paisa`
- [x] `bt_api_iifl`
- [x] `bt_api_kotak`
- [x] `bt_api_motilal`
- [x] `bt_api_groww`

共同要求：

- P0 优先 `STK`
- F&O 能力以统一模板补齐，不要求一开始全部达到生产深度一致
- 共享验证与 README 结构必须一致

### 172D：核心消费链与文档收口（跨仓）

- [x] 通过各扩展包内 `test_bt_api_integration.py` 覆盖 `PluginLoader / ExchangeRegistry / BtApi` 消费 smoke slice
- [x] 既有 `PluginLoader / ExchangeRegistry / BtApi` 消费链未因新增 14 个扩展包而破坏
- [x] `backtrader_web` 继续只保留消费侧 alias / capability / 文档协同，不回流 broker 实现

---

## 6. 每个包的完成标准

一个包只有在满足以下条件后，才算进入“172 已实现”清单：

1. 存在独立包目录与可安装 `pyproject.toml`
2. 声明 `bt_api.plugins` entry point
3. 能返回正确 `PluginInfo`
4. `ExchangeRegistry.create_feed()` 能创建该包的 `runtime/feed`
5. `BtApi.update_total_balance()` 能消费该包
6. 至少存在一个最小 `subscribe()` / 行情请求 smoke path（如 broker 本身支持）
7. `GatewayAdapter` 支持 `connect / disconnect / get_balance / get_positions / place_order / cancel_order`
8. 包内测试通过：`plugin / exchange_data / runtime_feed / contract`
9. README 说明安装、使用、限制项与测试命令
10. 不依赖 `backtrader_web` 私有实现

---

## 7. 风险切片

### 7.1 共同风险

- OAuth / token 生命周期与 refresh 逻辑差异大
- symbol / instrument token / 合约标识映射差异大
- 某些 broker 的 quote / history / order / positions 字段命名不统一
- WebSocket / push 流程可能依赖厂商专有 SDK 或 session
- 测试资产不足时，容易只做到 package skeleton 而未真正穿过 `BtApi` 消费链

### 7.2 分组风险

#### 国际 broker

- `Tradier`: 证券与期权资产口径不同，需要明确最小优先级
- `Saxo`: 认证、资产广度、symbol resolution 更复杂，容易过早把范围做大

#### Indian core batch

- `Zerodha / Upstox / Angel One / Fyers / Dhan` 可能各自有不同的 token、product type、instrument token 和订阅模式
- 如果没有抽出共性模板，后续 7 个 long-tail broker 的成本会显著升高

#### Indian long-tail batch

- API 文档可获得性与稳定性差异可能更大
- 某些 broker 的 F&O / WebSocket 能力可能不适合直接复制前一批做法
- 必须接受“P0 先做到 `STK`，P1 再补 F&O”这一现实切片

---

## 8. 与 `backtrader_web` 的协同边界

172 中 `backtrader_web` 可以做：

- 新增迭代与架构文档
- 记录 broker capability matrix
- 在消费侧维护最小 alias / provider name / exchange_type 归一化说明
- 为后续配置页、健康检查页、能力展示页补最小展示层兼容

172 中 `backtrader_web` 不做：

- 不新增 broker runtime / adapter 主实现
- 不在本仓定义第二套 plugin loader / registry
- 不把任何新 broker 的核心认证 / 下单 / 行情实现放回 FastAPI service

---

## 9. 任务分解

### 172T1：批量模板与共享契约先行（P0）

- [x] 从 `bt_api_alpaca` 提炼可复制模板
- [x] 明确 14 个包的命名、注册名与目录结构
- [x] 以各扩展包 `BtApi` 集成测试固化批量插件 smoke harness 规范
- [x] 固化 Indian broker 共享问题清单：auth、instrument lookup、order mapping、subscription mapping

### 172T2：国际 broker 样板包（P0）

- [x] `bt_api_tradier` skeleton + plugin registration + runtime feed + gateway adapter + tests
- [x] `bt_api_saxo` skeleton + plugin registration + runtime feed + gateway adapter + tests
- [x] 完成两包 README 与 `BtApi` 消费 smoke test

### 172T3：Indian core batch（P0/P1）

- [x] `bt_api_zerodha`
- [x] `bt_api_upstox`
- [x] `bt_api_angelone`
- [x] `bt_api_fyers`
- [x] `bt_api_dhan`
- [x] 将 Indian broker 的共享问题固化为统一的 `auth.py / mapping.py / transport.py / exchange_data.py` 模板，而不是回流到 web 仓

### 172T4：Indian long-tail batch（P1）

- [x] `bt_api_shoonya`
- [x] `bt_api_aliceblue`
- [x] `bt_api_5paisa`
- [x] `bt_api_iifl`
- [x] `bt_api_kotak`
- [x] `bt_api_motilal`
- [x] `bt_api_groww`

### 172T5：消费层与文档收口（跨仓）

- [x] 通过各扩展包 `test_bt_api_integration.py` 固化 `PluginLoader / ExchangeRegistry / BtApi` 消费 smoke path
- [x] `backtrader_web` 记录统一消费边界与配置映射
- [x] 14 个包均补齐统一 README / 安装 / 验证命令

---

## 10. 验收标准

### 10.1 功能验收

- 14 个券商都已进入独立 `bt_api_xx` 包路线
- 所有包都能被 `PluginLoader` 发现
- 所有包都能通过 `ExchangeRegistry` 被 `BtApi` 消费
- 至少完成：`balance / account / quote-or-kline / place_order / cancel_order` 的最小闭环
- `backtrader_web` 仍保持 consumer-only 边界

### 10.2 技术验收

- 包结构一致，不出现多套互相冲突的扩展模式
- 全部使用 old plugin mode，而不是回退到已废弃的新模式探索路径
- `bt_api_py` 不因新增 14 个扩展包破坏既有 `alpaca / ib_web / mt5 / binance / okx / ctp` 的消费链
- 每个包都有 targeted tests，不以“只有 README / skeleton”冒充完成

### 10.3 文档验收

- `docs/iterations/README.md` 已收录迭代 172
- 170 / 171 中对后续迭代的引用不再与当前 172 目标冲突
- 172 文档明确写清主实施仓与 web 仓边界

### 10.4 实际验收结果（2026-05-26）

- 14 个券商扩展包均已完成独立包落地
- `Tradier / Saxo / Zerodha / Upstox / Angel One / Fyers / Dhan / Shoonya / AliceBlue / 5paisa / IIFL / Kotak / Motilal / Groww` 对应仓库已完成 push 后 `CI = success`
- `backtrader_web` 在 172 中继续保持 consumer-only 边界，未回流任何 broker 主实现

---

## 11. 后续建议

若 172 完成后继续推进，建议顺序为：

- **迭代 173**：`MetaTrader4 / MetaApi` 桥接、剩余 broker 长尾、以及 `Quant Tool Registry` MCP server 化 / AI Quant Lab 深化
- **迭代 174**：全球市场扩展、复杂终端工作台深化、以及更强消费层产品化收口

但在 172 未完成前，不建议重新把 broker 工作分流回 `backtrader_web`。
