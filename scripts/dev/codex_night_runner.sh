#!/usr/bin/env bash
# ==============================================================================
# codex_night_runner.sh — Unattended overnight runner for OpenAI Codex CLI
#
# Purpose:
#   Reads a task file (e.g. docs/迭代113-继续完善项目.md), feeds its content as
#   the prompt to `codex exec --full-auto`, and automatically restarts when
#   each session finishes — so it keeps making progress all night long.
#
# Prerequisites:
#   - codex CLI installed and logged in (`codex login`)
#   - tmux or screen (recommended, so the session survives terminal close)
#
# Usage:
#   1) Make executable (first time only):
#        chmod +x scripts/codex_night_runner.sh
#
#   2) Simplest run (uses defaults for this project):
#        scripts/codex_night_runner.sh
#
#   3) Run with custom options:
#        scripts/codex_night_runner.sh \
#          --task-file docs/迭代113-继续完善项目.md \
#          --workdir /path/to/project \
#          --model o3 \
#          --restart-delay 10
#
#   4) Overnight in tmux (recommended):
#        tmux new -s codex-night
#        scripts/codex_night_runner.sh
#        # Detach:   Ctrl+b  then  d
#        # Reattach: tmux attach -t codex-night
#
# Options:
#   --task-file <path>     Task markdown file (default: docs/迭代113-继续完善项目.md)
#   --workdir <path>       Project root (default: script's parent directory)
#   --log-dir <path>       Log directory (default: <workdir>/logs/codex)
#   --model <model>        Codex model to use (default: auto, i.e. codex CLI default)
#   --restart-delay <s>    Seconds between restarts (default: 10)
#   --max-runs <n>         Max restart cycles, 0 = infinite (default: 0)
#   --extra-args <args>    Extra arguments passed verbatim to codex exec
#   -h, --help             Show this help
#
# How it works:
#   Each cycle:  cat <task-file> | codex exec --full-auto -C <workdir> -m <model> -
#   When codex finishes (task done / error / token limit), the script waits
#   --restart-delay seconds and then starts a fresh session with the same task
#   file, so codex picks up where it left off by reading the current code state.
#
# Notes:
#   - --full-auto = automatic command approval + workspace-write sandbox.
#   - Logs are written to timestamped files under --log-dir for review.
#   - Press Ctrl+C to stop the loop.
# ==============================================================================

set -euo pipefail

# ---- Resolve defaults relative to this script's location ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_WORKDIR="$(cd "$SCRIPT_DIR/.." && pwd)"

WORKDIR="$DEFAULT_WORKDIR"
TASK_FILE="docs/迭代113-继续完善项目.md"
LOG_DIR=""
MODEL=""
RESTART_DELAY=10
MAX_RUNS=0
EXTRA_ARGS=""
RUN_COUNT=0

print_help() {
  sed -n '/^# ==/,/^# ==/p' "$0" | sed 's/^# *//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-file)    TASK_FILE="${2:?--task-file requires a value}";  shift 2 ;;
    --workdir)      WORKDIR="${2:?--workdir requires a value}";      shift 2 ;;
    --log-dir)      LOG_DIR="${2:?--log-dir requires a value}";      shift 2 ;;
    --model)        MODEL="${2:?--model requires a value}";          shift 2 ;;
    --restart-delay) RESTART_DELAY="${2:?--restart-delay requires a value}"; shift 2 ;;
    --max-runs)     MAX_RUNS="${2:?--max-runs requires a value}";    shift 2 ;;
    --extra-args)   EXTRA_ARGS="${2:-}";                             shift 2 ;;
    -h|--help)      print_help; exit 0 ;;
    *)              echo "Unknown option: $1"; print_help; exit 1 ;;
  esac
done

# ---- Validate ----
TASK_FULL_PATH="$WORKDIR/$TASK_FILE"
if [[ ! -f "$TASK_FULL_PATH" ]]; then
  echo "Error: task file not found: $TASK_FULL_PATH"
  exit 1
fi

if [[ -z "$LOG_DIR" ]]; then
  LOG_DIR="$WORKDIR/logs/codex"
fi
mkdir -p "$LOG_DIR"

if ! [[ "$RESTART_DELAY" =~ ^[0-9]+$ ]]; then
  echo "Error: --restart-delay must be a non-negative integer"; exit 1
fi
if ! [[ "$MAX_RUNS" =~ ^[0-9]+$ ]]; then
  echo "Error: --max-runs must be a non-negative integer"; exit 1
fi

if ! command -v codex &>/dev/null; then
  echo "Error: 'codex' command not found. Install it first: npm install -g @openai/codex"
  exit 1
fi

# ---- Print config ----
echo "╔════════════════════════════════════════════════════════════╗"
echo "║         codex_night_runner.sh — Overnight Mode            ║"
echo "╠════════════════════════════════════════════════════════════╣"
printf "║ %-14s %s\n" "Workdir:"       "$WORKDIR"
printf "║ %-14s %s\n" "Task file:"     "$TASK_FILE"
printf "║ %-14s %s\n" "Model:"         "${MODEL:-auto (codex default)}"
printf "║ %-14s %s\n" "Log dir:"       "$LOG_DIR"
printf "║ %-14s %ss\n" "Restart delay:" "$RESTART_DELAY"
printf "║ %-14s %s\n" "Max runs:"      "$( [[ $MAX_RUNS -eq 0 ]] && echo 'infinite' || echo $MAX_RUNS )"
[[ -n "$EXTRA_ARGS" ]] && printf "║ %-14s %s\n" "Extra args:" "$EXTRA_ARGS"
echo "╚════════════════════════════════════════════════════════════╝"
echo

# ---- Build codex exec arguments ----
CODEX_ARGS=(exec --full-auto -C "$WORKDIR")
[[ -n "$MODEL" ]] && CODEX_ARGS+=(-m "$MODEL")
# shellcheck disable=SC2206
[[ -n "$EXTRA_ARGS" ]] && CODEX_ARGS+=($EXTRA_ARGS)
CODEX_ARGS+=(-)

# ---- Main loop ----
while true; do
  RUN_COUNT=$((RUN_COUNT + 1))

  if [[ $MAX_RUNS -gt 0 && $RUN_COUNT -gt $MAX_RUNS ]]; then
    echo "[DONE] Reached max runs ($MAX_RUNS). Exiting."
    break
  fi

  ts="$(date +%F_%H-%M-%S)"
  log_file="$LOG_DIR/codex_run${RUN_COUNT}_${ts}.log"

  {
    echo "==================================================================="
    echo "[RUN  ] #$RUN_COUNT"
    echo "[START] $(date '+%F %T')"
    echo "[TASK ] $TASK_FILE"
    echo "[MODEL] ${MODEL:-auto}"
    echo "[CMD  ] codex ${CODEX_ARGS[*]}"
    echo "==================================================================="
  } | tee -a "$log_file"

  set +e
  cat "$TASK_FULL_PATH" | codex "${CODEX_ARGS[@]}" \
    2>&1 | tee -a "$log_file"
  exit_code=${PIPESTATUS[1]}
  set -e

  {
    echo
    echo "==================================================================="
    echo "[END  ] $(date '+%F %T')"
    echo "[CODE ] $exit_code"
    echo "==================================================================="
  } | tee -a "$log_file"

  if [[ $exit_code -eq 0 ]]; then
    echo "[OK  ] Run #$RUN_COUNT finished successfully."
  else
    echo "[WARN] Run #$RUN_COUNT exited with code $exit_code."
  fi

  echo "[INFO] Next run in ${RESTART_DELAY}s... (Ctrl+C to stop)"
  sleep "$RESTART_DELAY"
done
