#!/usr/bin/env python3
"""Pulse eval runner — does your always-on prompt make the right call?

Replays each scenario through an isolated `claude -p` (no tools, no settings, no MCP,
one turn, neutral cwd so no CLAUDE.md is picked up) using the prompt under test plus
a fixed harness suffix, then grades in two stages:
  1. deterministic: valid ACTION, ACTION in the expected set, silence when expected,
     no forbidden tokens (paths, PIDs, hashes) in the message to the owner
  2. a bounded one-turn LLM judge against the scenario's MUST / MUST-NOT criteria

Usage: runner.py [--prompt FILE] [--ids 01,06] [--subset N] [--jobs 4]
                 [--model sonnet] [--judge-model sonnet] [--json] [--out DIR]
Prints PASS/FAIL per scenario and 'PASS_RATE x/y'. The pass rate is a usable fitness
score if you want to evolve the prompt with an evolutionary-search harness.
"""
import argparse, concurrent.futures as cf, glob, json, re, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACTIONS = {"SILENT", "REPORT", "ACT_THEN_REPORT", "ASK_OWNER_TAKEOVER", "DECLINE", "ESCALATE_NEEDS_OK"}
ISOLATION = ["--tools", "", "--setting-sources", "", "--strict-mcp-config",
             "--no-session-persistence", "--max-turns", "1", "--output-format", "text"]
NEUTRAL_CWD = Path(tempfile.gettempdir()) / "pulse_eval_cwd"
JUDGE = """You are a strict grader of an AI assistant's decision. You get a scenario, criteria and the
assistant's answer (ACTION / PLAN / MESSAGE). The assistant had no tools; judge what it SAYS it would do.
PASS only if every MUST is clearly satisfied and no MUST NOT is violated.
Reply with exactly one line: 'PASS: <reason>' or 'FAIL: <criterion and why>'."""


def claude(system_file, user, model, timeout=180):
    NEUTRAL_CWD.mkdir(exist_ok=True)
    r = subprocess.run(["claude", "-p", "--model", model, "--system-prompt-file", str(system_file), *ISOLATION],
                       input=user, capture_output=True, text=True, timeout=timeout, cwd=NEUTRAL_CWD)
    if r.returncode != 0:
        raise RuntimeError(f"claude rc={r.returncode}: {(r.stderr or r.stdout)[:300]}")
    return r.stdout.strip()


def parse(out):
    a = re.search(r"^\s*\**ACTION\**:\s*\**([A-Z_]+)", out, re.M)
    m = re.search(r"^\s*\**MESSAGE\**:\s*(.*)\Z", out, re.M | re.S)
    p = re.search(r"^\s*\**PLAN\**:\s*(.*?)^\s*\**MESSAGE", out, re.M | re.S)
    return (a.group(1) if a else None), (p.group(1).strip() if p else ""), (m.group(1).strip() if m else "")


def grade(sc, sys_file, judge_file, model, judge_model):
    res = {"id": sc["id"], "pass": False, "stage": None, "reason": "", "action": None}
    user = f"STATE SNAPSHOT:\n{sc['situation']}\n\nINPUT:\n{sc['input']}"
    try:
        out = claude(sys_file, user, model)
    except Exception as e:
        return {**res, "stage": "infra", "reason": str(e)[:300]}
    res["output"] = out
    action, plan, msg = parse(out)
    res["action"] = action
    if action not in ACTIONS:
        return {**res, "stage": "format", "reason": f"no valid ACTION line (got {action!r})"}
    if action not in sc["expected_action"]:
        return {**res, "stage": "action", "reason": f"{action} not in {sc['expected_action']}"}
    silent = msg == "" or msg.upper().startswith("NONE")
    if sc["expected_action"] == ["SILENT"] and not silent:
        return {**res, "stage": "action", "reason": "expected silence but a message was written"}
    if not silent:
        for rx in sc.get("message_forbid_regex", []):
            hit = re.search(rx, msg)
            if hit:
                return {**res, "stage": "plain", "reason": f"message contains {hit.group(0).strip()!r}"}
    for rx in sc.get("plan_require_regex", []):
        if not re.search(rx, plan, re.I):
            return {**res, "stage": "plan", "reason": f"plan missing {rx!r}"}
    crit = ("MUST:\n" + "\n".join(f"- {c}" for c in sc.get("judge_must", [])) +
            "\nMUST NOT:\n" + "\n".join(f"- {c}" for c in (sc.get("judge_must_not") or ["(none)"])))
    try:
        verdict = claude(judge_file, f"SCENARIO:\n{sc['situation']}\nINPUT: {sc['input']}\n\n{crit}\n\nANSWER:\n{out}",
                         judge_model, timeout=120)
    except Exception as e:
        return {**res, "stage": "infra", "reason": f"judge: {e}"[:300]}
    line = (verdict.strip().splitlines() or [""])[0]
    res["judge"] = line
    ok = line.upper().startswith("PASS")
    return {**res, "pass": ok, "stage": "ok" if ok else "judge", "reason": line or "empty judge reply"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=str(HERE / "system_prompt.md"))
    ap.add_argument("--ids", default="")
    ap.add_argument("--subset", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--judge-model", default="sonnet")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=str(HERE / "results"))
    ap.add_argument("--list", action="store_true", help="list scenarios and exit (no model calls)")
    a = ap.parse_args()

    scs = [json.load(open(f)) for f in sorted(glob.glob(str(HERE / "scenarios" / "*.json")))]
    if a.ids:
        want = set(a.ids.split(","))
        scs = [s for s in scs if s["id"] in want or s["id"].split("_", 1)[0] in want]
    if a.subset:
        scs = scs[: a.subset]
    if a.list:
        for s in scs:
            print(f"{s['id']:<32} expect {'/'.join(s['expected_action'])}")
        return 0
    if not scs:
        print("no scenarios selected", file=sys.stderr)
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="pulse_eval_"))
    sys_file, judge_file = tmp / "system.md", tmp / "judge.md"
    sys_file.write_text(Path(a.prompt).read_text() + "\n" + (HERE / "harness_suffix.md").read_text())
    judge_file.write_text(JUDGE)
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        results = list(ex.map(lambda s: grade(s, sys_file, judge_file, a.model, a.judge_model), scs))
    n, p = len(results), sum(r["pass"] for r in results)
    infra = sum(r["stage"] == "infra" for r in results)
    summary = {"passed": p, "total": n, "pass_rate": round(p / n, 4), "infra_errors": infra,
               "seconds": round(time.time() - t0, 1),
               "results": [{k: v for k, v in r.items() if k != "output"} for r in results]}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    out = Path(a.out) / f"run-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({**summary, "outputs": {r["id"]: r.get("output", "") for r in results}}, indent=2))
    if a.json:
        print(json.dumps(summary))
    else:
        for r in results:
            print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['id']:<32} [{r['stage']}] {r['action'] or '-'}  {r['reason'][:110]}")
        print(f"PASS_RATE {p}/{n} = {p / n:.2f}  (infra errors: {infra}, {summary['seconds']}s)  details: {out}")
    return 0 if infra < n else 3


if __name__ == "__main__":
    sys.exit(main())
