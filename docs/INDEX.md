# Backtrader Web Documentation

## Documentation Sites

- **English**: https://backtrader-web.github.io/backtrader_web/en/
- **中文**: https://backtrader-web.github.io/backtrader_web/zh/

## New Documentation (MkDocs)

The new bilingual documentation is built with MkDocs and Material theme:

```
docs/
├── mkdocs.yml              # MkDocs configuration
├── docs/
│   ├── en/                # English documentation
│   │   ├── index.md
│   │   ├── getting-started/
│   │   ├── features/
│   │   ├── development/
│   │   ├── deployment/
│   │   └── reference/
│   └── zh/                # Chinese documentation
│       ├── index.md
│       ├── getting-started/
│       ├── features/
│       ├── development/
│       ├── deployment/
│       └── reference/
```

### Building Locally

```bash
# Install dependencies
pip install mkdocs mkdocs-material mkdocs-i18n

# Serve locally
mkdocs serve -f docs/mkdocs.yml

# Build for production
mkdocs build -f docs/mkdocs.yml
```

### Deployment

- **GitHub Pages**: Automatically deployed via `.github/workflows/docs.yml`
- **ReadTheDocs**: Configured via `.readthedocs.yml`

## Legacy Documentation

The original documentation is preserved in this directory:

- `*.md` - Core documentation files
- `iterations/` - Development iteration history
- `contracts/` - Project contracts and policies

---

## 项目文档

### 新文档 (MkDocs)

双语文档使用 MkDocs 和 Material 主题构建：

| 语言 | 链接 |
|------|------|
| English | /en/ |
| 中文 | /zh/ |

### 本地构建

```bash
pip install mkdocs mkdocs-material mkdocs-i18n
mkdocs serve -f docs/mkdocs.yml
```

### 部署

- **GitHub Pages**: 通过 `.github/workflows/docs.yml` 自动部署
- **ReadTheDocs**: 通过 `.readthedocs.yml` 配置
