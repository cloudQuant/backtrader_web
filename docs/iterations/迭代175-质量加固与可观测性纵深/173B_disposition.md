# 173B disposition for iteration 175

> 评估日期：2026-05-28
> 评估人：@yunjinqi（owner，175 评审会主持人）
> 评估对象：迭代 173B 登记的 T2 / T7 / T10 三项残项（FinceptTerminal 相关产品化深化）

---

## 总览

| Item | 实现完成度 | 剩余工作清单（摘要） | 决议 | 判定依据 | 责任人 | 目标日期 |
|---|---|---|---|---|---|---|
| T2 - WS Gateway Migration | 70% | 1) `WS_GATEWAY_MIGRATION.md` 收口文档；2) 剩余高价值 WS 入口迁移；3) 兼容策略与回滚路径 | **顺延 176** | 余下工作量 ≥ 5 工作日，超出 175 容量；175 主线（mypy + a11y + i18n + OTel + e2e CI）已饱和 | @yunjinqi | 2026-08-15 |
| T7 - News Intelligence 产品化 | 65% | 1) RSS 拉取链路；2) 前端 richer filter；3) cluster 展开体验 | **顺延 176** | 涉及前端新视图与后端拉取调度，工作量 ≥ 8 工作日；与 175 范围正交 | @yunjinqi | 2026-09-01 |
| T10 - Quant Tool Registry 产品化 | 75% | 1) `quant_tools_runtime.py` 模块化拆分；2) 剩余 handler 接真实服务 | **顺延 176** | 涉及 runtime 拆分（与 174 主线 C 切片节奏冲突），工作量 ≥ 4 工作日；175 不重做切片 | @yunjinqi | 2026-08-30 |

---

## 三项决议详解

### T2 - WS Gateway Migration → 顺延 176

- **判定依据**：剩余 3 个未收口点中，「兼容策略与回滚路径」是 WS 网关层级的设计决策，需要 1 份独立 RFC + 灰度切换计划；175 主线没有 WS 网关层面的工作量预算，强行纳入会冲掉 OTel 全链路和 e2e CI 上线两个核心目标。
- **承接载体**：176 迭代主线之一；预计 W1 出 RFC，W2-W3 落地剩余迁移，W4 收口文档。
- **登记位置**：175 关闭后，本项写入 `docs/REFACTORING_BACKLOG.md` 「176 候选」段落。

### T7 - News Intelligence 产品化 → 顺延 176

- **判定依据**：RSS 拉取链路是后端调度任务的新增；前端 filter / cluster 展开是新视图开发；两类工作都超过 175 「不接受新功能 PRD」的硬约束。
- **承接载体**：176 候选；建议作为独立产品 epic 立项，可能需要独立产品 brief，超出常规迭代范围。
- **登记位置**：175 关闭后写入 `docs/REFACTORING_BACKLOG.md` 「176 候选」+ 标注「需独立产品 brief」。

### T10 - Quant Tool Registry 产品化 → 顺延 176

- **判定依据**：`quant_tools_runtime.py` 的进一步模块化拆分本质是「文件切片」类工作，应跟随 174 主线 C 的节奏延续；175 已显式标注「不重做 174 主线 C」，所以 T10 不应在 175 内做。
- **承接载体**：176 候选；可与 174 收尾后的剩余切片合并为「174.5 / 176 切片续作」小批次。
- **登记位置**：175 关闭后写入 `docs/REFACTORING_BACKLOG.md` 「176 候选」+ 引用 174 主线 C 的方法论。

---

## 175 子需求增补结论

由于 T2 / T7 / T10 三项**均决议为「顺延 176」**，**不**触发 §10.3 中「纳入 175」的转写流程；`requirements.md` 的 Requirements 列表保持 11 项不变。

---

## 一致性约束

本文档需与 `docs/iterations/README.md` 中 173B 行的以下三个字段始终保持一致：

- 决议类型（顺延 176）
- 责任人（@yunjinqi）
- 目标日期（T2: 2026-08-15；T7: 2026-09-01；T10: 2026-08-30）

任意一字段不一致 → `scripts/ci/check_173b_disposition_consistency.py` exit 1 → 175 验收失败。

---

## 关闭后处理（175 retrospective 时）

175 retrospective 文档归档至 `docs/iterations/迭代175-质量加固与可观测性纵深/RETROSPECTIVE.md` 时：

1. 把 T2 / T7 / T10 三项写入 `docs/REFACTORING_BACKLOG.md` 「176 候选」段落
2. `iterations/README.md` 中 173B 行的「活动条目」标记移除，仅留可追溯链接
3. `docs/iterations/迭代173B-171残项独立收口摘要.md` 末尾追加一段：「175 完成后转入 176 候选」与本 disposition 文档链接
