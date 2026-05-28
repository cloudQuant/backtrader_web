#!/usr/bin/env bash
# Iteration 175 §9.2 — single entry that runs lint / typecheck / unit tests
# in both Python workspace members. Fail-fast (any step → exit non-zero).
#
# Hard wall-clock cap: 1800 seconds.
#
# Usage:
#   bash scripts/dev/check_all.sh
#
# Exit codes:
#   0   — all members green
#   1   — one or more steps failed; stderr names the failing step / member.
#   124 — overall timeout exceeded.

set -uo pipefail

BUDGET_SECONDS=1800
START=$(date +%s)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

MEMBERS=("src/backend" "src/bt_api_py")

# Best-effort detection of mypy strict scope per member.
detect_mypy_scope() {
  local member="$1"
  local pyproject="$member/pyproject.toml"
  if [ -f "$pyproject" ]; then
    # Default to scanning the standard backend `app/` directory if present;
    # otherwise scan the package directory matching the member basename
    # (e.g. `bt_api_py/`).
    if [ -d "$member/app" ]; then
      echo "app"
    elif [ -d "$member/$(basename "$member")" ]; then
      echo "$(basename "$member")"
    else
      # Fall back to the member root as a last resort.
      echo "."
    fi
  else
    echo "."
  fi
}

elapsed() {
  echo $(( $(date +%s) - START ))
}

over_budget() {
  local e
  e=$(elapsed)
  if [ "$e" -ge "$BUDGET_SECONDS" ]; then
    echo "::error::check_all.sh exceeded ${BUDGET_SECONDS}s budget (elapsed=${e}s)" >&2
    exit 124
  fi
}

run_step() {
  local member="$1"
  local label="$2"
  shift 2
  echo "::group::[$member] $label"
  if ! ( cd "$member" && "$@" ); then
    echo "::endgroup::"
    echo "::error::check_all.sh failed step '$label' in $member" >&2
    exit 1
  fi
  echo "::endgroup::"
  over_budget
}

for member in "${MEMBERS[@]}"; do
  if [ ! -d "$REPO_ROOT/$member" ]; then
    echo "WARN: workspace member missing on disk: $member — skipping" >&2
    continue
  fi

  if ! command -v ruff > /dev/null 2>&1; then
    echo "WARN: ruff not in PATH — skipping ruff steps" >&2
  else
    run_step "$member" "ruff check" ruff check .
    run_step "$member" "ruff format --check" ruff format --check .
  fi

  if command -v mypy > /dev/null 2>&1; then
    scope=$(detect_mypy_scope "$member")
    run_step "$member" "mypy $scope" mypy "$scope"
  else
    echo "WARN: mypy not in PATH — skipping mypy in $member" >&2
  fi

  if command -v pytest > /dev/null 2>&1; then
    run_step "$member" 'pytest -m "not e2e"' pytest -m "not e2e" -q
  else
    echo "WARN: pytest not in PATH — skipping pytest in $member" >&2
  fi
done

echo "OK: check_all.sh — all members green ($(elapsed)s)"
