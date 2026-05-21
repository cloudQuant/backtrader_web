#!/usr/bin/env bash
# CI script: Check frontend bundle size against thresholds.
#
# Thresholds are intentionally generous to catch regressions without
# blocking normal feature development. Adjust as the project matures.
#
# Usage:
#   ./scripts/check_bundle_size.sh [dist_dir]
#
# Exit codes:
#   0 - All checks passed
#   1 - Bundle size exceeds threshold

set -euo pipefail

DIST_DIR="${1:-src/frontend/dist}"

# Thresholds in KB (uncompressed)
# Note: Monaco editor + workers account for ~12MB. These thresholds are set
# to catch unexpected regressions, not to enforce minimal bundle size.
MAX_TOTAL_KB=20000       # 20 MB total (includes monaco-editor workers ~12MB)
MAX_ENTRY_KB=1200        # Entry chunk (index-*.js) - includes Vue + Element Plus + router
MAX_VENDOR_CHUNK_KB=8000 # Largest vendor chunk (monaco ts.worker)

echo "=========================================="
echo "Frontend Bundle Size Check"
echo "=========================================="

if [ ! -d "$DIST_DIR" ]; then
  echo "ERROR: dist directory not found at $DIST_DIR"
  echo "Run 'npm run build' first."
  exit 1
fi

# Calculate total size
TOTAL_BYTES=$(find "$DIST_DIR" -type f \( -name "*.js" -o -name "*.css" \) -exec stat -f%z {} + 2>/dev/null | awk '{s+=$1} END {print s+0}' || find "$DIST_DIR" -type f \( -name "*.js" -o -name "*.css" \) -exec stat --format=%s {} + 2>/dev/null | awk '{s+=$1} END {print s+0}')
TOTAL_KB=$((TOTAL_BYTES / 1024))

echo ""
echo "Total JS+CSS size: ${TOTAL_KB} KB"

# Find entry chunk size
ENTRY_FILE=$(find "$DIST_DIR/assets" -name "index-*.js" -type f 2>/dev/null | head -1)
if [ -n "$ENTRY_FILE" ]; then
  ENTRY_BYTES=$(stat -f%z "$ENTRY_FILE" 2>/dev/null || stat --format=%s "$ENTRY_FILE" 2>/dev/null)
  ENTRY_KB=$((ENTRY_BYTES / 1024))
  echo "Entry chunk: ${ENTRY_KB} KB ($(basename "$ENTRY_FILE"))"
else
  ENTRY_KB=0
  echo "Entry chunk: not found (skipping check)"
fi

# Find largest chunk
LARGEST_FILE=$(find "$DIST_DIR/assets" -name "*.js" -type f -exec stat -f"%z %N" {} + 2>/dev/null | sort -rn | head -1 || find "$DIST_DIR/assets" -name "*.js" -type f -printf "%s %p\n" 2>/dev/null | sort -rn | head -1)
if [ -n "$LARGEST_FILE" ]; then
  LARGEST_BYTES=$(echo "$LARGEST_FILE" | awk '{print $1}')
  LARGEST_NAME=$(echo "$LARGEST_FILE" | awk '{print $2}')
  LARGEST_KB=$((LARGEST_BYTES / 1024))
  echo "Largest chunk: ${LARGEST_KB} KB ($(basename "$LARGEST_NAME"))"
else
  LARGEST_KB=0
fi

echo ""
echo "--- Size Breakdown ---"
find "$DIST_DIR/assets" -name "*.js" -type f -exec stat -f"%z %N" {} + 2>/dev/null | sort -rn | head -10 | while read -r size name; do
  echo "  $((size / 1024)) KB  $(basename "$name")"
done 2>/dev/null || find "$DIST_DIR/assets" -name "*.js" -type f -printf "%s %f\n" 2>/dev/null | sort -rn | head -10 | while read -r size name; do
  echo "  $((size / 1024)) KB  $name"
done

echo ""
echo "--- Threshold Check ---"

FAILED=0

if [ "$TOTAL_KB" -gt "$MAX_TOTAL_KB" ]; then
  echo "::warning::FAIL: Total bundle size ${TOTAL_KB}KB exceeds ${MAX_TOTAL_KB}KB threshold"
  FAILED=1
else
  echo "PASS: Total ${TOTAL_KB}KB <= ${MAX_TOTAL_KB}KB"
fi

if [ "$ENTRY_KB" -gt "$MAX_ENTRY_KB" ] && [ "$ENTRY_KB" -gt 0 ]; then
  echo "::warning::FAIL: Entry chunk ${ENTRY_KB}KB exceeds ${MAX_ENTRY_KB}KB threshold"
  FAILED=1
elif [ "$ENTRY_KB" -gt 0 ]; then
  echo "PASS: Entry ${ENTRY_KB}KB <= ${MAX_ENTRY_KB}KB"
fi

if [ "$LARGEST_KB" -gt "$MAX_VENDOR_CHUNK_KB" ]; then
  echo "::warning::WARN: Largest chunk ${LARGEST_KB}KB exceeds ${MAX_VENDOR_CHUNK_KB}KB (advisory)"
fi

echo ""
echo "=========================================="
if [ "$FAILED" -eq 1 ]; then
  echo "❌ Bundle size check FAILED"
  exit 1
else
  echo "✅ Bundle size check PASSED"
  exit 0
fi
