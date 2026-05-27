#!/bin/bash
# Deprecated root shim; use ./scripts/app.sh start instead.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/app.sh" start "$@"
