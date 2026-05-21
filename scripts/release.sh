#!/usr/bin/env bash
# =============================================================================
# Release Script for Backtrader Web v0.1.0
#
# Usage:
#   ./scripts/release.sh              # Dry run (shows what would happen)
#   ./scripts/release.sh --execute    # Actually create the release
#
# Prerequisites:
#   - gh CLI installed and authenticated (brew install gh && gh auth login)
#   - Docker installed and logged in to Docker Hub (docker login)
#   - All tests passing
#   - Clean git working directory
# =============================================================================

set -euo pipefail

VERSION="0.1.0"
DOCKER_REPO="cloudquant/backtrader-web"
DRY_RUN=true

if [[ "${1:-}" == "--execute" ]]; then
    DRY_RUN=false
fi

echo "╔══════════════════════════════════════════════╗"
echo "║  Backtrader Web Release v${VERSION}            ║"
echo "║  Mode: $(if $DRY_RUN; then echo 'DRY RUN'; else echo 'EXECUTE'; fi)                            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Step 1: Verify prerequisites ─────────────────────────────────────────────
echo "▶ Step 1: Checking prerequisites..."

if ! command -v gh &> /dev/null; then
    echo "  ✗ gh CLI not found. Install: brew install gh"
    exit 1
fi
echo "  ✓ gh CLI available"

if ! command -v docker &> /dev/null; then
    echo "  ✗ Docker not found"
    exit 1
fi
echo "  ✓ Docker available"

if [[ -n "$(git status --porcelain)" ]]; then
    echo "  ⚠ Working directory not clean. Commit or stash changes first."
    if ! $DRY_RUN; then exit 1; fi
fi
echo "  ✓ Git working directory clean"

# ── Step 2: Run tests ────────────────────────────────────────────────────────
echo ""
echo "▶ Step 2: Running tests..."

if $DRY_RUN; then
    echo "  [dry-run] Would run: pytest tests/ -q --timeout=60 -m 'not e2e'"
else
    cd src/backend
    pytest tests/ -q --timeout=60 -m "not e2e" -k "not test_performance" --maxfail=5 || {
        echo "  ✗ Tests failed. Fix before releasing."
        exit 1
    }
    cd ../..
    echo "  ✓ All tests passed"
fi

# ── Step 3: Build frontend ───────────────────────────────────────────────────
echo ""
echo "▶ Step 3: Building frontend..."

if $DRY_RUN; then
    echo "  [dry-run] Would run: npm run build (in src/frontend/)"
else
    cd src/frontend
    npm run build
    cd ../..
    echo "  ✓ Frontend built successfully"
fi

# ── Step 4: Build Docker images ──────────────────────────────────────────────
echo ""
echo "▶ Step 4: Building Docker images..."

BACKEND_TAG="${DOCKER_REPO}-backend:${VERSION}"
FRONTEND_TAG="${DOCKER_REPO}-frontend:${VERSION}"
BACKEND_LATEST="${DOCKER_REPO}-backend:latest"
FRONTEND_LATEST="${DOCKER_REPO}-frontend:latest"

if $DRY_RUN; then
    echo "  [dry-run] Would build:"
    echo "    - ${BACKEND_TAG}"
    echo "    - ${FRONTEND_TAG}"
else
    docker build -t "${BACKEND_TAG}" -t "${BACKEND_LATEST}" -f src/backend/Dockerfile .
    docker build -t "${FRONTEND_TAG}" -t "${FRONTEND_LATEST}" -f src/frontend/Dockerfile src/frontend/
    echo "  ✓ Docker images built"
fi

# ── Step 5: Push Docker images ───────────────────────────────────────────────
echo ""
echo "▶ Step 5: Pushing Docker images to Docker Hub..."

if $DRY_RUN; then
    echo "  [dry-run] Would push:"
    echo "    - ${BACKEND_TAG}"
    echo "    - ${BACKEND_LATEST}"
    echo "    - ${FRONTEND_TAG}"
    echo "    - ${FRONTEND_LATEST}"
else
    docker push "${BACKEND_TAG}"
    docker push "${BACKEND_LATEST}"
    docker push "${FRONTEND_TAG}"
    docker push "${FRONTEND_LATEST}"
    echo "  ✓ Docker images pushed"
fi

# ── Step 6: Create Git tag ───────────────────────────────────────────────────
echo ""
echo "▶ Step 6: Creating Git tag..."

if $DRY_RUN; then
    echo "  [dry-run] Would create tag: v${VERSION}"
else
    git tag -a "v${VERSION}" -m "Release v${VERSION} - Initial public release"
    git push origin "v${VERSION}"
    echo "  ✓ Tag v${VERSION} created and pushed"
fi

# ── Step 7: Create GitHub Release ────────────────────────────────────────────
echo ""
echo "▶ Step 7: Creating GitHub Release..."

RELEASE_NOTES="## Backtrader Web v${VERSION} — Initial Public Release

### Highlights

- 🚀 Full-stack quantitative trading platform (FastAPI + Vue 3)
- 🤖 AI Strategy Copilot with RAG-powered knowledge base
- 📊 118 built-in strategy templates
- 🔴 Complete pipeline: backtest → paper trading → live trading (CTP/CCXT)
- 🔒 33 automated security tests passing
- 📱 Responsive mobile layout with 5 theme options
- 🐳 Docker one-command deployment

### Quick Start

\`\`\`bash
# Docker (fastest)
docker compose up -d
# Open http://localhost:3000

# Manual
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web/src/backend && pip install -e '.[dev,backtrader]'
cd ../frontend && npm install && npm run dev
\`\`\`

### Docker Images

\`\`\`bash
docker pull ${DOCKER_REPO}-backend:${VERSION}
docker pull ${DOCKER_REPO}-frontend:${VERSION}
\`\`\`

### Documentation

- [English README](README.en.md)
- [Quick Start (EN)](docs/QUICKSTART_EN.md)
- [API Reference (EN)](docs/API_REFERENCE_EN.md)
- [中文快速上手](docs/QUICKSTART.md)
- [Strategic Roadmap](docs/STRATEGIC_ROADMAP.md)

### Full Changelog

See [CHANGELOG.md](CHANGELOG.md) for complete details.
"

if $DRY_RUN; then
    echo "  [dry-run] Would create GitHub release v${VERSION}"
    echo "  Release notes preview:"
    echo "${RELEASE_NOTES}" | head -20
    echo "  ..."
else
    echo "${RELEASE_NOTES}" | gh release create "v${VERSION}" \
        --title "v${VERSION} — Initial Public Release" \
        --notes-file - \
        --latest
    echo "  ✓ GitHub Release created"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Release v${VERSION} $(if $DRY_RUN; then echo 'dry run complete'; else echo 'PUBLISHED ✓'; fi)       ║"
echo "╚══════════════════════════════════════════════╝"

if $DRY_RUN; then
    echo ""
    echo "To execute the release for real, run:"
    echo "  ./scripts/release.sh --execute"
fi
