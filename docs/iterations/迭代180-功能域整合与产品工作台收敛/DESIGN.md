# 迭代 180 设计方案 - 功能域整合与产品工作台收敛

> **创建日期**: 2026-06-13
> **对应计划**: `PLAN.md`
> **设计目标**: 保留所有现有功能，通过能力地图、产品域导航、canonical route 和状态聚合完成第一阶段产品整合。

---

## 1. 设计边界

本设计只处理“入口和编排层”，不重写业务能力：

- 前端：新增能力地图与产品域导航，新增 canonical route，旧 route 保留。
- 后端：新增能力状态聚合端点，复用现有 optional router status。
- 文档：补齐能力地图、工作流和验收说明。
- 不做：交易写路径、网关生命周期、Broker adapter、数据源新增、数据库 schema 大改。

---

## 2. 核心模型

### 2.1 Product Domain

产品域是用户理解平台的第一层入口。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 稳定 ID，如 `research` |
| `path` | string | canonical route，如 `/research` |
| `labelKey` | string | i18n key |
| `icon` | string | UI 图标名 |
| `requiresAdmin` | boolean | 是否管理员可见 |

首批产品域：

- `home`
- `data`
- `research`
- `trading`
- `portfolio`
- `ai`
- `admin`

### 2.2 Capability

Capability 是一个可导航、可验收、可归属的功能单元。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 稳定能力 ID，如 `research.strategies` |
| `domainId` | string | 所属产品域 |
| `path` | string | canonical path |
| `labelKey` | string | i18n key |
| `legacyPaths` | string[] | 旧路径，兼容期保留 |
| `requiresAdmin` | boolean | 权限 |
| `status` | `stable/beta/admin/legacy/hidden` | UI 与文档状态 |

能力地图是前端导航、页面标题、面包屑、文档和验收用例的共同真相源。

---

## 3. 前端设计

### 3.1 文件结构

```text
src/frontend/src/navigation/
  capabilities.ts        # 产品域与能力地图

src/frontend/src/components/common/
  AppLayout.vue          # 使用 capability registry 渲染一级导航与当前域二级导航
```

### 3.2 导航策略

- 左侧栏只渲染产品域：最多 7 项。
- Header 中渲染当前域的二级入口。
- 当前页面标题优先来自匹配 capability；无法匹配时使用产品域名称。
- 桌面和移动端使用同一份 `productDomains` 配置。
- `requiresAdmin` 在导航层过滤，同时 route guard 继续负责强约束。

### 3.3 路由策略

新增 canonical routes，但不删除旧 routes。

示例：

```text
/strategy                    # old, 保留
/research/strategies         # new canonical

/workspace                   # old, 保留
/research/workspaces         # new canonical

/quote                       # old, 保留
/data/quote                  # new canonical
```

旧路径至少保留两个迭代周期。后续是否移除要依赖访问 telemetry，而不是凭主观判断。

---

## 4. 后端设计

### 4.1 新端点

新增：

```text
GET /api/v1/status/capabilities
```

响应结构：

```json
{
  "domains": [
    {
      "id": "research",
      "label": "Strategy Research",
      "status": "available",
      "capabilities": [
        {
          "id": "strategy",
          "api_prefixes": ["/api/v1/strategy"],
          "available": true,
          "requires_admin": false,
          "degraded_reason": null
        }
      ]
    }
  ]
}
```

### 4.2 可用性来源

- core API 默认 `available=true`。
- optional API 通过 `app.api.router.optional_router_status` 判断。
- 一个 capability 包含多个 optional prefix 时，只要关键依赖不可用，即标记 `degraded`。
- 不替换 `/api/v1/status/routers`，只提供产品域聚合视图。

---

## 5. 文档设计

新增：

```text
docs/product/CAPABILITY_MAP.md
docs/product/WORKFLOWS.md
```

首批可以在迭代文档中先沉淀，后续再同步到 `docs/product/`。

---

## 6. 兼容性要求

- 旧页面路径直接访问不能 404。
- 旧页面刷新不能丢失参数。
- route guard 对新旧路径表现一致。
- admin-only 的旧路径和新路径都必须校验权限。
- 新导航不改变 API 调用 payload 和返回结构。

---

## 7. 开发切片

### Slice 1 - 文档与能力地图

- 新增设计/验收文档。
- 新增 `capabilities.ts`。
- 更新 i18n 仅补产品域必要 key。

### Slice 2 - 导航收敛

- `AppLayout.vue` 改为读取 registry。
- 左侧只显示产品域。
- Header 显示当前域二级入口。

### Slice 3 - Canonical route

- 新增 `/research/*`、`/data/quote`、`/data/intelligence/*`、`/trading/*`、`/portfolio/*`、`/ai/*`、`/admin/settings`。
- 保留旧 route。

### Slice 4 - 后端状态聚合

- 新增 `/status/capabilities`。
- 增加单测。

### Slice 5 - 验收测试

- 前端 router/AppLayout 测试覆盖新导航和旧路径。
- 后端 status 测试覆盖聚合结构。

