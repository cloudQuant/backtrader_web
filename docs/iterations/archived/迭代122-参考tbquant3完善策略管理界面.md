# 迭代122 - 参考TBQuant3完善策略管理界面

## 1. 概述

本文档基于 **TBQuant3 实际运行界面截图** 和 **backtrader_web 前后端源码** 的深入对比分析，提出具体的界面改进和功能完善方案。

**参考来源**:
- TBQuant3 v1.3.9.4 运行截图 (30+ 张，保存在 `docs/tbquant_screenshots/`)
- TBQuant3 安装目录分析 (`D:\program\TBQuant`)
- [TBQuant3帮助文档](https://tbq3.tbquant.net/helper)
- backtrader_web 前端源码 (15个页面, 13个组件)
- backtrader_web 后端源码 (23个API模块, 20+个服务)

**创建时间**: 2026-03-13

---

## 2. 功能对比总表

> 基于 TBQuant3 实际截图 vs backtrader_web 源码的逐项对比

### 2.1 backtrader_web 已实现且与 TBQuant3 对齐的功能

| 功能 | TBQuant3 | backtrader_web | 质量评估 |
|-----|---------|---------------|---------|
| 策略创建/编辑 | 公式管理器 + TB语言编辑器 | StrategyPage + Monaco编辑器(Python) | 基本对齐 |
| 策略模板库 | 内置多种策略模板 | 策略Gallery + 分类筛选(6类) | 基本对齐 |
| 策略回测 | 策略研究模块 | BacktestPage + 异步执行 + WebSocket进度 | 基本对齐 |
| 参数优化 | ArgumentsOptimize.dll | OptimizationPage + 网格搜索 + 并行优化 | 基本对齐 |
| 模拟交易 | 内置模拟模式 | SimulatePage + 子进程管理 | 基本对齐 |
| 实盘交易 | AutoTrade.dll + AlgoTrade.dll | LiveTradingPage + Gateway连接 | 基本对齐 |
| 数据查询 | Quote.dll 行情模块 | DataPage + AkShare数据源 | 部分对齐 |
| 回测结果分析 | 绩效报告 | EquityCurve/DrawdownChart/TradeSignalChart 等6个图表组件 | 基本对齐 |
| 自动交易调度 | 模式运行管理 | AutoTradingScheduler + 交易时段配置 | 基本对齐 |

### 2.2 backtrader_web 独有优势（TBQuant3 不具备）

| 功能 | backtrader_web 实现 | 价值 |
|-----|-------------------|------|
| **Web访问** | 浏览器随时访问，无需安装 | 远程管理、跨平台 |
| **策略版本控制** | Git风格分支/回滚/版本对比 | 策略迭代管理 |
| **RBAC权限** | 角色/权限管理 | 多人协作 |
| **回测对比** | 多回测结果并排对比 | 策略选优 |
| **告警系统** | AlertRule + 多通道通知 | 风险监控 |
| **REST API** | 23个API模块，可编程 | 二次开发 |
| **组合管理** | PortfolioPage + 资产配置 | 组合分析 |
| **月度收益热力图** | ReturnHeatmap组件 | 可视化分析 |

### 2.3 TBQuant3 有但 backtrader_web 缺失的功能

> 以下是基于**实际截图**确认的功能差距，按影响程度排序

| # | 功能 | TBQuant3 实现(截图来源) | 对 backtrader_web 的价值 | 优先级 |
|---|-----|----------------------|----------------------|-------|
| 1 | **实时策略监控面板** | 监控器 + 模式运行(策略菜单截图) | 策略运行状态一览，快速启停 | P0 |
| 2 | **实时资金曲线** | 策略菜单独立入口"实时资金曲线" | 运行中策略的实时权益推送 | P0 |
| 3 | **策略代码验证反馈** | 编译状态实时提示，错误行定位 | 编辑即验证，减少运行时错误 | P0 |
| 4 | **K线图表集成** | 独立K线工作区，内置15+技术指标 | 回测/交易中实时查看行情 | P1 |
| 5 | **工作区/多Tab系统** | 多Tab并行工作(截图可见多Tab) | 同时查看多个功能页面 | P1 |
| 6 | **双行快捷工具栏** | 30+个一键功能按钮(toolbar截图) | 高频操作快速访问 | P1 |
| 7 | **底部状态栏** | 实时滚动指数行情(主界面截图) | 市场动态一览 | P1 |
| 8 | **可视化策略生成器** | 生成器模块(19_data_center截图) | 降低策略开发门槛 | P2 |
| 9 | **策略文件夹/分组** | 公式管理器树形结构 | 策略数量多时分类管理 | P2 |
| 10 | **策略导入/导出** | 公式导入导出功能 | 策略分享与备份 | P2 |
| 11 | **深色专业主题** | 全局深色主题(所有截图) | 专业量化软件观感 | P2 |
| 12 | **期权T型报价** | T型报价视图(08截图) | 期权交易支持 | P3 |
| 13 | **指数板块分类** | 指数报价+板块标签(25截图) | 多维度行情分析 | P3 |

---

## 3. P0 优先级 - 详细改进方案

### 3.1 实时策略监控面板

#### 现状问题

backtrader_web 的 SimulatePage 和 LiveTradingPage 提供了实例列表和启停操作，但**缺少集中监控视图**。用户需要逐一点击进入各实例详情页才能了解运行状态，没有全局概览。

#### TBQuant3 参考 (来自策略菜单截图)

TBQuant3 的"监控器"和"模式运行管理"提供：
- 所有运行中策略的集中面板
- 实时状态指示（运行中/停止/异常）
- 快速启停操作
- 实时资金曲线缩略图

#### 改进方案

**新增页面**: `MonitorDashboard.vue`

```
┌─────────────────────────────────────────────────────────────────┐
│  策略监控中心                               [全部启动] [全部停止] │
├─────────────────────────────────────────────────────────────────┤
│  运行中: 3  │  已停止: 2  │  异常: 1  │  总收益: +12.5%        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────┐  ┌──────────────────────┐            │
│  │ 双均线策略           │  │ RSI策略              │            │
│  │ 状态: 🟢 运行中      │  │ 状态: 🟢 运行中      │            │
│  │ 收益: +5.2%         │  │ 收益: +3.1%         │            │
│  │ 持仓: IF2406 多1手   │  │ 持仓: 无            │            │
│  │ ~~~权益曲线缩略图~~~ │  │ ~~~权益曲线缩略图~~~ │            │
│  │ [停止] [详情] [日志] │  │ [停止] [详情] [日志] │            │
│  └──────────────────────┘  └──────────────────────┘            │
│  ┌──────────────────────┐  ┌──────────────────────┐            │
│  │ 布林带策略           │  │ MACD策略              │            │
│  │ 状态: 🔴 异常        │  │ 状态: ⚪ 已停止       │            │
│  │ 错误: 连接超时       │  │ 上次收益: -1.2%       │            │
│  │ [重启] [详情] [日志] │  │ [启动] [详情] [编辑]  │            │
│  └──────────────────────┘  └──────────────────────┘            │
├─────────────────────────────────────────────────────────────────┤
│  实时日志流 (最新10条)                                [清除]    │
│  15:23:01 [双均线] 信号: IF2406 买入开仓 @ 4601.8              │
│  15:22:45 [RSI] 指标更新: RSI=45.2                             │
│  15:22:30 [布林带] 错误: Gateway 连接超时，正在重连...          │
└─────────────────────────────────────────────────────────────────┘
```

**技术实现**:
- 前端: 新增 `MonitorDashboard.vue` 页面
- 后端: 复用 `simulation.py` 和 `live_trading_api.py` 的实例列表接口
- WebSocket: 复用 `websocket_manager.py`，新增 `/ws/monitor` 端点推送所有实例的聚合状态
- 路由: `/monitor` 加入 AppLayout 侧边栏

**改动文件**:
- 新增: `src/frontend/src/views/MonitorDashboard.vue`
- 新增: `src/frontend/src/api/monitor.ts`
- 修改: `src/frontend/src/router/index.ts` (添加路由)
- 修改: `src/frontend/src/components/common/AppLayout.vue` (侧边栏添加"策略监控")
- 修改: `src/backend/app/main.py` (添加 WebSocket 端点)

---

### 3.2 实时资金曲线

#### 现状问题

backtrader_web 的 EquityCurve 组件只展示**回测完成后**的静态曲线。策略运行过程中（模拟/实盘）没有实时资金推送。

#### TBQuant3 参考

TBQuant3 在策略菜单中有独立的"实时资金曲线"入口，可在策略运行时查看实时权益变化。

#### 改进方案

**增强现有组件**: `EquityCurve.vue` 添加实时模式

```typescript
// 新增 WebSocket 推送端点
// src/backend/app/api/live_trading_api.py
@router.websocket("/ws/equity/{instance_id}")
async def equity_ws(websocket: WebSocket, instance_id: str):
    """推送策略实例的实时权益数据"""
    await manager.connect(websocket, instance_id)
    try:
        while True:
            equity = await get_instance_equity(instance_id)
            await websocket.send_json({
                "timestamp": equity.timestamp.isoformat(),
                "value": equity.total_value,
                "cash": equity.cash,
                "positions_value": equity.positions_value,
                "drawdown": equity.current_drawdown,
            })
            await asyncio.sleep(5)  # 每5秒推送一次
    except WebSocketDisconnect:
        manager.disconnect(websocket, instance_id)
```

```vue
<!-- EquityCurve.vue 增强 -->
<template>
  <div>
    <div class="flex justify-between items-center mb-2">
      <span class="font-medium">权益曲线</span>
      <el-tag v-if="realtime" type="success" size="small">实时</el-tag>
    </div>
    <v-chart :option="chartOption" :autoresize="true" />
  </div>
</template>

<script setup>
const props = defineProps({
  data: Array,          // 静态数据(回测用)
  instanceId: String,   // 实例ID(实时用)
  realtime: Boolean,    // 是否实时模式
})
</script>
```

**改动文件**:
- 修改: `src/frontend/src/components/charts/EquityCurve.vue` (添加 realtime props 和 WebSocket 连接)
- 修改: `src/backend/app/api/live_trading_api.py` (添加 equity WebSocket)
- 修改: `src/frontend/src/views/SimulateDetailPage.vue` (嵌入实时曲线)
- 修改: `src/frontend/src/views/LiveTradingDetailPage.vue` (嵌入实时曲线)
- 修改: 上方 MonitorDashboard.vue 中的策略卡片嵌入缩略图

---

### 3.3 策略代码验证反馈

#### 现状问题

backtrader_web 后端已有 `sandbox.py` 实现策略代码安全检查，但**前端没有集成验证按钮**。用户编写策略代码后只能运行回测才能发现错误，体验差。

#### TBQuant3 参考

TBQuant3 的公式管理器在编辑器中提供：
- 编译按钮 (Ctrl+F7)
- 实时编译状态提示
- 错误行定位

#### 改进方案

**增强策略编辑对话框**: StrategyPage.vue

```
┌─────────────────────────────────────────────────────────────────┐
│  编辑策略 - 双均线策略                                          │
├─────────────────────────────────────────────────────────────────┤
│  名称: [双均线策略          ]                                   │
│  分类: [趋势策略 ▼]                                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  1│ import backtrader as bt                             │   │
│  │  2│                                                     │   │
│  │  3│ class DualMA(bt.Strategy):                          │   │
│  │  4│     params = (('fast', 5), ('slow', 20))            │   │
│  │  5│                                                     │   │
│  │  6│     def __init__(self):                             │   │
│  │  7│         self.sma_fast = bt.ind.SMA(period=self.p.fast) │
│  │  8│         self.sma_slow = bt.ind.SMA(period=self.p.slow) │
│  │  9│                                                     │   │
│  │ 10│     def next(self):                                 │   │
│  │ 11│         if self.sma_fast > self.sma_slow:           │   │
│  │ 12│             self.buy()                              │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  验证结果:                                                      │
│  ✅ 语法检查通过                                                │
│  ✅ 发现策略类: DualMA (继承 bt.Strategy)                       │
│  ✅ 提取到参数: fast(默认5), slow(默认20)                       │
│  ⚠️ 建议: 缺少 stop() 方法，可能无法获取最终统计               │
├─────────────────────────────────────────────────────────────────┤
│                                      [验证代码] [保存] [取消]   │
└─────────────────────────────────────────────────────────────────┘
```

**后端新增验证API**:

```python
# src/backend/app/api/strategy.py 新增
@router.post("/validate", summary="验证策略代码")
async def validate_strategy_code(request: ValidateRequest):
    """验证策略代码的语法、结构正确性，提取参数"""
    sandbox = StrategySandbox()
    result = {
        "valid": False,
        "errors": [],
        "warnings": [],
        "strategy_class": None,
        "params": [],
    }

    # 1. Python语法检查 (ast.parse)
    try:
        tree = ast.parse(request.code)
    except SyntaxError as e:
        result["errors"].append({
            "line": e.lineno,
            "message": f"语法错误: {e.msg}",
        })
        return result

    # 2. 安全检查 (复用sandbox)
    safety_issues = sandbox.check_code_safety(request.code)
    if safety_issues:
        result["errors"].extend(safety_issues)
        return result

    # 3. 策略类检查 (在sandbox中执行)
    try:
        strategy_cls = sandbox.discover_strategy(request.code)
        result["strategy_class"] = strategy_cls.__name__
        result["params"] = extract_params(strategy_cls)
        result["valid"] = True
    except Exception as e:
        result["errors"].append({"message": str(e)})

    # 4. 建议检查
    if not has_method(tree, "stop"):
        result["warnings"].append("缺少 stop() 方法")
    if not has_method(tree, "__init__"):
        result["warnings"].append("缺少 __init__() 方法")

    return result
```

**改动文件**:
- 修改: `src/frontend/src/views/StrategyPage.vue` (添加验证按钮和结果面板)
- 新增: `src/frontend/src/api/strategy.ts` 中添加 `validateCode()` 方法
- 修改: `src/backend/app/api/strategy.py` (添加 `/validate` 端点)
- 修改: `src/backend/app/utils/sandbox.py` (抽取 `check_code_safety` 和 `discover_strategy` 为公开方法)

---

## 4. P1 优先级 - 改进方案

### 4.1 K线图表集成增强

#### 现状

backtrader_web 有 `KlineChart.vue` 组件，但仅用于回测结果展示（BacktestResultPage）。

#### TBQuant3 参考 (来自截图 08_after_dialog.png)

TBQuant3 的K线图表功能包含：
- 多时间周期切换 (分时/5分钟/15分钟/30分钟/日线/周线)
- 15+ 技术指标 (MACD, KDJ, RSI, BOLL, WR, OBV, CCI, KD, DMA, TRIX)
- 买卖信号标注
- 绘图工具 (画线、标注)
- 联动功能 (多图表联动)

#### 改进方案

1. **增强 KlineChart.vue**:
   - 添加时间周期切换按钮组
   - 添加技术指标选择器（MACD/KDJ/RSI/BOLL 至少4种）
   - 指标在副图区域显示
   - 买卖信号用箭头标注在K线上

2. **在 DataPage 中嵌入K线图表**:
   - 查询数据后不仅显示表格，同时显示K线图
   - 支持选择技术指标叠加显示

3. **在策略监控详情中嵌入K线**:
   - 实时K线 + 策略信号标注

**改动文件**:
- 修改: `src/frontend/src/components/charts/KlineChart.vue` (添加周期切换、指标选择)
- 修改: `src/frontend/src/views/DataPage.vue` (嵌入K线图表)
- 修改: `src/frontend/src/views/SimulateDetailPage.vue` (嵌入K线)

---

### 4.2 多Tab工作区系统

#### 现状

backtrader_web 使用传统的单页面路由切换，同一时间只能查看一个功能页面。

#### TBQuant3 参考

TBQuant3 支持多Tab并行工作(截图中可见"行情报价"、"T型报价"、"生成器"等多个Tab同时打开)。

#### 改进方案

在 AppLayout.vue 中引入 Tab 系统：

```
┌──────────────────────────────────────────────────────────────────┐
│ [侧边栏]  │  [策略管理 x] [回测分析 x] [策略监控 x] [+ 新建]    │
│            ├──────────────────────────────────────────────────────┤
│  首页      │                                                      │
│  回测分析  │  当前选中Tab的内容                                    │
│  策略管理  │                                                      │
│  策略监控  │                                                      │
│  ...       │                                                      │
└────────────┴──────────────────────────────────────────────────────┘
```

**实现要点**:
- 使用 Pinia store 管理打开的 Tab 列表
- Tab 支持关闭(x按钮)和切换
- 使用 `<keep-alive>` 缓存已打开的页面状态
- 侧边栏点击打开新Tab或切换到已有Tab

**改动文件**:
- 修改: `src/frontend/src/components/common/AppLayout.vue` (添加Tab栏)
- 新增: `src/frontend/src/stores/tabs.ts` (Tab状态管理)
- 修改: `src/frontend/src/router/index.ts` (路由切换时更新Tab)

---

### 4.3 快捷工具栏

#### 现状

backtrader_web 仅通过侧边栏导航，没有工具栏快捷入口。

#### TBQuant3 参考 (来自 toolbar_detail.png)

TBQuant3 有双行工具栏共30+个快捷按钮，一键触达核心功能。

#### 改进方案

在 AppLayout 顶部添加可折叠的快捷工具栏：

```
┌─────────────────────────────────────────────────────────────────────┐
│ [+新建策略] [运行回测] [参数优化] | [启动监控] [停止全部] | [数据查询] │
└─────────────────────────────────────────────────────────────────────┘
```

- 显示当前上下文最相关的6-8个快捷操作
- 支持折叠/展开
- 不同页面显示不同的快捷按钮集

---

### 4.4 底部状态栏

#### TBQuant3 参考 (来自主界面截图)

底部滚动显示: 上证指数 4095.45 -33.65 -0.81% | 深证成指 14280.78 -94.09 -0.65% | ...

#### 改进方案

在 AppLayout 底部添加固定状态栏：

```vue
<!-- AppLayout.vue 底部 -->
<div class="fixed bottom-0 w-full h-6 bg-slate-800 text-xs text-gray-300 flex items-center px-4">
  <span class="mr-4">连接: <span class="text-green-400">正常</span></span>
  <span class="mr-4">运行策略: 3</span>
  <span class="mr-4">|</span>
  <!-- 实时指数数据(如果有数据源) -->
  <marquee scrollamount="2">
    上证指数 4095.45 -33.65 -0.81% | 深证成指 14280.78 | 沪深300 4669.14
  </marquee>
</div>
```

---

## 5. P2 优先级 - 改进方案

### 5.1 可视化策略生成器

#### TBQuant3 参考 (来自 19_data_center.png 截图)

TBQuant3 的生成器提供:
- 预设进出场模式 (EntryStop, ExitStop, TrailEntry, TrailStop 等)
- 可视化配置参数
- 公式组合与依赖管理
- 一键生成策略代码

#### 改进方案

新增简化版策略生成器页面 `StrategyGenerator.vue`:

```
┌─────────────────────────────────────────────────────────────────┐
│  策略生成器                                        [生成代码]    │
├──────────────┬──────────────────────────────────────────────────┤
│ 选择策略模式 │  参数配置                                        │
│              │                                                  │
│ ○ 均线交叉   │  快线周期: [5  ]                                 │
│ ● 突破策略   │  慢线周期: [20 ]                                 │
│ ○ RSI反转    │  突破周期: [20 ]                                 │
│ ○ 布林通道   │                                                  │
│ ○ 自定义组合 │  止损设置:                                       │
│              │  ☑ 固定止损  比例: [2 ]%                         │
│              │  ☐ 跟踪止损                                      │
│              │                                                  │
│              │  仓位管理:                                       │
│              │  ● 固定比例 [10]%  ○ 固定手数 [1]手              │
├──────────────┴──────────────────────────────────────────────────┤
│  生成的代码预览:                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  class BreakoutStrategy(bt.Strategy):                    │  │
│  │      params = (('period', 20), ('stop_loss', 0.02))     │  │
│  │      ...                                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            [复制代码] [保存为我的策略] [直接回测] │
└─────────────────────────────────────────────────────────────────┘
```

---

### 5.2 策略文件夹/分组管理

#### 现状

StrategyPage 的"我的策略"Tab使用平铺的表格列表，无分组功能。

#### 改进方案

1. 后端新增 `StrategyGroup` 模型 (id, name, parent_id, user_id)
2. 前端"我的策略"Tab改为左侧树形目录 + 右侧策略列表：

```
┌──────────────┬────────────────────────────────────────────────┐
│ 📁 全部策略  │  策略列表                      [卡片|列表] 视图  │
│ 📁 趋势策略  │  ┌─────────────────────────────────────────┐   │
│   ├ 双均线   │  │ 双均线策略    趋势    2天前  [编辑][删除] │   │
│   └ MACD     │  │ MACD策略     趋势    5天前  [编辑][删除] │   │
│ 📁 均值回归  │  └─────────────────────────────────────────┘   │
│   └ RSI      │                                                │
│ 📁 实验中    │                                                │
│ [+ 新建分组] │                                                │
└──────────────┴────────────────────────────────────────────────┘
```

---

### 5.3 策略导入/导出

#### 改进方案

- 导出: 将策略代码 + 参数配置 + README打包为 `.json` 或 `.zip` 文件
- 导入: 上传文件后预览并导入为"我的策略"
- 后端新增: `POST /strategy/export/{id}`, `POST /strategy/import`

---

### 5.4 深色专业主题优化

#### 现状

backtrader_web 已有 ThemeToggle 组件支持 dark/light 切换，但深色主题并非默认，且可能未对所有组件充分适配。

#### TBQuant3 参考 (所有截图均为深色主题)

TBQuant3 全局使用深蓝黑色主题 (#0D0D1A 背景)，所有截图一致。

#### 改进方案

1. 将深色主题设为默认主题
2. 检查并适配所有 Element Plus 组件的深色样式
3. 参考 TBQuant3 配色方案调整深色主题色值：
   - 主背景: `#0D0D1A` (极深蓝黑)
   - 面板背景: `#1A1A2E` (深蓝灰)
   - 上涨: `#FF3333` (红)
   - 下跌: `#33FF33` (绿)
   - 高亮选中: `#0A3050` (深蓝)

---

## 6. 实施路线图

### Phase 1: 核心监控 (1-2周)

| 任务 | 类型 | 改动范围 |
|-----|------|---------|
| 新增策略监控面板页面 | 新增 | 前端1个页面 + 后端1个WebSocket |
| 策略代码验证API | 新增 | 后端1个端点 + 前端策略编辑器改造 |
| 实时资金曲线推送 | 增强 | 前端组件改造 + 后端WebSocket |

### Phase 2: 交互体验 (1-2周)

| 任务 | 类型 | 改动范围 |
|-----|------|---------|
| K线图表增强(周期/指标) | 增强 | 前端组件改造 |
| 多Tab工作区 | 新增 | 前端布局改造 + Pinia store |
| 快捷工具栏 | 新增 | 前端布局改造 |
| 底部状态栏 | 新增 | 前端布局改造 |

### Phase 3: 功能扩展 (2-3周)

| 任务 | 类型 | 改动范围 |
|-----|------|---------|
| 可视化策略生成器 | 新增 | 前端1个页面 |
| 策略分组/文件夹 | 新增 | 前后端各1个模块 |
| 策略导入/导出 | 新增 | 后端2个端点 + 前端UI |
| 深色主题适配 | 优化 | 全局样式调整 |

---

## 7. 附录

### 7.1 backtrader_web 现有技术栈

| 层级 | 技术 |
|-----|------|
| 前端框架 | Vue 3.4 + TypeScript |
| UI组件 | Element Plus 2.5 |
| 状态管理 | Pinia 2.1 |
| 图表 | ECharts 5.4 + Vue-ECharts |
| 代码编辑 | Monaco Editor 0.55 |
| 样式 | Tailwind CSS 3.4 |
| 后端框架 | FastAPI (async) |
| 数据库 | SQLAlchemy 2.x (SQLite/PostgreSQL/MySQL) |
| 认证 | JWT + bcrypt |
| 实时通信 | WebSocket (内置) |
| 数据源 | AkShare (A股) |

### 7.2 TBQuant3 截图索引

详见 `docs/TBQUANT_SCREENSHOTS.md`

### 7.3 关键截图参考

| 截图 | 分析要点 |
|-----|---------|
| `01_main_interface.png` | 完整工具栏布局、行情表格结构、底部状态栏 |
| `17_strategy_trading.png` | 策略菜单10个子功能完整列表 |
| `toolbar_detail.png` | 双行工具栏30+按钮布局 |
| `08_after_dialog.png` | T型报价+K线+15种技术指标 |
| `19_data_center.png` | 生成器三栏布局、模式策略树、参数配置 |
| `25_account_menu.png` | 指数报价+板块分类 |

---

## 8. 更新记录

| 版本 | 日期 | 更新内容 |
|-----|------|---------|
| 1.0 | 2026-03-13 | 初始版本，基于 TBQuant3 官方文档分析 |
| 1.1 | 2026-03-13 | 添加本地 TBQuant 安装目录探索结果 |
| 1.2 | 2026-03-13 | 新增界面布局方案、策略分组管理、快捷键系统、风控面板等改进方案 |
| 2.0 | 2026-03-13 | 添加 TBQuant3 实际运行界面截图分析 |
| **3.0** | **2026-03-13** | **全面重写**: 基于TBQuant3截图 + backtrader_web源码的逐项对比分析；明确已有/缺失/独有功能；P0-P3优先级改进方案含具体代码和文件改动清单 |

---

*文档版本: 3.0*
*最后更新: 2026-03-13*
*分析方法: TBQuant3 实际截图(30+张) + backtrader_web 源码分析(前端15页面+13组件, 后端23API+20服务)*
