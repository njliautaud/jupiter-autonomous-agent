# shellcheck shell=bash
# Source me from any bash script in this kit:  . "$(dirname "$0")/agent_env.sh"
# Resolves AGENT_HOME (env, else the parent of this bin/ directory) and exports config/agent.env values that
# are not already set in the environment. Never echoes secret values.
: "${AGENT_HOME:=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)}"
export AGENT_HOME
_agent_env_file="$AGENT_HOME/config/agent.env"
if [ -r "$_agent_env_file" ]; then
  while IFS= read -r _l || [ -n "$_l" ]; do
    _l="${_l#export }"
    case "$_l" in ''|'#'*) continue ;; *=*) ;; *) continue ;; esac
    _k="${_l%%=*}"; _v="${_l#*=}"
    _k="$(printf '%s' "$_k" | tr -d '[:space:]')"
    case "$_k" in ''|*[!A-Za-z0-9_]*) continue ;; esac
    case "$_v" in \"*\") _v="${_v#\"}"; _v="${_v%\"}" ;; \'*\') _v="${_v#\'}"; _v="${_v%\'}" ;; *) _v="${_v%% #*}" ;; esac
    if [ -z "${!_k:-}" ]; then export "$_k=$_v"; fi
  done < "$_agent_env_file"
fi
unset _l _k _v _agent_env_file
mkdir -p "$AGENT_HOME/state" "$AGENT_HOME/logs" 2>/dev/null || true
