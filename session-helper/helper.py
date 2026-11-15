"""Hold a portal session in a real browser and pass it to Home Assistant.

A person logs in to the Canal de Isabel II virtual office through the remote
view of this container's browser. This script never logs in: it waits for a
logged-in page, reads the session cookie, hands it to the integration with
the canal_de_isabel_ii.set_session service, and keeps checking the session.
When the portal ends the session it asks for a new login through a Home
Assistant notification.
"""
import glob
import json
import logging
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request

import websocket

BASE_URL = "https://oficinavirtual.canaldeisabelsegunda.es"
CONSUMPTION_URL = f"{BASE_URL}/group/ovir/consumo"
CDP = "http://127.0.0.1:9222"
PROFILE_DIR = "/data/profile"
NOTIFICATION_ID = "canal_de_isabel_ii_login_needed"

HA_URL = os.environ["HA_URL"].rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
if not HA_TOKEN:
    with open(os.environ["HA_TOKEN_FILE"], encoding="utf-8") as _token_file:
        HA_TOKEN = _token_file.read().strip()
HA_ENTRY_ID = os.environ.get("HA_ENTRY_ID", "")
HA_VERIFY_SSL = os.environ.get("HA_VERIFY_SSL", "true").lower() != "false"
HELPER_URL = os.environ.get("HELPER_URL", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "600"))
SCREEN_SIZE = os.environ.get("SCREEN_SIZE", "1280x800").replace("x", ",")
LOGIN_POLL = 5

# True once the page is a logged-in consumption page.
LOGGED_IN_JS = (
    "location.pathname.startsWith('/group/') && "
    "!!document.querySelector('a[href*=\"export-csv\"], #selectPeriodicidad')"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("helper")


# --- Home Assistant -------------------------------------------------------

def call_ha(service: str, data: dict) -> bool:
    """Call a Home Assistant service. Returns True on success."""
    request = urllib.request.Request(
        f"{HA_URL}/api/services/{service}",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    context = None
    if HA_URL.startswith("https") and not HA_VERIFY_SSL:
        context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=90, context=context):
            return True
    except urllib.error.HTTPError as err:
        log.warning("Home Assistant refused %s: HTTP %s %s", service, err.code, err.read()[:300])
    except OSError as err:
        log.warning("Home Assistant not reachable for %s: %s", service, err)
    return False


def send_session(jsessionid: str) -> bool:
    data = {"jsessionid": jsessionid}
    if HA_ENTRY_ID:
        data["entry_id"] = HA_ENTRY_ID
    return call_ha("canal_de_isabel_ii/set_session", data)


def notify_login_needed() -> None:
    where = f"[Open the helper browser]({HELPER_URL})" if HELPER_URL else "Open the helper browser"
    call_ha(
        "persistent_notification/create",
        {
            "notification_id": NOTIFICATION_ID,
            "title": "Canal de Isabel II: login needed",
            "message": f"There is no active portal session. {where} and log in to the virtual office.",
        },
    )


def dismiss_notification() -> None:
    call_ha("persistent_notification/dismiss", {"notification_id": NOTIFICATION_ID})


# --- Browser --------------------------------------------------------------

def start_browser() -> subprocess.Popen:
    """Start Chromium on the virtual screen with a local control port."""
    # A lock left by a previous container would stop Chromium from starting.
    for lock in glob.glob(f"{PROFILE_DIR}/Singleton*"):
        os.remove(lock)
    process = subprocess.Popen(
        [
            "chromium",
            f"--user-data-dir={PROFILE_DIR}",
            "--remote-debugging-port=9222",
            # Containers rarely allow Chromium's own sandbox. This browser is
            # only meant for the Canal de Isabel II portal.
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--password-store=basic",
            "--lang=es-ES",
            "--window-position=0,0",
            f"--window-size={SCREEN_SIZE}",
            CONSUMPTION_URL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{CDP}/json/version", timeout=2).close()
            return process
        except OSError:
            time.sleep(1)
    process.kill()
    raise RuntimeError("Chromium did not start")


class Tab:
    """The first browser tab, driven over Chromium's local control port."""

    def __init__(self) -> None:
        with urllib.request.urlopen(f"{CDP}/json/list", timeout=5) as response:
            pages = [t for t in json.load(response) if t.get("type") == "page"]
        if not pages:
            request = urllib.request.Request(f"{CDP}/json/new?{CONSUMPTION_URL}", method="PUT")
            with urllib.request.urlopen(request, timeout=5) as response:
                pages = [json.load(response)]
        self._ws = websocket.create_connection(
            pages[0]["webSocketDebuggerUrl"], timeout=30, suppress_origin=True
        )
        self._next_id = 0

    def close(self) -> None:
        self._ws.close()

    def _call(self, method: str, params: dict = None) -> dict:
        self._next_id += 1
        self._ws.send(json.dumps({"id": self._next_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self._ws.recv())
            if message.get("id") == self._next_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]

    def evaluate(self, expression: str):
        result = self._call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return result["result"].get("value")

    def url(self) -> str:
        return self.evaluate("location.href") or ""

    def open(self, url: str) -> None:
        """Navigate and wait for the page to finish loading."""
        self._call("Page.navigate", {"url": url})
        time.sleep(2)
        for _ in range(60):
            try:
                if self.evaluate("document.readyState") == "complete":
                    return
            except RuntimeError:
                pass  # page is mid-navigation
            time.sleep(1)

    def logged_in(self) -> bool:
        return bool(self.evaluate(LOGGED_IN_JS))

    def session_cookie(self) -> str:
        cookies = self._call("Network.getCookies", {"urls": [BASE_URL]})["cookies"]
        return next((c["value"] for c in cookies if c["name"] == "JSESSIONID"), "")


def wait_for_login(tab: Tab) -> None:
    """Leave the page alone until a person has logged in."""
    if not tab.url().startswith(BASE_URL):
        tab.open(CONSUMPTION_URL)  # redirects to the login form
    while True:
        time.sleep(LOGIN_POLL)
        url = tab.url()
        if url.startswith(f"{BASE_URL}/group/"):
            tab.open(CONSUMPTION_URL)
            if tab.logged_in():
                return


def run(browser: subprocess.Popen) -> None:
    tab = Tab()
    sent = ""
    try:
        tab.open(CONSUMPTION_URL)
        while browser.poll() is None:
            if not tab.logged_in():
                log.info("Not logged in. Waiting for a login in the helper browser.")
                notify_login_needed()
                wait_for_login(tab)
                log.info("Login detected.")

            cookie = tab.session_cookie()
            if cookie and cookie != sent:
                if send_session(cookie):
                    log.info("Session handed to Home Assistant.")
                    sent = cookie
                    dismiss_notification()

            time.sleep(CHECK_INTERVAL)
            tab.open(CONSUMPTION_URL)
    finally:
        tab.close()


def main() -> None:
    while True:
        browser = start_browser()
        try:
            run(browser)
        except Exception as err:  # the tab was closed, the browser crashed...
            log.warning("Restarting the browser after an error: %s", err)
        finally:
            browser.kill()
            browser.wait()
        time.sleep(5)


if __name__ == "__main__":
    main()
