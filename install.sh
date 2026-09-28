#!/usr/bin/env bash
# install.sh — install the always-on Claude Code agent starter kit.
#
#   ./install.sh [--no-system] [--no-cron] [--no-hooks] [--start] [-h]
#
#   AGENT_HOME   install target (default ~/agent). Clone this repo somewhere else
#                (e.g. ~/src/jupiter-autonomous-agent) and install INTO AGENT_HOME.
#   --no-system  only write files under AGENT_HOME: no ~/.claude changes, no crontab,
#                no symlink, no tmux (use this to try it out or for tests)
#   --no-cron    skip the crontab block          --no-hooks  skip ~/.claude changes
#   --start      start the tmux supervisors now (always-on/start.sh)
#
# Idempotent and non-destructive: re-running upgrades the kit files, keeps your
# config/agent.env, memory and state, never duplicates hooks or cron lines, and
# backs up every file outside AGENT_HOME before changing it. It never uses sudo.
set -euo pipefail
SRC="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
AGENT_HOME="${AGENT_HOME:-$HOME/agent}"
AGENT_HOME="$(mkdir -p "$AGENT_HOME" && cd "$AGENT_HOME" && pwd)"
export AGENT_HOME
SYSTEM=1; CRON=1; HOOKS=1; START=0
for a in "$@"; do
  case "$a" in
    --no-system) SYSTEM=0 ;;
    --no-cron) CRON=0 ;;
    --no-hooks) HOOKS=0 ;;
    --start) START=1 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "unknown option: $a"; exit 2 ;;
  esac
done
[ "$SYSTEM" = 0 ] && { CRON=0; HOOKS=0; START=0; }
say() { printf '  %s\n' "$*"; }
echo "Installing into $AGENT_HOME"

# ---- 1. prerequisites (warn, never install system packages) -------------------
command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' || { echo "python3 >= 3.8 required"; exit 1; }
python3 -c 'import sqlite3; c=sqlite3.connect(":memory:"); c.execute("create virtual table t using fts5(x)")' 2>/dev/null \
  || say "note: SQLite FTS5 unavailable -> mem search falls back to a simple scan"
command -v claude >/dev/null || say "note: Claude Code CLI not found on PATH (https://www.anthropic.com/claude-code)"
command -v tmux >/dev/null || say "note: tmux not found (needed for the always-on supervisors)"

# ---- 2. kit files ------------------------------------------------------------------
mkdir -p "$AGENT_HOME"/{bin,always-on/loops,config,evals,claude,docs,memory/briefs,state,logs,work}
chmod 700 "$AGENT_HOME/state" "$AGENT_HOME/config"
render() {  # render SRC_FILE DEST_FILE : copy with {{AGENT_HOME}} substituted
  mkdir -p "$(dirname "$2")"
  sed "s#{{AGENT_HOME}}#$AGENT_HOME#g" "$1" > "$2.tmp.$$" && mv "$2.tmp.$$" "$2"
}
if [ "$SRC" != "$AGENT_HOME" ]; then
  cp -a "$SRC/bin/." "$AGENT_HOME/bin/"
  cp -a "$SRC/always-on/." "$AGENT_HOME/always-on/"
  cp -a "$SRC/docs/." "$AGENT_HOME/docs/"
  cp "$SRC/config/"*.example* "$AGENT_HOME/config/"
  (cd "$SRC" && find evals claude templates -type f) | while read -r f; do
    case "$f" in *.md) render "$SRC/$f" "$AGENT_HOME/$f" ;; *) mkdir -p "$AGENT_HOME/$(dirname "$f")"; cp -a "$SRC/$f" "$AGENT_HOME/$f" ;; esac
  done
fi
chmod +x "$AGENT_HOME"/bin/* "$AGENT_HOME"/always-on/*.sh "$AGENT_HOME"/always-on/loops/*.sh "$AGENT_HOME"/evals/pulse/*.py 2>/dev/null || true
say "kit files: ok"

# ---- 3. secrets file (created once, chmod 600, never overwritten) --------------------
ENVF="$AGENT_HOME/config/agent.env"
umask 077
[ -f "$ENVF" ] || { cp "$SRC/config/agent.env.example" "$ENVF"; say "created config/agent.env from the example"; }
chmod 600 "$ENVF"
python3 - "$ENVF" <<'PY'
import re, secrets, sys
p = sys.argv[1]; s = open(p).read(); changed = []
def fill(key, val):
    global s
    if re.search(rf"^{key}=\s*(#.*)?$", s, re.M):
        s = re.sub(rf"^{key}=.*$", f"{key}={val}", s, count=1, flags=re.M); changed.append(key)
fill("MEM_TOKEN", secrets.token_urlsafe(32))
fill("TTYD_CREDENTIAL", "agent:" + secrets.token_urlsafe(18))
open(p, "w").write(s)
if changed: print("  generated: " + ", ".join(changed) + " (stored only in config/agent.env)")
PY
umask 022

# ---- 4. memory store + agent instructions ---------------------------------------------
[ -f "$AGENT_HOME/memory/MEMORY.md" ] || printf '# Memory index\n\nOne line per memory. Maintained additively by mem / mem_server.\n\n' > "$AGENT_HOME/memory/MEMORY.md"
[ -f "$AGENT_HOME/memory/_PROJECTS.json" ] || cp "$SRC/config/projects.example.json" "$AGENT_HOME/memory/_PROJECTS.json"
if [ ! -f "$AGENT_HOME/CLAUDE.md" ]; then render "$SRC/templates/CLAUDE.md" "$AGENT_HOME/CLAUDE.md"; say "created CLAUDE.md from the template (edit the HARD BOUNDARIES section)"; fi
[ -f "$AGENT_HOME/NOTES.md" ] || printf '# NOTES — live project state\n\n' > "$AGENT_HOME/NOTES.md"
touch "$AGENT_HOME/ACTIONS.log"
python3 "$AGENT_HOME/bin/usage_tier.py" > /dev/null   # seed state/usage_tier.json
say "memory + state: ok"

# ---- 5. Claude Code hooks, agents, skills (user scope) -------------------------------
backup_copy() {  # backup_copy SRC DEST : install a file, backing up a different existing one
  if [ -f "$2" ] && ! cmp -s "$1" "$2"; then cp -a "$2" "$2.bak.$(date +%s)"; fi
  mkdir -p "$(dirname "$2")"; cp "$1" "$2"
}
if [ "$HOOKS" = 1 ]; then
  python3 "$AGENT_HOME/bin/install_hooks.py" --settings "${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
  (cd "$AGENT_HOME/claude" && find agents skills -type f) | while read -r f; do backup_copy "$AGENT_HOME/claude/$f" "$HOME/.claude/$f"; done
  mkdir -p "$HOME/.local/bin" && ln -sf "$AGENT_HOME/bin/mem" "$HOME/.local/bin/mem"
  say "hooks, agents, skills: installed in ~/.claude (mem linked into ~/.local/bin)"
fi

# ---- 6. crontab block (flock + backup + marker-delimited, idempotent) ---------------
if [ "$CRON" = 1 ] && command -v crontab >/dev/null; then
  (
    flock -w 30 9
    cur="$(crontab -l 2>/dev/null || true)"
    printf '%s\n' "$cur" > "$AGENT_HOME/state/crontab.bak.$(date +%s)"
    block="$(sed "s#__AGENT_HOME__#$AGENT_HOME#g" "$SRC/config/crontab.example" | sed -n '/^# >>> jupiter-agent >>>/,/^# <<< jupiter-agent <<</p')"
    rest="$(printf '%s\n' "$cur" | sed '/^# >>> jupiter-agent >>>/,/^# <<< jupiter-agent <<</d')"
    printf '%s\n%s\n' "$rest" "$block" | sed '/./,$!d' | crontab -
  ) 9> "$AGENT_HOME/state/crontab.lock"
  say "crontab: jupiter-agent block installed (previous crontab backed up in state/)"
fi

# ---- 7. start services ------------------------------------------------------------------
[ "$START" = 1 ] && bash "$AGENT_HOME/always-on/start.sh"

cat <<EOF

Done. Next:
  1. Edit $AGENT_HOME/config/agent.env (BIND_ADDR, NOTIFY_WEBHOOK_URL, which services to enable).
  2. Edit the HARD BOUNDARIES section of $AGENT_HOME/CLAUDE.md.
  3. Try:  $AGENT_HOME/bin/mem write hello --desc "first memory" --body "it works"; $AGENT_HOME/bin/mem search hello
  4. Start: $AGENT_HOME/always-on/start.sh   (then: tmux attach -t agent)
  Docs: $AGENT_HOME/docs/  (SECURITY.md first)
EOF
