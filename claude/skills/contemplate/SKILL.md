---
name: contemplate
description: Think-harder mode for HARD, HIGH-STAKES or genuinely AMBIGUOUS problems only — runs 3 independent subagents with deliberately different approaches (separate git worktrees for code), then selects by execution or merges with a contrarian critique. Use when a wrong answer is expensive (architecture choice, a bug that resisted 2+ attempts, security/production decision, the owner asks to think hard). Not for routine tasks, lookups, simple fixes or anything with an obvious answer. Requires usage tier GREEN; otherwise does one careful attempt.
---

# contemplate — N independent attempts, then aggregate

Why: parallel independent attempts + aggregation ("think wider, not longer") beats one
long attempt on hard problems — at ~3-4x the cost. Always-on swarms and debate panels cost
far more for small gains, so this is OFF by default and gated.

## Gate (every time)
1. Is it actually hard / high-stakes / ambiguous? If one competent attempt would very likely
   be right → stop and just do it.
2. `cat {{AGENT_HOME}}/state/usage_tier.json` → if `tier` is not `GREEN` → one careful attempt,
   and note "single attempt — usage tier <X>".
3. Budget: exactly 3 attempts, one aggregation, no second round.

## Framings (make them genuinely different)
- **A — Direct:** what an expert would try first; smallest change.
- **B — Root cause:** ignore the obvious fix; re-derive what is going on from logs/data/specs;
  question the problem statement.
- **C — Contrarian:** assume A is wrong; solve it a structurally different way (other layer,
  other algorithm, delete instead of add).
For decisions: A = best case for option 1, B = best case for option 2 / status quo,
C = red team ("what goes wrong in 3 months if we do the obvious thing").

## Run
- Code: one worktree per attempt from the same base commit:
  `git -C <repo> worktree add {{AGENT_HOME}}/work/contemplate-<slug>-{a,b,c} <base-sha>`.
  Each subagent works only there, commits locally, never pushes or deploys, and ends with
  how to run its verification.
- Spawn all 3 in ONE message (parallel). Each prompt: the problem, its framing, "work
  independently", the success check, "bounded: finish and report, no polling", and
  "run `mem search <topic>` first".
- Each returns: answer/diff summary, how it was verified (commands + output), confidence,
  known weaknesses.

## Aggregate (where the value is)
1. **Select by execution** when possible: run the SAME test against each worktree yourself.
   Best passing score wins; ties → smallest diff. Verified beats claimed.
2. Otherwise **merge**: where all three agree (high confidence), where they differ and why;
   build from the strongest parts; write a short contrarian critique of the merge; adjust.
3. Report the answer, one line on why it won, what is still uncertain. Remove losing
   worktrees (keep a branch if it holds a useful idea).
4. `mem log "contemplate: <problem> -> chose <A|B|C|merge> because <reason>"`.
