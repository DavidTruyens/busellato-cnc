#!/usr/bin/env bash
# Start the nesting tool on Linux or macOS (desktop icon or terminal).
# 1. update from GitHub if possible (never waits for a password, never stops on failure)
# 2. find Python 3.11+, 3. open the page if the tool already runs, else start it on port 8800;
#    the tool stops by itself when the page is closed.
# Everything is logged to ~/nesting-project/start.log (a second click while the tool runs does
# not erase it); a failure also shows a desktop notice.
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
    # Until it is known that no tool runs, log to a file of this start only: a second click
    # on the icon must never truncate the log the running tool still writes to.
    local NEW="$PROJECT/start.log.new.$$"
    local CUR=""          # the file that holds this start's messages ("" when none)
    local TERM_OUT=""     # set when started from a terminal: the log is shown there too
    local TEE_PID=""      # the tee that shows the log in the terminal
    local here PY OLD c code seed

    # Move this start's lines onto start.log and keep logging there (append mode).
    # Only for a start or a failure, never when the tool already runs.
    promote() {
        [ -n "$CUR" ] && [ "$CUR" = "$NEW" ] || return 0
        if mv -f "$NEW" "$LOG" 2>/dev/null; then
            CUR="$LOG"
            if [ -n "$TERM_OUT" ]; then
                cat "$LOG" >&3
                show_and_log "$LOG"
            else
                exec >>"$LOG" 2>&1
            fi
        elif [ -n "$TERM_OUT" ]; then
            cat "$NEW" >&3
            show_and_log "$NEW"
        fi
    }

    # Terminal: show the output there and append it to file $1. tee reads a fifo and runs in
    # the background, so main can let it write the last lines before the script ends.
    show_and_log() {
        local fifo="$PROJECT/.start.fifo.$$"
        rm -f "$fifo"
        if mkfifo "$fifo" 2>/dev/null; then
            tee -a "$1" <"$fifo" >&3 2>&4 &
            TEE_PID=$!
            exec >"$fifo" 2>&1
            rm -f "$fifo"
        else
            exec >>"$1" 2>&1
        fi
    }

    fail() {
        local msg="$2"
        promote
        echo
        echo "$msg"
        echo "Log: ${CUR:-(the log file cannot be written)}"
        if command -v notify-send >/dev/null 2>&1 && notify-send "Nesting tool" "$msg"; then
            :
        elif command -v zenity >/dev/null 2>&1; then
            zenity --error --title="Nesting tool" --text="$msg"
        fi
        return "$1"
    }

    steps() {
        # ---- log --------------------------------------------------------------------------------
        exec 3>&1 4>&2       # the original output, for the terminal
        [ -t 1 ] && TERM_OUT=1
        if mkdir -p "$PROJECT" 2>/dev/null && { : >"$NEW"; } 2>/dev/null; then
            CUR="$NEW"
            [ -n "$TERM_OUT" ] && echo "Checking for updates and Python..."
            exec >"$NEW" 2>&1
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
        # The first one that is 3.11 or newer (python3 is 3.10 on Ubuntu 22.04, for example).
        PY=""
        OLD=""          # the first Python found that is too old
        for c in python3.13 python3.12 python3.11 python3 python; do
            "$c" --version >/dev/null 2>&1 || continue
            if "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
                PY="$c"
                break
            fi
            [ -n "$OLD" ] || OLD="$c"
        done
        if [ -z "$PY" ] && [ -z "$OLD" ]; then
            fail 2 "Python 3 was not found. Install Python 3.11 or newer."
            return
        fi
        if [ -z "$PY" ]; then
            fail 3 "This Python is too old (3.11 or newer is needed): $("$OLD" --version 2>&1)"
            return
        fi

        # ---- already running? -------------------------------------------------------------------
        "$PY" -m nesting.ping "$PORT"
        code=$?
        case "$code" in
            0)
                # Never truncate start.log here: the running tool writes to it (append mode).
                [ -n "$TERM_OUT" ] && [ -n "$CUR" ] && cat "$CUR" >&3
                [ -n "$CUR" ] && rm -f "$CUR"
                if [ -n "$TERM_OUT" ]; then
                    show_and_log "$LOG"
                else
                    exec >>"$LOG" 2>&1 || exec >/dev/null 2>&1
                fi
                echo "The tool is already running: opening the page $URL"
                "$PY" -m webbrowser "$URL" >/dev/null   # its stdout is only a bell character
                return 0
                ;;
            1) ;;
            *)
                fail 4 "Port $PORT is in use by another program (or an old copy of the tool still runs in a window: close it). Nothing was started."
                return
                ;;
        esac

        # ---- start ------------------------------------------------------------------------------
        promote
        seed=""
        [ -e "$PROJECT/shapes" ] || seed="--seed-plates"
        echo "Project folder: $PROJECT"
        echo "The page opens in the browser: $URL"
        "$PY" -m nesting "$PROJECT" --port "$PORT" --open --exit-when-closed ${seed:+"$seed"}
        code=$?
        case "$code" in
            0) ;;
            129|130|143)    # hangup, Ctrl+C, terminate (e.g. logout): not a failure
                echo "The tool was stopped (signal)."
                return 0
                ;;
            *)
                # Two clicks at once: both found the port free, the other one's tool got it.
                # That is no failure (only this start's lines replaced start.log).
                if "$PY" -m nesting.ping "$PORT"; then
                    echo "The tool is already running (started by another click): opening the page."
                    "$PY" -m webbrowser "$URL" >/dev/null
                    return 0
                fi
                fail 5 "The tool did not start or stopped with an error."
                return
                ;;
        esac
        echo "The tool has stopped."
    }

    steps
    code=$?
    if [ -n "$TEE_PID" ]; then     # let tee write the last lines before the script ends
        exec >&3 2>&4
        c=0
        while kill -0 "$TEE_PID" 2>/dev/null && [ "$c" -lt 30 ]; do
            sleep 0.1
            c=$((c + 1))
        done
    fi
    return "$code"
}

main "$@"; exit $?
