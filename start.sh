#!/usr/bin/env bash
# Start the nesting tool on Linux or macOS (desktop icon or terminal).
# 1. update from GitHub if possible (never waits for a password, never stops on failure)
# 2. find Python 3.11+, 3. open the page if the tool already runs, else start it on port 8800;
#    the tool stops by itself when the page is closed.
# Everything is logged to ~/nesting-project/start.log; a failure also shows a desktop notice.
# Exit codes: 0 ok or already running, 1 cannot open the folder of this script, 2 no Python,
# 3 Python older than 3.11, 4 port taken by another program, 5 the tool did not start.
# For tests: NESTING_PORT (default 8800) and NESTING_PROJECT (default ~/nesting-project).
#
# All of it is in main(): bash reads the whole function before running it, so a pull that
# rewrites this file cannot change what runs now (the new version runs at the next start).

main() {
    local PORT="${NESTING_PORT:-8800}"
    local PROJECT="${NESTING_PROJECT:-$HOME/nesting-project}"
    local URL="http://127.0.0.1:$PORT/"
    local LOG="$PROJECT/start.log"
    local here PY c code seed

    fail() {
        local msg="$2"
        echo
        echo "$msg"
        echo "Log: $LOG"
        if command -v notify-send >/dev/null 2>&1; then
            notify-send "Nesting tool" "$msg"
        elif command -v zenity >/dev/null 2>&1; then
            zenity --error --title="Nesting tool" --text="$msg"
        fi
        return "$1"
    }

    # ---- log (overwritten at each start; also shown when run in a terminal) ----------------
    if mkdir -p "$PROJECT" 2>/dev/null && { : >"$LOG"; } 2>/dev/null; then
        if [ -t 1 ]; then
            exec > >(tee "$LOG") 2>&1
        else
            exec >"$LOG" 2>&1
        fi
    else
        LOG="(cannot write $LOG)"
    fi
    echo "Nesting tool, started $(date '+%Y-%m-%d %H:%M:%S')"

    here="$(dirname "${BASH_SOURCE[0]}")"
    cd "$here" 2>/dev/null || { fail 1 "Cannot open the folder of start.sh: $here"; return; }
    echo "Nesting tool in $PWD"

    # ---- update -----------------------------------------------------------------------------
    if command -v git >/dev/null 2>&1; then
        echo "Checking for updates..."
        if GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false SSH_ASKPASS=/bin/false \
            GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes}" \
            git -c credential.interactive=never \
                -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=30 \
                pull --ff-only -q </dev/null; then
            echo "Update: up to date with GitHub."
        else
            echo "Update skipped (offline, local changes or no access): starting the version on this PC."
        fi
        git --no-pager log -1 --format='Version %h of %cs' </dev/null 2>/dev/null
    else
        echo "Git not found: no update, starting the version on this PC."
    fi

    # ---- Python -----------------------------------------------------------------------------
    PY=""
    for c in python3 python; do
        if "$c" --version >/dev/null 2>&1; then
            PY="$c"
            break
        fi
    done
    if [ -z "$PY" ]; then
        fail 2 "Python 3 was not found. Install Python 3.11 or newer."
        return
    fi
    if ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        fail 3 "This Python is too old (3.11 or newer is needed): $("$PY" --version 2>&1)"
        return
    fi

    # ---- already running? -------------------------------------------------------------------
    "$PY" -m nesting.ping "$PORT"
    code=$?
    case "$code" in
        0)
            echo "The tool is already running: opening the page $URL"
            "$PY" -m webbrowser "$URL"
            return 0
            ;;
        1) ;;
        *)
            fail 4 "Port $PORT is in use by another program (or an old copy of the tool still runs in a window: close it). Nothing was started."
            return
            ;;
    esac

    # ---- start ------------------------------------------------------------------------------
    seed=""
    [ -e "$PROJECT/shapes" ] || seed="--seed-plates"
    echo "Project folder: $PROJECT"
    echo "The page opens in the browser: $URL"
    if ! "$PY" -m nesting "$PROJECT" --port "$PORT" --open --exit-when-closed ${seed:+"$seed"}; then
        fail 5 "The tool did not start or stopped with an error."
        return
    fi
    echo "The tool has stopped."
}

main "$@"; exit $?
