#!/usr/bin/env bash
# Writes a desktop entry that starts the nesting tool (start.sh) without a terminal.
# Run it once, and again if the repo folder moves.

die() { echo "$*" >&2; exit 1; }

# Value of a plain string key (Path=): only the general escape applies: \ -> \\
escape_string() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g'
}

# Value of Exec= inside double quotes: the quoting rules first (\ " ` $ get a
# backslash), then the general string escape (every \ doubled), then % -> %%.
# shellcheck disable=SC2016  # the backtick and $ in the sed patterns are literal
escape_exec_arg() {
    printf '%s' "$1" | sed \
        -e 's/\\/\\\\\\\\/g' \
        -e 's/"/\\\\"/g' \
        -e 's/`/\\\\`/g' \
        -e 's/\$/\\\\$/g' \
        -e 's/%/%%/g'
}

main() {
    local repo start data apps desktop entry
    repo=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P) || die "Cannot find the folder of this script."
    start="$repo/start.sh"
    [ -f "$start" ] || die "start.sh is not next to install-launcher.sh ($repo)."
    case "$repo" in
        *$'\n'*) die "The folder name contains a newline; move the tool to a folder without one." ;;
    esac

    data="${XDG_DATA_HOME:-$HOME/.local/share}"
    apps="$data/applications"
    mkdir -p "$apps" || die "Cannot create $apps"

    entry="[Desktop Entry]
Type=Application
Version=1.0
Name=Nesting tool
Comment=Plan the blanks and write the programs (stops by itself when the page is closed)
Exec=/bin/bash \"$(escape_exec_arg "$start")\"
Path=$(escape_string "$repo")
Icon=applications-engineering
Terminal=false
Categories=Utility;
"
    printf '%s' "$entry" > "$apps/nesting-tool.desktop" || die "Cannot write $apps/nesting-tool.desktop"
    chmod 755 "$apps/nesting-tool.desktop"
    echo "Wrote $apps/nesting-tool.desktop"

    desktop=""
    if command -v xdg-user-dir >/dev/null 2>&1; then
        desktop=$(xdg-user-dir DESKTOP 2>/dev/null)
        # It answers the home folder itself when no desktop folder is set up.
        [ "${desktop%/}" = "${HOME%/}" ] && desktop=""
        [ -d "$desktop" ] || desktop=""
    fi
    if [ -z "$desktop" ] && [ -d "$HOME/Desktop" ]; then
        desktop="$HOME/Desktop"
    fi
    if [ -n "$desktop" ]; then
        printf '%s' "$entry" > "$desktop/nesting-tool.desktop" || die "Cannot write $desktop/nesting-tool.desktop"
        chmod 755 "$desktop/nesting-tool.desktop"
        echo "Wrote $desktop/nesting-tool.desktop"
        if ! { command -v gio >/dev/null 2>&1 &&
               gio set "$desktop/nesting-tool.desktop" metadata::trusted true >/dev/null 2>&1; }; then
            echo "If the desktop icon does not start, right-click it and choose Allow Launching."
        fi
    else
        echo "No desktop folder found; skipped the desktop icon."
    fi

    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$apps" >/dev/null 2>&1 || true
    fi
    echo "Run it again if the folder moves."
}

main "$@"
