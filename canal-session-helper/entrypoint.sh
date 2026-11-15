#!/bin/sh
# Starts a virtual screen, a password-protected remote view of it (noVNC on
# port 6080) and the helper that runs the browser.
set -eu

# As a Home Assistant add-on: the Supervisor gives the API token, ingress
# does the authentication, and the options come from /data/options.json.
if [ -n "${SUPERVISOR_TOKEN:-}" ] && [ -z "${HELPER_ADDON_READY:-}" ]; then
    export HA_URL="http://supervisor/core"
    export HA_TOKEN="$SUPERVISOR_TOKEN"
    export VNC_NO_PASSWORD="true"
    if [ -r /data/options.json ]; then
        eval "$(python3 - <<'PY'
import json, shlex
options = json.load(open("/data/options.json"))
print("export CHECK_INTERVAL=" + shlex.quote(str(options.get("check_interval", 600))))
print("export HA_ENTRY_ID=" + shlex.quote(str(options.get("entry_id") or "")))
PY
)"
    fi
    export HELPER_ADDON_READY=1
fi

# Started as root (the image default, and always as an add-on): give the
# data folder to the unprivileged user and continue as that user.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /data
    chown -R helper:helper /data
    exec setpriv --reuid helper --regid helper --init-groups env HOME=/home/helper "$0" "$@"
fi

# Each secret may be given directly or as a file (VNC_PASSWORD_FILE, HA_TOKEN_FILE).
if [ -z "${VNC_PASSWORD:-}" ] && [ -n "${VNC_PASSWORD_FILE:-}" ]; then
    VNC_PASSWORD="$(head -n 1 "$VNC_PASSWORD_FILE")"
fi
if [ -z "${HA_TOKEN:-}" ] && [ -z "${HA_TOKEN_FILE:-}" ]; then
    echo "Set HA_TOKEN or HA_TOKEN_FILE to a Home Assistant long-lived access token" >&2
    exit 1
fi
# The remote view shows a logged-in browser, so going without a password has to be asked for explicitly:
# VNC_NO_PASSWORD=true, for when port 6080 is only reachable through a proxy that already authenticates.
if [ "${VNC_NO_PASSWORD:-}" != "true" ]; then
    : "${VNC_PASSWORD:?Set VNC_PASSWORD or VNC_PASSWORD_FILE, or VNC_NO_PASSWORD=true behind an authenticating proxy}"
fi
: "${HA_URL:?Set HA_URL, for example http://homeassistant.local:8123}"

SCREEN="${SCREEN_SIZE:-1280x800}"

Xvfb "$DISPLAY" -screen 0 "${SCREEN}x24" -nolisten tcp &
sleep 1

if [ "${VNC_NO_PASSWORD:-}" = "true" ]; then
    VNC_AUTH="-nopw"
else
    x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vncpass >/dev/null 2>&1
    VNC_AUTH="-rfbauth /tmp/vncpass"
fi
# shellcheck disable=SC2086
x11vnc -display "$DISPLAY" $VNC_AUTH -forever -shared -localhost -quiet -bg -o /tmp/x11vnc.log >/dev/null
# Listen on IPv6 too where the container has it (the socket then takes IPv4 as well): a proxy that resolves
# this container to its IPv6 address would otherwise get "connection refused".
if [ -e /proc/net/if_inet6 ]; then LISTEN="[::]:6080"; else LISTEN="6080"; fi
websockify --web /usr/share/novnc "$LISTEN" localhost:5900 >/tmp/websockify.log 2>&1 &

exec python3 -u /app/helper.py
