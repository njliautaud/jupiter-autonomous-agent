#!/usr/bin/env python3
"""Claude Code hook that enforces the shared usage tier in every local session.

  usage_hook.py prompt   (UserPromptSubmit)
      Prints ONE line of context only when the tier is not GREEN (keeps the prompt
      prefix small on normal days). Also nags a session whose context has grown past
      USAGE_CTX_NAG_TOKENS (default 200k) to /compact or /clear.
  usage_hook.py pretool  (PreToolUse, matcher "Agent|Task")
      In RED, denies spawning new subagents.

Protected directories (USAGE_PROTECTED_DIRS, colon-separated absolute paths) are
exempt from the subagent block and get a softer line: use this for anything
time-critical (e.g. an ops bot that must never be delayed by budget text).

Never fails loudly: any error -> exit 0 with no output.
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentlib as A


def protected(cwd):
    dirs = [os.path.realpath(os.path.expanduser(p)) for p in (A.env("USAGE_PROTECTED_DIRS", "") or "").split(":") if p.strip()]
    rc = os.path.realpath(cwd or ".")
    return any(rc == d or rc.startswith(d + os.sep) for d in dirs)


def when(ts):
    return time.strftime("%a %H:%M", time.localtime(ts)) if ts else "?"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"
    try:
        ev = json.load(sys.stdin)
    except Exception:
        ev = {}
    cwd = ev.get("cwd") or os.getcwd()
    try:
        t = json.load(open(os.path.join(A.STATE, "usage_tier.json")))
    except Exception:
        t = None
    fresh = bool(t) and time.time() - t.get("ts", 0) <= 3600   # tier computer dead -> ignore
    tier = t.get("tier") if fresh else None
    line = ""
    if fresh:
        line = (f"USAGE {tier} (shared plan budget): 5h {t.get('five_hour_pct')}% resets {when(t.get('five_hour_reset'))}, "
                f"7d {t.get('seven_day_pct')}% resets {when(t.get('seven_day_reset'))} - {'; '.join(t.get('reasons', []))}.")
    prot = protected(cwd)

    if mode == "prompt":
        out = []
        sid = "".join(c for c in str(ev.get("session_id", "")) if c.isalnum() or c in "-_")[:80]
        limit = A.env_int("USAGE_CTX_NAG_TOKENS", 200000)
        try:
            c = json.load(open(os.path.join(A.STATE, "ctx", f"{sid}.json")))
            if not prot and c["tokens"] >= limit and time.time() - c["ts"] < 3600:
                out.append(f"CONTEXT {c['tokens'] // 1000}k tokens: every turn re-reads all of it. "
                           "If the task is done, say so and suggest /clear; mid-task, /compact at the next natural break.")
        except Exception:
            pass
        if tier in ("YELLOW", "RED"):
            if prot:
                out.append(line + " Time-critical work here ALWAYS proceeds; only skip optional extras.")
            elif tier == "YELLOW":
                out.append(line + " Be lean: no new expensive subagents, trim tool output, /compact if large, defer low-priority work.")
            else:
                out.append(line + " Critical work only: no subagents, finish or park the current task, say what was deferred and when the window resets.")
        if out:
            print("\n".join(out))
    elif mode == "pretool":
        if tier == "RED" and not prot:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": line + " New subagents are blocked until the tier drops. Do the step inline or defer it."}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
