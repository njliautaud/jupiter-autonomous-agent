#!/usr/bin/env python3
"""Claude Code statusLine command + account-usage SENSOR.

Every interactive Claude Code session pipes its status JSON into this script.
When the payload carries `rate_limits` (subscription plans), we record the REAL
account-wide 5-hour / 7-day usage percentages into a shared ledger:

    $AGENT_HOME/state/usage_ledger.json

usage_tier.py turns that ledger into GREEN / YELLOW / RED for every agent on the
box. We also record each session's context size so usage_hook.py can nag long
sessions to /compact. Output: one short status line, e.g. "5h 12% · 7d 40% · ctx 31% · GREEN".
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentlib as A

A.ensure_dirs()
LEDGER = os.path.join(A.STATE, "usage_ledger.json")

try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
now = time.time()
rl = d.get("rate_limits") or {}
fh, sd = rl.get("five_hour") or {}, rl.get("seven_day") or {}
f_pct, s_pct = fh.get("used_percentage"), sd.get("used_percentage")

if f_pct is not None or s_pct is not None:
    try:
        old = json.load(open(LEDGER))
    except Exception:
        old = {}
    # write at most once a minute unless the 5h number moved
    if now - old.get("ts", 0) >= 60 or f_pct != old.get("five_hour_pct"):
        try:
            A.atomic_json(LEDGER, {
                "ts": now,
                "five_hour_pct": f_pct, "five_hour_reset": fh.get("resets_at"),
                "seven_day_pct": s_pct, "seven_day_reset": sd.get("resets_at"),
            })
        except OSError:
            pass

cw = d.get("context_window") or {}
sid = d.get("session_id")
if sid and cw.get("total_input_tokens"):
    cdir = os.path.join(A.STATE, "ctx")
    try:
        os.makedirs(cdir, exist_ok=True)
        safe = "".join(c for c in str(sid) if c.isalnum() or c in "-_")[:80]
        A.atomic_json(os.path.join(cdir, f"{safe}.json"), {"ts": now, "tokens": cw["total_input_tokens"]})
    except OSError:
        pass

tier = "?"
try:
    tier = json.load(open(os.path.join(A.STATE, "usage_tier.json"))).get("tier", "?")
except Exception:
    pass
parts = []
if f_pct is not None:
    parts.append(f"5h {f_pct:.0f}%")
if s_pct is not None:
    parts.append(f"7d {s_pct:.0f}%")
if cw.get("used_percentage") is not None:
    parts.append(f"ctx {cw['used_percentage']:.0f}%")
parts.append(tier)
print(" · ".join(parts))
