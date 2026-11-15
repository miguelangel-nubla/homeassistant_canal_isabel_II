#!/bin/sh
# Starts a virtual screen, a password-protected remote view of it (noVNC on
# port 6080) and the helper that runs the browser.
set -eu

: "${VNC_PASSWORD:?Set VNC_PASSWORD: the remote view shows a logged-in browser}"
: "${HA_URL:?Set HA_URL, for example http://homeassistant.local:8123}"
: "${HA_TOKEN:?Set HA_TOKEN to a Home Assistant long-lived access token}"

SCREEN="${SCREEN_SIZE:-1280x800}"

Xvfb "$DISPLAY" -screen 0 "${SCREEN}x24" -nolisten tcp &
sleep 1

x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vncpass >/dev/null 2>&1
x11vnc -display "$DISPLAY" -rfbauth /tmp/vncpass -forever -shared -localhost -quiet -bg -o /tmp/x11vnc.log >/dev/null
websockify --web /usr/share/novnc 6080 localhost:5900 >/tmp/websockify.log 2>&1 &

exec python3 -u /app/helper.py
