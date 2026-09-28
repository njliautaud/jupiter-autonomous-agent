#!/usr/bin/env python3
"""
pulse_precheck — SCRIPT-FIRST pulse: do the cheap checks in plain Python and wake
Claude ONLY when something actually changed. A scheduled "check everything" prompt
that usually finds nothing is the single most expensive habit an always-on agent
can have (each wake re-reads a large prompt prefix). This skeleton replaces it.

Example checks (all optional, configured in config/agent.env):
  PULSE_URLS          comma-separated URLs that must answer HTTP < 400  (site up/down)
  PULSE_DISK_PATHS    comma-separated mount points (default "/")
  PULSE_DISK_WARN     percent full that counts as a problem (default 90)
  PULSE_INBOX_CMD     shell command printing one integer (e.g. unread mail count)
  PULSE_HEARTBEAT_H   hours between "all quiet" heartbeat wakes (default 24, 0 = never)

Every event carries a PRIORITY that goes through bin/usage_gate.sh:
  critical  a site went DOWN                     -> always wakes
  normal    a site recovered / disk crossed WARN -> skipped only in RED
  low       inbox grew / heartbeat               -> skipped in YELLOW or RED
A skipped wake does NOT advance the baseline, so the change is re-detected later.

FAIL-SAFE: the whole check runs under a hard timeout that raises CheckTimeout, a
BaseException subclass, so no `except Exception` inside a check can swallow it.
Any crash or timeout wakes Claude with the FULL original pulse prompt (the old,
expensive behaviour) at most once per PULSE_FAIL_COOLDOWN_M minutes (default 60).

Wake action: `claude -p <prompt> --max-turns PULSE_MAX_TURNS` in $AGENT_HOME, or
PULSE_WAKE_CMD (a shell command that receives the prompt on stdin).

Usage: pulse_precheck.py [--dry-run] [--force]      (cron: every 10-15 min)
"""
import argparse, json, os, shutil, signal, subprocess, sys, time, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentlib as A

STATE_F = os.path.join(A.STATE, "pulse_precheck.json")
LOG_F = os.path.join(A.LOGS, "pulse_precheck.log")
PRIO_RANK = {"low": 0, "normal": 1, "critical": 2}
FULL_PROMPT = ("PULSE (full check): the cheap precheck could not run. Check the watched sites, disk "
               "space and inbox yourself. If nothing needs attention, say nothing. If something does, "
               "fix what you safely can, then send the owner one short plain-English line.")


class CheckTimeout(BaseException):
    """Raised by SIGALRM. BaseException so `except Exception` in checks can't eat it."""


def _on_alarm(*_):
    raise CheckTimeout()


def log(msg):
    os.makedirs(A.LOGS, exist_ok=True)
    with open(LOG_F, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


# ------------------------------------------------------------------ checks
def check_sites():
    out = {}
    for url in [u.strip() for u in (A.env("PULSE_URLS", "") or "").split(",") if u.strip()]:
        try:
            req = urllib.request.Request(url, method="GET", headers={"User-Agent": "pulse-precheck"})
            with urllib.request.urlopen(req, timeout=10) as r:
                out[url] = "up" if r.status < 400 else f"down:{r.status}"
        except urllib.error.HTTPError as e:
            out[url] = "up" if e.code < 400 else f"down:{e.code}"
        except Exception as e:
            out[url] = f"down:{type(e).__name__}"
    return out


def check_disk():
    out = {}
    for p in [x.strip() for x in (A.env("PULSE_DISK_PATHS", "/") or "/").split(",") if x.strip()]:
        try:
            u = shutil.disk_usage(p)
            out[p] = round(100 * u.used / u.total, 1)
        except OSError:
            out[p] = None
    return out


def check_inbox():
    cmd = A.env("PULSE_INBOX_CMD")
    if not cmd:
        return None
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return int(r.stdout.strip().split()[0])


def snapshot():
    return {"sites": check_sites(), "disk": check_disk(), "inbox": check_inbox()}


def diff(old, new):
    """-> list of (priority, human line)."""
    ev = []
    for url, st in new["sites"].items():
        was = old.get("sites", {}).get(url, "up")
        if st != "up" and was == "up":
            ev.append(("critical", f"site DOWN: {url} ({st})"))
        elif st == "up" and was != "up":
            ev.append(("normal", f"site recovered: {url}"))
    warn = A.env_float("PULSE_DISK_WARN", 90)
    for p, pct in new["disk"].items():
        was = old.get("disk", {}).get(p)
        if pct is not None and pct >= warn and (was is None or was < warn):
            ev.append(("normal", f"disk {p} at {pct}% (warn {warn:.0f}%)"))
    if new["inbox"] is not None and old.get("inbox") is not None and new["inbox"] > old["inbox"]:
        ev.append(("low", f"inbox grew {old['inbox']} -> {new['inbox']}"))
    return ev


# ------------------------------------------------------------------ wake
def gate(prio, label):
    return subprocess.run([os.path.join(A.BIN, "usage_gate.sh"), prio, label]).returncode == 0


def wake(prompt, dry):
    if dry:
        print("[dry-run] WAKE:\n" + prompt)
        return True
    cmd = A.env("PULSE_WAKE_CMD")
    try:
        if cmd:
            r = subprocess.run(cmd, shell=True, input=prompt, text=True, timeout=1800, cwd=A.AGENT_HOME)
        else:
            r = subprocess.run(["claude", "-p", prompt, "--max-turns", str(A.env_int("PULSE_MAX_TURNS", 15))],
                               timeout=1800, cwd=A.AGENT_HOME, capture_output=True, text=True)
        log(f"wake rc={r.returncode}")
        return r.returncode == 0
    except Exception as e:
        log(f"wake failed: {type(e).__name__}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="wake even if nothing changed")
    a = ap.parse_args()
    A.ensure_dirs()
    try:
        st = json.load(open(STATE_F))
    except Exception:
        st = {}
    now = time.time()

    signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(A.env_int("PULSE_TIMEOUT_S", 60))
    try:
        new = snapshot()
        signal.alarm(0)
    except (CheckTimeout, Exception) as e:  # fail-safe: fall back to the full check
        signal.alarm(0)
        why = "timeout" if isinstance(e, CheckTimeout) else f"{type(e).__name__}: {e}"
        log(f"precheck failed ({why}) -> full check")
        cooldown = A.env_int("PULSE_FAIL_COOLDOWN_M", 60) * 60
        if now - st.get("last_fail_wake", 0) >= cooldown and gate("normal", "pulse fail-safe"):
            if wake(FULL_PROMPT + f"\n(precheck error: {why})", a.dry_run) and not a.dry_run:
                st["last_fail_wake"] = now
                A.atomic_json(STATE_F, st)
        print(f"precheck failed ({why}); fail-safe path taken")
        return 0

    old = st.get("snap")
    events = diff(old, new) if old else []
    hb_h = A.env_float("PULSE_HEARTBEAT_H", 24)
    if not events and hb_h > 0 and now - st.get("last_wake", 0) >= hb_h * 3600 and old:
        events = [("low", "heartbeat: all quiet")]
    if a.force:
        events = events or [("normal", "forced run")]
    if not old:
        st.update(snap=new, last_wake=now)
        if not a.dry_run:
            A.atomic_json(STATE_F, st)
        print("baseline recorded; no wake")
        return 0
    if not events:
        st["snap"] = new
        if not a.dry_run:
            A.atomic_json(STATE_F, st)
        print("no change; Claude not woken")
        return 0

    prio = max((p for p, _ in events), key=PRIO_RANK.get)
    lines = "\n".join(f"- [{p}] {t}" for p, t in events)
    if not gate(prio, lines.replace("\n", " | ")):
        log(f"gated ({prio}): {lines!r}")
        print(f"change detected but gated by usage tier ({prio}); baseline kept")
        return 0
    prompt = ("PULSE: the precheck found these changes since the last check:\n" + lines +
              "\n\nInvestigate only these. Fix what you safely can. Then send the owner ONE short "
              "plain-English line (use bin/notify) unless it is just a heartbeat with nothing to say.")
    if wake(prompt, a.dry_run):
        st.update(snap=new, last_wake=now)
        if not a.dry_run:
            A.atomic_json(STATE_F, st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
