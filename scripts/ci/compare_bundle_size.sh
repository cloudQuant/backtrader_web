#!/usr/bin/env bash
# CI script: compare current entry chunk gzip size against the target branch.
#
# Iteration 175 §7.6 — > 10% growth blocks the PR. base missing → emit a
# notice and skip. The blocking can be bypassed by either:
#
#   - PR label `BUNDLE_SIZE_GROWTH_OVERRIDE`
#   - PR description containing `<!-- bundle-size-override: <reason> -->`
#
# An override additionally requires CODEOWNERS approval (advisory check —
# the actual approval enforcement happens in branch protection rules).
#
# Usage:
#   ./scripts/ci/compare_bundle_size.sh <current_dist_dir> <base_entry_gzip_bytes>
#
# Exit codes:
#   0 - within budget OR base missing OR override active
#   1 - growth > 10% AND no valid override

set -euo pipefail

CURRENT_DIST="${1:-src/frontend/dist}"
BASE_GZIP_BYTES="${2:-}"

GROWTH_THRESHOLD_PCT=10  # > 10% growth blocks
GROWTH_THRESHOLD_NUM=10
GROWTH_THRESHOLD_DEN=100

filesize() {
  local p="$1"
  stat -f%z "$p" 2>/dev/null || stat --format=%s "$p" 2>/dev/null
}

ENTRY_FILE=$(find "$CURRENT_DIST/assets" -maxdepth 1 -name "index-*.js" -type f 2>/dev/null | head -1)
if [ -z "$ENTRY_FILE" ]; then
  echo "ERROR: entry chunk dist/assets/index-*.js not found"
  exit 1
fi
CURRENT_BYTES=$(gzip -c -9 "$ENTRY_FILE" | wc -c | tr -d ' ')

if [ -z "$BASE_GZIP_BYTES" ] || [ "$BASE_GZIP_BYTES" -le 0 ] 2>/dev/null; then
  echo "::notice::bundle-size base missing, ratchet skipped"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
      echo "### Bundle Size Ratchet"
      echo ""
      echo "_skipped — base entry chunk gzip size unavailable (target branch artifact missing)_"
    } >> "$GITHUB_STEP_SUMMARY"
  fi
  exit 0
fi

# Compute (current - base) * 100 / base using integer math, then compare to 10.
DELTA=$((CURRENT_BYTES - BASE_GZIP_BYTES))
# Guard against div-by-zero (already excluded above)
if [ "$BASE_GZIP_BYTES" -eq 0 ]; then
  echo "::notice::bundle-size base = 0, ratchet skipped"
  exit 0
fi
GROWTH_NUM=$((DELTA * 100))
GROWTH_INT=$((GROWTH_NUM / BASE_GZIP_BYTES))

echo "Current entry gzip: $CURRENT_BYTES bytes"
echo "Base entry gzip:    $BASE_GZIP_BYTES bytes"
echo "Delta:              $DELTA bytes (~ ${GROWTH_INT}%)"

if [ "$GROWTH_INT" -le "$GROWTH_THRESHOLD_NUM" ]; then
  echo "::notice::Bundle size growth ${GROWTH_INT}% within ratchet (<= ${GROWTH_THRESHOLD_NUM}%)"
  exit 0
fi

# Growth exceeds threshold — check overrides.
OVERRIDE_REASON=""
if [ -n "${PR_LABELS:-}" ] && echo "$PR_LABELS" | grep -q "BUNDLE_SIZE_GROWTH_OVERRIDE"; then
  OVERRIDE_REASON="label:BUNDLE_SIZE_GROWTH_OVERRIDE"
fi
if [ -n "${PR_BODY:-}" ]; then
  REASON_FROM_BODY=$(printf '%s' "$PR_BODY" | grep -oE '<!--[[:space:]]*bundle-size-override:[[:space:]]*[^>]+-->' | head -1 || true)
  if [ -n "$REASON_FROM_BODY" ]; then
    OVERRIDE_REASON="${OVERRIDE_REASON:+$OVERRIDE_REASON; }body:$REASON_FROM_BODY"
  fi
fi

if [ -n "$OVERRIDE_REASON" ]; then
  echo "::warning::bundle-size growth ${GROWTH_INT}% exceeds ${GROWTH_THRESHOLD_NUM}% threshold but override active: $OVERRIDE_REASON"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
      echo "### Bundle Size Ratchet"
      echo ""
      echo "⚠️ growth=${GROWTH_INT}% exceeds threshold but override is active: \`${OVERRIDE_REASON}\`"
      echo ""
      echo "Reminder: PR must additionally have a CODEOWNERS approval before merge."
    } >> "$GITHUB_STEP_SUMMARY"
  fi
  exit 0
fi

echo "::error::Bundle size growth ${GROWTH_INT}% exceeds ${GROWTH_THRESHOLD_NUM}% threshold (no override active)"
echo "Apply label \`BUNDLE_SIZE_GROWTH_OVERRIDE\` or include \`<!-- bundle-size-override: <reason> -->\` in PR description if growth is intentional."
exit 1
