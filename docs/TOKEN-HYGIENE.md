# Token hygiene — lessons from running an agent 24/7 on a subscription

On a Pro/Max plan the constraint is the rolling 5-hour and weekly usage limits, not
dollars. These are the lessons that moved the needle, roughly in order of impact.

## 1. Cache reads dominate — so session length dominates
Every turn re-sends the whole accumulated conversation. Prompt caching makes that
cheap per token, but across a long session it is still the bulk of usage: in our
measurements, cache reads were ~85-90% of the weekly total. What you type barely matters;
**how long the prefix is when you type it** does.
- `/clear` at task boundaries (deliverable finished → clear before the next one).
- `/compact` mid-task when context passes ~50% of the window.
- New session when switching projects. The included prompt hook nags past 200k tokens.

## 2. Script-first pulses
A scheduled "check everything" prompt that usually finds nothing is the most expensive
habit an always-on agent has: each wake pays for the full system prompt, tools and
memory. Let a plain script decide whether anything changed and wake Claude only with
the diff (`bin/pulse_precheck.py`). A precheck that crashes or hangs must fall back to
the full check — the timeout is raised as a `BaseException` so no `except Exception`
inside a check can swallow it.

## 3. Measure the real account %, not dollar estimates
Estimating spend from transcripts (per-token prices × tokens) is off by large factors
for subscription limits and double-counts easily (the same message appears in several
log files — dedupe by message id if you do it). The status line receives the real
rate-limit percentages; `usage_statusline.py` records them for every agent to share.

## 4. One shared tier with priorities
Every scheduled job declares a priority and goes through `usage_gate.sh`:
- `critical` always runs (access to the machine, safety, anything time-critical)
- `normal` skips in RED
- `low` (briefings, research, heartbeats) skips in YELLOW and RED
Missing data never blocks work.

## 5. Bounded subagents
Subagents are great for keeping heavy searches out of the main context, but each one is
a fresh prompt prefix. Always: a scoped task, `--max-turns`, commit-and-exit, **no
polling** (never let an agent sleep-and-check a long job — use a script and a
notification). In RED, the included hook denies new subagents.

## 6. Route by task, not by budget panic
Small/fast models for lookups, status and mechanical edits; the strongest model for
things other people will see. Controlling cost by bounding work beats downgrading the
model on deliverables and redoing them.

## 7. Keep always-loaded context small
CLAUDE.md, the memory index and hook output are paid on every turn of every session.
Keep CLAUDE.md to rules that change behaviour; move reference material into memories the
agent searches on demand (`mem search`), and briefs it reads per project.
