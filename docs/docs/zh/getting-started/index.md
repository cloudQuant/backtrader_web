# 快速开始

本节帮助您完成一次最小、可验证的投研闭环：启动服务、选择数据、创建策略、运行回测并查看结果。

## 前提

- Python 3.10+、Node.js 20+、Git。
- 需要回测时安装 `backtrader` 额外依赖；需要在线行情时安装 `akshare`；需要语义检索时安装 `rag` 额外依赖。
- 生产或团队协作环境建议使用 PostgreSQL/MySQL；默认应用数据库可以使用 SQLite。

## 推荐路径

1. [安装指南](./installation.md)：创建后端环境、安装前端依赖并配置 `.env`。
2. [快速上手](./quickstart.md)：从市场数据到研究工作区完成首次回测。
3. [知识库](../features/knowledge-base.md)：导入、建立索引并使用带引用的问答。
4. [市场数据](../features/market-data.md)：理解本地 MySQL 优先和手动 AkShare 刷新的行为。

## 运行前检查

仓库提供环境检查脚本；在依赖安装前后各运行一次：

```bash
./scripts/dev/verify-dev-env.sh --preinstall
./scripts/dev/verify-dev-env.sh --postinstall
```

API 契约以运行中的 `http://localhost:8000/docs` 为准。页面和 API 均要求登录；管理员设置页还需要管理员权限。
