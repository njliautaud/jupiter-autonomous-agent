#!/usr/bin/env bash
# setup_desktop.sh — one-time setup for the agent's virtual desktop.
# Does NOT use sudo: prints the package command if something is missing.
#  1. checks Xvfb, x11vnc, a window manager, scrot, websockify
#  2. fetches noVNC into $AGENT_HOME/vendor/noVNC (pinned tag)
#  3. creates a VNC password (from VNC_PASSWORD in config/agent.env, else random)
#     stored hashed in $AGENT_HOME/state/vnc/passwd (chmod 600)
. "$(dirname "$(readlink -f "$0")")/../bin/agent_env.sh"
missing=()
for b in Xvfb x11vnc scrot openssl git; do command -v $b >/dev/null || missing+=("$b"); done
command -v openbox >/dev/null || command -v fluxbox >/dev/null || missing+=("openbox")
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing: ${missing[*]}"
  echo "Debian/Ubuntu:  sudo apt install xvfb x11vnc openbox scrot openssl git"
fi
command -v websockify >/dev/null || echo "Missing websockify:  python3 -m pip install --user websockify"
if [ ! -d "$AGENT_HOME/vendor/noVNC" ]; then
  mkdir -p "$AGENT_HOME/vendor"
  git clone --depth 1 --branch "${NOVNC_TAG:-v1.5.0}" https://github.com/novnc/noVNC.git "$AGENT_HOME/vendor/noVNC" \
    && echo "noVNC installed"
fi
mkdir -p "$AGENT_HOME/state/vnc"; chmod 700 "$AGENT_HOME/state/vnc"
if [ ! -f "$AGENT_HOME/state/vnc/passwd" ] && command -v x11vnc >/dev/null; then
  PW="${VNC_PASSWORD:-$(head -c 12 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 8)}"
  x11vnc -storepasswd "$PW" "$AGENT_HOME/state/vnc/passwd" >/dev/null 2>&1
  chmod 600 "$AGENT_HOME/state/vnc/passwd"
  [ -z "${VNC_PASSWORD:-}" ] && echo "Generated a VNC password. Save it in your password manager, then set VNC_PASSWORD in config/agent.env:" && echo "  $PW"
fi
echo "Enable with DESKTOP_ENABLE=1 in config/agent.env, then: always-on/start.sh --only desktop"
