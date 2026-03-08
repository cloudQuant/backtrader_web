#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0
WARNINGS=0

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

print_ok() {
  echo "✅ $1"
}

print_warn() {
  echo "⚠️  $1"
  WARNINGS=$((WARNINGS + 1))
}

print_error() {
  echo "❌ $1"
  ERRORS=$((ERRORS + 1))
}

print_section() {
  echo ""
  echo "=========================================="
  echo "  $1"
  echo "=========================================="
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/verify-dev-env.sh --preinstall
  ./scripts/verify-dev-env.sh --postinstall
  ./scripts/verify-dev-env.sh --all

Modes:
  --preinstall   Check system-level prerequisites only
  --postinstall  Check installed project dependencies only
  --all          Run preinstall checks first, then postinstall checks
EOF
}

check_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    print_error "Missing required command: $1"
    return 1
  fi
  return 0
}

check_python_version() {
  local python_info python_major python_minor

  python_info="$(
    python - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY
  )"
  python_major="${python_info%%.*}"
  python_minor="$(echo "$python_info" | cut -d. -f2)"

  if [ "$python_major" -lt 3 ] || {
    [ "$python_major" -eq 3 ] && [ "$python_minor" -lt 10 ];
  }; then
    print_error "Python $python_info detected. Python 3.10+ is required."
    return
  fi

  print_ok "Python $python_info is compatible with the backend baseline"
  if [ "$python_major" -ne 3 ] || [ "$python_minor" -ne 10 ]; then
    print_warn "Python 3.10.x is the CI baseline. Current version is $python_info."
  fi
}

run_preinstall_checks() {
  print_section "Preinstall Checks"

  check_command node || true
  check_command npm || true
  check_command python || true

  if command -v node >/dev/null 2>&1; then
    local node_version node_major
    node_version="$(node -p "process.versions.node")"
    node_major="${node_version%%.*}"
    if [ "$node_major" = "20" ]; then
      print_ok "Node.js $node_version matches the required 20.x baseline"
    else
      print_error "Node.js $node_version detected. Use Node.js 20.x for this project."
      echo "   Suggested fix: nvm install 20 && nvm use 20"
    fi
  fi

  if command -v python >/dev/null 2>&1; then
    check_python_version
  fi

  if [ -f "$ROOT_DIR/.nvmrc" ]; then
    print_ok "Found Node version pin: $(cat "$ROOT_DIR/.nvmrc")"
  else
    print_warn "Missing .nvmrc in project root"
  fi

  if [ -f "$ROOT_DIR/src/backend/pyproject.toml" ]; then
    print_ok "Backend pyproject.toml found"
  else
    print_error "Backend pyproject.toml is missing"
  fi

  if [ -f "$ROOT_DIR/src/frontend/package.json" ]; then
    print_ok "Frontend package.json found"
  else
    print_error "Frontend package.json is missing"
  fi
}

run_postinstall_checks() {
  print_section "Postinstall Checks"

  check_command python || true

  if ! command -v python >/dev/null 2>&1; then
    return
  fi

  local backtrader_check
  backtrader_check="$(
    python - <<'PY'
try:
    import backtrader as bt
    path = getattr(bt, "__file__", None) or "<namespace-package>"
    has_analyzer = hasattr(bt, "Analyzer")
    print(f"IMPORT_OK|{path}|{has_analyzer}")
except Exception as exc:
    print(f"IMPORT_ERROR|{type(exc).__name__}: {exc}")
PY
  )"

  if [[ "$backtrader_check" == IMPORT_OK* ]]; then
    local backtrader_path backtrader_analyzer
    backtrader_path="$(echo "$backtrader_check" | cut -d'|' -f2)"
    backtrader_analyzer="$(echo "$backtrader_check" | cut -d'|' -f3)"
    if [ "$backtrader_analyzer" = "True" ]; then
      print_ok "backtrader import is healthy ($backtrader_path)"
      print_ok "backtrader.Analyzer is available"
    else
      print_error "backtrader imported from $backtrader_path but is missing Analyzer"
      echo "   Reinstall with: cd src/backend && pip install -e \".[dev,backtrader]\""
    fi
  else
    print_error "backtrader import failed: ${backtrader_check#IMPORT_ERROR|}"
    echo "   Install backend deps first: cd src/backend && pip install -e \".[dev,backtrader]\""
  fi

  if python -c "import fastapi" >/dev/null 2>&1; then
    print_ok "FastAPI import succeeded"
  else
    print_error "FastAPI import failed"
  fi

  if python -c "import sqlalchemy" >/dev/null 2>&1; then
    print_ok "SQLAlchemy import succeeded"
  else
    print_error "SQLAlchemy import failed"
  fi
}

finish() {
  local label="$1"

  echo ""
  echo "-----------------------------------"
  echo "  $label Summary"
  echo "-----------------------------------"

  if [ "$ERRORS" -gt 0 ]; then
    echo -e "${RED}✗${NC} Found $ERRORS error(s) and $WARNINGS warning(s)."
    exit 1
  fi

  echo -e "${GREEN}✓${NC} Completed with $WARNINGS warning(s)."
  exit 0
}

MODE="${1:---preinstall}"

case "$MODE" in
  --preinstall)
    run_preinstall_checks
    finish "Preinstall"
    ;;
  --postinstall)
    run_postinstall_checks
    finish "Postinstall"
    ;;
  --all)
    run_preinstall_checks
    if [ "$ERRORS" -gt 0 ]; then
      finish "Combined"
    fi
    run_postinstall_checks
    finish "Combined"
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
