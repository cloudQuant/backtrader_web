#!/usr/bin/env bash
# bandit_gate.sh - Bandit security scan gate for CI
# Runs Bandit, parses JSON output, and exits non-zero only for
# HIGH severity issues with MEDIUM or HIGH confidence.
# LOW/MEDIUM severity issues are reported as warnings but do not block.

set -euo pipefail

TARGET_DIR="${1:-app}"
REPORT_FILE="bandit-report.json"

echo "=== Running Bandit security scan on '${TARGET_DIR}' ==="

# Run Bandit and capture exit code
# Bandit exits non-zero when it finds ANY issue, so we capture the code
bandit_exit=0
bandit -r "${TARGET_DIR}" -f json -o "${REPORT_FILE}" 2>/dev/null || bandit_exit=$?

# If bandit itself failed to run (not just finding issues)
# Exit codes: 0 = no issues, 1 = issues found, 2+ = bandit error
if [ "${bandit_exit}" -gt 1 ]; then
    echo "::error::Bandit failed to complete scan (exit code: ${bandit_exit}). Scan incomplete."
    exit 1
fi

# Check if report file was created
if [ ! -f "${REPORT_FILE}" ]; then
    echo "::error::Bandit report file not generated. Scan incomplete."
    exit 1
fi

# Parse JSON report for HIGH severity + MEDIUM/HIGH confidence issues
python_exit=0
python3 -c "
import json
import sys

try:
    with open('${REPORT_FILE}', 'r') as f:
        report = json.load(f)
except (json.JSONDecodeError, FileNotFoundError) as e:
    print(f'::error::Failed to parse Bandit report: {e}', file=sys.stderr)
    sys.exit(2)

results = report.get('results', [])
high_blocking = []
warnings = []

for issue in results:
    severity = issue.get('issue_severity', '').upper()
    confidence = issue.get('issue_confidence', '').upper()
    filename = issue.get('filename', 'unknown')
    line = issue.get('line_number', 0)
    test_id = issue.get('test_id', '')
    text = issue.get('issue_text', '')

    if severity == 'HIGH' and confidence in ('MEDIUM', 'HIGH'):
        high_blocking.append(issue)
        print(f'::error file={filename},line={line}::[{test_id}] {text} (severity={severity}, confidence={confidence})')
    else:
        warnings.append(issue)
        print(f'::warning file={filename},line={line}::[{test_id}] {text} (severity={severity}, confidence={confidence})')

if warnings:
    print(f'\n⚠️  {len(warnings)} LOW/MEDIUM severity issue(s) found (non-blocking):')
    for w in warnings:
        print(f'  - [{w[\"test_id\"]}] {w[\"filename\"]}:{w[\"line_number\"]} - {w[\"issue_text\"]}')

if high_blocking:
    print(f'\n❌ {len(high_blocking)} HIGH severity issue(s) with MEDIUM/HIGH confidence found (blocking):')
    for h in high_blocking:
        print(f'  - [{h[\"test_id\"]}] {h[\"filename\"]}:{h[\"line_number\"]} - {h[\"issue_text\"]}')
    sys.exit(1)
else:
    print('\n✅ No HIGH severity issues with MEDIUM/HIGH confidence found.')
    sys.exit(0)
" || python_exit=$?

if [ "${python_exit}" -eq 2 ]; then
    echo "::error::Failed to parse Bandit report. Scan incomplete."
    exit 1
fi

exit "${python_exit}"
