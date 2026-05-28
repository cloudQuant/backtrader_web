#!/usr/bin/env bash
# Iteration 175 §6.7 — when nightly e2e fails, create or comment on the
# tracking issue.
#
# Strategy:
#   1. List open issues in the last 7 days with the title prefix
#      `[nightly-e2e] failure on `.
#   2. If found, append a comment with today's failure summary.
#   3. Otherwise, create a new issue with title
#      `[nightly-e2e] failure on YYYY-MM-DD`.
#   4. If gh API itself fails, write a notice to job summary so the failure
#      is still observable, but exit 0 (don't fail the entire workflow on
#      issue-management infra problems).
#
# Required env:
#   GH_TOKEN              GitHub token with issue write access
#   FAILURE_SUMMARY_PATH  path to a markdown file with failure details
#                          (uploaded as artifact alongside)
#
# Usage:
#   bash scripts/ci/report_nightly_failure.sh

set -uo pipefail

DATE=$(date -u +%Y-%m-%d)
TITLE="[nightly-e2e] failure on $DATE"
LABEL="nightly-e2e-failure"
SUMMARY_FILE="${FAILURE_SUMMARY_PATH:-failure_summary.md}"

emit_skip() {
  local reason="$1"
  echo "::warning::$reason"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
      echo "### Nightly E2E Issue Management"
      echo ""
      echo "_skipped — $reason_"
    } >> "$GITHUB_STEP_SUMMARY"
  fi
}

if ! command -v gh > /dev/null 2>&1; then
  emit_skip "gh CLI not available, issue creation skipped"
  exit 0
fi

if [ -z "${GH_TOKEN:-}" ]; then
  emit_skip "GH_TOKEN not set, issue creation skipped"
  exit 0
fi

# Build the comment body.
if [ ! -f "$SUMMARY_FILE" ]; then
  echo "WARN: $SUMMARY_FILE not found; using placeholder body"
  printf '## Nightly E2E failure on %s\n\nNo summary file produced — see workflow run artifacts.\n' "$DATE" > /tmp/failure_body.md
  SUMMARY_FILE=/tmp/failure_body.md
fi

# Find existing issue from the last 7 days.
EXISTING=$(gh issue list \
  --label "$LABEL" \
  --search "[nightly-e2e] failure" \
  --state open \
  --json number,createdAt,title \
  --jq '.[] | select(.title | startswith("[nightly-e2e] failure")) | select((.createdAt | fromdateiso8601) > (now - 604800)) | .number' \
  2>/dev/null | head -1 || true)

if [ -n "$EXISTING" ]; then
  echo "Reusing issue #$EXISTING"
  if ! gh issue comment "$EXISTING" --body-file "$SUMMARY_FILE" 2>/tmp/gh_err; then
    emit_skip "gh issue comment failed: $(cat /tmp/gh_err)"
    exit 0
  fi
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    echo "### Nightly E2E Issue Management" >> "$GITHUB_STEP_SUMMARY"
    echo "" >> "$GITHUB_STEP_SUMMARY"
    echo "Commented on existing issue #$EXISTING." >> "$GITHUB_STEP_SUMMARY"
  fi
  exit 0
fi

echo "No recent issue found, creating a new one."
if ! gh issue create \
  --title "$TITLE" \
  --label "$LABEL" \
  --body-file "$SUMMARY_FILE" 2>/tmp/gh_err; then
  emit_skip "gh issue create failed: $(cat /tmp/gh_err)"
  exit 0
fi

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  echo "### Nightly E2E Issue Management" >> "$GITHUB_STEP_SUMMARY"
  echo "" >> "$GITHUB_STEP_SUMMARY"
  echo "Created new issue: $TITLE" >> "$GITHUB_STEP_SUMMARY"
fi
