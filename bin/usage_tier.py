#!/usr/bin/env python3
"""Tier computer: shared usage ledger -> ONE budget tier for every agent on the box.

    GREEN   normal
    YELLOW  lean: no new expensive subagents, skip low-priority scheduled work
    RED     critical work only, no subagents
    UNKNOWN no fresh reading (never blocks anything)

Writes $AGENT_HOME/state/usage_tier.json. Run from cron every 10 minutes.
On a real change between known tiers it (a) logs to the shared memory feed,
(b) refreshes the `usage-ledger` memory so remote agents can read it, and
(c) sends one rate-limited phone alert via bin/notify (if configured).

Staleness: a ledger older than 30 min means no interactive session is feeding the
status line. If the manual brake file state/TOKEN_SAVER exists -> RED. Otherwise the
last reading is carried for up to 6 h (a 5h window that has since reset counts as
0%), after which the tier is UNKNOWN.

Thresholds (env / config/agent.env):
  USAGE_5H_YELLOW=60  USAGE_5H_RED=85  USAGE_7D_YELLOW=70  USAGE_7D_RED=90
  USAGE_PACE_YELLOW=10   (7d points ahead of an even weekly pace)
"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentlib as A

A.ensure_dirs()
LEDGER = os.path.join(A.STATE, "usage_ledger.json")
OUT = os.path.join(A.STATE, "usage_tier.json")
LAST_KNOWN = os.path.join(A.STATE, "usage_tier.last_known")
WEEK = 7 * 86400
ORDER = ["GREEN", "YELLOW", "RED"]
now = time.time()

T5Y, T5R = A.env_float("USAGE_5H_YELLOW", 60), A.env_float("USAGE_5H_RED", 85)
T7Y, T7R = A.env_float("USAGE_7D_YELLOW", 70), A.env_float("USAGE_7D_RED", 90)
PACE_Y = A.env_float("USAGE_PACE_YELLOW", 10)


def compute(l):
    f, s = l.get("five_hour_pct"), l.get("seven_day_pct")
    tier, reasons, pace = "GREEN", [], None

    def bump(t, why):
        nonlocal tier
        if ORDER.index(t) > ORDER.index(tier):
            tier = t
        reasons.append(why)

    if f is not None:
        if f > T5R:
            bump("RED", f"5h {f:.0f}%")
        elif f >= T5Y:
            bump("YELLOW", f"5h {f:.0f}%")
    if s is not None:
        if s > T7R:
            bump("RED", f"7d {s:.0f}%")
        elif s > T7Y:
            bump("YELLOW", f"7d {s:.0f}%")
        reset = l.get("seven_day_reset")
        if reset:
            elapsed = max(0.0, min(1.0, 1 - (reset - now) / WEEK))
            pace = s - 100 * elapsed
            proj = s / elapsed if elapsed > 0.05 else s
            if proj >= 100 and s > 40:
                bump("RED", f"7d on pace to hit the cap ({proj:.0f}% projected)")
            elif pace > PACE_Y:
                bump("YELLOW", f"7d {pace:.0f} pts ahead of even pace")
    return tier, reasons, pace


def main():
    try:
        l = json.load(open(LEDGER))
    except Exception:
        l = {}
    age = now - l.get("ts", 0)
    if l and age <= 1800:
        tier, reasons, pace = compute(l)
    else:
        brake = os.path.exists(os.path.join(A.STATE, "TOKEN_SAVER"))
        tier = "RED" if brake else "UNKNOWN"
        reasons = ["ledger stale" + ("; TOKEN_SAVER brake on" if brake else "")]
        pace = None
        if not brake and l and age <= 6 * 3600 and (l.get("seven_day_reset") or 0) > now:
            l2 = dict(l)
            if (l2.get("five_hour_reset") or 0) <= now:
                l2["five_hour_pct"] = 0
            tier, r2, pace = compute(l2)
            reasons = r2 + [f"carried from a {int(age // 60)} min old reading"]
    rec = {"tier": tier, "reasons": reasons, "ts": now,
           "ledger_age_s": int(age) if l else None,
           "five_hour_pct": l.get("five_hour_pct"), "five_hour_reset": l.get("five_hour_reset"),
           "seven_day_pct": l.get("seven_day_pct"), "seven_day_reset": l.get("seven_day_reset"),
           "pace_pts": None if pace is None else round(pace, 1)}
    A.atomic_json(OUT, rec)

    try:
        last = open(LAST_KNOWN).read().strip()
    except OSError:
        last = ""
    # only transitions between KNOWN tiers are news (UNKNOWN flaps are not)
    if tier in ORDER and tier != last:
        open(LAST_KNOWN, "w").write(tier)
        if last:
            announce(last, tier, rec)
    print(json.dumps(rec))


def announce(prev, tier, rec):
    mem = os.path.join(A.BIN, "mem")
    msg = f"USAGE TIER {prev} -> {tier}: " + "; ".join(rec["reasons"] or ["ok"])
    body = ("Live shared usage tier for ALL agents. Read before any non-trivial job.\n"
            "GREEN = normal. YELLOW = no new expensive subagents, compact long sessions, skip "
            "low-priority pulses. RED = critical work only, no subagents, defer the rest.\n\n"
            + json.dumps(rec, indent=1))
    runs = [
        ([sys.executable, mem, "log", msg, "--author", "usage-tier"], None),
        ([sys.executable, mem, "write", "usage-ledger", "--type", "project", "--author", "usage-tier",
          "--desc", f"LIVE shared usage tier: {tier} (read before big jobs)"], body),
    ]
    nice = {"GREEN": "back to normal", "YELLOW": "getting tight, trimming low-priority work",
            "RED": "near the cap, critical work only"}[tier]
    runs.append(([os.path.join(A.BIN, "notify"), "--key", "usage-tier",
                  f"Usage tier {prev} -> {tier}: {nice} (5h {rec['five_hour_pct']}%, 7d {rec['seven_day_pct']}%)"], None))
    for cmd, stdin in runs:
        try:
            subprocess.run(cmd, input=stdin, text=True, capture_output=True, timeout=40)
        except Exception:
            pass


if __name__ == "__main__":
    main()
