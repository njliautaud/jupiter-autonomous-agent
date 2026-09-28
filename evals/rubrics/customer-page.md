# Rubric: customer-facing page / site / public UI (anything a non-team person sees)
Includes `_common.md`.

- P1 MUST — Actually live: `curl -sS -o /dev/null -w '%{http_code}' <url>` = 200 and the served HTML/JS contains a string unique to THIS change (not a cached or stale build).
- P2 MUST — Renders correctly at phone width (~400px) and desktop: screenshots of both; no horizontal scroll, clipped text or broken images.
- P3 MUST — Zero console errors on load and on the main interaction.
- P4 MUST — Every number, price, date and name shown is real and correct — spot-check at least 3 against the source of truth. No placeholder, lorem ipsum, "TODO" or test data.
- P5 MUST — Nothing internal exposed: no API keys in page source, no internal hostnames or private IPs, no stack traces, no admin routes reachable without auth.
- P6 MUST — Primary links and forms work: each call-to-action leads somewhere real; forms show a success or error state.
- P7 SHOULD — Copy reads like a person wrote it: clear, consistent names, no typos.
- P8 SHOULD — Basic accessibility: alt text, labelled buttons, readable contrast in light and dark.
- P9 SHOULD — Legal pieces present where needed (privacy/terms; third-party data terms honoured).
- P10 SHOULD — Main content visible in under ~3 s on mobile; no multi-MB unoptimised images.
