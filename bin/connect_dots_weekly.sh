#!/usr/bin/env bash
# connect_dots_weekly.sh [--dry-run] [--force]
# Headless weekly run of the connect-dots skill. Only when the usage tier is GREEN
# (or --force) and the TOKEN_SAVER brake is off. Bounded: sonnet, read-only tools,
# --max-turns 15. The skill itself appends to memory/_IDEAS.md and logs to the feed.
. "$(dirname "$(readlink -f "$0")")/agent_env.sh"
DRY=0; FORCE=0
for a in "$@"; do case "$a" in --dry-run) DRY=1 ;; --force) FORCE=1 ;; esac; done
TIER=$(python3 -c "import json;print(json.load(open('$AGENT_HOME/state/usage_tier.json')).get('tier','UNKNOWN'))" 2>/dev/null || echo UNKNOWN)
if [ "$FORCE" != 1 ] && { [ "$TIER" != GREEN ] || [ -e "$AGENT_HOME/state/TOKEN_SAVER" ]; }; then
  echo "connect-dots skipped (tier $TIER)"; exit 0
fi
CMD=(claude -p "/connect-dots" --model sonnet --max-turns 15 --allowedTools "Read,Grep,Glob,Bash($AGENT_HOME/bin/mem:*),Edit($AGENT_HOME/memory/_IDEAS.md),Write($AGENT_HOME/memory/_IDEAS.md)")
if [ "$DRY" = 1 ]; then printf '%q ' "${CMD[@]}"; echo; exit 0; fi
cd "$AGENT_HOME" && timeout 900 "${CMD[@]}" >> "$AGENT_HOME/logs/connect_dots.log" 2>&1
