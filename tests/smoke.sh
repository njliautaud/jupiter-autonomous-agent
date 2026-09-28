#!/usr/bin/env bash
# tests/smoke.sh — offline smoke test. Installs into a throw-away AGENT_HOME with
# --no-system (no ~/.claude, crontab or tmux changes) and exercises every piece that
# does not need a model call. Exit 0 = all passed.
set -uo pipefail
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/agent-smoke.XXXXXX")"
export AGENT_HOME="$T/agent"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ok   $*"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL $*"; }
check() { local name="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$name"; else bad "$name"; fi; }
cleanup() { [ -n "${SRV:-}" ] && kill "$SRV" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT

echo "== syntax"
while IFS= read -r f; do
  case "$(head -1 "$f")" in
    *python*) check "py_compile ${f#$REPO/}" python3 -c "import py_compile,sys; py_compile.compile(sys.argv[1], cfile='$T/x.pyc', doraise=True)" "$f" ;;
    *bash*|*sh) check "bash -n ${f#$REPO/}" bash -n "$f" ;;
  esac
done < <(find "$REPO" -type f \( -name '*.sh' -o -name '*.py' -o -path '*/bin/*' \) -not -path '*/.git/*' | sort)
for f in "$REPO"/evals/pulse/scenarios/*.json "$REPO"/config/*.json; do check "json ${f#$REPO/}" python3 -m json.tool "$f"; done

echo "== install (--no-system) twice"
check "install #1" bash "$REPO/install.sh" --no-system
check "install #2 (idempotent)" bash "$REPO/install.sh" --no-system
check "agent.env is chmod 600" test "$(stat -c %a "$AGENT_HOME/config/agent.env")" = 600
check "MEM_TOKEN generated" grep -Eq '^MEM_TOKEN=.{20,}' "$AGENT_HOME/config/agent.env"
check "CLAUDE.md rendered" grep -q "$AGENT_HOME" "$AGENT_HOME/CLAUDE.md"
check "no {{placeholders}} left in installed md" bash -c "! grep -rl '{{AGENT_HOME}}' '$AGENT_HOME'"
B="$AGENT_HOME/bin"

echo "== hooks installer (temp settings file)"
S="$T/settings.json"; echo '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo keep-me"}]}]}}' > "$S"
python3 "$B/install_hooks.py" --settings "$S" >/dev/null; python3 "$B/install_hooks.py" --settings "$S" >/dev/null
check "hooks installed once, foreign hook kept" python3 - "$S" <<'PY'
import json, sys
s = json.load(open(sys.argv[1])); h = s["hooks"]
assert len(h["UserPromptSubmit"]) == 1 and len(h["PreToolUse"]) == 1, h
assert h["Stop"][0]["hooks"][0]["command"] == "echo keep-me"
assert "usage_statusline.py" in s["statusLine"]["command"]
PY
python3 "$B/install_hooks.py" --settings "$S" --uninstall >/dev/null
check "uninstall leaves only the foreign hook" python3 -c "import json,sys; s=json.load(open('$S')); assert list(s['hooks'])==['Stop'] and 'statusLine' not in s"

echo "== usage tier"
NOW=$(date +%s)
echo "{\"session_id\":\"s1\",\"rate_limits\":{\"five_hour\":{\"used_percentage\":92,\"resets_at\":$((NOW+3600))},\"seven_day\":{\"used_percentage\":30,\"resets_at\":$((NOW+500000))}},\"context_window\":{\"total_input_tokens\":250000,\"used_percentage\":60}}" \
  | python3 "$B/usage_statusline.py" > "$T/sl.txt"
check "statusline prints 5h %" grep -q "5h 92%" "$T/sl.txt"
check "ledger written" test -s "$AGENT_HOME/state/usage_ledger.json"
python3 "$B/usage_tier.py" > /dev/null
check "tier = RED at 5h 92%" python3 -c "import json; assert json.load(open('$AGENT_HOME/state/usage_tier.json'))['tier']=='RED'"
OUT=$(echo '{"session_id":"s1","cwd":"/tmp"}' | python3 "$B/usage_hook.py" prompt)
check "prompt hook: RED line" grep -q "USAGE RED" <<<"$OUT"
check "prompt hook: compact nag at 250k" grep -q "CONTEXT 250k" <<<"$OUT"
OUT=$(echo '{"cwd":"/tmp"}' | python3 "$B/usage_hook.py" pretool)
check "pretool hook: RED denies subagent" grep -q '"deny"' <<<"$OUT"
mkdir -p "$T/critical-bot"
OUT=$(echo "{\"cwd\":\"$T/critical-bot\"}" | USAGE_PROTECTED_DIRS="$T/critical-bot" python3 "$B/usage_hook.py" pretool)
check "pretool hook: protected dir exempt" test -z "$OUT"
check "gate: critical runs in RED" "$B/usage_gate.sh" critical t
check "gate: normal skipped in RED" bash -c "! '$B/usage_gate.sh' normal t"
check "gate: low skipped in RED" bash -c "! '$B/usage_gate.sh' low t"
echo "{\"session_id\":\"s1\",\"rate_limits\":{\"five_hour\":{\"used_percentage\":10,\"resets_at\":$((NOW+3600))},\"seven_day\":{\"used_percentage\":5,\"resets_at\":$((NOW+500000))}}}" \
  | python3 "$B/usage_statusline.py" >/dev/null
sleep 0; python3 "$B/usage_tier.py" > /dev/null
check "tier back to GREEN" python3 -c "import json; assert json.load(open('$AGENT_HOME/state/usage_tier.json'))['tier']=='GREEN'"
OUT=$(echo '{"session_id":"none","cwd":"/tmp"}' | python3 "$B/usage_hook.py" prompt)
check "prompt hook silent in GREEN" test -z "$OUT"
check "gate: low runs in GREEN" "$B/usage_gate.sh" low t
check "tier change logged to feed" grep -q "USAGE TIER RED -> GREEN" "$AGENT_HOME/memory/_FEED.md"

echo "== memory bus"
check "mem write" bash -c "echo 'Deploys go through the staging box first; rollback with the previous tag.' | '$B/mem' write deploy-procedure --desc 'How deploys and rollbacks work' --author smoke"
check "mem search finds it (stemmed)" bash -c "'$B/mem' search deploying | grep -q deploy-procedure"
check "mem read" bash -c "'$B/mem' read deploy-procedure | grep -q rollback"
check "mem log + feed" bash -c "'$B/mem' log 'smoke test ran' --author smoke && '$B/mem' feed 5 | grep -q 'smoke test ran'"
check "index updated additively" grep -q "deploy-procedure" "$AGENT_HOME/memory/MEMORY.md"
echo '{"session_id":"abcdef123456","cwd":"/tmp","reason":"clear","hook_event_name":"SessionEnd"}' | python3 "$B/hook_session_end.py"
check "SessionEnd hook logs to feed" grep -q "session ended (reason=clear)" "$AGENT_HOME/memory/_FEED.md"
printf '%s\n' '---' 'name: orphan' 'description: an infra note never indexed' '---' '' 'see [[deploy-procedur]]' > "$AGENT_HOME/memory/orphan.md"
check "dream runs" python3 "$B/mem_dream.py"
check "dream: index sync added orphan" grep -q "orphan" "$AGENT_HOME/memory/MEMORY.md"
check "dream: near-certain link fixed" grep -q "\[\[deploy-procedure\]\]" "$AGENT_HOME/memory/orphan.md"
check "dream: brief built" bash -c "'$B/mem' brief agent-infra | grep -q orphan"

echo "== memory HTTP API"
PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
TOK=$(grep '^MEM_TOKEN=' "$AGENT_HOME/config/agent.env" | cut -d= -f2-)
MEM_PORT=$PORT python3 "$B/mem_server.py" > "$T/srv.log" 2>&1 & SRV=$!
for i in $(seq 1 30); do curl -s "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 0.2; done
check "health open" bash -c "curl -sf http://127.0.0.1:$PORT/health | grep -q '\"ok\": true'"
check "no token -> 401" test "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/list")" = 401
check "bad token -> 401" test "$(curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer nope' "http://127.0.0.1:$PORT/list")" = 401
check "POST /write with token" bash -c "curl -sf -H 'Authorization: Bearer $TOK' -d '{\"slug\":\"remote-note\",\"description\":\"from a remote agent\",\"body\":\"hello\"}' http://127.0.0.1:$PORT/write | grep -q created"
check "GET /search with token" bash -c "curl -sf -H 'Authorization: Bearer $TOK' 'http://127.0.0.1:$PORT/search?q=remote' | grep -q remote-note"
check "non-loopback bind without token refused" bash -c "! MEM_BIND=0.0.0.0 MEM_TOKEN= AGENT_HOME='$T/empty' timeout 5 python3 '$B/mem_server.py'"

echo "== script-first pulse"
export PULSE_URLS="http://127.0.0.1:$PORT/health" PULSE_INBOX_CMD="echo 3" PULSE_HEARTBEAT_H=0
check "pulse baseline" bash -c "python3 '$B/pulse_precheck.py' | grep -q baseline"
check "pulse no change -> no wake" bash -c "python3 '$B/pulse_precheck.py' | grep -q 'no change'"
kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null; SRV=""
check "site down -> critical wake (dry-run)" bash -c "python3 '$B/pulse_precheck.py' --dry-run | grep -q 'site DOWN'"
check "fail-safe on timeout" bash -c "PULSE_INBOX_CMD='sleep 5' PULSE_TIMEOUT_S=1 python3 '$B/pulse_precheck.py' --dry-run | grep -q 'fail-safe'"

echo "== notify / takeover / eval runner"
check "notify dry-run" bash -c "'$B/notify' --dry-run --key t 'hello' | grep -q 'would send'"
check "notify without webhook is a no-op" bash -c "NOTIFY_WEBHOOK_URL= '$B/notify' --key t2 'hello' | grep -q 'not set'"
check "takeover dry-run" bash -c "NOVNC_URL=https://example.invalid/vnc.html '$B/takeover' --dry-run 'test login' 2>/dev/null | grep -q 'take over'"
check "eval runner lists scenarios" bash -c "python3 '$AGENT_HOME/evals/pulse/runner.py' --list | grep -q 01_nothing_changed"

echo
echo "passed: $PASS  failed: $FAIL"
[ "$FAIL" = 0 ]
