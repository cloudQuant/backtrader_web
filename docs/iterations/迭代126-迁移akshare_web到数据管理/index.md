# 迭代126 - 迁移 akshare_web 到数据管理 - 文档索引

> **迭代目标**：将 `akshare_web` 的数据治理能力整合进 `backtrader_web` 的“数据管理”域  
> **文档状态**：已按当前项目真实代码基线重构  
> **交付对象**：产品、前端、后端、测试

---

## 1. 阅读顺序

| 文档 | 说明 | 建议阅读顺序 |
|------|------|--------------|
| [初始需求.md](初始需求.md) | 原始需求描述 | 1 |
| [迭代计划.md](迭代计划.md) | 主计划文档：目标、范围、阶段、风险、工期 | 2 |
| [总体方案设计.md](总体方案设计.md) | 架构设计、迁移边界、模块映射、技术决策 | 3 |
| [研发任务拆分与验收标准.md](研发任务拆分与验收标准.md) | Story 拆分、交付要求、DoD、测试口径 | 4 |
| [迁移预检与切换清单.md](迁移预检与切换清单.md) | 迁移前检查、对账、切库、回退操作清单 | 5 |

---

## 2. 本迭代要解决什么问题

当前 `backtrader_web` 已有 `数据管理` 页面，但能力主要集中在：

- 股票 K 线查询
- 期货 Gateway 账户与持仓查询

而 `akshare_web` 已经具备一套独立的数据治理能力，包括：

- 数据接口
- 定时任务
- 执行记录
- 数据表
- 接口管理

本次迭代的目标，是将这套能力整合到当前项目中，而不是维护两个并行后台。

---

## 3. 关键结论速览

- `数据管理` 仍保留侧边栏单一入口
- `/data` 将从单页升级为父子路由结构
- `市场数据` 作为 `/data/market` 子页面保留，数据源**不做任何改动**
- akshare 迁移能力使用新的页面、服务、API 和模型承接
- 后端 API 继续归属 `/api/v1/data/*`
- akshare 迁移过来的管理表使用 `ak_` 前缀，避免与主业务表冲突
- **数据库引擎**：采用**两个 MySQL 数据库**——`backtrader_web` + `akshare_data`
- 本迭代包含历史数据迁移：`akshare_web` 管理库数据与当前 SQLite 业务数据都要迁入 `backtrader_web`
- 迁移完成后，运行时不再依赖 SQLite
- **本迭代不对接回测**：akshare 数据仅作为数据治理能力落户，回测对接留给下一个迭代
- **前向兼容设计**：数据模型为后续对接回测预留扩展字段

---

## 4. 建议实施顺序

```text
先读需求 -> 冻结主计划 -> 看总体方案 -> 按研发任务文档拆工 -> 进入开发
```

推荐研发顺序：

```text
后端模型/Schema -> 服务层/调度器 -> API 路由 -> 前端容器页 -> 前端业务页 -> 联调测试
```

---

## 5. 研发进入前的前置决策（已全部冻结）

| # | 决策项 | 结论 |
|---|--------|------|
| 1 | 是否迁移 akshare_web 历史数据 | ✅ 迁移到 `backtrader_web` MySQL |
| 2 | SQLite 现有业务数据 | ✅ 迁移到 `backtrader_web` MySQL，迁移后停用 SQLite |
| 3 | akshare 管理表命名 | ✅ 使用 `ak_` 前缀落入 `backtrader_web` MySQL |
| 4 | 接口管理权限边界 | ✅ 仅管理员可操作（详见迭代计划 7.1） |
| 5 | 调度器部署假设 | ✅ 单实例部署 |
| 6 | 数据采集脚本迁移范围 | ✅ 分批迁移，首版优先最小闭环 |
| 7 | 数据库引擎方案 | ✅ 运行时只保留 `backtrader_web` + `akshare_data` 两个 MySQL |
| 8 | 是否对接回测 | ✅ 本迭代不对接，留给下一个迭代 |
| 9 | 是否修改 `/api/v1/data/kline` | ✅ 不修改 |
| 10 | `backtrader_web` MySQL 若不存在 | ✅ 本迭代负责创建 |

详细决策依据见 `迭代计划.md` 第 2.0 节、第 3.3 节、第 7 节。

切库执行细节见 `迁移预检与切换清单.md`。

---

## 6. 对应代码主落点

### 后端

```text
src/backend/app/db/database.py               # 主业务切换到 backtrader_web MySQL
src/backend/app/db/akshare_data_database.py  # 独立 akshare_data MySQL engine
src/backend/app/models/akshare_mgmt.py       # 新增：7 张 ak_ 前缀管理表模型
src/backend/app/schemas/akshare_mgmt.py      # 新增
src/backend/app/services/akshare_*.py        # 新增：多个服务文件
src/backend/app/api/akshare_*.py             # 新增：5 个 router 文件
src/backend/alembic/                         # 主库 MySQL schema 与迁移脚本
scripts/migrate_sqlite_to_mysql.py           # 新增：SQLite -> backtrader_web 数据迁移
scripts/migrate_akshare_web_to_mysql.py      # 新增：akshare_web -> backtrader_web 管理数据迁移
src/backend/.env.example                     # 更新 DATABASE_URL / AKSHARE_DATA_DATABASE_URL
```

### 前端

```text
src/frontend/src/views/data/
src/frontend/src/components/data/
src/frontend/src/api/
src/frontend/src/stores/
src/frontend/src/router/index.ts
```

---

## 7. 使用说明

如果你是：

- **产品/项目经理**：优先阅读 `迭代计划.md`
- **后端研发**：重点阅读 `总体方案设计.md` 与 `研发任务拆分与验收标准.md`
- **前端研发**：重点阅读 `迭代计划.md` 第 5、6 节与 `研发任务拆分与验收标准.md`
- **测试**：重点阅读 `研发任务拆分与验收标准.md` 的验收与测试部分
