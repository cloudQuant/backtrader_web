---
title: 首页
description: 基于 Backtrader 的现代化量化交易全栈管理平台
---

# Backtrader Web

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Vue](https://img.shields.io/badge/Vue-3.4+-green.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**基于 Backtrader 的现代化量化交易全栈管理平台**

[English](./en/){ .md-button }
[中文](./zh/){ .md-button }

</div>

## 功能特性

- 🚀 **开箱即用** - 5分钟完成首次回测
- 📊 **专业图表** - Echarts K线图 + 10+ 分析图表
- 🔌 **API优先** - 15+ 模块，80+ RESTful API 端点
- 💾 **多数据库** - 支持 SQLite / PostgreSQL / MySQL
- 🎯 **策略管理** - 策略版本控制 + 代码编辑器 + 118 内置模板
- 📈 **模拟交易** - 完整的模拟交易环境
- 🔴 **实盘交易** - 多券商实盘对接 (CTP/CCXT)
- 📡 **实时行情** - WebSocket 实时推送
- 🚨 **监控告警** - 实时监控和告警系统

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Echarts |
| 后端 | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 |
| 数据库 | SQLite (默认) / PostgreSQL / MySQL |
| 回测引擎 | Backtrader + fincore |
| 测试 | pytest + Playwright (E2E) + Vitest |

## 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web

# 后端安装
cd src/backend
python -m venv venv
source venv/bin/activate
pip install -e ".[dev,backtrader]"

# 前端安装
cd src/frontend
npm install
```

### 启动服务

**开发模式：**
```bash
# 后端
cd src/backend && uvicorn app.main:app --reload --port 8000

# 前端
cd src/frontend && npm run dev
```

**Docker 部署：**
```bash
docker compose -f docker-compose.prod.yml up -d
```

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端 (开发) | http://localhost:8080 |
| 前端 (Docker) | http://localhost |
| 后端 API 文档 | http://localhost:8000/docs |
| WebSocket | ws://localhost:8000/ws |

## 文档

- [快速开始](./getting-started/)
- [安装指南](./getting-started/installation.md)
- [快速上手](./getting-started/quickstart.md)
- [API 参考](./development/api.md)
- [架构设计](./development/architecture.md)

## 许可证

[MIT License](https://github.com/cloudQuant/backtrader_web/blob/main/LICENSE)
