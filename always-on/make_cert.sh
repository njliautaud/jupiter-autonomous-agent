#!/usr/bin/env bash
# make_cert.sh — self-signed TLS cert for the web terminal / noVNC fronts.
# Written to $AGENT_HOME/state/tls (key chmod 600). CN/SAN = BIND_ADDR.
# For a trusted cert on a tailnet, prefer your VPN's own cert tooling
# (e.g. `tailscale cert`) and point TLS_CERT / TLS_KEY at it instead.
. "$(dirname "$(readlink -f "$0")")/../bin/agent_env.sh"
D="$AGENT_HOME/state/tls"; mkdir -p "$D"; chmod 700 "$D"
[ -f "$D/server.crt" ] && [ "${1:-}" != "--force" ] && { echo "cert exists (use --force to regenerate)"; exit 0; }
H="${BIND_ADDR:-127.0.0.1}"
case "$H" in *[!0-9.]*) SAN="DNS:$H" ;; *) SAN="IP:$H" ;; esac
openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=$H" \
  -addext "subjectAltName=$SAN" -keyout "$D/server.key" -out "$D/server.crt" 2>/dev/null
chmod 600 "$D/server.key"
echo "wrote $D/server.crt (self-signed, CN=$H)"
