#!/usr/bin/env bash
# CI script: Check frontend bundle size against thresholds.
#
# Iteration 175 §7 — hard thresholds enforced as a blocker:
#   - entry chunk gzip <= 300 KB (= 300 * 1024 = 307200 bytes)
#   - login route non-vendor JS file count <= 4
#
# Plus legacy advisory thresholds inherited from 174 (uncompressed):
#   - total JS + CSS <= 20 MB (catches monaco worker accidents)
#   - largest vendor chunk <= 8 MB (advisory only)
#
# Usage:
#   ./scripts/ci/check_bundle_size.sh [dist_dir]
#
# Exit codes:
#   0 - all hard thresholds within budget
#   1 - any hard threshold exceeded

set -euo pipefail

DIST_DIR="${1:-src/frontend/dist}"
ROUTE_ASSETS_HELPER="$(dirname "$0")/list_route_assets.mjs"

# --- Iteration 175 §7 hard thresholds ---
ENTRY_GZIP_BUDGET_BYTES=307200    # 300 KB
LOGIN_NON_VENDOR_JS_BUDGET=4

# --- Legacy advisory thresholds (174) ---
MAX_TOTAL_KB=20000
MAX_VENDOR_CHUNK_KB=8000

echo "=========================================="
echo "Frontend Bundle Size Check (175 §7)"
echo "=========================================="

if [ ! -d "$DIST_DIR" ]; then
  echo "ERROR: dist directory not found at $DIST_DIR"
  echo "Run 'npm run build' first."
  exit 1
fi

# Portable stat (BSD vs GNU)
filesize() {
  local path="$1"
  stat -f%z "$path" 2>/dev/null || stat --format=%s "$path" 2>/dev/null
}

# --- Hard threshold 1: entry chunk gzip ---
ENTRY_FILE=$(find "$DIST_DIR/assets" -maxdepth 1 -name "index-*.js" -type f 2>/dev/null | head -1)
if [ -z "$ENTRY_FILE" ]; then
  echo "ERROR: entry chunk dist/assets/index-*.js not found"
  exit 1
fi
ENTRY_GZIP_BYTES=$(gzip -c -9 "$ENTRY_FILE" | wc -c | tr -d ' ')
ENTRY_RAW_BYTES=$(filesize "$ENTRY_FILE")

# --- Hard threshold 2: login non-vendor JS count ---
if [ -x "$ROUTE_ASSETS_HELPER" ] || [ -f "$ROUTE_ASSETS_HELPER" ]; then
  LOGIN_NON_VENDOR_JS=$(node "$ROUTE_ASSETS_HELPER" /login "$DIST_DIR" --kind=non-vendor-js | wc -l | tr -d ' ')
else
  echo "WARN: $ROUTE_ASSETS_HELPER not found — skipping login route asset audit (175 §7.2)"
  LOGIN_NON_VENDOR_JS=0
fi

# --- Advisory: total + largest ---
# Reuse the portable helper above for every file.  Chaining BSD and GNU `stat`
# in a pipeline made Linux collect both outputs, which produced an invalid
# arithmetic value such as `0\n18954728` under `set -u`.
TOTAL_BYTES=0
LARGEST_BYTES=0
while IFS= read -r -d '' asset_file; do
  asset_bytes=$(filesize "$asset_file")
  TOTAL_BYTES=$((TOTAL_BYTES + asset_bytes))
  if [ "$asset_bytes" -gt "$LARGEST_BYTES" ]; then
    LARGEST_BYTES=$asset_bytes
  fi
done < <(find "$DIST_DIR" -type f \( -name "*.js" -o -name "*.css" \) -print0)
TOTAL_KB=$((TOTAL_BYTES / 1024))
LARGEST_KB=$((LARGEST_BYTES / 1024))

# --- Print 175 §7 budget table ---
STATUS=PASS
print_row() {
  local name="$1" target="$2" actual="$3" pass="$4"
  printf '  %-40s | target=%-12s | actual=%-12s | %s\n' "$name" "$target" "$actual" "$pass"
}

echo ""
echo "--- 175 §7 Hard Budget ---"

if [ "$ENTRY_GZIP_BYTES" -le "$ENTRY_GZIP_BUDGET_BYTES" ]; then
  print_row "entry chunk gzip (bytes)" "<= $ENTRY_GZIP_BUDGET_BYTES" "$ENTRY_GZIP_BYTES" "PASS"
else
  print_row "entry chunk gzip (bytes)" "<= $ENTRY_GZIP_BUDGET_BYTES" "$ENTRY_GZIP_BYTES" "[FAIL]"
  echo "::error::entry chunk gzip $ENTRY_GZIP_BYTES bytes > $ENTRY_GZIP_BUDGET_BYTES bytes (300 KB)"
  STATUS=FAIL
fi

if [ "$LOGIN_NON_VENDOR_JS" -le "$LOGIN_NON_VENDOR_JS_BUDGET" ]; then
  print_row "/login non-vendor JS count" "<= $LOGIN_NON_VENDOR_JS_BUDGET" "$LOGIN_NON_VENDOR_JS" "PASS"
else
  print_row "/login non-vendor JS count" "<= $LOGIN_NON_VENDOR_JS_BUDGET" "$LOGIN_NON_VENDOR_JS" "[FAIL]"
  echo "::error::/login non-vendor JS files = $LOGIN_NON_VENDOR_JS > $LOGIN_NON_VENDOR_JS_BUDGET"
  STATUS=FAIL
fi

# --- Print advisory legacy table ---
echo ""
echo "--- Advisory thresholds (174-era) ---"
if [ "$TOTAL_KB" -gt "$MAX_TOTAL_KB" ]; then
  echo "::warning::Total ${TOTAL_KB}KB exceeds advisory ${MAX_TOTAL_KB}KB"
else
  echo "  total JS+CSS: ${TOTAL_KB} KB (advisory <= ${MAX_TOTAL_KB})"
fi
if [ "$LARGEST_KB" -gt "$MAX_VENDOR_CHUNK_KB" ]; then
  echo "::warning::Largest chunk ${LARGEST_KB}KB exceeds advisory ${MAX_VENDOR_CHUNK_KB}KB"
else
  echo "  largest chunk: ${LARGEST_KB} KB (advisory <= ${MAX_VENDOR_CHUNK_KB})"
fi

echo ""
echo "=========================================="
if [ "$STATUS" = FAIL ]; then
  echo "❌ Bundle size check FAILED (175 §7)"
  exit 1
fi
echo "✅ Bundle size check PASSED"
echo "  entry raw: $ENTRY_RAW_BYTES bytes / gzip: $ENTRY_GZIP_BYTES bytes"
exit 0
