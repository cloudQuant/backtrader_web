#!/usr/bin/env bash
#
# purge_secret_history.sh — Iteration 178 §A (P0 security follow-up)
#
# Permanently removes runtime files that leaked REAL exchange/database
# credentials from the ENTIRE git history (not just the working tree).
#
# Background
# ----------
# Iteration 177 §D `git rm --cached`-ed these files so they no longer appear in
# the latest commit, and added a .gitignore + gitleaks gate so no NEW secret can
# land. But the historical commits still contain the plaintext credentials:
#
#     git show <old-sha>:src/backend/data/manual_gateways.json
#
# still prints live Binance/OKX/CTP/MT5/IB keys and MySQL root passwords. This
# script rewrites history with `git filter-repo` to erase those blobs entirely.
#
# ⚠️  THIS IS DESTRUCTIVE AND REWRITES HISTORY.
#     - Every commit SHA after the earliest affected commit changes.
#     - After running, you MUST force-push and EVERY collaborator must re-clone
#       (or hard-reset), or they will reintroduce the secrets on their next push.
#     - Do NOT run this on a whim. Coordinate a window with all collaborators.
#
# ⚠️  ROTATION FIRST.
#     Purging history does NOT make leaked keys safe — anyone who already cloned
#     has them. You MUST rotate every credential at the provider FIRST. This
#     script refuses to proceed unless you confirm rotation is done.
#     See: docs/iterations/迭代178-安全纵深收口与质量债治理/ROTATION_RUNBOOK.md
#
# Usage
# -----
#   scripts/ops/purge_secret_history.sh --dry-run     # safe: list paths only
#   scripts/ops/purge_secret_history.sh --execute     # destructive rewrite
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Paths to scrub from all of history. Keep in sync with .gitignore (178 §A /
# 177 §5.3) and CLOSURE.md. Directory entries scrub everything beneath them.
# ---------------------------------------------------------------------------
PATHS_TO_PURGE=(
  "src/backend/data/manual_gateways.json"
  "src/backend/data/manual_gateways"
  "src/backend/data/sync_config.json"
  "src/backend/data/sync_history.json"
  "src/backend/data/auto_trading_config.json"
  "src/backend/data/live_trading_instances.json"
  "src/backend/data/quote_custom_symbols.json"
)

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
  echo "ERROR: not inside a git repository." >&2
  exit 2
fi
cd "${REPO_ROOT}"

MODE="${1:-}"
if [[ "${MODE}" != "--dry-run" && "${MODE}" != "--execute" ]]; then
  echo "Usage: $0 --dry-run | --execute" >&2
  exit 2
fi

echo "=== Secret-history purge (mode: ${MODE}) ==="
echo "Repo: ${REPO_ROOT}"
echo

echo "--- Files targeted for history removal (with historical commit counts) ---"
for p in "${PATHS_TO_PURGE[@]}"; do
  count="$(git log --all --oneline -- "${p}" 2>/dev/null | wc -l | tr -d ' ')"
  printf '  %4s commit(s)  %s\n' "${count}" "${p}"
done
echo

if [[ "${MODE}" == "--dry-run" ]]; then
  echo "Dry run only — no history was modified."
  echo "Re-run with --execute (after rotation + collaborator coordination) to apply."
  exit 0
fi

# ----- Destructive path from here on -----

if ! command -v git-filter-repo >/dev/null 2>&1 && ! git filter-repo --help >/dev/null 2>&1; then
  cat >&2 <<'EOF'
ERROR: git-filter-repo is not installed.
Install it first, e.g.:
    pipx install git-filter-repo
    # or: pip install git-filter-repo
    # or: brew install git-filter-repo
Docs: https://github.com/newren/git-filter-repo
EOF
  exit 3
fi

echo "⚠️  You are about to REWRITE GIT HISTORY. This cannot be undone."
echo

read -r -p "Have you ALREADY rotated every leaked credential at the provider? [type 'rotated' to continue]: " ROT
if [[ "${ROT}" != "rotated" ]]; then
  echo "Aborting: rotate credentials first (see ROTATION_RUNBOOK.md)." >&2
  exit 4
fi

read -r -p "Have you coordinated a re-clone window with ALL collaborators? [type 'coordinated' to continue]: " COORD
if [[ "${COORD}" != "coordinated" ]]; then
  echo "Aborting: coordinate with collaborators first (force-push breaks their clones)." >&2
  exit 4
fi

read -r -p "Final confirm — rewrite history now? [type 'PURGE' to proceed]: " FINAL
if [[ "${FINAL}" != "PURGE" ]]; then
  echo "Aborting: not confirmed." >&2
  exit 4
fi

# Build the --path / --path-glob arguments. filter-repo with --invert-paths
# drops exactly the listed paths from every commit.
FILTER_ARGS=()
for p in "${PATHS_TO_PURGE[@]}"; do
  FILTER_ARGS+=(--path "${p}")
done

echo
echo ">>> Running git filter-repo (invert-paths, force)..."
git filter-repo --invert-paths "${FILTER_ARGS[@]}" --force

echo
echo "=== History rewrite complete. Verify, then force-push. ==="
cat <<'EOF'

NEXT STEPS (manual, by the repo owner):

  1. Verify the secrets are gone from history:
       git log --all --oneline -- src/backend/data/manual_gateways.json   # expect empty
       gitleaks detect --config .gitleaks.toml --no-banner --redact       # expect 0 findings

  2. filter-repo removes the 'origin' remote as a safety measure. Re-add it:
       git remote add origin <your-remote-url>

  3. Force-push every ref (coordinate the window first!):
       git push origin --force --all
       git push origin --force --tags

  4. Tell ALL collaborators to re-clone (or `git fetch && git reset --hard origin/<branch>`).
     Their old clones still contain the secrets and will reintroduce them if pushed.

  5. Flip the CI secret-scan full-history step from advisory to blocking:
     set SECRET_SCAN_HISTORY_BLOCKING=true (repo/org variable) — see
     .github/workflows/ci.yml and docs/iterations/迭代178-.../ROTATION_RUNBOOK.md.
EOF
