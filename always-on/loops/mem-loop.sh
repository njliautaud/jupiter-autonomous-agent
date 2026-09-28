#!/usr/bin/env bash
. "$(dirname "$(readlink -f "$0")")/../../bin/agent_env.sh"
while true; do
  python3 "$AGENT_HOME/bin/mem_server.py" >> "$AGENT_HOME/logs/mem_server.log" 2>&1
  sleep 5
done
