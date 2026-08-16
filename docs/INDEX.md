# AI for Investor 文档导航

本目录按“发布文档、当前工程文档、历史归档”组织。不要从历史方案或旧截图推断当前产品行为；功能、接口和命令应优先以发布站点、运行中的 OpenAPI 和测试为准。

## 发布文档（MkDocs）

发布站点源文件位于 `docs/docs/{zh,en}/`，由 `docs/mkdocs.yml` 构建：

| 内容 | 中文 | English |
| --- | --- | --- |
| 首页与工作流 | [中文首页](docs/zh/index.md) | [English home](docs/en/index.md) |
| 安装与首次研究 | [快速开始](docs/zh/getting-started/index.md) | [Getting started](docs/en/getting-started/index.md) |
| 产品功能 | [功能介绍](docs/zh/features/index.md) | [Features](docs/en/features/index.md) |
| 开发与 API | [开发指南](docs/zh/development/index.md) | [Development](docs/en/development/index.md) |
| 部署与配置 | [部署运维](docs/zh/deployment/index.md) | [Deployment](docs/en/deployment/index.md) |

本地预览或严格构建：

```bash
python -m pip install -r docs/requirements.txt
python -m mkdocs serve -f docs/mkdocs.yml
python -m mkdocs build -f docs/mkdocs.yml --strict
```

## 当前工程文档

| 目录/文件 | 用途 |
| --- | --- |
| `project-introduction/` | 当前项目介绍、产品定位与投研流程背景；以 `ai-for-investor-project-introduction.md` 为基线。 |
| `guides/` | 面向开发者和运营者的具体操作，如策略开发、AI Copilot、数据连接、组合账本。 |
| `how-to/` | 开发、测试、Airflow 和数据库迁移等实施手册。 |
| `operations/` | 部署、初始化、日志、同步安全、CI/CD 与故障排查。 |
| `reference/` | API、数据库、性能、代码规范、安全和设计系统等稳定参考。 |
| `adr/` | 架构决策记录；保留决策历史，不作为当前接口清单。 |
| `contracts/`、`security/` | 工程契约、CI 门禁与安全治理资料。 |
| `strategies/` | 策略参考和研究资料，不属于产品帮助站导航。 |

## 迭代与归档

| 位置 | 规则 |
| --- | --- |
| `iterations/` | 当前及可追溯的迭代记录。`iterations/README.md` 标明仍在使用的迭代；其 `archived/` 子目录保存早期历史。 |
| `reports/archive/` | 已完成的评审、快照和专项报告。 |
| `archive/plans/2026-q2/` | 已完成、仅供追溯的 2026 年第二季度方案。 |
| `archive/project-introductions/` | 被当前项目介绍替代的旧项目介绍。 |

归档文件保留历史事实，但不再维护为当前操作说明。若要变更当前能力，请先更新 `docs/docs/` 发布页面及对应的工程手册；新增过时计划或报告应直接放入相应 archive 目录。

## 发布与外部入口

- 中文站点（GitHub Pages）：<https://cloudquant.github.io/backtrader_web/>
- English site（GitHub Pages）：<https://cloudquant.github.io/backtrader_web/en/>
- 运行中 API：`http://localhost:8000/docs`
- 部署流水线：`.github/workflows/docs.yml`（master 上 `docs/**` 变更自动重建）
