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
# The portal's cookie is a session cookie, which Chromium forgets when it
# closes. A copy is kept here so a restart of the container or the browser
# does not ask for a new login while the portal still accepts the session.
SESSION_FILE = "/data/session"
RETRY_INTERVAL = 60
NOTIFICATION_ID = "canal_de_isabel_ii_login_needed"

HA_URL = os.environ["HA_URL"].rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
if not HA_TOKEN:
    with open(os.environ["HA_TOKEN_FILE"], encoding="utf-8") as _token_file:
        HA_TOKEN = _token_file.read().strip()
HA_ENTRY_ID = os.environ.get("HA_ENTRY_ID", "")
HA_VERIFY_SSL = os.environ.get("HA_VERIFY_SSL", "true").lower() != "false"
HELPER_URL = os.environ.get("HELPER_URL", "")
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
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

def addon_ingress_url() -> str:
    """As an add-on, the path that opens this add-on's page in Home Assistant."""
    request = urllib.request.Request(
        "http://supervisor/addons/self/info",
        headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return f"/hassio/ingress/{json.load(response)['data']['slug']}"
    except (OSError, KeyError, ValueError) as err:
        log.warning("Could not ask the Supervisor for the add-on address: %s", err)
        return ""


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


def notify_login_needed() -> bool:
    where = f"[Open the helper browser]({HELPER_URL})" if HELPER_URL else "Open the helper browser"
    return call_ha(
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

    def set_session_cookie(self, value: str) -> None:
        self._call(
            "Network.setCookie",
            {
                "name": "JSESSIONID",
                "value": value,
                "url": BASE_URL,
                "path": "/",
                "secure": True,
                "httpOnly": True,
            },
        )


def saved_session() -> str:
    try:
        with open(SESSION_FILE, encoding="utf-8") as file:
            return file.read().strip()
    except OSError:
        return ""


def save_session(cookie: str) -> None:
    """Keep (or with an empty value, forget) the session for the next start."""
    try:
        if not cookie:
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
            return
        descriptor = os.open(SESSION_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(cookie)
    except OSError as err:
        log.warning("Could not update %s: %s", SESSION_FILE, err)


def wait_for_login(tab: Tab) -> None:
    """Leave the page alone until a person has logged in.

    The page is only reloaded when it sits on a portal page that should be
    the consumption page, or on no portal page at all (a failed load), and
    then at most once a minute.
    """
    notified = notify_login_needed()
    last_try = time.monotonic()
    last_open = float("-inf")
    while True:
        time.sleep(LOGIN_POLL)
        now = time.monotonic()
        if not notified and now - last_try >= RETRY_INTERVAL:
            # Home Assistant was not reachable when the login was first needed.
            notified = notify_login_needed()
            last_try = now
        url = tab.url()
        inside = url.startswith(f"{BASE_URL}/group/")
        if (inside or not url.startswith(BASE_URL)) and now - last_open >= RETRY_INTERVAL:
            tab.open(CONSUMPTION_URL)
            last_open = time.monotonic()
        if inside and tab.logged_in():
            return


def run(browser: subprocess.Popen) -> None:
    tab = Tab()
    sent = ""
    try:
        previous = saved_session()
        # The login page has already given the new browser a cookie of its
        # own; the kept one replaces it.
        if previous and previous != tab.session_cookie():
            log.info("Restoring the session kept from before the restart.")
            tab.set_session_cookie(previous)
        tab.open(CONSUMPTION_URL)
        while browser.poll() is None:
            if not tab.logged_in():
                save_session("")
                log.info("Not logged in. Waiting for a login in the helper browser.")
                wait_for_login(tab)
                log.info("Login detected.")

            cookie = tab.session_cookie()
            if cookie != saved_session():
                save_session(cookie)

            # Until the next check of the portal, keep offering the session
            # to Home Assistant if it did not take it (it may be restarting).
            next_check = time.monotonic() + CHECK_INTERVAL
            while True:
                if cookie and cookie != sent and send_session(cookie):
                    log.info("Session handed to Home Assistant.")
                    sent = cookie
                    dismiss_notification()
                remaining = next_check - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(remaining if cookie == sent or not cookie else min(RETRY_INTERVAL, remaining))
            tab.open(CONSUMPTION_URL)
    finally:
        tab.close()


def main() -> None:
    global HELPER_URL
    if SUPERVISOR_TOKEN and not HELPER_URL:
        HELPER_URL = addon_ingress_url()
    while True:
        browser = None
        try:
            browser = start_browser()
            run(browser)
        except Exception as err:  # the tab was closed, the browser crashed...
            log.warning("Restarting the browser after an error: %s", err)
        finally:
            if browser is not None:
                browser.kill()
                browser.wait()
        time.sleep(5)


if __name__ == "__main__":
    main()
