#!/usr/bin/env bash
# Web terminal (https://github.com/tsl0922/ttyd) attached to the `agent` tmux session.
# Binds BIND_ADDR only (your VPN/tailnet address or 127.0.0.1) — never a public IP.
# Basic auth from TTYD_CREDENTIAL (user:password). Note: ttyd takes it on the command
# line, so it is visible to other local users in `ps`; run this on a single-user box.
. "$(dirname "$(readlink -f "$0")")/../../bin/agent_env.sh"
export PATH="$HOME/.local/bin:$PATH"
[ -n "${TTYD_CREDENTIAL:-}" ] || { echo "TTYD_CREDENTIAL not set - refusing to start an unauthenticated terminal"; sleep 60; exit 1; }
while true; do
  ttyd -p "${TTYD_PORT:-7681}" -i "${BIND_ADDR:-127.0.0.1}" -W -c "$TTYD_CREDENTIAL" \
       -t fontSize=16 -t titleFixed="${AGENT_NAME:-agent}" tmux attach -t agent
  sleep 2
done
