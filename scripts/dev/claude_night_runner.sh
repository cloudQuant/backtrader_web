#!/usr/bin/env bash
# ==============================================================================
# claude_night_runner.sh — Unattended overnight runner for Claude Code CLI
#
# Purpose:
#   Runs `claude -p --dangerously-skip-permissions` in a loop, mimicking the
#   behaviour of manually opening Claude interactive mode and typing the task
#   file path.  Each cycle:
#     1. Sends the task file path as the prompt (identical to manual usage).
#     2. Claude reads the file, follows its instructions, and exits.
#     3. Subsequent cycles use `--continue` to resume the same conversation,
#        preserving context so Claude remembers previous fixes.
#     4. Every COMPACT_INTERVAL runs the conversation is reset (fresh start)
#        to keep context size manageable — equivalent to `/compact`.
#     5. Optionally runs git auto-commit between cycles.
#
# Prerequisites:
#   - Claude Code CLI installed and authenticated
#   - tmux or screen recommended (so the session survives terminal close)
#
# Usage:
#   chmod +x scripts/claude_night_runner.sh
#
#   # Simplest (defaults):
#   scripts/claude_night_runner.sh
#
#   # Custom:
#   scripts/claude_night_runner.sh \
#     --task-file docs/迭代/迭代45-继续优化.md \
#     --restart-delay 10 --max-runs 20 --compact-interval 3
#
#   # In tmux (recommended):
#   tmux new -s claude-night
#   scripts/claude_night_runner.sh
#   # Ctrl+b d  to detach;  tmux attach -t claude-night  to reattach
#
# Options:
#   --task-file <path>       Task markdown (relative to workdir)
#                            (default: docs/迭代/迭代45-继续优化.md)
#   --workdir <path>         Project root (default: script's parent dir)
#   --log-dir <path>         Log directory (default: <workdir>/logs/claude)
#   --restart-delay <s>      Seconds between cycles (default: 10)
#   --max-runs <n>           Max cycles, 0 = infinite (default: 0)
#   --compact-interval <n>   Start a fresh conversation every N runs to
#                            manage context size (simulates /compact).
#                            0 = never reset (default: 5)
#   --max-turns <n>          Max agentic turns per cycle (default: 200).
#                            Set high to match interactive-mode behaviour.
#   --model <name>           Model to use, e.g. sonnet, opus (default: CLI default)
#   --extra-args <args>      Extra arguments passed to claude CLI
#   --skip-git               Skip post-run git auto-commit
#   -h, --help               Show this help
# ==============================================================================

set -euo pipefail

# ---- Resolve defaults ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_WORKDIR="$(cd "$SCRIPT_DIR/.." && pwd)"

WORKDIR="$DEFAULT_WORKDIR"
TASK_FILE="docs/迭代/迭代45-继续优化.md"
LOG_DIR=""
MODEL=""
RESTART_DELAY=10
MAX_RUNS=0
COMPACT_INTERVAL=5
MAX_TURNS=200
EXTRA_ARGS=""
SKIP_GIT=false
RUN_COUNT=0

print_help() {
  sed -n '/^# ==/,/^# ==/p' "$0" | sed 's/^# *//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-file)         TASK_FILE="${2:?--task-file requires a value}";         shift 2 ;;
    --workdir)           WORKDIR="${2:?--workdir requires a value}";             shift 2 ;;
    --log-dir)           LOG_DIR="${2:?--log-dir requires a value}";             shift 2 ;;
    --model)             MODEL="${2:?--model requires a value}";                 shift 2 ;;
    --restart-delay)     RESTART_DELAY="${2:?--restart-delay requires a value}"; shift 2 ;;
    --max-runs)          MAX_RUNS="${2:?--max-runs requires a value}";           shift 2 ;;
    --compact-interval)  COMPACT_INTERVAL="${2:?--compact-interval requires a value}"; shift 2 ;;
    --max-turns)         MAX_TURNS="${2:?--max-turns requires a value}";         shift 2 ;;
    --extra-args)        EXTRA_ARGS="${2:-}";                                    shift 2 ;;
    --skip-git)          SKIP_GIT=true;                                          shift   ;;
    -h|--help)           print_help; exit 0 ;;
    *)                   echo "Unknown option: $1"; print_help; exit 1 ;;
  esac
done

# ---- Validate ----
TASK_FULL_PATH="$WORKDIR/$TASK_FILE"
if [[ ! -f "$TASK_FULL_PATH" ]]; then
  echo "Error: task file not found: $TASK_FULL_PATH"; exit 1
fi
if [[ -z "$LOG_DIR" ]]; then
  LOG_DIR="$WORKDIR/logs/claude"
fi
mkdir -p "$LOG_DIR"

if ! command -v claude &>/dev/null; then
  echo "Error: 'claude' not found. Install Claude Code CLI first."
  echo "  npm install -g @anthropic-ai/claude-code"
  exit 1
fi

# ---- Build base claude args ----
# -p = non-interactive print mode (process prompt, use tools, exit)
# --dangerously-skip-permissions = auto-approve all tool/command usage
# --output-format stream-json = real-time streaming for dual terminal+log output
CLAUDE_BASE_ARGS=(-p --dangerously-skip-permissions --verbose --output-format stream-json)
[[ "$MAX_TURNS" -gt 0 ]] && CLAUDE_BASE_ARGS+=(--max-turns "$MAX_TURNS")
[[ -n "$MODEL" ]] && CLAUDE_BASE_ARGS+=(--model "$MODEL")
# shellcheck disable=SC2206
[[ -n "$EXTRA_ARGS" ]] && CLAUDE_BASE_ARGS+=($EXTRA_ARGS)

# ---- Build the prompt ----
# Use the exact same input as manual interactive usage — just the task file path.
# Claude reads the file and follows its instructions.
PROMPT="$TASK_FILE"
CONTINUE_PROMPT="$TASK_FILE"

# ---- Print config ----
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  claude_night_runner.sh — Overnight Mode (backtrader_web)    ║"
echo "╠════════════════════════════════════════════════════════════════╣"
printf "║ %-20s %s\n" "Workdir:"          "$WORKDIR"
printf "║ %-20s %s\n" "Task file:"        "$TASK_FILE"
printf "║ %-20s %s\n" "Model:"            "${MODEL:-default}"
printf "║ %-20s %s\n" "Log dir:"          "$LOG_DIR"
printf "║ %-20s %ss\n" "Restart delay:"   "$RESTART_DELAY"
printf "║ %-20s %s\n" "Max runs:"         "$( [[ $MAX_RUNS -eq 0 ]] && echo 'infinite' || echo $MAX_RUNS )"
printf "║ %-20s %s\n" "Compact interval:" "$( [[ $COMPACT_INTERVAL -eq 0 ]] && echo 'disabled' || echo "every ${COMPACT_INTERVAL} runs" )"
printf "║ %-20s %s\n" "Max turns/cycle:"  "$MAX_TURNS"
printf "║ %-20s %s\n" "Git auto-commit:"  "$( $SKIP_GIT && echo 'disabled' || echo 'enabled' )"
echo "╚════════════════════════════════════════════════════════════════╝"
echo
echo "[INFO] Press Ctrl+C to stop."
echo

# ---- Main loop ----
while true; do
  RUN_COUNT=$((RUN_COUNT + 1))

  if [[ $MAX_RUNS -gt 0 && $RUN_COUNT -gt $MAX_RUNS ]]; then
    echo "[DONE] Reached max runs ($MAX_RUNS). Exiting."
    break
  fi

  ts="$(date +%F_%H-%M-%S)"
  log_file="$LOG_DIR/claude_run${RUN_COUNT}_${ts}.log"

  # Decide whether to --continue or start fresh (compact).
  # First run is always fresh. After that, use --continue unless we hit
  # the compact interval boundary.
  USE_CONTINUE=false
  if [[ $RUN_COUNT -gt 1 ]]; then
    if [[ $COMPACT_INTERVAL -gt 0 ]] && (( (RUN_COUNT - 1) % COMPACT_INTERVAL == 0 )); then
      echo "[COMPACT] Run #$RUN_COUNT: starting fresh conversation (context reset)." | tee -a "$log_file"
      USE_CONTINUE=false
    else
      USE_CONTINUE=true
    fi
  fi

  # Build args for this run
  CLAUDE_ARGS=("${CLAUDE_BASE_ARGS[@]}")
  CURRENT_PROMPT="$PROMPT"
  if $USE_CONTINUE; then
    CLAUDE_ARGS+=(--continue)
    CURRENT_PROMPT="$CONTINUE_PROMPT"
  fi

  {
    echo "==================================================================="
    echo "[RUN  ] #$RUN_COUNT  $(if $USE_CONTINUE; then echo '(--continue)'; else echo '(fresh)'; fi)"
    echo "[START] $(date '+%F %T')"
    echo "[TASK ] $TASK_FILE"
    echo "[CMD  ] claude ${CLAUDE_ARGS[*]} \"$CURRENT_PROMPT\""
    echo "==================================================================="
  } | tee -a "$log_file"

  # ---- Run claude ----
  # Use stream-json output format for real-time streaming (like interactive mode).
  # A Python filter extracts human-readable content and displays it on terminal
  # while saving the raw JSON events to the log file — dual output.
  set +e
  (
    cd "$WORKDIR"
    claude "${CLAUDE_ARGS[@]}" "$CURRENT_PROMPT" 2>&1
  ) | LOG_FILE="$log_file" python3 -u -c '
import os, sys, json

log_path = os.environ["LOG_FILE"]
with open(log_path, "a") as log:
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        log.write(line)
        log.flush()
        s = line.strip()
        if not s:
            continue
        try:
            d = json.loads(s)
            msg_type = d.get("type", "")
            content = d.get("content", "")
            tool = d.get("tool", "")
            if msg_type == "assistant" and content:
                print(content, flush=True)
            elif msg_type == "tool" and tool:
                print(f"[Tool: {tool}]", flush=True)
            elif msg_type == "result" and content:
                print(content, flush=True)
        except (json.JSONDecodeError, KeyError):
            print(s, flush=True)
'
  exit_code=${PIPESTATUS[0]}
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

  # ---- Post-run git auto-commit ----
  if ! $SKIP_GIT; then
    (
      cd "$WORKDIR"
      if git diff --quiet && git diff --cached --quiet; then
        echo "[GIT ] No changes to commit." | tee -a "$log_file"
      else
        git add -A
        git commit -m "auto: claude night runner cycle #${RUN_COUNT} — $(date '+%F %T')" \
          2>&1 | tee -a "$log_file" || true
      fi
    )
  fi

  echo "[INFO] Next run in ${RESTART_DELAY}s... (Ctrl+C to stop)"
  sleep "$RESTART_DELAY"
done
