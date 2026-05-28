#!/usr/bin/env bash
# generate_lockfiles.sh - Generate pinned dependency lockfiles for reproducible builds.
#
# Usage:
#   ./scripts/generate_lockfiles.sh
#
# This script creates two lockfiles in the project root:
#   - requirements-dev.lock   (all dev + optional deps frozen)
#   - requirements-prod.lock  (production-only deps frozen)
#
# Run this script whenever pyproject.toml dependencies change.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/src/backend"

echo "=== Generating dependency lockfiles ==="
echo "Backend directory: $BACKEND_DIR"

# Create a temporary virtualenv for clean installs
TMPDIR_DEV=$(mktemp -d)
TMPDIR_PROD=$(mktemp -d)

cleanup() {
    rm -rf "$TMPDIR_DEV" "$TMPDIR_PROD"
}
trap cleanup EXIT

# --- Generate requirements-dev.lock ---
echo ""
echo "--- Generating requirements-dev.lock (dev + all optional deps) ---"
python -m venv "$TMPDIR_DEV/venv"
source "$TMPDIR_DEV/venv/bin/activate"
pip install --upgrade pip --quiet
pip install --no-cache-dir -e "$BACKEND_DIR[dev,backtrader,data,redis]" --quiet
pip freeze --exclude-editable > "$PROJECT_ROOT/requirements-dev.lock"
deactivate
echo "✓ requirements-dev.lock generated ($(wc -l < "$PROJECT_ROOT/requirements-dev.lock") packages)"

# --- Generate requirements-prod.lock ---
echo ""
echo "--- Generating requirements-prod.lock (production deps only) ---"
python -m venv "$TMPDIR_PROD/venv"
source "$TMPDIR_PROD/venv/bin/activate"
pip install --upgrade pip --quiet
pip install --no-cache-dir -e "$BACKEND_DIR[prod]" --quiet
pip freeze --exclude-editable > "$PROJECT_ROOT/requirements-prod.lock"
deactivate
echo "✓ requirements-prod.lock generated ($(wc -l < "$PROJECT_ROOT/requirements-prod.lock") packages)"

echo ""
echo "=== Done. Lockfiles written to project root ==="
echo "  - $PROJECT_ROOT/requirements-dev.lock"
echo "  - $PROJECT_ROOT/requirements-prod.lock"
echo ""
echo "Commit these files to ensure reproducible builds."
