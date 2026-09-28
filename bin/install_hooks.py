#!/usr/bin/env python3
"""install_hooks — merge this kit's statusLine + hooks into a Claude Code settings.json.

  install_hooks.py [--settings PATH] [--uninstall] [--dry-run]

Default PATH: $CLAUDE_SETTINGS or ~/.claude/settings.json (user scope, so every
session on the box shares the same usage tier and memory feed).
Idempotent: our entries are recognised by the kit's bin path and replaced, never
duplicated; every other hook you have is left untouched. A timestamped backup is
written next to the file before any change. An existing statusLine that is not
ours is kept unless --force-statusline is given.
"""
import argparse, json, os, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentlib as A


def ours(cmd):
    return A.BIN in (cmd or "")


def entries():
    py = sys.executable or "python3"
    pre = f"AGENT_HOME={A.AGENT_HOME} "
    c = lambda s, t=5: {"type": "command", "command": pre + s, "timeout": t}
    return {
        "UserPromptSubmit": [{"hooks": [c(f"{py} {A.BIN}/usage_hook.py prompt")]}],
        "PreToolUse": [{"matcher": "Agent|Task", "hooks": [c(f"{py} {A.BIN}/usage_hook.py pretool")]}],
        "SessionEnd": [{"hooks": [c(f"{py} {A.BIN}/hook_session_end.py")]}],
        "PreCompact": [{"hooks": [c(f"{py} {A.BIN}/hook_session_end.py")]}],
    }, {"type": "command", "command": pre + f"{py} {A.BIN}/usage_statusline.py"}


def strip(settings):
    hooks = settings.get("hooks") or {}
    for ev in list(hooks):
        kept = []
        for group in hooks[ev] or []:
            hs = [h for h in group.get("hooks", []) if not ours(h.get("command"))]
            if hs:
                kept.append({**group, "hooks": hs})
        if kept:
            hooks[ev] = kept
        else:
            hooks.pop(ev)
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)
    if ours((settings.get("statusLine") or {}).get("command")):
        settings.pop("statusLine")
    return settings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", default=os.environ.get("CLAUDE_SETTINGS") or os.path.expanduser("~/.claude/settings.json"))
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--force-statusline", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        with open(a.settings) as f:
            settings = json.load(f)
    except FileNotFoundError:
        settings = {}
    before = json.dumps(settings, sort_keys=True)
    settings = strip(settings)
    if not a.uninstall:
        new, status = entries()
        hooks = settings.setdefault("hooks", {})
        for ev, groups in new.items():
            hooks.setdefault(ev, []).extend(groups)
        if "statusLine" not in settings or a.force_statusline:
            settings["statusLine"] = status
        else:
            print("note: kept your existing statusLine; the usage SENSOR needs ours "
                  "(re-run with --force-statusline, or call usage_statusline.py from yours)")
    after = json.dumps(settings, sort_keys=True)
    if before == after:
        print(f"settings already up to date: {a.settings}")
        return
    if a.dry_run:
        print(json.dumps(settings, indent=2))
        return
    os.makedirs(os.path.dirname(os.path.abspath(a.settings)), exist_ok=True)
    if os.path.exists(a.settings):
        bak = f"{a.settings}.bak.{int(time.time())}"
        shutil.copy2(a.settings, bak)
        print(f"backup: {bak}")
    tmp = a.settings + ".tmp"
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=2)
    os.replace(tmp, a.settings)
    print(f"{'removed' if a.uninstall else 'installed'} hooks in {a.settings}")


if __name__ == "__main__":
    main()
