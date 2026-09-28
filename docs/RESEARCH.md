# Research notes (2026) — what informed this kit

A survey of always-on agent systems and agent-engineering results from 2026, and what
we took (or deliberately did not take) from each. Links are to public sources.

## Curated skills beat self-generated ones
**SkillsBench** (86 tasks, 11 domains, 7,308 trajectories): curated skills raised pass
rates by ~16 points on average (with wide variance, and some tasks got worse), while
skills the model wrote for itself gave **no benefit on average**. Focused skills with a
few modules beat sprawling documentation.
- https://arxiv.org/abs/2602.12670
- Takeaway: rubrics and skills here are hand-curated; agents may *propose* edits, humans
  approve. No auto-promotion of agent-written instructions.

## Separate grader against a rubric ("outcomes")
Anthropic's Managed Agents added *outcomes* (a separate grader in its own context scores
work against a written rubric; reported up to ~10 points better task success) and
*dreaming* (scheduled memory curation between sessions), plus multi-agent orchestration.
- https://claude.com/blog/new-in-claude-managed-agents
- Takeaway: `work-reviewer` + `review-work` + rubrics implement the grader locally;
  `mem_dream.py` is a conservative, mechanical-first dreaming pass.

## Think wider, not longer (Muse Spark "Contemplating")
Meta's Muse Spark ships a mode where several agents reason in parallel and their answers
are reconciled, instead of one agent thinking longer.
- https://ai.meta.com/blog/introducing-muse-spark-msl/
- Takeaway: the `contemplate` skill — 3 deliberately different framings, select by
  execution or merge + critique — gated to hard problems and GREEN tier because it
  multiplies cost.

## Always-on teammates with human takeover (Grok Bot)
xAI's Grok Bot runs always-on agents on their own cloud computer; consequential actions
stop for approval, and passwords/2FA/CAPTCHAs trigger a *computer takeover* that hands
control to the human.
- https://x.ai/news/introducing-grok-bot
- Takeaway: `takeover` + the virtual desktop (Xvfb + noVNC) give the same pattern on your
  own box; the safety reflex in CLAUDE.md mirrors the approval gates.

## Evolutionary search with the agent as the mutation operator (AVO)
NVIDIA's Agentic Variation Operators: an evolutionary-search harness where a coding-agent
session proposes each variation, gated by a correctness check and a score.
- https://arxiv.org/abs/2603.24517
- Takeaway: the pulse eval suite outputs a single pass rate, so the agent's own operating
  prompt can be an optimisation target. Winners should still be reviewed before use.

## Remote Control instead of hand-rolled phone plumbing
Claude Code can expose a local session to the Claude mobile app / web.
- https://code.claude.com/docs/en/remote-control
- Takeaway: `rc-loop.sh` keeps a Remote Control server alive; the web terminal remains as
  a fallback that does not depend on any cloud relay.

## Don't-build list
Things we evaluated and decided are not worth building for a personal agent:
- **Always-on multi-agent swarms / debate panels** — several times the cost for small
  gains; use `contemplate` on demand instead.
- **Self-writing skills or rubrics without review** — measured to not help (above).
- **A vector database for memory** — at personal scale, SQLite FTS5 over markdown with
  good descriptions finds things fine, and stays human-readable.
- **Dollar-based budget estimators** — measure the real account percentage instead.
- **Custom chat bridges** when Remote Control or a webhook covers the need.
- **Polling agents** that sleep and re-check long jobs — use scripts + notifications.
- **Automatic CAPTCHA/2FA handling** — hand control to the human, always.

## Optional: fallback to another model when the plan is exhausted
Some setups route Claude Code through an OpenAI/Anthropic-compatible proxy to a
cheaper or free model when limits hit. It works for simple chores, but tool-use quality
drops sharply and it adds a moving part with its own keys. If you try it, keep it
opt-in per session (never the default), keep its key in `config/agent.env`, and never
let it run unattended jobs that touch anything under HARD BOUNDARIES.
