#!/usr/bin/env bash
# Isolated sandbox for poking at `quota-monitor setup` / `uninstall` / etc.
# without touching your real ~/.quota-monitor, ~/.claude, or installed wheel.
#
# Usage:
#   scripts/sandbox.sh enter   # create + drop into a sandboxed sub-shell
#   scripts/sandbox.sh clean   # tear the sandbox down
#   scripts/sandbox.sh reset   # clean + enter
#
# What's isolated:
#   - $HOME redirected to $QM_SANDBOX_DIR (default ~/.qm-sandbox)
#   - so ~/.quota-monitor/, ~/Library/LaunchAgents/, ~/.claude/, ~/.codex/,
#     and the CF relay workdir all live inside the sandbox
#   - quota-monitor is installed editable from this repo into a sandbox venv,
#     so source edits show up immediately
#
# What's NOT isolated (and why):
#   - launchd is per-user, not per-HOME. If you pick "launchagent" in the
#     schedule step, the plist content uses the same hardcoded label as your
#     real install — they will collide. Pick "skip" unless you've first run
#     `quota-monitor uninstall` outside the sandbox.
#   - `wrangler` talks to your real Cloudflare account. Avoid CF mode here
#     unless you have a throwaway account configured.
#   - `osascript` macOS notifications fire to your real Notification Center.
#     Harmless, just noisy.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SANDBOX="${QM_SANDBOX_DIR:-$HOME/.qm-sandbox}"

cmd_enter() {
    mkdir -p "$SANDBOX"

    # Seed an empty ~/.claude/settings.json so the statusline-install path
    # has a file to wrap. Otherwise install_wrapper has nothing to back up.
    mkdir -p "$SANDBOX/.claude"
    if [ ! -f "$SANDBOX/.claude/settings.json" ]; then
        printf '{}\n' >"$SANDBOX/.claude/settings.json"
    fi
    mkdir -p "$SANDBOX/Library/LaunchAgents"

    if [ ! -x "$SANDBOX/.venv/bin/python" ]; then
        echo "==> creating sandbox venv"
        python3 -m venv "$SANDBOX/.venv"
        "$SANDBOX/.venv/bin/pip" install --quiet --upgrade pip
    fi
    echo "==> installing quota-monitor (editable) from $REPO_ROOT"
    "$SANDBOX/.venv/bin/pip" install --quiet -e "$REPO_ROOT"

    cat <<EOF

🏖  QuotaMonitor sandbox ready @ $SANDBOX
   Code:   $REPO_ROOT  (editable, edits hot-reload)
   HOME:   $SANDBOX
   Try:    quota-monitor setup
           quota-monitor status
           quota-monitor notify-test --backend macos_native
           quota-monitor uninstall
   Notes:  pick "skip" for the LaunchAgent step to avoid colliding
           with your real install; skip CF mode unless on a throwaway
           Cloudflare account.
   Exit:   Ctrl-D (or 'exit') to leave the sub-shell.

EOF

    exec env -i \
        HOME="$SANDBOX" \
        USER="${USER:-}" \
        LOGNAME="${LOGNAME:-${USER:-}}" \
        SHELL="${SHELL:-/bin/zsh}" \
        TERM="${TERM:-xterm-256color}" \
        LANG="${LANG:-en_US.UTF-8}" \
        VIRTUAL_ENV="$SANDBOX/.venv" \
        PATH="$SANDBOX/.venv/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
        PS1='(qm-sandbox) %~ %# ' \
        QM_SANDBOX=1 \
        "${SHELL:-/bin/zsh}" -i
}

cmd_clean() {
    if [ ! -d "$SANDBOX" ]; then
        echo "Nothing at $SANDBOX"
        return 0
    fi
    # Best-effort: unload any plist the sandbox left behind. Targets the
    # sandbox plist path explicitly so we don't touch the real LaunchAgent
    # if labels happen to collide.
    local plist="$SANDBOX/Library/LaunchAgents/io.github.frank.quotamonitor.plist"
    if [ -f "$plist" ]; then
        launchctl unload "$plist" 2>/dev/null || true
    fi
    rm -rf "$SANDBOX"
    echo "Removed $SANDBOX"
}

case "${1:-enter}" in
    enter) cmd_enter ;;
    clean) cmd_clean ;;
    reset) cmd_clean; cmd_enter ;;
    -h|--help|help)
        sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
        ;;
    *)
        echo "Usage: $0 {enter|clean|reset}" >&2
        exit 2
        ;;
esac
