#!/usr/bin/env bash
# watchdog.sh — cron every 5 min. Checks each ENABLED service with a real HTTP probe
# (any HTTP status, e.g. 401/404, counts as alive; only "no answer" is down), retries
# once, and recovers by running start.sh (which only creates missing sessions) or by
# restarting the one wedged session. Quiet when healthy.
#
# Lesson baked in: never probe with `ss | grep -q` under `set -o pipefail` — grep exits
# early, ss dies of SIGPIPE, the pipeline "fails" and you get endless false recoveries.
. "$(dirname "$(readlink -f "$0")")/../bin/agent_env.sh"
LOG="$AGENT_HOME/logs/watchdog.log"
B="${BIND_ADDR:-127.0.0.1}"
ts() { date '+%F %T'; }
probe() { local c; c=$(curl -sk -o /dev/null -w '%{http_code}' -m 6 "$1" 2>/dev/null); [ -n "$c" ] && [ "$c" != "000" ]; }
declare -A URL
[ "${MEM_ENABLE:-1}" = 1 ]     && URL[mem]="http://${MEM_BIND:-127.0.0.1}:${MEM_PORT:-7692}/health"
[ "${TTYD_ENABLE:-0}" = 1 ]    && URL[ttyd]="http://$B:${TTYD_PORT:-7681}/"
[ "${TLS_ENABLE:-0}" = 1 ]     && URL[tls]="https://$B:${TLS_PORT:-7683}/"
[ "${DESKTOP_ENABLE:-0}" = 1 ] && URL[desktop]="http://$B:${NOVNC_PORT:-7682}/vnc.html"
bash "$AGENT_HOME/always-on/start.sh" >/dev/null 2>&1   # recreate any missing session
for name in "${!URL[@]}"; do
  probe "${URL[$name]}" && continue
  sleep 3; probe "${URL[$name]}" && continue
  echo "$(ts) $name not answering -> restarting its session" >> "$LOG"
  tmux kill-session -t "$name" 2>/dev/null
  bash "$AGENT_HOME/always-on/start.sh" --only "$name" >> "$LOG" 2>&1
  sleep 5
  if probe "${URL[$name]}"; then echo "$(ts) $name recovered" >> "$LOG"
  else echo "$(ts) $name STILL DOWN" >> "$LOG"
       "$AGENT_HOME/bin/notify" --key "watchdog-$name" "Heads up: the $name service is down and did not restart. Looking into it." >/dev/null 2>&1
  fi
done
exit 0
