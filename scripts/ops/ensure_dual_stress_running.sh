#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PID_DIR="${PROJECT_ROOT}/.pids"
REPORT_DIR="${PROJECT_ROOT}/reports"
PID_FILE="${DUAL_STRESS_PID_FILE:-${PID_DIR}/dual_stress_watchdog.pid}"
LOG_FILE="${DUAL_STRESS_LOG_FILE:-${REPORT_DIR}/dual_stress_watchdog_7d.log}"
MONITOR_PID_FILE="${DUAL_STRESS_MONITOR_PID_FILE:-${PID_DIR}/dual_stress_monitor.pid}"
MONITOR_LOG_FILE="${DUAL_STRESS_MONITOR_LOG_FILE:-${REPORT_DIR}/dual_stress_monitor_7d.log}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python)}"
TARGETS="${TARGETS:-futures,ib,mt5}"
HOLD_SECONDS="${HOLD_SECONDS:-604800}"
STATUS_INTERVAL="${STATUS_INTERVAL:-30}"
NO_STOP_EXISTING="${NO_STOP_EXISTING:-1}"
STOP_TIMEOUT_SECONDS="${STOP_TIMEOUT_SECONDS:-60}"
ACTION="${1:-start}"

mkdir -p "$PID_DIR" "$REPORT_DIR"

is_running() {
    local pid="${1:-}"
    [[ -n "$pid" ]] && ps -p "$pid" >/dev/null 2>&1
}

pid_from_file() {
    local pid_file="${1:-$PID_FILE}"
    if [[ -f "$pid_file" ]]; then
        tr -d '[:space:]' < "$pid_file"
    fi
}

cmdline_for_pid() {
    local pid="${1:-}"
    if [[ -z "$pid" ]]; then
        return 1
    fi
    if [[ -r "/proc/${pid}/cmdline" ]]; then
        tr '\0' ' ' < "/proc/${pid}/cmdline"
        return 0
    fi
    ps -p "$pid" -o args= 2>/dev/null || return 1
}

pid_matches_mode() {
    local mode="$1"
    local pid="${2:-}"
    local require_targets="${3:-1}"
    local script_path="${PROJECT_ROOT}/src/backend/scripts/run_dual_exchange_simulation.py"
    local relative_script_path="src/backend/scripts/run_dual_exchange_simulation.py"
    local cmdline

    if [[ -z "$pid" ]]; then
        return 1
    fi
    cmdline="$(cmdline_for_pid "$pid" 2>/dev/null || true)"
    if [[ "$cmdline" != *"$script_path"* && "$cmdline" != *"$relative_script_path"* ]]; then
        return 1
    fi
    if [[ "$require_targets" == "1" && "$cmdline" != *"--targets ${TARGETS}"* ]]; then
        return 1
    fi
    [[ "$cmdline" != *" --no-hold"* ]] || return 1
    case "$mode" in
        monitor)
            [[ "$cmdline" == *" --monitor-only"* ]] || return 1
            ;;
        supervisor)
            [[ "$cmdline" != *" --monitor-only"* ]] || return 1
            ;;
        *)
            return 2
            ;;
    esac
}

find_existing_process() {
    local mode="$1"
    local script_path="${PROJECT_ROOT}/src/backend/scripts/run_dual_exchange_simulation.py"
    local relative_script_path="src/backend/scripts/run_dual_exchange_simulation.py"
    local pid cmdline

    for proc_dir in /proc/[0-9]*; do
        [[ -d "$proc_dir" ]] || continue
        pid="${proc_dir##*/}"
        [[ "$pid" != "$$" ]] || continue
        cmdline="$(cmdline_for_pid "$pid" 2>/dev/null || true)"
        if [[ "$cmdline" != *"$script_path"* && "$cmdline" != *"$relative_script_path"* ]]; then
            continue
        fi
        [[ "$cmdline" == *"--targets ${TARGETS}"* ]] || continue
        [[ "$cmdline" != *" --no-hold"* ]] || continue
        case "$mode" in
            monitor)
                [[ "$cmdline" == *" --monitor-only"* ]] || continue
                ;;
            supervisor)
                [[ "$cmdline" != *" --monitor-only"* ]] || continue
                ;;
            *)
                return 2
                ;;
        esac
        echo "$pid"
        return 0
    done
    return 1
}

find_existing_supervisor_processes() {
    local script_path="${PROJECT_ROOT}/src/backend/scripts/run_dual_exchange_simulation.py"
    local relative_script_path="src/backend/scripts/run_dual_exchange_simulation.py"
    local pid cmdline

    for proc_dir in /proc/[0-9]*; do
        [[ -d "$proc_dir" ]] || continue
        pid="${proc_dir##*/}"
        [[ "$pid" != "$$" ]] || continue
        cmdline="$(cmdline_for_pid "$pid" 2>/dev/null || true)"
        if [[ "$cmdline" != *"$script_path"* && "$cmdline" != *"$relative_script_path"* ]]; then
            continue
        fi
        [[ "$cmdline" != *" --monitor-only"* ]] || continue
        [[ "$cmdline" != *" --no-hold"* ]] || continue
        echo "$pid"
    done
}

current_or_discovered_pid() {
    local mode="$1"
    local pid_file="$2"
    local current_pid

    current_pid="$(pid_from_file "$pid_file" || true)"
    if pid_matches_mode "$mode" "$current_pid"; then
        echo "$current_pid"
        return 0
    fi

    current_pid="$(find_existing_process "$mode" || true)"
    if is_running "$current_pid"; then
        echo "$current_pid" > "$pid_file"
        echo "$current_pid"
        return 0
    fi

    rm -f "$pid_file"
    return 1
}

status_split_supervisors() {
    local primary_pid="${1:-}"
    local seen_pids=" ${primary_pid} "
    local found=0
    local discover=1
    local pid_file pid label
    local -a pid_files=()

    if [[ -n "${DUAL_STRESS_SUPERVISOR_PID_FILES:-}" ]]; then
        read -r -a pid_files <<< "${DUAL_STRESS_SUPERVISOR_PID_FILES}"
        discover=0
    else
        pid_files=("${PID_DIR}"/*supervisor.pid)
    fi

    for pid_file in "${pid_files[@]}"; do
        [[ -f "$pid_file" ]] || continue
        pid="$(pid_from_file "$pid_file" || true)"
        if ! pid_matches_mode supervisor "$pid" 0; then
            rm -f "$pid_file"
            continue
        fi
        if [[ "$seen_pids" == *" ${pid} "* ]]; then
            continue
        fi
        label="$(basename "$pid_file")"
        echo "split stress supervisor running: pid=${pid} file=${label}"
        seen_pids+="${pid} "
        found=1
    done

    if [[ "$discover" == "0" ]]; then
        if [[ "$found" == "0" ]]; then
            echo "split stress supervisors not running"
        fi
        return 0
    fi

    while IFS= read -r pid; do
        [[ -n "$pid" ]] || continue
        if [[ "$seen_pids" == *" ${pid} "* ]]; then
            continue
        fi
        if ! is_running "$pid"; then
            continue
        fi
        echo "split stress supervisor running: pid=${pid} file=discovered"
        seen_pids+="${pid} "
        found=1
    done < <(find_existing_supervisor_processes || true)

    if [[ "$found" == "0" ]]; then
        echo "split stress supervisors not running"
    fi
}

first_split_supervisor_pid() {
    local primary_pid="${1:-}"
    local seen_pids=" ${primary_pid} "
    local discover=1
    local pid_file pid
    local -a pid_files=()

    if [[ -n "${DUAL_STRESS_SUPERVISOR_PID_FILES:-}" ]]; then
        read -r -a pid_files <<< "${DUAL_STRESS_SUPERVISOR_PID_FILES}"
        discover=0
    else
        pid_files=("${PID_DIR}"/*supervisor.pid)
    fi

    for pid_file in "${pid_files[@]}"; do
        [[ -f "$pid_file" ]] || continue
        pid="$(pid_from_file "$pid_file" || true)"
        if ! pid_matches_mode supervisor "$pid" 0; then
            rm -f "$pid_file"
            continue
        fi
        if [[ "$seen_pids" == *" ${pid} "* ]]; then
            continue
        fi
        echo "$pid"
        return 0
    done

    if [[ "$discover" == "0" ]]; then
        return 1
    fi

    while IFS= read -r pid; do
        [[ -n "$pid" ]] || continue
        if [[ "$seen_pids" == *" ${pid} "* ]]; then
            continue
        fi
        if ! is_running "$pid"; then
            continue
        fi
        echo "$pid"
        return 0
    done < <(find_existing_supervisor_processes || true)

    return 1
}

start_supervisor() {
    local current_pid
    current_pid="$(current_or_discovered_pid supervisor "$PID_FILE" || true)"
    if is_running "$current_pid"; then
        echo "dual stress supervisor already running: pid=${current_pid}"
        return 0
    fi

    local split_pid
    split_pid="$(first_split_supervisor_pid "$current_pid" || true)"
    if [[ "${NO_START_IF_SPLIT_SUPERVISOR:-1}" == "1" ]] && is_running "$split_pid"; then
        echo "split stress supervisor already running: pid=${split_pid}; not starting dual stress supervisor"
        status_split_supervisors "$current_pid"
        return 0
    fi

    rm -f "$PID_FILE"

    local -a cmd=(
        "$PYTHON_BIN"
        -u
        "$PROJECT_ROOT/src/backend/scripts/run_dual_exchange_simulation.py"
        --targets "$TARGETS"
        --hold-seconds "$HOLD_SECONDS"
        --status-interval "$STATUS_INTERVAL"
    )

    if [[ "$NO_STOP_EXISTING" == "1" ]]; then
        cmd+=(--no-stop-existing)
    fi

    if [[ "${SKIP_SEED:-0}" == "1" ]]; then
        cmd+=(--skip-seed)
    fi

    if command -v setsid >/dev/null 2>&1; then
        setsid "${cmd[@]}" >> "$LOG_FILE" 2>&1 &
    else
        nohup "${cmd[@]}" >> "$LOG_FILE" 2>&1 &
    fi

    local pid=$!
    echo "$pid" > "$PID_FILE"
    echo "started dual stress supervisor: pid=${pid} log=${LOG_FILE}"
}

stop_supervisor() {
    local current_pid elapsed
    current_pid="$(current_or_discovered_pid supervisor "$PID_FILE" || true)"
    if ! is_running "$current_pid"; then
        rm -f "$PID_FILE"
        return 0
    fi

    if ! kill "$current_pid" 2>/dev/null; then
        if ! is_running "$current_pid"; then
            rm -f "$PID_FILE"
            return 0
        fi
        echo "failed to signal dual stress supervisor: pid=${current_pid}" >&2
        return 1
    fi

    for ((elapsed = 0; elapsed < STOP_TIMEOUT_SECONDS; elapsed++)); do
        sleep 1
        if ! is_running "$current_pid"; then
            rm -f "$PID_FILE"
            return 0
        fi
    done

    echo "dual stress supervisor still running after ${STOP_TIMEOUT_SECONDS}s: pid=${current_pid}" >&2
    return 1
}

start_monitor() {
    local current_pid
    current_pid="$(current_or_discovered_pid monitor "$MONITOR_PID_FILE" || true)"
    if is_running "$current_pid"; then
        echo "dual stress monitor already running: pid=${current_pid}"
        return 0
    fi

    rm -f "$MONITOR_PID_FILE"

    local -a cmd=(
        "$PYTHON_BIN"
        -u
        "$PROJECT_ROOT/src/backend/scripts/run_dual_exchange_simulation.py"
        --monitor-only
        --skip-seed
        --targets "$TARGETS"
        --hold-seconds "$HOLD_SECONDS"
        --status-interval "$STATUS_INTERVAL"
    )

    if command -v setsid >/dev/null 2>&1; then
        setsid "${cmd[@]}" >> "$MONITOR_LOG_FILE" 2>&1 &
    else
        nohup "${cmd[@]}" >> "$MONITOR_LOG_FILE" 2>&1 &
    fi

    local pid=$!
    echo "$pid" > "$MONITOR_PID_FILE"
    echo "started dual stress monitor: pid=${pid} log=${MONITOR_LOG_FILE}"
}

status_supervisor() {
    local current_pid
    current_pid="$(current_or_discovered_pid supervisor "$PID_FILE" || true)"
    if is_running "$current_pid"; then
        echo "dual stress supervisor running: pid=${current_pid}"
    else
        echo "dual stress supervisor not running"
    fi
    status_split_supervisors "$current_pid"
    local monitor_pid
    monitor_pid="$(current_or_discovered_pid monitor "$MONITOR_PID_FILE" || true)"
    if is_running "$monitor_pid"; then
        echo "dual stress monitor running: pid=${monitor_pid}"
    else
        echo "dual stress monitor not running"
    fi

    "$PYTHON_BIN" -u "$PROJECT_ROOT/src/backend/scripts/run_dual_exchange_simulation.py" \
        --monitor-only \
        --skip-seed \
        --targets "$TARGETS" \
        --no-hold
}

case "$ACTION" in
    start)
        start_supervisor
        ;;
    monitor)
        start_monitor
        ;;
    status)
        status_supervisor
        ;;
    restart)
        stop_supervisor
        start_supervisor
        ;;
    *)
        echo "usage: $0 [start|monitor|status|restart]" >&2
        exit 2
        ;;
esac
