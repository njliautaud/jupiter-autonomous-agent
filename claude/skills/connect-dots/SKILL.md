---
name: connect-dots
description: Cross-project connection finder — reads every project brief and recent shared-memory activity and proposes a few NON-OBVIOUS opportunities (a tool from project A reused in B, a shared root cause behind separate bugs, an unused asset, duplicated effort to merge), each with a concrete next action, then logs them to shared memory. Use when the owner asks "what am I missing / any ideas", at a weekly review, or headless via bin/connect_dots_weekly.sh. Read-only on projects; it proposes, it does not build.
---

# connect-dots — find the non-obvious links across projects

## Inputs (bounded: slices, not dumps)
1. Project briefs: `mem brief` lists them; `mem brief <name>` reads one (short by design).
   No briefs yet → read `{{AGENT_HOME}}/memory/MEMORY.md` and `mem read` the ~8 most relevant entries.
2. Recent activity: `mem feed 80`.
3. Earlier ideas: `tail -60 {{AGENT_HOME}}/memory/_IDEAS.md` if it exists — do not re-propose
   an idea unless something material changed (then say what).
4. Optional: `mem search "<term>"` to confirm an asset exists before proposing to reuse it.

## A good connection is one of
- **Reuse:** something built for A solves a live problem in B.
- **Shared root cause:** two "separate" issues, one underlying cause, one fix.
- **Unused asset:** something already paid for or built that nobody uses.
- **Duplicated effort:** two agents/projects building the same thing → merge.
- **Risk echo:** a failure mode learned in A that B has not guarded against.
Reject generic advice ("add tests"), single-project ideas, anything that would cross a HARD
BOUNDARY in CLAUDE.md (those can only be proposed to the owner), and anything without evidence.

## Output: 3-7 ideas ranked by value × ease, each exactly
```
### <short title>
Link: <project A> ↔ <project B> — <reuse|root-cause|asset|dup|risk>
Why: <2 sentences citing memory slugs / feed lines>
Next action: <one concrete step, who (agent|owner), rough effort>
```

## Record
- Append under a dated heading `## YYYY-MM-DD` to `{{AGENT_HOME}}/memory/_IDEAS.md` (append only).
- `mem log "connect-dots: <top idea> (+N more in _IDEAS.md)" --author connect-dots`
- Do not implement the ideas in this run.
