# AI for Trader Documentation

## Documentation Sites

- **English**: https://cloudquant.github.io/ai-for-trader/en/
- **中文**: https://cloudquant.github.io/ai-for-trader/zh/

## Internal Docs Layout

The published bilingual site is built from `docs/docs/{en,zh}/` (see `mkdocs.yml`).
The other folders below are internal references for contributors.

```
docs/
├── mkdocs.yml              # MkDocs configuration
├── INDEX.md                # ← this file
│
├── docs/                   # Published documentation (en/zh)
│   ├── en/{getting-started,features,development,deployment,reference}/
│   └── zh/{getting-started,features,development,deployment,reference}/
│
├── guides/                 # User-facing how-to guides (internal)
│   ├── INSTALLATION.md
│   ├── QUICKSTART.md
│   ├── USER_GUIDE.md
│   ├── BACKTEST_GUIDE.md
│   ├── STRATEGY_DEVELOPMENT.md
│   ├── LIVE_TRADING.md
│   ├── PARAMETER_OPTIMIZATION.md
│   ├── AI_STRATEGY_COPILOT.md
│   ├── API_GUIDE.md
│   ├── KEYBOARD_SHORTCUTS.md
│   ├── DARK_THEME_GUIDE.md
│   └── TBQUANT_SCREENSHOTS.md
│
├── operations/             # Deployment, ops, troubleshooting
│   ├── DEPLOYMENT.md
│   ├── OPERATIONS.md
│   ├── CI_CD.md
│   ├── CI_STATUS_BADGES.md
│   ├── LOGGING.md
│   ├── DATABASE_INIT.md
│   ├── TROUBLESHOOTING.md
│   └── BACKTRADER_IMPORT_TROUBLESHOOTING.md
│
├── reports/archive/        # Dated reviews, retros, sprint snapshots
│
├── iterations/             # Sprint / iteration design notes
├── contracts/              # Project contracts and policies
├── strategies/             # Strategy reference docs
└── tbquant_screenshots/    # Screenshot reference assets
```

### Top-level reference docs (kept at `docs/`)

| File | Purpose |
|------|---------|
| `ARCHITECTURE.md` | System architecture overview |
| `API_OVERVIEW.md` | REST API surface summary |
| `DATABASE.md` | Database schema reference |
| `SECURITY.md` | Security model |
| `CODING_STANDARDS.md` | Coding standards |
| `TESTING.md` | Testing strategy |
| `DEVELOPMENT.md` | Developer setup |
| `DESIGN_SYSTEM.md` | Frontend design token and theming contract |
| `AGILE_DEVELOPMENT.md` | Process notes |
| `CONTRIBUTING.md` | Contribution workflow |
| `CHANGELOG.md` | Release log |
| `REFACTORING_BACKLOG.md` | Open refactoring items |
| `REQUEST_SCOPED_SESSION.md` | Request lifecycle reference |
| `PERFORMANCE.md` | Current performance notes |
| `TECHNICAL_DOCS.md` | Misc technical reference |
| `STRATEGIC_ROADMAP.md` | Long-term strategic plan and product roadmap |
| `RELEASE_PLAN_V2.md` | v2.0.0 release plan and migration guide |
| `project-context.md` | LLM-optimized project context for AI agents |
| `CENTENNIAL_VISION.md` | 百年老店愿景：长期发展纲要与治理模型 |
| `MARKET_RESEARCH.md` | 量化交易平台市场研究与竞品深度分析 |
| `TECHNICAL_RESEARCH.md` | 技术研究：架构演进与关键技术方向 |
| `PRODUCT_BRIEF.md` | 产品简报：定义、现状与路线图摘要 |
| `INNOVATION_STRATEGY.md` | 创新战略：差异化与颠覆路径 |
| `IMPROVEMENT_ROADMAP.md` | 改进优化发展方向：可执行行动计划 |
| `adr/` | Architecture Decision Records (ADRs) |

## Building Locally

```bash
pip install mkdocs mkdocs-material mkdocs-i18n
mkdocs serve -f docs/mkdocs.yml
```

## Deployment

- **GitHub Pages**: Automatically deployed via `.github/workflows/docs.yml`
- **ReadTheDocs**: Configured via `.readthedocs.yml`

---

## 项目文档

| 语言 | 链接 |
|------|------|
| English | /en/ |
| 中文 | /zh/ |
