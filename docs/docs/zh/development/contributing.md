# 贡献指南

如何为 AI for Investor 贡献代码与文档。本地开发、测试与代码规范的完整说明见根目录
[CONTRIBUTING.md](https://github.com/cloudQuant/backtrader_web/blob/master/CONTRIBUTING.md)。

## 分支模型（iteration 195）

| 分支 | 定位 | 接受的 PR |
| --- | --- | --- |
| `dev` | 日常集成分支 | 全部常规 PR（`feature/*`、`fix/*`、`docs/*` 等） |
| `master` | 发布主干 | 仅 `release/vX.Y.Z` 发布晋升 PR 与 `hotfix/master-*` 紧急修复 PR |

**常规变更必须以 `dev` 为目标分支。** 其他来源分支指向 `master` 的 PR 会被 PR Governance
门禁拒绝。

## Fork 与克隆

1. 在 GitHub 上 Fork 本仓库。
2. 克隆你自己的 fork（把 `YOUR_USERNAME` 替换成你的用户名）：

   ```bash
   git clone https://github.com/YOUR_USERNAME/backtrader_web.git
   cd backtrader_web
   ```

3. 添加 upstream 远端，并基于 `dev` 创建分支：

   ```bash
   git remote add upstream https://github.com/cloudQuant/backtrader_web.git
   git fetch upstream
   git checkout -b feature/your-feature upstream/dev
   ```

## 发起 Pull Request

1. 推送分支并创建**目标为 `dev`** 的 PR。
2. 按 `.github/PULL_REQUEST_TEMPLATE.md` 填写：
   - `## Governance declaration`：目标分支理由、风险等级（按变更路径自动分类，label 不能下调）、测试证据；
   - `master` hotfix PR 需额外填写 dev 前移计划；release promotion PR 需链接发布清单；
   - 改动国际化文案时如实填写 `i18n 变更清单`（CI 校验）。
3. 等待维护者评审——自动化检查通过是必要条件而非充分条件；合并需要人工批准。

## 提交 Issue

- Bug：使用 Bug Report 表单，附最小复现步骤与环境信息。
- 功能建议：使用 Feature Request 表单。
- 使用问题：请在 [Discussions](https://github.com/cloudQuant/backtrader_web/discussions)
  提问，不要新建 question issue。

## 行为约定

评审对事不对人；保持建设性与尊重。提交贡献即表示同意以 MIT License 授权。
