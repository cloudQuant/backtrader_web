#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PID_DIR="$PROJECT_ROOT/.pids"

usage() {
  cat <<'EOF'
Usage: ./scripts/app.sh <start|stop|restart|status>

Commands:
  start    Start backend and frontend development services
  stop     Stop backend and frontend development services
  restart  Stop and then start development services
  status   Show PID-file based service status
EOF
}

show_status() {
  local service_name="$1"
  local pid_file="$2"

  if [ ! -f "$pid_file" ]; then
    echo "$service_name: stopped (no PID file)"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
    echo "$service_name: running (PID: $pid)"
  else
    echo "$service_name: stale PID file ($pid)"
  fi
}

command="${1:-}"
shift || true

case "$command" in
  start)
    exec bash "$SCRIPT_DIR/start_app.sh" "$@"
    ;;
  stop)
    exec bash "$SCRIPT_DIR/stop_app.sh" "$@"
    ;;
  restart)
    exec bash "$SCRIPT_DIR/restart_app.sh" "$@"
    ;;
  status)
    show_status "backend" "$PID_DIR/backend.pid"
    show_status "frontend" "$PID_DIR/frontend.pid"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $command" >&2
    usage >&2
    exit 2
    ;;
esac
