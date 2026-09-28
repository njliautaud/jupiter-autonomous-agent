#!/usr/bin/env bash
# usage_gate.sh <critical|normal|low> [label]
# Shared budget gate for scheduled jobs. Put it in front of anything that wakes Claude:
#     usage_gate.sh low "morning briefing" && claude -p ...
# exit 0 = run, exit 1 = skip.
#   critical -> ALWAYS runs (safety / time-critical paths are never gated)
#   normal   -> skipped only in RED
#   low      -> skipped in YELLOW or RED
#   unknown priority label -> treated as normal
# A missing, unreadable or stale (>2h) tier file counts as UNKNOWN -> everything runs
# (never block work on missing data). Skips are logged to $AGENT_HOME/logs/usage_gate.log.
. "$(dirname "$(readlink -f "$0")")/agent_env.sh"
PRIO="${1:-normal}"
LABEL="${2:-}"
[ "$PRIO" = "critical" ] && exit 0
TIER=$(python3 - "$AGENT_HOME/state/usage_tier.json" 2>/dev/null <<'PY'
import json, sys, time
try:
    d = json.load(open(sys.argv[1]))
    t = str(d.get("tier", "UNKNOWN")).upper()
    if time.time() - float(d.get("ts", 0)) > 7200:
        t = "UNKNOWN"
    print(t if t in ("GREEN", "YELLOW", "RED") else "UNKNOWN")
except Exception:
    print("UNKNOWN")
PY
)
[ -z "$TIER" ] && TIER=UNKNOWN
SKIP=0
case "$PRIO" in
  low) { [ "$TIER" = "RED" ] || [ "$TIER" = "YELLOW" ]; } && SKIP=1 ;;
  *)   [ "$TIER" = "RED" ] && SKIP=1 ;;
esac
if [ "$SKIP" = "1" ]; then
  echo "[$(date '+%F %T')] SKIP prio=$PRIO tier=$TIER ${LABEL:0:100}" >> "$AGENT_HOME/logs/usage_gate.log"
  exit 1
fi
exit 0
