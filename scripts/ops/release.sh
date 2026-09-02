#!/usr/bin/env bash
# v0.2.0 release guard
#
# Mutable release operations must not run from a developer workstation. Use a
# release/vX.Y.Z -> master pull request, then let an authorized release manager
# create a protected tag that the artifact-only workflow can validate.

set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    printf '%s\n' \
        "This command is intentionally retired." \
        "Promote releases through release/vX.Y.Z -> master, then use the protected-tag workflow." \
        "It never creates tags, releases, or registry images."
    exit 0
fi

printf '%s\n' \
    "Refusing to perform a mutable local release." \
    "Use the release pull-request process and the protected-tag artifact workflow instead." >&2
exit 2
