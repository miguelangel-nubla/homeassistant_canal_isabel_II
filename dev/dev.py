#!/usr/bin/env python3
"""Drive the throwaway Home Assistant in this folder (standard library only).

    python3 dev/dev.py setup      create the user, add the integration
    python3 dev/dev.py wanted     what the session helper would be asked to do
    python3 dev/dev.py session    deliver a session cookie, as the helper does
    python3 dev/dev.py status     entry state, sensors and stored statistics

Secrets are read from standard input, so they never show up in the shell
history or the process list: for setup, the document number and the
password of the virtual office, one per line; for session, a JSESSIONID.
"""
import json
import os
import pathlib
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).parent
# DEV_HA_URL / DEV_HA_STATE point the script at another instance, such as
# the Home Assistant OS VM started by dev/haos.sh.
URL = os.environ.get("DEV_HA_URL", "http://127.0.0.1:18123")
CONFIG = pathlib.Path(os.environ.get("DEV_HA_STATE", HERE / "config"))
TOKEN_FILE = CONFIG / ".dev_token"
DOMAIN = "canal_de_isabel_ii"
CONFIGURATION = """default_config:
logger:
  default: warning
  logs:
    custom_components.canal_de_isabel_ii: debug
"""


def call(path, data=None, token=None, form=False):
    headers = {}
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(URL + path, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read() or b"null")
    except urllib.error.HTTPError as err:
        sys.exit(f"{path}: HTTP {err.code} {err.read()[:300]!r}")


def wait_for_ha():
    for _ in range(120):
        try:
            urllib.request.urlopen(URL + "/manifest.json", timeout=3).close()
            return
        except OSError:
            time.sleep(2)
    sys.exit("Home Assistant did not start: docker compose -f dev/docker-compose.yml logs")


def token():
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    client = URL + "/"
    code = call(
        "/api/onboarding/users",
        {"client_id": client, "name": "Dev", "username": "dev", "password": "dev-dev-dev", "language": "en"},
    )["auth_code"]
    tokens = call(
        "/auth/token",
        {"grant_type": "authorization_code", "code": code, "client_id": client},
        form=True,
    )
    # A long-lived token needs the websocket API; the refresh token is enough here.
    TOKEN_FILE.write_text(tokens["refresh_token"])
    TOKEN_FILE.chmod(0o600)
    return tokens["refresh_token"]


def access_token():
    refresh = token()
    return call(
        "/auth/token",
        {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": URL + "/"},
        form=True,
    )["access_token"]


def read_line(what):
    line = sys.stdin.readline().strip()
    if not line:
        sys.exit(f"Give {what} on standard input")
    return line


def setup():
    wait_for_ha()
    auth = access_token()
    account = {
        "document": read_line("the document number"),
        "password": read_line("the password"),
        "profile": os.environ.get("DEV_PROFILE", "particular"),
    }
    flow = call("/api/config/config_entries/flow", {"handler": DOMAIN}, auth)
    result = call(f"/api/config/config_entries/flow/{flow['flow_id']}", account, auth)
    print("config flow:", result.get("type"), result.get("errors") or result.get("reason") or "")


def wanted():
    wait_for_ha()
    answer = call(f"/api/services/{DOMAIN}/session_request?return_response", {}, access_token())
    requests = answer["service_response"]["requests"]
    for request in requests:
        print("wants a session:", request["entry_id"], request["profile"], "(credentials not shown)")
    if not requests:
        print("no entry wants a session")


def session():
    wait_for_ha()
    call(f"/api/services/{DOMAIN}/set_session", {"jsessionid": read_line("the JSESSIONID")}, access_token())
    print("session delivered")


def status():
    wait_for_ha()
    auth = access_token()
    for entry in call("/api/config/config_entries/entry", token=auth):
        if entry["domain"] == DOMAIN:
            print("entry:", entry["state"], entry.get("reason") or "")
    for state in call("/api/states", token=auth):
        if state["entity_id"].startswith(f"sensor.{DOMAIN}"):
            unit = state["attributes"].get("unit_of_measurement", "")
            print("sensor:", state["entity_id"].rsplit("_", 1)[-1], state["state"], unit)
    if not (CONFIG / "home-assistant_v2.db").exists():
        return
    database = sqlite3.connect(f"file:{CONFIG / 'home-assistant_v2.db'}?mode=ro", uri=True)
    rows = database.execute(
        "select m.id, count(*), min(s.start_ts), max(s.start_ts), max(s.sum), "
        "sum(case when s.state < 0 then 1 else 0 end) "
        "from statistics_meta m join statistics s on s.metadata_id = m.id "
        "where m.source = ? group by m.id",
        (DOMAIN,),
    ).fetchall()
    for _id, count, first, last, total, negative in rows:
        fmt = lambda ts: time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
        print(f"statistic: {count} hours, {fmt(first)} to {fmt(last)}, total {total:.0f} L, negative hours {negative}")
    if not rows:
        print("statistic: nothing stored yet")


if __name__ == "__main__":
    CONFIG.mkdir(exist_ok=True)
    if "DEV_HA_STATE" not in os.environ and not (CONFIG / "configuration.yaml").exists():
        (CONFIG / "configuration.yaml").write_text(CONFIGURATION)
    commands = {"setup": setup, "wanted": wanted, "session": session, "status": status}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()
