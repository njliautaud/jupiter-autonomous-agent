#!/usr/bin/env bash
# start.sh [--only NAME] [--list] — create every MISSING tmux supervisor session.
# Idempotent: existing sessions are never touched, so it is safe from cron/@reboot
# and from the watchdog. Each session runs a loop script that restarts its service.
#   agent    the interactive Claude Code session you attach to (phone or desktop)
#   mem      shared-memory HTTP API (bin/mem_server.py)
#   ttyd     web terminal attached to the `agent` session         (TTYD_ENABLE=1)
#   tls      HTTPS front for ttyd (secure context for clipboard)  (TLS_ENABLE=1)
#   rc       Claude Code Remote Control server                    (RC_ENABLE=1)
#   desktop  virtual desktop: Xvfb + x11vnc + noVNC                (DESKTOP_ENABLE=1)
. "$(dirname "$(readlink -f "$0")")/../bin/agent_env.sh"
L="$AGENT_HOME/always-on/loops"
ONLY=""
case "${1:-}" in
  --only) ONLY="${2:-}" ;;
  --list) echo "agent mem ttyd tls rc desktop"; exit 0 ;;
esac
command -v tmux >/dev/null || { echo "tmux not installed"; exit 1; }
want() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }
up() {  # up NAME ENABLED SCRIPT
  local name="$1" enabled="$2" script="$3"
  want "$name" || return 0
  [ "$enabled" = "1" ] || { [ -n "$ONLY" ] && echo "$name disabled in config/agent.env"; return 0; }
  if tmux has-session -t "$name" 2>/dev/null; then echo "$name: running"; return 0; fi
  tmux new-session -d -s "$name" -x 220 -y 50 "bash '$L/$script'" && echo "$name: started"
}
up agent   "${AGENT_ENABLE:-1}"    agent-loop.sh
up mem     "${MEM_ENABLE:-1}"      mem-loop.sh
up ttyd    "${TTYD_ENABLE:-0}"     ttyd-loop.sh
up tls     "${TLS_ENABLE:-0}"      tls-loop.sh
up rc      "${RC_ENABLE:-0}"       rc-loop.sh
up desktop "${DESKTOP_ENABLE:-0}"  desktop-loop.sh
