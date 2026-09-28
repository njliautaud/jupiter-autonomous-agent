#!/usr/bin/env bash
# Claude Code Remote Control server: drive this machine's Claude from the Claude
# mobile app / claude.ai/code (https://code.claude.com/docs/en/remote-control).
# Server mode exits after a while without network -> this loop restarts it.
# Pause without killing the loop: touch $AGENT_HOME/state/RC_STOP
# RC_PERMISSION_MODE defaults to "default" (asks before risky tools). Setting it to
# bypassPermissions gives the phone the same trust as the web terminal — your call.
. "$(dirname "$(readlink -f "$0")")/../../bin/agent_env.sh"
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"
unset ANTHROPIC_API_KEY   # Remote Control needs the subscription login, not an API key
cd "$AGENT_HOME" || exit 1
trap '' INT
while true; do
  if [ -f "$AGENT_HOME/state/RC_STOP" ]; then sleep 60; continue; fi
  echo "$(date '+%F %T') starting remote-control" >> "$AGENT_HOME/logs/rc-loop.log"
  claude remote-control --name "${RC_NAME:-${AGENT_NAME:-agent}}" --spawn same-dir \
    --capacity "${RC_CAPACITY:-4}" --permission-mode "${RC_PERMISSION_MODE:-default}"
  echo "$(date '+%F %T') remote-control exited rc=$?; restarting in 15s" >> "$AGENT_HOME/logs/rc-loop.log"
  sleep 15
done
