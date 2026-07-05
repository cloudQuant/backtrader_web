# MVP Prelaunch Notes

更新日期：2026-06-13

## 本轮已处理

- 生产环境配置安全：`DEBUG=false` 时拒绝 `CORS_ORIGINS=*`，避免带凭证跨域被误放开。
- 知识库源文件下载：移除裸 `axios` 和手写 `Authorization`，统一走前端 `api` 客户端复用 token 注入、重试和 401 处理。
- 历史知识库迁移：确认旧数据来源为 ReqDocs 的 `document_management` MySQL/MongoDB；已按 10 篇文档一批迁移到当前 `ai_for_investor` 知识库表，结果为 44 个知识库、30,148 篇文档、11 个对话、44 条消息，且 44 个知识库均可公开读取。
- 知识库页面初始化：前端默认知识库列表请求改为 `limit=100`，避免历史 44 个知识库被后端默认 20 条分页截断。
- 知识库文档列表减载：`GET /knowledge-base/{kb_id}/documents/` 已改为只返回文档摘要，不再查询/返回正文；页面选中文档后再调用详情接口加载正文。16,422 篇文档的大知识库摘要读取 smoke 为 0.43s，响应项无 `content` 字段。
- 前端 lint error：修复策略编辑/详情、数据同步配置表单的 prop mutation；修复一个测试变量声明问题。
- 单测收集：`vitest.config.ts` 纳入 `.spec.ts`，避免历史 spec 测试文件被 `npm run test` 漏跑。

## 剩余非阻塞项

- `npm run lint` 当前为 0 error，但仍有 warning，主要集中在旧组件缩进、属性顺序和少量 `any` 类型。未在本轮批量格式化，避免扩大 diff。
- `npm run build` 通过，但 Vite 仍提示 Monaco、ECharts、Element Plus 等 vendor chunk 超过 500KB。现有 bundle gate 已通过，入口 chunk gzip 约 174KB，登录页非 vendor JS 数量为 2；后续如继续优化，应按页面懒加载编辑器/图表依赖。
- `npm run test -- --run` 通过，但 happy-dom/DOMPurify 的恶意 HTML/iframe 场景会输出非阻塞 stderr 噪音；测试结果为通过。
