"""Log in to the Canal de Isabel II virtual office for Home Assistant.

The integration canal_de_isabel_ii reads the portal with a browser session,
and the portal's login form runs an invisible reCAPTCHA, so the login has
to happen in a real browser. This is that browser.

It is a client of Home Assistant and nothing calls it. Every minute it asks
the integration which accounts want a session (service session_request,
which also gives the credentials). For each one it logs in, hands the
session cookie over (set_session), or says why it could not (report_login)
so that the integration can tell the person. In between it does nothing:
no session is kept alive.

Nothing here answers or avoids the captcha. If it asks for a challenge, or
the portal refuses the login, a person is asked to step in, and can log in
by hand through the remote view of this browser. The portal's cookie dialog
is answered with "allow all".
"""
import glob
import hashlib
import json
import logging
import os
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.request

import websocket

# PORTAL_URL exists for the tests, which run a fake portal.
BASE_URL = os.environ.get("PORTAL_URL", "https://oficinavirtual.canaldeisabelsegunda.es").rstrip("/")
CONSUMPTION_URL = f"{BASE_URL}/group/ovir/consumo"
CDP = "http://127.0.0.1:9222"
PROFILE_DIR = "/data/profile"
# What the automatic login remembers between restarts (see AutoLogin).
LOGIN_STATE_FILE = "/data/login_state"

HA_URL = os.environ["HA_URL"].rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
if not HA_TOKEN:
    with open(os.environ["HA_TOKEN_FILE"], encoding="utf-8") as _token_file:
        HA_TOKEN = _token_file.read().strip()
HA_VERIFY_SSL = os.environ.get("HA_VERIFY_SSL", "true").lower() != "false"
HELPER_URL = os.environ.get("HELPER_URL", "")
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
SCREEN_SIZE = os.environ.get("SCREEN_SIZE", "1280x800").replace("x", ",")
# Seconds between questions to Home Assistant. They never reach the portal.
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))

# The profile to choose on the login form, by the id of its radio button.
PROFILES = {
    "particular": "radioParticularLoginDesktop",
    "empresa": "radioEmpresaLoginDesktop",
    "administrador": "radioAdministradorFincasLoginDesktop",
    "entidad_publica": "radioEntidadesPublicasLoginDesktop",
}

# How long a login may take from the click to the logged-in page.
LOGIN_TIMEOUT = int(os.environ.get("LOGIN_TIMEOUT", "90"))
# A login the portal refused is tried again after these waits and then no
# more: repeating a wrong password could get the account locked.
REFUSED_DELAYS = (3600, 6 * 3600)
# A login that could not be completed (the portal is down, the page did not
# load, a captcha challenge nobody answered) is tried again, forever.
FAILED_DELAYS = (300, 900, 1800, 3600)
# While a login is not due, Home Assistant is reminded of why this often.
# It forgets when it restarts.
REPORT_INTERVAL = int(os.environ.get("REPORT_INTERVAL", "600"))

LOGIN_OK = "ok"
LOGIN_REFUSED = "refused"      # the portal answered the login with the form again
LOGIN_CHALLENGE = "challenge"  # the captcha wants a person
LOGIN_FAILED = "failed"        # no answer that could be understood

LOGIN_FORM_JS = (
    "!!document.querySelector('#btLogin') && !!document.querySelector('#numeroDocumento')"
    " && !!document.querySelector('#passwordFieldHidden')"
)
# True when the form holds something this script did not write there.
TYPED_BY_PERSON_JS = (
    "!window.__helperLogin && ['numeroDocumento', 'passwordFieldHidden']"
    ".some(id => (document.getElementById(id) || {}).value)"
)
CAPTCHA_READY_JS = (
    "typeof grecaptcha !== 'undefined' && !!grecaptcha.enterprise"
    " && typeof recaptchaLogin !== 'undefined'"
)
# reCAPTCHA shows its challenge in this frame, hidden until it is needed.
CAPTCHA_CHALLENGE_JS = """
[...document.querySelectorAll('iframe[src*="recaptcha"][src*="bframe"]')].some(frame => {
    const box = frame.getBoundingClientRect();
    let visible = box.width > 0 && box.height > 0;
    for (let node = frame; node && visible; node = node.parentElement) {
        const style = getComputedStyle(node);
        if (style.visibility === 'hidden' || style.display === 'none') visible = false;
    }
    return visible;
})
"""
# The portal asks about cookies with a Cookiebot dialog, which stays on top
# of the page until it is answered. The helper answers "allow all": with
# fewer cookies parts of the portal may not work.
COOKIES_UNANSWERED_JS = (
    "typeof Cookiebot !== 'undefined' && !Cookiebot.consented && !Cookiebot.declined"
)
COOKIES_ALLOW_ALL_ID = "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"
COOKIES_BUTTON_JS = f"!!(document.getElementById('{COOKIES_ALLOW_ALL_ID}') || {{}}).offsetParent"

# What is written in the elements that match a selector and are on screen
# (the page also carries hidden messages), for the log and the notification.
_SHOWN_TEXT_JS = """
[...document.querySelectorAll('%s')].filter(node => node.getClientRects().length)
    .map(node => node.innerText.replace(/\\s+/g, ' ').trim()).filter(Boolean).join(' / ').slice(0, 200)
"""
# The form's own complaints, before anything is sent.
FORM_COMPLAINTS_JS = _SHOWN_TEXT_JS % "#login-form label.error, #login-form .invalid.d-block"
# The portal's answer to a login it did not accept.
PORTAL_ERRORS_JS = _SHOWN_TEXT_JS % (
    '[role="alert"], .alert-danger, .alert-error, .portlet-msg-error, #login-form .invalid.d-block'
)

# True on any page behind the login.
INSIDE_JS = "location.pathname.startsWith('/group/')"
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


_ha_problem = ""


def call_ha(service: str, data: dict):
    """Call a Home Assistant service. Returns its answer, or None if it failed.

    A problem that repeats is logged once, not on every call.
    """
    global _ha_problem
    request = urllib.request.Request(
        f"{HA_URL}/api/services/{service}",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    context = None
    if HA_URL.startswith("https") and not HA_VERIFY_SSL:
        context = ssl._create_unverified_context()
    name = service.split("?")[0]
    try:
        with urllib.request.urlopen(request, timeout=90, context=context) as response:
            answer = json.load(response)
        if _ha_problem:
            log.info("Home Assistant answers again.")
            _ha_problem = ""
        return answer
    except urllib.error.HTTPError as err:
        problem = f"Home Assistant refused {name}: HTTP {err.code} {err.read()[:300]}"
    except (OSError, ValueError) as err:
        problem = f"Home Assistant not reachable for {name}: {err}"
    if problem != _ha_problem:
        log.warning("%s", problem)
        _ha_problem = problem
    return None


def ask_for_work() -> list:
    """The accounts that want a session now, each with its credentials."""
    answer = call_ha(
        "canal_de_isabel_ii/session_request?return_response",
        {"helper_url": HELPER_URL} if HELPER_URL else {},
    )
    try:
        return answer["service_response"]["requests"]
    except (KeyError, TypeError):
        return []


def send_session(entry_id: str, jsessionid: str) -> bool:
    answer = call_ha("canal_de_isabel_ii/set_session", {"entry_id": entry_id, "jsessionid": jsessionid})
    return answer is not None


def report_login(entry_id: str, outcome: str, detail: str, next_try) -> None:
    """Tell the integration that the login did not work, so it tells the person."""
    data = {"entry_id": entry_id, "result": outcome}
    if detail:
        data["detail"] = detail
    if next_try is not None:
        data["retry_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(next_try))
    if HELPER_URL:
        data["helper_url"] = HELPER_URL
    call_ha("canal_de_isabel_ii/report_login", data)


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
            # Nothing is asked of the portal until Home Assistant wants a session.
            "about:blank",
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
            request = urllib.request.Request(f"{CDP}/json/new?about:blank", method="PUT")
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

    def wait_for(self, expression: str, seconds: int) -> bool:
        """Wait until the expression is true. False if it never was."""
        deadline = time.monotonic() + seconds
        while True:
            try:
                if self.evaluate(expression):
                    return True
            except RuntimeError:
                pass  # page is mid-navigation
            if time.monotonic() >= deadline:
                return False
            time.sleep(1)

    def allow_cookies(self, wait: int = 0) -> None:
        """Answer the cookie dialog, if the page is asking, with "allow all"."""
        try:
            if not self.evaluate(COOKIES_UNANSWERED_JS) or not self.wait_for(COOKIES_BUTTON_JS, wait):
                return
            self.evaluate(f"document.getElementById('{COOKIES_ALLOW_ALL_ID}').click()")
            self.wait_for(f"!({COOKIES_BUTTON_JS})", 5)
            log.info("Cookie dialog answered: all cookies allowed.")
        except RuntimeError:
            pass  # page is mid-navigation; the dialog comes back on the next page

    def type_into(self, element_id: str, text: str) -> bool:
        """Replace the content of a field, as typing does. True if it took it.

        The text travels as keyboard input and never as part of a script, so
        it cannot end up in an error message or a log.
        """
        self.evaluate(
            f"(() => {{ const field = document.getElementById('{element_id}');"
            " field.focus(); field.select(); })()"
        )
        self._call("Input.insertText", {"text": text})
        length = self.evaluate(f"document.getElementById('{element_id}').value.length")
        return length == len(text)

    def click(self, element_id: str) -> None:
        """Click an element: with the mouse if it can be reached, else directly.

        Something may lie on top of the element. The portal's cookie dialog
        covers the login button in a browser that has never answered it.
        """
        box = self.evaluate(
            f"(() => {{ const node = document.getElementById('{element_id}');"
            " node.scrollIntoView({block: 'center'});"
            " const box = node.getBoundingClientRect();"
            " const x = box.left + box.width / 2, y = box.top + box.height / 2;"
            " return {x, y, reachable: node.contains(document.elementFromPoint(x, y))}; })()"
        )
        if not box["reachable"]:
            self.evaluate(f"document.getElementById('{element_id}').click()")
            return
        for event in ("mousePressed", "mouseReleased"):
            self._call(
                "Input.dispatchMouseEvent",
                {"type": event, "x": box["x"], "y": box["y"], "button": "left", "clickCount": 1},
            )

    def session_cookie(self) -> str:
        cookies = self._call("Network.getCookies", {"urls": [BASE_URL]})["cookies"]
        return next((c["value"] for c in cookies if c["name"] == "JSESSIONID"), "")

    def forget_session(self) -> None:
        """Log out, as far as the browser is concerned."""
        self._call("Network.deleteCookies", {"name": "JSESSIONID", "url": BASE_URL})


class AutoLogin:
    """When the login of an account may be tried, remembered across restarts.

    A restart must not be a way to try a refused password again, so the
    count of refusals and the time of the next try are kept in /data. They
    are forgotten when the credentials are entered again in Home Assistant
    or a login succeeds, by this script or by a person.
    """

    def __init__(self, request: dict) -> None:
        self._entry_id = request["entry_id"]
        # Tells one entering of the credentials from another without keeping them.
        self._key = hashlib.sha256(
            "\0".join(
                str(request.get(field, ""))
                for field in ("profile", "document", "password", "credentials_set_at")
            ).encode()
        ).hexdigest()
        self.refusals = 0
        self.failures = 0
        self.next_try = 0.0  # epoch seconds; None when no more tries are due
        self.outcome = ""    # how the last try ended, if it did not log in
        self.detail = ""
        try:
            state = self._read()[self._entry_id]
            if state["key"] == self._key:
                self.refusals = int(state["refusals"])
                self.failures = int(state["failures"])
                self.next_try = state["next_try"]
                self.outcome = str(state["outcome"])
                self.detail = str(state["detail"])
        except (KeyError, ValueError, TypeError):
            pass

    @staticmethod
    def _read() -> dict:
        try:
            with open(LOGIN_STATE_FILE, encoding="utf-8") as file:
                states = json.load(file)
            return states if isinstance(states, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        states = self._read()
        states[self._entry_id] = {
            "key": self._key,
            "refusals": self.refusals,
            "failures": self.failures,
            "next_try": self.next_try,
            "outcome": self.outcome,
            "detail": self.detail,
        }
        try:
            descriptor = os.open(LOGIN_STATE_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(states, file)
        except OSError as err:
            log.warning("Could not update %s: %s", LOGIN_STATE_FILE, err)

    def due(self) -> bool:
        return self.next_try is not None and time.time() >= self.next_try

    def record(self, outcome: str, detail: str = "") -> None:
        """Note how a try ended and decide when the next one is."""
        if outcome == LOGIN_OK:
            self.reset()
            return
        self.outcome, self.detail = outcome, detail
        if outcome == LOGIN_REFUSED:
            self.refusals += 1
            if self.refusals > len(REFUSED_DELAYS):
                self.next_try = None
            else:
                self.next_try = time.time() + REFUSED_DELAYS[self.refusals - 1]
        else:
            self.failures += 1
            delay = FAILED_DELAYS[min(self.failures, len(FAILED_DELAYS)) - 1]
            if outcome == LOGIN_CHALLENGE:
                # Leave the challenge on screen for a person to answer.
                delay = FAILED_DELAYS[-1]
            self.next_try = time.time() + delay
        self._save()

    def reset(self) -> None:
        if self.refusals or self.failures or self.next_try or self.outcome:
            self.refusals = self.failures = 0
            self.next_try = 0.0
            self.outcome = self.detail = ""
            self._save()


def attempt_login(tab: Tab, request: dict) -> tuple:
    """Fill in the login form and send it. Returns (outcome, detail)."""
    # A form this script has already written in is not used again.
    if not tab.evaluate(f"{LOGIN_FORM_JS} && !window.__helperLogin"):
        tab.open(CONSUMPTION_URL)  # without a session the portal answers with the login form
    if tab.logged_in():
        return LOGIN_OK, ""
    if not tab.wait_for(LOGIN_FORM_JS, 20):
        return LOGIN_FAILED, "the login form did not appear"
    # The button does nothing until the captcha script has loaded.
    if not tab.wait_for(CAPTCHA_READY_JS, 30):
        return LOGIN_FAILED, "the captcha of the login form did not load"
    tab.allow_cookies(wait=10)

    document = str(request["document"]).strip().upper()
    document_type = "NIE" if re.match(r"[XYZ]\d", document) else "NIF"
    profile = PROFILES.get(request.get("profile"), PROFILES["particular"])
    tab.evaluate(
        "(() => { window.__helperLogin = true;"
        f" document.getElementById('{profile}').click();"
        " const type = document.getElementById('tipoDocumento');"
        f" if (type) {{ type.value = '{document_type}';"
        " type.dispatchEvent(new Event('change', {bubbles: true})); } })()"
    )
    if not tab.type_into("numeroDocumento", document) or not tab.type_into(
        "passwordFieldHidden", str(request["password"])
    ):
        return LOGIN_FAILED, "the login form did not take the credentials"
    tab.click("btLogin")

    # The page that answers the login no longer carries the mark set above.
    deadline = time.monotonic() + LOGIN_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(2)
        try:
            if tab.evaluate("document.readyState") != "complete":
                continue
            if tab.evaluate("window.__helperLogin"):
                # Still on the form: it is waiting for the captcha, or it
                # found something wrong before sending anything.
                if tab.evaluate(CAPTCHA_CHALLENGE_JS):
                    return LOGIN_CHALLENGE, ""
                complaint = tab.evaluate(FORM_COMPLAINTS_JS)
                if complaint:
                    return LOGIN_REFUSED, complaint
                continue
            if tab.evaluate(INSIDE_JS):
                if not tab.logged_in():
                    tab.open(CONSUMPTION_URL)
                if tab.logged_in():
                    return LOGIN_OK, ""
                return LOGIN_FAILED, "logged in, but the consumption page did not open"
            if tab.evaluate(LOGIN_FORM_JS):
                return LOGIN_REFUSED, tab.evaluate(PORTAL_ERRORS_JS) or ""
        except RuntimeError:
            pass  # page is mid-navigation
    return LOGIN_FAILED, "the portal did not answer the login"


def deliver(tab: Tab, request: dict, auto: AutoLogin) -> None:
    """Hand the browser's session to Home Assistant."""
    auto.reset()  # logged in: the refusals are history
    if send_session(request["entry_id"], tab.session_cookie()):
        log.info("Session handed to Home Assistant.")
        # Leave the portal: an open page of it could keep talking to it.
        tab.open("about:blank")


def serve(tab: Tab, request: dict, memory: dict) -> None:
    """Get Home Assistant the session it wants for one account.

    The portal is only visited when there is something to do there: to log
    in when a login is due, or to check on a page that looks logged in (a
    person may have logged in through the remote view). While a failed
    login waits for its next try, the login form stays on screen untouched.
    """
    entry_id = request["entry_id"]
    auto = AutoLogin(request)
    if memory["owner"] != entry_id:
        # The browser holds no session, or that of another account.
        tab.forget_session()
        memory["owner"] = entry_id
        tab.open(CONSUMPTION_URL)
    elif tab.evaluate(INSIDE_JS):
        tab.open(CONSUMPTION_URL)
    if tab.logged_in():
        deliver(tab, request, auto)
        return

    if not auto.due():
        # Home Assistant forgets a report when it restarts: remind it.
        if time.monotonic() - memory["reported"].get(entry_id, float("-inf")) >= REPORT_INTERVAL:
            report_login(entry_id, auto.outcome or LOGIN_FAILED, auto.detail, auto.next_try)
            memory["reported"][entry_id] = time.monotonic()
        return
    if tab.evaluate(TYPED_BY_PERSON_JS):
        return  # a person is filling in the form

    log.info("Logging in.")
    try:
        outcome, detail = attempt_login(tab, request)
    except (RuntimeError, TypeError, KeyError) as err:
        outcome, detail = LOGIN_FAILED, f"the browser did not follow: {err}"
    auto.record(outcome, detail)
    if outcome == LOGIN_OK:
        log.info("Logged in.")
        deliver(tab, request, auto)
        return
    if outcome == LOGIN_REFUSED:
        log.warning("The portal refused the login%s.", f": {detail}" if detail else "")
    elif outcome == LOGIN_CHALLENGE:
        log.warning("The captcha of the login form asks for a person.")
    else:
        log.warning("The login could not be completed: %s.", detail)
    if auto.next_try is None:
        log.warning("No more logins until the credentials are entered again or a person logs in.")
    else:
        log.info("Next login at %s.", time.strftime("%H:%M", time.localtime(auto.next_try)))
    report_login(entry_id, outcome, detail, auto.next_try)
    memory["reported"][entry_id] = time.monotonic()


def run(browser: subprocess.Popen) -> None:
    tab = Tab()
    # Whose session the browser holds, and when each account's failure was last reported.
    memory = {"owner": None, "reported": {}}
    try:
        while browser.poll() is None:
            for request in ask_for_work():
                serve(tab, request, memory)
            time.sleep(POLL_INTERVAL)
    finally:
        tab.close()


def main() -> None:
    global HELPER_URL
    if SUPERVISOR_TOKEN and not HELPER_URL:
        HELPER_URL = addon_ingress_url()
    log.info("Waiting for Home Assistant to want a portal session.")
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
