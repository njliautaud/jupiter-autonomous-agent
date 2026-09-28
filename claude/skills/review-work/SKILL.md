---
name: review-work
description: Grade a finished deliverable with a fresh-context adversarial reviewer before calling it done. Use before reporting ANY non-trivial deliverable as complete — an app release, a customer-facing page, a report/audit, an infra change (cron/hooks/services/agents), or a data analysis. Picks the matching rubric, spawns the work-reviewer agent, applies at most one FIX round, re-reviews once, then reports. Skip for one-line answers, status checks and trivial edits.
---

# review-work — rubric + separate grader before "done"

Why: a separate grader with its own context, checking against a written rubric, beats
self-review (the "outcomes" pattern), and models routinely claim success that did not
happen. The builder never grades its own work.

## When
- USE: you are about to tell the owner (or another agent) a non-trivial deliverable is done.
- SKIP: status replies, lookups, one obvious edit, anything already reviewed this round, or
  when `{{AGENT_HOME}}/state/usage_tier.json` says RED (then say "not independently
  reviewed — usage RED" in the report).

## Steps (bounded: max 2 review rounds, 1 fix round)
1. **Pick the rubric** (pass two if two apply). All live in `{{AGENT_HOME}}/evals/rubrics/`:
   | Deliverable | Rubric |
   |---|---|
   | App build / release / anything installed on a device | `app-release.md` |
   | Web page, site, public UI, email template | `customer-page.md` |
   | Report, research, audit, plan, recommendation | `report.md` |
   | Scripts, cron, hooks, services, settings, agents/skills | `infra-change.md` |
   | Numbers from data: books, usage, analytics | `data-analysis.md` |
   Every rubric also includes `_common.md`.
2. **Write the hand-off** — facts only, no persuasion: what was built, exact locations
   (branch+commit, URL, paths), the claims you are making, resources it may use.
3. **Spawn** `Agent(subagent_type="work-reviewer", prompt=<hand-off + rubric path(s)>)`.
   Never review in your own context — the fresh context is the point.
4. **SHIP** → step 6.
5. **FIX** → fix every MUST item and any cheap, real contrarian finding. One fix round.
   Re-spawn the reviewer ONCE with the same hand-off plus "Round 2: previous FIX list was
   …; verify these, then re-check the rest." Disagree with evidence, not argument.
6. **Report** plainly: result first, what changed, next step. If round 2 still says FIX,
   say honestly what still fails — never loop a third time.
7. `mem log "review-work: <deliverable> -> <SHIP|FIX-remaining> (<rubric>)"`.
   A NEW recurring failure mode goes to the owner as a rubric suggestion — rubrics are
   hand-curated; self-written, unreviewed guidance measurably hurts.

## Guardrails
- The reviewer is read-only; you do the fixes.
- Never skip a MUST because it is inconvenient; mark it UNVERIFIED and say so.
- Cost: one strong-model reviewer per round, ≤ 2 rounds, once per deliverable.
