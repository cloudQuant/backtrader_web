# 迭代 197 文档并行基线整合记录

## 目的

`codex/iteration-197-data-platform` 与 `codex/iteration-197-design-docs` 从同一基线并行推进，均提供了同名的需求、设计和验收文档。两套文本都保留在本次 `dev` 整合中，避免以冲突解决的方式丢失任一工作区的设计结论。

## 当前文档位置

以下四份无后缀文档是当前实现候选的规范文档，反映数据中台代码、测试和已知验收边界：

- [README](README.md)
- [需求文档](REQUIREMENTS.md)
- [设计文档](DESIGN.md)
- [验收文档](ACCEPTANCE.md)

来自独立设计工作区的原始并行基线分别完整归档为：

- [README 设计基线](README_DESIGN_BASELINE_20260908.md)
- [需求设计基线](REQUIREMENTS_DESIGN_BASELINE_20260908.md)
- [设计设计基线](DESIGN_DESIGN_BASELINE_20260908.md)
- [验收设计基线](ACCEPTANCE_DESIGN_BASELINE_20260908.md)
- [实现候选说明](IMPLEMENTATION_CANDIDATE.md)

`SCOPE_MANIFEST.md` 和 `PRODUCT_EXPANSION_PLAN.md` 来自数据中台实现工作区，并继续作为当前候选的范围与产品规划材料。

## 状态边界

本记录只处理文档冲突，并不改变发布判断。真实 OpenBB 出站、跨数据库 PIT、操作系统级 runner 隔离和生产开关仍应以当前 [验收文档](ACCEPTANCE.md) 的 `NOT_RUN`、`BLOCKED` 与 `NO-GO` 证据为准。
