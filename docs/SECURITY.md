# Security model

An always-on agent with shell access is a remote shell with opinions. Treat it that way.

## Network: VPN / tailnet only
- Every listener binds to `BIND_ADDR` / `MEM_BIND`, default `127.0.0.1`. To reach it from a
  phone, set them to this machine's address on a private overlay network (WireGuard,
  Tailscale, ZeroTier, ...). **Never** bind a public interface, forward a router port,
  or put these services behind a public tunnel.
- Check what is listening after any change: `ss -tlnp`. Nothing of this kit should show
  `0.0.0.0` or a public address.
- Use your VPN's access controls so only your own devices can reach this machine.

## Authentication
- Web terminal: ttyd basic auth (`TTYD_CREDENTIAL`, generated at install). ttyd reads it
  from its command line, so other local users could see it in `ps` — run this on a
  single-user machine. The loop refuses to start without a credential.
- Memory API: bearer token (`MEM_TOKEN`, 32 random bytes, constant-time compare). The
  server refuses to bind a non-loopback address without a token (fail closed).
  `/health` is the only unauthenticated route and reveals only a count.
- Desktop: x11vnc listens on localhost only, with a hashed password file; noVNC is the
  only way in and is itself on the VPN address. The takeover message never includes the
  VNC password.
- Remote Control: authenticated by your Claude account. `RC_PERMISSION_MODE` defaults to
  `default` (Claude asks before risky tools). `bypassPermissions` gives the phone the same
  trust as the web terminal — choose deliberately.

## Secrets
- All secrets live in `$AGENT_HOME/config/agent.env`, created `chmod 600` (directory 700).
  `.gitignore` blocks `*.env`, `state/`, `logs/`, `memory/`, keys and certs.
- Scripts never print secret values; the notify webhook URL is never logged.
- Keep secrets out of: crontab lines, command arguments (where avoidable), memory entries,
  logs, commit messages and chat transcripts.
- Rotate anything that ever lands in a transcript or a repo, even a private one.

## Agent behaviour boundaries (in CLAUDE.md)
- HARD BOUNDARIES section: production systems the agent may read but never change.
- Safety reflex: state + log before any irreversible, outward-facing action.
- Finance read-only: never move money, even when a connected tool allows it.
- Human takeover for logins, 2FA and CAPTCHAs — the agent never tries to bypass them.
- Hooks can enforce more than prose: the included PreToolUse hook is a template for
  denying tools by condition; add your own for paths you consider sacred.

## Before publishing a fork
Run a secret scan on the tree AND the history (e.g. gitleaks and trufflehog), and grep
for your own IPs, hostnames, usernames, emails and home paths. Start public repos from a
fresh history rather than scrubbing an old one.
