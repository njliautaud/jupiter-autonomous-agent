#!/usr/bin/env bash
# Virtual desktop for the agent (NOT your real screen):
#   Xvfb :$DISPLAY_NUM  + a light window manager
#   x11vnc on 127.0.0.1:$VNC_PORT (password file from setup_desktop.sh)
#   noVNC/websockify on $BIND_ADDR:$NOVNC_PORT -> the link `takeover` sends you
. "$(dirname "$(readlink -f "$0")")/../../bin/agent_env.sh"
export PATH="$HOME/.local/bin:$PATH"
D=":${DISPLAY_NUM:-99}"; export DISPLAY="$D"
PW="$AGENT_HOME/state/vnc/passwd"
NOVNC="$AGENT_HOME/vendor/noVNC"
[ -f "$PW" ] && [ -d "$NOVNC" ] || { echo "run always-on/setup_desktop.sh first"; sleep 60; exit 1; }
ensure() {
  pgrep -f "Xvfb $D" >/dev/null || { Xvfb "$D" -screen 0 "${DESKTOP_SIZE:-1920x1080}x24" -nolisten tcp >/dev/null 2>&1 & sleep 2; }
  for wm in openbox fluxbox xfwm4; do command -v $wm >/dev/null && { pgrep -x $wm >/dev/null || { $wm >/dev/null 2>&1 & }; break; }; done
  pgrep -f "x11vnc.*-rfbport ${VNC_PORT:-5901}" >/dev/null || \
    { x11vnc -display "$D" -rfbauth "$PW" -rfbport "${VNC_PORT:-5901}" -localhost -forever -shared -noxdamage -quiet >/dev/null 2>&1 & sleep 1; }
}
( while true; do ensure; sleep 15; done ) &
ensure
while true; do
  if [ -f "$AGENT_HOME/state/tls/server.crt" ]; then TLSARGS=(--cert "$AGENT_HOME/state/tls/server.crt" --key "$AGENT_HOME/state/tls/server.key"); else TLSARGS=(); fi
  websockify "${TLSARGS[@]}" --web "$NOVNC" "${BIND_ADDR:-127.0.0.1}:${NOVNC_PORT:-7682}" "127.0.0.1:${VNC_PORT:-5901}"
  sleep 5
done
