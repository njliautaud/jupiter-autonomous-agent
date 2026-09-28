# Common items (apply to EVERY rubric)

- C1 MUST — Claimed == verified. Every "done / works / live / fixed" in the summary is backed by a check the reviewer re-ran, not the author's word.
- C2 MUST — The summary to the owner is plain English: result first, then what changed, then the next step. No file paths, PIDs, hashes or jargon unless asked.
- C3 MUST — No hard boundary crossed (see HARD BOUNDARIES in {{AGENT_HOME}}/CLAUDE.md); no money moved.
- C4 MUST — Irreversible outward actions (email, post, deploy to production, delete) were logged in {{AGENT_HOME}}/ACTIONS.log before being done.
- C5 SHOULD — Honest about gaps: anything not verified is named as not verified.
- C6 SHOULD — The owner is not the test rig: nothing asks them to "try it and see" something the agent could have checked.
- C7 SHOULD — Durable learnings saved to shared memory (`mem write` / `mem log`).
