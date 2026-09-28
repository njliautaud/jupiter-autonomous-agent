#!/usr/bin/env python3
"""
SessionEnd / PreCompact hook -> one line on the shared activity feed, e.g.
  "session ended (reason=clear) cwd=~/projects/app sid=1a2b3c4d transcript=3.1MB/812 lines"

Fast (hard 2 s ceiling), never blocks session exit or compaction, never prints,
always exits 0. Skips headless helper runs whose cwd is $AGENT_HOME/state.
"""
import os, sys, json, signal


def main():
    signal.signal(signal.SIGALRM, lambda *a: os._exit(0))
    signal.alarm(2)
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    if not isinstance(data, dict) or not data.get("session_id"):
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import agentlib as A
    import mem_core as M
    home = os.path.expanduser("~")
    cwd = data.get("cwd") or os.getcwd()
    if os.path.realpath(cwd) == os.path.realpath(A.STATE):
        return
    if (data.get("hook_event_name") or ("PreCompact" if "trigger" in data else "")) == "PreCompact":
        what = f"session compacting (trigger={data.get('trigger', '?')})"
    else:
        what = f"session ended (reason={data.get('reason', '?')})"
    size = ""
    tp = data.get("transcript_path") or ""
    try:
        st = os.stat(tp)
        lines = 0
        if st.st_size < 64 * 1024 * 1024:
            with open(tp, "rb") as f:
                lines = sum(buf.count(b"\n") for buf in iter(lambda: f.read(1 << 20), b""))
        size = f" transcript={st.st_size / 1e6:.1f}MB/{lines} lines"
    except Exception:
        pass
    short = cwd.replace(home, "~", 1)
    author = os.environ.get("MEM_AUTHOR") or os.environ.get("AGENT_NAME") or "session-hook"
    M.log(f"{what} cwd={short} sid={str(data['session_id'])[:8]}{size}", author)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    os._exit(0)
