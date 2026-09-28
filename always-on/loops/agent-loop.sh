#!/usr/bin/env bash
# The main interactive Claude Code session. Ctrl+C never kills the loop; if Claude
# exits it restarts in 2 s. Start fresh each time (use /resume to pick an old one up):
# long-lived sessions are the #1 cost driver.
. "$(dirname "$(readlink -f "$0")")/../../bin/agent_env.sh"
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"
cd "$AGENT_HOME" || exit 1
trap '' INT
while true; do
  claude ${AGENT_CLAUDE_ARGS:-}
  sleep 2
done
