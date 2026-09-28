# Rubric: infra change (scripts, cron, hooks, services, settings, agents/skills)
Includes `_common.md`.

- I1 MUST — Root cause stated in one plain line before the fix, and the fix is the smallest one that addresses it (a setting or one-liner beats new machinery).
- I2 MUST — Verified by EXECUTION: the script ran, the port answered, the cron command was dry-run, the hook fired — with output shown. Reading your own code does not count.
- I3 MUST — Every edited pre-existing file outside the repo has a timestamped backup. Nothing of the owner's deleted (archived/moved instead).
- I4 MUST — Crontab edits (if any) were made under a lock, a backup exists, and `crontab -l` afterwards still has every other entry (diff vs backup shows only the intended lines).
- I5 MUST — Everything under HARD BOUNDARIES untouched; new listeners bind only to loopback or the VPN/tailnet address — never a public interface.
- I6 MUST — Bounded cost: new scheduled or agentic jobs go through `usage_gate.sh` with an honest priority, set --max-turns / timeouts, and never poll in a loop.
- I7 MUST — Idempotent and safe on re-run and reboot: running twice does not duplicate cron lines, processes or data; failures log clearly instead of silently.
- I8 SHOULD — No secrets in crontab, scripts, logs or process arguments where avoidable; files holding them are chmod 600.
- I9 SHOULD — New agents/skills: valid frontmatter (name, description), bounded instructions, reviewed by a human before use.
- I10 SHOULD — `mem log` entry written so other agents know the change exists; NOTES.md updated if it is live state.
