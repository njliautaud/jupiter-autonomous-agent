# Rubric: app release (mobile/desktop build pushed to testers, a store track, or a device)
Includes `_common.md`.

- A1 MUST — Built from the intended branch and commit: `git rev-parse HEAD` in the build tree matches the commit claimed; branch state checked against a FRESH fetch of the remote, not stale local refs.
- A2 MUST — CLEAN build for anything that leaves the machine (no incremental build artifacts); the build log shows success.
- A3 MUST — Launch smoke test on an emulator/simulator/test device: install, launch, the expected first screen is in focus, and the crash log is empty (no fatal exceptions / verifier errors). Compile-green is not crash-free.
- A4 MUST — The changed screen or flow was opened and exercised end-to-end, with a screenshot showing the new behaviour on real data (not an empty state).
- A5 MUST — Device discipline: only the device/emulator assigned to this agent was used; no one else's device (and never the owner's personal phone) served as the test target.
- A6 MUST — Work landed on the development branch; production is only ever a promotion from it.
- A7 SHOULD — Work was done in a separate worktree when the checkout is shared with other sessions.
- A8 SHOULD — Shared UI helpers (motion, press states, theming) were reused rather than hand-rolled.
- A9 SHOULD — Release notes are one or two plain sentences a user would understand.
