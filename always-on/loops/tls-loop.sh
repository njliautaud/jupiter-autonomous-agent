#!/usr/bin/env bash
. "$(dirname "$(readlink -f "$0")")/../../bin/agent_env.sh"
[ -f "$AGENT_HOME/state/tls/server.crt" ] || bash "$AGENT_HOME/always-on/make_cert.sh"
while true; do
  python3 "$AGENT_HOME/always-on/tls_proxy.py" >> "$AGENT_HOME/logs/tls_proxy.log" 2>&1
  sleep 2
done
