# Backtrader Web Frontend

基于 Vue 3 + TypeScript + Vite 的 Backtrader 量化交易回测 Web 前端。

## 技术栈

- **Vue 3** - 前端框架 (Composition API)
- **TypeScript** - 类型系统
- **Vite** - 构建工具
- **Pinia** - 状态管理
- **Vue Router** - 路由管理
- **Element Plus** - UI 组件库
- **Echarts** - 图表库
- **TailwindCSS** - CSS 框架
- **Axios** - HTTP 客户端

## 功能页面

- **Dashboard** - 仪表盘，统计概览
- **Backtest** - 回测分析，运行回测、查看结果
- **Strategy** - 策略管理，创建、编辑、删除策略
- **Data** - 数据查询，K 线图展示
- **Settings** - 系统设置

## 快速开始

### 1. 安装依赖

```bash
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:3000

### 3. 构建生产版本

```bash
npm run build
```

## 项目结构

```
frontend/
├── src/
│   ├── api/              # API 调用
│   │   ├── auth.ts
│   │   ├── backtest.ts
│   │   └── strategy.ts
│   ├── components/       # 组件
│   │   ├── charts/       # 图表组件
│   │   │   ├── KlineChart.vue
│   │   │   └── EquityCurve.vue
│   │   └── common/       # 通用组件
│   │       └── AppLayout.vue
│   ├── views/            # 页面
│   │   ├── Dashboard.vue
│   │   ├── BacktestPage.vue
│   │   ├── StrategyPage.vue
│   │   ├── DataPage.vue
│   │   └── SettingsPage.vue
│   ├── stores/           # Pinia 状态
│   │   ├── auth.ts
│   │   ├── backtest.ts
│   │   └── strategy.ts
│   ├── router/           # 路由
│   ├── types/            # TypeScript 类型
│   ├── App.vue
│   └── main.ts
├── package.json
├── vite.config.ts
├── tsconfig.json
└── tailwind.config.js
```

## 图表组件

### KlineChart

专业 K 线图组件，支持：
- 标准 K 线显示 (OHLC)
- MA 均线叠加
- 成交量柱状图
- DataZoom 缩放
- 十字线联动

### EquityCurve

资金曲线图组件，支持：
- 资金曲线折线图
- 回撤区域显示
- 缩放交互

## 环境配置

开发环境会自动将 `/api` 请求代理到后端服务 `http://localhost:8000`。

生产环境需配置 Nginx 反向代理。

## License

MIT
